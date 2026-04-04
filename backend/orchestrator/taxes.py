"""
Lumare Tax Estimation Engine

Tracks cost basis (FIFO, LIFO, specific-id), computes realized / unrealized
gains, estimates federal tax liability, detects wash sales, and surfaces
tax-loss harvesting candidates.
"""

import os
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Optional


# ─── 2024 Federal Tax Brackets ────────────────────────────

# Long-term capital gains brackets by filing status
# (threshold, rate) — rate applies to income ABOVE previous threshold
LTCG_BRACKETS = {
    "single": [
        (0, 0.00),
        (47_025, 0.15),
        (518_900, 0.20),
    ],
    "married_filing_jointly": [
        (0, 0.00),
        (94_050, 0.15),
        (583_750, 0.20),
    ],
    "head_of_household": [
        (0, 0.00),
        (63_000, 0.15),
        (551_350, 0.20),
    ],
}

# Short-term (ordinary income) brackets by filing status
ORDINARY_BRACKETS = {
    "single": [
        (0, 0.10),
        (11_600, 0.12),
        (47_150, 0.22),
        (100_525, 0.24),
        (191_950, 0.32),
        (243_725, 0.35),
        (609_350, 0.37),
    ],
    "married_filing_jointly": [
        (0, 0.10),
        (23_200, 0.12),
        (94_300, 0.22),
        (201_050, 0.24),
        (383_900, 0.32),
        (487_450, 0.35),
        (731_200, 0.37),
    ],
    "head_of_household": [
        (0, 0.10),
        (16_550, 0.12),
        (63_100, 0.22),
        (100_500, 0.24),
        (191_950, 0.32),
        (243_700, 0.35),
        (609_350, 0.37),
    ],
}


def _compute_bracket_tax(amount: float, brackets: list[tuple[float, float]]) -> float:
    """Progressive tax computation across bracket thresholds."""
    if amount <= 0:
        return 0.0
    tax = 0.0
    for i, (threshold, rate) in enumerate(brackets):
        next_threshold = brackets[i + 1][0] if i + 1 < len(brackets) else float("inf")
        taxable_in_bracket = min(amount, next_threshold) - threshold
        if taxable_in_bracket <= 0:
            break
        tax += taxable_in_bracket * rate
    return round(tax, 2)


