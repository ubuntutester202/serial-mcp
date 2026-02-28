import asyncio
import pytest
from serial_mcp.serial_manager import SerialManager

pytestmark = pytest.mark.anyio

async def test_wait_context():
    mgr = SerialManager()
    mgr.inject_log("booting")
    mgr.inject_log("init")
    mgr.inject_log("main.cpp:33 start")
    mgr.inject_log("work1")
    mgr.inject_log("work2")
    r = await mgr.wait_marker_context("main.cpp:33", before=2, after=2, timeout=1)
    assert r["marker_index"] >= 0
    assert len(r["lines"]) >= 3

async def test_wait_between():
    mgr = SerialManager()
    mgr.inject_log("boot")
    mgr.inject_log("main.cpp:33 start")
    mgr.inject_log("run a")
    mgr.inject_log("moduleA.cpp:80 done")
    r = await mgr.wait_between("main.cpp:33", "moduleA.cpp:80", timeout=1)
    assert r["start_index"] >= 0
    assert r["end_index"] >= 0
    assert len(r["lines"]) >= 2

async def test_wait_multiple():
    mgr = SerialManager()
    async def produce():
        await asyncio.sleep(0.05)
        mgr.inject_log("x")
        mgr.inject_log("main.cpp:33 here")
        mgr.inject_log("y")
        mgr.inject_log("moduleA.cpp:80 end")
    t = asyncio.create_task(produce())
    qs = [
        {"kind": "context", "marker": "main.cpp:33", "before": 1, "after": 1},
        {"kind": "between", "start": "main.cpp:33", "end": "moduleA.cpp:80"},
    ]
    r = await mgr.wait_multiple(qs, timeout=2)
    await t
    assert len(r) == 2

async def test_wait_multiple_between():
    mgr = SerialManager()
    async def produce():
        await asyncio.sleep(0.05)
        mgr.inject_log("main.cpp:12 start")
        mgr.inject_log("noise a")
        mgr.inject_log("function1.cpp:256 end")
        mgr.inject_log("noise b")
        mgr.inject_log("function2.cpp:50 begin")
        mgr.inject_log("noise c")
        mgr.inject_log("module7.cpp:30 done")
    t = asyncio.create_task(produce())
    qs = [
        {"kind": "between", "start": "main.cpp:12", "end": "function1.cpp:256"},
        {"kind": "between", "start": "function2.cpp:50", "end": "module7.cpp:30"},
    ]
    r = await mgr.wait_multiple(qs, timeout=2)
    await t
    assert len(r) == 2
    texts0 = [l["text"] for l in r[0]["result"]["lines"]]
    texts1 = [l["text"] for l in r[1]["result"]["lines"]]
    assert any("main.cpp:12" in t for t in texts0)
    assert any("function1.cpp:256" in t for t in texts0)
    assert any("function2.cpp:50" in t for t in texts1)
    assert any("module7.cpp:30" in t for t in texts1)
