"""
Lumare Risk Analytics Engine — Institutional-grade portfolio risk calculations.

Provides:
  - Value at Risk (Historical, Parametric, Monte Carlo)
  - Stress Testing (predefined + custom scenarios)
  - Correlation Matrix
  - Risk Metrics (Beta, Sortino, Max Drawdown, Calmar, CVaR)
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ═══════════════════════════════════════════════════════════
# Synthetic Data Generation
# ═══════════════════════════════════════════════════════════

# Default portfolio holdings for synthetic generation
DEFAULT_HOLDINGS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "SPY"]

# Realistic annualized return / vol profiles per ticker
_TICKER_PROFILES: Dict[str, Tuple[float, float]] = {
    "AAPL":  (0.18, 0.28),
    "MSFT":  (0.20, 0.26),
    "NVDA":  (0.35, 0.55),
    "GOOGL": (0.15, 0.30),
    "AMZN":  (0.16, 0.32),
    "META":  (0.22, 0.40),
    "TSLA":  (0.12, 0.60),
    "SPY":   (0.10, 0.16),
    "BTC":   (0.25, 0.65),
    "ETH":   (0.20, 0.75),
}


def _get_profile(symbol: str) -> Tuple[float, float]:
    """Return (annualized_return, annualized_vol) for a symbol."""
    return _TICKER_PROFILES.get(symbol, (0.10, 0.25))


def generate_daily_returns(
    symbols: List[str],
    days: int = 252,
    seed: int = 42,
) -> Dict[str, np.ndarray]:
    """
    Generate correlated synthetic daily returns for a set of symbols.
    Uses a Cholesky decomposition on a realistic correlation structure.
    """
    rng = np.random.default_rng(seed)
    n = len(symbols)

    # Build a realistic correlation matrix (tech stocks are highly correlated)
    base_corr = np.full((n, n), 0.55)
    np.fill_diagonal(base_corr, 1.0)

    # Make SPY slightly less correlated with individual names
    for i, s in enumerate(symbols):
        if s == "SPY":
            for j in range(n):
                if i != j:
                    base_corr[i, j] = 0.75
                    base_corr[j, i] = 0.75

    # Crypto less correlated with equities
    for i, si in enumerate(symbols):
        for j, sj in enumerate(symbols):
            if i != j:
                if si in ("BTC", "ETH") and sj not in ("BTC", "ETH"):
                    base_corr[i, j] = 0.25
                    base_corr[j, i] = 0.25
                elif si in ("BTC", "ETH") and sj in ("BTC", "ETH"):
                    base_corr[i, j] = 0.80
                    base_corr[j, i] = 0.80

    # Cholesky decomposition for correlated normals
    try:
        L = np.linalg.cholesky(base_corr)
    except np.linalg.LinAlgError:
        # Fallback: make correlation matrix positive-definite
        eigvals, eigvecs = np.linalg.eigh(base_corr)
        eigvals = np.maximum(eigvals, 1e-6)
        base_corr = eigvecs @ np.diag(eigvals) @ eigvecs.T
        np.fill_diagonal(base_corr, 1.0)
        L = np.linalg.cholesky(base_corr)

    uncorrelated = rng.standard_normal((days, n))
    correlated = uncorrelated @ L.T

    result: Dict[str, np.ndarray] = {}
    for i, symbol in enumerate(symbols):
        mu_annual, sigma_annual = _get_profile(symbol)
        mu_daily = mu_annual / 252
        sigma_daily = sigma_annual / math.sqrt(252)
        result[symbol] = mu_daily + sigma_daily * correlated[:, i]

    return result


def generate_portfolio_returns(
    symbols: Optional[List[str]] = None,
    weights: Optional[List[float]] = None,
    days: int = 252,
    seed: int = 42,
) -> np.ndarray:
    """Generate synthetic portfolio-level daily returns."""
    if symbols is None:
        symbols = DEFAULT_HOLDINGS[:6]
    if weights is None:
        n = len(symbols)
        weights = [1.0 / n] * n

    asset_returns = generate_daily_returns(symbols, days, seed)
    w = np.array(weights)
    returns_matrix = np.column_stack([asset_returns[s] for s in symbols])
    return returns_matrix @ w


# ═══════════════════════════════════════════════════════════
# Value at Risk
# ═══════════════════════════════════════════════════════════

class VaRCalculator:
    """Value at Risk calculations using multiple methodologies."""

    def __init__(
        self,
        portfolio_returns: np.ndarray,
        portfolio_value: float = 100_000.0,
    ):
        self.returns = portfolio_returns
        self.portfolio_value = portfolio_value

    def historical(self, confidence: float = 0.95) -> Dict[str, Any]:
        """
        Historical VaR — uses empirical distribution of returns.
        """
        alpha = 1.0 - confidence
        var_pct = float(np.percentile(self.returns, alpha * 100))
        var_dollar = abs(var_pct * self.portfolio_value)
        return {
            "method": "Historical",
            "confidence": confidence,
            "var_pct": round(var_pct * 100, 4),
            "var_dollar": round(var_dollar, 2),
            "observation_days": len(self.returns),
        }

    def parametric(self, confidence: float = 0.95) -> Dict[str, Any]:
        """
        Parametric (Variance-Covariance) VaR — assumes normal distribution.
        """
        from scipy.stats import norm
        mu = float(np.mean(self.returns))
        sigma = float(np.std(self.returns, ddof=1))
        z = norm.ppf(1.0 - confidence)
        var_pct = mu + z * sigma
        var_dollar = abs(var_pct * self.portfolio_value)
        return {
            "method": "Parametric",
            "confidence": confidence,
            "var_pct": round(var_pct * 100, 4),
            "var_dollar": round(var_dollar, 2),
            "mean_return": round(mu * 100, 4),
            "std_dev": round(sigma * 100, 4),
        }

    def monte_carlo(
        self,
        confidence: float = 0.95,
        simulations: int = 1000,
        horizon: int = 1,
        seed: int = 99,
    ) -> Dict[str, Any]:
        """
        Monte Carlo VaR — geometric Brownian motion simulation.
        """
        rng = np.random.default_rng(seed)
        mu = float(np.mean(self.returns))
        sigma = float(np.std(self.returns, ddof=1))

        # Simulate terminal portfolio values using GBM
        dt = 1.0  # daily steps
        Z = rng.standard_normal((simulations, horizon))
        drift = (mu - 0.5 * sigma ** 2) * dt
        diffusion = sigma * np.sqrt(dt) * Z
        log_returns = np.sum(drift + diffusion, axis=1)
        simulated_values = self.portfolio_value * np.exp(log_returns)
        simulated_pnl = simulated_values - self.portfolio_value

        alpha = 1.0 - confidence
        var_dollar = abs(float(np.percentile(simulated_pnl, alpha * 100)))
        var_pct = var_dollar / self.portfolio_value

        return {
            "method": "Monte Carlo",
            "confidence": confidence,
            "var_pct": round(var_pct * 100, 4),
            "var_dollar": round(var_dollar, 2),
            "simulations": simulations,
            "horizon_days": horizon,
            "mean_pnl": round(float(np.mean(simulated_pnl)), 2),
            "worst_case": round(float(np.min(simulated_pnl)), 2),
            "best_case": round(float(np.max(simulated_pnl)), 2),
        }

    def all_methods(self, confidence: float = 0.95) -> Dict[str, Any]:
        """Run all three VaR methods and return combined results."""
        return {
            "historical": self.historical(confidence),
            "parametric": self.parametric(confidence),
            "monte_carlo": self.monte_carlo(confidence),
            "portfolio_value": self.portfolio_value,
            "confidence": confidence,
        }


# ═══════════════════════════════════════════════════════════
# Stress Testing
# ═══════════════════════════════════════════════════════════

PREDEFINED_SCENARIOS = [
    {
        "name": "2008 Financial Crisis",
        "drawdown": -0.38,
        "description": "Credit crisis, Lehman collapse, systemic bank failures. S&P 500 peak-to-trough -57% over 17 months.",
        "duration": "17 months",
        "vix_peak": 80,
    },
    {
        "name": "COVID Crash (2020)",
        "drawdown": -0.34,
        "description": "Global pandemic lockdowns triggered fastest 30% decline in history. Recovery in 5 months.",
        "duration": "33 days",
        "vix_peak": 82,
    },
    {
        "name": "Dot-com Burst (2000)",
        "drawdown": -0.49,
        "description": "Tech bubble collapse. NASDAQ lost 78% over 30 months. Broad market -49%.",
        "duration": "30 months",
        "vix_peak": 45,
    },
    {
        "name": "Flash Crash (2010)",
        "drawdown": -0.09,
        "description": "Algorithmic cascade caused 9% drop in minutes. Dow dropped ~1000 points intraday.",
        "duration": "36 minutes",
        "vix_peak": 40,
    },
    {
        "name": "Rate Shock",
        "drawdown": -0.15,
        "description": "Sudden 200bp rate hike scenario. Growth/tech equities hit hardest. Duration risk materializes.",
        "duration": "3-6 months",
        "vix_peak": 35,
    },
]


class StressTester:
    """Run stress test scenarios against portfolio."""

    def __init__(
        self,
        portfolio_value: float = 100_000.0,
        beta: float = 1.0,
    ):
        self.portfolio_value = portfolio_value
        self.beta = beta

    def run_scenario(self, name: str, drawdown: float, description: str, **kwargs) -> Dict[str, Any]:
        """
        Calculate portfolio impact for a single scenario.
        Portfolio impact = market drawdown * portfolio beta * portfolio value.
        """
        portfolio_impact_pct = drawdown * self.beta
        portfolio_impact_dollar = self.portfolio_value * portfolio_impact_pct
        remaining_value = self.portfolio_value + portfolio_impact_dollar
        survives = remaining_value > 0

        return {
            "scenario": name,
            "market_drawdown_pct": round(drawdown * 100, 2),
            "portfolio_impact_pct": round(portfolio_impact_pct * 100, 2),
            "portfolio_impact_dollar": round(portfolio_impact_dollar, 2),
            "remaining_value": round(remaining_value, 2),
            "description": description,
            "survives": survives,
            "duration": kwargs.get("duration", "N/A"),
            "vix_peak": kwargs.get("vix_peak"),
        }

    def run_all_predefined(self) -> List[Dict[str, Any]]:
        """Run all predefined stress scenarios."""
        return [self.run_scenario(**s) for s in PREDEFINED_SCENARIOS]

    def run_custom(self, name: str, drawdown_pct: float) -> Dict[str, Any]:
        """Run a custom stress test with user-specified drawdown."""
        return self.run_scenario(
            name=name,
            drawdown=drawdown_pct / 100.0,
            description=f"Custom scenario: {drawdown_pct}% market drawdown",
        )


# ═══════════════════════════════════════════════════════════
# Correlation Matrix
# ═══════════════════════════════════════════════════════════

def compute_correlation_matrix(
    symbols: Optional[List[str]] = None,
    days: int = 252,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Calculate pairwise correlation between portfolio holdings.
    Returns nested dict for frontend rendering.
    """
    if symbols is None:
        symbols = DEFAULT_HOLDINGS

    asset_returns = generate_daily_returns(symbols, days, seed)
    returns_matrix = np.column_stack([asset_returns[s] for s in symbols])
    corr_matrix = np.corrcoef(returns_matrix, rowvar=False)

    # Build nested dict: { "AAPL": { "AAPL": 1.0, "MSFT": 0.72, ... }, ... }
    matrix_dict: Dict[str, Dict[str, float]] = {}
    for i, si in enumerate(symbols):
        matrix_dict[si] = {}
        for j, sj in enumerate(symbols):
            matrix_dict[si][sj] = round(float(corr_matrix[i, j]), 4)

    return {
        "symbols": symbols,
        "matrix": matrix_dict,
        "observation_days": days,
    }


