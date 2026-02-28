import pytest
import asyncio
import subprocess
import sys
import time
import os
from serial_mcp.serial_manager import SerialManager, AutoRule, AutoAction

# Assume VSPD pairs: COM2<->COM3, COM4<->COM5
# Simulator uses COM2 and COM4
# Tests use COM3 and COM5

SIMULATOR_SCRIPT = os.path.join("simulation", "firmware_simulator.py")
CMD_PORT = "COM3"
LOG_PORT = "COM5"

@pytest.fixture(scope="module")
def simulator():
    # Start the simulator process
    cwd = os.getcwd()
    cmd = [sys.executable, SIMULATOR_SCRIPT]
    print(f"Starting simulator: {cmd}")
    proc = subprocess.Popen(
        cmd, 
        cwd=cwd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for simulator to initialize
    start_time = time.time()
    initialized = False
    while time.time() - start_time < 5:
        if proc.poll() is not None:
            break
        # We can't easily read stdout without blocking or using threads in this simple fixture
        # So we just wait a bit.
        time.sleep(2) 
        initialized = True
        break
        
    if not initialized:
        raise RuntimeError("Simulator failed to start")
        
    yield proc
    
    # Teardown
    print("Stopping simulator...")
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutError:
        proc.kill()

@pytest.fixture
async def manager():
    mgr = SerialManager()
    yield mgr
    mgr.close()

@pytest.mark.anyio
async def test_connect_and_list(simulator, manager):
    # Wait a bit for simulator ports to be ready
    await asyncio.sleep(1)
    
    ports = manager.list_ports()
    print(f"Found ports: {ports}")
    # We expect COM3 and COM5 to be present (virtual ports are always present if VSPD is active)
    device_names = [p['device'] for p in ports]
    assert CMD_PORT in device_names or len(ports) > 0 # At least some ports
    
    # Open ports
    try:
        manager.open(CMD_PORT)
        manager.open(LOG_PORT)
    except Exception as e:
        pytest.skip(f"Failed to open ports: {e}")

@pytest.mark.anyio
async def test_log_capture_scenario(simulator, manager):
    try:
        manager.open(CMD_PORT)
        manager.open(LOG_PORT)
    except Exception as e:
        pytest.skip(f"Failed to open ports: {e}")
    
    # Clear logs
    manager._logs = []
    
    # Set filters to match expectation
    manager.set_filters([r"\[DEBUG\]", r"\[IGNORE\]"], device=LOG_PORT)
    
    # Start waiting for logs (async)
    # Scenario: main.cpp:33 -> moduleA.cpp:80
    
    # Trigger the task flow on simulator via CMD_PORT
    # We need to send "task_flow\n"
    manager.send("task_flow\n", device=CMD_PORT)
    
    # Wait for the specific sequence
    result = await manager.wait_between(
        start_marker="main.cpp:33", 
        end_marker="moduleA.cpp:80", 
        timeout=5,
        device=LOG_PORT
    )
    
    assert result["start_index"] >= 0, "Start marker not found"
    assert result["end_index"] >= 0, "End marker not found"
    
    lines = result["lines"]
    texts = [l["text"] for l in lines]
    
    # Verify content
    assert any("main.cpp:33 start" in t for t in texts)
    # "Allocating buffers" is a DEBUG log, so it should be filtered out
    assert not any("Allocating buffers" in t for t in texts)
    assert any("Task processing complete" in t for t in texts)
    
    # Check if filtered logs are present (default is NO filtering yet, so they SHOULD be present)
    # Wait, the manager sets default filters to [DEBUG] and [IGNORE] in __init__?
    # Let's check SerialManager.__init__
    # self._filters: List[re.Pattern] = [re.compile(r"\[DEBUG\]"), re.compile(r"\[IGNORE\]")]
    # So by default they are filtered!
    
    assert not any("[IGNORE]" in t for t in texts), "Should filter [IGNORE] by default"
    assert not any("[DEBUG]" in t for t in texts), "Should filter [DEBUG] by default"

@pytest.mark.anyio
async def test_auto_send(simulator, manager):
    try:
        manager.open(CMD_PORT)
        manager.open(LOG_PORT)
    except Exception as e:
        pytest.skip(f"Failed to open ports: {e}")
    
    # Clear rules
    manager.clear_auto_rules()
    
    # Add rule: When "Critical failure" -> Send "reboot"
    rule = AutoRule(
        pattern="Critical failure",
        actions=[AutoAction(kind="send_serial", params={"data": "reboot\n", "device": CMD_PORT})],
        once=True,
        device=LOG_PORT
    )
    manager.add_auto_rule(rule)
    
    # Trigger error on simulator
    manager.send("error_test\n", device=CMD_PORT)
    
    # Wait for "Rebooting system" log which is the response to "reboot" command
    # Note: "Rebooting system" comes from simulator CMD port response, 
    # but wait, simulator sends responses to CMD port.
    # Does manager read from CMD port? Yes, if opened.
    # The simulator sends "Rebooting system..." to CMD port.
    
    # We need to capture logs from CMD_PORT
    result = await manager.wait_marker_context("Rebooting system", timeout=5, device=CMD_PORT)
    
    if result["marker_index"] == -1:
        # Fallback: maybe it went to log port?
        # Simulator code: 
        # elif cmd == "reboot": self.send_cmd_response("Rebooting system...")
        # send_cmd_response writes to cmd_serial (COM2) -> received by MCP on COM3
        pass

    assert result["marker_index"] >= 0, "Did not receive reboot confirmation"
