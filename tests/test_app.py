import unittest
import json
import glob
import os
from sagemcom2mqtt.app import parse_docsis_data

class TestModemDataParsing(unittest.TestCase):
    maxDiff = None

    def test_all_modem_files_against_expected_output(self):
        """
        Automatically discovers and tests all JSON files in the 'modems/' directory
        by comparing their parsed output to a corresponding '.expected.json' file.
        """
        modem_files = [f for f in glob.glob('modems/*.json') if not f.endswith('.expected.json')]
        self.assertGreater(len(modem_files), 0, "No modem data files found in modems/ directory")

        for modem_file_path in modem_files:
            base, _ = os.path.splitext(modem_file_path)
            expected_file_path = f"{base}.expected.json"

            with self.subTest(msg=f"Testing against snapshot: {os.path.basename(modem_file_path)}"):
                self.assertTrue(os.path.exists(expected_file_path), f"Expected output file not found: {expected_file_path}")

                with open(modem_file_path, 'r') as f:
                    modem_data = json.load(f)
                
                with open(expected_file_path, 'r') as f:
                    expected_data = json.load(f)

                # Call the parsing function with the test data
                mqtt_data, device_metadata = parse_docsis_data(modem_data)

                # Combine the results into a single dictionary for comparison
                actual_data = {
                    "mqtt_data": mqtt_data,
                    "device_metadata": device_metadata
                }

                # Compare the actual parsed data with the expected data from the snapshot file
                self.assertDictEqual(actual_data, expected_data, "The parsed data does not match the expected output.")


if __name__ == '__main__':
    unittest.main() 