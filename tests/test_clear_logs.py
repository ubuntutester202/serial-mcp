import pytest
import time
from serial_mcp.serial_manager import SerialManager, LogLine

@pytest.mark.anyio
async def test_clear_logs():
    mgr = SerialManager()
    
    # Inject some logs
    with mgr._log_lock:
        mgr._logs.append(LogLine(ts=time.time(), text="Log 1", device="dev1"))
        mgr._logs.append(LogLine(ts=time.time(), text="Log 2", device="dev2"))
        mgr._logs.append(LogLine(ts=time.time(), text="Log 3", device="dev1"))
        mgr._log_base_index = 10 # Simulate some history
    
    assert len(mgr.get_logs()) == 3
    
    # Clear device dev1
    mgr.clear_logs("dev1")
    logs = mgr.get_logs()
    assert len(logs) == 1
    assert logs[0]["text"] == "Log 2"
    assert logs[0]["device"] == "dev2"
    
    # Clear all
    mgr.clear_logs(None)
    assert len(mgr.get_logs()) == 0
    assert mgr._log_base_index == 0
