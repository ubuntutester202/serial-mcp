import pytest
import asyncio
from serial_mcp.serial_manager import SerialManager

@pytest.mark.anyio
async def test_send_ascii_and_hex():
    mgr = SerialManager()
    
    # Mocking serial port since we can't open real ports easily without simulator running
    # But SerialManager checks if port is open before writing.
    # So we need a mock serial object.
    
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
            
    # Inject mock
    mgr._ports["COM_TEST"] = type('obj', (object,), {
        "device": "COM_TEST",
        "port": MockSerial(),
        "mode": "ascii",
        "reader_thread": None
    })
    
    # Test ASCII Send
    mgr.send("hello", device="COM_TEST")
    assert mgr._ports["COM_TEST"].port.written_data == b"hello"
    
    # Clear buffer
    mgr._ports["COM_TEST"].port.written_data = b""
    
    # Test HEX Send
    mgr.set_mode("hex", device="COM_TEST")
    # "41 42 43" -> "ABC"
    mgr.send("41 42 43", device="COM_TEST") 
    assert mgr._ports["COM_TEST"].port.written_data == b"ABC"
    
    # Test Mixed Case HEX
    mgr._ports["COM_TEST"].port.written_data = b""
    mgr.send("44 45 46", device="COM_TEST")
    assert mgr._ports["COM_TEST"].port.written_data == b"DEF"

    # Test HEX without spaces
    mgr._ports["COM_TEST"].port.written_data = b""
    mgr.send("414243", device="COM_TEST")
    assert mgr._ports["COM_TEST"].port.written_data == b"ABC"

    # Test Odd Length HEX (pads last nibble with 0)
    mgr._ports["COM_TEST"].port.written_data = b""
    mgr.send("41424", device="COM_TEST")
    assert mgr._ports["COM_TEST"].port.written_data == b"AB@"
    
    # Test Invalid HEX (Should probably raise or be handled)
    # Current impl: bytes.fromhex(data.replace(" ", ""))
    with pytest.raises(RuntimeError):
        mgr.send("ZZ", device="COM_TEST")

    mgr.close()
