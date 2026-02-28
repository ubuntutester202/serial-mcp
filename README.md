<div align="center">

[![English](https://img.shields.io/badge/lang-English-blue.svg)](README.md) [![简体中文](https://img.shields.io/badge/lang-简体中文-inactive.svg)](README_zh.md)

</div>

# 🔌 Serial MCP Server

A powerful Serial Port MCP Server with Web UI, offering cross-platform support, log filtering, auto-responses, and synchronous log capture capabilities.

## 🎯 Background & Motivation

The original motivation for developing this tool came from a practical AI-assisted embedded development workflow:

1.  **AI Code Generation**: AI helps complete firmware code development.
2.  **Automated Flashing**: Automatically invokes command-line tools (like ST-Link/J-Link) to flash the firmware.
3.  **Verification Loop**: Starts the new firmware and captures its running logs via `serial-mcp`.
4.  **Feedback**: Returns these logs to the AI for analysis and verification, completing the closed-loop development process.

This tool serves as the critical bridge in this automated "Code -> Flash -> Verify" loop, enabling AI to interact with physical hardware through serial ports.

## ✨ Features
- **Cross-Platform**: Manage serial ports, baud rate, parity, data bits, stop bits.
- **Log Management**: HEX/ASCII support, configurable filtering (default `[DEBUG]`/`[IGNORE]`) with device-specific support.
- **Auto-Response**: Trigger serial sends or shell commands based on log patterns.
- **Sync Log Capture**: Wait for specific log contexts or ranges (useful for test automation).
- **Firmware Flashing**: Automate flashing and immediate log capture.
- **Web UI**: Modern interface for local interaction and monitoring. Supports **downloading logs locally** or **saving to server**.

## ⚙️ Configuration

Add the following to your `mcpServers` configuration:

### 📦 Option 1: Using uv (Recommended)
```json
{
  "mcpServers": {
    "serial-mcp": {
      "command": "uv",
      "args": ["run", "serial-mcp-stdio"],
      "cwd": "/path/to/serial-mcp",
      "env": { "PYTHONUNBUFFERED": "1" }
    }
  }
}
```

### Web UI Configuration

By default, the Web UI starts on port 8363. If this port is occupied, the server will fail to start. You can customize the port by adding arguments to `args`:

- `--web-port <PORT>`: Force a specific port (e.g., 8363).
- `--web-host <HOST>`: Bind to a specific interface (default: 127.0.0.1).

Example with custom port:
```json
{
  "mcpServers": {
    "serial-mcp": {
      "command": "uv",
      "args": ["run", "serial-mcp-stdio", "--web-port", "8363"],
      "cwd": "/path/to/serial-mcp",
      "env": { "PYTHONUNBUFFERED": "1" }
    }
  }
}
```

### 🐍 Option 2: System Python
```json
{
  "mcpServers": {
    "serial-mcp": {
      "command": "python",
      "args": ["-m", "serial_mcp.mcp_server"],
      "cwd": "/path/to/serial-mcp",
      "env": { "PYTHONUNBUFFERED": "1" }
    }
  }
}
```

## Installation & Development

```bash
pip install -e .
# Or using uv
uv venv && source .venv/bin/activate
uv pip install -e .
```

## Usage

### 🖥️ Unified Server (Recommended)
Starts a unified HTTP server providing both Web UI (at `/`) and MCP SSE service (at `/mcp/sse`). Supports remote LAN access.

```bash
# Local access
uv run serial-mcp-http

# Remote LAN access (ensure port is allowed by firewall)
# Web UI: http://<HOST_IP>:8363
# MCP SSE Endpoint: http://<HOST_IP>:8363/mcp/sse
uv run serial-mcp-http --host 0.0.0.0 --port 8363
```

**Important**: Due to serial port exclusivity, **NEVER** run multiple server instances simultaneously (e.g., running `serial-mcp-web` and `serial-mcp-http` at the same time). This causes `PermissionError` and inconsistent state.

### Web UI Only
Start the standalone Web UI (no MCP service):
```bash
serial-mcp-web
# With debug logging
serial-mcp-web --debug
```

### 📟 Standard MCP (Stdio)
Run as a standard MCP server via stdio (for IDE integration). 

By default, it also starts a **Background Web UI** at `http://127.0.0.1:8363` (or the next available port). You can customize this using `--web-port`.

```bash
serial-mcp-stdio
# Or with custom Web UI port
serial-mcp-stdio --web-port 8080
# Or
python -m serial_mcp.mcp_server
```
Configuration example:
`"args": ["run", "serial-mcp-stdio", "--debug", "--web-port", "8080"]`

### 🤖 HTTP API & Agent Skills Integration

When running (default port 8363), you can access the service via standard HTTP endpoints. This allows you to use tools like `curl` or custom scripts to build **Agent Skills** that orchestrate serial operations.

**Common Endpoints:**

- `GET /ports`: List available serial ports.
- `POST /open?device=COMx&baudrate=115200`: Open a connection.
- `POST /send?device=COMx&data=Hello`: Send data.
- `GET /logs?device=COMx`: Retrieve logs.

**Example: Agent Skill Workflow using curl**
You can define a "Health Check" skill by combining these calls:

```bash
# 1. Find ports
curl "http://127.0.0.1:8363/ports"

# 2. Connect
curl -X POST "http://127.0.0.1:8363/open?device=COM3&baudrate=115200"

# 3. Send Status Command
curl -X POST "http://127.0.0.1:8363/send?device=COM3&data=STATUS\n"

# 4. Check Logs
curl "http://127.0.0.1:8363/logs?device=COM3&limit=10"
```

### Simulation
See [simulation/README.md](simulation/README.md) for details on running the firmware simulator for testing.

## 🔧 MCP Tools

- `list_ports`: List available serial ports.
- `open_port(device, baudrate, ...)`: Open a connection.
- `close_port(device)`: Close connection.
- `set_mode(mode, device)`: Set data mode (ASCII/HEX).
- `send_data(data, device)`: Send data to port.
- `get_logs(device)`: Retrieve logs.
- `clear_logs(device)`: Clear logs.
- `save_logs(path, device)`: Save logs to the **server-side** filesystem.
- `set_auto_save(enabled, path, device)`: Configure automatic log saving.
- `set_filters(patterns, regex, device)`: Set log filters.
- `add_auto_rule(rule)`: Add auto-response rule.
- `delete_auto_rules(ids, device)`: Delete specific rules.
- `clear_auto_rules()`: Clear all rules.
- `flash_firmware(command, cwd, timeout)`: Flash firmware.
- `wait_log_context(marker, ...)`: Wait for log marker.
- `wait_log_between(start, end, ...)`: Capture logs between markers.
- `wait_log_multiple(queries, timeout)`: Wait for multiple conditions.
- `get_server_info()`: Get server version and Web UI URL.

For Chinese documentation, see [README_zh.md](README_zh.md).

## ❤️ Support

If you find this project helpful, you can buy me a coffee!

<div align="center">
  <figure style="display:inline-block;margin:0 10px;">
    <img src="serial_mcp/static/assets/alipay.jpg" width="200" alt="Alipay" />
    <figcaption>Alipay</figcaption>
  </figure>
  <figure style="display:inline-block;margin:0 10px;">
    <img src="serial_mcp/static/assets/wechat.jpg" width="200" alt="WeChat Pay" />
    <figcaption>WeChat Pay</figcaption>
  </figure>
</div>
