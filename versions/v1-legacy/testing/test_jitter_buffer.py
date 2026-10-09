#!/usr/bin/env python3
"""
Test script to demonstrate jitter buffer effect
Simulates various network conditions:
- Random jitter (variable packet delays)
- Packet loss
- Packet reordering
- Burst delays (simulates congestion)
"""

import socket
import time
import random
import sys
import threading
from cw_protocol import CWProtocol, UDP_PORT

class NetworkSimulator:
    """Simulate various network conditions"""
    
    def __init__(self, host, port, jitter_ms=50, loss_percent=0, reorder_percent=0, burst_delay_ms=0):
        self.host = host
        self.port = port
        self.jitter_ms = jitter_ms
        self.loss_percent = loss_percent
        self.reorder_percent = reorder_percent
        self.burst_delay_ms = burst_delay_ms
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.packet_queue = []
        self.queue_lock = threading.Lock()
        self.running = False
        self.stats = {
            'sent': 0,
            'dropped': 0,
            'reordered': 0,
            'delayed': 0
        }
    
    def start(self):
        """Start background thread for sending packets with delays"""
        self.running = True
        self.sender_thread = threading.Thread(target=self._sender_loop, daemon=True)
        self.sender_thread.start()
    
    def stop(self):
        """Stop background sender"""
        self.running = False
        if hasattr(self, 'sender_thread'):
            self.sender_thread.join(timeout=1.0)
    
    def _sender_loop(self):
        """Background thread that sends queued packets with proper delays"""
        while self.running:
            with self.queue_lock:
                if not self.packet_queue:
                    time.sleep(0.001)
                    continue
                
                # Check if first packet is ready to send
                send_time, packet = self.packet_queue[0]
                if time.time() >= send_time:
                    self.packet_queue.pop(0)
                    self.sock.sendto(packet, (self.host, self.port))
                    self.stats['sent'] += 1
                else:
                    time.sleep(0.001)
    
    def send_packet(self, packet, verbose=False):
        """
        Send packet with simulated network conditions
        
        Args:
            packet: Packet bytes to send
            verbose: Print what's happening
        
        Returns:
            dict with status info
        """
        # Simulate packet loss
        if self.loss_percent > 0 and random.random() * 100 < self.loss_percent:
            self.stats['dropped'] += 1
            if verbose:
                print("    [DROPPED]")
            return {'dropped': True}
        
        # Calculate delay
        base_jitter = random.randint(0, self.jitter_ms) if self.jitter_ms > 0 else 0
        
        # Add burst delay occasionally (simulates congestion)
        burst_delay = 0
        if self.burst_delay_ms > 0 and random.random() < 0.1:  # 10% chance of burst
            burst_delay = random.randint(0, self.burst_delay_ms)
            self.stats['delayed'] += 1
        
        total_delay = base_jitter + burst_delay
        send_time = time.time() + (total_delay / 1000.0)
        
        # Simulate packet reordering
        reorder = False
        if self.reorder_percent > 0 and random.random() * 100 < self.reorder_percent:
            # This packet will be sent slightly later than next packet
            send_time += 0.05  # 50ms extra delay
            reorder = True
            self.stats['reordered'] += 1
        
        with self.queue_lock:
            self.packet_queue.append((send_time, packet))
            # Keep queue sorted by send time
            self.packet_queue.sort(key=lambda x: x[0])
        
        if verbose:
            status_parts = []
            if base_jitter > 0:
                status_parts.append(f"jitter +{base_jitter}ms")
            if burst_delay > 0:
                status_parts.append(f"BURST +{burst_delay}ms")
            if reorder:
                status_parts.append("REORDER")
            status = f"({', '.join(status_parts)})" if status_parts else ""
            if status:
                print(f"    {status}")
        
        return {
            'dropped': False,
            'jitter_ms': base_jitter,
            'burst_ms': burst_delay,
            'reordered': reorder
        }
    
    def get_stats(self):
        """Get transmission statistics"""
        return self.stats.copy()


