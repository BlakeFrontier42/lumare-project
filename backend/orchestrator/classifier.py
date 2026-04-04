"""
Intent Classifier — Deterministic, rule-based classification.

No LLM call needed for 90%+ of requests. Fast, auditable, testable.
Falls back to keyword scoring when exact patterns don't match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from backend.orchestrator.schemas import IntentCategory


@dataclass
class Intent:
    category: IntentCategory
    confidence: float  # 0.0–1.0
    symbols: List[str] = field(default_factory=list)
    sub_intent: Optional[str] = None  # e.g. "options_chain", "backtest", "stress_test"
    raw_query: str = ""


# ─── Symbol extraction ────────────────────────────────────

_KNOWN_SYMBOLS = {
    # Crypto
    "BTC", "ETH", "SOL", "XRP", "ADA", "AVAX", "DOGE", "DOT", "LINK", "MATIC",
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "AVAXUSDT",
    # Equities
    "SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMZN", "MSFT", "GOOGL", "META",
    "AMD", "NFLX", "JPM", "GS", "BAC", "V", "MA", "UNH", "JNJ", "PFE",
    "XOM", "CVX", "COP", "GLD", "SLV", "TLT", "IWM", "DIA", "ARKK",
    # Futures
    "ES", "NQ", "YM", "RTY", "CL", "GC", "SI", "ZB", "ZN", "6E",
}

_SYMBOL_RE = re.compile(r"\b([A-Z]{1,6}(?:USDT)?)\b")


def extract_symbols(text: str) -> List[str]:
    """Pull known ticker symbols from free text."""
    found = _SYMBOL_RE.findall(text.upper())
    return [s for s in found if s in _KNOWN_SYMBOLS]


# ─── Keyword banks ────────────────────────────────────────

_CATEGORY_KEYWORDS: Dict[IntentCategory, List[str]] = {
    IntentCategory.TRADE: [
        "buy", "sell", "long", "short", "entry", "exit", "stop loss",
        "take profit", "order", "execute", "position", "leverage",
        "limit order", "market order", "scale in", "scale out",
        "close position", "tp", "sl", "dca", "fill",
    ],
    IntentCategory.RESEARCH: [
        "research", "analyze", "analysis", "what is", "explain",
        "news", "sentiment", "why is", "outlook", "forecast",
        "deep dive", "thesis", "bull case", "bear case", "catalyst",
        "earnings", "filing", "sec", "10-k", "10-q", "prospectus",
    ],
    IntentCategory.PORTFOLIO: [
        "portfolio", "allocation", "rebalance", "diversify", "holdings",
        "net worth", "asset allocation", "weight", "exposure",
        "concentrated", "underweight", "overweight", "hedge",
    ],
    IntentCategory.MACRO: [
        "macro", "fed", "fomc", "cpi", "gdp", "inflation", "rates",
        "yield curve", "treasury", "unemployment", "nonfarm", "pce",
        "ism", "pmi", "housing", "consumer", "recession", "expansion",
        "monetary policy", "fiscal", "geopolitical", "dxy", "vix",
    ],
    IntentCategory.RISK: [
        "risk", "var", "value at risk", "stress test", "drawdown",
        "correlation", "max loss", "circuit breaker", "heat",
        "exposure limit", "margin", "liquidation", "risk check",
    ],
    IntentCategory.QUANT: [
        "backtest", "monte carlo", "sharpe", "sortino", "factor",
        "regression", "optimize", "efficient frontier", "beta",
        "alpha", "volatility", "correlation matrix", "covariance",
        "walk forward", "rolling", "simulation", "bootstrap",
    ],
    IntentCategory.MEMORY: [
        "remember", "preference", "my settings", "last time",
        "history", "save this", "bookmark", "favorite", "recall",
        "what did i", "my style", "my risk", "track record",
    ],
}

# Sub-intents for finer routing
_SUB_INTENTS: Dict[str, Tuple[IntentCategory, str]] = {
    "options chain": (IntentCategory.TRADE, "options_chain"),
    "option": (IntentCategory.TRADE, "options"),
    "greeks": (IntentCategory.TRADE, "options_greeks"),
    "iv skew": (IntentCategory.TRADE, "iv_skew"),
    "futures": (IntentCategory.TRADE, "futures"),
    "backtest": (IntentCategory.QUANT, "backtest"),
    "monte carlo": (IntentCategory.QUANT, "monte_carlo"),
    "stress test": (IntentCategory.RISK, "stress_test"),
    "congressional": (IntentCategory.RESEARCH, "congressional_trades"),
    "insider": (IntentCategory.RESEARCH, "insider_trades"),
    "dark pool": (IntentCategory.RESEARCH, "dark_pool"),
    "unusual flow": (IntentCategory.RESEARCH, "unusual_flow"),
    "economic calendar": (IntentCategory.MACRO, "calendar"),
    "earnings calendar": (IntentCategory.RESEARCH, "earnings_calendar"),
    "rebalance": (IntentCategory.PORTFOLIO, "rebalance"),
    "allocation": (IntentCategory.PORTFOLIO, "allocation"),
}


class IntentClassifier:
    """
    Deterministic intent classifier.

    Priority order:
    1. Exact sub-intent pattern match (highest confidence)
    2. Keyword density scoring per category
    3. Category hint from frontend (if provided)
    4. Default to GENERAL
    """

    def classify(
        self,
        query: str,
        category_hint: Optional[IntentCategory] = None,
        context: dict = None,
    ) -> Intent:
        query_lower = query.lower().strip()
        symbols = extract_symbols(query)

        # 1) Sub-intent exact match
        for pattern, (cat, sub) in _SUB_INTENTS.items():
            if pattern in query_lower:
                return Intent(
                    category=cat,
                    confidence=0.95,
                    symbols=symbols,
                    sub_intent=sub,
                    raw_query=query,
                )

        # 2) Keyword density scoring
        scores: Dict[IntentCategory, float] = {}
        for cat, keywords in _CATEGORY_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in query_lower)
            if hits > 0:
                # Normalize by keyword bank size, weight by hit count
                scores[cat] = hits / len(keywords) + (hits * 0.1)

        if scores:
            best_cat = max(scores, key=scores.get)
            best_score = scores[best_cat]
            # Confidence = clamped normalized score
            confidence = min(0.5 + best_score, 0.95)
            return Intent(
                category=best_cat,
                confidence=confidence,
                symbols=symbols,
                raw_query=query,
            )

        # 3) Category hint from frontend
        if category_hint:
            return Intent(
                category=category_hint,
                confidence=0.6,
                symbols=symbols,
                raw_query=query,
            )

        # 4) If symbols present, default to TRADE
        if symbols:
            return Intent(
                category=IntentCategory.TRADE,
                confidence=0.4,
                symbols=symbols,
                raw_query=query,
            )

        # 5) Default
        return Intent(
            category=IntentCategory.GENERAL,
            confidence=0.3,
            symbols=symbols,
            raw_query=query,
        )
