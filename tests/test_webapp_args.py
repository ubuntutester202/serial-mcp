import unittest
import sys
from unittest.mock import patch, MagicMock
from serial_mcp.webapp import run
from serial_mcp.serial_manager import SerialManager

class TestWebappArgs(unittest.TestCase):
    @patch('serial_mcp.webapp.uvicorn')
    @patch('serial_mcp.webapp.manager')
    def test_args_parsing(self, mock_manager, mock_uvicorn):
        # Mock sys.argv
        test_args = ['webapp.py', '--port', '9000', '--debug']
        with patch.object(sys, 'argv', test_args):
            run()
            
            # Verify port
            mock_uvicorn.run.assert_called()
            kwargs = mock_uvicorn.run.call_args[1]
            self.assertEqual(kwargs['port'], 9000)

if __name__ == '__main__':
    unittest.main()
