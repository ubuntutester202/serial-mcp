import asyncio
import threading
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from .serial_manager import SerialManager, AutoRule, AutoAction

mcp = FastMCP("serial-mcp")
manager = SerialManager()

@mcp.tool()
async def list_ports() -> str:
    """List available serial ports on the system.
    
    Returns:
        JSON string containing list of dictionaries with port information:
        - device: Port name (e.g. "COM1" on Windows, "/dev/ttyUSB0" on Linux)
        - description: Human readable description of the port
        - hwid: Hardware ID/USB VID:PID
        - is_open: Boolean, True if currently open by this MCP server instance
    """
    import json
    return json.dumps(manager.list_ports())

@mcp.tool()
async def open_port(device: str, baudrate: int = 115200, parity: str = "N", bytesize: int = 8, stopbits: float = 1, rtscts: bool = False, xonxoff: bool = False, dsrdtr: bool = False) -> str:
    """Open a serial port with specified settings.
    
    Args:
        device: Port name (e.g. "COM1", "/dev/ttyUSB0").
        baudrate: Communication speed. Common values: 9600, 115200, 921600.
        parity: Parity check. Values: 'N' (None), 'E' (Even), 'O' (Odd), 'M' (Mark), 'S' (Space).
        bytesize: Number of data bits. Values: 5, 6, 7, 8.
        stopbits: Number of stop bits. Values: 1, 1.5, 2.
        rtscts: Enable hardware flow control (RTS/CTS).
        xonxoff: Enable software flow control (XON/XOFF).
        dsrdtr: Enable hardware flow control (DSR/DTR).
        
    Returns:
        JSON string with operation status:
        - ok: True if successful (False maybe if port is already open in web UI, so it's not opened here, can continue next step)
        - device: The opened device name
        - config: The applied configuration
    """
    import json
    manager.open(device, baudrate=baudrate, parity=parity, bytesize=int(bytesize), stopbits=1 if stopbits == 1 else (2 if stopbits >= 2 else 1.5), rtscts=rtscts, xonxoff=xonxoff, dsrdtr=dsrdtr)
    return json.dumps({
        "ok": True, 
        "device": device, 
        "config": {
            "baudrate": baudrate,
            "parity": parity,
            "bytesize": bytesize,
            "stopbits": stopbits,
            "rtscts": rtscts,
            "xonxoff": xonxoff,
            "dsrdtr": dsrdtr
        }
    })

@mcp.tool()
async def save_logs(path: str, device: Optional[str] = None) -> str:
    """Save accumulated logs to a file on the SERVER (where this MCP server is running).
    
    Args:
        path: Absolute file path on the SERVER'S filesystem where logs should be saved (e.g. "D:/logs/session.log").
        device: Optional device name to filter logs. If None, saves logs from all devices.
        
    Returns:
        JSON string with status:
        - ok: True
        - path: The used file path
        - device: The applied filter
    """
    import json
    manager.save_logs_to_file(path, device)
    return json.dumps({"ok": True, "path": path, "device": device or "all"})

@mcp.tool()
async def set_auto_save(enabled: bool, path: str = "", device: Optional[str] = None) -> str:
    """Configure automatic real-time log saving to a file.
    
    Args:
        enabled: Set to True to enable auto-save, False to disable.
        path: Absolute file path for saving logs (required if enabled is True).
        device: Apply to specific device. If None, applies to global/default settings.
        
    Returns:
        JSON string with status:
        - ok: True
    """
    import json
    manager.set_auto_save(enabled, path, device)
    return json.dumps({"ok": True})

@mcp.tool()
async def delete_auto_rules(ids: List[str], device: Optional[str] = None) -> str:
    """Delete specific auto-response rules by their IDs.
    
    Args:
        ids: List of rule IDs (strings) to delete.
        device: Optional device scope. If provided, only searches rules for that device.
        
    Returns:
        JSON string with status:
        - ok: True
    """
    import json
    manager.delete_auto_rules(ids, device)
    return json.dumps({"ok": True})


