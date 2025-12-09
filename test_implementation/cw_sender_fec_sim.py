#!/usr/bin/env python3
"""
CW Sender with FEC and Network Simulation
Simulates packet loss and jitter for testing FEC recovery
"""

import socket
import time
import random
import argparse
from cw_protocol_fec import CWProtocolFEC, UDP_PORT


class NetworkSimulator:
    """Simulate network conditions (packet loss, jitter, reordering)"""
    
    def __init__(self, loss_rate=0.0, jitter_ms=0, reorder_prob=0.0):
        """
        Initialize network simulator
        
        Args:
            loss_rate: Packet loss probability (0.0 to 1.0)
            jitter_ms: Maximum jitter in milliseconds (±jitter_ms)
            reorder_prob: Probability of packet reordering (0.0 to 1.0)
        """
        self.loss_rate = loss_rate
        self.jitter_ms = jitter_ms
        self.reorder_prob = reorder_prob
        
        self.packets_sent = 0
        self.packets_dropped = 0
        self.packets_delayed = 0
        self.packets_reordered = 0
        
        # Buffer for reordering
        self.reorder_buffer = []
    
    def should_drop(self):
        """Determine if packet should be dropped"""
        if random.random() < self.loss_rate:
            self.packets_dropped += 1
            return True
        return False
    
    def get_delay(self):
        """Get jitter delay for packet"""
        if self.jitter_ms > 0:
            delay = random.uniform(-self.jitter_ms, self.jitter_ms) / 1000.0
            if delay > 0:
                self.packets_delayed += 1
            return max(0, delay)
        return 0
    
    def send_packet(self, sock, packet, addr):
        """
        Send packet with network simulation
        
        Args:
            sock: Socket to send on
            packet: Packet data
            addr: Destination address tuple (host, port)
        """
        self.packets_sent += 1
        
        # Check if packet should be dropped
        if self.should_drop():
            return
        
        # Check if packet should be reordered
        if random.random() < self.reorder_prob and len(self.reorder_buffer) > 0:
            # Send a buffered packet first
            buffered = self.reorder_buffer.pop(0)
            delay = self.get_delay()
            if delay > 0:
                time.sleep(delay)
            sock.sendto(buffered, addr)
            self.packets_reordered += 1
            
            # Buffer current packet
            self.reorder_buffer.append(packet)
        else:
            # Send packet with jitter
            delay = self.get_delay()
            if delay > 0:
                time.sleep(delay)
            sock.sendto(packet, addr)
            
            # Occasionally buffer packets for reordering
            if random.random() < self.reorder_prob * 0.5:
                self.reorder_buffer.append(packet)
    
    def flush(self, sock, addr):
        """Flush any buffered packets"""
        for packet in self.reorder_buffer:
            sock.sendto(packet, addr)
        self.reorder_buffer = []
    
    def get_stats(self):
        """Get simulation statistics"""
        return {
            'sent': self.packets_sent,
            'dropped': self.packets_dropped,
            'delayed': self.packets_delayed,
            'reordered': self.packets_reordered,
            'loss_rate': (self.packets_dropped / max(1, self.packets_sent)) * 100
        }


