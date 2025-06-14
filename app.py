import os
import time
import json
import asyncio
import logging
import sys
import aiohttp
import paho.mqtt.client as mqtt
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod

# Basic logging configuration for the application
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)

# Set paho-mqtt log level to INFO to avoid excessive messages
logging.getLogger("paho").setLevel(logging.INFO)

# --- aiohttp tracing functions ---
async def on_request_start(session, trace_config_ctx, params):
    _LOGGER.info(f"Starting request: {params.method} {params.url}")

async def on_request_end(session, trace_config_ctx, params):
    _LOGGER.info(f"Request finished: {params.method} {params.url} -> {params.response.status}")

async def get_docsis_data(modem_hostname, modem_username, modem_password, encryption_method):
    """
    Retrieves DOCSIS information from the Sagemcom modem.
    """
    # Create a TraceConfig for logging HTTP requests
    trace_config = aiohttp.TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)

    # Create a connector to disable SSL certificate verification while still using SSL
    connector = aiohttp.TCPConnector(ssl=True, verify_ssl=False)

    try:
        # Create a client session with our trace config and custom connector
        async with aiohttp.ClientSession(
            trace_configs=[trace_config], connector=connector
        ) as session:
            async with SagemcomClient(
                modem_hostname,
                modem_username,
                modem_password,
                encryption_method,
                ssl=True,  # This is required to use HTTPS for the URL
                session=session  # Pass the configured session to the client
            ) as client:
                await client.login()

                # These XPaths are common, but may need to be adjusted for your modem.
                # Use discover.py to find the correct paths for your device.
                #interface_info = await client.get_value_by_xpath("Device/Docsis/Interface/1") or {}
                cable_modem = await client.get_value_by_xpath("device/docsis/cable_modem") or {}
                downstream_raw = await client.get_value_by_xpath("device/docsis/cable_modem/downstreams") or {}
                upstream_raw = await client.get_value_by_xpath("device/docsis/cable_modem/upstreams") or {}

                if not downstream_raw and not downstream_raw and not upstream_raw:
                    _LOGGER.error("Could not retrieve any DOCSIS information. Please check XPaths and modem mode.")
                    return None

                downstream_channels = list(downstream_raw.values())
                upstream_channels = list(upstream_raw.values())

                ds_power = [float(ch['power_level']) for ch in downstream_channels if 'power_level' in ch and ch.get('power_level')]
                ds_snr = [float(ch['SNR']) for ch in downstream_channels if 'SNR' in ch and ch.get('SNR')]
                us_power = [float(ch['power_level']) for ch in upstream_channels if 'power_level' in ch and ch.get('power_level')]

                data = {
                    "status": cable_modem.get('status'),
                    #"operational_status": interface_info.get('OperationalStatus'),
                    "downstream_channels_connected": len(downstream_channels),
                    "downstream_power_min_dbmv": min(ds_power) if ds_power else None,
                    "downstream_power_avg_dbmv": round(sum(ds_power) / len(ds_power), 2) if ds_power else None,
                    "downstream_power_max_dbmv": max(ds_power) if ds_power else None,
                    "downstream_snr_avg_db": round(sum(ds_snr) / len(ds_snr), 2) if ds_snr else None,
                    "downstream_snr_max_db": max(ds_snr) if ds_snr else None,
                    "upstream_channels_connected": len(upstream_channels),
                    "upstream_power_min_dbmv": min(us_power) if us_power else None,
                    "upstream_power_avg_dbmv": round(sum(us_power) / len(us_power), 2) if us_power else None,
                    "upstream_power_max_dbmv": max(us_power) if us_power else None,
                }
                return data

    except Exception as e:
        _LOGGER.error(f"An error occurred: {e}", exc_info=True)
        return None

async def main():
    # Get configuration from environment variables
    modem_hostname = os.getenv("MODEM_HOSTNAME")
    modem_username = os.getenv("MODEM_USERNAME")
    modem_password = os.getenv("MODEM_PASSWORD")
    encryption_str = os.getenv("MODEM_ENCRYPTION", "SHA512").upper()
    poll_interval = int(os.getenv("POLL_INTERVAL", 30))
    mqtt_hostname = os.getenv("MQTT_HOSTNAME")
    mqtt_port = int(os.getenv("MQTT_PORT", 1883))
    mqtt_username = os.getenv("MQTT_USERNAME")
    mqtt_password = os.getenv("MQTT_PASSWORD")
    mqtt_topic = os.getenv("MQTT_TOPIC", "sagemcom/docsis/status")

    if not all([modem_hostname, modem_username, modem_password]):
        _LOGGER.error("Error: MODEM_HOSTNAME, MODEM_USERNAME, and MODEM_PASSWORD must be set.")
        return

    if encryption_str == "MD5":
        encryption_method = EncryptionMethod.MD5
    else:
        encryption_method = EncryptionMethod.SHA512

    # One-shot test mode
    if not mqtt_hostname:
        _LOGGER.info("MQTT_HOSTNAME not set. Running in one-shot test mode.")
        data = await get_docsis_data(modem_hostname, modem_username, modem_password, encryption_method)
        if data:
            print(json.dumps(data, indent=4))
        return

    # MQTT mode
    mqtt_client = mqtt.Client()
    if mqtt_username:
        mqtt_client.username_pw_set(mqtt_username, mqtt_password)
    
    try:
        mqtt_client.connect(mqtt_hostname, mqtt_port, 60)
        mqtt_client.loop_start()
    except Exception as e:
        _LOGGER.error(f"Error connecting to MQTT broker: {e}")
        return

    while True:
        data = await get_docsis_data(modem_hostname, modem_username, modem_password, encryption_method)
        if data:
            mqtt_client.publish(mqtt_topic, payload=json.dumps(data), qos=0, retain=False)
            _LOGGER.info(f"Published data to MQTT topic '{mqtt_topic}'")
        else:
            _LOGGER.warning("Failed to retrieve data from modem.")

        await asyncio.sleep(poll_interval)

if __name__ == "__main__":
    asyncio.run(main()) 