@mcp.tool()
async def close_port(device: Optional[str] = None) -> str:
    """Close currently open serial port(s).
    
    Args:
        device: Specific port name to close (e.g. "COM1"). If None, closes ALL open ports.
        
    Returns:
        JSON string indicating success:
        - ok: True
        - target: The target device name or "all"
    """
    import json
    manager.close(device)
    return json.dumps({"ok": True, "target": device or "all"})

@mcp.tool()
async def set_mode(mode: str = "ascii", device: Optional[str] = None) -> str:
    """Set data sending/receiving mode (ASCII vs HEX).
    
    Args:
        mode: "ascii" (default) or "hex". 
              In HEX mode, input data is treated as hex string (e.g. "A1 B2").
        device: Specific port to set mode for. If None, applies to all ports.
        
    Returns:
        JSON string with status:
        - ok: True
        - mode: The set mode
    """
    import json
    manager.set_mode(mode, device)
    return json.dumps({"ok": True, "mode": mode, "target": device or "all"})

@mcp.tool()
async def set_filters(patterns: List[str], regex: bool = True, device: Optional[str] = None) -> str:
    """Set log filters to ignore unwanted log lines.
    
    Args:
        patterns: List of string patterns to ignore.
        regex: If True, patterns are treated as Python regular expressions. 
               If False, performs simple substring matching.
        device: Specific port to apply filters to. If None, sets global default filters.
        
    Returns:
        JSON string with status:
        - ok: True
        - patterns: The list of patterns set
    """
    import json
    manager.set_filters(patterns, regex=regex, device=device)
    return json.dumps({"ok": True, "patterns": patterns, "regex": regex, "target": device or "global"})

@mcp.tool()
async def send_data(data: str, device: Optional[str] = None) -> str:
    """Send data to a serial port.
    
    Args:
        data: The string data to send. 
              If mode is 'hex', this should be a hex string (e.g. "01 02 FF").
              If mode is 'ascii', this is sent as UTF-8 encoded bytes.
        device: Target serial port. If None, sends to ALL open ports.
        
    Returns:
        JSON string with status:
        - ok: True
        - sent_length: Number of bytes/characters sent
    """
    import json
    manager.send(data, device)
    return json.dumps({"ok": True, "sent_length": len(data), "target": device or "all"})

@mcp.tool()
async def get_logs(device: Optional[str] = None, include_hex: bool = False) -> str:
    """Get accumulated logs from the internal buffer.
    
    Args:
        device: Optional filter to return logs only for a specific device.
        include_hex: If True, include hex representation of logs. Default is False.
        
    Returns:
        JSON string with list of log objects:
        - timestamp: Formatted timestamp string
        - text: Log content (text representation)
        - hex: Log content (hex representation, optional)
        - device: Device name
        - packet: Boolean, True if this log entry is a combined packet
        - index: Global log index (useful for pagination/sync)
    """
    import json
    return json.dumps(manager.get_logs(device, include_hex=include_hex))

@mcp.tool()
async def clear_logs(device: Optional[str] = None) -> str:
    """Clear accumulated logs from memory.
    
    Args:
        device: Clear logs for specific device only. If None, clears ALL logs.
        
    Returns:
        JSON string with status:
        - ok: True
    """
    import json
    manager.clear_logs(device)
    return json.dumps({"ok": True, "target": device or "all"})

@mcp.tool()
async def add_auto_rule(rule: Dict[str, Any]) -> str:
    """Add an automatic response rule (trigger-action).
    
    Args:
        rule: A dictionary defining the rule:
            - pattern (str): Text or Regex to match in incoming logs.
            - regex (bool): True to use regex matching (default True).
            - once (bool): If True, rule fires only once (default True).
            - delay_ms (int): Delay in milliseconds before executing action.
            - device (str): Specific device to monitor.
            - actions (List[Dict]): List of actions to execute.
              Each action dict has:
              - kind (str): "send_serial" or "run_shell".
              - params (Dict): 
                - For "send_serial": {"data": "...", "device": "..."}
                - For "run_shell": {"command": "...", "cwd": "..."}
              
    Returns:
        JSON string with status:
        - ok: True
    """
    import json
    actions = [AutoAction(kind=a.get("kind"), params=a.get("params", {})) for a in rule.get("actions", [])]
    r = AutoRule(
        pattern=rule.get("pattern", ""), 
        regex=rule.get("regex", True), 
        actions=actions, 
        once=rule.get("once", True), 
        delay_ms=rule.get("delay_ms", 0),
        device=rule.get("device")
    )
    manager.add_auto_rule(r)
    return json.dumps({"ok": True})

