import requests
import time
import uuid
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
        if not self.client_id or not self.access_token:
            raise RuntimeError("Dhan credentials are required for live trading")
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

    def _get_order_status(self, order_id: str) -> Dict[str, Any]:
        try:
            response = requests.get(f"{self.base_url}/super/orders", headers=self.headers, timeout=8)
            if response.status_code == 200:
                orders = response.json()
                return next((item for item in orders if str(item.get("orderId")) == str(order_id)), {})
        except requests.RequestException as exc:
            logger.warning(f"DhanBroker: unable to reconcile order {order_id}: {exc}")
        return {}

    def place_order(self, symbol: str, action: str, quantity: int, order_type: str = "MARKET", limit_price: float = 0.0, current_market_price: float = 0.0, stop_loss: float = 0.0, target: float = 0.0) -> Dict[str, Any]:
        """Places an intraday Dhan Super Order with broker-managed target and stop loss."""
        clean_symbol = symbol.replace(".NS", "")
        sec_id = get_dhan_security_id(symbol)
        if not sec_id or quantity <= 0:
            return {"status": "REJECTED", "reason": "INVALID_INSTRUMENT_OR_QUANTITY"}
        if action not in {"BUY", "SELL"}:
            return {"status": "REJECTED", "reason": "INVALID_ACTION"}
        if action == "SELL" and not settings.ALLOW_SHORT_SELLING:
            return {"status": "REJECTED", "reason": "SHORT_SELLING_DISABLED"}
        if stop_loss <= 0 or target <= 0:
            return {"status": "REJECTED", "reason": "PROTECTIVE_EXIT_REQUIRED"}

        url = f"{self.base_url}/super/orders"
        correlation_id = f"TA-{uuid.uuid4().hex[:20]}"
        
        payload = {
            "dhanClientId": self.client_id,
            "correlationId": correlation_id,
            "transactionType": action,
            "exchangeSegment": "NSE_EQ",
            "productType": "INTRADAY",
            "orderType": "MARKET" if order_type == "MARKET" else "LIMIT",
            "securityId": sec_id,
            "quantity": quantity,
            "price": limit_price if order_type == "LIMIT" else 0.0,
            "targetPrice": target,
            "stopLossPrice": stop_loss,
            "trailingJump": 0
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

                order_id = res_data.get("orderId")
                if not order_id:
                    return {"status": "REJECTED", "reason": "MISSING_ORDER_ID", "response": res_data}
                
                deadline = time.monotonic() + settings.ORDER_STATUS_TIMEOUT_SECONDS
                while time.monotonic() < deadline:
                    status_data = self._get_order_status(order_id)
                    order_status = status_data.get("orderStatus", order_status)
                    if order_status in {"TRADED", "PART_TRADED", "REJECTED", "CANCELLED", "EXPIRED"}:
                        res_data = status_data or res_data
                        break
                    time.sleep(0.5)

                if order_status in {"REJECTED", "CANCELLED", "EXPIRED"}:
                    return {"status": "REJECTED", "reason": f"ORDER_REJECTED:{order_status}", "order_id": order_id, "response": res_data}

                fill_price = float(res_data.get("averageTradedPrice", current_market_price) or current_market_price)
                if fill_price <= 0:
                    fill_price = current_market_price

                self.local_positions[symbol] = {"stop_loss": stop_loss, "target": target, "order_id": order_id}
                logger.info(f"DhanBroker: Order ACCEPTED/FILLED [{action}] {quantity}x {clean_symbol} | Status: {order_status} | OrderID: {order_id}")

                return {
                    "order_id": order_id,
                    "symbol": symbol,
                    "action": action,
                    "quantity": quantity,
                    "fill_price": fill_price,
                    "price": fill_price,
                    "status": "FILLED",
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
                        buy_avg = float(pos.get("buyAvg", pos.get("costPrice", pos.get("averagePrice", 0.0))))
                        ltp_val = float(pos.get("lastTradedPrice", pos.get("ltp", buy_avg)))
                        local_meta = self.local_positions.get(clean_sym, {})
                        
                        positions_list.append({
                            "symbol": clean_sym,
                            "qty": abs(net_qty),
                            "net_qty": net_qty,
                            "side": "LONG" if net_qty > 0 else "SHORT",
                            "entry_price": buy_avg if buy_avg > 0 else local_meta.get("entry_price", 0.0),
                            "current_price": ltp_val if ltp_val > 0 else local_meta.get("current_price", buy_avg),
                            "stop_loss": local_meta.get("stop_loss", 0.0),
                            "target": local_meta.get("target", 0.0),
                            "unrealized_pnl": float(pos.get("unrealizedProfit", 0.0))
                        })
                # Prune stale memory for symbols closed directly on Dhan
                active_symbols = {p["symbol"] for p in positions_list}
                self.local_positions = {sym: meta for sym, meta in self.local_positions.items() if sym in active_symbols}
        except Exception as e:
            logger.error(f"DhanBroker: Exception fetching positions: {e}")
            
        return positions_list

    def close_position(self, symbol: str, reason: str = "MANUAL") -> Dict[str, Any]:
        positions = self.get_positions()
        target_pos = next((p for p in positions if p["symbol"] == symbol), None)
        if not target_pos:
            return {"status": "FAILED", "reason": "POSITION_NOT_FOUND"}
            
        order_id = self.local_positions.get(symbol, {}).get("order_id")
        if not order_id:
            try:
                response = requests.get(f"{self.base_url}/super/orders", headers=self.headers, timeout=8)
                if response.status_code == 200:
                    match = next((item for item in response.json()
                                  if item.get("tradingSymbol") == symbol.replace(".NS", "")
                                  and item.get("orderStatus") in {"PENDING", "PART_TRADED", "TRADED"}), None)
                    order_id = match.get("orderId") if match else None
            except requests.RequestException as exc:
                return {"status": "FAILED", "reason": f"CANNOT_RECONCILE_PROTECTIVE_ORDER:{exc}"}
        if order_id:
            # Cancel all linked legs before sending an explicit exit, preventing a
            # later protective leg from reopening/reversing the position.
            try:
                cancellation = requests.delete(f"{self.base_url}/super/orders/{order_id}/ENTRY_LEG", headers=self.headers, timeout=8)
                if cancellation.status_code not in {200, 202}:
                    return {"status": "FAILED", "reason": f"CANNOT_CANCEL_PROTECTIVE_ORDER:{cancellation.text}"}
            except requests.RequestException as exc:
                return {"status": "FAILED", "reason": f"CANNOT_CANCEL_PROTECTIVE_ORDER:{exc}"}
        sec_id = get_dhan_security_id(symbol)
        payload = {"dhanClientId": self.client_id, "correlationId": f"EXIT-{uuid.uuid4().hex[:20]}",
                   "transactionType": "SELL" if target_pos.get("net_qty", target_pos["qty"]) > 0 else "BUY",
                   "exchangeSegment": "NSE_EQ", "productType": "INTRADAY", "orderType": "MARKET",
                   "validity": "DAY", "securityId": sec_id, "quantity": abs(target_pos["qty"]),
                   "price": 0, "triggerPrice": 0, "afterMarketOrder": False}
        try:
            response = requests.post(f"{self.base_url}/orders", headers=self.headers, json=payload, timeout=8)
            data = response.json() if response.content else {}
            if response.status_code in {200, 201} and data.get("orderStatus") not in {"REJECTED", "CANCELLED"}:
                self.local_positions.pop(symbol, None)
                return {"status": "SUCCESS", "order_id": data.get("orderId"), "symbol": symbol, "exit_reason": reason}
            return {"status": "FAILED", "reason": data.get("remarks", response.text)}
        except requests.RequestException as exc:
            return {"status": "FAILED", "reason": str(exc)}

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
