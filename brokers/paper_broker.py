import uuid
from datetime import datetime
from typing import Dict, List, Any
from brokers.base_broker import BaseBroker
from agents.memory_agent import memory_agent
from utils.logger import logger

class PaperBroker(BaseBroker):
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.cash_balance = initial_capital
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.order_history: List[Dict[str, Any]] = []
        self.realized_pnl: float = 0.0

    def get_account_balance(self) -> Dict[str, float]:
        unrealized_pnl = sum(pos.get("unrealized_pnl", 0.0) for pos in self.positions.values())
        portfolio_value = self.cash_balance + sum(pos["qty"] * pos["current_price"] for pos in self.positions.values())
        total_trades = len(self.order_history)
        avg_slippage = (sum(o.get("realized_slippage_pct", 0.0) for o in self.order_history) / total_trades) if total_trades > 0 else 0.0
        return {
            "cash_balance": round(self.cash_balance, 2),
            "portfolio_value": round(portfolio_value, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "initial_capital": self.initial_capital,
            "total_return_pct": round(((portfolio_value - self.initial_capital) / self.initial_capital) * 100, 2),
            "total_trades": total_trades,
            "avg_slippage_pct": round(avg_slippage, 4)
        }

    def place_order(self, symbol: str, action: str, quantity: int, order_type: str = "MARKET", limit_price: float = 0.0, current_market_price: float = 0.0, stop_loss: float = 0.0, target: float = 0.0) -> Dict[str, Any]:
        execution_price = current_market_price if order_type == "MARKET" else limit_price
        total_cost = quantity * execution_price

        if action == "BUY" and total_cost > self.cash_balance:
            logger.warning(f"PaperBroker: Order REJECTED for {symbol}. Insufficient funds. Required: ₹{total_cost}, Available: ₹{self.cash_balance}")
            return {"status": "REJECTED", "reason": "INSUFFICIENT_FUNDS"}

        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if action == "BUY":
            self.cash_balance -= total_cost
            if symbol in self.positions:
                # Average position
                existing = self.positions[symbol]
                total_qty = existing["qty"] + quantity
                avg_price = ((existing["qty"] * existing["entry_price"]) + total_cost) / total_qty
                existing["qty"] = total_qty
                existing["entry_price"] = avg_price
            else:
                self.positions[symbol] = {
                    "symbol": symbol,
                    "qty": quantity,
                    "entry_price": execution_price,
                    "current_price": execution_price,
                    "stop_loss": stop_loss,
                    "target": target,
                    "unrealized_pnl": 0.0,
                    "entry_time": timestamp
                }
        elif action == "SELL":
            if symbol in self.positions:
                pos = self.positions[symbol]
                trade_pnl = (execution_price - pos["entry_price"]) * quantity
                self.realized_pnl += trade_pnl
                self.cash_balance += (quantity * execution_price)
                
                pos["qty"] -= quantity
                if pos["qty"] <= 0:
                    del self.positions[symbol]
            else:
                logger.warning(f"PaperBroker: Cannot short sell {symbol} in simple paper mode")
                return {"status": "REJECTED", "reason": "NO_POSITION_TO_SELL"}

        order_record = {
            "order_id": order_id,
            "timestamp": timestamp,
            "signal_timestamp": timestamp,
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "signal_price": limit_price if limit_price > 0 else execution_price,
            "fill_price": execution_price,
            "realized_slippage_pct": round(abs(execution_price - (limit_price if limit_price > 0 else execution_price)) / (limit_price if limit_price > 0 else execution_price) * 100, 4),
            "stop_loss": stop_loss,
            "target": target,
            "status": "FILLED"
        }
        self.order_history.append(order_record)
        logger.info(f"PaperBroker: Order FILLED [{action}] {quantity}x {symbol} @ INR {execution_price:.2f} (SL: INR {stop_loss:.2f}, TGT: INR {target:.2f}, Slippage: {order_record['realized_slippage_pct']}%)")
        return order_record

    def update_market_prices(self, price_map: Dict[str, float]) -> List[Dict[str, Any]]:
        """Updates prices of positions and checks for Stop Loss / Target triggers."""
        auto_exits = []
        for symbol, pos in list(self.positions.items()):
            if symbol in price_map:
                current_price = price_map[symbol]
                pos["current_price"] = current_price
                pos["unrealized_pnl"] = round((current_price - pos["entry_price"]) * pos["qty"], 2)
                
                # Check Stop Loss trigger
                if pos["stop_loss"] > 0 and current_price <= pos["stop_loss"]:
                    logger.warning(f"PaperBroker: STOP LOSS TRIGGERED for {symbol} @ INR {current_price:.2f} (SL: INR {pos['stop_loss']:.2f})")
                    exit_record = self.close_position(symbol, reason="STOP_LOSS")
                    auto_exits.append(exit_record)
                # Check Target trigger
                elif pos["target"] > 0 and current_price >= pos["target"]:
                    logger.info(f"PaperBroker: TARGET REACHED for {symbol} @ INR {current_price:.2f} (TGT: INR {pos['target']:.2f})")
                    exit_record = self.close_position(symbol, reason="TARGET_HIT")
                    auto_exits.append(exit_record)

        return auto_exits

    def get_positions(self) -> List[Dict[str, Any]]:
        return list(self.positions.values())

    def close_position(self, symbol: str, reason: str = "MANUAL") -> Dict[str, Any]:
        if symbol not in self.positions:
            return {"status": "FAILED", "reason": "POSITION_NOT_FOUND"}

        pos = self.positions[symbol]
        current_price = pos["current_price"]
        entry_price = pos["entry_price"]
        trade_pnl = (current_price - entry_price) * pos["qty"]

        exit_order = self.place_order(
            symbol=symbol,
            action="SELL",
            quantity=pos["qty"],
            order_type="MARKET",
            current_market_price=current_price
        )
        exit_order["exit_reason"] = reason

        # Store in Mistake Memory if the trade resulted in a loss
        if trade_pnl < 0:
            memory_agent.log_losing_trade(
                symbol=symbol,
                entry_price=entry_price,
                exit_price=current_price,
                loss_amount=trade_pnl,
                entry_reason="Technical & Sentiment Strategy Signal",
                exit_reason=reason
            )

        return exit_order

    def square_off_all(self, reason: str = "AUTO_SQUARE_OFF") -> List[Dict[str, Any]]:
        results = []
        for symbol in list(self.positions.keys()):
            res = self.close_position(symbol, reason=reason)
            results.append(res)
        logger.info(f"PaperBroker: Square-off ALL executed ({reason}). Exited {len(results)} positions.")
        return results