@mcp.tool()
async def clear_auto_rules() -> str:
    """Clear all active auto-response rules.
    
    Returns:
        JSON string with status:
        - ok: True
    """
    import json
    manager.clear_auto_rules()
    return json.dumps({"ok": True})

@mcp.tool()
async def flash_firmware(command: str, cwd: Optional[str] = None, timeout: Optional[float] = None) -> str:
    """Execute a firmware flashing command (shell command) and return the output.
    
    Args:
        command: The shell command to execute (e.g. "esptool.py write_flash ...").
        cwd: Working directory for the command.
        timeout: Maximum execution time in seconds.
        
    Returns:
        JSON string with execution result:
        - code: Exit code
        - stdout: Standard output
        - stderr: Standard error
    """
    import json
    res = await manager.flash(command, cwd=cwd, env=None, timeout=timeout)
    return json.dumps(res)

@mcp.tool()
async def wait_log_context(marker: str, before: int = 20, after: int = 40, timeout: Optional[float] = None, device: Optional[str] = None) -> str:
    """Wait for a specific log marker to appear and return surrounding lines.
    
    This tool blocks until the marker is found or timeout occurs.
    
    Args:
        marker: String or pattern to search for in logs.
        before: Number of lines to include before the marker.
        after: Number of lines to include after the marker.
        timeout: Max seconds to wait.
        device: Optional device name to filter logs. If provided, ONLY logs from this device are searched and returned.
        
    Returns:
        JSON string containing:
        - marker_index: Index of the found marker (-1 if not found)
        - lines: List of context log lines. Configured filters are applied to these lines.
    """
    import json
    res = await manager.wait_marker_context(marker, before=before, after=after, timeout=timeout, device=device)
    return json.dumps(res)

@mcp.tool()
async def wait_log_between(start_marker: str, end_marker: str, timeout: Optional[float] = None, device: Optional[str] = None) -> str:
    """Wait for a start marker and then an end marker, returning all lines between them.
    
    This tool blocks until the sequence is complete or timeout occurs.
    
    Args:
        start_marker: Start marker string.
        end_marker: End marker string.
        timeout: Max seconds to wait.
        device: Optional device name to filter logs. If provided, ONLY logs from this device are searched and returned.
        
    Returns:
        JSON string containing:
        - start_index: Index of start marker (-1 if not found)
        - end_index: Index of end marker (-1 if not found)
        - lines: List of log lines between markers (inclusive). Configured filters are applied to these lines.
    """
    import json
    res = await manager.wait_between(start_marker, end_marker, timeout=timeout, device=device)
    return json.dumps(res)

@mcp.tool()
async def wait_log_multiple(queries: List[Dict[str, Any]], timeout: Optional[float] = None) -> str:
    """Wait for multiple log conditions to be met (in parallel).
    
    Args:
        queries: List of query dicts. Each dict must have 'kind' ('context' or 'between')
                 and matching parameters (see wait_log_context/wait_log_between).
        timeout: Max seconds to wait for all queries to complete.
                 
    Returns:
        JSON string with list of results corresponding to each query. Strict device filtering and configured filters apply.
    """
    import json
    res = await manager.wait_multiple(queries, timeout=timeout)
    return json.dumps(res)

