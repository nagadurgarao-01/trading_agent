from typing import Dict, Any
from config.settings import settings
from utils.logger import logger

class StrategyAgent:
    def __init__(self):
        logger.info("Strategy & Reasoning Master Agent initialized")

    def evaluate_opportunity(self, quote: Dict[str, Any], tech_summary: Dict[str, Any], sentiment_summary: Dict[str, Any]) -> Dict[str, Any]:
        symbol = quote["symbol"]
        ltp = quote["ltp"]
        tech_signal = tech_summary.get("signal", "NEUTRAL")
        sentiment_score = sentiment_summary.get("sentiment_score", 0.0)

        action = "HOLD"
        confidence = 0.0
        stop_loss = 0.0
        target = 0.0
        reasoning = ""

        # Strategy Logic: Multi-factor confirmation
        if tech_signal == "BULLISH" and sentiment_score >= -0.2:
            action = "BUY"
            confidence = round(0.75 + (sentiment_score * 0.2), 2)
            # Calculate Stop Loss & Target based on VWAP or percentage settings
            sl_dist = max(ltp * (settings.DEFAULT_STOP_LOSS_PCT / 100.0), abs(ltp - tech_summary.get("vwap", ltp)))
            stop_loss = round(ltp - sl_dist, 2)
            target = round(ltp + (sl_dist * settings.MIN_RISK_REWARD_RATIO), 2)
            reasoning = f"Strong Bullish Technical Alignment (Supertrend Bullish, Price above VWAP) + Non-negative sentiment ({sentiment_score})"
        
        elif tech_signal == "BEARISH" and sentiment_score <= 0.2:
            action = "SELL"
            confidence = round(0.75 + (abs(sentiment_score) * 0.2), 2)
            sl_dist = max(ltp * (settings.DEFAULT_STOP_LOSS_PCT / 100.0), abs(ltp - tech_summary.get("vwap", ltp)))
            stop_loss = round(ltp + sl_dist, 2)
            target = round(ltp - (sl_dist * settings.MIN_RISK_REWARD_RATIO), 2)
            reasoning = f"Bearish Technical Alignment (Supertrend Bearish, Price below VWAP) + Non-positive sentiment ({sentiment_score})"

        else:
            reasoning = f"No trade setup. Technical Signal: {tech_signal}, Sentiment Score: {sentiment_score}"

        proposal = {
            "symbol": symbol,
            "action": action,
            "ltp": ltp,
            "confidence": confidence,
            "suggested_entry": ltp,
            "suggested_stop_loss": stop_loss,
            "suggested_target": target,
            "reasoning": reasoning
        }
        
        if action != "HOLD":
            logger.info(f"StrategyAgent Proposal [{action}] {symbol}: Entry INR {ltp}, SL INR {stop_loss}, TGT INR {target} (Conf: {confidence})")
            
        return proposal

strategy_agent = StrategyAgent()
