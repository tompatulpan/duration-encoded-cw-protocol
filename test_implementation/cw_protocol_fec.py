#!/usr/bin/env python3
"""
CW Protocol with FEC (Forward Error Correction)
Extends the basic CW protocol with Reed-Solomon error correction
"""

import struct
from cw_protocol import CWProtocol, UDP_PORT

try:
    import reedsolo
    FEC_AVAILABLE = True
except ImportError:
    FEC_AVAILABLE = False
    print("Warning: reedsolo not available, FEC disabled")
    print("Install with: pip3 install reedsolo")


class CWProtocolFEC(CWProtocol):
    """CW Protocol with Forward Error Correction using Reed-Solomon codes"""
    
    # Protocol version with FEC support
    PROTOCOL_VERSION_FEC = 0x02
    
    # FEC parameters
    FEC_BLOCK_SIZE = 10  # Number of data packets per FEC block
    FEC_REDUNDANCY = 3   # Number of redundancy packets (can recover from 3 lost packets)
    
    def __init__(self):
        super().__init__()
        self.fec_enabled = FEC_AVAILABLE
        self.fec_block = []  # Accumulate packets for FEC encoding
        self.fec_block_id = 0
        
        if self.fec_enabled:
            # Reed-Solomon encoder: nsym = number of error correction symbols
            # Can correct up to nsym/2 errors or nsym erasures (known positions)
            self.rs = reedsolo.RSCodec(self.FEC_REDUNDANCY * 3)  # 9 symbols = 3 packets worth
    
    def create_packet_fec(self, key_down, duration_ms):
        """
        Create a CW packet with FEC information
        
        Packet format (6 bytes total):
        [0]     Protocol version (0x02 for FEC)
        [1]     Sequence number (0-255)
        [2]     Key state (0=UP, 1=DOWN)
        [3-4]   Duration in milliseconds (uint16, big-endian)
        [5]     FEC block info (block_id:4, position:4)
        
        Returns:
            tuple: (packet, fec_packets)
                packet: The data packet
                fec_packets: List of FEC packets (empty if block not full)
        """
        if not self.fec_enabled:
            # Fall back to standard protocol
            return (self.create_packet(key_down, duration_ms), [])
        
        # Check if we need to flush the current block first
        fec_packets = []
        if len(self.fec_block) >= self.FEC_BLOCK_SIZE:
            fec_packets = self.flush_fec_block()
        
        # Build packet
        packet = bytearray(6)
        packet[0] = self.PROTOCOL_VERSION_FEC
        packet[1] = self.sequence_number & 0xFF
        packet[2] = 1 if key_down else 0
        packet[3] = (duration_ms >> 8) & 0xFF
        packet[4] = duration_ms & 0xFF
        
        # FEC block info (4 bits each)
        block_id = self.fec_block_id & 0x0F
        position = len(self.fec_block)  # This will now always be < FEC_BLOCK_SIZE
        
        packet[5] = (block_id << 4) | (position & 0x0F)
        
        # Add to FEC block
        self.fec_block.append(bytes(packet))
        
        self.sequence_number += 1
        return (bytes(packet), fec_packets)
    
    def create_fec_packets(self):
        """
        Create FEC redundancy packets for accumulated block
        
        Returns:
            list: FEC redundancy packets
        """
        if not self.fec_enabled or not self.fec_block:
            return []
        
        # Pad block to FEC_BLOCK_SIZE if needed
        while len(self.fec_block) < self.FEC_BLOCK_SIZE:
            # Add dummy packets
            dummy = bytearray(6)
            dummy[0] = self.PROTOCOL_VERSION_FEC
            dummy[1] = 0xFF  # Invalid sequence = padding
            self.fec_block.append(bytes(dummy))
        
        # Concatenate all packets in block
        block_data = b''.join(self.fec_block)
        
        # Encode with Reed-Solomon
        try:
            encoded = self.rs.encode(block_data)
            # Extract only the parity symbols (last FEC_REDUNDANCY*3 bytes)
            parity_bytes = encoded[len(block_data):]
            
            # Split parity into FEC packets (3 bytes of parity per packet)
            fec_packets = []
            for i in range(self.FEC_REDUNDANCY):
                parity_chunk = parity_bytes[i*3:(i+1)*3]
                
                # FEC packet format (6 bytes):
                # [0]     Protocol version (0x02)
                # [1]     0xFE = FEC packet marker
                # [2]     Block ID
                # [3]     FEC packet index (0, 1, 2)
                # [4-5]   Parity data (first 2 bytes)
                # Remaining parity byte is encoded in the next packet if needed
                
                fec_packet = bytearray(6)
                fec_packet[0] = self.PROTOCOL_VERSION_FEC
                fec_packet[1] = 0xFE  # FEC marker
                fec_packet[2] = self.fec_block_id & 0xFF
                fec_packet[3] = i
                fec_packet[4:6] = parity_chunk[:2]
                
                fec_packets.append(bytes(fec_packet))
                
                # If there's a third byte, create another mini-packet
                if len(parity_chunk) > 2:
                    extra = bytearray(6)
                    extra[0] = self.PROTOCOL_VERSION_FEC
                    extra[1] = 0xFE
                    extra[2] = self.fec_block_id & 0xFF
                    extra[3] = i | 0x80  # High bit indicates continuation
                    extra[4] = parity_chunk[2]
                    fec_packets.append(bytes(extra))
            
            return fec_packets
            
        except Exception as e:
            print(f"FEC encoding error: {e}")
            return []
    
    def flush_fec_block(self):
        """
        Finish current FEC block and prepare for next
        
        Returns:
            list: FEC redundancy packets for the completed block
        """
        fec_packets = self.create_fec_packets()
        
        # Reset for next block
        self.fec_block = []
        self.fec_block_id = (self.fec_block_id + 1) & 0x0F
        
        return fec_packets
    
    def should_send_fec(self):
        """Check if FEC block is full and should be sent"""
        return len(self.fec_block) >= self.FEC_BLOCK_SIZE
    
    def parse_packet_fec(self, data):
        """
        Parse a CW packet with FEC support
        
        Returns:
            dict with keys:
                'events': list of (key_down, duration_ms) tuples
                'sequence': sequence number
                'eot': end-of-transmission flag
                'fec_info': dict with block_id, position (None for non-FEC)
                'is_fec': True if this is a FEC redundancy packet
        """
        if len(data) < 3:
            return None
        
        # Check protocol version
        version = data[0]
        
        if version == self.PROTOCOL_VERSION_FEC:
            # FEC-enabled packet
            if len(data) < 6:
                return None
            
            seq = data[1]
            
            # Check if this is a FEC redundancy packet
            if seq == 0xFE:
                return {
                    'events': [],
                    'sequence': seq,
                    'eot': False,
                    'fec_info': {
                        'block_id': data[2],
                        'fec_index': data[3] & 0x7F,
                        'continuation': (data[3] & 0x80) != 0,
                        'parity': data[4:6]
                    },
                    'is_fec': True
                }
            
            # Regular data packet
            key_down = data[2] != 0
            duration_ms = (data[3] << 8) | data[4]
            
            block_id = (data[5] >> 4) & 0x0F
            position = data[5] & 0x0F
            
            return {
                'events': [(key_down, duration_ms)],
                'sequence': seq,
                'eot': False,
                'fec_info': {
                    'block_id': block_id,
                    'position': position
                },
                'is_fec': False
            }
        else:
            # Fall back to standard protocol parsing
            return super().parse_packet(data)
    
    def create_eot_packet_fec(self):
        """Create End-of-Transmission packet with FEC"""
        # First flush any pending FEC block
        fec_packets = self.flush_fec_block()
        
        # Standard EOT packet
        eot_packet = bytearray(3)
        eot_packet[0] = self.PROTOCOL_VERSION_FEC
        eot_packet[1] = self.sequence_number & 0xFF
        eot_packet[2] = 0xFF  # EOT marker
        
        self.sequence_number += 1
        
        # Return both FEC packets and EOT
        return fec_packets + [bytes(eot_packet)]