@mcp.tool()
async def get_server_info() -> str:
    """Get information about the running server, including Web UI URL.
    
    Returns:
        JSON string containing:
        - web_ui_url: The URL of the Web UI (if running)
        - version: Server version
    """
    import json
    return json.dumps({
        "web_ui_url": manager.web_ui_url,
        "version": "0.1.0"
    })

def run_web_server(mgr: SerialManager, host: str = "127.0.0.1", port: Optional[int] = None) -> None:
    """Run FastAPI server in a separate thread."""
    import uvicorn
    from . import webapp
    import socket
    
    # Inject the shared manager instance
    webapp.set_manager(mgr)
    
    # Use default port 8363 if not specified
    if port is None:
        port = 8363
    
    try:
        # Configure uvicorn to be quiet on stdout/stderr to avoid interfering with MCP stdio
        config = uvicorn.Config(
            webapp.app, 
            host=host, 
            port=port, 
            log_level="critical", # Only critical errors
            access_log=False      # Disable access log
        )
        server = uvicorn.Server(config)
        
        url = f"http://{host}:{port}"
        if host == "0.0.0.0":
             url = f"http://127.0.0.1:{port}"
        
        mgr.web_ui_url = url
        import sys
        print(f"[INFO] Serial MCP Web UI started at {url}", file=sys.stderr)
        
        server.run()
    except Exception as e:
        import sys
        print(f"[ERROR] Failed to start Web UI: {e}", file=sys.stderr)

def run_stdio() -> None:
    import argparse
    import logging
    import sys
    
    # Parse known args to avoid conflict with potential internal MCP args (though usually none for stdio)
    parser = argparse.ArgumentParser(description="Serial MCP Server")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--web-host", type=str, default="127.0.0.1", help="Background web server host (default: 127.0.0.1)")
    parser.add_argument("--web-port", type=int, default=None, help="Background web server port (default: 8363)")
    
    # We use parse_known_args because we don't want to fail if there are other args 
    # (though typically there aren't for stdio transport)
    args, unknown = parser.parse_known_args()
    
    # Configure logging
    # Note: For MCP stdio, we MUST NOT log to stdout. 
    # Logging.basicConfig defaults to stderr, which is safe.
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Register signal handlers for graceful shutdown
    import signal
    def handle_sigterm(signum, frame):
        import sys
        print("[INFO] Received signal {}, exiting...".format(signum), file=sys.stderr)
        manager.close()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, handle_sigterm)
    # SIGINT is usually handled by FastMCP or leads to KeyboardInterrupt, 
    # which will be caught by the try/finally block below or just exit.
    
    # Start Web UI in a daemon thread
    t = threading.Thread(target=run_web_server, args=(manager, args.web_host, args.web_port), daemon=True)
    t.start()
    
    try:
        mcp.run()
    finally:
        import sys
        print("[INFO] Shutting down Serial MCP Server...", file=sys.stderr)
        manager.close()

def run_http() -> None:
    import argparse
    import uvicorn
    from . import webapp
    
    parser = argparse.ArgumentParser(description="Serial MCP Server (HTTP/SSE + Web UI)")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8363, help="Port to bind to (default: 8363)")
    
    args = parser.parse_args()
    
    # Inject the shared manager instance into the webapp
    webapp.set_manager(manager)
    
    # Register cleanup on shutdown
    @webapp.app.on_event("shutdown")
    def shutdown_event():
        import sys
        print("[INFO] Shutting down Serial MCP Server (HTTP)...", file=sys.stderr)
        manager.close()

    # Mount MCP SSE app into the Web App
    # We mount it at /mcp so the SSE endpoint will be /mcp/sse
    # This allows running both Web UI and MCP Server in the same process (sharing SerialManager)
    webapp.app.mount("/mcp", mcp.sse_app)
    
    print(f"Starting Serial MCP Server on http://{args.host}:{args.port}")
    print(f"  - Web UI: http://{args.host}:{args.port}/")
    print(f"  - MCP SSE: http://{args.host}:{args.port}/mcp/sse")
    
    uvicorn.run(webapp.app, host=args.host, port=args.port)

if __name__ == "__main__":
    run_stdio()
