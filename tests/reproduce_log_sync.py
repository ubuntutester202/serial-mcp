import asyncio
import time
import serial_mcp
print(f"DEBUG: serial_mcp file: {serial_mcp.__file__}")
from serial_mcp.serial_manager import SerialManager, SerialState

class MockSerial:
    def __init__(self):
        self.is_open = True
        self.written_data = b""
    def write(self, data):
        self.written_data += data
    def read(self, size):
        return b""
    def close(self):
        self.is_open = False

def test_send_logs_tx():
    print("Initializing SerialManager...")
    mgr = SerialManager()
    
    # Inject Mock Port
    device_name = "COM_MOCK"
    mock_port = MockSerial()
    
    # We need to use the internal _ports dict directly to inject
    # The SerialState dataclass is required
    state = SerialState(device=device_name, port=mock_port)
    mgr._ports[device_name] = state
    
    print(f"Sending 'test_command' to {device_name}...")
    try:
        mgr.send("test_command", device=device_name)
    except Exception as e:
        print(f"Send failed: {e}")
        return

    print("Checking logs...")
    logs = mgr.get_logs(device=device_name)
    
    found = False
    for log in logs:
        print(f"Log: {log}")
        if ">> test_command" in log["text"]:
            found = True
            print("SUCCESS: Found TX log entry.")
            break
            
    if not found:
        print("FAILURE: Did not find '>> test_command' in logs.")
        print("All logs:", logs)
    else:
        # Also check global logs (device=None)
        all_logs = mgr.get_logs(device=None)
        found_global = any(">> test_command" in l["text"] for l in all_logs)
        if found_global:
            print("SUCCESS: Found TX log entry in global logs.")
        else:
            print("FAILURE: Did not find TX log entry in global logs.")

if __name__ == "__main__":
    test_send_logs_tx()
