import json
import argparse
import sys
from .app import parse_docsis_data
import logging

def main():
    """
    CLI tool to parse a local Sagemcom JSON data file and print the parsed output.
    """
    parser = argparse.ArgumentParser(
        description="Parse a Sagemcom JSON data file and output the structured data, suitable for use as a test snapshot."
    )
    parser.add_argument(
        "input_file",
        help="The path to the input JSON file (e.g., modems/FAST3896.json).",
    )
    args = parser.parse_args()

    # Suppress most logging to keep stdout clean for piping output
    logging.basicConfig(level=logging.ERROR)
    _LOGGER = logging.getLogger(__name__)


    try:
        with open(args.input_file, 'r') as f:
            modem_data = json.load(f)
    except FileNotFoundError:
        _LOGGER.error(f"Error: Input file not found at '{args.input_file}'")
        sys.exit(1)
    except json.JSONDecodeError:
        _LOGGER.error(f"Error: Could not decode JSON from '{args.input_file}'")
        sys.exit(1)

    # Call the parsing function
    mqtt_data, device_metadata = parse_docsis_data(modem_data)

    # Structure the data exactly as the unit test expects it
    expected_data = {
        "mqtt_data": mqtt_data,
        "device_metadata": device_metadata
    }

    # Print the resulting JSON to standard output
    print(json.dumps(expected_data, indent=4))

if __name__ == "__main__":
    main() 