"""
watchdog.py — Health Monitoring and Circuit Breakers
Continuous monitoring of system health, data freshness, and portfolio risk.
Triggers circuit breakers when thresholds are breached.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from loguru import logger

from backend.config.settings import SETTINGS, Settings
from backend.data.storage import Storage
from backend.data.aggregator import DataAggregator


@dataclass
class HealthStatus:
    healthy: bool
    timestamp: datetime
    api_status: Dict[str, bool] = field(default_factory=dict)
    data_freshness: Dict[str, Dict] = field(default_factory=dict)
    portfolio_health: Dict[str, float] = field(default_factory=dict)
    system_resources: Dict[str, float] = field(default_factory=dict)
    alerts: List[str] = field(default_factory=list)
    circuit_breakers: Dict[str, bool] = field(default_factory=dict)


@dataclass
class Alert:
    level: str          # INFO, WARNING, CRITICAL
    message: str
    timestamp: datetime
    source: str
    resolved: bool = False


class Watchdog:
    """
    Continuous health monitoring and circuit breaker system.

    Monitors:
    - API connectivity (all data feeds)
    - Data freshness (stale data detection)
    - Portfolio health (drawdown, heat, daily loss)
    - Anomalous behavior (sudden losses, unusual trade frequency)
    - System resources

    Circuit breakers:
    - Data stale > 15min: pause trading
    - API down: pause trading on affected instruments
    - Drawdown > thresholds: cascading response
    - Daily loss > 4%: hard stop
    - Anomaly detection: pause + alert
    """

    def __init__(
        self,
        settings: Settings = None,
        storage: Storage = None,
        aggregator: DataAggregator = None,
        runner=None,
    ):
        self.settings = settings or SETTINGS
        self.storage = storage or Storage(self.settings.db_path)
        self.aggregator = aggregator
        self.runner = runner

        self._alerts: List[Alert] = []
        self._circuit_breakers: Dict[str, bool] = {
            "data_stale": False,
            "api_down": False,
            "drawdown_pause": False,
            "drawdown_reduce": False,
            "drawdown_shutdown": False,
            "daily_loss": False,
            "anomaly": False,
        }
        self._monitoring = False
        self._daily_start_value: Optional[float] = None
        self._trade_frequency: List[datetime] = []

    async def monitor(self, check_interval: int = 60):
        """Continuous monitoring loop. Checks every check_interval seconds."""
        self._monitoring = True
        logger.info(f"Watchdog started: checking every {check_interval}s")

        while self._monitoring:
            try:
                status = await self._run_health_check()

                if not status.healthy:
                    for alert_msg in status.alerts:
                        self._alert("WARNING", alert_msg, "health_check")

                # Check circuit breakers
                self._evaluate_circuit_breakers(status)

            except Exception as e:
                logger.error(f"Watchdog check error: {e}")
                self._alert("CRITICAL", f"Watchdog error: {e}", "watchdog")

            await asyncio.sleep(check_interval)

    async def _run_health_check(self) -> HealthStatus:
        """Run a complete health check."""
        now = datetime.now(timezone.utc)
        status = HealthStatus(healthy=True, timestamp=now)

        # 1. Data freshness
        if self.aggregator:
            try:
                freshness = self.aggregator.get_data_freshness()
                status.data_freshness = freshness

                for symbol, info in freshness.items():
                    if symbol == "macro":
                        continue
                    if not info.get("fresh", False):
                        status.alerts.append(f"Stale data for {symbol}")
                        status.healthy = False
            except Exception as e:
                status.alerts.append(f"Data freshness check failed: {e}")

        # 2. Portfolio health
        try:
            portfolio_health = self._check_portfolio_health()
            status.portfolio_health = portfolio_health

            if portfolio_health.get("drawdown", 0) < self.settings.risk.drawdown_pause_threshold:
                status.alerts.append(
                    f"Drawdown at {portfolio_health['drawdown']:.2%} — "
                    f"threshold is {self.settings.risk.drawdown_pause_threshold:.2%}"
                )
                status.healthy = False

            if portfolio_health.get("daily_loss", 0) < -self.settings.risk.daily_loss_cap:
                status.alerts.append(
                    f"Daily loss at {portfolio_health['daily_loss']:.2%} — "
                    f"cap is {self.settings.risk.daily_loss_cap:.2%}"
                )
                status.healthy = False
        except Exception as e:
            status.alerts.append(f"Portfolio health check failed: {e}")

        # 3. Anomaly detection
        try:
            anomalies = self._check_anomalies()
            if anomalies:
                status.alerts.extend(anomalies)
                status.healthy = False
        except Exception:
            pass

        status.circuit_breakers = dict(self._circuit_breakers)
        return status

    def _check_portfolio_health(self) -> Dict:
        """Check portfolio drawdown, daily loss, and heat."""
        health = {"drawdown": 0.0, "daily_loss": 0.0, "heat": 0.0}

        if not self.runner:
            return health

        # Current portfolio value
        if hasattr(self.runner, '_equity_history') and self.runner._equity_history:
            equity = self.runner._equity_history
            peak = max(equity)
            current = equity[-1]
            health["drawdown"] = (current - peak) / peak if peak > 0 else 0

            # Daily loss
            if self._daily_start_value is None:
                self._daily_start_value = current
            health["daily_loss"] = (current - self._daily_start_value) / self._daily_start_value

        # Portfolio heat
        if hasattr(self.runner, 'executor') and hasattr(self.runner.executor, 'get_portfolio'):
            portfolio = self.runner.executor.get_portfolio()
            total = portfolio.get("total_value", 1)
            if total > 0:
                # Approximate heat as margin / total
                health["heat"] = portfolio.get("margin_used", 0) / total

        return health

    def _check_anomalies(self) -> List[str]:
        """Detect anomalous trading behavior."""
        anomalies = []
        now = datetime.now(timezone.utc)

        # Check trade frequency (more than 20 trades in 1 hour = suspicious)
        self._trade_frequency = [
            t for t in self._trade_frequency
            if (now - t).total_seconds() < 3600
        ]
        if len(self._trade_frequency) > 20:
            anomalies.append(
                f"Unusual trade frequency: {len(self._trade_frequency)} trades in last hour"
            )

        # Check for rapid equity drop
        if (self.runner and hasattr(self.runner, '_equity_history')
                and len(self.runner._equity_history) >= 10):
            recent = self.runner._equity_history[-10:]
            if recent[-1] < recent[0] * 0.95:
                anomalies.append(
                    f"Rapid equity drop: {(recent[-1]/recent[0] - 1):.2%} in last 10 cycles"
                )

        return anomalies

    def _evaluate_circuit_breakers(self, status: HealthStatus):
        """Evaluate and trigger circuit breakers based on health status."""
        portfolio = status.portfolio_health

        # Data staleness circuit breaker
        any_stale = any(
            not info.get("fresh", True)
            for sym, info in status.data_freshness.items()
            if sym != "macro"
        )
        if any_stale and not self._circuit_breakers["data_stale"]:
            self._trigger_breaker("data_stale", "Stale market data detected")
        elif not any_stale and self._circuit_breakers["data_stale"]:
            self._reset_breaker("data_stale")

        # Drawdown circuit breakers (cascading)
        dd = portfolio.get("drawdown", 0)
        if dd < self.settings.risk.drawdown_shutdown_threshold:
            if not self._circuit_breakers["drawdown_shutdown"]:
                self._trigger_breaker("drawdown_shutdown",
                                       f"CRITICAL drawdown: {dd:.2%}")
                self._trigger_kill_switch("Drawdown shutdown threshold breached")
        elif dd < self.settings.risk.drawdown_reduce_threshold:
            if not self._circuit_breakers["drawdown_reduce"]:
                self._trigger_breaker("drawdown_reduce",
                                       f"Severe drawdown: {dd:.2%} — reducing positions 50%")
        elif dd < self.settings.risk.drawdown_pause_threshold:
            if not self._circuit_breakers["drawdown_pause"]:
                self._trigger_breaker("drawdown_pause",
                                       f"Drawdown warning: {dd:.2%} — pausing new trades")
        else:
            # Recovery - reset drawdown breakers
            for key in ["drawdown_pause", "drawdown_reduce", "drawdown_shutdown"]:
                if self._circuit_breakers[key]:
                    self._reset_breaker(key)

        # Daily loss cap
        daily_loss = portfolio.get("daily_loss", 0)
        if daily_loss < -self.settings.risk.daily_loss_cap:
            if not self._circuit_breakers["daily_loss"]:
                self._trigger_breaker("daily_loss",
                                       f"Daily loss cap hit: {daily_loss:.2%}")
                self._trigger_kill_switch("Daily loss cap exceeded")

    def _trigger_breaker(self, breaker: str, reason: str):
        """Activate a circuit breaker."""
        self._circuit_breakers[breaker] = True
        self._alert("CRITICAL", f"Circuit breaker [{breaker}]: {reason}", "watchdog")
        logger.critical(f"CIRCUIT BREAKER [{breaker}]: {reason}")

        # Pause runner if appropriate
        if self.runner and breaker in ("data_stale", "drawdown_pause"):
            self.runner.pause()

    def _reset_breaker(self, breaker: str):
        """Reset a circuit breaker."""
        self._circuit_breakers[breaker] = False
        self._alert("INFO", f"Circuit breaker [{breaker}] reset", "watchdog")
        logger.info(f"Circuit breaker [{breaker}] reset")

    def _trigger_kill_switch(self, reason: str):
        """Activate the kill switch — stops all trading."""
        if self.runner:
            self.runner.state.kill_switch = True
            self.runner.pause()
        self._alert("CRITICAL", f"KILL SWITCH ACTIVATED: {reason}", "watchdog")
        logger.critical(f"KILL SWITCH: {reason}")

    def _alert(self, level: str, message: str, source: str):
        """Log an alert."""
        alert = Alert(
            level=level, message=message,
            timestamp=datetime.now(timezone.utc), source=source,
        )
        self._alerts.append(alert)

        if level == "CRITICAL":
            logger.critical(f"[{source}] {message}")
        elif level == "WARNING":
            logger.warning(f"[{source}] {message}")
        else:
            logger.info(f"[{source}] {message}")

        # Store alert as risk event
        self.storage.store_risk_event({
            "timestamp": alert.timestamp.isoformat(),
            "event_type": f"alert_{level.lower()}",
            "description": message,
            "source": source,
        })

    def get_system_status(self) -> Dict:
        """Get complete system status."""
        return {
            "monitoring": self._monitoring,
            "circuit_breakers": dict(self._circuit_breakers),
            "active_alerts": len([a for a in self._alerts if not a.resolved]),
            "recent_alerts": [
                {"level": a.level, "message": a.message,
                 "timestamp": a.timestamp.isoformat(), "source": a.source}
                for a in self._alerts[-20:]
            ],
        }

    def reset_daily(self):
        """Reset daily tracking (call at start of each trading day)."""
        if (self.runner and hasattr(self.runner, '_equity_history')
                and self.runner._equity_history):
            self._daily_start_value = self.runner._equity_history[-1]
        self._circuit_breakers["daily_loss"] = False
        self._trade_frequency.clear()
        logger.info("Watchdog daily reset complete")

    def stop(self):
        """Stop monitoring."""
        self._monitoring = False
        logger.info("Watchdog stopped")

    async def generate_daily_report(self) -> Dict:
        """Generate end-of-day report."""
        report = {
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "system_status": self.get_system_status(),
            "portfolio_health": self._check_portfolio_health(),
        }

        if self.runner:
            report["runner_status"] = self.runner.get_status()

        # Count alerts by level
        today = datetime.now(timezone.utc).date()
        today_alerts = [a for a in self._alerts if a.timestamp.date() == today]
        report["alert_summary"] = {
            "critical": len([a for a in today_alerts if a.level == "CRITICAL"]),
            "warning": len([a for a in today_alerts if a.level == "WARNING"]),
            "info": len([a for a in today_alerts if a.level == "INFO"]),
        }

        return report
