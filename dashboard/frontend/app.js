const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${wsProtocol}//${window.location.host}/ws/telemetry`;

let socket;

function initWebSocket() {
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log("Telemetry WebSocket Connected");
    appendLog("System", "WebSocket telemetry connected to agent core.", "INFO");
  };

  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data);
      const { type, data } = payload;

      if (type === "INITIAL_STATE" || type === "METRICS_UPDATE") {
        updateMetrics(data.metrics || data);
      }
      if (type === "POSITIONS_UPDATE") {
        renderPositions(data);
      }
      if (type === "LOG_EVENT") {
        appendLog("AgentCore", data.message, data.level || "INFO");
      }
    } catch (err) {
      console.error("Error processing telemetry packet:", err);
    }
  };

  socket.onclose = () => {
    console.warn("WebSocket Disconnected. Retrying in 3s...");
    setTimeout(initWebSocket, 3000);
  };
}

function updateMetrics(metrics) {
  if (!metrics) return;
  const pnlEl = document.getElementById("val-pnl");
  const returnEl = document.getElementById("val-return");
  const equityEl = document.getElementById("val-equity");
  const cashEl = document.getElementById("val-cash");
  
  const pnl = metrics.realized_pnl + (metrics.unrealized_pnl || 0);
  pnlEl.textContent = `₹${pnl.toFixed(2)}`;
  pnlEl.className = `card-value ${pnl >= 0 ? 'val-green' : 'val-red'}`;
  
  returnEl.textContent = `${metrics.total_return_pct >= 0 ? '+' : ''}${metrics.total_return_pct.toFixed(2)}% Return`;
  equityEl.textContent = `₹${metrics.portfolio_value.toLocaleString('en-IN')}`;
  cashEl.textContent = `Cash: ₹${metrics.cash_balance.toLocaleString('en-IN')}`;
}

function renderPositions(positions) {
  const tbody = document.getElementById("positions-tbody");
  if (!positions || positions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 24px;">No active open positions</td></tr>`;
    return;
  }

  tbody.innerHTML = positions.map(pos => `
    <tr>
      <td style="font-weight:600;">${pos.symbol}</td>
      <td>${pos.qty}</td>
      <td>₹${pos.entry_price.toFixed(2)}</td>
      <td>₹${pos.current_price.toFixed(2)}</td>
      <td style="color: var(--danger);">₹${pos.stop_loss.toFixed(2)}</td>
      <td style="color: var(--success);">₹${pos.target.toFixed(2)}</td>
      <td class="${pos.unrealized_pnl >= 0 ? 'val-green' : 'val-red'}" style="font-weight:600;">
        ₹${pos.unrealized_pnl.toFixed(2)}
      </td>
      <td>
        <button class="btn-danger" style="padding: 4px 10px; font-size:11px;" onclick="closePosition('${pos.symbol}')">Square Off</button>
      </td>
    </tr>
  `).join('');
}

function appendLog(sender, message, level = "INFO") {
  const consoleBox = document.getElementById("console-stream");
  const now = new Date().toLocaleTimeString('en-US', { hour12: false });
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.innerHTML = `<span class="log-time">[${now}]</span> <span class="log-${level}">[${sender}] ${message}</span>`;
  consoleBox.appendChild(entry);
  consoleBox.scrollTop = consoleBox.scrollHeight;
}

async function triggerKillSwitch() {
  if (confirm("⚠️ Are you sure you want to execute the Emergency Kill-Switch? This will close ALL open positions immediately.")) {
    try {
      const res = await fetch("/api/kill-switch", { method: "POST" });
      const data = await res.json();
      alert(`Kill-Switch Triggered: ${data.status} (${data.exited_positions_count || 0} positions closed)`);
    } catch (e) {
      alert("Error activating kill-switch: " + e);
    }
  }
}

function updateClock() {
  const clockEl = document.getElementById("live-clock");
  if (clockEl) {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString('en-IN', { hour12: false }) + " IST";
  }
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  updateClock();
  setInterval(updateClock, 1000);
});
