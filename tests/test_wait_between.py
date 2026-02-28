import asyncio
import time
from serial_mcp.serial_manager import SerialManager, LogLine

def test_wait_between():
    async def run_async_test():
        manager = SerialManager()
        
        print("--- Test 1: S1...E1 (Complete pair) ---")
        with manager._log_lock:
            manager._logs = [] # Reset
            manager._logs.append(LogLine(ts=time.time(), text="Start 1", device="test"))
            manager._logs.append(LogLine(ts=time.time(), text="Mid 1", device="test"))
            manager._logs.append(LogLine(ts=time.time(), text="End 1", device="test"))
        
        res = await manager.wait_between("Start", "End", timeout=1)
        print(f"Result: Start Index {res['start_index']}, End Index {res['end_index']}")
        assert res['start_index'] == 0
        assert res['end_index'] == 2
        
        print("\n--- Test 2: S1...E1...S2 (Incomplete second pair) ---")
        with manager._log_lock:
            manager._logs.append(LogLine(ts=time.time(), text="Start 2", device="test"))
            manager._logs.append(LogLine(ts=time.time(), text="Mid 2", device="test"))
        
        # This should timeout if looking for *latest* Start (S2) and waiting for E2.
        try:
            res = await asyncio.wait_for(manager.wait_between("Start", "End", timeout=2), timeout=3)
            print(f"Result: Start Index {res['start_index']}, End Index {res['end_index']}")
            assert res['start_index'] == -1
            print("Correctly timed out (waiting for End 2)")
        except asyncio.TimeoutError:
             print("Timed out as expected (waiting for End 2)")
    
        print("\n--- Test 3: Injecting End 2 ---")
        # We need to run wait_between in background while we inject
        async def inject_delayed():
            await asyncio.sleep(1)
            print("Injecting End 2...")
            with manager._log_lock:
                manager._logs.append(LogLine(ts=time.time(), text="End 2", device="test"))
            manager._new_line_event.set()
    
        t = asyncio.create_task(inject_delayed())
        res = await manager.wait_between("Start", "End", timeout=3)
        print(f"Result: Start Index {res['start_index']}, End Index {res['end_index']}")
        # Expect Start 2 (index 3) and End 2 (index 5)
        # Indices: 0:S1, 1:M1, 2:E1, 3:S2, 4:M2, 5:E2
        assert res['start_index'] == 3
        assert res['end_index'] == 5

    asyncio.run(run_async_test())

if __name__ == "__main__":
    test_wait_between()
