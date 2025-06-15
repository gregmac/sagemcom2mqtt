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
import traceback

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

def parse_docsis_data(device_info):
    """
    Parses the DOCSIS information from the raw device info dictionary.
    """
    if not device_info:
        _LOGGER.error("Device info is empty, cannot parse DOCSIS data.")
        return None

    # Navigate the structure in Python
    docsis_data = device_info.get("device", {}).get("docsis", {})
    cable_modem = docsis_data.get("cable_modem", {})
    downstream_channels = cable_modem.get("downstreams", [])
    upstream_channels = cable_modem.get("upstreams", [])

    if not downstream_channels and not upstream_channels:
        _LOGGER.error("Could not retrieve any DOCSIS information. Please check XPaths and modem mode.")
        return None

    ds_power = [float(ch['power_level']) for ch in downstream_channels if 'power_level' in ch and ch.get('power_level')]
    us_power = [float(ch['power_level']) for ch in upstream_channels if 'power_level' in ch and ch.get('power_level')]

    ds_snr = [float(ch['SNR']) for ch in downstream_channels if 'SNR' in ch and ch.get('SNR')]

    correctable = sum([int(ch['correctable_codewords']) for ch in downstream_channels if 'correctable_codewords' in ch and ch.get('correctable_codewords')])
    uncorrectable = sum([int(ch['uncorrectable_codewords']) for ch in downstream_channels if 'uncorrectable_codewords' in ch and ch.get('uncorrectable_codewords')])

    # Prepare data for MQTT
    data = {
        'ds_power_avg': round(sum(ds_power) / len(ds_power), 2) if ds_power else 0,
        'us_power_avg': round(sum(us_power) / len(us_power), 2) if us_power else 0,
        'ds_snr_avg': round(sum(ds_snr) / len(ds_snr), 2) if ds_snr else 0,
        'correctable_sum': correctable,
        'uncorrectable_sum': uncorrectable,
        'downstream_channels': len(downstream_channels),
        'upstream_channels': len(upstream_channels),
    }

    return data

# Create a TraceConfig for logging HTTP requests
trace_config = aiohttp.TraceConfig()
trace_config.on_request_start.append(on_request_start)
trace_config.on_request_end.append(on_request_end)

async def get_docsis_data(modem_hostname, modem_username, modem_password, encryption_method):
    """
    Retrieves DOCSIS information from the Sagemcom modem.
    """
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

                # Fetch the entire device tree at once, as deep paths are not supported.
                device_info = await client.get_value_by_xpath("Device") or {}

                return parse_docsis_data(device_info)

    except Exception as e:
        _LOGGER.error(f"An error occurred: {e}")
        traceback.print_exc()
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
        docsis_data = await get_docsis_data(modem_hostname, modem_username, modem_password, encryption_method)

        if docsis_data:
            # Publish to MQTT
            mqtt_client.publish(mqtt_topic, json.dumps(docsis_data))
            _LOGGER.info(f"Published to {mqtt_topic}: {docsis_data}")

        # Wait for the next interval
        await asyncio.sleep(poll_interval)

if __name__ == "__main__":
    asyncio.run(main()) 