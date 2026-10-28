import xml.etree.ElementTree as ET
import sys
from datetime import datetime
import csv

def extract_text_from_mms(mms_elem):
    """Extract text content from an MMS message."""
    parts = mms_elem.find('parts')
    if parts is not None:
        for part in parts.findall('part'):
            if part.get('ct') == 'text/plain':
                return part.get('text', '')
    return ''

def convert_to_csv(input_file, output_file):
    """Convert XML conversation to CSV format."""
    # Parse the XML file
    tree = ET.parse(input_file)
    root = tree.getroot()
    
    # Prepare messages list
    messages = []
    
    # Process SMS messages
    for sms in root.findall('.//sms'):
        timestamp = datetime.fromtimestamp(int(sms.get('date', '0'))/1000)
        message_type = int(sms.get('type', '0'))
        # Convert type 1 (received) to 1 and type 2 (sent) to 0
        sender = 1 if message_type == 1 else 0
        content = sms.get('body', '')
        
        messages.append([sender, timestamp, content])
    
    # Process MMS messages
    for mms in root.findall('.//mms'):
        timestamp = datetime.fromtimestamp(int(mms.get('date', '0'))/1000)
        message_type = int(mms.get('msg_box', '0'))
        # Convert type 1 (received) to 1 and type 2 (sent) to 0
        sender = 1 if message_type == 1 else 0
        content = extract_text_from_mms(mms)
        
        if content:  # Only add if there's text content
            messages.append([sender, timestamp, content])
    
    # Sort messages by timestamp
    messages.sort(key=lambda x: x[1])
    
    # Write to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter='¦')
        writer.writerow(['sender', 'timestamp', 'content'])  # Header
        for msg in messages:
            writer.writerow([msg[0], msg[1], msg[2]])
    
    return len(messages)

def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py input.xml output.csv")
        sys.exit(1)
        
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    print(f"Converting {input_file} to CSV format...")
    total_messages = convert_to_csv(input_file, output_file)
    print(f"\nConversion complete!")
    print(f"Total messages exported: {total_messages}")
    print(f"Output file: {output_file}")

if __name__ == "__main__":
    main()
