import asyncio
import json
from typing import Set, Dict, Any, List
from fastapi import WebSocket

class TelemetryHub:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.latest_state: Dict[str, Any] = {
            "metrics": {
                "cash_balance": 100000.0,
                "portfolio_value": 100000.0,
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "total_return_pct": 0.0,
                "win_rate": 75.0,
                "profit_factor": 1.85,
                "max_drawdown": 0.5
            },
            "market_phase": "OPEN",
            "positions": [],
            "logs": [],
            "equity_history": []
        }

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        # Send current state upon connection
        await websocket.send_text(json.dumps({
            "type": "INITIAL_STATE",
            "data": self.latest_state
        }))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, event_type: str, data: Any):
        payload = json.dumps({"type": event_type, "data": data})
        if event_type == "METRICS_UPDATE":
            self.latest_state["metrics"].update(data)
        elif event_type == "POSITIONS_UPDATE":
            self.latest_state["positions"] = data
        elif event_type == "LOG_EVENT":
            self.latest_state["logs"].append(data)
            if len(self.latest_state["logs"]) > 100:
                self.latest_state["logs"].pop(0)

        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception:
                self.disconnect(connection)

telemetry_hub = TelemetryHub()
