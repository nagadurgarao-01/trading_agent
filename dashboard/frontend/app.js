const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${wsProtocol}//${window.location.host}/ws/telemetry`;

let socket;
let currentFilter = 'ALL';

function initWebSocket() {
  const socketStatusEl = document.getElementById("socket-status");
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log("Telemetry WebSocket Connected");
    if (socketStatusEl) {
      socketStatusEl.textContent = "● WebSocket Connected";
      socketStatusEl.className = "socket-online";
    }
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
    if (socketStatusEl) {
      socketStatusEl.textContent = "○ Reconnecting...";
      socketStatusEl.className = "socket-offline";
    }
    setTimeout(initWebSocket, 3000);
  };
}

function updateMetrics(metrics) {
  if (!metrics) return;
  const pnlEl = document.getElementById("val-pnl");
  const returnEl = document.getElementById("val-return");
  const equityEl = document.getElementById("val-equity");
  const cashEl = document.getElementById("val-cash");
  const cashPillEl = document.getElementById("val-cash-pill");
  
  const pnl = metrics.realized_pnl + (metrics.unrealized_pnl || 0);
  const pnlFormatted = pnl >= 0 ? `+₹${pnl.toFixed(2)}` : `-₹${Math.abs(pnl).toFixed(2)}`;
  
  if (pnlEl) {
    pnlEl.textContent = pnlFormatted;
    pnlEl.className = `kpi-value ${pnl >= 0 ? 'text-green' : 'text-red'}`;
  }
  
  if (returnEl) {
    returnEl.textContent = `${metrics.total_return_pct >= 0 ? '+' : ''}${metrics.total_return_pct.toFixed(2)}% Return`;
    returnEl.className = `kpi-pill ${metrics.total_return_pct >= 0 ? 'text-green' : 'text-red'}`;
  }

  const equity = metrics.portfolio_value || 0;
  const cash = metrics.cash_balance || 0;
  
  if (equityEl) {
    equityEl.textContent = `₹${equity.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  
  if (cashEl) {
    cashEl.textContent = `Available Free Margin: ₹${cash.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  if (cashPillEl && equity > 0) {
    const cashPct = Math.round((cash / equity) * 100);
    cashPillEl.textContent = `${cashPct}% Cash`;
  }

  // Update Live Readiness Progress Banner
  updateLiveReadinessProgress(metrics.total_trades || 0, pnl, metrics.avg_slippage_pct || 0);
}

function updateLiveReadinessProgress(totalTradesCount, realizedPnl, avgSlippagePct) {
  const badge = document.getElementById("readiness-status-badge");
  const progressText = document.getElementById("readiness-progress-text");
  const progressBar = document.getElementById("readiness-progress-bar");
  const tradesCountEl = document.getElementById("readiness-trades-count");
  const expectancyEl = document.getElementById("readiness-expectancy");
  const slippageEl = document.getElementById("readiness-slippage");
  const ciEl = document.getElementById("readiness-ci");

  if (!badge) return;

  const targetTrades = 50;
  const count = totalTradesCount || 0;
  const pct = Math.min(100, Math.round((count / targetTrades) * 100));

  if (tradesCountEl) tradesCountEl.textContent = `${count} / ${targetTrades} Trades`;
  if (progressText) progressText.textContent = `${count} / ${targetTrades} Trades (${pct}%)`;
  if (progressBar) progressBar.style.width = `${pct}%`;

  const expectancy = count > 0 ? (realizedPnl / count) : 0;
  if (expectancyEl) {
    expectancyEl.textContent = `₹${expectancy.toFixed(2)} / trade`;
    expectancyEl.style.color = expectancy >= 0 ? "#10b981" : "#f43f5e";
  }

  const slippage = avgSlippagePct || 0;
  if (slippageEl) {
    slippageEl.textContent = `${slippage.toFixed(4)}% (< 0.08% target)`;
    slippageEl.style.color = slippage < 0.08 ? "#10b981" : "#f43f5e";
  }

  if (count < targetTrades) {
    badge.textContent = `🔒 IN PROGRESS (${count}/${targetTrades} Trades)`;
    badge.className = "badge-evaluating";
    if (ciEl) ciEl.textContent = "Evaluating (Needs N=50)";
  } else if (expectancy >= 0 && slippage < 0.08) {
    badge.textContent = "🟢 READY FOR LIVE DEPLOYMENT";
    badge.style.color = "#10b981";
    badge.style.background = "rgba(16, 185, 129, 0.15)";
    badge.style.borderColor = "rgba(16, 185, 129, 0.35)";
    if (ciEl) ciEl.textContent = "CI Excludes 0 (Ready)";
  }
}

function getSectorForStock(sym) {
  const clean = sym.replace(".NS", "").toUpperCase();
  const map = {
    "IDEA": "Telecom",
    "YESBANK": "Banking",
    "RENUKA": "FMCG",
    "SOUTHBANK": "Banking",
    "SUZLON": "Energy",
    "NBCC": "Infra"
  };
  return map[clean] || "NSE";
}

function renderPositions(positions) {
  const tbody = document.getElementById("positions-body");
  if (!tbody) return;

  if (!positions || positions.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state">
          <div class="empty-icon">📂</div>
          <div class="empty-text">No active open positions</div>
          <div class="empty-sub">Agent is scanning NSE watchlist every 10s for R:R ≥ 1.50 setups</div>
        </td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = positions.map(pos => {
    const unPnl = pos.unrealized_pnl || 0;
    const pnlClass = unPnl >= 0 ? 'text-green' : 'text-red';
    const sector = getSectorForStock(pos.symbol);
    const entry = pos.entry_price ? `₹${pos.entry_price.toFixed(2)}` : '—';
    const ltp = pos.current_price ? `₹${pos.current_price.toFixed(2)}` : '—';
    const sl = pos.stop_loss ? `₹${pos.stop_loss.toFixed(2)}` : '—';
    const tgt = pos.target ? `₹${pos.target.toFixed(2)}` : '—';

    return `
      <tr>
        <td>
          <span class="stock-symbol">${pos.symbol}</span>
          <span class="stock-tag">${sector}</span>
        </td>
        <td><strong>${pos.qty}</strong></td>
        <td>${entry}</td>
        <td><strong>${ltp}</strong></td>
        <td style="color: var(--color-red);">${sl}</td>
        <td style="color: var(--color-green);">${tgt}</td>
        <td class="${pnlClass}" style="font-weight: 700;">
          ${unPnl >= 0 ? '+' : ''}₹${unPnl.toFixed(2)}
        </td>
        <td style="text-align: right;">
          <button class="btn-sqoff" onclick="closePosition('${pos.symbol}')">Square Off</button>
        </td>
      </tr>
    `;
  }).join('');
}

function appendLog(sender, message, level = "INFO") {
  const consoleBox = document.getElementById("console-stream");
  if (!consoleBox) return;

  const now = new Date().toLocaleTimeString('en-IN', { hour12: false });
  const entry = document.createElement("div");
  entry.className = `log-entry log-${level.toLowerCase()}`;
  
  let tagClass = "tag-agent";
  let msgClass = "";

  if (message.includes("TRADE EXECUTED") || message.includes("AUTO EXIT")) {
    tagClass = "tag-trade";
    msgClass = "log-trade-msg";
    entry.dataset.category = "TRADE";
  } else if (message.includes("RISK REJECTED") || message.includes("CIRCUIT BREAKER")) {
    tagClass = "tag-risk";
    msgClass = "log-risk-msg";
    entry.dataset.category = "RISK";
  } else if (message.includes("StrategyAgent")) {
    tagClass = "tag-strategy";
    entry.dataset.category = "STRATEGY";
  } else if (sender === "System") {
    tagClass = "tag-system";
    entry.dataset.category = "SYSTEM";
  } else if (level === "ERROR" || level === "CRITICAL") {
    tagClass = "tag-error";
    msgClass = "log-error-msg";
    entry.dataset.category = "ERROR";
  } else {
    entry.dataset.category = "ALL";
  }

  entry.innerHTML = `
    <span class="log-time">[${now}]</span>
    <span class="log-tag ${tagClass}">[${sender}]</span>
    <span class="log-msg ${msgClass}">${message}</span>
  `;

  if (currentFilter !== 'ALL' && entry.dataset.category !== currentFilter) {
    entry.style.display = 'none';
  }

  consoleBox.appendChild(entry);
  consoleBox.scrollTop = consoleBox.scrollHeight;
}

function filterLogs(filterType) {
  currentFilter = filterType;
  const chips = document.querySelectorAll(".filter-chip");
  chips.forEach(chip => {
    chip.classList.toggle("active", chip.textContent.toUpperCase() === filterType || (filterType === 'ALL' && chip.textContent === 'All'));
  });

  const entries = document.querySelectorAll(".log-entry");
  entries.forEach(entry => {
    if (filterType === 'ALL') {
      entry.style.display = 'flex';
    } else {
      entry.style.display = (entry.dataset.category === filterType) ? 'flex' : 'none';
    }
  });
}

function clearConsole() {
  const consoleBox = document.getElementById("console-stream");
  if (consoleBox) consoleBox.innerHTML = '';
}

async function triggerKillSwitch() {
  if (confirm("⚠️ Execute Emergency Kill-Switch? This will close ALL open positions immediately.")) {
    try {
      const res = await fetch("/api/kill-switch", { method: "POST" });
      const data = await res.json();
      alert(`Kill-Switch Activated: ${data.status} (${data.exited_positions_count || 0} positions closed)`);
    } catch (e) {
      alert("Error activating kill-switch: " + e);
    }
  }
}

async function closePosition(symbol) {
  if (!confirm(`Square off ${symbol}?`)) return;
  try {
    const res = await fetch(`/api/positions/${encodeURIComponent(symbol)}/close`, { method: "POST" });
    const data = await res.json();
    if (!res.ok || !["SUCCESS", "FILLED"].includes(data.status)) {
      throw new Error(data.reason || data.detail || "Position exit was rejected");
    }
  } catch (err) {
    alert(`Could not square off ${symbol}: ${err.message || err}`);
  }
}

function updateClock() {
  const clockEl = document.getElementById("live-clock");
  if (clockEl) {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString('en-IN', { hour12: false }) + " IST";
  }
}

async function loadTradingMode() {
  const badge = document.getElementById("trading-mode-badge");
  if (!badge) return;
  try {
    const res = await fetch("/api/config");
    if (!res.ok) return;
    const data = await res.json();
    if (data.env === "live") {
      badge.textContent = "⚡ LIVE MODE (" + data.broker.toUpperCase() + ")";
      badge.className = "mode-pill mode-live";
    } else {
      badge.textContent = "📄 PAPER MODE (SIMULATED)";
      badge.className = "mode-pill mode-paper";
    }
  } catch (err) {
    console.error("Failed to load mode config", err);
  }
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initWebSocket();
  updateClock();
  loadTradingMode();
  setInterval(updateClock, 1000);
});
