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
                mqtt_data, device_metadata = parse_docsis_data(modem_data)

                # 1. Basic sanity checks for both returned objects
                self.assertIsNotNone(mqtt_data, "MQTT data parsing returned None")
                self.assertIsInstance(mqtt_data, dict, "MQTT data is not a dictionary")
                self.assertIsNotNone(device_metadata, "Device metadata parsing returned None")
                self.assertIsInstance(device_metadata, dict, "Device metadata is not a dictionary")

                # 2. Check for key metrics and their types in mqtt_data
                self.assertIn('downstream', mqtt_data)
                self.assertIn('upstream', mqtt_data)
                self.assertIn('status', mqtt_data)
                
                # 3. Check for logical values in mqtt_data
                self.assertGreaterEqual(mqtt_data['downstream']['channels'], 0)
                self.assertGreaterEqual(mqtt_data['upstream']['channels'], 0)
                self.assertGreater(mqtt_data['downstream']['channels'] + mqtt_data['upstream']['channels'], 0, "No channels were found")

                # 4. Check for device_metadata content
                expected_metadata_keys = [
                    'serial_number', 'manufacturer', 'model_number', 
                    'mac_address', 'hardware_version', 'software_version'
                ]
                for key in expected_metadata_keys:
                    self.assertIn(key, device_metadata, f"Key '{key}' is missing from device_metadata")
                
                self.assertIsInstance(device_metadata['serial_number'], str, "Serial number is not a string")
                self.assertTrue(device_metadata['serial_number'], "Serial number is blank")


if __name__ == '__main__':
    unittest.main() 