from typing import Dict, Any, List, Optional
from core.models import TradeIntent, OrderFill
from storage.db import db_repo
from utils.logger import logger

class OrderManagementSystem:
    """Order Management System (OMS) for intent submission, fills, and SQLite persistence."""
    def __init__(self, broker: Any):
        self.broker = broker

    def submit_intent(self, intent: TradeIntent) -> Dict[str, Any]:
        # 1. Persist Intent to DB
        db_repo.save_trade_intent(intent)
        db_repo.log_audit("INTENT_SUBMITTED", "OMS", f"Submitted intent for {intent.symbol}", {"intent_id": intent.intent_id})

        # 2. Execute via Broker
        order = self.broker.place_order(
            symbol=intent.symbol,
            action=intent.side.value if hasattr(intent.side, 'value') else str(intent.side),
            quantity=intent.quantity,
            order_type="MARKET",
            limit_price=intent.suggested_entry,
            current_market_price=intent.suggested_entry,
            stop_loss=intent.stop_loss,
            target=intent.target
        )

        if order.get("status") in {"FILLED", "SUCCESS"}:
            # 3. Create OrderFill Record
            fill = OrderFill(
                intent_id=intent.intent_id,
                symbol=intent.symbol,
                side=order.get("action", "BUY"),
                quantity=order.get("quantity", 0),
                signal_price=intent.suggested_entry,
                fill_price=order.get("fill_price", order.get("price", intent.suggested_entry)),
                realized_slippage_pct=order.get("realized_slippage_pct", 0.0),
                fee_inr=order.get("brokerage_fee", 20.0)
            )
            db_repo.save_order_fill(fill)
            db_repo.log_audit("ORDER_FILLED", "OMS", f"Order filled for {intent.symbol}", {"fill_id": fill.fill_id, "price": fill.fill_price})
            return {"status": "SUCCESS", "fill": fill, "order": order}

        db_repo.log_audit("ORDER_REJECTED", "OMS", f"Broker rejected order for {intent.symbol}", order)
        return {"status": "REJECTED", "reason": order.get("reason", "BROKER_REJECTED"), "order": order}
