import asyncio
import json
from typing import Dict, Any
from fastapi import WebSocket

class TelemetryHub:
    def __init__(self):
        self.active_connections: Dict[WebSocket, asyncio.AbstractEventLoop] = {}
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
        self.active_connections[websocket] = asyncio.get_running_loop()
        # Send current state upon connection
        await websocket.send_text(json.dumps({
            "type": "INITIAL_STATE",
            "data": self.latest_state
        }))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.pop(websocket, None)

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

        current_loop = asyncio.get_running_loop()
        for connection, connection_loop in list(self.active_connections.items()):
            try:
                if connection_loop is current_loop:
                    await connection.send_text(payload)
                else:
                    future = asyncio.run_coroutine_threadsafe(connection.send_text(payload), connection_loop)
                    await asyncio.wrap_future(future)
            except Exception:
                self.disconnect(connection)

telemetry_hub = TelemetryHub()