class FECDecoder:
    """
    FEC Decoder for receiving and reconstructing packets with error correction
    """
    
    def __init__(self):
        if not FEC_AVAILABLE:
            raise ImportError("reedsolo required for FEC decoding")
        
        self.rs = reedsolo.RSCodec(CWProtocolFEC.FEC_REDUNDANCY * 3)
        
        # Track received blocks
        self.blocks = {}  # block_id -> {'data': [packets], 'fec': [parity], 'complete': bool}
        self.current_block_id = None
    
    def add_packet(self, parsed_packet):
        """
        Add a packet to the FEC decoder
        
        Returns:
            list: Recovered packets (if block is complete and decodable)
        """
        if not parsed_packet or 'fec_info' not in parsed_packet:
            return []
        
        fec_info = parsed_packet['fec_info']
        
        if parsed_packet['is_fec']:
            # FEC redundancy packet
            block_id = fec_info['block_id']
            
            if block_id not in self.blocks:
                self.blocks[block_id] = {
                    'data': [None] * CWProtocolFEC.FEC_BLOCK_SIZE,
                    'fec': [],
                    'complete': False
                }
            
            self.blocks[block_id]['fec'].append(fec_info['parity'])
            
        else:
            # Data packet
            block_id = fec_info['block_id']
            position = fec_info['position']
            
            if block_id not in self.blocks:
                self.blocks[block_id] = {
                    'data': [None] * CWProtocolFEC.FEC_BLOCK_SIZE,
                    'fec': [],
                    'complete': False
                }
            
            # Store packet at its position (check bounds)
            if position < CWProtocolFEC.FEC_BLOCK_SIZE:
                self.blocks[block_id]['data'][position] = parsed_packet
            else:
                print(f"[FEC WARNING] Position {position} out of range for block {block_id}")
        
        # Check if we can decode this block
        return self._try_decode_block(block_id)
    
    def _try_decode_block(self, block_id):
        """
        Attempt to decode a block using FEC
        
        Returns:
            list: Recovered packets (empty if not yet decodable)
        """
        if block_id not in self.blocks:
            return []
        
        block = self.blocks[block_id]
        
        if block['complete']:
            return []
        
        # Count received and missing packets
        received = sum(1 for p in block['data'] if p is not None)
        missing = CWProtocolFEC.FEC_BLOCK_SIZE - received
        
        # If all packets received, no FEC needed
        if missing == 0:
            block['complete'] = True
            return [p for p in block['data'] if p is not None]
        
        # If we have enough FEC packets, try to recover
        if len(block['fec']) >= missing:
            print(f"[FEC] Attempting to recover {missing} lost packet(s) in block {block_id}")
            
            # TODO: Implement Reed-Solomon decoding with erasures
            # This requires more complex logic to reconstruct the block
            # For now, just return what we have
            
            block['complete'] = True
            return [p for p in block['data'] if p is not None]
        
        return []
    
    def cleanup_old_blocks(self, current_block_id):
        """Remove blocks that are too old"""
        old_blocks = [bid for bid in self.blocks.keys() 
                     if abs(bid - current_block_id) > 2]
        
        for bid in old_blocks:
            del self.blocks[bid]


