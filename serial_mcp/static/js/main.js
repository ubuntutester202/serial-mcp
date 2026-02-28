// --- State ---
let state = {
    selectedPort: null,
    ports: [],
    connectedPorts: new Set(),
    logs: [],
    rules: [],
    logCursor: 0,
    wsConnected: false,
    logLimit: 360000,
    logItems: [],
    visibleItems: [],
    flushScheduled: false,
    isRebuilding: false,
    renderToken: 0,
    renderStart: 0,
    renderEnd: 0,
    virtualScheduled: false,
    rowHeight: 20, // Fixed row height from CSS
    overscan: 20,
    lastTotal: 0,
    logSizer: null,
    logContent: null,
    virtualForce: false,
    followTail: true,
    loadingConfig: false
};

let autoSendTimer = null;
let autoSendInFlight = false;

// --- API Helper ---
const api = {
    get: async (url) => (await fetch(url)).json(),
    post: async (url, data) => (await fetch(url, {
        method: 'POST', 
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })).json(),
    postForm: async (url, params) => (await fetch(url + '?' + new URLSearchParams(params), {method: 'POST'})).json(),
    del: async (url) => fetch(url, {method: 'DELETE'})
};
// --- UI References ---
const ui = {
    portList: document.getElementById('portList'),
    currentPortName: document.getElementById('currentPortName'),
    connectBtn: document.getElementById('connectBtn'),
    disconnectBtn: document.getElementById('disconnectBtn'),
    logContainer: document.getElementById('logContainer'),
    rulesList: document.getElementById('rulesList'),
    tabs: document.querySelectorAll('.tab'),
    tabContents: document.querySelectorAll('.tab-content')
};

// --- Modal Helper ---
const modal = {
    overlay: document.getElementById('modalOverlay'),
    title: document.getElementById('modalTitle'),
    message: document.getElementById('modalMessage'),
    input: document.getElementById('modalInput'),
    confirmBtn: document.getElementById('modalConfirmBtn'),
    cancelBtn: document.getElementById('modalCancelBtn'),
    resolve: null,

    show: function(title, message, defaultValue = null) {
        return new Promise((resolve) => {
            this.resolve = resolve;
            this.title.textContent = title;
            this.message.textContent = message;
            
            if (defaultValue !== null) {
                this.input.value = defaultValue;
                this.input.classList.remove('hidden');
                this.input.focus();
            } else {
                this.input.classList.add('hidden');
            }
            
            this.overlay.classList.remove('hidden');
        });
    },

    hide: function() {
        this.overlay.classList.add('hidden');
        this.input.value = '';
        this.resolve = null;
    }
};

modal.confirmBtn.onclick = () => {
    if (modal.resolve) {
        const val = modal.input.classList.contains('hidden') ? true : modal.input.value;
        modal.resolve(val);
    }
    modal.hide();
};

modal.cancelBtn.onclick = () => {
    if (modal.resolve) modal.resolve(null);
    modal.hide();
};

modal.input.onkeydown = (e) => {
    if (e.key === 'Enter') modal.confirmBtn.click();
    if (e.key === 'Escape') modal.cancelBtn.click();
};

// --- Core Logic ---

async function fetchPorts() {
    const ports = await api.get('/ports');
    state.ports = ports;
    renderPortList();
}

function renderPortList() {
    ui.portList.innerHTML = '';
    state.ports.forEach(p => {
        const isOpen = p.is_open !== undefined ? p.is_open : state.connectedPorts.has(p.device);
        if (isOpen) state.connectedPorts.add(p.device);
        
        const isBusy = p.status === 'busy';
        
        const div = document.createElement('div');
        div.className = `port-item ${state.selectedPort === p.device ? 'active' : ''} ${isOpen ? 'connected' : ''} ${isBusy ? 'busy' : ''}`;
        div.onclick = () => selectPort(p.device);
        div.innerHTML = `
            <div class="port-status"></div>
            <div class="port-info">
                <div class="port-name">${p.device} ${isBusy ? '(busy)' : ''}</div>
                <div class="port-desc">${p.description}</div>
            </div>
        `;
        ui.portList.appendChild(div);
    });
    renderRuleTargetDeviceOptions();
}

function selectPort(device) {
    state.selectedPort = device;
    ui.currentPortName.textContent = device;
    renderPortList();
    updateHeaderActions();
    filterLogsByDevice(device);
    fetchConfig(device);
}

function filterLogsByDevice(device) {
    renderLogsForSelection();
}

function updateHeaderActions() {
    if (!state.selectedPort) {
        ui.connectBtn.classList.add('hidden');
        ui.disconnectBtn.classList.add('hidden');
        return;
    }
    const isConnected = state.connectedPorts.has(state.selectedPort);
    if (isConnected) {
        ui.connectBtn.classList.add('hidden');
        ui.disconnectBtn.classList.remove('hidden');
    } else {
        ui.connectBtn.classList.remove('hidden');
        ui.disconnectBtn.classList.add('hidden');
    }
}

// --- Event Listeners for New Controls ---

document.getElementById('chkAutoScroll').onchange = (e) => {
    const enabled = e.target.checked;
    state.followTail = enabled;
    if (enabled) {
        scrollToBottom();
    }
    saveConsoleConfig();
};

const clearHandler = async () => {
    try {
        // Call backend to clear logs
        // If a port is selected, clear only that port's logs.
        // If no port is selected (viewing all), clear all logs.
        await api.postForm('/logs/clear', {device: state.selectedPort || ''});
        
        // Sync log cursor with backend to ensure we pick up new logs correctly.
        // If we cleared all, stats.total_logs will be 0.
        // If we cleared one device, stats.total_logs will be unchanged (due to base_index adjustment),
        // or effectively represent the next available index.
        const stats = await api.get('/logs/stats');
        if (stats && typeof stats.total_logs === 'number') {
            state.logCursor = stats.total_logs;
        }
    } catch (e) {
        console.error("Failed to clear backend logs", e);
    }

    ensureVirtualStructure();
    state.logContent.innerHTML = '';
    state.logItems = [];
    state.visibleItems = [];
    state.renderStart = 0;
    state.renderEnd = 0;
    state.logSizer.style.height = '0px';
    if (document.getElementById('chkAutoScroll').checked) {
        state.followTail = true;
    }
};
document.getElementById('clearLogBtn').onclick = clearHandler;
document.getElementById('clearLogBtnSettings').onclick = clearHandler;

