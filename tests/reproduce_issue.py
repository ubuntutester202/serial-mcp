
import unittest
import asyncio
from fastapi.testclient import TestClient
from serial_mcp.webapp import app, manager
from serial_mcp.serial_manager import SerialManager

class TestLargeLogIssue(unittest.TestCase):
    def setUp(self):
        # Reset manager logs
        manager._logs = []
        manager._log_base_index = 0
        manager._log_max_lines = 500000 # Increase limit for test
        
        # Populate with 400,000 logs
        print("Populating 400,000 logs...")
        # Direct injection to be faster
        import time
        from serial_mcp.serial_manager import LogLine
        
        # Create a large batch
        batch = []
        base_ts = time.time()
        for i in range(400000):
            batch.append(LogLine(ts=base_ts + i*0.001, text=f"Log line {i}", device="test"))
        
        with manager._log_lock:
            manager._logs.extend(batch)
            
        print(f"Manager stats: {manager.get_stats()}")
        self.client = TestClient(app)

    def test_stats_endpoint(self):
        resp = self.client.get("/logs/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        print(f"Stats response: {data}")
        self.assertEqual(data["total_logs"], 400000)

    def test_websocket_default_behavior(self):
        # Test WS connection without start_index (should default to tail 2000)
        # Note: TestClient.websocket_connect might not support query params easily in older versions,
        # but let's try standard path
        
        # Case 1: No params -> Should get last 2000 logs
        # But wait, our new code in webapp.py handles start_index=-1 default.
        # If we don't pass start_index, it might be None or validation error if not optional?
        # In webapp.py: async def ws_logs(ws: WebSocket, device: str = None, start_index: int = -1):
        
        with self.client.websocket_connect("/ws/logs") as websocket:
            # Receive first message
            data = websocket.receive_json()
            # The first message should be around index 398000
            print(f"First WS message index: {data.get('index')}")
            self.assertGreaterEqual(data.get('index'), 398000)

    def test_websocket_with_explicit_index(self):
        # Case 2: start_index = 399900
        with self.client.websocket_connect("/ws/logs?start_index=399900") as websocket:
            data = websocket.receive_json()
            print(f"Explicit WS message index: {data.get('index')}")
            self.assertEqual(data.get('index'), 399900)

    def test_websocket_from_zero(self):
        # Case 3: start_index = 0 (simulating the bug)
        # We only read one to verify start
        with self.client.websocket_connect("/ws/logs?start_index=0") as websocket:
            data = websocket.receive_json()
            print(f"Zero WS message index: {data.get('index')}")
            self.assertEqual(data.get('index'), 0)

if __name__ == '__main__':
    unittest.main()
