
import time
import serial_mcp
from serial_mcp.serial_manager import SerialManager, LogLine

def test_export():
    print("Testing export_logs_text...")
    mgr = SerialManager()
    
    # Inject some logs manually to avoid needing real ports
    ts = 1700000000.0
    with mgr._log_lock:
        mgr._logs.append(LogLine(ts=ts, text="Line 1", device="COM1"))
        mgr._logs.append(LogLine(ts=ts+1, text="Line 2", device="COM2"))
        mgr._logs.append(LogLine(ts=ts+2, text="Line 3", device="COM1"))
    
    # Test 1: Export all
    txt_all = mgr.export_logs_text()
    print("--- Export All ---")
    print(txt_all)
    assert "Line 1" in txt_all
    assert "Line 2" in txt_all
    assert "Line 3" in txt_all
    assert "[COM1]" in txt_all
    assert "[COM2]" in txt_all
    
    # Test 2: Export COM1
    txt_com1 = mgr.export_logs_text(device="COM1")
    print("\n--- Export COM1 ---")
    print(txt_com1)
    assert "Line 1" in txt_com1
    assert "Line 2" not in txt_com1
    assert "Line 3" in txt_com1
    
    print("\nSUCCESS: Export logic verified.")

if __name__ == "__main__":
    test_export()
