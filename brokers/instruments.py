import requests
import csv
import os
from utils.logger import logger

# Pre-resolved static mapping for ultra-fast lookup
SECURITY_ID_MAP = {
    "IDEA": "14366",
    "YESBANK": "11915",
    "RENUKA": "12026",
    "UCOBANK": "11223",
    "IOB": "9348",
    "CENTRALBK": "14894",
    "SOUTHBANK": "5948",
    "SUZLON": "12018",
    "IDFCFIRSTB": "11184",
    "NHPC": "17400",
    "SJVN": "18883",
    "PNB": "10666",
    "NBCC": "31415",
    "IRFC": "2029",
    "HUDCO": "20825",
    "BEL": "383",
    "TATAPOWER": "3426",
    "RELIANCE": "2885",
    "TCS": "11536",
    "INFY": "1594",
    "HDFCBANK": "1333",
    "ICICIBANK": "4963",
    "SBIN": "3045",
    "BHARTIARTL": "10604",
    "ITC": "1660",
    "LT": "11483"
}

def get_dhan_security_id(trading_symbol: str) -> str:
    clean = trading_symbol.replace(".NS", "").upper()
    if clean in SECURITY_ID_MAP:
        return SECURITY_ID_MAP[clean]
    
    # Fallback to DhanHQ API Scrip Master CSV download
    try:
        url = "https://images.dhan.co/api-data/api-scrip-master.csv"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            reader = csv.DictReader(resp.text.splitlines())
            for row in reader:
                tsym = row.get("SEM_TRADING_SYMBOL", "")
                ex = row.get("SEM_EXM_EXCH_ID", "")
                seg = row.get("SEM_SEGMENT", "")
                if ex == "NSE" and seg == "E" and tsym == clean:
                    sec_id = row.get("SEM_SMST_SECURITY_ID", "")
                    SECURITY_ID_MAP[clean] = sec_id
                    return sec_id
    except Exception as e:
        logger.error(f"DhanInstrumentResolver: Failed to fetch online securityId for {clean}: {e}")
        
    return ""
