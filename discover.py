import os
import sys
import json
import asyncio
import logging
from sagemcom_api.client import SagemcomClient
from sagemcom_api.enums import EncryptionMethod

async def main():
    """
    Connects to the Sagemcom modem and explores its API structure.
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Get configuration from environment variables
    modem_hostname = os.getenv("MODEM_HOSTNAME")
    modem_username = os.getenv("MODEM_USERNAME")
    modem_password = os.getenv("MODEM_PASSWORD")
    encryption_str = os.getenv("MODEM_ENCRYPTION", "SHA512").upper()

    if not all([modem_hostname, modem_username, modem_password]):
        logging.error("Error: MODEM_HOSTNAME, MODEM_USERNAME, and MODEM_PASSWORD must be set.")
        return

    if encryption_str == "MD5":
        encryption_method = EncryptionMethod.MD5
    else:
        encryption_method = EncryptionMethod.SHA512

    # Determine the starting path from command-line arguments, default to "Device"
    start_path = sys.argv[1] if len(sys.argv) > 1 else "Device"
    
    logging.info(f"Starting API discovery at path: {start_path}")

    try:
        async with SagemcomClient(
            modem_hostname,
            modem_username,
            modem_password,
            encryption_method,
            ssl=True,
            verify_ssl=False
        ) as client:
            await client.login()
            
            logging.info("Successfully logged in. Exploring API...")
            
            value = await client.get_value_by_xpath(start_path)
            
            print(json.dumps(value, indent=4))

    except Exception as e:
        logging.error(f"An error occurred during discovery: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(main()) 