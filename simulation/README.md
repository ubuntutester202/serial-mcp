# Firmware Simulator for Serial MCP Testing

This simulator mimics a device firmware to test the Serial MCP Server capabilities.

## Setup
- **Virtual Serial Ports**: Ensure you have the following pairs created:
  - **Windows**: Use [Virtual Serial Port Driver](https://www.eltima.com/products/vspdxp/) (recommended) or [com0com](http://com0com.sourceforge.net/).
  - **Linux**: Use `socat` (e.g., `socat -d -d pty,raw,echo=0 pty,raw,echo=0`).

  **Required Pairs:**
  - Pair A: `COM2` <-> `COM3`
  - Pair B: `COM4` <-> `COM5`

## Connections
- **Simulator**: Connects to `COM2` (Commands) and `COM4` (Logs).
- **MCP Server**: Should connect to `COM3` (Commands) and `COM5` (Logs).

## Usage
1. Start the simulator:
   ```bash
   # From project root
   python simulation/firmware_simulator.py
   
   # Or from simulation directory
   cd simulation
   python firmware_simulator.py
   ```

2. Start your MCP Server (configured to use `COM3` and `COM5`).

## Features
The simulator accepts commands on `COM2` and outputs logs on `COM4`.

### Supported Commands (send to COM2)
- Supports `\n` (Line Feed) or `\r` (Carriage Return) as line terminators.
- `help`: List available commands.
- `reboot`: Simulates a system reboot with boot logs.
- `task_flow`: Triggers the specific log sequence requested:
  - Starts with `main.cpp:33`
  - Ends with `moduleA.cpp:80`
  - Includes intermediate logs and some `[IGNORE]` / `[DEBUG]` tags for filter testing.
- `error_test`: Emits error logs.
- `spam`: Emits a burst of logs.

### Log Format (on COM4)
Logs are formatted as:
`[YYYY-MM-DD HH:MM:SS.mmm] [LEVEL] File:Line - Message`

## Testing Scenarios

1. **Auto-Send / Interaction**:
   - Configure MCP to send `task_flow` when it detects `System heartbeat`.
   - Configure MCP to send `reboot` when it detects `Critical failure`.

2. **Log Capture (Sync)**:
   - Use MCP API to wait for `main.cpp:33` -> `moduleA.cpp:80`.
   - Send `task_flow` command to Simulator.
   - Verify MCP captures the sequence.

3. **Filtering**:
   - The `task_flow` command emits logs with `[IGNORE]` and `[DEBUG]`.
   - Configure MCP to filter these out and verify they are missing from the captured output.
