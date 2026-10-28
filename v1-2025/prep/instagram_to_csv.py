import json
import sys
from datetime import datetime
import csv
from pathlib import Path
import glob

def process_json_files(directory_path, output_file):
    """Process all message_*.json files and convert to CSV format."""
    # Find all message JSON files
    json_files = sorted(glob.glob(str(Path(directory_path) / 'message_*.json')))
    
    if not json_files:
        print(f"No message_*.json files found in {directory_path}")
        return 0
    
    # Get participant names from first file to determine sender mapping
    with open(json_files[0], 'r', encoding='utf-8') as f:
        first_file = json.load(f)
        participants = [p['name'] for p in first_file['participants']]
        
    if len(participants) != 2:
        print("Error: Expected exactly 2 participants")
        return 0
        
    # Map sender names to 0/1 (assuming first participant is "you")
    sender_map = {participants[0]: 1, participants[1]: 0}  # the exporting account is 0, the other person 1
    
    # Collect all messages
    all_messages = []
    ai_messages_filtered = 0
    
    # Process each JSON file
    for json_file in json_files:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
            for message in data['messages']:
                # Skip if sender is not in our participant list (e.g., Meta AI)
                if message['sender_name'] not in sender_map:
                    ai_messages_filtered += 1
                    continue
                    
                # Only process messages with content
                if 'content' in message:
                    sender = sender_map[message['sender_name']]
                    timestamp = datetime.fromtimestamp(message['timestamp_ms']/1000)
                    content = message['content']
                    
                    all_messages.append([sender, timestamp, content])
    
    # Sort messages by timestamp
    all_messages.sort(key=lambda x: x[1])
    
    # Write to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, delimiter='¦')
        writer.writerow(['sender', 'timestamp', 'content'])  # Header
        for msg in all_messages:
            writer.writerow([msg[0], msg[1], msg[2]])
    
    print(f"Filtered out {ai_messages_filtered} AI messages")
    return len(all_messages)

def main():
    if len(sys.argv) != 3:
        print("Usage: python script.py directory_path output.csv")
        print("Example: python script.py ./instagram_messages output.csv")
        sys.exit(1)
        
    directory_path = sys.argv[1]
    output_file = sys.argv[2]
    
    print(f"Processing Instagram DM files from {directory_path}...")
    total_messages = process_json_files(directory_path, output_file)
    
    print(f"\nConversion complete!")
    print(f"Total messages exported: {total_messages}")
    print(f"Output file: {output_file}")

if __name__ == "__main__":
    main()
