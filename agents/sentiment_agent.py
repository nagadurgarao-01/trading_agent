import json
import urllib.request
import urllib.parse
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List
from config.settings import settings
from config.prompt_templates import SENTIMENT_ANALYSIS_PROMPT
from utils.logger import logger

class SentimentAgent:
    def __init__(self):
        logger.info("News & Sentiment Analysis Agent initialized (LLM + Web Scraper)")

    def fetch_headlines(self, symbol: str) -> List[str]:
        """Scrapes recent Indian stock news headlines for a ticker."""
        clean_symbol = symbol.replace(".NS", "")
        query = urllib.parse.quote(f"{clean_symbol} stock news India Moneycontrol")
        url = f"https://news.google.com/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
        
        headlines = []
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                html = response.read().decode('utf-8')
                soup = BeautifulSoup(html, 'html.parser')
                articles = soup.find_all('a', class_='JtA2fe') or soup.find_all('article')
                for item in articles[:5]:
                    text = item.get_text().strip()
                    if text and len(text) > 15:
                        headlines.append(text)
        except Exception as e:
            logger.warning(f"SentimentAgent: Headline fetch fallback triggered for {symbol}: {e}")
            
        return headlines

    def analyze_with_gemini(self, symbol: str, headlines: List[str]) -> Dict[str, Any]:
        """Calls Gemini API for structured financial sentiment evaluation."""
        try:
            api_key = settings.GEMINI_API_KEY
            if not api_key:
                return None

            prompt_text = SENTIMENT_ANALYSIS_PROMPT.format(
                symbol=symbol,
                headlines="\n- ".join(headlines)
            )

            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.LLM_MODEL}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }

            resp = requests.post(endpoint, json=payload, timeout=8)
            if resp.status_code == 200:
                result = resp.json()
                text_content = result["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_content)
                logger.info(f"SentimentAgent [Gemini LLM] {symbol}: Score={parsed.get('sentiment_score')} Rec={parsed.get('recommendation')}")
                return parsed
        except Exception as e:
            logger.warning(f"SentimentAgent: Gemini API call failed for {symbol}: {e}. Falling back to rule engine.")
        
        return None

    def analyze_sentiment(self, symbol: str) -> Dict[str, Any]:
        headlines = self.fetch_headlines(symbol)
        if not headlines:
            return {"symbol": symbol, "sentiment_score": 0.0, "confidence": 0.0,
                    "headlines_count": 0, "key_drivers": ["No verified current headlines available"],
                    "recommendation": "NEUTRAL"}
        
        # Try Gemini LLM Analysis first if API key is present
        if settings.GEMINI_API_KEY:
            llm_result = self.analyze_with_gemini(symbol, headlines)
            if llm_result:
                return llm_result

        # Heuristic fallback rule engine
        positive_keywords = ["growth", "buy", "profit", "surge", "gain", "outperform", "bullish", "record", "order", "rally"]
        negative_keywords = ["loss", "fall", "sell", "decline", "penalty", "bearish", "slump", "probe", "down", "drop"]
        
        score = 0.0
        matched_drivers = []
        
        for text in headlines:
            text_lower = text.lower()
            pos_matches = [w for w in positive_keywords if w in text_lower]
            neg_matches = [w for w in negative_keywords if w in text_lower]
            
            if pos_matches:
                score += 0.3 * len(pos_matches)
                matched_drivers.append(f"Positive news driver: '{text[:60]}...'")
            if neg_matches:
                score -= 0.3 * len(neg_matches)
                matched_drivers.append(f"Negative news driver: '{text[:60]}...'")

        bounded_score = max(-1.0, min(1.0, round(score, 2)))
        recommendation = "BULLISH" if bounded_score > 0.2 else ("BEARISH" if bounded_score < -0.2 else "NEUTRAL")
        
        return {
            "symbol": symbol,
            "sentiment_score": bounded_score,
            "confidence": 0.85,
            "headlines_count": len(headlines),
            "key_drivers": matched_drivers if matched_drivers else ["Stable market news sentiment"],
            "recommendation": recommendation
        }

sentiment_agent = SentimentAgent()
