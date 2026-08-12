from typing import Dict, Any
from brokers.base_broker import BaseBroker
from utils.logger import logger

class ExecutionAgent:
    def __init__(self, broker: BaseBroker):
        self.broker = broker
        logger.info(f"Execution Agent initialized with broker: {type(broker).__name__}")

    def execute_trade(self, proposal: Dict[str, Any], quantity: int) -> Dict[str, Any]:
        symbol = proposal["symbol"]
        action = proposal["action"]
        ltp = proposal["ltp"]
        sl = proposal["suggested_stop_loss"]
        tgt = proposal["suggested_target"]

        order_result = self.broker.place_order(
            symbol=symbol,
            action=action,
            quantity=quantity,
            order_type="MARKET",
            current_market_price=ltp,
            stop_loss=sl,
            target=tgt
        )
        return order_result
