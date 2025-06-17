import json
import random
import string
import re
import ipaddress
import argparse

# --- Global State & Mappings ---
FAKE_SERIAL_NUMBER = 'JW' + ''.join(random.choice(string.digits) for _ in range(12))
WITTY_SSIDS = [
    "Tell my WiFi love her",
    "Pretty Fly for a Wi-Fi",
    "The LAN Before Time",
    "Searching...",
    "Get off my LAN"
]
# This map will store all replacements to ensure consistency.
REPLACEMENTS_MAP = {}

# --- Regex Patterns ---
IPV4_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
# A more accurate IPv6 regex to avoid matching MACs or DUIDs.
IPV6_PATTERN = re.compile(r'\b(?:[a-f0-9]{1,4}:){2,7}[a-f0-9]{1,4}\b', re.IGNORECASE)
MAC_ADDRESS_PATTERN = re.compile(r'\b(?:[0-9A-Fa-f]{2}[:-]){5}(?:[0-9A-Fa-f]{2})\b')

# --- Anonymization Core Functions ---

def get_or_create_mac_replacement(original_mac):
    """Anonymizes a MAC address, randomizing the last three octets."""
    if original_mac in REPLACEMENTS_MAP:
        return REPLACEMENTS_MAP[original_mac]

    separator = original_mac[2]
    parts = original_mac.split(separator)
    new_parts = parts[:3] + [
        f'{random.randint(0, 255):02x}',
        f'{random.randint(0, 255):02x}',
        f'{random.randint(0, 255):02x}'
    ]
    new_mac = separator.join(new_parts).upper()
    REPLACEMENTS_MAP[original_mac] = new_mac
    return new_mac

def get_or_create_ipv4_replacement(ip_str):
    """Anonymizes an IPv4 address based on a specific set of rules."""
    if ip_str in REPLACEMENTS_MAP:
        return REPLACEMENTS_MAP[ip_str]

    octets = [int(o) for o in ip_str.split('.')]

    # Rule: 192.168.x.y IPs
    if octets[0] == 192 and octets[1] == 168:
        if 1 < octets[3] < 255:
            new_octets = octets[:3] + [random.randint(2, 254)]
            new_ip = ".".join(map(str, new_octets))
        else:
            new_ip = ip_str # Keep it intact if y is 0, 1, or 255
    else: # Rule: All other IPv4s
        new_octets = [10, random.randint(0, 255), random.randint(0, 255), 0]
        if octets[3] in [0, 1, 255]:
            new_octets[3] = octets[3]
        else:
            new_octets[3] = random.randint(2, 254)
        new_ip = ".".join(map(str, new_octets))

    REPLACEMENTS_MAP[ip_str] = new_ip
    return new_ip

def get_or_create_ipv6_replacement(ip_str):
    """Anonymizes an IPv6 address, preserving the first segment and '0'/'1' segments."""
    if ip_str in REPLACEMENTS_MAP:
        return REPLACEMENTS_MAP[ip_str]

    ip = ipaddress.IPv6Address(ip_str)
    parts = ip.exploded.split(':')
    new_parts = [parts[0]] # Always preserve the first segment
    for part in parts[1:]:
        if part in ['0000', '0001']:
            new_parts.append(part)
        else:
            new_parts.append(f'{random.randint(0, 65535):04x}')

    new_ip = str(ipaddress.IPv6Address(':'.join(new_parts)))
    REPLACEMENTS_MAP[ip_str] = new_ip
    return new_ip

def get_or_create_ssid_replacement(original_ssid):
    if original_ssid in REPLACEMENTS_MAP:
        return REPLACEMENTS_MAP[original_ssid]
    new_ssid = random.choice(WITTY_SSIDS)
    REPLACEMENTS_MAP[original_ssid] = new_ssid
    return new_ssid

# --- Regex Substitution Callbacks ---

def sub_mac_match(match):
    return get_or_create_mac_replacement(match.group(0))

def sub_ipv4_match(match):
    ip_str = match.group(0)
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_loopback or ip.is_unspecified or ip_str.startswith('255.'):
            return ip_str # Rule: Do not change these IPs
        return get_or_create_ipv4_replacement(ip_str)
    except ValueError:
        return ip_str # Not a valid IP, don't change it

def sub_ipv6_match(match):
    ip_str = match.group(0)
    try:
        # Validate that it's a real IPv6 address before trying to anonymize
        ipaddress.IPv6Address(ip_str)
        return get_or_create_ipv6_replacement(ip_str)
    except ValueError:
        return ip_str # Not a valid IPv6, so don't change it

# --- Main Anonymization Logic ---

def anonymize_value(key, value):
    """
    Intelligently anonymizes a value based on its key and content.
    This function defines the order of operations.
    """
    if not isinstance(value, str) or not value:
        return value # Only anonymize non-empty strings

    # --- Rule 1: Handle high-priority key-based exclusions ---
    key_lower = key.lower()
    if "version" in key_lower or "ssid_reference" in key_lower:
        return value
    if "prefix" in key_lower and ":" in value: # Likely an IPv6 Prefix
        return value

    # --- Rule 2: Handle specific key-based replacements ---
    if "serial_number" == key_lower:
        return FAKE_SERIAL_NUMBER # Will be blank if original was blank (checked above)
    if any(s in key_lower for s in ["password", "passphrase"]) and value:
        return ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    if "ssid" == key_lower:
        return get_or_create_ssid_replacement(value)
    # BSSID uses the same logic as a general MAC address search
    if "bssid" == key_lower:
         return MAC_ADDRESS_PATTERN.sub(sub_mac_match, value)

    # --- Rule 3: For all other strings, perform content-based replacement ---
    anonymized_val = value
    anonymized_val = MAC_ADDRESS_PATTERN.sub(sub_mac_match, anonymized_val)
    anonymized_val = IPV4_PATTERN.sub(sub_ipv4_match, anonymized_val)
    anonymized_val = IPV6_PATTERN.sub(sub_ipv6_match, anonymized_val)
    return anonymized_val

def anonymize_data(data):
    """
    Traverses a JSON-like structure (dicts and lists) and applies anonymization.
    """
    if isinstance(data, dict):
        return {k: anonymize_value(k, anonymize_data(v)) for k, v in data.items()}
    elif isinstance(data, list):
        return [anonymize_data(item) for item in data]
    else:
        return data

def anonymize_file(input_file, output_file):
    """
    Reads a JSON file, anonymizes its contents, and writes the anonymized data to a new file.
    """
    if not input_file or not output_file:
        print("Error: Both input and output file paths must be provided.")
        return

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        anonymized_data = anonymize_data(data)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(anonymized_data, f, indent=4)
            print(f"Anonymized data written to {output_file}")

    except FileNotFoundError:
        print(f"Error: '{input_file}' not found.")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{input_file}'.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

def main():
    """Command-line interface entry point for anonymizer."""
    parser = argparse.ArgumentParser(description='Anonymize a Sagemcom modem JSON data file.')
    parser.add_argument('input_file', help='The path to the input JSON file.')
    parser.add_argument('output_file', nargs='?', default=None, help='The path to the output JSON file. Defaults to (input).anonymized.json.')
    args = parser.parse_args()

    anonymize_file(args.input_file, args.output_file)

if __name__ == "__main__":
    main() 