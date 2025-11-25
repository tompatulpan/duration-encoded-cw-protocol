#!/usr/bin/env python3
"""
Forward Error Correction (FEC) for CW Protocol

Implements simple FEC using packet duplication and XOR redundancy.
Two strategies:
1. Simple duplication - send each packet N times
2. XOR parity - send groups of K packets plus 1 XOR parity packet
"""

import struct
from cw_protocol import CWProtocol

class CWProtocolFEC(CWProtocol):
    """CW Protocol with Forward Error Correction"""
    
    def __init__(self, fec_mode='duplicate', fec_param=2):
        """
        Initialize FEC-enabled protocol
        
        Args:
            fec_mode: 'duplicate' or 'xor'
            fec_param: For duplicate: number of copies (2-5)
                      For xor: group size K (2-10)
        """
        super().__init__()
        self.fec_mode = fec_mode
        self.fec_param = fec_param
        
        # For XOR mode
        self.xor_buffer = []  # Buffer of packets waiting for parity
        
    def create_packet_with_fec(self, key_down, duration_ms, sequence=None):
        """
        Create packet(s) with FEC
        
        Returns: list of packets to send
        """
        # Create base packet
        base_packet = self.create_packet(key_down, duration_ms, sequence)
        
        if self.fec_mode == 'duplicate':
            # Simple duplication - send same packet N times
            # Each duplicate uses same sequence number
            return [base_packet] * self.fec_param
            
        elif self.fec_mode == 'xor':
            # XOR parity mode - buffer packets and send parity
            self.xor_buffer.append(base_packet)
            packets_to_send = [base_packet]
            
            # When we have K packets, send parity packet
            if len(self.xor_buffer) >= self.fec_param:
                parity = self._create_xor_parity(self.xor_buffer)
                packets_to_send.append(parity)
                self.xor_buffer = []
                
            return packets_to_send
            
        else:
            # No FEC
            return [base_packet]
    
    def _create_xor_parity(self, packets):
        """
        Create XOR parity packet from group of packets
        
        The parity packet has special marker in client_id field
        and XORed payload of all packets in group.
        """
        if not packets:
            return None
        
        # Start with first packet as base
        result = bytearray(packets[0])
        
        # XOR with remaining packets
        for pkt in packets[1:]:
            # Extend result if needed
            if len(pkt) > len(result):
                result.extend(b'\x00' * (len(pkt) - len(result)))
            
            # XOR byte by byte
            for i in range(len(pkt)):
                result[i] ^= pkt[i]
        
        # Mark as parity packet by setting client_id MSB
        result[2] |= 0x80
        
        return bytes(result)
    
    def flush_xor_buffer(self):
        """
        Flush any pending XOR packets (call at end of transmission)
        
        Returns: list of packets (parity if buffer not empty)
        """
        if self.fec_mode == 'xor' and self.xor_buffer:
            parity = self._create_xor_parity(self.xor_buffer)
            self.xor_buffer = []
            return [parity] if parity else []
        return []


class FECReceiver:
    """Receiver with FEC reconstruction capability"""
    
    def __init__(self, fec_mode='duplicate'):
        """
        Initialize FEC receiver
        
        Args:
            fec_mode: 'duplicate' or 'xor'
        """
        self.fec_mode = fec_mode
        self.received_sequences = {}  # seq -> packet (for deduplication)
        self.xor_groups = {}  # group_id -> list of packets
        
    def process_packet(self, packet_bytes):
        """
        Process received packet with FEC handling
        
        Returns: packet_bytes if new/valid, None if duplicate
        """
        if len(packet_bytes) < 3:
            return None
        
        seq = packet_bytes[1]
        client_id = packet_bytes[2]
        
        # Check if this is a parity packet (MSB of client_id set)
        is_parity = bool(client_id & 0x80)
        
        if self.fec_mode == 'duplicate':
            # Simple deduplication
            if seq in self.received_sequences:
                # Duplicate - ignore
                return None
            else:
                # New packet - store and process
                self.received_sequences[seq] = packet_bytes
                # Keep cache size limited
                if len(self.received_sequences) > 256:
                    # Remove oldest
                    oldest_seq = min(self.received_sequences.keys())
                    del self.received_sequences[oldest_seq]
                return packet_bytes
                
        elif self.fec_mode == 'xor':
            if is_parity:
                # TODO: Implement XOR reconstruction
                # For now, just ignore parity packets
                return None
            else:
                # Normal packet
                if seq in self.received_sequences:
                    return None
                self.received_sequences[seq] = packet_bytes
                if len(self.received_sequences) > 256:
                    oldest_seq = min(self.received_sequences.keys())
                    del self.received_sequences[oldest_seq]
                return packet_bytes
        
        # No FEC
        return packet_bytes
    
    def detect_loss(self, expected_seq, received_seq):
        """
        Detect if packets were lost
        
        Returns: list of missing sequence numbers
        """
        if received_seq < expected_seq:
            # Sequence wrapped around
            missing = []
        else:
            missing = list(range(expected_seq, received_seq))
        
        # Filter out sequences we actually received
        missing = [s for s in missing if s not in self.received_sequences]
        
        return missing
    
    def interpolate_missing(self, seq_before, seq_after, packets_before, packets_after):
        """
        Attempt to interpolate missing packet(s) based on CW patterns
        
        For CW, timing is often predictable:
        - Dits are typically 60ms, dahs 180ms
        - Alternating up/down pattern
        
        Args:
            seq_before: sequence number before gap
            seq_after: sequence number after gap
            packets_before: recent packets before gap
            packets_after: packet after gap
            
        Returns: list of interpolated packets (or None if can't interpolate)
        """
        gap_size = seq_after - seq_before - 1
        
        # Only interpolate small gaps (1-2 packets)
        if gap_size < 1 or gap_size > 2:
            return None
        
        # Parse packets to understand pattern
        if not packets_before:
            return None
        
        last_packet = packets_before[-1]
        if len(last_packet) < 4:
            return None
        
        # Extract last event
        last_event_byte = last_packet[3]
        last_key_down = bool(last_event_byte & 0x80)
        
        # CW alternates: if last was DOWN, next should be UP
        interpolated_key_down = not last_key_down
        
        # Estimate duration: average of recent events
        durations = []
        for pkt in packets_before[-3:]:
            if len(pkt) >= 4:
                event_byte = pkt[3]
                # Rough decode (good enough for interpolation)
                timing = event_byte & 0x7F
                if timing <= 0x3F:
                    duration = timing
                elif timing <= 0x5F:
                    duration = 64 + 2 * (timing - 0x40)
                else:
                    duration = 128 + 8 * (timing - 0x60)
                durations.append(duration)
        
        if not durations:
            # Default to typical dit timing
            est_duration = 60
        else:
            est_duration = int(sum(durations) / len(durations))
        
        # Create interpolated packet(s)
        from cw_protocol import CWProtocol
        proto = CWProtocol()
        
        interpolated = []
        for i in range(gap_size):
            seq = seq_before + 1 + i
            # Alternate key state for each missing packet
            key_down = interpolated_key_down if (i % 2 == 0) else (not interpolated_key_down)
            pkt = proto.create_packet(key_down, est_duration, sequence=seq)
            interpolated.append(pkt)
        
        return interpolated
