[![Docker Image](https://img.shields.io/badge/ghcr.io-gregmac/sagemcom2mqtt-blue?logo=docker)](https://github.com/users/gregmac/packages/container/package/sagemcom2mqtt)
[![Build and Publish](https://github.com/gregmac/sagemcom2mqtt/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/gregmac/sagemcom2mqtt/actions/workflows/docker-publish.yml)

# Sagemcom2MQTT

This Python application reads DOCSIS data from a Sagemcom modem and publishes it to an MQTT broker. It is designed to run easily in Docker, but can also be run directly from source.

## Features

- 🚀 **Easy integration**: Connects to Sagemcom modems using [python-sagemcom-api](https://github.com/iMicknl/python-sagemcom-api)
- 📊 **Comprehensive metrics**: Collects DOCSIS stats (power, SNR, channel status) plus system usage
- ⏱️ **Configurable polling**: Polls your modem at a user-defined interval and publishes results to MQTT
- 🏠 **Home Assistant ready**: Publishes [Home Assistant auto-discovery](https://www.home-assistant.io/integrations/mqtt#mqtt-discovery) messages for all sensors
- 🐳 **Runs anywhere**: Designed for easy deployment in Docker, but can also run directly from Python
- 🧪 **Test & debug modes**: Supports one-shot test mode for diagnostics without MQTT

### Data Supported

The following data points are collected and published:

-   Registration and Operational Status
-   DOCSIS stats
    -   Number of connected downstream and upstream channels
    -   Downstream Min, Average and Max Power (dBmV)
    -   Downstream Average and Max SNR (dB)
    -   Upstream Min, Average and Max Power (dBmV)
-   Load average (1m)
-   Memory usage (%)
-   System information including serial number, MAC address 
-   IP address

## Installation

### Recommended: Run from Docker

The easiest way to run Sagemcom2MQTT is using the pre-built Docker image from GitHub Container Registry.

```sh
docker pull ghcr.io/gregmac/sagemcom2mqtt:latest
```

Run the container, passing configuration as environment variables:

```sh
docker run -d --name sagemcom2mqtt \
  -e MODEM_HOSTNAME="192.168.100.1" \
  -e MODEM_USERNAME="admin" \
  -e MODEM_PASSWORD="your_modem_password" \
  -e MQTT_HOSTNAME="your_mqtt_broker" \
  --restart unless-stopped \
  ghcr.io/gregmac/sagemcom2mqtt:latest
```

See [Configuration](#configuration) for all options.

### Alternatives

#### Build and run local Docker image

From the root of the cloned repository:

```sh
docker build -t sagemcom2mqtt .
docker run -d --name sagemcom2mqtt ... sagemcom2mqtt
```

#### Run from Python directly

Install the package:

```sh
pip install .
```

Or for development:

```sh
pip install -e .[test]
```

Then run:

```sh
sagemcom2mqtt
```

---

## Configuration

The application is configured using environment variables.

| Variable                          | Description                                                                                       | Default                            | Required     |
| --------------------------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------- | ------------ |
| `MODEM_HOSTNAME`                  | The hostname or IP address of the Sagemcom modem.                                                 |                                    | ✅ Yes      |
| `MODEM_USERNAME`                  | The username for the modem's web interface.                                                       |                                    | ✅ Yes      |
| `MODEM_PASSWORD`                  | The password for the modem's web interface.                                                       |                                    | ✅ Yes      |
| `MODEM_ENCRYPTION`                | The encryption method used for authentication.                                                    | `SHA512`                           | -            |
| `POLLING_INTERVAL_SECONDS`        | The interval in seconds to poll the modem for data.                                               | `30`                               | -            |
| `LOG_LEVEL`                       | The log level for the application's output. Can be `DEBUG`, `INFO`, `WARNING`, `ERROR`.           | `INFO`                             | -            |
| `MQTT_HOSTNAME`                   | The hostname or IP address of the MQTT broker.                                                    |                                    | *️⃣ For MQTT |
| `MQTT_PORT`                       | The port of the MQTT broker.                                                                      | `1883`                             | -            |
| `MQTT_USERNAME`                   | The username for the MQTT broker.                                                                 |                                    | -            |
| `MQTT_PASSWORD`                   | The password for the MQTT broker.                                                                 |                                    | -            |
| `MQTT_TOPIC`                      | The base topic to publish messages to. The device serial number and metric path will be appended. | `sagemcom/docsis`                  | -            |
| `MESSAGE_EXPIRY_SECONDS`          | The number of seconds after which MQTT messages should expire.                                    | `POLLING_INTERVAL_SECONDS * 4`     | -            |
| `HOMEASSISTANT_DISCOVERY_PREFIX`  | If set, the application will publish discovery messages for Home Assistant                        | `homeassistant`                    | -            |

- *️⃣ **Note:** If `MQTT_HOSTNAME` is not provided, the application will run in a one-shot test mode. It will connect to the modem, read the data, print it to the console, and then exit.

---

## Supported Devices

In theory any device supported by [python-sagemcom-api](https://github.com/iMicknl/python-sagemcom-api) with the expected data structure will work.

Verified models:

| Device Model        | Firmware Version                  |
|---------------------|-----------------------------------|
| Sagemcom FAST3896   | FAST3896UM_CCX_sw18.83.15.16v-38  |

---

## Development

### Adding New Devices

To add support for a new Sagemcom modem model:

1. **Discover API paths:**
   - Use the `sagemcom2mqtt-discover` tool to dump the modem's API structure:
     ```sh
     # Set your modem credentials (example for PowerShell)
     $env:MODEM_HOSTNAME="192.168.100.1"
     $env:MODEM_USERNAME="your_username"
     $env:MODEM_PASSWORD="your_password"
     sagemcom2mqtt-discover > modems/my_modem_dump.json
     ```
   - Or using Docker:
     ```sh
     docker run --rm ghcr.io/gregmac/sagemcom2mqtt:latest sagemcom2mqtt-discover > modems/my_modem_dump.json
     ```
2. **Parse and test:**
   - Use `sagemcom2mqtt-parse` to parse the dump and print the output:
     ```sh
     sagemcom2mqtt-parse modems/my_modem_dump.json
     ```
   - To create a test snapshot:
     ```sh
     sagemcom2mqtt-parse modems/my_modem_dump.json > modems/my_modem_dump.expected.json
     ```
3. **Anonymize before sharing:**
   - Before committing or sharing modem dumps, anonymize them:
     ```sh
     sagemcom2mqtt-anonymize modems/my_modem_dump.json > modems/my_modem_dump.anonymized.json
     ```

If your device uses different API paths, update the `get_docsis_data` function in `app.py` accordingly.

### Running Tests

This project uses `pytest` for unit testing. To run tests:

1. Install in editable mode with test dependencies:
   ```sh
   pip install -e .[test]
   ```
2. Run tests:
   ```sh
   pytest
   ```

#### Using Docker

1. Build the image:
   ```sh
   docker build -t sagemcom2mqtt .
   ```
2. Run tests:
   ```sh
   docker run --rm sagemcom2mqtt pytest
   ```

---

## License

This project is licensed under the GNU General Public License v3.0. 
