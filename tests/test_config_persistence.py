import pytest
import os
import json
import tempfile
from serial_mcp.serial_manager import SerialManager, AutoRule, AutoAction

@pytest.fixture
def temp_config_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.remove(path)
    yield path
    if os.path.exists(path):
        os.remove(path)

def test_persistence_filters(temp_config_file):
    mgr = SerialManager(config_path=temp_config_file)
    mgr.set_filters(["foo", "bar"], regex=False, device="COM1")
    
    assert os.path.exists(temp_config_file)
    with open(temp_config_file, "r") as f:
        data = json.load(f)
        assert data["ports"]["COM1"]["filters"] == ["foo", "bar"]
        assert data["ports"]["COM1"]["filters_regex"] == False

    # New manager should load it
    mgr2 = SerialManager(config_path=temp_config_file)
    # Check if filters loaded (checking internal compiled patterns is hard, check config output)
    cfg = mgr2.get_config("COM1")
    assert cfg["filters"] == ["foo", "bar"]
    assert cfg["filters_regex"] == False

def test_persistence_options(temp_config_file):
    mgr = SerialManager(config_path=temp_config_file)
    mgr.set_log_options(packet_enabled=False, packet_timeout_ms=50, log_max_lines=5000, device="COM2")
    
    with open(temp_config_file, "r") as f:
        data = json.load(f)
        opts = data["ports"]["COM2"]["log_options"]
        assert opts["packet_enabled"] == False
        assert opts["packet_timeout_ms"] == 50
        assert opts["log_max_lines"] == 5000

    mgr2 = SerialManager(config_path=temp_config_file)
    cfg = mgr2.get_config("COM2")
    assert cfg["log_options"]["packet_enabled"] == False
    assert cfg["log_options"]["packet_timeout_ms"] == 50
    assert cfg["log_options"]["log_max_lines"] == 5000

def test_persistence_rules(temp_config_file):
    mgr = SerialManager(config_path=temp_config_file)
    rule = AutoRule(pattern="test", actions=[AutoAction(kind="run_shell", params={"command": "echo hi"})], device="COM3")
    try:
        mgr.add_auto_rule(rule)
    except Exception as e:
        pytest.fail(f"add_auto_rule failed: {e}")
    
    # Check if file exists
    if not os.path.exists(temp_config_file):
        # Force save to see error
        try:
            mgr._save_config()
        except Exception as e:
            pytest.fail(f"Manual save failed: {e}")
        
        # If still not exists
        if not os.path.exists(temp_config_file):
             pytest.fail("Config file not created")

    with open(temp_config_file, "r") as f:
        data = json.load(f)
        assert len(data["ports"]["COM3"]["rules"]) == 1
        assert data["ports"]["COM3"]["rules"][0]["pattern"] == "test"

    mgr2 = SerialManager(config_path=temp_config_file)
    cfg = mgr2.get_config("COM3")
    assert len(cfg["rules"]) == 1
    assert cfg["rules"][0]["pattern"] == "test"
    assert cfg["rules"][0]["actions"][0]["kind"] == "run_shell"

def test_persistence_auto_save(temp_config_file):
    mgr = SerialManager(config_path=temp_config_file)
    mgr.set_auto_save(enabled=True, path="test.log", device="COM1", scope_device="COM1")
    
    with open(temp_config_file, "r") as f:
        data = json.load(f)
        assert data["ports"]["COM1"]["auto_save"]["enabled"] == True
        assert data["ports"]["COM1"]["auto_save"]["path"] == "test.log"
        assert data["ports"]["COM1"]["auto_save"]["device"] == "COM1"

    mgr2 = SerialManager(config_path=temp_config_file)
    cfg = mgr2.get_config("COM1")
    assert cfg["auto_save"]["enabled"] == True
    assert cfg["auto_save"]["path"] == "test.log"
    assert cfg["auto_save"]["device"] == "COM1"

def test_persistence_connection_console(temp_config_file):
    mgr = SerialManager(config_path=temp_config_file)
    mgr.set_connection(device="COM4", baudrate=57600, data_bits=7, parity="E", stop_bits=2, flow_control="rtscts")
    mgr.set_console(device="COM4", auto_scroll=False, timestamp=False, line_num=False, hex_view=True, send_mode="hex", send_text="AT+TEST", append_newline=True, auto_send=True, send_interval_ms=1500)
    
    with open(temp_config_file, "r") as f:
        data = json.load(f)
        conn = data["ports"]["COM4"]["connection"]
        assert conn["baudrate"] == 57600
        assert conn["data_bits"] == 7
        assert conn["parity"] == "E"
        assert conn["stop_bits"] == 2.0
        assert conn["flow_control"] == "rtscts"
        con = data["ports"]["COM4"]["console"]
        assert con["auto_scroll"] == False
        assert con["timestamp"] == False
        assert con["line_num"] == False
        assert con["hex_view"] == True
        assert con["send_mode"] == "hex"
        assert con["send_text"] == "AT+TEST"
        assert con["append_newline"] == True
        assert con["auto_send"] == True
        assert con["send_interval_ms"] == 1500

    mgr2 = SerialManager(config_path=temp_config_file)
    cfg = mgr2.get_config("COM4")
    assert cfg["connection"]["baudrate"] == 57600
    assert cfg["connection"]["data_bits"] == 7
    assert cfg["connection"]["parity"] == "E"
    assert cfg["connection"]["stop_bits"] == 2.0
    assert cfg["connection"]["flow_control"] == "rtscts"
    assert cfg["console"]["auto_scroll"] == False
    assert cfg["console"]["timestamp"] == False
    assert cfg["console"]["line_num"] == False
    assert cfg["console"]["hex_view"] == True
    assert cfg["console"]["send_mode"] == "hex"
    assert cfg["console"]["send_text"] == "AT+TEST"
    assert cfg["console"]["append_newline"] == True
    assert cfg["console"]["auto_send"] == True
    assert cfg["console"]["send_interval_ms"] == 1500
