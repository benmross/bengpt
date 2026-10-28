import xml.etree.ElementTree as ET
import sys
from pathlib import Path

def normalize_phone_number(number):
    """
    Normalize phone number by removing any non-digit characters and ensuring
    consistent formatting.
    """
    # Remove any non-digit characters
    digits = ''.join(filter(str.isdigit, number))
    
    # If it starts with a country code, keep it as is
    # Otherwise, assume US number and add +1 if 10 digits
    if len(digits) == 10:
        return f"+1{digits}"
    return f"+{digits}" if not digits.startswith('+') else digits

def extract_conversation(input_file, phone_number, output_file):
    """
    Extract all SMS and MMS messages between the user and a specific phone number.
    """
    # Normalize the target phone number
    target_number = normalize_phone_number(phone_number)
    
    # Parse the XML file
    tree = ET.parse(input_file)
    root = tree.getroot()
    
    # Create new root with same attributes
    new_root = ET.Element('smses')
    for key, value in root.attrib.items():
        new_root.set(key, value)
    
    # Track statistics
    total_sms = 0
    total_mms = 0
    
    # Extract SMS messages
    for sms in root.findall('.//sms'):
        if normalize_phone_number(sms.get('address', '')) == target_number:
            new_root.append(sms)
            total_sms += 1
    
    # Extract MMS messages
    for mms in root.findall('.//mms'):
        if normalize_phone_number(mms.get('address', '')) == target_number:
            new_root.append(mms)
            total_mms += 1
    
    # Update count attributes
    new_root.set('count', str(total_sms + total_mms))
    
    # Create new tree and write to file
    new_tree = ET.ElementTree(new_root)
    new_tree.write(output_file, encoding='utf-8', xml_declaration=True)
    
    # Print statistics
    print("\nExtraction complete!")
    print(f"SMS messages extracted: {total_sms}")
    print(f"MMS messages extracted: {total_mms}")
    print(f"Total messages: {total_sms + total_mms}")
    print(f"Output file: {output_file}")

def main():
    if len(sys.argv) != 4:
        print("Usage: python extract_conversation.py input.xml phone_number output.xml")
        print("Example: python extract_conversation.py backup.xml +1234567890 conversation.xml")
        sys.exit(1)
        
    input_file = sys.argv[1]
    phone_number = sys.argv[2]
    output_file = sys.argv[3]
    
    print(f"Extracting conversation with {phone_number} from {input_file}...")
    extract_conversation(input_file, phone_number, output_file)

if __name__ == "__main__":
    main()
