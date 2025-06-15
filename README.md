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

## Configuration

The application is configured using environment variables.

| Variable                          | Description                                                                                                                              | Default                            | Required |
| --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- | -------- |
| `MODEM_HOSTNAME`                  | The hostname or IP address of the Sagemcom modem.                                                                                        |                                    | Yes      |
| `MODEM_USERNAME`                  | The username for the modem's web interface.                                                                                              |                                    | Yes      |
| `MODEM_PASSWORD`                  | The password for the modem's web interface.                                                                                              |                                    | Yes      |
| `MODEM_ENCRYPTION`                | The encryption method used for authentication.                                                                                           | `SHA512`                           | No       |
| `POLLING_INTERVAL_SECONDS`        | The interval in seconds to poll the modem for data.                                                                                      | `30`                               | No       |
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
    docker build -t sagemcom-mqtt .
    ```

2.  **Run the Docker container:**

    ### Example: Polling a modem and publishing to MQTT
    ```sh
    docker run -d --name sagemcom-mqtt \
      -e MODEM_HOSTNAME="192.168.100.1" \
      -e MODEM_USERNAME="admin" \
      -e MODEM_PASSWORD="your_modem_password" \
      -e MQTT_HOSTNAME="your_mqtt_broker" \
      --restart unless-stopped \
      sagemcom-mqtt
    ```
    
    ### Example: One-shot test mode
    ```sh
    docker run --rm \
      -e MODEM_HOSTNAME="192.168.100.1" \
      -e MODEM_USERNAME="admin" \
      -e MODEM_PASSWORD="your_modem_password" \
      sagemcom-mqtt
    ```

### Docker Compose

Alternatively, you can use `docker-compose`. Create a `docker-compose.yml` file like this:

```yaml
version: '3'
services:
  sagemcom-mqtt:
    build: .
    container_name: sagemcom-mqtt
    restart: unless-stopped
    environment:
      - MODEM_HOSTNAME=192.168.100.1
      - MODEM_USERNAME=admin
      - MODEM_PASSWORD=your_modem_password
      # - MODEM_ENCRYPTION=MD5
      - MQTT_HOSTNAME=your_mqtt_broker
      # - MQTT_USERNAME=your_mqtt_user
      # - MQTT_PASSWORD=your_mqtt_password
      # - MQTT_TOPIC=sagemcom/docsis/status
      # - POLL_INTERVAL=60
```

Then, run it with:
```sh
docker-compose up -d
```

## Running Tests

This project includes a unit test suite to validate the data parsing logic against sample modem data.

### Local
To run the tests locally, ensure you have installed the dependencies from `requirements.txt` and run:
```sh
python test_app.py
```

### Using Docker
To run the tests within a Docker container, you must first build the image. Then, you can execute the test script inside a new container.

1.  **Build the image:**
    ```sh
    docker build -t sagemcom-mqtt .
    ```

2.  **Run the tests:**
    ```sh
    docker run --rm sagemcom-mqtt python test_app.py
    ```

## Discovering API Paths (discover.py)

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
    docker run --rm sagemcom-mqtt python discover.py > modems/my_modem_dump.json
    ```

3.  The resulting `.json` file can then be inspected to find the correct paths for your device, or used as a new test case for the unit tests.

4.  You can also explore specific sub-paths by passing them as an argument:
    ```sh
    python discover.py Device/Docsis/cable_modem/downstreams
    ```
4.  Once you find the correct paths for the downstream, upstream, and interface status data, you can update the `get_docsis_data` function in `app.py`. 