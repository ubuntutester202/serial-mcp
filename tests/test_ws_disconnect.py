import pytest
from fastapi.testclient import TestClient
from serial_mcp.webapp import app, set_manager
from serial_mcp.serial_manager import SerialManager
import time

def test_websocket_disconnect_error():
    # Setup manager
    mgr = SerialManager()
    set_manager(mgr)
    
    with TestClient(app) as client:
        with client.websocket_connect("/ws/logs") as websocket:
            # Add a log so the server tries to send it
            # mgr._logs is a list of LogLine objects
            mgr._append_log(b"test log", "device1", packet=False)
            
            # Receive one message to ensure connection is established and working
            data = websocket.receive_json()
            assert data["text"] == "test log"
            
            # Now close the client connection
            websocket.close()
            
            # Add another log. The server loop (running in background/async) 
            # will try to send this and should encounter the disconnect.
            mgr._append_log(b"test log 2", "device1", packet=False)

            
    # If the server code raises RuntimeError during cleanup/loop, pytest might catch it.
