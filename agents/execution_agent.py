from typing import Dict, Any
from brokers.base_broker import BaseBroker
from core.models import TradeIntent, Side
from services.oms import OrderManagementSystem
from utils.logger import logger

class ExecutionAgent:
    def __init__(self, broker: BaseBroker):
        self.broker = broker
        self.oms = OrderManagementSystem(broker)
        logger.info(f"Execution Agent initialized with broker: {type(broker).__name__}")

    def execute_trade(self, proposal: Dict[str, Any], quantity: int) -> Dict[str, Any]:
        symbol = proposal["symbol"]
        action = proposal["action"]
        ltp = proposal["ltp"]
        sl = proposal["suggested_stop_loss"]
        tgt = proposal["suggested_target"]

        intent = TradeIntent(symbol=symbol, side=Side(action), quantity=quantity,
                             suggested_entry=ltp, stop_loss=sl, target=tgt,
                             risk_reward_ratio=abs(tgt - ltp) / max(abs(ltp - sl), 1e-9),
                             rationale=proposal.get("reasoning", ""))
        return self.oms.submit_intent(intent)
