import unittest
from unittest.mock import MagicMock, patch
import threading
import time
from serial_mcp.serial_manager import SerialManager, SerialState

class TestSerialManager(unittest.TestCase):
    def setUp(self):
        self.manager = SerialManager()
        # Mock the serial module
        self.mock_serial_patcher = patch('serial_mcp.serial_manager.serial')
        self.mock_serial = self.mock_serial_patcher.start()
        self.mock_serial.tools.list_ports.comports.return_value = []
        
    def tearDown(self):
        self.manager.close()
        self.mock_serial_patcher.stop()

    def test_open_close(self):
        # Setup mock port
        mock_port = MagicMock()
        mock_port.is_open = True
        self.mock_serial.Serial.return_value = mock_port
        
        # Test Open
        self.manager.open("COM1")
        self.assertIn("COM1", self.manager._ports)
        # We only check positionals or simple kwargs because constants are mocked
        self.mock_serial.Serial.assert_called()
        args, kwargs = self.mock_serial.Serial.call_args
        self.assertEqual(args[0], "COM1")
        self.assertEqual(kwargs['baudrate'], 115200)
        self.assertEqual(kwargs['timeout'], 0)
        
        # Test Close
        self.manager.close("COM1")
        self.assertNotIn("COM1", self.manager._ports)
        mock_port.close.assert_called()

    def test_send_ascii(self):
        mock_port = MagicMock()
        mock_port.is_open = True
        self.mock_serial.Serial.return_value = mock_port
        self.manager.open("COM1")
        
        # Test sending ASCII
        self.manager.send("Hello\n", "COM1")
        mock_port.write.assert_called_with(b"Hello\n")

    def test_send_hex(self):
        mock_port = MagicMock()
        mock_port.is_open = True
        self.mock_serial.Serial.return_value = mock_port
        self.manager.open("COM1")
        self.manager.set_mode("hex", "COM1")
        
        # Test sending Hex with spaces
        self.manager.send("48 65 6C 6C 6F", "COM1") # Hello
        mock_port.write.assert_called_with(b"Hello")
        
        # Test sending Hex without spaces
        self.manager.send("4142", "COM1") # AB
        mock_port.write.assert_called_with(b"AB")
        
        # Test invalid Hex
        with self.assertRaises(RuntimeError) as cm:
            self.manager.send("ZZ", "COM1")
        self.assertIn("Invalid HEX format", str(cm.exception))

    def test_multi_port_send(self):
        p1 = MagicMock()
        p2 = MagicMock()
        self.mock_serial.Serial.side_effect = [p1, p2]
        
        self.manager.open("COM1")
        self.manager.open("COM2")
        
        self.manager.send("Broadcast")
        
        p1.write.assert_called_with(b"Broadcast")
        p2.write.assert_called_with(b"Broadcast")

    def test_list_ports_status(self):
        # Mock available ports
        com1 = MagicMock()
        com1.device = "COM1"
        com1.description = "Port 1"
        com1.hwid = "ID1"
        
        self.mock_serial.tools.list_ports.comports.return_value = [com1]
        
        # Initially closed
        ports = self.manager.list_ports()
        self.assertEqual(ports[0]['is_open'], False)
        
        # Open port
        mock_port = MagicMock()
        self.mock_serial.Serial.return_value = mock_port
        self.manager.open("COM1")
        
        # Check status
        ports = self.manager.list_ports()
        self.assertEqual(ports[0]['is_open'], True)

if __name__ == '__main__':
    unittest.main()
