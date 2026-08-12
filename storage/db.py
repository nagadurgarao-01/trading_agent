import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Any, Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trading_system.db")

class StorageRepository:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Trade Intents Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trade_intents (
                    intent_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    suggested_entry REAL,
                    stop_loss REAL,
                    target REAL,
                    risk_reward_ratio REAL,
                    rationale TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            # Fills & Orders Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_fills (
                    fill_id TEXT PRIMARY KEY,
                    intent_id TEXT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    signal_price REAL,
                    fill_price REAL,
                    realized_slippage_pct REAL,
                    fee_inr REAL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY(intent_id) REFERENCES trade_intents(intent_id)
                )
            """)
            # Daily Snapshots Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE NOT NULL,
                    portfolio_value REAL,
                    cash_balance REAL,
                    realized_pnl REAL,
                    unrealized_pnl REAL,
                    open_positions_json TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            # Audit Logs Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    component TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_trade_intent(self, intent: Any):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO trade_intents 
                (intent_id, symbol, side, quantity, suggested_entry, stop_loss, target, risk_reward_ratio, rationale, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                intent.intent_id, intent.symbol, intent.side.value if hasattr(intent.side, 'value') else str(intent.side),
                intent.quantity, intent.suggested_entry, intent.stop_loss, intent.target,
                intent.risk_reward_ratio, intent.rationale, intent.created_at
            ))

    def save_order_fill(self, fill: Any):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO order_fills
                (fill_id, intent_id, symbol, side, quantity, signal_price, fill_price, realized_slippage_pct, fee_inr, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fill.fill_id, fill.intent_id, fill.symbol, fill.side, fill.quantity,
                fill.signal_price, fill.fill_price, fill.realized_slippage_pct, fill.fee_inr, fill.timestamp
            ))

    def log_audit(self, event_type: str, component: str, message: str, details: Optional[Dict[str, Any]] = None):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO audit_logs (event_type, component, message, details_json, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (event_type, component, message, json.dumps(details or {}), datetime.now().isoformat()))

db_repo = StorageRepository()