def send_with_jitter(host, port, wpm=20, jitter_ms=50, loss_percent=0, 
                     reorder_percent=0, burst_delay_ms=0, text="SOS SOS"):
    """
    Send CW pattern with simulated network conditions
    
    Args:
        host: Target hostname/IP
        port: UDP port
        wpm: Words per minute
        jitter_ms: Maximum random jitter (milliseconds)
        loss_percent: Percentage of packets to drop (0-100)
        reorder_percent: Percentage of packets to reorder (0-100)
        burst_delay_ms: Maximum additional burst delay (simulates congestion)
        text: Text to send in CW
    """
    from cw_auto_sender import CWAutoSender, MORSE_CODE
    
    protocol = CWProtocol()
    
    # Calculate timing for given WPM
    dit_ms = int(1200 / wpm)
    
    print(f"Sending to {host}:{port}")
    print(f"Speed: {wpm} WPM (dit={dit_ms}ms)")
    print(f"Text: '{text}'")
    print("-" * 60)
    print("Network conditions:")
    print(f"  Jitter:        0-{jitter_ms}ms")
    if loss_percent > 0:
        print(f"  Packet loss:   {loss_percent}%")
    if reorder_percent > 0:
        print(f"  Reordering:    {reorder_percent}%")
    if burst_delay_ms > 0:
        print(f"  Burst delays:  0-{burst_delay_ms}ms (10% chance)")
    print("-" * 60)
    
    # Create network simulator
    net_sim = NetworkSimulator(host, port, jitter_ms, loss_percent, 
                               reorder_percent, burst_delay_ms)
    net_sim.start()
    
    # Use auto sender to generate proper CW
    sender = CWAutoSender(host, port, wpm)
    
    # Intercept send_event to route through network simulator
    original_send = sender.send_event
    
    def simulated_send(key_down, duration_ms):
        packet = protocol.create_packet(key_down, duration_ms)
        state_str = "█ DOWN" if key_down else "  UP"
        print(f"  {state_str} {duration_ms:3d}ms", end='')
        net_sim.send_packet(packet, verbose=True)
        # Still call original for visual feedback
        if key_down:
            symbol = '▬' if duration_ms > dit_ms * 2 else '▪'
            print(f" {symbol}", end='', flush=True)
    
    sender.send_event = simulated_send
    
    # Send the text
    print("\nTransmitting:")
    sender.send_text(text)
    
    # Wait for all packets to be sent
    time.sleep(1.0)
    
    net_sim.stop()
    sender.close()
    
    # Show statistics
    stats = net_sim.get_stats()
    print("\n" + "=" * 60)
    print("TRANSMISSION STATISTICS")
    print("=" * 60)
    print(f"Packets sent:     {stats['sent']}")
    print(f"Packets dropped:  {stats['dropped']}")
    print(f"Packets delayed:  {stats['delayed']} (burst congestion)")
    print(f"Packets reordered: {stats['reordered']}")
    
    total = stats['sent'] + stats['dropped']
    if total > 0:
        actual_loss = (stats['dropped'] / total) * 100
        print(f"\nActual loss rate: {actual_loss:.1f}%")
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("\nWithout jitter buffer: You should hear timing variations")
    print("With jitter buffer:    Timing should be smooth and consistent")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Test DECW protocol with simulated network conditions',
        epilog='''
Examples:
  Basic jitter test:
    %(prog)s --jitter 50
  
  With packet loss:
    %(prog)s --jitter 100 --loss 5
  
  Heavy network issues:
    %(prog)s --jitter 150 --loss 10 --reorder 5 --burst 200
  
  Custom text:
    %(prog)s --text "CQ CQ DE KN4EIN" --wpm 25
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    
    parser.add_argument('--host', default='127.0.0.1',
                        help='Target host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=UDP_PORT,
                        help='UDP port (default: 7355)')
    parser.add_argument('--wpm', type=int, default=20,
                        help='Words per minute (default: 20)')
    parser.add_argument('--jitter', type=int, default=50,
                        help='Maximum jitter in milliseconds (default: 50)')
    parser.add_argument('--loss', type=int, default=0,
                        help='Packet loss percentage 0-100 (default: 0)')
    parser.add_argument('--reorder', type=int, default=0,
                        help='Packet reordering percentage 0-100 (default: 0)')
    parser.add_argument('--burst', type=int, default=0,
                        help='Maximum burst delay in ms to simulate congestion (default: 0)')
    parser.add_argument('--text', default='SOS SOS',
                        help='Text to send in CW (default: "SOS SOS")')
    parser.add_argument('--no-prompt', action='store_true',
                        help='Skip interactive prompt')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("DECW Network Condition Simulator")
    print("=" * 60)
    print()
    print("This script sends CW with simulated network issues.")
    print()
    print("To test:")
    print("  1. Start receiver WITHOUT jitter buffer:")
    print("     python3 cw_receiver.py")
    print("     → You should hear timing issues")
    print()
    print("  2. Start receiver WITH jitter buffer:")
    print("     python3 cw_receiver.py --jitter-buffer 100")
    print("     → Timing should be smooth despite network issues")
    print()
    
    if not args.no_prompt:
        try:
            input("Press ENTER to start test (Ctrl+C to cancel)...")
        except KeyboardInterrupt:
            print("\nCancelled")
            sys.exit(0)
    
    send_with_jitter(args.host, args.port, args.wpm, args.jitter,
                    args.loss, args.reorder, args.burst, args.text)
