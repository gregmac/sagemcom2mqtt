import os
import time
import json
import asyncio
import logging
import sys
import aiohttp
import paho.mqtt.client as mqtt
from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod
import traceback

__version__ = "1.1.0"

# Get log level from environment variable, default to INFO
log_level_name = os.getenv('LOG_LEVEL', 'INFO').upper()
# Ensure the log level is a valid one
try:
    log_level = getattr(logging, log_level_name)
except AttributeError:
    log_level = logging.INFO # Default to INFO if invalid level is provided

# Basic logging configuration for the application
logging.basicConfig(
    level=log_level,
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
    Returns a tuple of (mqtt_data, device_metadata).
    """
    if not device_info:
        _LOGGER.error("Device info is empty, cannot parse DOCSIS data.")
        return None, None

    # Navigate the structure in Python
    device_info_data = device_info.get("device", {}).get("device_info", {})
    docsis_data = device_info.get("device", {}).get("docsis", {})
    cable_modem = docsis_data.get("cable_modem", {})
    downstream_channels = cable_modem.get("downstreams", [])
    upstream_channels = cable_modem.get("upstreams", [])

    if not downstream_channels and not upstream_channels:
        _LOGGER.error("Could not retrieve any DOCSIS information. Please check XPaths and modem mode.")
        return None, None

    # Find the specific WAN IPv4 address by iterating through the interfaces
    wan_ipv4_address = None
    ip_interfaces = device_info.get("device", {}).get("IP", {}).get("interfaces", [])
    for interface in ip_interfaces:
        ipv4_addresses = interface.get("i_pv4_addresses", [])
        for address in ipv4_addresses:
            if address.get("alias") == "IP_DATA_ADDRESS":
                wan_ipv4_address = address.get("ip_address")
                break  # Found it, no need to search further in this interface
        if wan_ipv4_address:
            break  # Found it, no need to search further in other interfaces
            
    ds_power = [float(ch['power_level']) for ch in downstream_channels if 'power_level' in ch and ch.get('power_level')]
    us_power = [float(ch['power_level']) for ch in upstream_channels if 'power_level' in ch and ch.get('power_level')]
    ds_snr = [float(ch['SNR']) for ch in downstream_channels if 'SNR' in ch and ch.get('SNR')]
    correctable = sum([int(ch['correctable_codewords']) for ch in downstream_channels if 'correctable_codewords' in ch and ch.get('correctable_codewords')])
    uncorrectable = sum([int(ch['uncorrectable_codewords']) for ch in downstream_channels if 'uncorrectable_codewords' in ch and ch.get('uncorrectable_codewords')])

    # Data to be published to MQTT
    mqtt_data = {
        'status': cable_modem.get('status', 'UNKNOWN'),
        'ipv4_address': wan_ipv4_address,
        'downstream': {
            'power_avg_dbmv': round(sum(ds_power) / len(ds_power), 1) if ds_power else 0,
            'power_min_dbmv': round(min(ds_power), 1) if ds_power else 0,
            'power_max_dbmv': round(max(ds_power), 1) if ds_power else 0,
            'snr_avg_db': round(sum(ds_snr) / len(ds_snr), 2) if ds_snr else 0,
            'channels': len(downstream_channels),
            'correctable_sum': correctable,
            'uncorrectable_sum': uncorrectable,
        },
        'upstream': {
            'power_avg_dbmv': round(sum(us_power) / len(us_power), 1) if us_power else 0,
            'power_min_dbmv': round(min(us_power), 1) if us_power else 0,
            'power_max_dbmv': round(max(us_power), 1) if us_power else 0,
            'channels': len(upstream_channels),
        }
    }

    # Add system metrics to MQTT data and collect device metadata
    process_status = device_info_data.get("process_status", {})
    memory_status = device_info_data.get("memory_status", {})
    
    mqtt_data['system'] = {
        'cpu_usage': int(process_status.get("cpu_usage") or 0),
        'load_average_1m': round(float(process_status.get("load_average", {}).get("load1") or 0.0), 2),
        'free_memory_percentage': int(memory_status.get("free_memory_percentage") or 0),
    }

    device_metadata = {
        'serial_number': device_info_data.get('serial_number'),
        'manufacturer': device_info_data.get('manufacturer'),
        'model_number': device_info_data.get('model_number'),
        'mac_address': device_info_data.get('mac_address'),
        'hardware_version': device_info_data.get('hardware_version'),
        'software_version': device_info_data.get('software_version'),
    }

    return mqtt_data, device_metadata

# Create a TraceConfig for logging HTTP requests
trace_config = aiohttp.TraceConfig()
trace_config.on_request_start.append(on_request_start)
trace_config.on_request_end.append(on_request_end)

def publish_ha_discovery_config(mqtt_client, discovery_prefix, device_metadata, base_topic):
    """Publishes the Home Assistant discovery configuration for all sensors."""
    _LOGGER.info(f"Publishing Home Assistant discovery config to prefix: {discovery_prefix}")

    serial_number = device_metadata.get("serial_number")
    
    # Get poll interval for expire_after
    poll_interval = int(os.getenv("POLL_INTERVAL", 30))
    expire_after = poll_interval * 4
    
    # Map the requested device fields to the standard Home Assistant device object format.
    device_payload = {
        "identifiers": [serial_number],
        "name": f"{device_metadata.get('manufacturer')} {device_metadata.get('model_number')}",
        "manufacturer": device_metadata.get('manufacturer'),
        "model": device_metadata.get('model_number'),
        "sw_version": device_metadata.get('software_version'),
        "hw_version": device_metadata.get('hardware_version'),
    }

    # Map the requested origin fields to the standard Home Assistant origin object format.
    origin_payload = {
        "name": "sagemcom2mqtt",
        "sw_version": __version__,
        "url": "https://github.com/gregmac/sagemcom2mqtt"
    }

    # Define how each piece of data maps to a Home Assistant sensor.
    sensors = {
        "status": {"name": "Status", "icon": "mdi:check-circle"},
        "ipv4_address": {"name": "WAN IPv4 Address", "icon": "mdi:ip-network"},
        "downstream/power_avg_dbmv": {"name": "Downstream Power Avg", "unit_of_measurement": "dBmV", "device_class": "signal_strength", "state_class": "measurement", "icon": "mdi:signal-cellular-2"},
        "downstream/power_min_dbmv": {"name": "Downstream Power Min", "unit_of_measurement": "dBmV", "device_class": "signal_strength", "state_class": "measurement", "icon": "mdi:signal-cellular-1"},
        "downstream/power_max_dbmv": {"name": "Downstream Power Max", "unit_of_measurement": "dBmV", "device_class": "signal_strength", "state_class": "measurement", "icon": "mdi:signal-cellular-3"},
        "downstream/snr_avg_db": {"name": "Downstream SNR Avg", "unit_of_measurement": "dB", "device_class": "signal_strength", "state_class": "measurement", "icon": "mdi:gauge"},
        "downstream/channels": {"name": "Downstream Channels", "icon": "mdi:counter", "state_class": "measurement"},
        "downstream/correctable_per_minute": {"name": "Downstream Correctable Rate", "unit_of_measurement": "errors/min", "state_class": "measurement", "icon": "mdi:wifi-check"},
        "downstream/uncorrectable_per_minute": {"name": "Downstream Uncorrectable Rate", "unit_of_measurement": "errors/min", "state_class": "measurement", "icon": "mdi:wifi-cancel"},
        "upstream/power_avg_dbmv": {"name": "Upstream Power Avg", "unit_of_measurement": "dBmV", "device_class": "signal_strength", "state_class": "measurement", "icon": "mdi:signal-cellular-2"},
        "upstream/power_min_dbmv": {"name": "Upstream Power Min", "unit_of_measurement": "dBmV", "device_class": "signal_strength", "state_class": "measurement", "icon": "mdi:signal-cellular-1"},
        "upstream/power_max_dbmv": {"name": "Upstream Power Max", "unit_of_measurement": "dBmV", "device_class": "signal_strength", "state_class": "measurement", "icon": "mdi:signal-cellular-3"},
        "upstream/channels": {"name": "Upstream Channels", "icon": "mdi:counter", "state_class": "measurement"},
        "system/cpu_usage": {"name": "CPU Usage", "unit_of_measurement": "%", "state_class": "measurement", "icon": "mdi:cpu-64-bit"},
        "system/load_average_1m": {"name": "Load Average (1m)", "state_class": "measurement", "icon": "mdi:chip"},
        "system/free_memory_percentage": {"name": "Free Memory", "unit_of_measurement": "%", "state_class": "measurement", "icon": "mdi:memory"},
    }

    for metric_path, config in sensors.items():
        object_id = metric_path.replace('/', '_')
        unique_id = f"{serial_number}_{object_id}"
        
        config_topic = f"{discovery_prefix}/sensor/{serial_number}/{object_id}/config"
        
        # The state topic must match where the data is actually published.
        state_topic = f"{base_topic}/{serial_number}/{metric_path}"

        payload = {
            "name": f"Sagemcom {config['name']}",
            "state_topic": state_topic,
            "unique_id": unique_id,
            "device": device_payload,
            "origin": origin_payload,
            "availability_topic": f"{base_topic}/{serial_number}/status",
            "payload_available": "OPERATIONAL",
            "payload_not_available": "OFFLINE", # A placeholder, modem doesn't have a specific offline status
            "expire_after": expire_after,
        }
        
        # Add optional keys from our sensor definition
        payload.update({k: v for k, v in config.items() if k not in ["name"]})

        mqtt_client.publish(config_topic, json.dumps(payload), retain=True)
        _LOGGER.info(f"Published discovery config for {unique_id} to {config_topic}")

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
    mqtt_topic = os.getenv("MQTT_TOPIC", "sagemcom/docsis")
    ha_discovery_prefix = os.getenv("HOMEASSISTANT_DISCOVERY_PREFIX")

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
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)
    if mqtt_username:
        mqtt_client.username_pw_set(mqtt_username, mqtt_password)
    
    try:
        mqtt_client.connect(mqtt_hostname, mqtt_port, 60)
        mqtt_client.loop_start()
    except Exception as e:
        _LOGGER.error(f"Error connecting to MQTT broker: {e}")
        return

    # State for rate calculation
    last_poll_time = None
    last_correctable_sum = None
    last_uncorrectable_sum = None
    discovery_published = False

    while True:
        result = await get_docsis_data(modem_hostname, modem_username, modem_password, encryption_method)
        current_poll_time = time.time()

        if result:
            mqtt_data, device_metadata = result
            serial_number = device_metadata.get('serial_number') if device_metadata else None

            if mqtt_data and serial_number:
                # Calculate error rates
                current_correctable_sum = mqtt_data.get('downstream', {}).get('correctable_sum', 0)
                current_uncorrectable_sum = mqtt_data.get('downstream', {}).get('uncorrectable_sum', 0)

                correctable_per_minute = 0
                uncorrectable_per_minute = 0

                if last_poll_time is not None and last_correctable_sum is not None:
                    time_delta = current_poll_time - last_poll_time

                    # Handle counter resets (e.g., modem reboot) by checking for negative delta
                    correctable_delta = current_correctable_sum - last_correctable_sum
                    if correctable_delta < 0:
                        correctable_delta = 0 # Counter reset, so rate for this period is 0

                    uncorrectable_delta = current_uncorrectable_sum - last_uncorrectable_sum
                    if uncorrectable_delta < 0:
                        uncorrectable_delta = 0 # Counter reset

                    if time_delta > 0:
                        correctable_per_minute = (correctable_delta / time_delta) * 60
                        uncorrectable_per_minute = (uncorrectable_delta / time_delta) * 60
                        _LOGGER.debug(f"Calculated error rates: time_delta={time_delta:.2f}s")
                        _LOGGER.debug(f"  Correctable current: {current_correctable_sum}, delta: {correctable_delta}, per min: {correctable_per_minute:.2f}")
                        _LOGGER.debug(f"  Uncorrectable current: {current_uncorrectable_sum}, delta: {uncorrectable_delta}, per min: {uncorrectable_per_minute:.2f}")

                # Update state for the next iteration
                last_poll_time = current_poll_time
                last_correctable_sum = current_correctable_sum
                last_uncorrectable_sum = current_uncorrectable_sum

                # Replace sum values with calculated rates for publishing
                if 'downstream' in mqtt_data:
                    del mqtt_data['downstream']['correctable_sum']
                    del mqtt_data['downstream']['uncorrectable_sum']
                    mqtt_data['downstream']['correctable_per_minute'] = round(correctable_per_minute, 2)
                    mqtt_data['downstream']['uncorrectable_per_minute'] = round(uncorrectable_per_minute, 2)
                
                # Publish Home Assistant discovery on the first successful data fetch
                if ha_discovery_prefix and not discovery_published:
                    publish_ha_discovery_config(mqtt_client, ha_discovery_prefix, device_metadata, mqtt_topic)
                    discovery_published = True

                # Log the collected (but not published) metadata
                _LOGGER.info(f"Collected device metadata: {device_metadata}")

                base_topic = f"{mqtt_topic}/{serial_number}"
                properties = Properties(PacketTypes.PUBLISH)
                properties.MessageExpiryInterval = poll_interval * 4

                # Recursively publish each metric to its own topic
                def publish_metrics(topic_parts, data):
                    for key, value in data.items():
                        new_topic_parts = topic_parts + [key]
                        if isinstance(value, dict):
                            publish_metrics(new_topic_parts, value)
                        else:
                            full_topic = "/".join(new_topic_parts)
                            mqtt_client.publish(full_topic, str(value), properties=properties)
                            _LOGGER.info(f"Published to {full_topic}: {value}")
                
                publish_metrics([base_topic], mqtt_data)
                
            elif mqtt_data:
                _LOGGER.warning(f"Could not determine serial number. Cannot publish individual metrics.")

        # Wait for the next interval
        await asyncio.sleep(poll_interval)

def main_cli():
    """Command-line interface entry point."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Process interrupted by user.")
        sys.exit(0)

if __name__ == "__main__":
    main_cli() 