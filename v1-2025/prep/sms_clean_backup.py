import xml.etree.ElementTree as ET
from pathlib import Path
import hashlib
import sys

def get_message_key(msg_elem):
    """
    Generate a unique key for a message based on its content and metadata, 
    regardless of whether it's SMS or MMS.
    """
    # Get basic attributes
    date = msg_elem.get('date', '')
    address = msg_elem.get('address', '')
    
    # Get message text content - handle both SMS and MMS formats
    text = ''
    if msg_elem.tag == 'sms':
        text = msg_elem.get('body', '')
    else:  # mms
        parts = msg_elem.find('parts')
        if parts is not None:
            for part in parts.findall('part'):
                if part.get('ct') == 'text/plain':
                    text = part.get('text', '')
                    break
    
    # Combine key elements and hash them
    key_string = f"{date}|{address}|{text}"
    return hashlib.md5(key_string.encode()).hexdigest()

def process_sms_backup(input_file, output_file):
    """
    Process the SMS backup XML file, remove images and videos,
    deduplicate messages, and save to a new file.
    """
    # Parse the XML file
    tree = ET.parse(input_file)
    root = tree.getroot()
    
    # Track statistics
    removed_images = 0
    removed_videos = 0
    removed_duplicates = 0
    original_size = Path(input_file).stat().st_size
    
    # Track unique messages and keep only the first occurrence
    seen_messages = {}
    unique_messages = []
    
    # First pass: identify unique messages across both SMS and MMS
    for msg in root.findall('.//sms') + root.findall('.//mms'):
        msg_key = get_message_key(msg)
        if msg_key not in seen_messages:
            seen_messages[msg_key] = msg.tag
            unique_messages.append(msg)
        else:
            # If this is an MMS and the previous was SMS, prefer the MMS version
            if msg.tag == 'mms' and seen_messages[msg_key] == 'sms':
                # Remove the SMS version and keep the MMS version
                unique_messages = [m for m in unique_messages if get_message_key(m) != msg_key]
                unique_messages.append(msg)
                seen_messages[msg_key] = 'mms'
            else:
                removed_duplicates += 1
    
    # Create new root with same attributes
    new_root = ET.Element('smses')
    for key, value in root.attrib.items():
        new_root.set(key, value)
    
    # Add unique messages to new root
    for msg in unique_messages:
        # Process MMS messages to remove media
        if msg.tag == 'mms':
            parts = msg.find('parts')
            if parts is not None:
                # Track parts to remove
                parts_to_remove = []
                
                for part in parts.findall('part'):
                    content_type = part.get('ct', '')
                    
                    # Remove both videos and images
                    if content_type.startswith('video/'):
                        parts_to_remove.append(part)
                        removed_videos += 1
                    elif content_type.startswith('image/'):
                        parts_to_remove.append(part)
                        removed_images += 1
                
                # Remove media parts
                for part in parts_to_remove:
                    parts.remove(part)
        
        new_root.append(msg)
    
    # Create new tree and write to file
    new_tree = ET.ElementTree(new_root)
    new_tree.write(output_file, encoding='utf-8', xml_declaration=True)
    
    # Calculate final size
    final_size = Path(output_file).stat().st_size
    
    # Print statistics
    print("\nProcessing complete!")
    print(f"Images removed: {removed_images}")
    print(f"Videos removed: {removed_videos}")
    print(f"Duplicate messages removed: {removed_duplicates}")
    print(f"Original file size: {original_size / 1024 / 1024:.2f} MB")
    print(f"Final file size: {final_size / 1024 / 1024:.2f} MB")
    print(f"Size reduction: {(1 - final_size/original_size) * 100:.1f}%")

def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py input.xml output.xml")
        sys.exit(1)
        
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    print(f"Processing {input_file}...")
    process_sms_backup(input_file, output_file)

if __name__ == "__main__":
    main()
