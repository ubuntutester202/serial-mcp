import asyncio
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import sys
from pathlib import Path
from .serial_manager import SerialManager

app = FastAPI()

# Dummy route to silence /@vite/client 404 errors in logs when running in some environments
@app.get("/@vite/client")
async def vite_client():
    return Response(content="", media_type="application/javascript")

def get_base_dir():
    """Get the base directory for static files and templates, compatible with PyInstaller."""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # Running in a PyInstaller bundle
        # The resources are located inside the _MEIPASS directory
        # If we added data as "serial_mcp/templates;serial_mcp/templates", 
        # then they are at sys._MEIPASS/serial_mcp/templates
        # Since this file (webapp.py) is inside serial_mcp package, 
        # we need to be careful about how it's structured in the bundle.
        # Usually, PyInstaller extracts everything to sys._MEIPASS.
        return Path(sys._MEIPASS) / "serial_mcp"
    else:
        # Running in normal Python environment
        return Path(__file__).parent

BASE_DIR = get_base_dir()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
manager: SerialManager = SerialManager()

def set_manager(new_manager: SerialManager):
    global manager
    manager = new_manager


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/config")
async def get_config(device: str = None):
    if device == "":
        device = None
    return manager.get_config(device)

@app.post("/config/connection")
async def set_connection(options: Dict[str, Any]):
    device = options.get("device")
    if device == "":
        device = None
    if not device:
        return {"ok": False}
    manager.set_connection(
        device=device,
        baudrate=options.get("baudrate"),
        data_bits=options.get("data_bits"),
        parity=options.get("parity"),
        stop_bits=options.get("stop_bits"),
        flow_control=options.get("flow_control")
    )
    return {"ok": True}

@app.post("/config/console")
async def set_console(options: Dict[str, Any]):
    device = options.get("device")
    if device == "":
        device = None
    if not device:
        return {"ok": False}
    manager.set_console(
        device=device,
        auto_scroll=options.get("auto_scroll"),
        timestamp=options.get("timestamp"),
        line_num=options.get("line_num"),
        hex_view=options.get("hex_view"),
        send_mode=options.get("send_mode"),
        send_text=options.get("send_text"),
        append_newline=options.get("append_newline"),
        auto_send=options.get("auto_send"),
        send_interval_ms=options.get("send_interval_ms")
    )
    return {"ok": True}

@app.get("/ports")
async def ports():
    return manager.list_ports()

@app.post("/open")
async def open_port(device: str, baudrate: int = 115200, parity: str = "N", bytesize: int = 8, stopbits: float = 1, flow: str = "none"):
    rtscts = flow == "rtscts"
    xonxoff = flow == "xonxoff"
    dsrdtr = flow == "dsrdtr"
    manager.open(
        device,
        baudrate=baudrate,
        parity=parity,
        bytesize=int(bytesize),
        stopbits=1 if stopbits == 1 else (2 if stopbits >= 2 else 1.5),
        rtscts=rtscts,
        xonxoff=xonxoff,
        dsrdtr=dsrdtr
    )
    return {"ok": True}

@app.post("/close")
async def close_port(device: str = None):
    manager.close(device)
    return {"ok": True}

@app.post("/logs/clear")
async def clear_logs(device: str = None):
    if device == "":
        device = None
    manager.clear_logs(device)
    return {"ok": True}

@app.post("/send")
async def send(data: str, mode: str = "ascii", device: str = None):
    # Ensure device is None if empty string to match SerialManager logic
    if not device: 
        device = None
    
    # If mode is provided, set it first
    if mode:
        manager.set_mode(mode, device)
        
    try:
        manager.send(data, device)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/filters")
async def filters(patterns: List[str], regex: bool = True, device: str = None):
    if device == "":
        device = None
    manager.set_filters(patterns, regex=regex, device=device)
    return {"ok": True}

@app.websocket("/ws/logs")
async def ws_logs(ws: WebSocket, device: str = None, start_index: int = -1):
    await ws.accept()
    
    # If start_index is not provided (-1), default to the last 2000 logs
    # to prevent streaming the entire history by default.
    if start_index == -1:
        stats = manager.get_stats()
        total = stats.get("total_logs", 0)
        start_index = max(0, total - 2000)
        
    last_index = start_index
    try:
        while True:
            await asyncio.sleep(0.1) # Slightly faster poll
            # Get only new logs
            new_logs = manager.get_logs(device, start_index=last_index, include_hex=True)
            if new_logs:
                for item in new_logs:
                    await ws.send_json(item)
                last_index += len(new_logs)
    except WebSocketDisconnect:
        # Client disconnected, stop the loop
        pass
    except Exception:
        # For other errors, try to close if possible, but ignore if already closed
        try:
            await ws.close()
        except Exception:
            pass

