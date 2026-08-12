import uuid
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional

class SystemState(Enum):
    STOPPED = "STOPPED"
    PRE_MARKET = "PRE_MARKET"
    MARKET_OPEN = "MARKET_OPEN"
    NO_NEW_ENTRIES = "NO_NEW_ENTRIES"
    SQUARE_OFF = "SQUARE_OFF"
    CLOSED = "CLOSED"

class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass(frozen=True)
class TradeIntent:
    intent_id: str = field(default_factory=lambda: f"INT-{uuid.uuid4().hex[:8].upper()}")
    symbol: str = ""
    side: Side = Side.BUY
    quantity: int = 0
    suggested_entry: float = 0.0
    stop_loss: float = 0.0
    target: float = 0.0
    risk_reward_ratio: float = 0.0
    rationale: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class OrderFill:
    fill_id: str = field(default_factory=lambda: f"FILL-{uuid.uuid4().hex[:8].upper()}")
    intent_id: str = ""
    symbol: str = ""
    side: str = "BUY"
    quantity: int = 0
    signal_price: float = 0.0
    fill_price: float = 0.0
    realized_slippage_pct: float = 0.0
    fee_inr: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
