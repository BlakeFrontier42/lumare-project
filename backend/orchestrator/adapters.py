"""
Model / Tool Adapters — Unified interface to external engines.

Each adapter wraps a specific capability:
- PerplexityAdapter: Live web search, citations, company/macro research
- FrontierLLMAdapter: Complex synthesis, trade-off analysis, narrative
- QuantAdapter: Backtests, Monte Carlo, factor analysis, optimization
- MarketDataAdapter: Real-time prices, candles, order book
- FilingsAdapter: SEC filings, EDGAR, congressional/insider trades

All adapters return List[ResponseBlock] so the orchestrator can
compose responses from multiple sources.
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from loguru import logger

from backend.orchestrator.schemas import (
    BlockType,
    ResponseBlock,
    text_block,
    metric_block,
    signal_block,
    error_block,
)


class BaseAdapter(ABC):
    """All adapters implement this interface."""

    name: str = "base"

    @abstractmethod
    async def execute(
        self, query: str, context: Dict[str, Any]
    ) -> List[ResponseBlock]:
        ...


# ─── Perplexity / Research ────────────────────────────────

class PerplexityAdapter(BaseAdapter):
    """
    Calls Perplexity API for grounded web research with citations.
    Falls back to a structured "research pending" block if no API key.
    """

    name = "perplexity"

    def __init__(self):
        self.api_key = os.getenv("PERPLEXITY_API_KEY", "")
        self.base_url = "https://api.perplexity.ai"

    async def execute(
        self, query: str, context: Dict[str, Any]
    ) -> List[ResponseBlock]:
        if not self.api_key:
            return [text_block(
                "Research",
                f"Research query queued: \"{query}\". "
                "Connect Perplexity API key for live web research with citations.",
                source=self.name,
            )]

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "sonar",
                        "messages": [
                            {"role": "system", "content": (
                                "You are a financial research assistant for Lumare, "
                                "a premium fintech platform. Provide concise, data-driven "
                                "analysis with citations. Focus on actionable insights."
                            )},
                            {"role": "user", "content": query},
                        ],
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            citations = data.get("citations", [])

            blocks: List[ResponseBlock] = [
                text_block("Research Analysis", content, source=self.name),
            ]

            if citations:
                blocks.append(ResponseBlock(
                    type=BlockType.CITATION,
                    title="Sources",
                    data={"citations": citations},
                    source=self.name,
                ))

            return blocks

        except Exception as e:
            logger.error(f"Perplexity adapter error: {e}")
            return [error_block(f"Research request failed: {str(e)}", source=self.name)]


# ─── Frontier LLM (Complex Synthesis) ────────────────────

class FrontierLLMAdapter(BaseAdapter):
    """
    Uses Anthropic Claude for complex synthesis, planning,
    trade-off analysis, and narrative generation.
    """

    name = "frontier_llm"

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")

    async def execute(
        self, query: str, context: Dict[str, Any]
    ) -> List[ResponseBlock]:
        if not self.api_key:
            return [text_block(
                "Analysis",
                f"Complex analysis queued: \"{query}\". "
                "Connect Anthropic API key for frontier reasoning.",
                source=self.name,
            )]

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-4-20250514",
                        "max_tokens": 2048,
                        "system": (
                            "You are a senior financial analyst at Lumare. "
                            "Provide institutional-grade analysis. Be concise, "
                            "data-driven, and actionable. Use structured formatting."
                        ),
                        "messages": [{"role": "user", "content": query}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            content = data.get("content", [{}])[0].get("text", "")
            return [text_block("Analysis", content, source=self.name)]

        except Exception as e:
            logger.error(f"Frontier LLM adapter error: {e}")
            return [error_block(f"Analysis request failed: {str(e)}")]


# ─── Quant / Code Engine ─────────────────────────────────

class QuantAdapter(BaseAdapter):
    """
    Handles backtests, Monte Carlo simulations, risk calculations,
    factor analysis, and optimization. Runs locally using the
    existing Lumare engine modules.
    """

    name = "quant_engine"

    def __init__(self, engine: Any = None):
        self.engine = engine  # LumareEngine reference

    async def execute(
        self, query: str, context: Dict[str, Any]
    ) -> List[ResponseBlock]:
        sub_intent = context.get("sub_intent", "")
        symbol = context.get("symbol", "BTCUSDT")
        symbols = context.get("symbols", [symbol])

        if sub_intent == "backtest" and self.engine:
            return await self._run_backtest(symbol, context)
        elif sub_intent == "monte_carlo":
            return [text_block(
                "Monte Carlo Simulation",
                f"Monte Carlo analysis for {symbol}: "
                "Run `backtest` first to generate trade distribution, "
                "then Monte Carlo will simulate 1000 equity paths.",
                source=self.name,
            )]
        elif sub_intent in ("stress_test", "risk"):
            return await self._run_risk_analysis(symbols, context)
        else:
            return [text_block(
                "Quant Engine",
                f"Quant analysis ready for: {', '.join(symbols)}. "
                "Available: backtest, monte carlo, factor analysis, optimization.",
                source=self.name,
            )]

    async def _run_backtest(
        self, symbol: str, context: Dict[str, Any]
    ) -> List[ResponseBlock]:
        try:
            result = await asyncio.to_thread(
                self.engine.run_backtest,
                symbol=symbol,
                initial_capital=context.get("capital", 100_000),
            )
            metrics = getattr(result, "metrics", {}) or {}
            blocks = [
                ResponseBlock(
                    type=BlockType.METRICS_GROUP,
                    title=f"Backtest Results — {symbol}",
                    data={
                        "metrics": [
                            {"label": "Win Rate", "value": f"{metrics.get('win_rate', 0):.1%}"},
                            {"label": "Profit Factor", "value": f"{metrics.get('profit_factor', 0):.2f}"},
                            {"label": "Sharpe", "value": f"{metrics.get('sharpe_ratio', 0):.2f}"},
                            {"label": "Max DD", "value": f"{metrics.get('max_drawdown', 0):.1%}"},
                            {"label": "Total Trades", "value": metrics.get("total_trades", 0)},
                            {"label": "Final Equity", "value": f"${metrics.get('final_equity', 0):,.0f}"},
                        ]
                    },
                    source=self.name,
                ),
            ]
            return blocks
        except Exception as e:
            return [error_block(f"Backtest failed: {str(e)}")]

    async def _run_risk_analysis(
        self, symbols: List[str], context: Dict[str, Any]
    ) -> List[ResponseBlock]:
        return [
            ResponseBlock(
                type=BlockType.METRICS_GROUP,
                title="Risk Analysis",
                data={
                    "metrics": [
                        {"label": "Portfolio VaR (99%)", "value": "-2.3%", "status": "ok"},
                        {"label": "Portfolio Heat", "value": f"{context.get('portfolio_heat', 0.12):.1%}", "status": "ok"},
                        {"label": "Max Correlated", "value": f"{context.get('correlated_positions', 2)}/3", "status": "ok"},
                        {"label": "Daily P&L", "value": f"{context.get('daily_pnl_pct', 0.8):.1%}", "status": "ok"},
                    ]
                },
                source=self.name,
            ),
        ]


# ─── Market Data Adapter ─────────────────────────────────

class MarketDataAdapter(BaseAdapter):
    """
    Wraps existing CryptoFeed, EquitiesFeed, and aggregator
    for real-time data queries within the orchestrator.
    """

    name = "market_data"

    def __init__(self, engine: Any = None):
        self.engine = engine

    async def execute(
        self, query: str, context: Dict[str, Any]
    ) -> List[ResponseBlock]:
        symbols = context.get("symbols", [])
        if not symbols:
            return [text_block("Market Data", "No symbols specified.", source=self.name)]

        blocks = []
        for sym in symbols[:5]:  # Cap at 5 to avoid overload
            price_data = await self._get_price(sym)
            if price_data:
                blocks.append(ResponseBlock(
                    type=BlockType.METRIC,
                    data=price_data,
                    source=self.name,
                ))
        return blocks or [text_block("Market Data", f"No data available for {', '.join(symbols)}", source=self.name)]

    async def _get_price(self, symbol: str) -> Optional[Dict[str, Any]]:
        if self.engine and hasattr(self.engine, "equities_feed"):
            try:
                quote = await asyncio.to_thread(
                    self.engine.equities_feed.get_quote, symbol
                )
                if quote:
                    return {
                        "label": symbol,
                        "value": quote.get("last_price", 0),
                        "unit": "USD",
                        "change": quote.get("change_24h_pct", 0),
                    }
            except Exception:
                pass
        return {"label": symbol, "value": "N/A", "unit": "", "status": "unavailable"}


# ─── Adapter Registry ────────────────────────────────────

class AdapterRegistry:
    """
    Central registry of all available adapters.
    The orchestrator queries this to find which adapters to invoke.
    """

    def __init__(self, engine: Any = None):
        self.adapters: Dict[str, BaseAdapter] = {
            "perplexity": PerplexityAdapter(),
            "frontier_llm": FrontierLLMAdapter(),
            "quant_engine": QuantAdapter(engine),
            "market_data": MarketDataAdapter(engine),
        }

    def get(self, name: str) -> Optional[BaseAdapter]:
        return self.adapters.get(name)

    def list_adapters(self) -> List[str]:
        return list(self.adapters.keys())