function scrollToBottom() {
    ui.logContainer.scrollTop = ui.logContainer.scrollHeight;
}

function getLogLimit() {
    const raw = parseInt(document.getElementById('replayLines').value, 10);
    return Number.isFinite(raw) && raw > 0 ? raw : 360000;
}

function formatLocalTimestamp(date) {
    const pad = (n, len = 2) => String(n).padStart(len, '0');
    const ms = String(date.getMilliseconds()).padStart(3, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${ms}`;
}

function getLevelClass(text) {
    if (text.includes('[DEBUG]')) return 'lvl-DEBUG';
    if (text.includes('[INFO]')) return 'lvl-INFO';
    if (text.includes('[WARN]')) return 'lvl-WARN';
    if (text.includes('[ERROR]') || text.includes('[CRITICAL]')) return 'lvl-ERROR';
    return '';
}

function bytesToHex(bytes) {
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0').toUpperCase()).join(' ');
}

function normalizeHexInput(text) {
    const clean = text.replace(/0x/gi, '').replace(/[^0-9a-fA-F]/g, '');
    const pairs = clean.match(/.{1,2}/g) || [];
    return pairs.map(p => p.padEnd(2, '0').toUpperCase()).join(' ');
}

function setContainerClasses() {
    ui.logContainer.classList.toggle('show-hex', document.getElementById('chkHexView').checked);
    ui.logContainer.classList.toggle('show-ts', document.getElementById('chkTimestamp').checked);
    ui.logContainer.classList.toggle('show-ln', document.getElementById('chkLineNum').checked);
}

function ensureVirtualStructure() {
    if (state.logContent) return;
    state.logSizer = document.getElementById('logSizer');
    state.logContent = document.getElementById('logContent');
    if (!state.logSizer || !state.logContent) {
        // Fallback if HTML not updated yet (though it should be)
        ui.logContainer.innerHTML = '';
        state.logSizer = document.createElement('div');
        state.logSizer.className = 'log-sizer';
        state.logContent = document.createElement('div');
        state.logContent.className = 'log-content';
        ui.logContainer.append(state.logSizer, state.logContent);
    }
}

function measureRowHeight() {
    return 20; // Hardcoded to match CSS
}

function createLogElement(item) {
    const div = document.createElement('div');
    div.className = 'log-line';
    if (item.device) div.setAttribute('data-device', item.device);

    const textValue = item.text || '';
    const hexValue = item.hex || '';
    const levelClass = getLevelClass(textValue);
    const textClass = item.textClass ? ` ${item.textClass}` : (textValue.startsWith('>>') || hexValue.startsWith('>>') ? ' log-tx' : '');
    
    const ln = document.createElement('span');
    ln.className = 'ln';
    ln.textContent = item.index !== undefined ? item.index : '';

    const ts = document.createElement('span');
    ts.className = 'ts';
    ts.textContent = item.timestamp || '';
    const dev = document.createElement('span');
    dev.className = 'dev-tag';
    dev.textContent = item.device || '';
    const txt = document.createElement('span');
    txt.className = `txt txt-text ${levelClass}${textClass}`;
    txt.textContent = item.text || '';
    const hex = document.createElement('span');
    hex.className = `txt txt-hex ${levelClass}${textClass}`;
    hex.textContent = item.hex || '';
    div.append(ln, ts, dev, txt, hex);
    return div;
}

function appendLogLine(item) {
    state.logItems.push(item);
    const limit = getLogLimit();
    // Batch cleanup to avoid O(N) splice on every frame
    const cleanupThreshold = 1000;
    if (state.logItems.length > limit + cleanupThreshold) {
        const overflow = state.logItems.length - limit;
        state.logItems.splice(0, overflow);
    }
    
    if (!state.selectedPort || !item.device || item.device === state.selectedPort) {
        state.visibleItems.push(item);
        if (state.visibleItems.length > limit + cleanupThreshold) {
            const visibleOverflow = state.visibleItems.length - limit;
            state.visibleItems.splice(0, visibleOverflow);
        }
    }
    const autoScrollEnabled = document.getElementById('chkAutoScroll').checked;
    if (autoScrollEnabled) {
        state.followTail = true;
    }
    scheduleVirtualRender(autoScrollEnabled);
}

function collectVisibleItems() {
    const selected = state.selectedPort;
    const limit = getLogLimit();
    if (!selected) {
        state.visibleItems = state.logItems.slice(-limit);
        return state.visibleItems;
    }
    const items = [];
    for (let i = state.logItems.length - 1; i >= 0 && items.length < limit; i -= 1) {
        const item = state.logItems[i];
        if (!item.device || item.device === selected) {
            items.push(item);
        }
    }
    state.visibleItems = items.reverse();
    return state.visibleItems;
}

function renderLogsForSelection() {
    state.renderToken += 1;
    state.isRebuilding = false;
    ensureVirtualStructure();
    collectVisibleItems();
    if (document.getElementById('chkAutoScroll').checked) {
        state.followTail = true;
    }
    scheduleVirtualRender(true);
}

function scheduleVirtualRender(force = false) {
    if (force) {
        state.virtualForce = true;
    }
    if (state.virtualScheduled) return;
    state.virtualScheduled = true;
    requestAnimationFrame(() => {
        const applyForce = state.virtualForce;
        state.virtualForce = false;
        renderVirtual(applyForce);
    });
}

function renderVirtual(force = false) {
    state.virtualScheduled = false;
    ensureVirtualStructure();
    setContainerClasses();

    const total = state.visibleItems.length;
    const viewHeight = ui.logContainer.clientHeight;
    const scrollTop = ui.logContainer.scrollTop;
    
    // Update total height
    state.logSizer.style.height = `${total * state.rowHeight}px`;

    const autoScroll = document.getElementById('chkAutoScroll').checked && state.followTail;

    let start;
    if (autoScroll) {
        // If auto-scrolling, always render the last page regardless of current scrollTop
        // This prevents "lag" where scrollTop is outdated
        const itemsPerPage = Math.ceil(viewHeight / state.rowHeight);
        start = Math.max(0, total - itemsPerPage - state.overscan);
    } else {
        start = Math.max(0, Math.floor(scrollTop / state.rowHeight) - state.overscan);
    }

    const end = Math.min(total, start + Math.ceil(viewHeight / state.rowHeight) + 2 * state.overscan);
    
    // Optimization: If visible range is unchanged and not forced, skip DOM update to preserve selection
    if (!force) {
        // Strict protection for text selection:
        // If auto-scroll is OFF, and user has selected text, NEVER update the DOM content.
        // We only update the sizer height (already done above) so the scrollbar reflects new content.
        const hasSelection = window.getSelection() && window.getSelection().toString().length > 0;
        if (!autoScroll && hasSelection) {
            state.lastTotal = total;
            return;
        }
        
        // Standard optimization: if range is unchanged
        if (start === state.renderStart && end === state.renderEnd) {
            state.lastTotal = total;
            if (autoScroll) {
                scrollToBottom();
            }
            return;
        }
    }
    
    state.renderStart = start;
    state.renderEnd = end;
    state.lastTotal = total;
    
    // Position content container
    state.logContent.style.transform = `translateY(${start * state.rowHeight}px)`;
    
    state.logContent.innerHTML = '';
    const fragment = document.createDocumentFragment();
    for (let i = start; i < end; i += 1) {
        fragment.appendChild(createLogElement(state.visibleItems[i]));
    }
    state.logContent.appendChild(fragment);
    
    if (document.getElementById('chkAutoScroll').checked && state.followTail) {
        scrollToBottom();
    }
}

// --- Actions ---

ui.connectBtn.onclick = async () => {
    if (!state.selectedPort) return;
    try {
        await api.postForm('/open', {
            device: state.selectedPort,
            baudrate: document.getElementById('baudRate').value,
            parity: document.getElementById('parity').value,
            bytesize: document.getElementById('dataBits').value,
            stopbits: document.getElementById('stopBits').value,
            flow: document.getElementById('flowControl').value
        });
        state.connectedPorts.add(state.selectedPort);
        await fetchPorts();
        updateHeaderActions();
    } catch (e) {
        alert('Connection failed: ' + e);
    }
};

ui.disconnectBtn.onclick = async () => {
    if (!state.selectedPort) return;
    try {
        await api.postForm('/close', {device: state.selectedPort});
        state.connectedPorts.delete(state.selectedPort);
        await fetchPorts();
        updateHeaderActions();
        stopAutoSend();
    } catch (e) {
        alert('Disconnect failed: ' + e);
    }
};

document.getElementById('refreshBtn').onclick = fetchPorts;

async function sendOnce(isAuto = false) {
    if (!state.selectedPort) {
        if (!isAuto) alert('Select a port first');
        stopAutoSend();
        return;
    }
    const input = document.getElementById('sendInput');
    const mode = document.getElementById('sendMode').value;
    const text = input.value;
    const appendNewline = document.getElementById('chkAppendNewline').checked;
    
    let payloads = [];
    
    if (mode === 'ascii') {
        // Split by newline to support multi-line commands
        // If text is empty, send nothing (or maybe empty string?)
        if (!text) return;
        
        const lines = text.split('\n');
        for (let i = 0; i < lines.length; i++) {
            // If the last line is empty (trailing newline), ignore it unless it's the only line
            if (i === lines.length - 1 && lines[i] === '' && lines.length > 1) continue;
            
            let line = lines[i];
            // Handle CRLF replacement for the line content itself if it had \r (unlikely with split \n)
            if (appendNewline) {
                line += '\r\n';
            }
            payloads.push(line);
        }
    } else {
        const normalized = normalizeHexInput(text);
        let payload = normalized;
        if (appendNewline && text) {
            const suffix = normalized ? ' ' : '';
            payload = `${normalized}${suffix}0D 0A`;
        }
        payloads.push(payload);
    }

    for (const payload of payloads) {
        const res = await api.postForm('/send', {
            data: payload,
            mode: mode,
            device: state.selectedPort
        });
        
        if (res.ok === false) {
            if (!isAuto) alert('Send failed: ' + (res.error || 'Unknown error'));
            stopAutoSend();
            break; // Stop sending subsequent lines on error
        }
        
        // Small delay between lines to ensure order/processing
        if (payloads.length > 1) {
            await new Promise(r => setTimeout(r, 10)); 
        }
    }
}

function startAutoSend() {
    const interval = parseInt(document.getElementById('sendIntervalMs').value, 10);
    const delay = Number.isFinite(interval) && interval > 0 ? interval : 1000;
    stopAutoSend(false);
    autoSendTimer = setInterval(async () => {
        if (autoSendInFlight) return;
        autoSendInFlight = true;
        try {
            await sendOnce(true);
        } finally {
            autoSendInFlight = false;
        }
    }, delay);
}

function stopAutoSend(uncheck = true) {
    if (autoSendTimer) {
        clearInterval(autoSendTimer);
        autoSendTimer = null;
    }
    if (uncheck) {
        document.getElementById('chkAutoSend').checked = false;
    }
}

document.getElementById('sendBtn').onclick = () => sendOnce(false);

// Allow Enter key to send (Shift+Enter for newline)
document.getElementById('sendInput').onkeydown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        document.getElementById('sendBtn').click();
    }
};

// --- Rules ---

function renderRuleTargetDeviceOptions() {
    const select = document.getElementById('ruleTargetDevice');
    if (!select) return;
    const currentValue = select.value;
    select.innerHTML = '';
    const follow = document.createElement('option');
    follow.value = '';
    follow.textContent = 'Follow Trigger Port';
    select.appendChild(follow);
    state.ports.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.device;
        opt.textContent = p.device;
        select.appendChild(opt);
    });
    if (currentValue && Array.from(select.options).some(o => o.value === currentValue)) {
        select.value = currentValue;
    } else {
        select.value = '';
    }
}

function updateRuleActionUi() {
    const kind = document.getElementById('ruleActionType').value;
    const isSend = kind === 'send_serial';
    document.getElementById('ruleSendModeGroup').classList.toggle('hidden', !isSend);
    document.getElementById('ruleTargetDeviceGroup').classList.toggle('hidden', !isSend);
    document.getElementById('ruleActionData').placeholder = isSend ? 'Response' : 'Command';
}

async function fetchRules() {
    if (!state.selectedPort) {
        state.rules = [];
        renderRules();
        return;
    }
    const query = `?device=${encodeURIComponent(state.selectedPort)}`;
    const rules = await api.get(`/rules${query}`);
    state.rules = rules;
    renderRules();
}

function renderRules() {
    ui.rulesList.innerHTML = '';
    if (state.rules.length === 0) {
        ui.rulesList.innerHTML = '<div class="empty-state">No active rules</div>';
        updateRuleSelection();
        return;
    }
    state.rules.forEach((r, i) => {
        const div = document.createElement('div');
        div.className = 'rule-item';
        const actionDesc = r.actions.map(a => {
            if (a.kind === 'send_serial') {
                const mode = (a.params && a.params.mode || 'ascii').toLowerCase() === 'hex' ? 'HEX' : 'TXT';
                const data = a.params && a.params.data !== undefined ? a.params.data : '';
                const crlf = a.params && a.params.crlf ? '+CRLF' : '';
                const target = a.params && a.params.device ? a.params.device : 'Rule Port';
                return `Send "${data}"${crlf} (${mode} via ${target})`;
            }
            if (a.kind === 'run_shell') {
                const cmd = a.params && a.params.command ? a.params.command : '';
                return `Run \`${cmd}\``;
            }
            return a.kind || '';
        }).join(', ');
        
        const intervalInfo = r.interval_ms > 0 ? ` • Interval ${r.interval_ms}ms` : '';

        div.innerHTML = `
            <div style="margin-right: 12px; display: flex; align-items: center;">
                <input type="checkbox" class="rule-chk" value="${r.id || ''}" onchange="updateRuleSelection()">
            </div>
            <div class="rule-info">
                <div class="rule-pattern">${r.pattern}</div>
                <div class="rule-meta">
                    ${r.once ? 'Once' : 'Loop'} • ${r.regex ? 'Regex' : 'Text'} • Delay ${r.delay_ms}ms${intervalInfo} • Device: ${r.device || 'All'}
                </div>
                <div class="rule-meta">→ ${actionDesc}</div>
            </div>
            <div class="rule-actions">
                <button class="sm-btn primary" onclick="triggerRule(${i})" title="Manual Trigger">Send</button>
            </div>
        `;
        ui.rulesList.appendChild(div);
    });
    updateRuleSelection();
}

