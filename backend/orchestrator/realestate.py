"""
Lumare Real Estate Portfolio Engine.

SQLite-backed tracker for real estate holdings — valuations, cashflow,
metrics (cap rate, CoC, NOI, GRM, DSCR, LTV), and allocation analysis.
"""

import sqlite3
import uuid
from datetime import datetime, date, timedelta
from typing import Optional

DB_PATH = "data/lumare_realestate.db"


class RealEstateEngine:
    """Core real-estate portfolio tracker with SQLite persistence."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    # ── DB bootstrap ─────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS properties (
                    id TEXT PRIMARY KEY,
                    address TEXT NOT NULL,
                    city TEXT NOT NULL,
                    state TEXT NOT NULL,
                    zip TEXT NOT NULL DEFAULT '',
                    type TEXT NOT NULL DEFAULT 'SFH',
                    purchase_price REAL NOT NULL DEFAULT 0,
                    purchase_date TEXT NOT NULL DEFAULT '',
                    current_value REAL NOT NULL DEFAULT 0,
                    monthly_rent REAL NOT NULL DEFAULT 0,
                    monthly_expenses REAL NOT NULL DEFAULT 0,
                    mortgage_balance REAL NOT NULL DEFAULT 0,
                    mortgage_rate REAL NOT NULL DEFAULT 0,
                    mortgage_payment REAL NOT NULL DEFAULT 0,
                    sqft REAL NOT NULL DEFAULT 0,
                    bedrooms INTEGER NOT NULL DEFAULT 0,
                    bathrooms REAL NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Active',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    date TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (property_id) REFERENCES properties(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS valuations (
                    id TEXT PRIMARY KEY,
                    property_id TEXT NOT NULL,
                    value REAL NOT NULL,
                    date TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    FOREIGN KEY (property_id) REFERENCES properties(id)
                )
            """)
            conn.commit()

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        return dict(row)

    # ── Properties CRUD ──────────────────────────────────────

    def add_property(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: str = "",
        prop_type: str = "SFH",
        purchase_price: float = 0,
        purchase_date: str = "",
        current_value: float = 0,
        monthly_rent: float = 0,
        monthly_expenses: float = 0,
        mortgage_balance: float = 0,
        mortgage_rate: float = 0,
        mortgage_payment: float = 0,
        sqft: float = 0,
        bedrooms: int = 0,
        bathrooms: float = 0,
        notes: str = "",
        status: str = "Active",
    ) -> dict:
        pid = str(uuid.uuid4())[:8]
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO properties
                   (id, address, city, state, zip, type, purchase_price,
                    purchase_date, current_value, monthly_rent, monthly_expenses,
                    mortgage_balance, mortgage_rate, mortgage_payment,
                    sqft, bedrooms, bathrooms, notes, status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    pid, address, city, state, zip_code, prop_type,
                    purchase_price, purchase_date,
                    current_value or purchase_price,
                    monthly_rent, monthly_expenses,
                    mortgage_balance, mortgage_rate, mortgage_payment,
                    sqft, bedrooms, bathrooms, notes, status,
                ),
            )
            conn.commit()
        return self.get_property(pid)

    def update_property(self, property_id: str, **kwargs) -> dict:
        allowed = {
            "address", "city", "state", "zip", "type",
            "purchase_price", "purchase_date", "current_value",
            "monthly_rent", "monthly_expenses",
            "mortgage_balance", "mortgage_rate", "mortgage_payment",
            "sqft", "bedrooms", "bathrooms", "notes", "status",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return self.get_property(property_id)
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [property_id]
        with self._conn() as conn:
            conn.execute(
                f"UPDATE properties SET {set_clause} WHERE id=?", values
            )
            conn.commit()
        return self.get_property(property_id)

    def get_property(self, property_id: str) -> dict:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM properties WHERE id=?", (property_id,)
            ).fetchone()
        if not row:
            return {}
        return self._row_to_dict(row)

    def get_all_properties(self) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM properties ORDER BY created_at DESC"
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ── Valuations ───────────────────────────────────────────

    def update_valuation(
        self, property_id: str, value: float, source: str = "manual"
    ) -> dict:
        vid = str(uuid.uuid4())[:8]
        today = date.today().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO valuations (id, property_id, value, date, source) VALUES (?,?,?,?,?)",
                (vid, property_id, value, today, source),
            )
            conn.execute(
                "UPDATE properties SET current_value=? WHERE id=?",
                (value, property_id),
            )
            conn.commit()
        return {"id": vid, "property_id": property_id, "value": value, "date": today}

    # ── Transactions ─────────────────────────────────────────

    def record_transaction(
        self,
        property_id: str,
        txn_type: str,
        amount: float,
        txn_date: str = "",
        description: str = "",
    ) -> dict:
        tid = str(uuid.uuid4())[:8]
        if not txn_date:
            txn_date = date.today().isoformat()
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO transactions (id, property_id, type, amount, date, description) VALUES (?,?,?,?,?,?)",
                (tid, property_id, txn_type, amount, txn_date, description),
            )
            conn.commit()
        return {
            "id": tid,
            "property_id": property_id,
            "type": txn_type,
            "amount": amount,
            "date": txn_date,
            "description": description,
        }

    # ── Metrics ──────────────────────────────────────────────

    def calculate_metrics(self, property_id: str) -> dict:
        prop = self.get_property(property_id)
        if not prop:
            return {}

        annual_rent = prop["monthly_rent"] * 12
        annual_expenses = prop["monthly_expenses"] * 12
        noi = annual_rent - annual_expenses
        purchase_price = prop["purchase_price"] or 1
        current_value = prop["current_value"] or purchase_price
        mortgage_balance = prop["mortgage_balance"]
        mortgage_payment = prop["mortgage_payment"]
        annual_debt_service = mortgage_payment * 12

        # Cap rate = NOI / Current Value
        cap_rate = (noi / current_value * 100) if current_value else 0

        # Cash-on-cash = (NOI - annual debt service) / down payment
        down_payment = purchase_price - mortgage_balance
        if down_payment <= 0:
            down_payment = purchase_price
        annual_cashflow = noi - annual_debt_service
        cash_on_cash = (annual_cashflow / down_payment * 100) if down_payment else 0

        # GRM = Price / Annual Gross Rent
        grm = (current_value / annual_rent) if annual_rent else 0

        # DSCR = NOI / Annual Debt Service
        dscr = (noi / annual_debt_service) if annual_debt_service else 0

        # Equity
        equity = current_value - mortgage_balance

        # LTV = Mortgage Balance / Current Value
        ltv = (mortgage_balance / current_value * 100) if current_value else 0

        # Appreciation
        appreciation = current_value - purchase_price
        appreciation_pct = (
            (appreciation / purchase_price * 100) if purchase_price else 0
        )

        # Monthly cashflow
        monthly_cashflow = prop["monthly_rent"] - prop["monthly_expenses"] - mortgage_payment

        return {
            "property_id": property_id,
            "noi": round(noi, 2),
            "cap_rate": round(cap_rate, 2),
            "cash_on_cash": round(cash_on_cash, 2),
            "grm": round(grm, 2),
            "dscr": round(dscr, 2),
            "equity": round(equity, 2),
            "ltv": round(ltv, 2),
            "appreciation": round(appreciation, 2),
            "appreciation_pct": round(appreciation_pct, 2),
            "monthly_cashflow": round(monthly_cashflow, 2),
            "annual_cashflow": round(annual_cashflow, 2),
        }

    # ── Cashflow Report ──────────────────────────────────────

    def get_cashflow_report(self, property_id: str, months: int = 12) -> dict:
        prop = self.get_property(property_id)
        if not prop:
            return {"months": [], "totals": {}}

        cutoff = (date.today() - timedelta(days=months * 31)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE property_id=? AND date>=? ORDER BY date",
                (property_id, cutoff),
            ).fetchall()

        txns = [self._row_to_dict(r) for r in rows]

        # Bucket by month
        monthly: dict[str, dict] = {}
        for t in txns:
            month_key = t["date"][:7]  # YYYY-MM
            if month_key not in monthly:
                monthly[month_key] = {"income": 0, "expenses": 0, "transactions": []}
            if t["type"] in ("rent", "income"):
                monthly[month_key]["income"] += t["amount"]
            else:
                monthly[month_key]["expenses"] += t["amount"]
            monthly[month_key]["transactions"].append(t)

        month_list = []
        total_income = 0
        total_expenses = 0
        for mk in sorted(monthly.keys()):
            m = monthly[mk]
            net = m["income"] - m["expenses"]
            total_income += m["income"]
            total_expenses += m["expenses"]
            month_list.append({
                "month": mk,
                "income": round(m["income"], 2),
                "expenses": round(m["expenses"], 2),
                "net": round(net, 2),
                "transactions": m["transactions"],
            })

        return {
            "property_id": property_id,
            "months": month_list,
            "totals": {
                "income": round(total_income, 2),
                "expenses": round(total_expenses, 2),
                "net": round(total_income - total_expenses, 2),
            },
        }

    # ── Portfolio Summary ────────────────────────────────────

    def get_portfolio_summary(self) -> dict:
        props = self.get_all_properties()
        if not props:
            return {
                "total_value": 0,
                "total_equity": 0,
                "total_monthly_cashflow": 0,
                "avg_cap_rate": 0,
                "total_appreciation": 0,
                "total_appreciation_pct": 0,
                "property_count": 0,
            }

        total_value = 0
        total_equity = 0
        total_monthly_cashflow = 0
        total_appreciation = 0
        total_purchase = 0
        cap_rates = []

        for p in props:
            metrics = self.calculate_metrics(p["id"])
            total_value += p["current_value"]
            total_equity += metrics.get("equity", 0)
            total_monthly_cashflow += metrics.get("monthly_cashflow", 0)
            total_appreciation += metrics.get("appreciation", 0)
            total_purchase += p["purchase_price"]
            cr = metrics.get("cap_rate", 0)
            if cr > 0:
                cap_rates.append(cr)

        avg_cap_rate = sum(cap_rates) / len(cap_rates) if cap_rates else 0

        return {
            "total_value": round(total_value, 2),
            "total_equity": round(total_equity, 2),
            "total_monthly_cashflow": round(total_monthly_cashflow, 2),
            "avg_cap_rate": round(avg_cap_rate, 2),
            "total_appreciation": round(total_appreciation, 2),
            "total_appreciation_pct": round(
                (total_appreciation / total_purchase * 100) if total_purchase else 0, 2
            ),
            "property_count": len(props),
        }

    # ── Portfolio Allocation ─────────────────────────────────

    def get_portfolio_allocation(self) -> list[dict]:
        props = self.get_all_properties()
        if not props:
            return []

        totals: dict[str, float] = {}
        grand_total = 0.0
        for p in props:
            t = p["type"]
            totals[t] = totals.get(t, 0) + p["current_value"]
            grand_total += p["current_value"]

        return [
            {
                "type": t,
                "value": round(v, 2),
                "percentage": round(v / grand_total * 100, 2) if grand_total else 0,
            }
            for t, v in sorted(totals.items(), key=lambda x: -x[1])
        ]

    # ── Demo Seed ────────────────────────────────────────────

    def seed_demo_properties(self) -> list[dict]:
        """Insert 3 showcase properties if portfolio is empty."""
        existing = self.get_all_properties()
        if existing:
            return existing

        demos = [
            dict(
                address="1245 Oak Ridge Drive",
                city="Austin",
                state="TX",
                zip_code="78704",
                prop_type="SFH",
                purchase_price=425000,
                purchase_date="2022-06-15",
                current_value=510000,
                monthly_rent=2800,
                monthly_expenses=650,
                mortgage_balance=320000,
                mortgage_rate=5.25,
                mortgage_payment=1766,
                sqft=2100,
                bedrooms=3,
                bathrooms=2,
                notes="Recently renovated kitchen, strong rental market",
                status="Active",
            ),
            dict(
                address="88 Harbor View Ct, Unit 4",
                city="Miami",
                state="FL",
                zip_code="33131",
                prop_type="Multi-Family",
                purchase_price=780000,
                purchase_date="2021-03-20",
                current_value=920000,
                monthly_rent=6200,
                monthly_expenses=1800,
                mortgage_balance=585000,
                mortgage_rate=4.75,
                mortgage_payment=3051,
                sqft=3400,
                bedrooms=6,
                bathrooms=4,
                notes="4-unit building, fully occupied",
                status="Active",
            ),
            dict(
                address="500 Commerce Blvd",
                city="Denver",
                state="CO",
                zip_code="80202",
                prop_type="Commercial",
                purchase_price=1250000,
                purchase_date="2020-11-01",
                current_value=1480000,
                monthly_rent=11500,
                monthly_expenses=3200,
                mortgage_balance=875000,
                mortgage_rate=5.5,
                mortgage_payment=4969,
                sqft=8500,
                bedrooms=0,
                bathrooms=4,
                notes="NNN lease, two tenants, 5-year terms",
                status="Active",
            ),
        ]

        results = []
        for d in demos:
            results.append(self.add_property(**d))
        return results