def send_text_fec_sim(text, host='127.0.0.1', port=UDP_PORT, wpm=25, 
                      loss_rate=0.0, jitter_ms=0, reorder_prob=0.0):
    """
    Send text as CW with FEC and network simulation
    
    Args:
        text: Text to send
        host: Target host
        port: UDP port
        wpm: Words per minute (12-35)
        loss_rate: Packet loss rate (0.0 to 1.0, e.g., 0.1 = 10%)
        jitter_ms: Maximum jitter in milliseconds
        reorder_prob: Probability of packet reordering (0.0 to 1.0)
    """
    protocol = CWProtocolFEC()
    
    if not protocol.fec_enabled:
        print("ERROR: FEC not available (reedsolo not installed)")
        print("Install with: pip3 install reedsolo")
        return
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Initialize network simulator
    net_sim = NetworkSimulator(loss_rate, jitter_ms, reorder_prob)
    
    # Calculate timing
    dit_ms = int(1200 / wpm)
    dah_ms = dit_ms * 3
    
    print(f"Sending '{text}' with FEC to {host}:{port} at {wpm} WPM")
    print(f"FEC: {protocol.FEC_BLOCK_SIZE} data packets + {protocol.FEC_REDUNDANCY} redundancy")
    print()
    print("Network Simulation:")
    print(f"  Packet loss rate: {loss_rate * 100:.1f}%")
    print(f"  Jitter: ±{jitter_ms}ms")
    print(f"  Reorder probability: {reorder_prob * 100:.1f}%")
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
            net_sim.send_packet(sock, packet, (host, port))
            packet_count += 1
            time.sleep(0.01)
            
            # Send any FEC packets that were generated
            if fec_packets:
                for fec_pkt in fec_packets:
                    net_sim.send_packet(sock, fec_pkt, (host, port))
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
            net_sim.send_packet(sock, packet, (host, port))
            packet_count += 1
            time.sleep(0.005)
            
            # Send any FEC packets that were generated
            if fec_packets:
                for fec_pkt in fec_packets:
                    net_sim.send_packet(sock, fec_pkt, (host, port))
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
            
            net_sim.send_packet(sock, packet, (host, port))
            packet_count += 1
            time.sleep(0.005)
            
            # Send any FEC packets that were generated
            if fec_packets:
                for fec_pkt in fec_packets:
                    net_sim.send_packet(sock, fec_pkt, (host, port))
                    fec_packet_count += 1
                    time.sleep(0.005)
                print(f"  [FEC] Sent {len(fec_packets)} redundancy packets")
    
    # Flush remaining FEC block
    fec_packets = protocol.flush_fec_block()
    if fec_packets:
        for fec_pkt in fec_packets:
            net_sim.send_packet(sock, fec_pkt, (host, port))
            fec_packet_count += 1
            time.sleep(0.005)
        print(f"  [FEC] Sent {len(fec_packets)} redundancy packets (final)")
    
    # Flush any reordered packets
    net_sim.flush(sock, (host, port))
    
    # Send EOT
    eot_packets = protocol.create_eot_packet_fec()
    for eot_pkt in eot_packets:
        net_sim.send_packet(sock, eot_pkt, (host, port))
        time.sleep(0.005)
    
    # Get simulation statistics
    sim_stats = net_sim.get_stats()
    
    print("=" * 60)
    print("Transmission Statistics:")
    print(f"Total data packets: {packet_count}")
    print(f"Total FEC packets: {fec_packet_count}")
    print(f"FEC overhead: {(fec_packet_count / packet_count * 100):.1f}%")
    print()
    print("Network Simulation Results:")
    print(f"  Packets attempted: {sim_stats['sent']}")
    print(f"  Packets dropped: {sim_stats['dropped']} ({sim_stats['loss_rate']:.1f}%)")
    print(f"  Packets delayed: {sim_stats['delayed']}")
    print(f"  Packets reordered: {sim_stats['reordered']}")
    print()
    print(f"Expected delivery: {sim_stats['sent'] - sim_stats['dropped']} packets")
    print(f"FEC can recover: up to {protocol.FEC_REDUNDANCY} lost per {protocol.FEC_BLOCK_SIZE} data packets")
    print("=" * 60)
    print("EOT sent")
    
    sock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='CW Sender with FEC and Network Simulation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 10% packet loss
  python3 cw_sender_fec_sim.py localhost 25 "CQ DE TEST" --loss 0.1
  
  # 20% loss + 50ms jitter
  python3 cw_sender_fec_sim.py localhost 25 "CQ DE TEST" --loss 0.2 --jitter 50
  
  # 15% loss + 30ms jitter + 10% reordering
  python3 cw_sender_fec_sim.py localhost 25 "CQ DE TEST" --loss 0.15 --jitter 30 --reorder 0.1
  
  # Extreme conditions (30% loss)
  python3 cw_sender_fec_sim.py localhost 25 "CQ DE TEST" --loss 0.3 --jitter 100
        """
    )
    
    parser.add_argument('host', nargs='?', default='127.0.0.1', 
                       help='Target host (default: 127.0.0.1)')
    parser.add_argument('wpm', nargs='?', type=int, default=25, 
                       help='Words per minute (default: 25)')
    parser.add_argument('text', nargs='?', default='CQ CQ DE TEST', 
                       help='Text to send (default: "CQ CQ DE TEST")')
    
    # Network simulation options
    parser.add_argument('--loss', type=float, default=0.0, 
                       help='Packet loss rate 0.0-1.0 (default: 0.0, e.g., 0.1 = 10%%)')
    parser.add_argument('--jitter', type=int, default=0, 
                       help='Maximum jitter in ms (default: 0, e.g., 50 = ±50ms)')
    parser.add_argument('--reorder', type=float, default=0.0, 
                       help='Packet reordering probability 0.0-1.0 (default: 0.0)')
    
    args = parser.parse_args()
    
    # Validate parameters
    if args.loss < 0 or args.loss > 1:
        parser.error("Loss rate must be between 0.0 and 1.0")
    if args.jitter < 0:
        parser.error("Jitter must be non-negative")
    if args.reorder < 0 or args.reorder > 1:
        parser.error("Reorder probability must be between 0.0 and 1.0")
    
    send_text_fec_sim(args.text, args.host, wpm=args.wpm,
                     loss_rate=args.loss, jitter_ms=args.jitter, 
                     reorder_prob=args.reorder)