class TaxEngine:
    """SQLite-backed tax lot tracker and estimator."""

    def __init__(self, db_path: str = "data/lumare_taxes.db"):
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    # ── Schema ────────────────────────────────────────────

    def _init_tables(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tax_lots (
                lot_id       TEXT PRIMARY KEY,
                symbol       TEXT NOT NULL,
                quantity     REAL NOT NULL,
                entry_price  REAL NOT NULL,
                entry_date   TEXT NOT NULL,
                side         TEXT NOT NULL DEFAULT 'long',
                exit_price   REAL,
                exit_date    TEXT,
                status       TEXT NOT NULL DEFAULT 'open',
                gain_loss    REAL,
                term         TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_lots_symbol ON tax_lots(symbol);
            CREATE INDEX IF NOT EXISTS idx_lots_status ON tax_lots(status);
            CREATE INDEX IF NOT EXISTS idx_lots_exit_date ON tax_lots(exit_date);
            """
        )
        self.conn.commit()

    # ── Record & Close ────────────────────────────────────

    def record_lot(
        self,
        symbol: str,
        quantity: float,
        price: float,
        date: str,
        side: str = "long",
    ) -> str:
        """Record a new tax lot. Returns the lot_id."""
        lot_id = str(uuid.uuid4())[:12]
        self.conn.execute(
            """INSERT INTO tax_lots (lot_id, symbol, quantity, entry_price, entry_date, side, status)
               VALUES (?, ?, ?, ?, ?, ?, 'open')""",
            (lot_id, symbol.upper(), quantity, price, date, side),
        )
        self.conn.commit()
        return lot_id

    def close_lot(self, lot_id: str, exit_price: float, exit_date: str) -> dict:
        """Close a lot and compute gain/loss and holding period term."""
        row = self.conn.execute(
            "SELECT * FROM tax_lots WHERE lot_id = ?", (lot_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"Lot {lot_id} not found")
        if row["status"] == "closed":
            raise ValueError(f"Lot {lot_id} is already closed")

        entry_price = row["entry_price"]
        quantity = row["quantity"]
        side = row["side"]

        if side == "long":
            gain_loss = (exit_price - entry_price) * quantity
        else:
            gain_loss = (entry_price - exit_price) * quantity

        # Determine short-term vs long-term (1 year threshold)
        entry_dt = datetime.fromisoformat(row["entry_date"][:10])
        exit_dt = datetime.fromisoformat(exit_date[:10])
        holding_days = (exit_dt - entry_dt).days
        term = "long_term" if holding_days > 365 else "short_term"

        self.conn.execute(
            """UPDATE tax_lots
               SET exit_price = ?, exit_date = ?, status = 'closed',
                   gain_loss = ?, term = ?
               WHERE lot_id = ?""",
            (exit_price, exit_date, round(gain_loss, 2), term, lot_id),
        )
        self.conn.commit()

        return {
            "lot_id": lot_id,
            "symbol": row["symbol"],
            "gain_loss": round(gain_loss, 2),
            "term": term,
            "holding_days": holding_days,
        }

    # ── Queries ───────────────────────────────────────────

    def get_lots(
        self,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        year: Optional[int] = None,
    ) -> list[dict]:
        """Get tax lots with optional filters."""
        query = "SELECT * FROM tax_lots WHERE 1=1"
        params: list = []
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if status:
            query += " AND status = ?"
            params.append(status)
        if year and status == "closed":
            query += " AND exit_date LIKE ?"
            params.append(f"{year}%")
        elif year and status != "closed":
            query += " AND entry_date LIKE ?"
            params.append(f"{year}%")
        query += " ORDER BY entry_date DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_realized_gains(self, year: int) -> dict:
        """Returns short-term and long-term realized capital gains for a given year."""
        rows = self.conn.execute(
            """SELECT term, SUM(gain_loss) as total
               FROM tax_lots
               WHERE status = 'closed' AND exit_date LIKE ?
               GROUP BY term""",
            (f"{year}%",),
        ).fetchall()

        result = {"short_term": 0.0, "long_term": 0.0, "total": 0.0}
        for r in rows:
            if r["term"] == "short_term":
                result["short_term"] = round(r["total"], 2)
            elif r["term"] == "long_term":
                result["long_term"] = round(r["total"], 2)
        result["total"] = round(result["short_term"] + result["long_term"], 2)
        return result

    def get_unrealized_gains(
        self,
        positions: list[dict],
        current_prices: dict[str, float],
    ) -> list[dict]:
        """
        Estimate unrealized gains from open positions.
        positions: list of {symbol, quantity, entry_price, side}
        current_prices: {symbol: current_price}
        """
        results = []
        for pos in positions:
            symbol = pos.get("symbol", "").upper()
            price_now = current_prices.get(symbol)
            if price_now is None:
                continue
            entry = pos.get("entry_price", 0)
            qty = pos.get("quantity", 0)
            side = pos.get("side", "long")
            if side == "long":
                gain = (price_now - entry) * qty
            else:
                gain = (entry - price_now) * qty
            results.append({
                "symbol": symbol,
                "quantity": qty,
                "entry_price": entry,
                "current_price": price_now,
                "unrealized_gain": round(gain, 2),
                "side": side,
            })
        return results

    def estimate_tax_liability(
        self,
        year: int,
        filing_status: str = "single",
        income_bracket: float = 0.0,
    ) -> dict:
        """
        Estimate federal tax liability on capital gains.
        income_bracket: additional ordinary income (for bracket placement).
        """
        gains = self.get_realized_gains(year)
        st_gain = gains["short_term"]
        lt_gain = gains["long_term"]

        filing = filing_status.lower().replace(" ", "_")
        if filing not in LTCG_BRACKETS:
            filing = "single"

        # Short-term taxed as ordinary income (added on top of income_bracket)
        st_tax = _compute_bracket_tax(
            income_bracket + max(st_gain, 0), ORDINARY_BRACKETS[filing]
        ) - _compute_bracket_tax(income_bracket, ORDINARY_BRACKETS[filing])

        # Long-term capital gains tax
        lt_tax = _compute_bracket_tax(max(lt_gain, 0), LTCG_BRACKETS[filing])

        total_tax = round(st_tax + lt_tax, 2)
        total_gains = gains["total"]
        effective_rate = round((total_tax / total_gains) * 100, 2) if total_gains > 0 else 0.0

        return {
            "year": year,
            "filing_status": filing,
            "short_term_gains": st_gain,
            "long_term_gains": lt_gain,
            "total_gains": total_gains,
            "short_term_tax": round(st_tax, 2),
            "long_term_tax": round(lt_tax, 2),
            "estimated_tax": total_tax,
            "effective_rate": effective_rate,
        }

    def get_wash_sale_flags(self, symbol: str, loss_date: str) -> list[dict]:
        """
        Detect potential wash sales: any buy of the same symbol
        within 30 days before or after a realized loss.
        """
        loss_dt = datetime.fromisoformat(loss_date[:10])
        window_start = (loss_dt - timedelta(days=30)).isoformat()[:10]
        window_end = (loss_dt + timedelta(days=30)).isoformat()[:10]

        rows = self.conn.execute(
            """SELECT * FROM tax_lots
               WHERE symbol = ? AND entry_date BETWEEN ? AND ?
               AND lot_id != (
                   SELECT lot_id FROM tax_lots
                   WHERE symbol = ? AND status = 'closed'
                   AND gain_loss < 0 AND exit_date LIKE ?
                   LIMIT 1
               )
               ORDER BY entry_date""",
            (symbol.upper(), window_start, window_end, symbol.upper(), f"{loss_date[:10]}%"),
        ).fetchall()

        return [
            {
                "lot_id": r["lot_id"],
                "symbol": r["symbol"],
                "entry_date": r["entry_date"],
                "quantity": r["quantity"],
                "entry_price": r["entry_price"],
                "wash_sale_risk": True,
                "loss_date": loss_date,
            }
            for r in rows
        ]

    def get_all_wash_sale_flags(self) -> list[dict]:
        """Scan all realized losses and check for wash sale violations."""
        losses = self.conn.execute(
            """SELECT * FROM tax_lots
               WHERE status = 'closed' AND gain_loss < 0
               ORDER BY exit_date DESC"""
        ).fetchall()

        flags = []
        for loss in losses:
            matches = self.get_wash_sale_flags(loss["symbol"], loss["exit_date"])
            for m in matches:
                m["loss_lot_id"] = loss["lot_id"]
                m["loss_amount"] = loss["gain_loss"]
                flags.append(m)
        return flags

    def tax_loss_harvest_candidates(
        self,
        positions: list[dict],
        current_prices: dict[str, float],
    ) -> list[dict]:
        """
        Find open positions with unrealized losses that could be harvested.
        Returns candidates sorted by largest potential savings.
        """
        candidates = []
        for pos in positions:
            symbol = pos.get("symbol", "").upper()
            price_now = current_prices.get(symbol)
            if price_now is None:
                continue
            entry = pos.get("entry_price", 0)
            qty = pos.get("quantity", 0)
            side = pos.get("side", "long")
            if side == "long":
                unrealized = (price_now - entry) * qty
            else:
                unrealized = (entry - price_now) * qty

            if unrealized < 0:
                # Estimate tax savings at a blended 25% rate
                est_savings = round(abs(unrealized) * 0.25, 2)
                candidates.append({
                    "symbol": symbol,
                    "quantity": qty,
                    "entry_price": entry,
                    "current_price": price_now,
                    "unrealized_loss": round(unrealized, 2),
                    "estimated_tax_savings": est_savings,
                    "side": side,
                })

        candidates.sort(key=lambda c: c["unrealized_loss"])
        return candidates

    def generate_tax_report(self, year: int, filing_status: str = "single") -> dict:
        """Comprehensive tax report for a given year."""
        gains = self.get_realized_gains(year)
        liability = self.estimate_tax_liability(year, filing_status)
        closed_lots = self.get_lots(status="closed", year=year)
        open_lots = self.get_lots(status="open")
        wash_sales = self.get_all_wash_sale_flags()

        # Build positions list from open lots for harvest candidates
        positions = [
            {
                "symbol": lot["symbol"],
                "quantity": lot["quantity"],
                "entry_price": lot["entry_price"],
                "side": lot["side"],
            }
            for lot in open_lots
        ]

        return {
            "year": year,
            "filing_status": filing_status,
            "realized_gains": gains,
            "estimated_liability": liability,
            "closed_lots": closed_lots,
            "open_lots": open_lots,
            "wash_sale_warnings": wash_sales,
            "total_closed_lots": len(closed_lots),
            "total_open_lots": len(open_lots),
        }


# ─── Singleton ────────────────────────────────────────────

_tax_engine: Optional[TaxEngine] = None


def get_tax_engine() -> TaxEngine:
    global _tax_engine
    if _tax_engine is None:
        _tax_engine = TaxEngine()
    return _tax_engine
