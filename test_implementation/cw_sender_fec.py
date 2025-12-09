#!/usr/bin/env python3
"""
CW Sender with FEC - Send CW with Forward Error Correction
"""

import socket
import time
import argparse
from cw_protocol_fec import CWProtocolFEC, UDP_PORT

def send_text_fec(text, host='127.0.0.1', port=UDP_PORT, wpm=25):
    """
    Send text as CW with FEC
    
    Args:
        text: Text to send
        host: Target host
        port: UDP port
        wpm: Words per minute (12-35)
    """
    protocol = CWProtocolFEC()
    
    if not protocol.fec_enabled:
        print("ERROR: FEC not available (reedsolo not installed)")
        print("Install with: pip3 install reedsolo")
        return
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Calculate timing
    dit_ms = int(1200 / wpm)
    dah_ms = dit_ms * 3
    
    print(f"Sending '{text}' with FEC to {host}:{port} at {wpm} WPM")
    print(f"FEC: {protocol.FEC_BLOCK_SIZE} data packets + {protocol.FEC_REDUNDANCY} redundancy")
    print("=" * 60)
    
    # Morse code table
    morse_table = {
        'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
        'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
        'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
        'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
        'Y': '-.--', 'Z': '--..',
        '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
        '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
        ' ': ' '
    }
    
    packet_count = 0
    fec_packet_count = 0
    
    for char in text.upper():
        if char not in morse_table:
            continue
        
        if char == ' ':
            # Word space
            packet, fec_packets = protocol.create_packet_fec(False, dit_ms * 4)
            sock.sendto(packet, (host, port))
            packet_count += 1
            time.sleep(0.01)
            
            # Send any FEC packets that were generated
            if fec_packets:
                for fec_pkt in fec_packets:
                    sock.sendto(fec_pkt, (host, port))
                    fec_packet_count += 1
                    time.sleep(0.005)
                print(f"  [FEC] Sent {len(fec_packets)} redundancy packets")
            
            continue
        
        morse = morse_table[char]
        print(f"{char} ({morse}):")
        
        for i, symbol in enumerate(morse):
            # Key down
            duration = dah_ms if symbol == '-' else dit_ms
            packet, fec_packets = protocol.create_packet_fec(True, duration)
            sock.sendto(packet, (host, port))
            packet_count += 1
            time.sleep(0.005)
            
            # Send any FEC packets that were generated
            if fec_packets:
                for fec_pkt in fec_packets:
                    sock.sendto(fec_pkt, (host, port))
                    fec_packet_count += 1
                    time.sleep(0.005)
                print(f"  [FEC] Sent {len(fec_packets)} redundancy packets")
            
            # Key up (inter-element or letter space)
            if i < len(morse) - 1:
                # Inter-element space
                packet, fec_packets = protocol.create_packet_fec(False, dit_ms)
            else:
                # Letter space
                packet, fec_packets = protocol.create_packet_fec(False, dit_ms * 3)
            
            sock.sendto(packet, (host, port))
            packet_count += 1
            time.sleep(0.005)
            
            # Send any FEC packets that were generated
            if fec_packets:
                for fec_pkt in fec_packets:
                    sock.sendto(fec_pkt, (host, port))
                    fec_packet_count += 1
                    time.sleep(0.005)
                print(f"  [FEC] Sent {len(fec_packets)} redundancy packets")
    
    # Flush remaining FEC block
    fec_packets = protocol.flush_fec_block()
    if fec_packets:
        for fec_pkt in fec_packets:
            sock.sendto(fec_pkt, (host, port))
            fec_packet_count += 1
            time.sleep(0.005)
        print(f"  [FEC] Sent {len(fec_packets)} redundancy packets (final)")
    
    # Send EOT
    eot_packets = protocol.create_eot_packet_fec()
    for eot_pkt in eot_packets:
        sock.sendto(eot_pkt, (host, port))
        time.sleep(0.005)
    
    print("=" * 60)
    print(f"Total data packets sent: {packet_count}")
    print(f"Total FEC packets sent: {fec_packet_count}")
    print(f"Overhead: {(fec_packet_count / packet_count * 100):.1f}%")
    print(f"Can recover from up to {protocol.FEC_REDUNDANCY} lost packets per block")
    print("EOT sent")
    
    sock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='CW Sender with FEC')
    parser.add_argument('host', nargs='?', default='127.0.0.1', help='Target host')
    parser.add_argument('wpm', nargs='?', type=int, default=25, help='Words per minute (12-35)')
    parser.add_argument('text', nargs='?', default='CQ CQ DE TEST', help='Text to send')
    
    args = parser.parse_args()
    
    send_text_fec(args.text, args.host, wpm=args.wpm)