window.updateRuleSelection = () => {
    const chks = document.querySelectorAll('.rule-chk');
    const checked = Array.from(chks).filter(c => c.checked);
    const btn = document.getElementById('deleteSelectedRulesBtn');
    if (btn) {
        btn.disabled = checked.length === 0;
        btn.textContent = checked.length > 0 ? `Delete Selected (${checked.length})` : 'Delete Selected';
    }
};

window.triggerRule = async (index) => {
    const rule = state.rules[index];
    if (!rule) return;
    
    // Visual feedback
    // Note: The button is inside the last child div of the rule item
    const ruleItem = ui.rulesList.children[index];
    if (!ruleItem) return;
    const btn = ruleItem.querySelector('button');
    if (!btn) return;
    
    const originalText = btn.textContent;
    btn.textContent = '...';
    btn.disabled = true;

    try {
        if (rule.delay_ms > 0) {
            await new Promise(r => setTimeout(r, rule.delay_ms));
        }

        for (const act of rule.actions) {
            if (act.kind === 'send_serial') {
                let data = act.params.data !== undefined ? act.params.data : '';
                const mode = act.params.mode || 'ascii';
                
                // Handle CRLF for manual trigger locally
                if (act.params.crlf && mode !== 'hex') {
                    if (!data.endsWith('\r\n')) data += '\r\n';
                }
                
                const target = act.params.device || rule.device || state.selectedPort;
                if (!target) {
                    console.warn('Skipping action: no target device');
                    continue;
                }
                
                const res = await api.postForm('/send', {
                    data: data,
                    mode: mode,
                    device: target
                });
                
                if (res.ok) {
                     appendLogLine({
                        timestamp: formatLocalTimestamp(new Date()),
                        device: target,
                        text: `>> ${data.replace(/[\r\n]+$/, '')} [Manual]`,
                        hex: mode === 'hex' ? `>> ${data}` : '',
                        textClass: 'log-tx'
                    });
                } else {
                    console.error("Manual send failed", res);
                    alert(`Send failed: ${res.error}`);
                }
            } else if (act.kind === 'run_shell') {
                console.warn("Shell command manual trigger not implemented");
            }
        }
    } catch (e) {
        alert('Trigger error: ' + e);
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
};

function parseRulesJson(text) {
    const data = JSON.parse(text);
    if (Array.isArray(data)) return data;
    if (data && typeof data === 'object' && Array.isArray(data.rules)) return data.rules;
    throw new Error('Invalid rules JSON');
}

function normalizeRuleForImport(rule) {
    const out = {
        pattern: rule && rule.pattern !== undefined ? String(rule.pattern) : '',
        regex: rule && rule.regex !== undefined ? Boolean(rule.regex) : true,
        once: rule && rule.once !== undefined ? Boolean(rule.once) : true,
        delay_ms: Number.isFinite(Number(rule && rule.delay_ms)) ? Number(rule.delay_ms) : 0,
        device: rule && rule.device ? String(rule.device) : (state.selectedPort || null),
        actions: []
    };
    const actions = rule && Array.isArray(rule.actions) ? rule.actions : [];
    actions.forEach(a => {
        if (!a || !a.kind) return;
        const kind = String(a.kind);
        const params = a.params && typeof a.params === 'object' ? a.params : {};
        if (kind === 'send_serial') {
            const mode = String(params.mode || 'ascii').toLowerCase() === 'hex' ? 'hex' : 'ascii';
            const data = params.data !== undefined ? String(params.data) : '';
            const device = params.device ? String(params.device) : '';
            const crlf = params.crlf !== undefined ? Boolean(params.crlf) : false;
            const sendParams = {data, mode, crlf};
            if (device) sendParams.device = device;
            out.actions.push({kind, params: sendParams});
        } else if (kind === 'run_shell') {
            const command = params.command !== undefined ? String(params.command) : '';
            const shellParams = {command};
            if (params.cwd) shellParams.cwd = String(params.cwd);
            out.actions.push({kind, params: shellParams});
        }
    });
    return out;
}

async function importRulesFromText(text) {
    let rules;
    try {
        rules = parseRulesJson(text);
    } catch (e) {
        alert('Invalid JSON format');
        return;
    }
    const normalized = rules.map(normalizeRuleForImport).filter(r => r.pattern || r.actions.length > 0);
    const missingDevice = normalized.some(r => !r.device);
    if (missingDevice) {
        alert('Please select a port or include device in rules JSON');
        return;
    }
    for (const r of normalized) {
        await api.post('/rules', r);
    }
    fetchRules();
    alert(`Imported ${normalized.length} rules`);
}

function exportRulesToJson() {
    const payload = JSON.stringify(state.rules || [], null, 2);
    document.getElementById('rulesJsonInput').value = payload;
    const blob = new Blob([payload], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const deviceName = state.selectedPort ? state.selectedPort.replace(/[\\/:*?"<>|]/g, '_') : 'rules';
    a.href = url;
    a.download = `auto_rules_${deviceName}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

document.getElementById('ruleActionType').onchange = updateRuleActionUi;
updateRuleActionUi();

document.getElementById('importRulesBtn').onclick = async () => {
    const text = document.getElementById('rulesJsonInput').value.trim();
    if (!text) {
        alert('Please paste JSON');
        return;
    }
    await importRulesFromText(text);
};

document.getElementById('openRulesFileBtn').onclick = () => {
    document.getElementById('rulesJsonFile').click();
};

document.getElementById('rulesJsonFile').onchange = async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const text = await file.text();
    document.getElementById('rulesJsonInput').value = text;
    await importRulesFromText(text);
    e.target.value = '';
};

document.getElementById('exportRulesBtn').onclick = exportRulesToJson;

document.getElementById('addRuleBtn').onclick = async () => {
    const kind = document.getElementById('ruleActionType').value;
    const data = document.getElementById('ruleActionData').value;
    const params = kind === 'send_serial' ? {data, mode: document.getElementById('ruleSendMode').value, crlf: document.getElementById('ruleCRLF').checked} : {command: data};
    if (kind === 'send_serial') {
        const targetDevice = document.getElementById('ruleTargetDevice').value;
        if (targetDevice) {
            params.device = targetDevice;
        }
    }
    
    await api.post('/rules', {
        pattern: document.getElementById('rulePattern').value,
        regex: true, // Defaulting to regex for power users
        once: document.getElementById('ruleOnce').checked,
        delay_ms: parseInt(document.getElementById('ruleDelay').value) || 0,
        interval_ms: 0,
        device: state.selectedPort || null, 
        actions: [{kind, params}]
    });
    fetchRules();
    alert('Rule added');
};

document.getElementById('clearRuleFormBtn').onclick = () => {
    document.getElementById('rulePattern').value = '';
    document.getElementById('ruleActionType').value = 'send_serial';
    document.getElementById('ruleActionData').value = '';
    document.getElementById('ruleSendMode').value = 'ascii';
    document.getElementById('ruleCRLF').checked = false;
    document.getElementById('ruleTargetDevice').value = '';
    document.getElementById('ruleDelay').value = '0';
    document.getElementById('ruleOnce').checked = true;
    updateRuleActionUi();
};

document.getElementById('clearRulesBtn').onclick = async () => {
    // Reusing modal for confirm, passing null as default value implies text input, so we use a trick or just simple confirm
    // Actually our modal supports hiding input if default is null? No, code says:
    // if (defaultValue !== null) ... else ... add('hidden')
    // So if we pass null, it's a confirm dialog!
    const confirmed = await modal.show("Clear Rules", "Are you sure you want to clear all rules?", null);
    if(confirmed) {
        if (state.selectedPort) {
            const query = `?device=${encodeURIComponent(state.selectedPort)}`;
            await api.del(`/rules${query}`);
        }
        fetchRules();
    }
};

document.getElementById('deleteSelectedRulesBtn').onclick = async () => {
    const chks = document.querySelectorAll('.rule-chk:checked');
    if (chks.length === 0) return;
    
    const confirmed = await modal.show("Delete Rules", `Delete ${chks.length} selected rules?`, null);
    if (confirmed) {
        const ids = Array.from(chks).map(c => c.value);
        const query = state.selectedPort ? `?device=${encodeURIComponent(state.selectedPort)}` : '';
        await api.post(`/rules/delete${query}`, ids);
        fetchRules();
    }
};

// --- Tabs ---
ui.tabs.forEach(tab => {
    tab.onclick = () => {
        ui.tabs.forEach(t => t.classList.remove('active'));
        ui.tabContents.forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
        if (tab.dataset.tab === 'console') {
            scheduleVirtualRender(true);
        }
    };
});

// --- Logs & Filters ---
document.getElementById('applyFilterBtn').onclick = () => {
    const raw = document.getElementById('filterInput').value.trim();
    const device = state.selectedPort ? `&device=${encodeURIComponent(state.selectedPort)}` : '';
    api.post(`/filters?regex=true${device}`, raw ? raw.split(',') : []);
};

function updateTimestampDisplay() {
    setContainerClasses();
    scheduleVirtualRender(true);
    saveConsoleConfig();
}

function updateLineNumDisplay() {
    setContainerClasses();
    scheduleVirtualRender(true);
    saveConsoleConfig();
}

function updateHexDisplay() {
    setContainerClasses();
    scheduleVirtualRender(true);
    saveConsoleConfig();
}

function applyLogOptions() {
    const packetEnabled = document.getElementById('chkPacketize').checked;
    const packetTimeout = parseInt(document.getElementById('packetTimeoutMs').value, 10) || 20;
    const logMaxLines = getLogLimit();
    state.logLimit = logMaxLines;
    document.getElementById('packetTimeoutMs').disabled = !packetEnabled;
    api.post('/logs/options', {
        packet_enabled: packetEnabled,
        packet_timeout_ms: packetTimeout,
        log_max_lines: logMaxLines,
        device: state.selectedPort || null
    });
    if (state.logItems.length > logMaxLines) {
        const overflow = state.logItems.length - logMaxLines;
        state.logItems.splice(0, overflow);
    }
    renderLogsForSelection();
}

document.getElementById('chkTimestamp').onchange = updateTimestampDisplay;
document.getElementById('chkLineNum').onchange = updateLineNumDisplay;
document.getElementById('chkHexView').onchange = updateHexDisplay;
document.getElementById('chkPacketize').onchange = applyLogOptions;
document.getElementById('packetTimeoutMs').onchange = applyLogOptions;
document.getElementById('replayLines').onchange = applyLogOptions;
document.getElementById('sendMode').onchange = saveConsoleConfig;
document.getElementById('chkAppendNewline').onchange = saveConsoleConfig;
document.getElementById('sendInput').onchange = saveConsoleConfig;

document.getElementById('chkAutoSend').onchange = (e) => {
    if (e.target.checked) startAutoSend();
    else stopAutoSend();
    saveConsoleConfig();
};

document.getElementById('sendIntervalMs').onchange = () => {
    if (document.getElementById('chkAutoSend').checked) startAutoSend();
    saveConsoleConfig();
};

document.getElementById('resetConnDefaultsBtn').onclick = () => {
    document.getElementById('baudRate').value = '115200';
    document.getElementById('dataBits').value = '8';
    document.getElementById('parity').value = 'N';
    document.getElementById('stopBits').value = '1';
    document.getElementById('flowControl').value = 'none';
    saveConnectionConfig();
};

document.getElementById('baudRate').onchange = saveConnectionConfig;
document.getElementById('dataBits').onchange = saveConnectionConfig;
document.getElementById('parity').onchange = saveConnectionConfig;
document.getElementById('stopBits').onchange = saveConnectionConfig;
document.getElementById('flowControl').onchange = saveConnectionConfig;

document.getElementById('applyAutoSaveBtn').onclick = async () => {
    const enabled = document.getElementById('chkAutoSave').checked;
    const path = document.getElementById('autoSavePath').value.trim();
    if (enabled && !path) {
        alert('Please provide a file path for auto-save.');
        document.getElementById('chkAutoSave').checked = false;
        return;
    }
    await api.post('/logs/auto-save', {
        enabled,
        path,
        device: state.selectedPort || null
    });
};

document.getElementById('chkAutoSave').onchange = () => {
    if (!document.getElementById('chkAutoSave').checked) {
        api.post('/logs/auto-save', {enabled: false, path: '', device: state.selectedPort || null});
    }
};

document.getElementById('saveLogBtn').onclick = async () => {
    const path = await modal.show("Save Log to Server", "Server-side path (absolute):", "D:/logs/session.log");
    if(path) {
        const res = await api.postForm('/logs/save', {path, device: state.selectedPort || ''});
        if(res.ok) alert('Saved to server!'); else alert('Error: ' + res.error);
    }
};

document.getElementById('downloadLogBtn').onclick = () => {
    const device = state.selectedPort || '';
    window.location.href = `/logs/download?device=${encodeURIComponent(device)}`;
};

let pollTimer = null;

async function pollLogs() {
    if (state.wsConnected) return;
    try {
        const res = await api.get(`/logs?start_index=${state.logCursor}&limit=2000`);
        if (res && Array.isArray(res.items)) {
            if (res.items.length > 500) {
                // Chunk processing for large payloads
                const chunkProcess = (items) => {
                    if (items.length === 0) return;
                    const chunk = items.splice(0, 500);
                    chunk.forEach(item => appendLogLine(item));
                    if (items.length > 0) {
                        requestAnimationFrame(() => chunkProcess(items));
                    }
                };
                chunkProcess([...res.items]); // Copy array to avoid issues if we modify original
            } else {
                res.items.forEach(item => appendLogLine(item));
            }
            
            if (typeof res.next_index === 'number') {
                state.logCursor = res.next_index;
            } else {
                state.logCursor += res.items.length;
            }
        }
    } catch (e) {
    }
}

function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(pollLogs, 500);
}

function stopPolling() {
    if (!pollTimer) return;
    clearInterval(pollTimer);
    pollTimer = null;
}

// --- WebSocket ---
const wsProtocol = location.protocol === 'https:' ? 'wss' : 'ws';
const wsBaseUrl = location.host ? `${wsProtocol}://${location.host}/ws/logs` : null;
let ws;

function connectWs() {
    if (!wsBaseUrl) {
        startPolling();
        return;
    }
    // Pass current cursor to resume/start from correct position
    const url = `${wsBaseUrl}?start_index=${state.logCursor}`;
    ws = new WebSocket(url);
    ws.onopen = () => {
        state.wsConnected = true;
        stopPolling();
    };
    
    const MAX_BUFFER_SIZE = 5000;
    let messageBuffer = [];
    let bufferTimeout = null;

    const flushBuffer = () => {
        if (messageBuffer.length === 0) return;
        
        // Batch append to avoid layout thrashing logic inside appendLogLine
        // We'll just push all and then check limits once
        const limit = getLogLimit();
        const autoScrollEnabled = document.getElementById('chkAutoScroll').checked;

        // Optimized bulk push
        // Note: state.logItems.push(...messageBuffer) might stack overflow if buffer is huge
        for (const item of messageBuffer) {
            state.logItems.push(item);
            if (typeof item.index === 'number') {
                state.logCursor = Math.max(state.logCursor, item.index + 1);
            }
        }
        
        // Bulk cleanup
        const cleanupThreshold = 1000;
        if (state.logItems.length > limit + cleanupThreshold) {
            const overflow = state.logItems.length - limit;
            state.logItems.splice(0, overflow);
        }

        // Handle visibility for current port
        const selected = state.selectedPort;
        if (!selected) {
             // If showing all ports, visible items are just the tail of logItems
             // This is an optimization assumption: if no filter, visible == logs
             // But we need to be careful if we had filtering logic before. 
             // Current logic in appendLogLine:
             // if (!state.selectedPort || !item.device || item.device === state.selectedPort)
             
             // For bulk add, we filter and push
             const newVisible = messageBuffer.filter(item => !item.device || item.device === selected); // selected is null here
             // Actually if selected is null, all are visible
             for (const item of messageBuffer) {
                 state.visibleItems.push(item);
             }
        } else {
             for (const item of messageBuffer) {
                 if (!item.device || item.device === selected) {
                     state.visibleItems.push(item);
                 }
             }
        }
        
        // Bulk visible cleanup
        if (state.visibleItems.length > limit + cleanupThreshold) {
             const visibleOverflow = state.visibleItems.length - limit;
             state.visibleItems.splice(0, visibleOverflow);
        }

        messageBuffer = [];
        bufferTimeout = null;

        if (autoScrollEnabled) {
            state.followTail = true;
        }
        scheduleVirtualRender(autoScrollEnabled);
    };

    ws.onmessage = (ev) => {
        const item = JSON.parse(ev.data);
        messageBuffer.push(item);
        
        // Flush if buffer gets too big immediately
        if (messageBuffer.length >= 2000) {
            if (bufferTimeout) cancelAnimationFrame(bufferTimeout);
            flushBuffer();
        } else if (!bufferTimeout) {
            bufferTimeout = requestAnimationFrame(flushBuffer);
        }
    };
    
    ws.onerror = () => {
        state.wsConnected = false;
        startPolling();
    };
    ws.onclose = () => {
        state.wsConnected = false;
        startPolling();
        setTimeout(connectWs, 1000);
    };
}
async function initLogState() {
    try {
        const stats = await api.get('/logs/stats');
        if (stats && typeof stats.total_logs === 'number') {
            // If total logs > 2000, start from end - 2000
            // This prevents fetching 360k logs on refresh
            const start = Math.max(0, stats.total_logs - 2000);
            state.logCursor = start;
            console.log(`Initialized log cursor at ${start} (total: ${stats.total_logs})`);
        }
    } catch (e) {
        console.warn("Failed to fetch log stats, starting from 0", e);
    }
    connectWs();
}

initLogState();

async function fetchConfig(device = null) {
    state.loadingConfig = true;
    try {
        const query = device ? `?device=${encodeURIComponent(device)}` : '';
        const config = await api.get(`/config${query}`);
        
        // Filters
        const filtersValue = config.filters && config.filters.length > 0 ? config.filters.join(',') : '';
        document.getElementById('filterInput').value = filtersValue;
        
        // Log Options
        if (config.log_options) {
            const opts = config.log_options;
            if (opts.packet_enabled !== undefined) document.getElementById('chkPacketize').checked = opts.packet_enabled;
            if (opts.packet_timeout_ms !== undefined) document.getElementById('packetTimeoutMs').value = opts.packet_timeout_ms;
            if (opts.log_max_lines !== undefined) {
                document.getElementById('replayLines').value = opts.log_max_lines;
                state.logLimit = opts.log_max_lines;
            }
            document.getElementById('packetTimeoutMs').disabled = !document.getElementById('chkPacketize').checked;
        }
        
        // Auto Save
        if (config.auto_save) {
            const as = config.auto_save;
            if (as.enabled !== undefined) document.getElementById('chkAutoSave').checked = as.enabled;
            if (as.path !== undefined) document.getElementById('autoSavePath').value = as.path;
        } else {
            document.getElementById('chkAutoSave').checked = false;
            document.getElementById('autoSavePath').value = '';
        }
        
        // Rules
        if (config.rules) {
            state.rules = config.rules;
            renderRules();
        }
        
        // Connection
        if (config.connection) {
            const conn = config.connection;
            if (conn.baudrate !== undefined) document.getElementById('baudRate').value = String(conn.baudrate);
            if (conn.data_bits !== undefined) document.getElementById('dataBits').value = String(conn.data_bits);
            if (conn.parity !== undefined) document.getElementById('parity').value = String(conn.parity);
            if (conn.stop_bits !== undefined) document.getElementById('stopBits').value = String(conn.stop_bits);
            if (conn.flow_control !== undefined) document.getElementById('flowControl').value = String(conn.flow_control);
        }

        // Console
        if (config.console) {
            const con = config.console;
            if (con.auto_scroll !== undefined) document.getElementById('chkAutoScroll').checked = con.auto_scroll;
            if (con.timestamp !== undefined) document.getElementById('chkTimestamp').checked = con.timestamp;
            if (con.line_num !== undefined) document.getElementById('chkLineNum').checked = con.line_num;
            if (con.hex_view !== undefined) document.getElementById('chkHexView').checked = con.hex_view;
            if (con.send_mode !== undefined) document.getElementById('sendMode').value = con.send_mode;
            if (con.send_text !== undefined) document.getElementById('sendInput').value = con.send_text;
            if (con.append_newline !== undefined) document.getElementById('chkAppendNewline').checked = con.append_newline;
            if (con.auto_send !== undefined) document.getElementById('chkAutoSend').checked = con.auto_send;
            if (con.send_interval_ms !== undefined) document.getElementById('sendIntervalMs').value = con.send_interval_ms;
            updateTimestampDisplay();
            updateLineNumDisplay();
            updateHexDisplay();
            if (document.getElementById('chkAutoSend').checked && state.selectedPort && state.connectedPorts.has(state.selectedPort)) {
                startAutoSend();
            } else {
                stopAutoSend(false);
            }
        }

    } catch (e) {
        console.error("Failed to fetch config", e);
    } finally {
        state.loadingConfig = false;
    }
}

function saveConnectionConfig() {
    if (!state.selectedPort || state.loadingConfig) return;
    api.post('/config/connection', {
        device: state.selectedPort,
        baudrate: parseInt(document.getElementById('baudRate').value, 10),
        data_bits: parseInt(document.getElementById('dataBits').value, 10),
        parity: document.getElementById('parity').value,
        stop_bits: document.getElementById('stopBits').value,
        flow_control: document.getElementById('flowControl').value
    });
}

function saveConsoleConfig() {
    if (!state.selectedPort || state.loadingConfig) return;
    api.post('/config/console', {
        device: state.selectedPort,
        auto_scroll: document.getElementById('chkAutoScroll').checked,
        timestamp: document.getElementById('chkTimestamp').checked,
        line_num: document.getElementById('chkLineNum').checked,
        hex_view: document.getElementById('chkHexView').checked,
        send_mode: document.getElementById('sendMode').value,
        send_text: document.getElementById('sendInput').value,
        append_newline: document.getElementById('chkAppendNewline').checked,
        auto_send: document.getElementById('chkAutoSend').checked,
        send_interval_ms: parseInt(document.getElementById('sendIntervalMs').value, 10)
    });
}

// --- View Settings (LocalStorage) ---
function loadViewSettings() {
    const get = (k) => localStorage.getItem('serial_mcp_' + k);
    const setChk = (id, k) => {
        const v = get(k);
        if (v !== null) document.getElementById(id).checked = v === 'true';
    };
    
    setChk('chkTimestamp', 'show_ts');
    setChk('chkLineNum', 'show_ln');
    setChk('chkHexView', 'show_hex');
    setChk('chkAutoScroll', 'auto_scroll');
    
    // Update state based on loaded settings
    updateTimestampDisplay();
    updateLineNumDisplay();
    updateHexDisplay();
    if (document.getElementById('chkAutoScroll').checked) {
        state.followTail = true;
    }
    // Force a render pass to ensure correct scroll position
    scheduleVirtualRender(true);
}

document.getElementById('chkTimestamp').addEventListener('change', (e) => saveViewSetting('show_ts', e.target.checked));
document.getElementById('chkLineNum').addEventListener('change', (e) => saveViewSetting('show_ln', e.target.checked));
document.getElementById('chkHexView').addEventListener('change', (e) => saveViewSetting('show_hex', e.target.checked));
document.getElementById('chkAutoScroll').addEventListener('change', (e) => saveViewSetting('auto_scroll', e.target.checked));

function saveViewSetting(key, val) {
    localStorage.setItem('serial_mcp_' + key, val);
}

// --- Init ---
fetchPorts();
loadViewSettings();
fetchConfig();
// fetchRules(); // Handled by fetchConfig
// applyLogOptions(); // Do not overwrite on start, fetchConfig handles loading
ui.logContainer.addEventListener('scroll', () => {
    if (document.getElementById('chkAutoScroll').checked) {
        const atBottom = ui.logContainer.scrollTop + ui.logContainer.clientHeight >= ui.logContainer.scrollHeight - 2;
        state.followTail = atBottom;
    }
    scheduleVirtualRender();
});
window.addEventListener('resize', () => scheduleVirtualRender(true));
// Poll for new ports every 5s
setInterval(fetchPorts, 5000);

// --- Context Menu ---
const ctxMenu = document.getElementById('logContextMenu');
const ctxCopy = document.getElementById('ctxCopy');
const ctxSelectAll = document.getElementById('ctxSelectAll');

document.addEventListener('click', (e) => {
    if (e.target.closest('.context-menu')) return;
    if (ctxMenu.classList.contains('visible')) {
        ctxMenu.classList.remove('visible');
    }
});

ui.logContainer.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    const x = e.clientX;
    const y = e.clientY;
    
    // Boundary check
    const menuWidth = 150;
    const menuHeight = 80;
    const winWidth = window.innerWidth;
    const winHeight = window.innerHeight;
    
    let left = x;
    let top = y;
    
    if (left + menuWidth > winWidth) left = winWidth - menuWidth;
    if (top + menuHeight > winHeight) top = winHeight - menuHeight;
    
    ctxMenu.style.left = `${left}px`;
    ctxMenu.style.top = `${top}px`;
    ctxMenu.classList.add('visible');
});

ctxCopy.onclick = async () => {
    const selection = window.getSelection();
    const text = selection ? selection.toString() : '';
    if (text) {
        try {
            await navigator.clipboard.writeText(text);
        } catch (e) {
            console.warn('Clipboard API failed, falling back to execCommand', e);
            try {
                document.execCommand('copy');
            } catch (e2) {
                console.error('Copy failed', e2);
            }
        }
    }
    ctxMenu.classList.remove('visible');
};

ctxSelectAll.onclick = () => {
    if (!state.logContent) return;
    const range = document.createRange();
    range.selectNodeContents(state.logContent);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    ctxMenu.classList.remove('visible');
};

const supportModal = document.getElementById('supportModal');
const supportAuthorBtn = document.getElementById('supportAuthorBtn');
const supportCloseBtn = document.getElementById('supportCloseBtn');

supportAuthorBtn.onclick = () => {
    supportModal.classList.remove('hidden');
};

supportCloseBtn.onclick = () => {
    supportModal.classList.add('hidden');
};

supportModal.onclick = (e) => {
    if (e.target === supportModal) {
        supportModal.classList.add('hidden');
    }
};
