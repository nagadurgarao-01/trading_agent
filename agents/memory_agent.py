import os
import json
from datetime import datetime
from typing import Dict, List, Any
from config.settings import settings
from utils.logger import logger

class MistakeMemoryAgent:
    """
    Stores losing trades, trade rejections, and execution errors.
    Provides self-reflection memory to prevent the agent from repeating past mistakes.
    """
    def __init__(self, memory_file: str = None):
        if memory_file is None:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            data_dir = os.path.join(base_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            self.memory_file = os.path.join(data_dir, "mistakes_memory.json")
        else:
            self.memory_file = memory_file
            
        self.mistakes: List[Dict[str, Any]] = self.load_memory()
        logger.info(f"Mistake Memory Agent initialized. Loaded {len(self.mistakes)} past lessons/mistakes.")

    def load_memory(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"MistakeMemoryAgent: Error reading memory file: {e}")
        return []

    def save_memory(self):
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(self.mistakes, f, indent=2)
        except Exception as e:
            logger.error(f"MistakeMemoryAgent: Error saving memory file: {e}")

    def log_losing_trade(self, symbol: str, entry_price: float, exit_price: float, loss_amount: float, entry_reason: str, exit_reason: str, market_data: Dict[str, Any] = None):
        """Records a losing trade with diagnostic metadata."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Self-reflection pattern tag
        pattern = "STOP_LOSS_HIT"
        reflection = f"Trade on {symbol} lost ₹{abs(loss_amount):.2f}. Entered on '{entry_reason}', exited via '{exit_reason}'."
        
        if exit_reason == "STOP_LOSS":
            if market_data and market_data.get("rsi", 50) > 70:
                pattern = "BUY_AT_OVERBOUGHT_RSI"
                reflection += " Lesson: Avoid buying when RSI is overbought (>70)."
            elif market_data and market_data.get("change_pct", 0) < -1.5:
                pattern = "TRADE_AGAINST_INDEX_TREND"
                reflection += " Lesson: Avoid buying when the stock momentum is sharply negative."

        record = {
            "id": len(self.mistakes) + 1,
            "timestamp": timestamp,
            "symbol": symbol,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "loss_amount": round(loss_amount, 2),
            "entry_reason": entry_reason,
            "exit_reason": exit_reason,
            "pattern_tag": pattern,
            "reflection_lesson": reflection
        }
        
        self.mistakes.append(record)
        self.save_memory()
        logger.warning(f"🧠 MISTAKE RECORDED [{pattern}] {symbol}: {reflection}")
        return record

    def check_for_past_mistake(self, symbol: str, proposed_action: str, tech_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Scans mistake database before placing a new trade.
        Returns warning if proposed trade matches a known past failure pattern.
        """
        rsi = tech_data.get("rsi", 50)
        
        for mistake in self.mistakes:
            # Check pattern match 1: Buying at overbought RSI
            if proposed_action == "BUY" and mistake.get("pattern_tag") == "BUY_AT_OVERBOUGHT_RSI" and rsi > 68:
                return {
                    "is_risky_repeat": True,
                    "reason": f"Mistake Warning #{mistake['id']}: Past trade on {mistake['symbol']} failed when buying at RSI > 68 (RSI currently {rsi})."
                }

        return {"is_risky_repeat": False, "reason": "No matching failure pattern"}

memory_agent = MistakeMemoryAgent()
