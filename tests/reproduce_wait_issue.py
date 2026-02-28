import asyncio
import time
from serial_mcp.serial_manager import SerialManager, LogLine

async def test_wait_behavior():
    manager = SerialManager()
    
    # Inject old logs
    print("Injecting old logs...")
    with manager._log_lock:
        manager._logs.append(LogLine(ts=time.time(), text="[OLD] This is a Match entry 1", device="test"))
        manager._logs.append(LogLine(ts=time.time(), text="[OLD] Filler line", device="test"))
        manager._logs.append(LogLine(ts=time.time(), text="[OLD] This is a Match entry 2", device="test"))
    
    # Test 1: wait_log_context with existing logs
    print("\nTest 1: Calling wait_log_context('Match') with existing logs...")
    result = await manager.wait_marker_context("Match", timeout=1)
    
    if result["marker_index"] != -1:
        print(f"Found match at index {result['marker_index']}")
        found_text = result["lines"][result["marker_index"] - result["lines"][0]["index"] if "index" in result["lines"][0] else 0]["text"]
        # Note: result['lines'] is a list of dicts. We need to find the one matching the marker.
        # But wait, the result structure is:
        # { "marker_index": idx, "lines": [ {text, ...}, ... ] }
        # The 'lines' are the context. We can just print the one that contains "Match".
        for l in result["lines"]:
            if "Match" in l["text"]:
                print(f"Returned line: {l['text']}")
    else:
        print("No match found (unexpected)")

    # Test 2: Inject new log and wait again
    print("\nTest 2: Injecting new log 'Match entry 3' and calling wait again...")
    with manager._log_lock:
        manager._logs.append(LogLine(ts=time.time(), text="[NEW] This is a Match entry 3", device="test"))
    manager._new_line_event.set()
    
    result = await manager.wait_marker_context("Match", timeout=1)
    if result["marker_index"] != -1:
        for l in result["lines"]:
            if "Match" in l["text"]:
                print(f"Returned line: {l['text']}")
    
if __name__ == "__main__":
    asyncio.run(test_wait_behavior())
