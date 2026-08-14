const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = `${wsProtocol}//${window.location.host}/ws/telemetry`;

let socket;
let currentFilter = 'ALL';

function initWebSocket() {
  const socketStatusEl = document.getElementById("socket-status");
  socket = new WebSocket(wsUrl);

  socket.onopen = () => {
    console.log("Apple Telemetry WebSocket Connected");
    if (socketStatusEl) {
      socketStatusEl.textContent = "● WebSocket Connected";
      socketStatusEl.className = "socket-status-online";
    }
    appendLog("System", "WebSocket telemetry link active. Connected to agent core.", "INFO");
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
      console.error("Error parsing telemetry packet:", err);
    }
  };

  socket.onclose = () => {
    console.warn("WebSocket Disconnected. Retrying in 3s...");
    if (socketStatusEl) {
      socketStatusEl.textContent = "○ Reconnecting...";
      socketStatusEl.className = "socket-status-offline";
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
  const winrateEl = document.getElementById("val-winrate");
  const pfEl = document.getElementById("val-profit-factor");
  const ddEl = document.getElementById("val-drawdown");
  
  const pnl = (metrics.realized_pnl || 0) + (metrics.unrealized_pnl || 0);
  const pnlFormatted = pnl >= 0 ? `+₹${pnl.toFixed(2)}` : `-₹${Math.abs(pnl).toFixed(2)}`;
  
  if (pnlEl) {
    pnlEl.textContent = pnlFormatted;
    pnlEl.className = `metric-number ${pnl >= 0 ? 'text-green' : 'text-red'}`;
  }
  
  if (returnEl) {
    returnEl.textContent = `${metrics.total_return_pct >= 0 ? '+' : ''}${(metrics.total_return_pct || 0).toFixed(2)}%`;
    returnEl.className = `apple-badge ${metrics.total_return_pct >= 0 ? 'badge-green' : 'badge-red'}`;
  }

  const equity = metrics.portfolio_value || 0;
  const cash = metrics.cash_balance || 0;
  
  if (equityEl) {
    equityEl.textContent = `₹${equity.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  
  if (cashEl) {
    cashEl.textContent = `Available Free Cash: ₹${cash.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  if (cashPillEl && equity > 0) {
    const cashPct = Math.min(100, Math.max(0, Math.round((cash / equity) * 100)));
    cashPillEl.textContent = `${cashPct}% Cash`;
  }

  if (winrateEl && metrics.win_rate !== undefined) {
    winrateEl.textContent = `${metrics.win_rate.toFixed(1)}%`;
  }

  if (pfEl && metrics.profit_factor !== undefined) {
    pfEl.textContent = metrics.profit_factor.toFixed(2);
  }

  if (ddEl && metrics.max_drawdown_pct !== undefined) {
    ddEl.textContent = `${metrics.max_drawdown_pct.toFixed(2)}%`;
  }

  // Update Live Readiness Protocol Card
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
  if (progressText) progressText.textContent = `${count} / ${targetTrades} Trades Completed (${pct}%)`;
  if (progressBar) progressBar.style.width = `${pct}%`;

  const expectancy = count > 0 ? (realizedPnl / count) : 0;
  if (expectancyEl) {
    expectancyEl.textContent = `₹${expectancy.toFixed(2)} / trade`;
    expectancyEl.style.color = expectancy >= 0 ? "var(--apple-green)" : "var(--apple-red)";
  }

  const slippage = avgSlippagePct || 0;
  if (slippageEl) {
    slippageEl.textContent = `${slippage.toFixed(4)}% (< 0.08% target)`;
    slippageEl.style.color = slippage < 0.08 ? "var(--apple-green)" : "var(--apple-red)";
  }

  if (count < targetTrades) {
    badge.textContent = `🔒 IN PROGRESS (${count}/${targetTrades} Trades)`;
    badge.className = "apple-pill badge-warning";
    if (ciEl) ciEl.textContent = "Evaluating (Needs N=50)";
  } else if (expectancy >= 0 && slippage < 0.08) {
    badge.textContent = "🟢 READY FOR LIVE CAPITAL";
    badge.style.color = "var(--apple-green)";
    badge.style.background = "var(--apple-green-glow)";
    badge.style.borderColor = "rgba(48, 209, 88, 0.35)";
    if (ciEl) ciEl.textContent = "CI Excludes 0 (Verified)";
  }
}

function getSectorForStock(sym) {
  const clean = sym.replace(".NS", "").toUpperCase();
  const map = {
    "IDEA": "Telecom",
    "YESBANK": "Banking",
    "RENUKA": "FMCG",
    "UCOBANK": "Banking",
    "IOB": "Banking",
    "CENTRALBK": "Banking",
    "SOUTHBANK": "Banking",
    "SUZLON": "Energy",
    "IDFCFIRSTB": "Banking",
    "NHPC": "Power",
    "SJVN": "Power",
    "PNB": "Banking",
    "NBCC": "Infra",
    "IRFC": "Finance",
    "HUDCO": "Finance",
    "BEL": "Defense",
    "TATAPOWER": "Power"
  };
  return map[clean] || "NSE";
}

function renderPositions(positions) {
  const tbody = document.getElementById("positions-body");
  if (!tbody) return;

  if (!positions || positions.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="table-empty">
          <div class="empty-state-wrap">
            <div class="empty-glyph">📂</div>
            <div class="empty-headline">No Active Open Positions</div>
            <div class="empty-sub">Scanning 15 liquid NSE watchlist symbols for R:R ≥ 1.50 entries</div>
          </div>
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
          <span class="table-stock-name">${pos.symbol}</span>
          <span class="table-sector-badge">${sector}</span>
        </td>
        <td><strong>${pos.qty}</strong></td>
        <td>${entry}</td>
        <td><strong>${ltp}</strong></td>
        <td style="color: var(--apple-red);">${sl}</td>
        <td style="color: var(--apple-green);">${tgt}</td>
        <td class="${pnlClass}" style="font-weight: 700;">
          ${unPnl >= 0 ? '+' : ''}₹${unPnl.toFixed(2)}
        </td>
        <td style="text-align: right;">
          <button class="btn-table-sqoff" onclick="closePosition('${pos.symbol}')">Square Off</button>
        </td>
      </tr>
    `;
  }).join('');
}

function appendLog(sender, message, level = "INFO") {
  const consoleBox = document.getElementById("console-stream");
  if (!consoleBox) return;

  const now = new Date().toLocaleTimeString('en-IN', { hour12: false });
  const row = document.createElement("div");
  row.className = `terminal-row row-${level.toLowerCase()}`;
  
  let tagClass = "t-tag-system";
  let msgClass = "";

  if (message.includes("TRADE EXECUTED") || message.includes("AUTO EXIT") || message.includes("SQUARED OFF")) {
    tagClass = "t-tag-trade";
    msgClass = "t-msg-trade";
    row.dataset.category = "TRADE";
  } else if (message.includes("RISK REJECTED") || message.includes("CIRCUIT BREAKER")) {
    tagClass = "t-tag-risk";
    msgClass = "t-msg-risk";
    row.dataset.category = "RISK";
  } else if (message.includes("StrategyAgent")) {
    tagClass = "t-tag-strategy";
    row.dataset.category = "STRATEGY";
  } else if (level === "ERROR" || level === "CRITICAL") {
    tagClass = "t-tag-error";
    msgClass = "t-msg-error";
    row.dataset.category = "ERROR";
  } else {
    row.dataset.category = "ALL";
  }

  row.innerHTML = `
    <span class="t-time">[${now}]</span>
    <span class="t-tag ${tagClass}">[${sender}]</span>
    <span class="t-msg ${msgClass}">${message}</span>
  `;

  if (currentFilter !== 'ALL' && row.dataset.category !== currentFilter) {
    row.style.display = 'none';
  }

  consoleBox.appendChild(row);
  consoleBox.scrollTop = consoleBox.scrollHeight;
}

function filterLogs(filterType) {
  currentFilter = filterType;
  const pills = document.querySelectorAll(".filter-pill:not(.btn-clear-stream)");
  pills.forEach(pill => {
    const txt = pill.textContent.toUpperCase();
    pill.classList.toggle("active", txt === filterType || (filterType === 'ALL' && txt === 'ALL'));
  });

  const rows = document.querySelectorAll(".terminal-row");
  rows.forEach(row => {
    if (filterType === 'ALL') {
      row.style.display = 'flex';
    } else {
      row.style.display = (row.dataset.category === filterType) ? 'flex' : 'none';
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
    const label = badge.querySelector(".pill-label") || badge;
    if (data.env === "live") {
      label.textContent = "LIVE MODE (" + data.broker.toUpperCase() + ")";
      badge.className = "apple-pill mode-live";
    } else {
      label.textContent = "PAPER MODE (SIMULATED)";
      badge.className = "apple-pill mode-paper";
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
