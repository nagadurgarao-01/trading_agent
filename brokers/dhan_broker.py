import requests
from typing import Dict, List, Any
from brokers.base_broker import BaseBroker
from brokers.instruments import get_dhan_security_id
from config.settings import settings
from utils.logger import logger

class DhanBroker(BaseBroker):
    """
    Official DhanHQ Broker API v2 Integration.
    Docs: https://dhanhq.co/docs/v2/
    """
    def __init__(self, client_id: str = None, access_token: str = None):
        self.client_id = client_id or settings.DHAN_CLIENT_ID
        self.access_token = access_token or settings.DHAN_ACCESS_TOKEN
        self.base_url = "https://api.dhan.co/v2"
        self.headers = {
            "access-token": self.access_token,
            "client-id": self.client_id,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        self.local_positions = {}
        logger.info(f"DhanBroker initialized for Client ID: {self.client_id}")

    def get_account_balance(self) -> Dict[str, float]:
        """Fetches account fund limits and cash balance from DhanHQ API."""
        try:
            url = f"{self.base_url}/fundlimit"
            resp = requests.get(url, headers=self.headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                avail_cash = float(data.get("availabelBalance", data.get("sodLimit", 100000.0)))
                collateral = float(data.get("collateralAmount", 0.0))
                realized_pnl = float(data.get("realizedProfitLoss", 0.0))
                unrealized_pnl = float(data.get("unrealizedProfitLoss", 0.0))
                
                return {
                    "cash_balance": round(avail_cash, 2),
                    "portfolio_value": round(avail_cash + collateral, 2),
                    "realized_pnl": round(realized_pnl, 2),
                    "unrealized_pnl": round(unrealized_pnl, 2),
                    "initial_capital": settings.INITIAL_CAPITAL,
                    "total_return_pct": round((realized_pnl / settings.INITIAL_CAPITAL) * 100, 2)
                }
            else:
                logger.warning(f"DhanBroker: Fund limits API returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.error(f"DhanBroker: Exception fetching balance: {e}")
            
        return {
            "cash_balance": 0.0,
            "portfolio_value": 0.0,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "initial_capital": settings.INITIAL_CAPITAL,
            "total_return_pct": 0.0
        }

    def place_order(self, symbol: str, action: str, quantity: int, order_type: str = "MARKET", limit_price: float = 0.0, current_market_price: float = 0.0, stop_loss: float = 0.0, target: float = 0.0) -> Dict[str, Any]:
        """Places a live trade order on DhanHQ (NSE Equity Intraday / MIS)."""
        clean_symbol = symbol.replace(".NS", "")
        sec_id = get_dhan_security_id(symbol)
        url = f"{self.base_url}/orders"
        
        payload = {
            "dhanClientId": self.client_id,
            "transactionType": "BUY" if action == "BUY" else "SELL",
            "exchangeSegment": "NSE_EQ",
            "productType": "INTRADAY", # MIS Intraday
            "orderType": "MARKET" if order_type == "MARKET" else "LIMIT",
            "validity": "DAY",
            "tradingSymbol": clean_symbol,
            "securityId": sec_id,
            "quantity": quantity,
            "price": limit_price if order_type == "LIMIT" else 0.0,
            "triggerPrice": 0.0,
            "afterMarketOrder": False
        }

        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=8)
            if resp.status_code in [200, 201]:
                res_data = resp.json()
                order_status = res_data.get("orderStatus", "TRANSIT")
                if order_status in ["REJECTED", "CANCELLED"]:
                    reason = res_data.get("remarks", res_data.get("errorMessage", "Order Rejected by Dhan"))
                    logger.error(f"DhanBroker: Order REJECTED on Dhan [{action}] {quantity}x {clean_symbol} (SecurityID: {sec_id}) | Reason: {reason}")
                    return {"status": "REJECTED", "reason": reason, "response": res_data}

                order_id = res_data.get("orderId", "DHAN-SUCCESS")
                logger.info(f"DhanBroker: Order PLACED successfully on Dhan [{action}] {quantity}x {clean_symbol} (SecurityID: {sec_id}) | OrderID: {order_id}")
                if action == "BUY":
                    self.local_positions[symbol] = {
                        "symbol": symbol,
                        "qty": quantity,
                        "entry_price": current_market_price,
                        "current_price": current_market_price,
                        "stop_loss": stop_loss,
                        "target": target,
                        "unrealized_pnl": 0.0
                    }
                elif action == "SELL" and symbol in self.local_positions:
                    del self.local_positions[symbol]

                return {
                    "order_id": order_id,
                    "symbol": symbol,
                    "action": action,
                    "quantity": quantity,
                    "price": current_market_price,
                    "status": "SUCCESS",
                    "response": res_data
                }
            else:
                logger.error(f"DhanBroker: Order placement failed with status {resp.status_code}: {resp.text}")
                return {"status": "REJECTED", "reason": resp.text}
        except Exception as e:
            logger.error(f"DhanBroker: Exception placing order for {symbol}: {e}")
            return {"status": "ERROR", "reason": str(e)}

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetches active positions from DhanHQ API."""
        url = f"{self.base_url}/positions"
        positions_list = []
        try:
            resp = requests.get(url, headers=self.headers, timeout=8)
            if resp.status_code == 200:
                raw_positions = resp.json()
                for pos in raw_positions if isinstance(raw_positions, list) else []:
                    net_qty = int(pos.get("netQty", 0))
                    if net_qty != 0:
                        tsym = pos.get("tradingSymbol", "")
                        clean_sym = tsym if tsym.endswith(".NS") else f"{tsym}.NS"
                        positions_list.append({
                            "symbol": clean_sym,
                            "qty": abs(net_qty),
                            "entry_price": float(pos.get("buyAvg", 0.0)),
                            "current_price": float(pos.get("lastTradedPrice", 0.0)),
                            "stop_loss": 0.0,
                            "target": 0.0,
                            "unrealized_pnl": float(pos.get("unrealizedProfit", 0.0))
                        })
        except Exception as e:
            logger.error(f"DhanBroker: Exception fetching positions: {e}")
            
        # Merge local in-memory position fallback if API delayed
        if hasattr(self, 'local_positions'):
            for sym, pos in self.local_positions.items():
                if not any(p["symbol"] == sym for p in positions_list):
                    positions_list.append(pos)

        return positions_list

    def close_position(self, symbol: str, reason: str = "MANUAL") -> Dict[str, Any]:
        positions = self.get_positions()
        target_pos = next((p for p in positions if p["symbol"] == symbol), None)
        if not target_pos:
            return {"status": "FAILED", "reason": "POSITION_NOT_FOUND"}
            
        return self.place_order(
            symbol=symbol,
            action="SELL" if target_pos["qty"] > 0 else "BUY",
            quantity=abs(target_pos["qty"]),
            order_type="MARKET"
        )

    def square_off_all(self, reason: str = "AUTO_SQUARE_OFF") -> List[Dict[str, Any]]:
        positions = self.get_positions()
        results = []
        for pos in positions:
            res = self.close_position(pos["symbol"], reason=reason)
            results.append(res)
        return results

    def update_market_prices(self, price_map: Dict[str, float]) -> List[Dict[str, Any]]:
        """Updates live price map for active positions on DhanHQ."""
        return []
