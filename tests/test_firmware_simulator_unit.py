import unittest
from unittest.mock import MagicMock, patch, PropertyMock
import sys
import os
import threading
import time

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../simulation')))

from firmware_simulator import FirmwareSimulator

class TestFirmwareSimulatorUnit(unittest.TestCase):
    def setUp(self):
        self.sim = FirmwareSimulator()
        self.sim.cmd_serial = MagicMock()
        self.sim.log_serial = MagicMock()
        self.sim.cmd_serial.is_open = True
        
    def test_process_command_help(self):
        """Test that process_command('help') sends response."""
        with patch.object(self.sim, 'send_cmd_response') as mock_send:
            self.sim.process_command('help')
            self.assertTrue(mock_send.called)
            # Check if one of the calls contained "Available Commands"
            found = False
            for call in mock_send.call_args_list:
                if "Available Commands" in call[0][0]:
                    found = True
                    break
            self.assertTrue(found)

    def test_command_loop_cr_only(self):
        """Test that command_loop handles '\\r' (Carriage Return) only."""
        # Setup mock for in_waiting and read
        # in_waiting is accessed twice per iteration (check and read arg)
        type(self.sim.cmd_serial).in_waiting = PropertyMock(side_effect=[5, 5, 0, 0])
        self.sim.cmd_serial.read.return_value = b'help\r'
        
        called_cmds = []
        def side_effect(cmd):
            called_cmds.append(cmd)
            self.sim.running = False
            
        self.sim.process_command = side_effect
        
        self.sim.command_loop()
        
        self.assertIn('help', called_cmds)

    def test_command_loop_crlf(self):
        """Test that command_loop handles '\\r\\n'."""
        self.sim.running = True
        type(self.sim.cmd_serial).in_waiting = PropertyMock(side_effect=[6, 6, 0, 0])
        self.sim.cmd_serial.read.return_value = b'help\r\n'
        
        called_cmds = []
        def side_effect(cmd):
            called_cmds.append(cmd)
            self.sim.running = False
            
        self.sim.process_command = side_effect
        
        self.sim.command_loop()
        
        self.assertIn('help', called_cmds)

    def test_command_loop_split_packets(self):
        """Test that command_loop handles split packets (he... lp\\r)."""
        self.sim.running = True
        # Iteration 1: 'he' (len 2) -> in_waiting called twice
        # Iteration 2: 'lp\r' (len 3) -> in_waiting called twice
        type(self.sim.cmd_serial).in_waiting = PropertyMock(side_effect=[2, 2, 3, 3, 0, 0])
        self.sim.cmd_serial.read.side_effect = [b'he', b'lp\r']
        
        called_cmds = []
        def side_effect(cmd):
            called_cmds.append(cmd)
            self.sim.running = False
            
        self.sim.process_command = side_effect
        
        self.sim.command_loop()
        
        self.assertIn('help', called_cmds)

if __name__ == '__main__':
    unittest.main()
