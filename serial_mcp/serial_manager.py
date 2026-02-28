import asyncio
import re
import time
import threading
import queue
import subprocess
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict, Any, Union
import json
import os
import uuid

logger = logging.getLogger(__name__)

try:
    import serial
    import serial.tools.list_ports
except Exception:
    serial = None
    logger.warning("pyserial not available")



@dataclass
class LogLine:
    ts: float
    text: str
    device: str = "unknown"
    hex_text: str = ""
    packet: bool = False


@dataclass
class AutoAction:
    kind: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AutoRule:
    pattern: str
    regex: bool = True
    actions: List[AutoAction] = field(default_factory=list)
    once: bool = True
    delay_ms: int = 0
    interval_ms: int = 0
    device: Optional[str] = None  # None matches any device
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    last_fired: float = field(default=0.0, init=False)


@dataclass
class SerialState:
    device: str
    port: Any  # serial.Serial
    reader_thread: Optional[threading.Thread] = None
    mode: str = "ascii"
    
class SerialManager:
    def __init__(self, config_path: Optional[str] = None) -> None:
        self._ports: Dict[str, SerialState] = {}  # device -> SerialState
        self._port_lock = threading.Lock()
        
        self._stop_reader = threading.Event()
        self._logs: List[LogLine] = []
        self._log_lock = threading.Lock()
        self._filters_default: List[re.Pattern] = [re.compile(r"\[IGNORE\]")]
        self._filters_source_default: List[str] = [r"\[IGNORE\]"]
        self._filters_regex_default = True
        self._filters_by_device: Dict[str, List[re.Pattern]] = {}
        self._filters_source_by_device: Dict[str, List[str]] = {}
        self._filters_regex_by_device: Dict[str, bool] = {}
        self._queue: "queue.Queue[tuple[str, str]]" = queue.Queue() # (text, device)
        self._log_max_lines_default = 360000
        self._log_max_lines = 360000
        self._log_base_index = 0
        self._packet_enabled_default = True
        self._packet_timeout_ms_default = 20
        self._auto_save_default_enabled = False
        self._auto_save_default_path = ""
        self._auto_save_default_device: Optional[str] = None
        self._log_options_by_device: Dict[str, Dict[str, Any]] = {}
        self._auto_save_by_device: Dict[str, Dict[str, Any]] = {}
        self._port_configs: Dict[str, Dict[str, Any]] = {}
        self._auto_save_lock = threading.Lock()
        
        try:
            self._loop = asyncio.get_event_loop()
        except RuntimeError:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
        self._new_line_event = asyncio.Event()
        
        self._auto_rules_by_device: Dict[str, List[AutoRule]] = {}
        self._auto_lock = threading.Lock()
        self._auto_thread: Optional[threading.Thread] = None
        self._stop_auto = threading.Event()
        self._timestamp_fmt = "%Y-%m-%d %H:%M:%S.%f"
        self.web_ui_url: Optional[str] = None
        
        self._config_path = config_path if config_path else os.path.join(os.getcwd(), "serial_mcp_config.json")
        self._load_config()

    def _cleanup_pending_tasks(self):
        """
        Cancel pending tasks but DO NOT close the loop.
        The loop might be shared with the main application (FastAPI, MCP server, or pytest).
        Closing it here would crash the hosting application.
        """
        try:
             # Cancel all running tasks that are not the current one
             if not self._loop.is_closed():
                 current = asyncio.current_task(self._loop)
                 for task in asyncio.all_tasks(self._loop):
                     if not task.done() and task is not current:
                         task.cancel()
        except Exception as e:
             logger.error(f"Error cleaning up tasks: {e}")

    def _load_config(self) -> None:
        if not os.path.exists(self._config_path):
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            ports = config.get("ports")
            if isinstance(ports, dict):
                for dev, cfg in ports.items():
                    if not isinstance(cfg, dict):
                        continue
                    self._ensure_port_config(dev)
                    if "filters" in cfg or "filters_regex" in cfg:
                        self.set_filters(
                            cfg.get("filters", []),
                            regex=cfg.get("filters_regex", True),
                            device=dev,
                            save=False
                        )
                    if "log_options" in cfg:
                        opts = cfg.get("log_options", {})
                        self.set_log_options(
                            packet_enabled=opts.get("packet_enabled"),
                            packet_timeout_ms=opts.get("packet_timeout_ms"),
                            log_max_lines=opts.get("log_max_lines"),
                            device=dev,
                            save=False
                        )
                    if "auto_save" in cfg:
                        as_opts = cfg.get("auto_save", {})
                        self.set_auto_save(
                            enabled=as_opts.get("enabled", False),
                            path=as_opts.get("path", ""),
                            device=as_opts.get("device", dev),
                            scope_device=dev,
                            save=False
                        )
                    if "connection" in cfg:
                        conn = cfg.get("connection", {})
                        self.set_connection(
                            device=dev,
                            baudrate=conn.get("baudrate"),
                            data_bits=conn.get("data_bits"),
                            parity=conn.get("parity"),
                            stop_bits=conn.get("stop_bits"),
                            flow_control=conn.get("flow_control"),
                            save=False
                        )
                    if "console" in cfg:
                        con = cfg.get("console", {})
                        self.set_console(
                            device=dev,
                            auto_scroll=con.get("auto_scroll"),
                            timestamp=con.get("timestamp"),
                            line_num=con.get("line_num"),
                            hex_view=con.get("hex_view"),
                            send_mode=con.get("send_mode"),
                            send_text=con.get("send_text"),
                            append_newline=con.get("append_newline"),
                            auto_send=con.get("auto_send"),
                            send_interval_ms=con.get("send_interval_ms"),
                            save=False
                        )
                    rules_data = cfg.get("rules", [])
                    if isinstance(rules_data, list):
                        with self._auto_lock:
                            for r in rules_data:
                                actions = [AutoAction(kind=a.get("kind"), params=a.get("params", {})) for a in r.get("actions", [])]
                                rule = AutoRule(
                                    pattern=r.get("pattern", ""),
                                    regex=r.get("regex", True),
                                    actions=actions,
                                    once=r.get("once", True),
                                    delay_ms=r.get("delay_ms", 0),
                                    interval_ms=r.get("interval_ms", 0),
                                    device=dev,
                                    id=r.get("id") or uuid.uuid4().hex
                                )
                                self._auto_rules_by_device.setdefault(dev, []).append(rule)
            else:
                legacy_filters = config.get("filters", [])
                legacy_regex = config.get("filters_regex", True)
                legacy_opts = config.get("log_options", {})
                legacy_auto_save = config.get("auto_save", {})
                legacy_rules = config.get("rules", [])
                if legacy_filters or legacy_opts:
                    self.set_filters(legacy_filters, regex=legacy_regex, device=None, save=False)
                    self.set_log_options(
                        packet_enabled=legacy_opts.get("packet_enabled"),
                        packet_timeout_ms=legacy_opts.get("packet_timeout_ms"),
                        log_max_lines=legacy_opts.get("log_max_lines"),
                        device=None,
                        save=False
                    )
                if legacy_auto_save:
                    self.set_auto_save(
                        enabled=legacy_auto_save.get("enabled", False),
                        path=legacy_auto_save.get("path", ""),
                        device=legacy_auto_save.get("device"),
                        scope_device=None,
                        save=False
                    )
                devices = set()
                auto_dev = legacy_auto_save.get("device")
                if auto_dev:
                    devices.add(auto_dev)
                for r in legacy_rules:
                    dev = r.get("device")
                    if dev:
                        devices.add(dev)
                for dev in devices:
                    self._ensure_port_config(dev)
                    if legacy_auto_save.get("device") == dev:
                        self.set_auto_save(
                            enabled=legacy_auto_save.get("enabled", False),
                            path=legacy_auto_save.get("path", ""),
                            device=legacy_auto_save.get("device", dev),
                            scope_device=dev,
                            save=False
                        )
                    rules_for_dev = [r for r in legacy_rules if r.get("device") == dev]
                    if rules_for_dev:
                        with self._auto_lock:
                            for r in rules_for_dev:
                                actions = [AutoAction(kind=a.get("kind"), params=a.get("params", {})) for a in r.get("actions", [])]
                                rule = AutoRule(
                                    pattern=r.get("pattern", ""),
                                    regex=r.get("regex", True),
                                    actions=actions,
                                    once=r.get("once", True),
                                    delay_ms=r.get("delay_ms", 0),
                                    interval_ms=r.get("interval_ms", 0),
                                    device=dev,
                                    id=r.get("id") or uuid.uuid4().hex
                                )
                                self._auto_rules_by_device.setdefault(dev, []).append(rule)
            
            logger.info(f"Loaded config from {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")

    def _save_config(self) -> None:
        try:
            config = {
                "ports": self._get_ports_config()
            }
            
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            logger.info("Saved config")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def get_config(self, device: Optional[str] = None) -> Dict[str, Any]:
        merged = self._get_port_config(device)
        # Convert patterns to strings for JSON serialization
        filters_str = []
        if "filters" in merged and isinstance(merged["filters"], list):
            for p in merged["filters"]:
                if hasattr(p, "pattern"):
                    filters_str.append(p.pattern)
                else:
                    filters_str.append(str(p))
        else:
            filters_str = []
            
        return {
            "filters": filters_str,
            "filters_regex": merged["filters_regex"],
            "log_options": merged["log_options"],
            "auto_save": merged["auto_save"],
            "connection": merged["connection"],
            "console": merged["console"],
            "rules": merged["rules"]
        }

    def _get_default_config(self) -> Dict[str, Any]:
        return {
            "filters": list(self._filters_source_default),
            "filters_regex": self._filters_regex_default,
            "log_options": {
                "packet_enabled": self._packet_enabled_default,
                "packet_timeout_ms": self._packet_timeout_ms_default,
                "log_max_lines": self._log_max_lines_default
            },
            "auto_save": {
                "enabled": self._auto_save_default_enabled,
                "path": self._auto_save_default_path,
                "device": self._auto_save_default_device
            },
            "connection": {
                "baudrate": 115200,
                "data_bits": 8,
                "parity": "N",
                "stop_bits": 1,
                "flow_control": "none"
            },
            "console": {
                "auto_scroll": True,
                "timestamp": True,
                "line_num": True,
                "hex_view": False,
                "send_mode": "ascii",
                "send_text": "",
                "append_newline": False,
                "auto_send": False,
                "send_interval_ms": 1000
            }
        }

    def _get_ports_config(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        devices = set(self._port_configs.keys())
        devices.update(self._auto_rules_by_device.keys())
        devices.update(self._filters_by_device.keys())
        devices.update(self._log_options_by_device.keys())
        devices.update(self._auto_save_by_device.keys())
        for device in devices:
            out[device] = self._get_port_config(device)
        return out

    def _get_port_config(self, device: Optional[str]) -> Dict[str, Any]:
        if not device:
            base = self._get_default_config()
            base["rules"] = []
            return base
        cfg = self._port_configs.get(device)
        if not cfg:
            cfg = self._ensure_port_config(device)
        return {
            "filters": list(self._filters_source_by_device.get(device, [])),
            "filters_regex": cfg.get("filters_regex", True),
            "log_options": dict(cfg.get("log_options", {})),
            "auto_save": dict(cfg.get("auto_save", {})),
            "connection": dict(cfg.get("connection", {})),
            "console": dict(cfg.get("console", {})),
            "rules": self.get_auto_rules(device)
        }

    def _ensure_port_config(self, device: str) -> Dict[str, Any]:
        if device not in self._port_configs:
            base = self._get_default_config()
            base["rules"] = []
            self._port_configs[device] = base
            compiled = []
            for pat in base.get("filters", []):
                try:
                    compiled.append(re.compile(pat) if base.get("filters_regex", True) else re.compile(re.escape(pat)))
                except Exception:
                    logger.error(f"Invalid regex pattern in default config: {pat}")
            self._filters_by_device[device] = compiled
            self._filters_source_by_device[device] = list(base.get("filters", []))
            self._filters_regex_by_device[device] = bool(base.get("filters_regex", True))
            self._log_options_by_device[device] = dict(base.get("log_options", {}))
            self._auto_save_by_device[device] = dict(base.get("auto_save", {}))
        return self._port_configs[device]

    def _get_filters_for_device(self, device: Optional[str]) -> List[re.Pattern]:
        if device and device in self._filters_by_device:
            return self._filters_by_device.get(device, [])
        return self._filters_default

    def _get_log_options_for_device(self, device: Optional[str]) -> Dict[str, Any]:
        if device and device in self._log_options_by_device:
            opts = dict(self._log_options_by_device.get(device, {}))
            merged = {
                "packet_enabled": self._packet_enabled_default,
                "packet_timeout_ms": self._packet_timeout_ms_default,
                "log_max_lines": self._log_max_lines_default
            }
            merged.update(opts)
            return merged
        return {
            "packet_enabled": self._packet_enabled_default,
            "packet_timeout_ms": self._packet_timeout_ms_default,
            "log_max_lines": self._log_max_lines_default
        }

    def _get_auto_save_for_device(self, device: Optional[str]) -> Dict[str, Any]:
        if device and device in self._auto_save_by_device:
            as_opts = dict(self._auto_save_by_device.get(device, {}))
            merged = {
                "enabled": self._auto_save_default_enabled,
                "path": self._auto_save_default_path,
                "device": self._auto_save_default_device
            }
            merged.update(as_opts)
            return merged
        return {
            "enabled": self._auto_save_default_enabled,
            "path": self._auto_save_default_path,
            "device": self._auto_save_default_device
        }

    def _recompute_log_max_lines(self) -> None:
        values = [self._log_max_lines_default]
        for opts in self._log_options_by_device.values():
            if "log_max_lines" in opts and opts["log_max_lines"] is not None:
                values.append(int(opts["log_max_lines"]))
        new_max = max(values) if values else self._log_max_lines_default
        if new_max != self._log_max_lines:
            self._log_max_lines = new_max
            with self._log_lock:
                if len(self._logs) > self._log_max_lines:
                    overflow = len(self._logs) - self._log_max_lines
                    del self._logs[:overflow]
                    self._log_base_index += overflow

    def _check_port_availability(self, device: str) -> str:
        """Check if a port can be opened. Returns 'available', 'busy', or 'error'."""
        try:
            # Try to open with minimal settings and short timeout
            s = serial.Serial(device, timeout=0.1)
            s.close()
            return "available"
        except serial.SerialException as e:
            msg = str(e)
            # Common Windows/Linux permission error strings
            if "PermissionError" in msg or "Access is denied" in msg or "Device or resource busy" in msg or "拒绝访问" in msg:
                return "busy"
            return "error"
        except Exception:
            return "error"

    def list_ports(self) -> List[Dict[str, Any]]:
        if serial is None:
            return []
        items = []
        # Get all physical ports via pyserial
        comports = serial.tools.list_ports.comports()
        found_devices = set()
        
        for p in comports:
            is_open = False
            with self._port_lock:
                is_open = p.device in self._ports
            
            status = "open" if is_open else self._check_port_availability(p.device)

            items.append({
                "device": p.device, 
                "description": p.description or "", 
                "hwid": p.hwid or "",
                "is_open": is_open,
                "status": status
            })
            found_devices.add(p.device)

        # Windows Registry Fallback
        import sys
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM")
                for i in range(winreg.QueryInfoKey(key)[1]):
                    try:
                        _, value, _ = winreg.EnumValue(key, i)
                        # value is usually "COMx"
                        if value not in found_devices:
                            is_open = False
                            with self._port_lock:
                                is_open = value in self._ports
                            
                            status = "open" if is_open else self._check_port_availability(value)

                            items.append({
                                "device": value,
                                "description": "Virtual Serial Port (Registry)",
                                "hwid": "REGISTRY_DETECTED",
                                "is_open": is_open,
                                "status": status
                            })
                            found_devices.add(value)
                    except Exception:
                        pass
                winreg.CloseKey(key)
            except Exception as e:
                logger.debug(f"Registry scan failed: {e}")

        logger.debug(f"list_ports found: {list(found_devices)}")
        return items

    def open(self, device: str, baudrate: int = 115200, parity: str = "N", bytesize: int = 8, stopbits: int = 1, rtscts: bool = False, xonxoff: bool = False, dsrdtr: bool = False) -> None:
        logger.info(f"Opening port {device} at {baudrate} baud")
        if serial is None:
            raise RuntimeError("pyserial not available")
            
        with self._port_lock:
            if device in self._ports:
                self.close(device)
                
            parity_map = {
                "N": serial.PARITY_NONE,
                "E": serial.PARITY_EVEN,
                "O": serial.PARITY_ODD,
                "M": serial.PARITY_MARK,
                "S": serial.PARITY_SPACE
            }
            par = parity_map.get(parity, serial.PARITY_NONE)
            bs = {5: serial.FIVEBITS, 6: serial.SIXBITS, 7: serial.SEVENBITS, 8: serial.EIGHTBITS}[bytesize]
            sb = {1: serial.STOPBITS_ONE, 1.5: serial.STOPBITS_ONE_POINT_FIVE, 2: serial.STOPBITS_TWO}[stopbits]
            
            port_obj = serial.Serial(device, baudrate=baudrate, parity=par, bytesize=bs, stopbits=sb, timeout=0, rtscts=rtscts, xonxoff=xonxoff, dsrdtr=dsrdtr)
            state = SerialState(device=device, port=port_obj)
            self._ports[device] = state
            logger.info(f"Port {device} opened successfully")
            
        self._start_reader(device)

    def close(self, device: Optional[str] = None) -> None:
        """Close specific device, or all if device is None"""
        logger.info(f"Closing port(s): {device if device else 'ALL'}")
        
        to_close = []
        with self._port_lock:
            targets = [device] if device else list(self._ports.keys())
            for dev in targets:
                if dev in self._ports:
                    to_close.append(self._ports[dev])
                    del self._ports[dev]
            
            if not self._ports:
                self._stop_reader.set() # Stop all if no ports left
                self._cleanup_pending_tasks()
        
        # Close ports outside the lock to prevent blocking other threads (e.g. list_ports)
        # if the driver close operation hangs.
        for state in to_close:
            if state.port:
                try:
                    state.port.close()
                    logger.debug(f"Closed {state.device}")
                except Exception as e:
                    logger.error(f"Error closing {state.device}: {e}")

    def set_mode(self, mode: str, device: Optional[str] = None) -> None:
        new_mode = "hex" if mode.lower() == "hex" else "ascii"
        logger.info(f"Setting mode to {new_mode} for {device if device else 'ALL'}")
        with self._port_lock:
            if device:
                if device in self._ports:
                    self._ports[device].mode = new_mode
            else:
                # Set for all
                for p in self._ports.values():
                    p.mode = new_mode

    def set_filters(self, patterns: List[str], regex: bool = True, device: Optional[str] = None, save: bool = True) -> None:
        logger.info(f"Setting filters: {patterns} (regex={regex}) for {device if device else 'DEFAULT'}")
        compiled = []
        for pat in patterns:
            compiled.append(re.compile(pat) if regex else re.compile(re.escape(pat)))
        with self._log_lock:
            if device:
                cfg = self._ensure_port_config(device)
                self._filters_by_device[device] = compiled
                self._filters_source_by_device[device] = list(patterns)
                self._filters_regex_by_device[device] = regex
                cfg["filters"] = list(patterns)
                cfg["filters_regex"] = regex
            else:
                self._filters_default = compiled
                self._filters_source_default = list(patterns)
                self._filters_regex_default = regex
        if save:
            self._save_config()

    def set_timestamp_format(self, fmt: str) -> None:
        self._timestamp_fmt = fmt

    def send(self, data: str, device: Optional[str] = None) -> None:
        """Send data to specific device or all active devices"""
        logger.debug(f"Sending data to {device if device else 'ALL'}: {repr(data)}")
        if not self._ports:
            raise RuntimeError("no serial ports open")
            
        targets = []
        with self._port_lock:
            if device:
                if device not in self._ports:
                    raise RuntimeError(f"port {device} not open")
                targets.append(self._ports[device])
            else:
                targets = list(self._ports.values())
        
        if not targets:
            raise RuntimeError(f"No target ports found for device={device}")

        for state in targets:
            try:
                if state.mode == "hex":
                    try:
                        clean_data = re.sub(r"0x", "", data, flags=re.IGNORECASE)
                        clean_data = re.sub(r"[^0-9a-fA-F]", "", clean_data)
                        if not clean_data:
                            raise ValueError("empty hex payload")
                        if len(clean_data) % 2 == 1:
                            clean_data = clean_data + "0"
                        raw = bytes.fromhex(clean_data)
                    except ValueError as e:
                        raise ValueError(f"Invalid HEX format: {str(e)}")
                else:
                    # ASCII mode: interpret escapes like \n, \r, \t
                    # But Python string from web might already be escaped or not.
                    # Usually users type "help\n" or "help". 
                    # If they type "help", we might want to append newline? 
                    # The user didn't ask for auto-newline, but it's common. 
                    # For now, let's just encode. 
                    # Also support C-style escapes if user types them? 
                    # Let's keep it simple for now, raw string.
                    raw = data.encode("utf-8", errors="ignore")
                
                state.port.write(raw)
                self._append_log(raw, state.device, packet=False, direction="tx")
            except Exception as e:
                logger.error(f"Failed to write to {state.device}: {e}")
                raise RuntimeError(f"Failed to write to {state.device}: {str(e)}")

    def _start_reader(self, device: str) -> None:
        logger.debug(f"Starting reader thread for {device}")
        self._stop_reader.clear()
        t = threading.Thread(target=self._reader_loop, args=(device,), daemon=True)
        with self._port_lock:
            if device in self._ports:
                self._ports[device].reader_thread = t
        t.start()

    def _reader_loop(self, device: str) -> None:
        buf = b""
        last_data_time = None
        port_obj = None
        
        with self._port_lock:
            if device in self._ports:
                port_obj = self._ports[device].port
                
        if not port_obj:
            logger.error(f"Reader loop started but port object not found for {device}")
            return

        while not self._stop_reader.is_set():
            try:
                if not port_obj.is_open:
                    logger.warning(f"Port {device} closed unexpectedly")
                    break
                chunk = port_obj.read(1024)
            except (OSError, serial.SerialException, AttributeError) as e:
                # AttributeError can happen on Windows if port is closed during read (hEvent is None)
                if not port_obj.is_open:
                     logger.debug(f"Port {device} closed during read ({e})")
                     break
                logger.error(f"Read error on {device}: {e}")
                break
                
            if chunk:
                # logger.debug(f"Read {len(chunk)} bytes from {device}") # Too verbose?
                buf += chunk
                last_data_time = time.time()
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    raw = line.rstrip(b"\r")
                    self._append_log(raw, device, packet=False)
            else:
                time.sleep(0.01)
            
            packet_opts = self._get_log_options_for_device(device)
            if packet_opts.get("packet_enabled") and buf and last_data_time:
                if (time.time() - last_data_time) * 1000 >= int(packet_opts.get("packet_timeout_ms", 20)):
                    self._append_log(buf, device, packet=True)
                    buf = b""
                    last_data_time = None

    def _filtered(self, text: str, device: Optional[str]) -> bool:
        for f in self._get_filters_for_device(device):
            if f.search(text):
                return True
        return False

    def _append_log(self, raw: bytes, device: str, packet: bool, direction: str = "rx") -> None:
        if isinstance(raw, bytes):
            txt = raw.decode("utf-8", errors="ignore")
            hex_text = raw.hex(" ").upper()
        elif isinstance(raw, bytearray):
            data = bytes(raw)
            txt = data.decode("utf-8", errors="ignore")
            hex_text = data.hex(" ").upper()
        else:
            txt = str(raw)
            hex_text = ""
        
        if direction == "tx":
            txt = f">> {txt}"
            if hex_text:
                hex_text = f">> {hex_text}"

        if self._filtered(txt, device):
            return
        
        ts = time.time()
        with self._log_lock:
            self._logs.append(LogLine(ts=ts, text=txt, device=device, hex_text=hex_text, packet=packet))
            if self._log_max_lines and len(self._logs) > self._log_max_lines:
                overflow = len(self._logs) - self._log_max_lines
                if overflow > 0:
                    del self._logs[:overflow]
                    self._log_base_index += overflow
        self._queue.put((txt, device))
        try:
            self._loop.call_soon_threadsafe(self._new_line_event.set)
        except RuntimeError:
             # Loop might be closed if shutting down
             pass
        auto_save_cfg = self._get_auto_save_for_device(device)
        if auto_save_cfg.get("enabled") and auto_save_cfg.get("path"):
            if auto_save_cfg.get("device") and auto_save_cfg.get("device") != device:
                return
            line_text = txt if txt else hex_text
            # Remove trailing whitespace including newlines to avoid double spacing in log file
            line_text = line_text.rstrip()
            line = f"[{self._format_ts(ts)}] [{device}] {line_text}\n"
            with self._auto_save_lock:
                import os
                path = auto_save_cfg.get("path")
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line)

    def clear_logs(self, device: Optional[str] = None) -> None:
        with self._log_lock:
            if device:
                # Filter out logs for specific device
                old_len = len(self._logs)
                self._logs = [l for l in self._logs if l.device != device]
                new_len = len(self._logs)
                
                # To maintain index continuity for subsequent logs (which use base + len),
                # we must increase the base index by the number of removed items.
                # This ensures that if we had 100 items (indices 0-99), next was 100.
                # If we remove 10 items, len becomes 90.
                # If we don't adjust base, next is 90. This is a regression!
                # By adding 10 to base, next becomes 0 + 10 + 90 = 100. Correct.
                # Note: This effectively "shifts" the indices of remaining items (e.g. device B)
                # to higher values. This is acceptable as the client will just skip the gap.
                self._log_base_index += (old_len - new_len)
            else:
                # Clear all
                self._logs = []
                self._log_base_index = 0
                
    def get_logs(self, device: Optional[str] = None, start_index: int = 0, limit: int = 10000, include_hex: bool = False) -> List[Dict[str, Any]]:
        with self._log_lock:
            if start_index < self._log_base_index:
                start_index = self._log_base_index
            local_start = max(0, start_index - self._log_base_index)
            
            # Apply limit to slice immediately to reduce memory usage under lock
            # We fetch a bit more than limit in case filtering by device reduces count
            # But simpler approach: just fetch 'limit' items from the global log
            # The client will ask for next chunk anyway.
            # If we strictly filter by device, we might need to scan more.
            # Let's try to scan up to limit * 2 or just limit.
            # If we don't return enough items for a specific device, client will poll again.
            
            # Optimization: slice self._logs directly
            # Note: limit refers to output items or input scanned items?
            # Usually API limit refers to output items.
            # If we filter by device, we might scan 100k items to find 1 item.
            # That's bad for lock contention.
            # Let's limit the SCAN range to prevent lock holding too long.
            scan_limit = limit * 5 # Heuristic: scan up to 5x limit
            
            if local_start >= len(self._logs):
                return []
                
            items_slice = self._logs[local_start : local_start + scan_limit]
            base_index = self._log_base_index + local_start
        
        # Release lock before processing/filtering
        out = []
        for i, l in enumerate(items_slice):
            if device and l.device != device:
                continue
            item = {
                "timestamp": self._format_ts(l.ts), 
                "text": l.text,
                "device": l.device,
                "packet": l.packet,
                "index": base_index + i
            }
            if include_hex:
                item["hex"] = l.hex_text
            out.append(item)
            if len(out) >= limit:
                break
                
        return out

    def get_stats(self) -> Dict[str, Any]:
        with self._log_lock:
            total = self._log_base_index + len(self._logs)
            return {
                "total_logs": total,
                "buffer_size": len(self._logs),
                "base_index": self._log_base_index
            }

    async def wait_marker_context(self, marker: str, before: int = 20, after: int = 40, timeout: Optional[float] = None, device: Optional[str] = None) -> Dict[str, Any]:
        start = time.time()
        idx = -1
        last_log_count = 0
        
        while True:
            with self._log_lock:
                last_log_count = len(self._logs)
                # Search backwards to find the latest occurrence
                for i in range(len(self._logs) - 1, -1, -1):
                    l = self._logs[i]
                    if device and l.device != device:
                        continue
                    if self._filtered(l.text, l.device):
                        continue
                    if marker in l.text:
                        idx = i
                        break
            if idx >= 0:
                with self._log_lock:
                    b = max(0, idx - before)
                    a = min(len(self._logs), idx + after + 1)
                    ctx = self._logs[b:a]
                
                lines = []
                for l in ctx:
                    if device and l.device != device:
                        continue
                    if self._filtered(l.text, l.device):
                        continue
                    lines.append({"timestamp": self._format_ts(l.ts), "text": l.text, "device": l.device})
                
                return {
                    "marker_index": idx, 
                    "lines": lines
                }

            elapsed = time.time() - start
            if timeout is not None:
                if elapsed > timeout:
                    return {"marker_index": -1, "lines": []}
                # Don't sleep too long to ensure responsiveness, but don't busy wait
                # We use polling to avoid asyncio event loop mismatch issues
                poll_interval = 0.1
            else:
                poll_interval = 0.1
            
            # Wait for new logs or timeout
            step_wait = 0
            while step_wait < 1.0: # Check at least once per second
                await asyncio.sleep(poll_interval)
                step_wait += poll_interval
                
                # Check total timeout
                if timeout is not None and (time.time() - start) > timeout:
                     return {"marker_index": -1, "lines": []}

                # Check if new logs arrived
                with self._log_lock:
                    curr_count = len(self._logs)
                if curr_count > last_log_count:
                    break # Break inner wait, go to outer scan

    async def wait_between(self, start_marker: str, end_marker: str, timeout: Optional[float] = None, device: Optional[str] = None) -> Dict[str, Any]:
        logger.info(f"wait_between start: start={start_marker}, end={end_marker}, dev={device}, timeout={timeout}")
        start = time.time()
        s_idx = -1
        e_idx = -1
        last_log_count = 0
        
        while True:
            with self._log_lock:
                last_log_count = len(self._logs)
                # Find the latest start_marker
                for i in range(len(self._logs) - 1, -1, -1):
                    l = self._logs[i]
                    if device and l.device != device:
                        continue
                    if self._filtered(l.text, l.device):
                        continue
                    if start_marker in l.text:
                        s_idx = i
                        break
                
                # If start found, search for end_marker AFTER start
                if s_idx >= 0:
                    for i in range(s_idx, len(self._logs)):
                        l = self._logs[i]
                        if device and l.device != device:
                            continue
                        if self._filtered(l.text, l.device):
                            continue
                        if end_marker in l.text:
                            e_idx = i
                            break
            
            if s_idx >= 0 and e_idx >= 0:
                logger.info(f"wait_between found: start_idx={s_idx}, end_idx={e_idx}")
                with self._log_lock:
                    ctx = self._logs[s_idx:e_idx + 1]
                
                lines = []
                for l in ctx:
                    if device and l.device != device:
                        continue
                    if self._filtered(l.text, l.device):
                        continue
                    lines.append({"timestamp": self._format_ts(l.ts), "text": l.text, "device": l.device})

                return {
                    "start_index": s_idx, 
                    "end_index": e_idx, 
                    "lines": lines
                }
            
            elapsed = time.time() - start
            if timeout is not None:
                if elapsed > timeout:
                    logger.warning(f"wait_between timeout: elapsed={elapsed} > {timeout}. s_idx={s_idx}")
                    return {"start_index": -1, "end_index": -1, "lines": []}
                # poll_interval set below
            
            poll_interval = 0.1
            
            # Wait for new logs or timeout
            step_wait = 0
            while step_wait < 1.0: # Check at least once per second
                await asyncio.sleep(poll_interval)
                step_wait += poll_interval
                
                # Check total timeout
                if timeout is not None and (time.time() - start) > timeout:
                     logger.warning("wait_between timeout during poll")
                     return {"start_index": -1, "end_index": -1, "lines": []}

                # Check if new logs arrived
                with self._log_lock:
                    curr_count = len(self._logs)
                if curr_count > last_log_count:
                    break # Break inner wait, go to outer scan

    async def wait_multiple(self, queries: List[Dict[str, Any]], timeout: Optional[float] = None) -> List[Dict[str, Any]]:
        async def run_query(q: Dict[str, Any]) -> Dict[str, Any]:
            kind = q.get("kind")
            dev = q.get("device")
            if kind == "context":
                r = await self.wait_marker_context(q.get("marker", ""), q.get("before", 20), q.get("after", 40), timeout, device=dev)
                return {"kind": "context", "result": r}
            if kind == "between":
                r = await self.wait_between(q.get("start", ""), q.get("end", ""), timeout, device=dev)
                return {"kind": "between", "result": r}
            return {"kind": kind or "", "result": None}

        tasks = [asyncio.create_task(run_query(q)) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return list(results)

    def add_auto_rule(self, rule: AutoRule, device: Optional[str] = None) -> None:
        logger.info(f"Adding auto rule: {rule}")
        target = device or rule.device
        if not target:
            return
        rule.device = target
        self._ensure_port_config(target)
        with self._auto_lock:
            self._auto_rules_by_device.setdefault(target, []).append(rule)
        if not self._auto_thread or not self._auto_thread.is_alive():
            self._start_auto()
        self._save_config()

    def clear_auto_rules(self, device: Optional[str] = None) -> None:
        logger.info(f"Clearing auto rules for {device if device else 'ALL'}")
        with self._auto_lock:
            if device:
                self._auto_rules_by_device.pop(device, None)
            else:
                self._auto_rules_by_device = {}
        self._save_config()

    def get_auto_rules(self, device: Optional[str] = None) -> List[Dict[str, Any]]:
        if not device:
            return []
        with self._auto_lock:
            rules = list(self._auto_rules_by_device.get(device, []))
        out = []
        for r in rules:
            out.append({
                "id": r.id,
                "pattern": r.pattern,
                "regex": r.regex,
                "once": r.once,
                "delay_ms": r.delay_ms,
                "device": r.device,
                "actions": [{"kind": a.kind, "params": a.params} for a in r.actions]
            })
        return out

    def delete_auto_rules(self, ids: List[str], device: Optional[str] = None) -> None:
        if not ids:
            return
        ids_set = set(str(i) for i in ids)
        with self._auto_lock:
            if device:
                rules = self._auto_rules_by_device.get(device, [])
                kept = [r for r in rules if r.id not in ids_set]
                if kept:
                    self._auto_rules_by_device[device] = kept
                else:
                    self._auto_rules_by_device.pop(device, None)
            else:
                for dev in list(self._auto_rules_by_device.keys()):
                    rules = self._auto_rules_by_device.get(dev, [])
                    kept = [r for r in rules if r.id not in ids_set]
                    if kept:
                        self._auto_rules_by_device[dev] = kept
                    else:
                        self._auto_rules_by_device.pop(dev, None)
        self._save_config()

    def export_logs_text(self, device: Optional[str] = None) -> str:
        """Export logs as a formatted string for file download"""
        lines = []
        with self._log_lock:
            for log in self._logs:
                if device and log.device != device:
                    continue
                line_text = log.text if log.text else log.hex_text
                # Format: [YYYY-MM-DD HH:MM:SS.mmm] [DEVICE] Text
                lines.append(f"[{self._format_ts(log.ts)}] [{log.device}] {line_text}")
        return "\n".join(lines)
    
    def save_logs_to_file(self, path: str, device: Optional[str] = None) -> None:
        logs = self.get_logs(device, include_hex=False)
        import os
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for l in logs:
                payload = l["text"] if l["text"] else l.get("hex", "")
                f.write(f"[{l['timestamp']}] [{l['device']}] {payload}\n")

    def set_log_options(self, packet_enabled: Optional[bool] = None, packet_timeout_ms: Optional[int] = None, log_max_lines: Optional[int] = None, device: Optional[str] = None, save: bool = True) -> None:
        if device:
            cfg = self._ensure_port_config(device)
            opts = self._log_options_by_device.get(device, {})
            if packet_enabled is not None:
                opts["packet_enabled"] = bool(packet_enabled)
            if packet_timeout_ms is not None:
                opts["packet_timeout_ms"] = max(1, int(packet_timeout_ms))
            if log_max_lines is not None:
                opts["log_max_lines"] = max(1000, int(log_max_lines))
            self._log_options_by_device[device] = opts
            cfg["log_options"] = dict(opts)
        else:
            if packet_enabled is not None:
                self._packet_enabled_default = bool(packet_enabled)
            if packet_timeout_ms is not None:
                self._packet_timeout_ms_default = max(1, int(packet_timeout_ms))
            if log_max_lines is not None:
                self._log_max_lines_default = max(1000, int(log_max_lines))
        self._recompute_log_max_lines()
        if save:
            self._save_config()

    def set_connection(self, device: Optional[str], baudrate: Optional[int] = None, data_bits: Optional[int] = None, parity: Optional[str] = None, stop_bits: Optional[Union[int, float, str]] = None, flow_control: Optional[str] = None, save: bool = True) -> None:
        if not device:
            return
        cfg = self._ensure_port_config(device)
        conn = dict(cfg.get("connection", {}))
        if baudrate is not None:
            conn["baudrate"] = int(baudrate)
        if data_bits is not None:
            conn["data_bits"] = int(data_bits)
        if parity is not None:
            conn["parity"] = str(parity)
        if stop_bits is not None:
            try:
                conn["stop_bits"] = float(stop_bits)
            except Exception:
                conn["stop_bits"] = stop_bits
        if flow_control is not None:
            conn["flow_control"] = str(flow_control)
        cfg["connection"] = conn
        if save:
            self._save_config()

    def set_console(self, device: Optional[str], auto_scroll: Optional[bool] = None, timestamp: Optional[bool] = None, line_num: Optional[bool] = None, hex_view: Optional[bool] = None, send_mode: Optional[str] = None, send_text: Optional[str] = None, append_newline: Optional[bool] = None, auto_send: Optional[bool] = None, send_interval_ms: Optional[int] = None, save: bool = True) -> None:
        if not device:
            return
        cfg = self._ensure_port_config(device)
        con = dict(cfg.get("console", {}))
        if auto_scroll is not None:
            con["auto_scroll"] = bool(auto_scroll)
        if timestamp is not None:
            con["timestamp"] = bool(timestamp)
        if line_num is not None:
            con["line_num"] = bool(line_num)
        if hex_view is not None:
            con["hex_view"] = bool(hex_view)
        if send_mode is not None:
            mode = str(send_mode).lower()
            con["send_mode"] = "hex" if mode == "hex" else "ascii"
        if send_text is not None:
            con["send_text"] = str(send_text)
        if append_newline is not None:
            con["append_newline"] = bool(append_newline)
        if auto_send is not None:
            con["auto_send"] = bool(auto_send)
        if send_interval_ms is not None:
            con["send_interval_ms"] = max(10, int(send_interval_ms))
        cfg["console"] = con
        if save:
            self._save_config()
    
    def set_auto_save(self, enabled: bool, path: str = "", device: Optional[str] = None, scope_device: Optional[str] = None, save: bool = True) -> None:
        if scope_device:
            cfg = self._ensure_port_config(scope_device)
            as_opts = self._auto_save_by_device.get(scope_device, {})
            as_opts["enabled"] = bool(enabled)
            as_opts["path"] = path or ""
            as_opts["device"] = device if device is not None else scope_device
            self._auto_save_by_device[scope_device] = as_opts
            cfg["auto_save"] = dict(as_opts)
        else:
            self._auto_save_default_enabled = bool(enabled)
            self._auto_save_default_path = path or ""
            self._auto_save_default_device = device
        if save:
            self._save_config()

    def _start_auto(self) -> None:
        self._stop_auto.clear()
        self._auto_thread = threading.Thread(target=self._auto_loop, daemon=True)
        self._auto_thread.start()

    def stop_auto(self) -> None:
        self._stop_auto.set()
        if self._auto_thread and self._auto_thread.is_alive():
            self._auto_thread.join(timeout=1.0)
        self._auto_thread = None

    def _match_rule(self, rule: AutoRule, text: str) -> bool:
        if rule.regex:
            return re.search(rule.pattern, text) is not None
        return rule.pattern in text

    def _auto_loop(self) -> None:
        fired = set()
        while not self._stop_auto.is_set():
            try:
                item = self._queue.get(timeout=0.1)
                txt, device = item
            except Exception:
                txt = None
                device = None
            if not txt:
                continue
            with self._auto_lock:
                rules = list(self._auto_rules_by_device.get(device, []))
            for r in rules:
                if r.once and r.id in fired:
                    continue
                if r.device and r.device != device:
                    continue
                if self._match_rule(r, txt):
                    now = time.time()
                    if r.interval_ms > 0:
                        if (now - r.last_fired) * 1000 < r.interval_ms:
                            continue
                    
                    logger.debug(f"Rule matched: {r.pattern} on {txt.strip()}")
                    if r.delay_ms > 0:
                        time.sleep(r.delay_ms / 1000.0)
                    for act in r.actions:
                        if act.kind == "send_serial":
                            target_dev = act.params.get("device", device)
                            self.set_mode(act.params.get("mode", "ascii"), device=target_dev)
                            data = act.params.get("data", "")
                            if act.params.get("crlf"):
                                if act.params.get("mode", "ascii") != "hex":
                                     if not data.endswith("\r\n"):
                                         data += "\r\n"
                            
                            logger.info(f"Auto-action: sending to {target_dev}")
                            # Inject log so user sees it in UI
                            self.inject_log(f">> {data}", device=target_dev)
                            self.send(data, device=target_dev)
                        elif act.kind == "run_shell":
                            cmd = act.params.get("command", "")
                            cwd = act.params.get("cwd", None)
                            logger.info(f"Auto-action: running shell {cmd}")
                            subprocess.run(cmd, shell=True, cwd=cwd)
                    
                    r.last_fired = time.time()
                    if r.once:
                        fired.add(r.id)

    async def flash(self, command: str, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
        logger.info(f"Executing flash command: {command}")
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                return {
                    "code": proc.returncode,
                    "stdout": stdout.decode("utf-8", errors="ignore") if stdout else "",
                    "stderr": stderr.decode("utf-8", errors="ignore") if stderr else ""
                }
            except asyncio.TimeoutError:
                proc.kill()
                return {"code": -1, "stdout": "", "stderr": "timeout"}
        except Exception as e:
             return {"code": -1, "stdout": "", "stderr": str(e)}
    
    def inject_log(self, text: str, device: str = "virtual") -> None:
        if self._filtered(text, device):
            return
        ts = time.time()
        with self._log_lock:
            self._logs.append(LogLine(ts=ts, text=text, device=device))
        self._queue.put((text, device))
        try:
            self._loop.call_soon_threadsafe(self._new_line_event.set)
        except RuntimeError:
             pass
    
    def _format_ts(self, ts: float) -> str:
        lt = time.localtime(ts)
        ms = int((ts - int(ts)) * 1000)
        fmt = self._timestamp_fmt
        if "%f" in fmt:
            base = time.strftime(fmt.replace("%f", "{ms}"), lt)
            return base.replace("{ms}", f"{ms:03d}")
        return time.strftime("%Y-%m-%d %H:%M:%S", lt) + f".{ms:03d}"
