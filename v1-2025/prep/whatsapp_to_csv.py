import sys
from datetime import datetime
import csv
import re

def parse_whatsapp_line(line):
    """Parse a WhatsApp message line into its components."""
    # Regular expression to match WhatsApp message format
    pattern = r'(\d{1,2}/\d{1,2}/\d{2,4}),\s(\d{1,2}:\d{2}\s[AP]M)\s-\s([^:]+):\s(.+)'
    
    match = re.match(pattern, line)
    if match:
        date, time, sender, content = match.groups()
        
        # Parse timestamp
        timestamp_str = f"{date} {time}"
        try:
            timestamp = datetime.strptime(timestamp_str, '%m/%d/%y %I:%M %p')
        except ValueError:
            # Try alternative date format if year is 4 digits
            timestamp = datetime.strptime(timestamp_str, '%m/%d/%Y %I:%M %p')
        
        return {
            'timestamp': timestamp,
            'sender': sender.strip(),
            'content': content.strip()
        }
    return None

def convert_to_csv(input_file, output_file):
    """Convert WhatsApp chat export to CSV format."""
    messages = []
    skipped_lines = 0
    
    # Read the first few lines to identify participants
    participants = set()
    with open(input_file, 'r', encoding='utf-8') as f:
        for _ in range(10):  # Check first 10 lines
            line = f.readline().strip()
            if line:
                parsed = parse_whatsapp_line(line)
                if parsed and not any(indicator in parsed['content'] for indicator in 
                    ['Messages and calls are end-to-end encrypted']):
                    participants.add(parsed['sender'])
    
    # Create sender mapping (assuming first participant alphabetically is sender 1)
    sender_list = sorted(list(participants))
    sender_map = {sender_list[1]: 0, sender_list[0]: 1}  # Map to 0 and 1
    
    print(f"Identified participants: {participants}")
    print(f"Mapping: {sender_map}")
    
    # Process all messages
    with open(input_file, 'r', encoding='utf-8') as f:
        current_message = []
        current_parsed = None
        
        for line in f:
            line = line.strip()
            if not line:
                continue
                
            parsed = parse_whatsapp_line(line)
            
            if parsed:
                # If we have a previous message with continuation lines, process it
                if current_parsed and current_message:
                    if current_parsed['sender'] in sender_map:
                        messages.append({
                            'sender': sender_map[current_parsed['sender']],
                            'timestamp': current_parsed['timestamp'],
                            'content': current_parsed['content'] + ' ' + ' '.join(current_message)
                        })
                
                # Reset continuation message buffer
                current_message = []
                current_parsed = parsed
                
                # Skip media messages and system messages
                if any(indicator in parsed['content'] for indicator in 
                      ['<Media omitted>', '(file attached)', 'security code changed',
                       'Messages and calls are end-to-end encrypted']):
                    skipped_lines += 1
                    continue
                
                if parsed['sender'] in sender_map:
                    messages.append({
                        'sender': sender_map[parsed['sender']],
                        'timestamp': parsed['timestamp'],
                        'content': parsed['content']
                    })
            else:
                # This line is probably a continuation of the previous message
                current_message.append(line)
    
    # Process any remaining continuation lines
    if current_parsed and current_message:
        if current_parsed['sender'] in sender_map:
            messages.append({
                'sender': sender_map[current_parsed['sender']],
                'timestamp': current_parsed['timestamp'],
                'content': current_parsed['content'] + ' ' + ' '.join(current_message)
            })
    
    # Sort messages by timestamp
    messages.sort(key=lambda x: x['timestamp'])
    
    # Write to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter='¦')
        writer.writerow(['sender', 'timestamp', 'content'])  # Header
        for msg in messages:
            writer.writerow([msg['sender'], msg['timestamp'], msg['content']])
    
    return len(messages), skipped_lines

def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py input.txt output.csv")
        print("Example: python script.py whatsapp_chat.txt output.csv")
        sys.exit(1)
        
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    print(f"Processing WhatsApp chat from {input_file}...")
    total_messages, skipped = convert_to_csv(input_file, output_file)
    
    print(f"\nConversion complete!")
    print(f"Total messages exported: {total_messages}")
    print(f"Skipped messages (media/system): {skipped}")
    print(f"Output file: {output_file}")

if __name__ == "__main__":
    main()
