import os
import time
import json
import asyncio
import logging
import paho.mqtt.client as mqtt
import aiohttp
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod

async def on_request_start(session, trace_config_ctx, params):
    logging.info(f"HTTP Request: {params.method} {params.url}")

async def on_request_end(session, trace_config_ctx, params):
    logging.info(f"HTTP Response: {params.response.status} for {params.method} {params.url}")

async def get_docsis_data(modem_hostname, modem_username, modem_password, encryption_method):
    """
    Retrieves DOCSIS information from the Sagemcom modem.
    """
    trace_config = aiohttp.TraceConfig()
    trace_config.on_request_start.append(on_request_start)
    trace_config.on_request_end.append(on_request_end)
    
    connector = aiohttp.TCPConnector(ssl=False)
    jar = aiohttp.CookieJar(unsafe=True)

    try:
        async with aiohttp.ClientSession(
            connector=connector,
            cookie_jar=jar,
            trace_configs=[trace_config]
        ) as session:
            async with SagemcomClient(modem_hostname, modem_username, modem_password, encryption_method, session=session) as client:
                await client.login()
                device_info = await client.get_device_info()
                wan_info = await client.get_wan_information()

                if wan_info.get('interface_type') != 'DOCSIS':
                    logging.error("Error: Modem is not in DOCSIS mode.")
                    return None
                
                docsis_info = wan_info.get('docsis_info', {})
                
                downstream_channels = docsis_info.get('downstream', [])
                upstream_channels = docsis_info.get('upstream', [])

                if not downstream_channels or not upstream_channels:
                    return {
                        "registration_status": docsis_info.get('registration_status'),
                        "operational_status": "Not available",
                        "error": "Downstream or upstream channel data not found"
                    }

                ds_power = [ch['power'] for ch in downstream_channels if 'power' in ch]
                ds_snr = [ch['snr'] for ch in downstream_channels if 'snr' in ch]
                us_power = [ch['power'] for ch in upstream_channels if 'power' in ch]

                data = {
                    "registration_status": docsis_info.get('registration_status'),
                    "operational_status": docsis_info.get('operational_status'),
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
        logging.error(f"An error occurred: {e}", exc_info=True)
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
        logging.error("Error: MODEM_HOSTNAME, MODEM_USERNAME, and MODEM_PASSWORD must be set.")
        return

    if encryption_str == "MD5":
        encryption_method = EncryptionMethod.MD5
    else:
        encryption_method = EncryptionMethod.SHA512

    # One-shot test mode
    if not mqtt_hostname:
        logging.info("MQTT_HOSTNAME not set. Running in one-shot test mode.")
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
        logging.error(f"Error connecting to MQTT broker: {e}")
        return

    while True:
        data = await get_docsis_data(modem_hostname, modem_username, modem_password, encryption_method)
        if data:
            mqtt_client.publish(mqtt_topic, payload=json.dumps(data), qos=0, retain=False)
            logging.info(f"Published data to MQTT topic '{mqtt_topic}'")
        else:
            logging.warning("Failed to retrieve data from modem.")

        await asyncio.sleep(poll_interval)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    asyncio.run(main()) 