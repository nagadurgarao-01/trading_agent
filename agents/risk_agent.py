from typing import Dict, Any, Tuple, List
from config.settings import settings
from agents.memory_agent import memory_agent
from utils.logger import logger

# Sector Mapping to prevent correlated bets
SECTOR_MAP = {
    "IDEA.NS": "Telecom",
    "YESBANK.NS": "Banking",
    "RENUKA.NS": "FMCG",
    "SOUTHBANK.NS": "Banking",
    "SUZLON.NS": "Energy"
}

class RiskAgent:
    def __init__(self):
        logger.info("Risk & Portfolio Manager Agent initialized (with Sector Diversification Enforcement)")
        self.start_of_day_equity = None

    def get_stock_sector(self, symbol: str) -> str:
        return SECTOR_MAP.get(symbol, "Other")

    def validate_trade(
        self,
        proposal: Dict[str, Any],
        account_balance: Dict[str, float],
        open_positions: List[Dict[str, Any]] = None,
        tech_summary: Dict[str, Any] = None
    ) -> Tuple[bool, int, str]:
        """
        Validates proposed trade against hard risk limits, sector concentration, and Mistake Memory.
        """
        symbol = proposal["symbol"]
        action = proposal["action"]
        ltp = proposal["ltp"]
        sl = proposal["suggested_stop_loss"]
        tgt = proposal["suggested_target"]

        if action == "HOLD":
            return False, 0, "No trade proposed"

        open_positions_list = open_positions if open_positions else []
        open_positions_count = len(open_positions_list)

        # Rule 1: Circuit Breaker - Max Daily Loss Check
        portfolio_val = account_balance.get("portfolio_value", settings.INITIAL_CAPITAL)
        if self.start_of_day_equity is None or self.start_of_day_equity <= 0:
            self.start_of_day_equity = portfolio_val

        drawdown_pct = ((self.start_of_day_equity - portfolio_val) / self.start_of_day_equity) * 100.0 if self.start_of_day_equity > 0 else 0.0
        
        if drawdown_pct >= settings.MAX_DAILY_LOSS_PCT:
            reason = f"CIRCUIT BREAKER: Daily drawdown ({drawdown_pct:.2f}%) exceeded limit ({settings.MAX_DAILY_LOSS_PCT}%)."
            logger.warning(f"RiskAgent: REJECTED {symbol} - {reason}")
            return False, 0, reason

        # Rule 2: Sector Concentration Check (Max 1 position per sector cluster)
        target_sector = self.get_stock_sector(symbol)
        for open_pos in open_positions_list:
            open_sym = open_pos.get("symbol", "")
            if self.get_stock_sector(open_sym) == target_sector:
                reason = f"SECTOR CONCENTRATION RISK: Already holding {open_sym} in {target_sector} sector (Correlation Protection)."
                logger.warning(f"RiskAgent: REJECTED {symbol} - {reason}")
                return False, 0, reason

        # Rule 3: Mistake Memory Pre-Check (Learn from past failures)
        if tech_summary:
            past_mistake_check = memory_agent.check_for_past_mistake(symbol, action, tech_summary)
            if past_mistake_check.get("is_risky_repeat"):
                reason = past_mistake_check.get("reason")
                logger.warning(f"RiskAgent: REJECTED {symbol} (Mistake Memory Triggered) - {reason}")
                return False, 0, reason

        # Rule 4: Max Simultaneous Open Positions Check
        if open_positions_count >= settings.MAX_OPEN_POSITIONS:
            reason = f"MAX POSITIONS REACHED ({open_positions_count}/{settings.MAX_OPEN_POSITIONS})."
            logger.warning(f"RiskAgent: REJECTED {symbol} - {reason}")
            return False, 0, reason

        # Rule 5: Risk-Reward Ratio Check
        risk_per_share = abs(ltp - sl)
        reward_per_share = abs(tgt - ltp)
        if risk_per_share == 0:
            return False, 0, "Invalid zero stop-loss distance"
            
        rr_ratio = reward_per_share / risk_per_share
        if rr_ratio < settings.MIN_RISK_REWARD_RATIO:
            reason = f"Insufficient Risk-Reward Ratio ({rr_ratio:.2f} < {settings.MIN_RISK_REWARD_RATIO})."
            logger.warning(f"RiskAgent: REJECTED {symbol} - {reason}")
            return False, 0, reason

        # Rule 6: Position Sizing (Max % Capital per trade)
        cash_balance = account_balance.get("cash_balance", 0.0)
        max_capital_for_trade = portfolio_val * (settings.MAX_POSITION_SIZE_PCT / 100.0)
        usable_cash = min(cash_balance, max_capital_for_trade)
        
        quantity = int(usable_cash // ltp)
        if quantity <= 0:
            reason = f"Insufficient usable cash (Available: ₹{usable_cash:.2f}, Required per share: ₹{ltp:.2f})."
            logger.warning(f"RiskAgent: REJECTED {symbol} - {reason}")
            return False, 0, reason

        logger.info(f"RiskAgent: APPROVED [{action}] {symbol} ({target_sector}) | Qty: {quantity} shares | Alloc: INR {quantity * ltp:.2f} | R:R = 1:{rr_ratio:.2f}")
        return True, quantity, "APPROVED"

risk_agent = RiskAgent()
