from abc import ABC, abstractmethod
from typing import Dict, List, Any

class BaseBroker(ABC):
    
    @abstractmethod
    def get_account_balance(self) -> Dict[str, float]:
        """Returns cash_balance, portfolio_value, realized_pnl, unrealized_pnl"""
        pass
        
    @abstractmethod
    def place_order(self, symbol: str, action: str, quantity: int, order_type: str = "MARKET", limit_price: float = 0.0, current_market_price: float = 0.0, stop_loss: float = 0.0, target: float = 0.0) -> Dict[str, Any]:
        """Places a buy/sell order"""
        pass
        
    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Returns list of open positions"""
        pass
        
    @abstractmethod
    def close_position(self, symbol: str, reason: str = "MANUAL") -> Dict[str, Any]:
        """Closes an active position for a specific symbol"""
        pass
        
    @abstractmethod
    def square_off_all(self, reason: str = "AUTO_SQUARE_OFF") -> List[Dict[str, Any]]:
        """Exits all open positions immediately"""
        pass

    @abstractmethod
    def update_market_prices(self, price_map: Dict[str, float]) -> List[Dict[str, Any]]:
        """Updates market prices for active positions and handles auto stop loss / target exits"""
        pass
