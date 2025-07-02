[![Docker Image](https://img.shields.io/badge/ghcr.io-gregmac/sagemcom2mqtt-blue?logo=docker)](https://github.com/users/gregmac/packages/container/package/sagemcom2mqtt)
[![Build and Publish](https://github.com/gregmac/sagemcom2mqtt/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/gregmac/sagemcom2mqtt/actions/workflows/docker-publish.yml)

# Sagemcom Modem DOCSIS Data to MQTT Reader

This Python application reads DOCSIS data from a Sagemcom modem and publishes it to an MQTT broker. It can be run as a service using Docker.

## Features

-   Connects to Sagemcom modems using `python-sagemcom-api`.
-   Polls the modem at a user-defined interval.
-   Gathers key DOCSIS metrics.
-   Publishes data to an MQTT broker.
-   Supports a one-shot test mode for quick diagnostics without MQTT.
-   Runs in a Docker container for easy deployment and isolation.

### Data Supported

The following DOCSIS data points are collected and published:

-   Registration Status
-   Operational status
-   Number of connected downstream channels
-   Downstream Min Power (dBmV)
-   Downstream Average Power (dBmV)
-   Downstream Max Power (dBmV)
-   Downstream Average SNR (dB)
-   Downstream Max SNR (dB)
-   Number of connected upstream channels
-   Upstream Min Power (dBmV)
-   Upstream Average Power (dBmV)
-   Upstream Max Power (dBmV)

## Installation

To run the application, it is recommended to first install it as a package. This can be done from the root of the project directory.

```sh
pip install .
```

For development, you can install it in "editable" mode, which allows you to make changes to the source code without reinstalling. To include the testing dependencies, use:

```sh
pip install -e .[test]
```

## Usage

Once installed, the application provides three command-line scripts:

*   `sagemcom2mqtt`: The main application to poll the modem and publish to MQTT.
*   `sagemcom2mqtt-discover`: A tool to explore the modem's API.
*   `sagemcom2mqtt-anonymize`: A tool to anonymize a modem data dump.
*   `sagemcom2mqtt-parse`: A utility to parse a local data file and print the output. Useful for creating new test snapshots.

These commands can be run directly from your terminal.

## Configuration

The application is configured using environment variables.

| Variable                          | Description                                                                                                                              | Default                            | Required |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- | -------- |
| `MODEM_HOSTNAME`                  | The hostname or IP address of the Sagemcom modem.                                                                                        |                                    | Yes      |
| `MODEM_USERNAME`                  | The username for the modem's web interface.                                                                                              |                                    | Yes      |
| `MODEM_PASSWORD`                  | The password for the modem's web interface.                                                                                              |                                    | Yes      |
| `MODEM_ENCRYPTION`                | The encryption method used for authentication.                                                                                           | `SHA512`                           | No       |
| `POLLING_INTERVAL_SECONDS`        | The interval in seconds to poll the modem for data.                                                                                      | `30`                               | No       |
| `LOG_LEVEL`                       | The log level for the application's output. Can be `DEBUG`, `INFO`, `WARNING`, `ERROR`.                                                  | `INFO`                             | No       |
| `MQTT_HOSTNAME`                   | The hostname or IP address of the MQTT broker.                                                                                           |                                    | No*      |
| `MQTT_PORT`                       | The port of the MQTT broker.                                                                                                             | `1883`                             | No       |
| `MQTT_USERNAME`                   | The username for the MQTT broker.                                                                                                        |                                    | No       |
| `MQTT_PASSWORD`                   | The password for the MQTT broker.                                                                                                        |                                    | No       |
| `MQTT_TOPIC`                      | The base topic to publish messages to. The device serial number and metric path will be appended.                                        | `sagemcom/docsis`                  | No       |
| `MESSAGE_EXPIRY_SECONDS`          | The number of seconds after which MQTT messages should expire.                                                                           | `POLLING_INTERVAL_SECONDS * 4`     | No       |
| `HOMEASSISTANT_DISCOVERY_PREFIX`  | If set, the application will publish discovery messages for Home Assistant. Set to your discovery prefix, e.g., `homeassistant`.         |                                    | No       |

-   **Note:** If `MQTT_HOSTNAME` is not provided, the application will run in a one-shot test mode. It will connect to the modem, read the data, print it to the console, and then exit.

## Running with Docker

To run the application using Docker, follow these steps:

1.  **Build the Docker image:**

    ```sh
    docker build -t sagemcom2mqtt .
    ```

2.  **Run the Docker container:**

    Pass the configuration as environment variables.

    ```sh
    docker run -d --name sagemcom2mqtt \
      -e MODEM_HOSTNAME="192.168.100.1" \
      -e MODEM_USERNAME="admin" \
      -e MODEM_PASSWORD="your_modem_password" \
      -e MQTT_HOSTNAME="your_mqtt_broker" \
      --restart unless-stopped \
      sagemcom2mqtt
    ```

## Running Tests

This project uses `pytest` for unit testing. The tests validate the data parsing logic against sample modem data.

To run the tests, first install the project in editable mode with the test dependencies (see Installation section), then run:

```sh
pytest
```

To create or update a test snapshot (`.expected.json` file) for a new modem data file, you can use the `sagemcom2mqtt-parse` utility:

```sh
sagemcom2mqtt-parse modems/NEW_MODEM_DATA.json > modems/NEW_MODEM_DATA.expected.json
```

### Using Docker

To run the tests within a Docker container, you must first build the image. Then, you can execute the test script inside a new container.

1.  **Build the image:**
    ```sh
    docker build -t sagemcom-mqtt .
    ```

2.  **Run the tests:**
    ```sh
    docker run --rm sagemcom2mqtt pytest
    ```

## Discovering API Paths

The `sagemcom_api` library allows you to explore the device's API to find the correct XPaths for the data you need. The `discover.py` script is provided for this purpose.

### Running the Discovery Script

The script will connect to the modem and print its API data structure as a large JSON object to your console. To save this output for analysis or for use with the unit tests, you can redirect the output to a file.

1.  Set the same environment variables you use for the main application (`MODEM_HOSTNAME`, `MODEM_USERNAME`, `MODEM_PASSWORD`).

2.  Run the script and redirect the output to a new file in the `modems` directory.

    **Example:**
    ```sh
    # Set your modem credentials first (example for PowerShell)
    $env:SAGEMCOM_HOSTNAME="192.168.100.1"
    $env:SAGEMCOM_USERNAME="your_username"
    $env:SAGEMCOM_PASSWORD="your_password"

    # Run the script and save the output
    python discover.py > modems/my_modem_dump.json
    ```

    or using Docker:

    ```sh
    docker run --rm sagemcom2mqtt sagemcom2mqtt-discover > modems/my_modem_dump.json
    ```

3.  The resulting `.json` file can then be inspected to find the correct paths for your device, or used as a new test case for the unit tests.

4.  You can also explore specific sub-paths by passing them as an argument:
    ```sh
    sagemcom2mqtt-discover Device/Docsis/cable_modem/downstreams
    ```
4.  Once you find the correct paths for the downstream, upstream, and interface status data, you can update the `get_docsis_data` function in `app.py`. 