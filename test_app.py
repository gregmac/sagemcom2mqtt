import unittest
import json
import glob
import os
from app import parse_docsis_data

class TestModemDataParsing(unittest.TestCase):

    def test_all_modem_files(self):
        """
        Automatically discovers and tests all JSON files in the 'modems/' directory.
        """
        modem_files = glob.glob('modems/*.json')
        self.assertGreater(len(modem_files), 0, "No modem files found in modems/ directory")

        for modem_file_path in modem_files:
            with self.subTest(msg=f"Testing file: {os.path.basename(modem_file_path)}"):
                with open(modem_file_path, 'r') as f:
                    modem_data = json.load(f)

                # Call the parsing function with the test data
                parsed_data = parse_docsis_data(modem_data)

                # 1. Basic sanity checks
                self.assertIsNotNone(parsed_data, "Parsing returned None")
                self.assertIsInstance(parsed_data, dict, "Parsing did not return a dictionary")

                # 2. Check for key metrics and their types
                expected_keys = {
                    'ds_power_avg': float,
                    'us_power_avg': float,
                    'ds_snr_avg': float,
                    'correctable_sum': int,
                    'uncorrectable_sum': int,
                    'downstream_channels': int,
                    'upstream_channels': int,
                }

                for key, expected_type in expected_keys.items():
                    self.assertIn(key, parsed_data, f"Key '{key}' is missing from parsed data")
                    self.assertIsInstance(parsed_data[key], expected_type, f"Key '{key}' has incorrect type")

                # 3. Check for logical values
                self.assertGreaterEqual(parsed_data['downstream_channels'], 0)
                self.assertGreaterEqual(parsed_data['upstream_channels'], 0)
                self.assertGreater(parsed_data['downstream_channels'] + parsed_data['upstream_channels'], 0, "No channels were found")


if __name__ == '__main__':
    unittest.main() 