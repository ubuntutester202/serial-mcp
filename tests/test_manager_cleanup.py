
import unittest
import threading
import time
from serial_mcp.serial_manager import SerialManager

class TestManagerCleanup(unittest.TestCase):
    def test_close_idempotency(self):
        """Test that close can be called multiple times safely"""
        mgr = SerialManager()
        # Mock a port
        mgr._ports["COM1"] = type('obj', (object,), {'port': None, 'device': 'COM1', 'reader_thread': None})
        
        mgr.close()
        self.assertEqual(len(mgr._ports), 0)
        
        # Call again
        try:
            mgr.close()
        except Exception as e:
            self.fail(f"Second close raised exception: {e}")

if __name__ == '__main__':
    unittest.main()
