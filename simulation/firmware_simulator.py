import serial
import time
import threading
import random
import datetime
import sys

class FirmwareSimulator:
    def __init__(self):
        self.running = True
        # Configuration based on user request
        # Simulator connects to COM2 (Command/Interactive) and COM4 (Logs)
        self.cmd_port_name = 'COM2' 
        self.log_port_name = 'COM4'
        self.baudrate = 115200
        
        self.cmd_serial = None
        self.log_serial = None
        self.flow_lock = threading.Lock()
        self.flow_thread = None
        self.flow_stop = threading.Event()
        self.flow_continue = threading.Event()
        self.flow_mode = "idle"
        self.flow_index = -1
        self.flow_state = "idle"
        self.flow_nodes = self._build_flow()
        
    def start(self):
        print(f"Initializing Firmware Simulator...")
        print(f"Connecting to {self.cmd_port_name} (Interactive/Shell) and {self.log_port_name} (Logs)...")
        
        try:
            self.cmd_serial = serial.Serial(self.cmd_port_name, self.baudrate, timeout=0.1)
            self.log_serial = serial.Serial(self.log_port_name, self.baudrate, timeout=0.1)
            print("Connected successfully.")
        except serial.SerialException as e:
            print(f"Error opening serial ports: {e}")
            print("Please ensure VSPD pairs (COM2<>COM3, COM4<>COM5) are created and not occupied.")
            return

        # Start threads
        t_cmd = threading.Thread(target=self.command_loop, daemon=True)
        t_log = threading.Thread(target=self.background_log_loop, daemon=True)
        
        t_cmd.start()
        t_log.start()
        
        print("Simulator is running. Press Ctrl+C to exit.")
        print("Simulated Scenarios:")
        print("1. Send 'help' to COM2 to see commands.")
        print("2. Send 'task_flow' to trigger the main.cpp:33 -> moduleA.cpp:80 sequence.")
        
        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopping simulator...")
            self.running = False
            
        if self.cmd_serial: self.cmd_serial.close()
        if self.log_serial: self.log_serial.close()

    def send_log(self, msg, level="INFO", file_info=None):
        """Send a formatted log message to the log port (COM4)."""
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        if file_info:
            content = f"[{ts}] [{level}] {file_info} - {msg}\n"
        else:
            content = f"[{ts}] [{level}] {msg}\n"
        
        if self.log_serial and self.log_serial.is_open:
            try:
                self.log_serial.write(content.encode('utf-8'))
            except Exception as e:
                print(f"Error writing to log port: {e}")

    def send_cmd_response(self, msg):
        """Send a response back to the command port (COM2)."""
        if self.cmd_serial and self.cmd_serial.is_open:
            try:
                self.cmd_serial.write((msg + "\r\n").encode('utf-8'))
            except Exception as e:
                print(f"Error writing to cmd port: {e}")

    def command_loop(self):
        buffer = ""
        while self.running:
            if self.cmd_serial and self.cmd_serial.is_open:
                try:
                    if self.cmd_serial.in_waiting:
                        data = self.cmd_serial.read(self.cmd_serial.in_waiting).decode('utf-8', errors='ignore')
                        buffer += data
                        
                        # Handle both \r and \n as line terminators
                        if '\r' in buffer:
                            buffer = buffer.replace('\r', '\n')
                            
                        if '\n' in buffer:
                            lines = buffer.split('\n')
                            # Process all complete lines
                            for line in lines[:-1]:
                                self.process_command(line.strip())
                            buffer = lines[-1] # Keep incomplete line
                except Exception as e:
                    print(f"Cmd Loop Error: {e}")
                    time.sleep(1) # Prevent busy loop on persistent error
            time.sleep(0.01)

    def process_command(self, cmd):
        if not cmd:
            return
        
        # Clean up command (remove \r if present)
        cmd = cmd.replace('\r', '')
        print(f"Received Command on {self.cmd_port_name}: {cmd}")
        
        # Echo back is common in shells
        # self.send_cmd_response(f"> {cmd}")

        parts = cmd.split()
        head = parts[0] if parts else ""
        sub = ""
        if head == "flow" and len(parts) > 1:
            sub = parts[1]
        if head.startswith("flow."):
            sub = head.split(".", 1)[1]

        if cmd == "help":
            self.send_cmd_response("Available Commands:")
            self.send_cmd_response("  help        - Show this help")
            self.send_cmd_response("  reboot      - Simulate system reboot")
            self.send_cmd_response("  task_flow   - Trigger main.cpp:33 to moduleA.cpp:80 sequence")
            self.send_cmd_response("  long_task   - Trigger 50s long task")
            self.send_cmd_response("  error_test  - Generate error logs")
            self.send_cmd_response("  spam        - Generate burst of logs")
            self.send_cmd_response("  flow.start [auto|interactive] - Start test flow")
            self.send_cmd_response("  flow.continue - Continue at stage control")
            self.send_cmd_response("  flow.status - Show current flow status")
            self.send_cmd_response("  flow.graph - Show flow graph")
            self.send_cmd_response("  flow.reset - Reset flow state")
            self.send_cmd_response("  flow.jump <node_id> - Jump to node")
            self.send_cmd_response("  flow.stop - Stop flow")
        
        elif cmd == "reboot":
            self.send_cmd_response("Rebooting system...")
            threading.Thread(target=self.simulate_boot, daemon=True).start()
            
        elif cmd == "task_flow":
            self.send_cmd_response("Starting Task Flow...")
            threading.Thread(target=self.simulate_task_flow, daemon=True).start()

        elif cmd == "long_task":
            self.send_cmd_response("Starting Long Task (50s)...")
            threading.Thread(target=self.simulate_long_task, daemon=True).start()
            
        elif cmd == "error_test":
            self.send_cmd_response("Generating errors...")
            self.send_log("Sensor timeout detected", "ERROR", "sensors.c:1024")
            self.send_log("Critical failure in power unit", "CRITICAL", "power.c:55")
            
        elif cmd == "spam":
            self.send_cmd_response("Spamming logs...")
            for i in range(20):
                self.send_log(f"Spam message #{i}", "DEBUG")
                time.sleep(0.05)

        elif cmd == "calibration":
            self.send_cmd_response("Starting Calibration...")
            threading.Thread(target=self.simulate_calibration, daemon=True).start()

        elif cmd == "ota_update":
            self.send_cmd_response("Starting OTA Update...")
            threading.Thread(target=self.simulate_ota, daemon=True).start()

        elif sub == "start" or cmd == "flow.start" or cmd == "flow_start":
            mode = "interactive"
            if len(parts) >= 2 and parts[0] == "flow" and len(parts) >= 3:
                mode = parts[2]
            elif len(parts) >= 2 and parts[0].startswith("flow."):
                mode = parts[1]
            self.start_flow(mode=mode)

        elif sub == "continue" or cmd == "flow.continue" or cmd == "flow_continue" or cmd == "flow.step":
            self.flow_continue.set()
            self.send_cmd_response("FLOW continue acknowledged")

        elif sub == "status" or cmd == "flow.status" or cmd == "flow_status":
            status = self.get_flow_status()
            self.send_cmd_response(f"FLOW status={status['status']} mode={status['mode']} index={status['index']}")
            self.send_cmd_response(f"FLOW node={status['node_id']} name={status['node_name']} waiting={status['waiting']}")

        elif sub == "graph" or cmd == "flow.graph" or cmd == "flow_graph":
            for line in self.format_flow_graph():
                self.send_cmd_response(line)

        elif sub == "reset" or cmd == "flow.reset" or cmd == "flow_reset":
            self.reset_flow()
            self.send_cmd_response("FLOW reset")

        elif sub == "jump" or cmd == "flow.jump" or cmd == "flow_jump":
            node_id = None
            if parts[0] == "flow" and len(parts) >= 3:
                node_id = parts[2]
            elif len(parts) >= 2:
                node_id = parts[1]
            if node_id:
                ok = self.jump_flow(node_id)
                self.send_cmd_response("FLOW jump ok" if ok else "FLOW jump failed")
            else:
                self.send_cmd_response("FLOW jump failed")

        elif sub == "stop" or cmd == "flow.stop" or cmd == "flow_stop":
            self.stop_flow()
            self.send_cmd_response("FLOW stop")
        
        else:
            self.send_cmd_response(f"Unknown command: {cmd}")

    def simulate_calibration(self):
        self.send_log("Calibration started", "INFO", "sensor.c:50")
        time.sleep(1)
        for i in range(10):
            self.send_log(f"Sensor reading {i}: {random.randint(100, 200)}", "DEBUG", "sensor.c:120")
            time.sleep(0.1)
        self.send_log("Calibration complete", "INFO", "sensor.c:200")

    def simulate_long_task(self):
        time.sleep(10) # Wait for test setup
        # Send to CMD port (COM2 -> COM3) per user request to match command port
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.send_cmd_response(f"[{ts}] [INFO] long_task.c:10 - Started long task")
        time.sleep(50)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.send_cmd_response(f"[{ts}] [INFO] long_task.c:99 - Finished long task")

    def simulate_boot(self):
        self.send_log("Bootloader start", "INFO", "boot.c:12")
        time.sleep(0.2)
        self.send_log("HW init ok", "INFO", "board.c:88")
        time.sleep(0.2)
        self.send_log("OS ready", "INFO", "kernel.c:256")
        time.sleep(0.2)
        self.send_log("System ready", "INFO", "main.cpp:9")

    def simulate_task_flow(self):
        self.send_log("User initiated task flow", "INFO", "main.cpp:12")
        self.send_log("main.cpp:33 start", "INFO", "main.cpp:33")
        self.emit_noise(4)
        self.send_log("Allocating buffers", "DEBUG", "memory.cpp:77")
        time.sleep(0.1)
        self.send_log("Task processing complete", "INFO", "moduleA.cpp:80")

    def _build_flow(self):
        return [
            {"id": "n0", "name": "Init", "kind": "log", "start": "main.cpp:12", "end": "function1.cpp:256", "duration": 0.4},
            {"id": "g1", "name": "Stage Gate A", "kind": "gate", "start": "gateA.cpp:10", "end": "gateA.cpp:90", "duration": 0.2},
            {"id": "n1", "name": "Phase 1", "kind": "log", "start": "function2.cpp:50", "end": "module7.cpp:30", "duration": 0.5},
            {"id": "g2", "name": "Stage Gate B", "kind": "gate", "start": "gateB.cpp:20", "end": "gateB.cpp:120", "duration": 0.2},
            {"id": "n2", "name": "Legacy Task Flow", "kind": "log", "start": "main.cpp:33", "end": "moduleA.cpp:80", "duration": 0.4}
        ]

    def start_flow(self, mode="interactive"):
        with self.flow_lock:
            if self.flow_thread and self.flow_thread.is_alive():
                self.send_cmd_response("FLOW already running")
                return
            self.flow_stop.clear()
            self.flow_continue.clear()
            self.flow_mode = mode if mode in ("auto", "interactive") else "interactive"
            self.flow_state = "running"
            self.flow_thread = threading.Thread(target=self._run_flow, daemon=True)
            self.flow_thread.start()
            self.send_cmd_response(f"FLOW started mode={self.flow_mode}")

    def stop_flow(self):
        self.flow_stop.set()
        self.flow_continue.set()
        with self.flow_lock:
            self.flow_state = "stopped"
            self.flow_mode = "idle"

    def reset_flow(self):
        self.stop_flow()
        with self.flow_lock:
            self.flow_index = -1
            self.flow_state = "idle"
            self.flow_mode = "idle"
            self.flow_continue.clear()

    def jump_flow(self, node_id: str) -> bool:
        with self.flow_lock:
            for idx, n in enumerate(self.flow_nodes):
                if n["id"] == node_id:
                    self.flow_index = idx - 1
                    return True
        return False

    def get_flow_status(self):
        with self.flow_lock:
            node = self.flow_nodes[self.flow_index] if 0 <= self.flow_index < len(self.flow_nodes) else None
            return {
                "status": self.flow_state,
                "mode": self.flow_mode,
                "index": self.flow_index,
                "node_id": node["id"] if node else "none",
                "node_name": node["name"] if node else "none",
                "waiting": self.flow_state == "waiting"
            }

    def format_flow_graph(self):
        lines = ["FLOW GRAPH:"]
        for idx, n in enumerate(self.flow_nodes):
            lines.append(f"  [{idx}] {n['id']} {n['name']} {n['kind']} {n['start']} -> {n['end']}")
        return lines

    def emit_noise(self, count=3):
        noise = [
            ("Cache flush", "DEBUG", "cache.cpp:77"),
            ("Telemetry heartbeat", "INFO", "telemetry.cpp:44"),
            ("Voltage check ok", "INFO", "power.cpp:201"),
            ("Ignoring stale packet", "IGNORE", "net.cpp:19"),
            ("Scheduler tick", "DEBUG", "sched.cpp:301"),
            ("IPC ping", "INFO", "ipc.cpp:88")
        ]
        for _ in range(count):
            msg, lvl, src = random.choice(noise)
            self.send_log(msg, lvl, src)
            time.sleep(0.05)

    def _run_flow(self):
        total = len(self.flow_nodes)
        for idx in range(self.flow_index + 1, total):
            if self.flow_stop.is_set():
                break
            node = self.flow_nodes[idx]
            with self.flow_lock:
                self.flow_index = idx
                self.flow_state = "running"
            self.send_log(f"{node['name']} start", "INFO", node["start"])
            self.emit_noise(3)
            if node["kind"] == "gate" and self.flow_mode == "interactive":
                with self.flow_lock:
                    self.flow_state = "waiting"
                self.send_cmd_response(f"FLOW WAIT {node['id']} {node['name']}")
                self.flow_continue.clear()
                while not self.flow_continue.is_set():
                    if self.flow_stop.is_set():
                        break
                    time.sleep(0.05)
            time.sleep(node.get("duration", 0.2))
            self.send_log(f"{node['name']} end", "INFO", node["end"])
        with self.flow_lock:
            if not self.flow_stop.is_set():
                self.flow_state = "done"
                self.flow_mode = "idle"

    def simulate_ota(self):
        self.send_log("OTA Update initiated", "INFO", "ota.c:10")
        time.sleep(1)
        for i in range(0, 101, 10):
            self.send_log(f"Downloading firmware: {i}%", "INFO", "ota.c:50")
            time.sleep(0.2)
        self.send_log("Download complete. Verifying...", "INFO", "ota.c:80")
        time.sleep(1)
        self.send_log("Rebooting for update...", "INFO", "ota.c:99")
        self.simulate_boot()

    def background_log_loop(self):
        """Emits random background logs."""
        cnt = 0
        while self.running:
            time.sleep(0.2)
            # Periodic heartbeat
            self.send_log(f"Watchdog feed {cnt}", "IGNORE", "watchdog.c:50")
            
            if cnt % 5 == 0:
                 self.send_log(f"System heartbeat tick {cnt}", "DEBUG", "sys.c:10")
            
            cnt += 1

if __name__ == "__main__":
    sim = FirmwareSimulator()
    sim.start()
