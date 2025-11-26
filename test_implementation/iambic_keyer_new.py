"""
Iambic Keyer Implementation - Based on n1gp/iambic-keyer - https://github.com/n1gp/iambic-keyer
Clean state machine approach
"""
import time

class IambicKeyer:
    """Iambic keyer logic (Mode A and Mode B)"""
    
    # State constants
    IDLE = 0
    DIT = 1
    DAH = 2
    
    def __init__(self, wpm=20, mode='B'):
        self.mode = mode  # 'A' or 'B'
        self.set_speed(wpm)
        
        # State
        self.state = self.IDLE
        self.dit_memory = False
        self.dah_memory = False
        
    def set_speed(self, wpm):
        """Set keyer speed"""
        self.wpm = wpm
        self.dit_duration = 1200 / wpm  # ms
        self.dah_duration = self.dit_duration * 3
        self.element_space = self.dit_duration
        self.char_space = self.dit_duration * 3
    
    def update(self, dit_paddle, dah_paddle, send_element_callback):
        """
        Main keyer update - call this in a loop
        
        Args:
            dit_paddle: bool - dit paddle currently pressed
            dah_paddle: bool - dah paddle currently pressed  
            send_element_callback: function(key_down: bool, duration_ms: float)
                Called to send keyer output
        
        Returns:
            bool - True if keyer is active, False if idle
        """
        
        # State: IDLE - waiting for paddle press
        if self.state == self.IDLE:
            if dit_paddle:
                self.dit_memory = False
                self.dah_memory = False
                self.state = self.DIT
                # Send dit
                send_element_callback(True, self.dit_duration)
                time.sleep(self.dit_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Check if dah was pressed during dit (Mode B memory)
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
                    
            elif dah_paddle:
                self.dit_memory = False
                self.dah_memory = False
                self.state = self.DAH
                # Send dah
                send_element_callback(True, self.dah_duration)
                time.sleep(self.dah_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Check if dit was pressed during dah (Mode B memory)
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
            else:
                return False  # Still idle
                
        # State: DIT - just sent a dit
        elif self.state == self.DIT:
            # Sample paddles during element space
            if dit_paddle:
                self.dit_memory = True
            if dah_paddle:
                self.dah_memory = True
                
            # Decide what's next
            if self.dah_memory:
                # Send dah next
                self.dah_memory = False
                self.state = self.DAH
                send_element_callback(True, self.dah_duration)
                time.sleep(self.dah_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Check paddle during element
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
                    
            elif dit_paddle or self.dit_memory:
                # Repeat dit
                self.dit_memory = False
                self.state = self.DIT
                send_element_callback(True, self.dit_duration)
                time.sleep(self.dit_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
            else:
                # End of character - add char space
                extra_space = self.char_space - self.element_space
                if extra_space > 0:
                    send_element_callback(False, extra_space)
                    time.sleep(extra_space / 1000.0)
                self.state = self.IDLE
                
        # State: DAH - just sent a dah
        elif self.state == self.DAH:
            # Sample paddles during element space
            if dit_paddle:
                self.dit_memory = True
            if dah_paddle:
                self.dah_memory = True
                
            # Decide what's next
            if self.dit_memory:
                # Send dit next
                self.dit_memory = False
                self.state = self.DIT
                send_element_callback(True, self.dit_duration)
                time.sleep(self.dit_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                # Check paddle during element
                if self.mode == 'B' and dah_paddle:
                    self.dah_memory = True
                    
            elif dah_paddle or self.dah_memory:
                # Repeat dah
                self.dah_memory = False
                self.state = self.DAH
                send_element_callback(True, self.dah_duration)
                time.sleep(self.dah_duration / 1000.0)
                send_element_callback(False, self.element_space)
                time.sleep(self.element_space / 1000.0)
                
                if self.mode == 'B' and dit_paddle:
                    self.dit_memory = True
            else:
                # End of character - add char space
                extra_space = self.char_space - self.element_space
                if extra_space > 0:
                    send_element_callback(False, extra_space)
                    time.sleep(extra_space / 1000.0)
                self.state = self.IDLE
                
        return self.state != self.IDLE
