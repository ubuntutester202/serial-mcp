import unittest
from unittest.mock import MagicMock, patch
import sys
from serial_mcp.serial_manager import SerialManager

class TestRegistryScan(unittest.TestCase):
    def setUp(self):
        self.manager = SerialManager()
        # Mock serial to return nothing so we rely on registry
        self.mock_serial_patcher = patch('serial_mcp.serial_manager.serial')
        self.mock_serial = self.mock_serial_patcher.start()
        self.mock_serial.tools.list_ports.comports.return_value = []
        
    def tearDown(self):
        self.mock_serial_patcher.stop()

    def test_registry_scan(self):
        # Only run on Windows logic simulation
        with patch('sys.platform', 'win32'):
            with patch('winreg.OpenKey') as mock_open:
                with patch('winreg.QueryInfoKey') as mock_query:
                    with patch('winreg.EnumValue') as mock_enum:
                        # Setup mocks
                        mock_query.return_value = (0, 2, 0) # 2 values
                        # Return (name, value, type)
                        mock_enum.side_effect = [
                            ("Device1", "COM99", 1),
                            ("Device2", "COM100", 1)
                        ]
                        
                        ports = self.manager.list_ports()
                        
                        devices = [p['device'] for p in ports]
                        self.assertIn("COM99", devices)
                        self.assertIn("COM100", devices)
                        self.assertEqual(ports[0]['hwid'], "REGISTRY_DETECTED")

if __name__ == '__main__':
    unittest.main()