# ═══════════════════════════════════════════════════════════
# Risk Metrics
# ═══════════════════════════════════════════════════════════

class RiskMetricsCalculator:
    """Comprehensive risk metrics for institutional reporting."""

    def __init__(
        self,
        portfolio_returns: np.ndarray,
        benchmark_returns: Optional[np.ndarray] = None,
        risk_free_rate: float = 0.05,
        portfolio_value: float = 100_000.0,
    ):
        self.returns = portfolio_returns
        self.benchmark = benchmark_returns
        self.rf_daily = risk_free_rate / 252
        self.portfolio_value = portfolio_value

    def beta(self) -> float:
        """Portfolio beta vs benchmark (SPY)."""
        if self.benchmark is None or len(self.benchmark) != len(self.returns):
            return 1.0
        cov = np.cov(self.returns, self.benchmark)
        var_benchmark = cov[1, 1]
        if var_benchmark == 0:
            return 1.0
        return round(float(cov[0, 1] / var_benchmark), 4)

    def sortino_ratio(self) -> float:
        """
        Sortino Ratio — like Sharpe but only penalizes downside volatility.
        """
        excess = self.returns - self.rf_daily
        mean_excess = float(np.mean(excess))
        downside = excess[excess < 0]
        if len(downside) < 2:
            return 0.0
        downside_std = float(np.std(downside, ddof=1))
        if downside_std == 0:
            return 0.0
        return round(float(mean_excess / downside_std * math.sqrt(252)), 4)

    def max_drawdown(self) -> Dict[str, Any]:
        """
        Maximum drawdown from equity curve (rolling).
        Returns both the max drawdown percentage and the drawdown series.
        """
        cumulative = np.cumprod(1.0 + self.returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        max_dd = float(np.min(drawdowns))
        max_dd_idx = int(np.argmin(drawdowns))

        # Find the peak before the max drawdown
        peak_idx = int(np.argmax(cumulative[:max_dd_idx + 1])) if max_dd_idx > 0 else 0

        return {
            "max_drawdown_pct": round(max_dd * 100, 4),
            "peak_day": peak_idx,
            "trough_day": max_dd_idx,
            "recovery_days": len(self.returns) - max_dd_idx,
            "current_drawdown_pct": round(float(drawdowns[-1]) * 100, 4),
        }

    def calmar_ratio(self) -> float:
        """
        Calmar Ratio — annualized return / max drawdown.
        Higher is better; measures return per unit of drawdown risk.
        """
        annualized_return = float(np.mean(self.returns)) * 252
        dd_info = self.max_drawdown()
        max_dd = abs(dd_info["max_drawdown_pct"] / 100)
        if max_dd == 0:
            return 0.0
        return round(annualized_return / max_dd, 4)

    def cvar(self, confidence: float = 0.95) -> Dict[str, Any]:
        """
        Conditional VaR (CVaR) / Expected Shortfall.
        Average loss beyond the VaR threshold — captures tail risk.
        """
        alpha = 1.0 - confidence
        var_threshold = float(np.percentile(self.returns, alpha * 100))
        tail_losses = self.returns[self.returns <= var_threshold]
        if len(tail_losses) == 0:
            cvar_pct = var_threshold
        else:
            cvar_pct = float(np.mean(tail_losses))

        cvar_dollar = abs(cvar_pct * self.portfolio_value)
        return {
            "confidence": confidence,
            "cvar_pct": round(cvar_pct * 100, 4),
            "cvar_dollar": round(cvar_dollar, 2),
            "var_pct": round(var_threshold * 100, 4),
            "tail_observations": int(len(tail_losses)),
        }

    def all_metrics(self) -> Dict[str, Any]:
        """Compute all risk metrics in one call."""
        dd = self.max_drawdown()
        cvar_95 = self.cvar(0.95)
        cvar_99 = self.cvar(0.99)

        return {
            "beta": self.beta(),
            "sortino_ratio": self.sortino_ratio(),
            "max_drawdown": dd,
            "calmar_ratio": self.calmar_ratio(),
            "cvar_95": cvar_95,
            "cvar_99": cvar_99,
            "annualized_return": round(float(np.mean(self.returns)) * 252 * 100, 4),
            "annualized_volatility": round(float(np.std(self.returns, ddof=1)) * math.sqrt(252) * 100, 4),
            "portfolio_value": self.portfolio_value,
        }


# ═══════════════════════════════════════════════════════════
# Facade — single entry point for all risk analytics
# ═══════════════════════════════════════════════════════════

class RiskAnalyticsEngine:
    """
    Top-level facade that wires together all risk sub-systems.
    Generates synthetic data when real data is unavailable.
    """

    def __init__(
        self,
        portfolio_value: float = 100_000.0,
        holdings: Optional[List[str]] = None,
        weights: Optional[List[float]] = None,
        days: int = 252,
        seed: int = 42,
    ):
        self.portfolio_value = portfolio_value
        self.holdings = holdings or DEFAULT_HOLDINGS[:6]
        self.weights = weights
        self.days = days
        self.seed = seed

        # Generate synthetic returns
        self._asset_returns = generate_daily_returns(self.holdings, days, seed)
        self._portfolio_returns = generate_portfolio_returns(
            self.holdings, self.weights, days, seed
        )

        # SPY benchmark
        spy_returns = generate_daily_returns(["SPY"], days, seed)
        self._benchmark_returns = spy_returns["SPY"]

        # Sub-engines
        self.var = VaRCalculator(self._portfolio_returns, portfolio_value)
        self.stress = StressTester(
            portfolio_value,
            beta=self._compute_beta(),
        )
        self.metrics = RiskMetricsCalculator(
            self._portfolio_returns,
            self._benchmark_returns,
            portfolio_value=portfolio_value,
        )

    def _compute_beta(self) -> float:
        """Quick beta computation for stress tester."""
        if len(self._benchmark_returns) != len(self._portfolio_returns):
            return 1.0
        cov = np.cov(self._portfolio_returns, self._benchmark_returns)
        var_b = cov[1, 1]
        if var_b == 0:
            return 1.0
        return float(cov[0, 1] / var_b)

    def get_var(self, confidence: float = 0.95) -> Dict[str, Any]:
        """Get VaR across all methods."""
        return self.var.all_methods(confidence)

    def get_stress_tests(self) -> List[Dict[str, Any]]:
        """Run all predefined stress scenarios."""
        return self.stress.run_all_predefined()

    def get_correlation(self) -> Dict[str, Any]:
        """Get correlation matrix for holdings."""
        return compute_correlation_matrix(self.holdings, self.days, self.seed)

    def get_metrics(self) -> Dict[str, Any]:
        """Get all risk metrics."""
        return self.metrics.all_metrics()
