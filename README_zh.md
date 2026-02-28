<div align="center">

[![English](https://img.shields.io/badge/lang-English-inactive.svg)](README.md) [![简体中文](https://img.shields.io/badge/lang-简体中文-blue.svg)](README_zh.md)

</div>

# 🔌 串口 MCP 服务器

一个功能强大的带有 Web UI 的串口 MCP 服务器，提供跨平台支持、日志过滤、自动响应和同步日志捕获功能。

## 🎯 背景与初衷

开发此工具的最初动力源于一个实际的 AI 辅助嵌入式开发工作流：

1.  **AI 代码生成**: AI 协助完成固件代码的开发。
2.  **自动烧录**: 自动调用命令行工具（如 ST-Link/J-Link）将固件烧录到设备。
3.  **验证闭环**: 启动新固件，并通过 `serial-mcp` 捕获其运行日志。
4.  **反馈分析**: 将运行日志返回给 AI 进行分析和验证，完成开发闭环。

本工具旨在作为这一自动化“代码 -> 烧录 -> 验证”循环中的关键桥梁，赋予 AI 通过串口与物理硬件交互的能力。

## ✨ 功能特性

- **跨平台**: 管理串口、波特率、校验位、数据位、停止位。
- **日志管理**: 支持 HEX/ASCII，可配置过滤（默认 `[DEBUG]`/`[IGNORE]`），支持特定设备。
- **自动响应**: 基于日志模式触发串口发送或 Shell 命令。
- **同步日志捕获**: 等待特定日志上下文或范围（适用于测试自动化）。
- **固件烧录**: 自动化烧录并立即捕获日志。
- **Web UI**: 用于本地交互和监控的现代界面。支持**本地下载日志**或**保存到服务器**。

## ⚙️ 配置

将以下内容添加到您的 `mcpServers` 配置中：

### 📦 选项 1：使用 uv（推荐）

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

### Web UI 配置

默认情况下，Web UI 在端口 8363 上启动。如果此端口被占用，服务器将无法启动。您可以通过向 `args` 添加参数来自定义端口：

- `--web-port <PORT>`: 强制使用特定端口（例如 8363）。
- `--web-host <HOST>`: 绑定到特定接口（默认：127.0.0.1）。

自定义端口示例：

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

### 选项 2：系统 Python

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

## 安装与开发

```bash
pip install -e .
# 或者使用 uv
uv venv && source .venv/bin/activate
uv pip install -e .
```

## 📖 用法

### 🖥️ 统一服务器（推荐）

启动统一的 HTTP 服务器，同时提供 Web UI（在 `/`）和 MCP SSE 服务（在 `/mcp/sse`）。支持远程局域网访问。

```bash
# 本地访问
uv run serial-mcp-http

# 远程局域网访问（确保防火墙允许该端口）
# Web UI: http://<HOST_IP>:8363
# MCP SSE 端点: http://<HOST_IP>:8363/mcp/sse
uv run serial-mcp-http --host 0.0.0.0 --port 8363
```

**重要提示**：由于串口独占性，**切勿**同时运行多个服务器实例（例如同时运行 `serial-mcp-web` 和 `serial-mcp-http`）。这会导致 `PermissionError` 和状态不一致。

### 🎨 仅 Web UI

启动独立 Web UI（无 MCP 服务）：

```bash
serial-mcp-web
# 开启调试日志
serial-mcp-web --debug
```

### 📟 标准 MCP (Stdio)

通过 stdio 作为标准 MCP 服务器运行（用于 IDE 集成）。

默认情况下，它还会在 `http://127.0.0.1:8363`（或下一个可用端口）启动**后台 Web UI**。您可以使用 `--web-port` 自定义此端口。

```bash
serial-mcp-stdio
# 或者指定自定义 Web UI 端口
serial-mcp-stdio --web-port 8080
# 或者
python -m serial_mcp.mcp_server
```

配置示例：
`"args": ["run", "serial-mcp-stdio", "--debug", "--web-port", "8080"]`

### HTTP API 与 Agent Skills 集成

运行时（默认端口 8363），您可以通过标准 HTTP 端点访问服务。这允许您使用 `curl` 等工具或自定义脚本构建编排串口操作的 **Agent Skills**。

**常用端点：**

- `GET /ports`: 列出可用串口。
- `POST /open?device=COMx&baudrate=115200`: 打开连接。
- `POST /send?device=COMx&data=Hello`: 发送数据。
- `GET /logs?device=COMx`: 获取日志。

**示例：使用 curl 的 Agent Skill 工作流**

您可以通过组合这些调用来定义“健康检查”技能：

```bash
# 1. 查找端口
curl "http://127.0.0.1:8363/ports"

# 2. 连接
curl -X POST "http://127.0.0.1:8363/open?device=COM3&baudrate=115200"

# 3. 发送状态命令
curl -X POST "http://127.0.0.1:8363/send?device=COM3&data=STATUS\n"

# 4. 检查日志
curl "http://127.0.0.1:8363/logs?device=COM3&limit=10"
```

### 🧪 模拟

有关运行固件模拟器进行测试的详细信息，请参阅 [simulation/README.md](simulation/README.md)。

## 🔧 MCP 工具

- `list_ports`: 列出可用串口。
- `open_port(device, baudrate, ...)`: 打开连接。
- `close_port(device)`: 关闭连接。
- `set_mode(mode, device)`: 设置数据模式 (ASCII/HEX)。
- `send_data(data, device)`: 向端口发送数据。
- `get_logs(device)`: 获取日志。
- `clear_logs(device)`: 清除日志。
- `save_logs(path, device)`: 将日志保存到**服务器端**文件系统。
- `set_auto_save(enabled, path, device)`: 配置自动日志保存。
- `set_filters(patterns, regex, device)`: 设置日志过滤器。
- `add_auto_rule(rule)`: 添加自动响应规则。
- `delete_auto_rules(ids, device)`: 删除特定规则。
- `clear_auto_rules()`: 清除所有规则。
- `flash_firmware(command, cwd, timeout)`: 烧录固件。
- `wait_log_context(marker, ...)`: 等待日志标记。
- `wait_log_between(start, end, ...)`: 捕获标记之间的日志。
- `wait_log_multiple(queries, timeout)`: 等待多个条件。
- `get_server_info()`: 获取服务器版本和 Web UI URL。

## ❤️ 支持

如果这个项目对您有帮助，欢迎请我喝杯咖啡！

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