@app.get("/logs")
async def get_logs(start_index: int = 0, limit: int = 10000, device: str = None):
    # Enforce a hard limit to prevent memory/network issues
    actual_limit = min(limit, 10000)
    items = manager.get_logs(device, start_index=start_index, limit=actual_limit, include_hex=True)
    
    # Calculate next_index correctly based on what we returned
    # If we returned fewer items than limit, next request should start after these items.
    # Note: manager.get_logs returns a list. We assume contiguous items from start_index.
    # If we filtered by device, the indices might not be contiguous in the main list, 
    # but the client usually tracks 'logCursor' as a global index.
    # Actually, manager.get_logs implementation needs checking. 
    # If it filters by device, it returns a subset. The 'start_index' passed to it 
    # is usually the global index.
    
    # To support correct pagination, the manager should probably return the next global index
    # or we infer it. For now, let's assume client increments by len(items) 
    # OR we return the max index seen + 1.
    # But wait, if we filter, we might skip many items.
    # Let's check manager.get_logs implementation first.
    # Based on previous read: it slices self._logs[local_start:].
    # So if we limit, we should limit the slice length.
    
    return {
        "items": items, 
        # We need to tell the client where to ask from next.
        # If we returned N items starting from start_index, next is start_index + N?
        # No, because of device filtering, we might have scanned M items to find N items.
        # This is complex with filtering.
        # Simpler approach: return the global index of the last item + 1.
        "next_index": items[-1]["index"] + 1 if items else start_index
    }

@app.get("/rules")
async def get_rules(device: str = None):
    if device == "":
        device = None
    return manager.get_auto_rules(device)

@app.post("/rules")
async def add_rule(rule: Dict[str, Any], device: str = None):
    from .serial_manager import AutoRule, AutoAction
    if device == "":
        device = None
    rule_device = rule.get("device") or device
    actions = [AutoAction(kind=a.get("kind"), params=a.get("params", {})) for a in rule.get("actions", [])]
    r = AutoRule(
        pattern=rule.get("pattern", ""), 
        regex=rule.get("regex", True), 
        actions=actions, 
        once=rule.get("once", True), 
        delay_ms=rule.get("delay_ms", 0),
        interval_ms=rule.get("interval_ms", 0),
        device=rule_device
    )
    manager.add_auto_rule(r, device=rule_device)
    return {"ok": True}

@app.post("/rules/delete")
async def delete_rules(ids: List[str], device: str = None):
    if device == "":
        device = None
    manager.delete_auto_rules(ids, device)
    return {"ok": True}

@app.delete("/rules")
async def clear_rules(device: str = None):
    if device == "":
        device = None
    manager.clear_auto_rules(device)
    return {"ok": True}

@app.post("/logs/save")
async def save_logs(path: str, device: str = None):
    try:
        if device == "": device = None
        manager.save_logs_to_file(path, device)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.get("/logs/download")
async def download_logs(device: str = None):
    if device == "":
        device = None
    content = manager.export_logs_text(device)
    filename = f"serial_logs_{device if device else 'all'}.txt"
    return Response(content=content, media_type="text/plain", headers={
        "Content-Disposition": f"attachment; filename={filename}"
    })

@app.get("/logs/stats")
async def log_stats():
    return manager.get_stats()

@app.post("/logs/options")
async def log_options(options: Dict[str, Any]):
    manager.set_log_options(
        packet_enabled=options.get("packet_enabled"),
        packet_timeout_ms=options.get("packet_timeout_ms"),
        log_max_lines=options.get("log_max_lines"),
        device=options.get("device")
    )
    return {"ok": True}

@app.post("/logs/auto-save")
async def auto_save(options: Dict[str, Any]):
    scope_device = options.get("device")
    if scope_device == "":
        scope_device = None
    manager.set_auto_save(
        enabled=options.get("enabled", False),
        path=options.get("path", ""),
        device=options.get("device"),
        scope_device=scope_device
    )
    return {"ok": True}

def run():
    import argparse
    import logging
    
    parser = argparse.ArgumentParser(description="Serial MCP Web Server")
    parser.add_argument("--port", type=int, default=8363, help="Web server port")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Web server host (default: 127.0.0.1)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    # We need to parse args but uvicorn might interfere if we just run this script directly.
    # However, this function is the entry point for the console script.
    args = parser.parse_args()
    
    # Configure logging
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    run()