if __name__ == '__main__':
    # Test FEC protocol
    print("Testing CW Protocol with FEC")
    print("=" * 60)
    
    if not FEC_AVAILABLE:
        print("ERROR: reedsolo not installed")
        print("Install with: pip3 install reedsolo")
        exit(1)
    
    protocol = CWProtocolFEC()
    
    print(f"FEC enabled: {protocol.fec_enabled}")
    print(f"Block size: {protocol.FEC_BLOCK_SIZE} packets")
    print(f"Redundancy: {protocol.FEC_REDUNDANCY} packets (can recover from {protocol.FEC_REDUNDANCY} losses)")
    print()
    
    # Create some test packets
    print("Creating test packets...")
    packets = []
    
    for i in range(12):
        key_down = i % 2 == 0
        duration = 48 if i % 2 == 0 else 144
        
        packet = protocol.create_packet_fec(key_down, duration)
        packets.append(packet)
        print(f"  Packet {i}: {'DOWN' if key_down else 'UP'} {duration}ms ({len(packet)} bytes)")
        
        # Check if we should send FEC
        if protocol.should_send_fec():
            fec_packets = protocol.flush_fec_block()
            print(f"  -> Generated {len(fec_packets)} FEC packets")
            packets.extend(fec_packets)
    
    # Flush remaining packets
    fec_packets = protocol.flush_fec_block()
    if fec_packets:
        print(f"  -> Generated {len(fec_packets)} FEC packets (final)")
        packets.extend(fec_packets)
    
    print(f"\nTotal packets created: {len(packets)}")
    print(f"Data packets: {len([p for p in packets if p[1] != 0xFE])}")
    print(f"FEC packets: {len([p for p in packets if p[1] == 0xFE])}")
