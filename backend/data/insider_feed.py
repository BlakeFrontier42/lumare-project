"""
insider_feed.py - SEC EDGAR connector for insider Form 4 filings.

Fetches and parses insider trading disclosures from the SEC EDGAR full-text
search API and RSS feed, with individual Form 4 XML parsing for transaction
detail. Includes SQLite caching, rate limiting, retries, and mock fallback.
"""

from __future__ import annotations

import asyncio
import os
import re
import sqlite3
import time
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
import numpy as np
import pandas as pd
from loguru import logger

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EDGAR_BASE = "https://efts.sec.gov/LATEST"
EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"
EDGAR_RSS = "https://www.sec.gov/cgi-bin/browse-edgar"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions"
EDGAR_ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

# SEC requires a valid User-Agent with contact info
DEFAULT_USER_AGENT = "Lumare-MIE/1.0 (contact@lumare.dev)"

FILING_COLUMNS = [
    "insider", "ticker", "transaction_type", "shares", "price", "date", "title",
]

# Transaction code mapping (Form 4)
TRANSACTION_CODES = {
    "P": "Purchase",
    "S": "Sale",
    "A": "Award",
    "D": "Disposition (gift)",
    "F": "Tax withholding",
    "M": "Option exercise",
    "G": "Gift",
    "C": "Conversion",
    "X": "Option expiry",
    "J": "Other",
}

# XML namespaces used in Form 4 filings
FORM4_NS = {
    "": "http://www.sec.gov/cgi-bin/viewer?action=view&cik={cik}&type=4",
}

# SQLite schema for insider filing cache
_INSIDER_SCHEMA = """
CREATE TABLE IF NOT EXISTS insider_filings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    insider             TEXT    NOT NULL,
    ticker              TEXT    NOT NULL,
    transaction_type    TEXT    NOT NULL,
    shares              INTEGER NOT NULL DEFAULT 0,
    price               REAL    NOT NULL DEFAULT 0.0,
    date                TEXT    NOT NULL,
    title               TEXT,
    accession_number    TEXT,
    fetched_at          TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_insider_ticker ON insider_filings(ticker);
CREATE INDEX IF NOT EXISTS idx_insider_date ON insider_filings(date);
CREATE INDEX IF NOT EXISTS idx_insider_name ON insider_filings(insider);
CREATE INDEX IF NOT EXISTS idx_insider_fetched ON insider_filings(fetched_at);
CREATE INDEX IF NOT EXISTS idx_insider_accession ON insider_filings(accession_number);
"""


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

class TTLCache:
    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[float, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires, value = entry
        if time.monotonic() > expires:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        self._store[key] = (time.monotonic() + (ttl or self._default_ttl), value)

    def clear(self) -> None:
        self._store.clear()


class RateLimiter:
    """SEC EDGAR requests: max 10 requests/second."""
    def __init__(self, max_calls: int = 8, period: float = 1.0):
        self._max = max_calls
        self._period = period
        self._tokens = float(max_calls)
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self._max, self._tokens + elapsed * (self._max / self._period))
            self._last = now
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) * (self._period / self._max)
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


# ---------------------------------------------------------------------------
# SQLite cache layer
# ---------------------------------------------------------------------------

class _InsiderDBCache:
    """Thread-safe SQLite cache for insider filings."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path, timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def _init_schema(self) -> None:
        conn = self._conn()
        conn.executescript(_INSIDER_SCHEMA)
        conn.commit()

    def get_cached_filings(self, max_age_seconds: int = 600) -> pd.DataFrame | None:
        """Return cached filings if fresh enough, else None."""
        conn = self._conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)).isoformat()
        row = conn.execute(
            "SELECT MAX(fetched_at) as latest FROM insider_filings"
        ).fetchone()
        if row is None or row["latest"] is None or row["latest"] < cutoff:
            return None

        rows = conn.execute(
            "SELECT insider, ticker, transaction_type, shares, price, date, title "
            "FROM insider_filings"
        ).fetchall()
        if not rows:
            return None

        df = pd.DataFrame([dict(r) for r in rows], columns=FILING_COLUMNS)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0).astype(int)
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
        return df.sort_values("date", ascending=False).reset_index(drop=True)

    def get_cached_by_ticker(self, ticker: str, max_age_seconds: int = 600) -> pd.DataFrame | None:
        """Return cached filings for a specific ticker if fresh enough."""
        conn = self._conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)).isoformat()
        row = conn.execute(
            "SELECT MAX(fetched_at) as latest FROM insider_filings WHERE ticker = ?",
            (ticker.upper(),),
        ).fetchone()
        if row is None or row["latest"] is None or row["latest"] < cutoff:
            return None

        rows = conn.execute(
            "SELECT insider, ticker, transaction_type, shares, price, date, title "
            "FROM insider_filings WHERE ticker = ?",
            (ticker.upper(),),
        ).fetchall()
        if not rows:
            return None

        df = pd.DataFrame([dict(r) for r in rows], columns=FILING_COLUMNS)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0).astype(int)
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
        return df.sort_values("date", ascending=False).reset_index(drop=True)

    def store_filings(self, df: pd.DataFrame) -> None:
        """Replace all cached filings with fresh data."""
        if df.empty:
            return
        conn = self._conn()
        conn.execute("DELETE FROM insider_filings")
        self._insert_rows(conn, df)

    def store_ticker_filings(self, ticker: str, df: pd.DataFrame) -> None:
        """Replace cached filings for a specific ticker."""
        if df.empty:
            return
        conn = self._conn()
        conn.execute("DELETE FROM insider_filings WHERE ticker = ?", (ticker.upper(),))
        self._insert_rows(conn, df)

    def _insert_rows(self, conn: sqlite3.Connection, df: pd.DataFrame) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for _, row in df.iterrows():
            dt = row.get("date")
            if pd.notna(dt):
                date_str = dt.isoformat() if hasattr(dt, "isoformat") else str(dt)
            else:
                date_str = ""
            rows.append((
                str(row.get("insider", "")),
                str(row.get("ticker", "")),
                str(row.get("transaction_type", "")),
                int(row.get("shares", 0)) if pd.notna(row.get("shares")) else 0,
                float(row.get("price", 0.0)) if pd.notna(row.get("price")) else 0.0,
                date_str,
                str(row.get("title", "")),
                str(row.get("accession_number", "")) if "accession_number" in row.index else "",
                now,
            ))
        conn.executemany(
            "INSERT INTO insider_filings "
            "(insider, ticker, transaction_type, shares, price, date, title, accession_number, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        logger.debug("Cached {} insider filings in SQLite", len(rows))


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_INSIDERS = [
    ("Satya Nadella", "MSFT", "CEO"),
    ("Tim Cook", "AAPL", "CEO"),
    ("Jensen Huang", "NVDA", "CEO"),
    ("Andy Jassy", "AMZN", "CEO"),
    ("Sundar Pichai", "GOOGL", "CEO"),
    ("Mark Zuckerberg", "META", "CEO"),
    ("Lisa Su", "AMD", "CEO"),
    ("Jamie Dimon", "JPM", "CEO"),
    ("Colette Kress", "NVDA", "CFO"),
    ("Luca Maestri", "AAPL", "CFO"),
    ("Amy Hood", "MSFT", "CFO"),
    ("Ruth Porat", "GOOGL", "CFO"),
    ("Brian Olsavsky", "AMZN", "CFO"),
    ("Susan Li", "META", "CFO"),
    ("John Smith", "TSLA", "VP"),
    ("Jane Doe", "CRM", "Director"),
]


def _generate_mock_filings(days: int = 30, count: int = 60) -> pd.DataFrame:
    np.random.seed(99)
    now = date.today()
    rows = []
    for _ in range(count):
        insider_name, ticker, title = MOCK_INSIDERS[np.random.randint(0, len(MOCK_INSIDERS))]
        tx_code = np.random.choice(["P", "S", "S", "S", "M", "A", "F"])  # bias toward sales
        tx_type = TRANSACTION_CODES.get(tx_code, "Other")
        shares = int(np.random.uniform(100, 500_000))
        price = round(np.random.uniform(20, 800), 2)
        trade_date = now - timedelta(days=int(np.random.uniform(0, days)))
        rows.append({
            "insider": insider_name,
            "ticker": ticker,
            "transaction_type": tx_type,
            "shares": shares,
            "price": price,
            "date": trade_date.isoformat(),
            "title": title,
        })
    df = pd.DataFrame(rows, columns=FILING_COLUMNS)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Form 4 XML Parser
# ---------------------------------------------------------------------------

def _parse_form4_xml(xml_text: str) -> list[dict]:
    """
    Parse a single Form 4 XML filing into a list of transaction dicts.

    Each Form 4 can contain multiple transactions (non-derivative and derivative).
    """
    transactions = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.debug("Failed to parse Form 4 XML: {}", exc)
        return []

    # Extract reporting owner info
    owner_name = ""
    owner_title = ""
    for owner in root.iter("reportingOwner"):
        oid = owner.find("reportingOwnerId")
        if oid is not None:
            name_el = oid.find("rptOwnerName")
            if name_el is not None and name_el.text:
                owner_name = name_el.text.strip()
        rel = owner.find("reportingOwnerRelationship")
        if rel is not None:
            for tag in ("officerTitle", "isOfficer", "isDirector", "isTenPercentOwner"):
                el = rel.find(tag)
                if tag == "officerTitle" and el is not None and el.text:
                    owner_title = el.text.strip()
                    break
            if not owner_title:
                if rel.find("isDirector") is not None and (rel.find("isDirector").text or "").strip() == "1":
                    owner_title = "Director"
                elif rel.find("isTenPercentOwner") is not None and (rel.find("isTenPercentOwner").text or "").strip() == "1":
                    owner_title = "10% Owner"

    # Extract issuer ticker
    issuer_ticker = ""
    issuer_el = root.find(".//issuer")
    if issuer_el is not None:
        ticker_el = issuer_el.find("issuerTradingSymbol")
        if ticker_el is not None and ticker_el.text:
            issuer_ticker = ticker_el.text.strip().upper()

    # Parse non-derivative transactions
    for tx_table in root.iter("nonDerivativeTransaction"):
        tx = _extract_transaction(tx_table, owner_name, owner_title, issuer_ticker)
        if tx:
            transactions.append(tx)

    # Parse derivative transactions
    for tx_table in root.iter("derivativeTransaction"):
        tx = _extract_transaction(tx_table, owner_name, owner_title, issuer_ticker)
        if tx:
            transactions.append(tx)

    return transactions


def _extract_transaction(
    tx_elem: ET.Element,
    owner_name: str,
    owner_title: str,
    issuer_ticker: str,
) -> dict | None:
    """Extract a single transaction from a Form 4 XML transaction element."""
    try:
        # Security title
        sec_title_el = tx_elem.find(".//securityTitle/value")

        # Transaction date
        tx_date_el = tx_elem.find(".//transactionDate/value")
        tx_date = tx_date_el.text.strip() if tx_date_el is not None and tx_date_el.text else ""

        # Transaction code
        tx_coding = tx_elem.find(".//transactionCoding")
        tx_code = ""
        if tx_coding is not None:
            code_el = tx_coding.find("transactionCode")
            if code_el is not None and code_el.text:
                tx_code = code_el.text.strip()

        tx_type = TRANSACTION_CODES.get(tx_code, f"Other ({tx_code})")

        # Shares
        shares = 0
        shares_el = tx_elem.find(".//transactionAmounts/transactionShares/value")
        if shares_el is not None and shares_el.text:
            try:
                shares = int(float(shares_el.text.strip()))
            except (ValueError, TypeError):
                pass

        # Price per share
        price = 0.0
        price_el = tx_elem.find(".//transactionAmounts/transactionPricePerShare/value")
        if price_el is not None and price_el.text:
            try:
                price = round(float(price_el.text.strip()), 4)
            except (ValueError, TypeError):
                pass

        # Acquisition or disposition
        ad_el = tx_elem.find(".//transactionAmounts/transactionAcquiredDisposedCode/value")
        ad_code = ""
        if ad_el is not None and ad_el.text:
            ad_code = ad_el.text.strip()

        return {
            "insider": owner_name,
            "ticker": issuer_ticker,
            "transaction_type": tx_type,
            "shares": shares,
            "price": price,
            "date": tx_date,
            "title": owner_title,
            "ad_code": ad_code,  # A=acquired, D=disposed
        }
    except Exception as exc:
        logger.debug("Failed to extract transaction: {}", exc)
        return None


# ---------------------------------------------------------------------------
# Insider Feed
# ---------------------------------------------------------------------------

class InsiderFeed:
    """
    SEC EDGAR insider trading (Form 4) data feed.

    Uses the EDGAR full-text search API (EFTS) to find recent Form 4 filings,
    then fetches and parses individual Form 4 XML documents for detailed
    transaction data.

    Parameters
    ----------
    user_agent : str
        Required by SEC EDGAR fair-access policy.
    use_mock : bool
        Return synthetic data.
    cache_ttl : int
        Default in-memory cache TTL in seconds.
    db_path : str | None
        Path for SQLite cache. If None, uses ``data/insider_cache.db``.
    max_retries : int
        Max retry attempts.
    max_filings_to_parse : int
        Max number of individual Form 4 filings to download and parse per
        request. Limits load on SEC servers.
    """

    def __init__(
        self,
        user_agent: str | None = None,
        use_mock: bool = False,
        cache_ttl: int = 300,
        db_path: str | None = None,
        max_retries: int = 3,
        max_filings_to_parse: int = 50,
    ) -> None:
        self.user_agent = user_agent or os.getenv("EDGAR_USER_AGENT", DEFAULT_USER_AGENT)
        self.use_mock = use_mock
        self.max_retries = max_retries
        self.max_filings_to_parse = max_filings_to_parse

        self._cache = TTLCache(default_ttl=cache_ttl)
        self._limiter = RateLimiter(max_calls=8, period=1.0)
        self._client: httpx.AsyncClient | None = None

        # SQLite persistent cache
        _db = db_path or os.path.join("data", "insider_cache.db")
        self._db = _InsiderDBCache(_db)

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20.0, connect=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json",
                },
                follow_redirects=True,
            )
        return self._client

    async def _request(
        self,
        url: str,
        params: dict | None = None,
        cache_key: str | None = None,
        cache_ttl: int | None = None,
        accept: str = "application/json",
    ) -> Any:
        if cache_key:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        await self._limiter.acquire()
        client = await self._get_client()

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await client.get(url, params=params, headers={"Accept": accept})

                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", 10))
                    logger.warning("EDGAR 429 -- waiting {}s", wait)
                    await asyncio.sleep(wait)
                    continue

                resp.raise_for_status()

                if accept == "application/json":
                    data = resp.json()
                else:
                    data = resp.text

                if cache_key:
                    self._cache.set(cache_key, data, cache_ttl)
                return data

            except (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                backoff = min(2 ** attempt, 15)
                logger.warning("EDGAR {} failed (attempt {}/{}): {}", url, attempt, self.max_retries, exc)
                await asyncio.sleep(backoff)

        raise last_exc  # type: ignore[misc]

    # ------------------------------------------------------------------
    # EDGAR full-text search for Form 4
    # ------------------------------------------------------------------

    async def _search_form4(self, ticker: str | None = None, days: int = 30) -> list[dict]:
        """
        Search EDGAR EFTS for recent Form 4 filings.

        Returns list of filing metadata dicts from the EFTS API.
        """
        end = date.today()
        start = end - timedelta(days=days)

        params: dict[str, str] = {
            "dateRange": "custom",
            "startdt": start.isoformat(),
            "enddt": end.isoformat(),
            "forms": "4",
        }
        if ticker:
            params["q"] = f'"{ticker.upper()}"'

        try:
            data = await self._request(
                f"{EDGAR_BASE}/search-index",
                params=params,
                cache_key=f"edgar_search:{ticker}:{days}",
                cache_ttl=300,
            )
            hits = data.get("hits", {}).get("hits", [])
            return hits
        except Exception as exc:
            logger.error("EDGAR Form 4 search failed: {}", exc)
            return []

    async def _fetch_form4_xml(self, filing_url: str) -> str | None:
        """Fetch and return the raw XML text of a Form 4 filing."""
        try:
            xml_text = await self._request(
                filing_url,
                accept="application/xml",
                cache_key=f"form4_xml:{filing_url}",
                cache_ttl=3600,
            )
            return xml_text if xml_text else None
        except Exception as exc:
            logger.debug("Failed to fetch Form 4 XML from {}: {}", filing_url, exc)
            return None

    def _build_filing_url(self, hit: dict) -> str | None:
        """
        Build the URL to the actual Form 4 XML document from an EFTS hit.

        EFTS hits contain ``_source.file_num`` and ``_id`` which map to the
        filing on EDGAR Archives.
        """
        src = hit.get("_source", {})
        # The _id field typically looks like "0001234567-XX-YYYYYY" (accession number)
        hit_id = hit.get("_id", "")
        file_num = src.get("file_num", "")

        # Try to reconstruct the filing URL from available data
        # Format: https://www.sec.gov/Archives/edgar/data/{CIK}/{accession_no_dashes}/{filename}.xml
        entity_id = src.get("entity_id", "")
        if not entity_id and src.get("ciks"):
            entity_id = str(src["ciks"][0])

        if hit_id and entity_id:
            # Accession number without dashes for path
            acc_no_dashes = hit_id.replace("-", "")
            return (
                f"https://www.sec.gov/Archives/edgar/data/{entity_id}/"
                f"{acc_no_dashes}/{hit_id}.txt"
            )
        return None

    async def _parse_filing_index(self, index_url: str) -> str | None:
        """
        Fetch a filing index page and find the Form 4 XML document URL.

        The filing index (.txt) contains an XML document reference.
        """
        try:
            text = await self._request(index_url, accept="text/html", cache_key=f"idx:{index_url}", cache_ttl=3600)
            if not text:
                return None

            # Look for the primary XML document link in the filing index
            # Common patterns: .xml files in the filing directory
            xml_pattern = re.compile(r'<a[^>]+href="([^"]+\.xml)"', re.IGNORECASE)
            matches = xml_pattern.findall(text)
            for match in matches:
                # Prefer the primary document (usually named like form4.xml or xslForm4X01)
                if "form4" in match.lower() or "primary_doc" in match.lower():
                    if match.startswith("/"):
                        return f"https://www.sec.gov{match}"
                    return match

            # Fall back to the first XML file
            if matches:
                m = matches[0]
                if m.startswith("/"):
                    return f"https://www.sec.gov{m}"
                return m

        except Exception as exc:
            logger.debug("Failed to parse filing index {}: {}", index_url, exc)
        return None

    # ------------------------------------------------------------------
    # EDGAR EFTS-based approach (primary)
    # ------------------------------------------------------------------

    async def _fetch_and_parse_filings(
        self,
        hits: list[dict],
        max_parse: int | None = None,
    ) -> pd.DataFrame:
        """
        From EFTS search hits, try to fetch individual Form 4 XMLs for
        detailed transaction data. Falls back to metadata-only parsing
        if XML fetch fails.
        """
        max_parse = max_parse or self.max_filings_to_parse
        all_transactions: list[dict] = []

        # First, extract what we can from the EFTS metadata
        metadata_rows = self._parse_efts_metadata(hits)

        # Try to fetch and parse individual Form 4 XMLs (limited to avoid
        # overwhelming SEC servers)
        filings_to_fetch = hits[:max_parse]
        parsed_accessions: set[str] = set()

        for hit in filings_to_fetch:
            src = hit.get("_source", {})
            accession = hit.get("_id", "")

            # Build URL to the filing index
            entity_id = ""
            if src.get("ciks"):
                entity_id = str(src["ciks"][0])
            elif src.get("entity_id"):
                entity_id = str(src["entity_id"])

            if not accession or not entity_id:
                continue

            acc_no_dashes = accession.replace("-", "")
            index_url = (
                f"https://www.sec.gov/Archives/edgar/data/{entity_id}/"
                f"{acc_no_dashes}/{accession}-index.htm"
            )

            xml_url = await self._parse_filing_index(index_url)
            if not xml_url:
                # Try direct XML URL pattern
                xml_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{entity_id}/"
                    f"{acc_no_dashes}/form4.xml"
                )

            xml_text = await self._fetch_form4_xml(xml_url)
            if xml_text:
                transactions = _parse_form4_xml(xml_text)
                if transactions:
                    for tx in transactions:
                        tx["accession_number"] = accession
                    all_transactions.extend(transactions)
                    parsed_accessions.add(accession)

        # For any filings we couldn't parse XML for, use EFTS metadata
        for row in metadata_rows:
            acc = row.get("accession_number", "")
            if acc and acc not in parsed_accessions:
                all_transactions.append(row)

        if not all_transactions:
            return pd.DataFrame(columns=FILING_COLUMNS)

        df = pd.DataFrame(all_transactions)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

        # Ensure all required columns
        for col in FILING_COLUMNS:
            if col not in df.columns:
                df[col] = None

        df["shares"] = pd.to_numeric(df["shares"], errors="coerce").fillna(0).astype(int)
        df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)

        return df[FILING_COLUMNS].sort_values("date", ascending=False).reset_index(drop=True)

    def _parse_efts_metadata(self, hits: list[dict]) -> list[dict]:
        """Parse EDGAR EFTS search hits into basic filing metadata."""
        rows = []
        for hit in hits:
            src = hit.get("_source", {})
            insider = (
                src.get("display_names", ["Unknown"])[0]
                if src.get("display_names")
                else "Unknown"
            )
            tickers = src.get("tickers", [])
            ticker = tickers[0].upper() if tickers else "N/A"
            file_date = src.get("file_date", "")

            rows.append({
                "insider": insider,
                "ticker": ticker,
                "transaction_type": "Form 4 Filing",
                "shares": 0,
                "price": 0.0,
                "date": file_date,
                "title": src.get("display_names_str", ""),
                "accession_number": hit.get("_id", ""),
            })
        return rows

    # ------------------------------------------------------------------
    # RSS feed approach (alternative / supplementary)
    # ------------------------------------------------------------------

    async def _fetch_rss_feed(self, ticker: str | None = None, count: int = 100) -> list[dict]:
        """
        Fetch the SEC EDGAR RSS feed for recent Form 4 filings.

        This provides a list of recent filings but limited transaction detail.
        """
        params: dict[str, str] = {
            "action": "getcompany",
            "type": "4",
            "dateb": "",
            "owner": "include",
            "count": str(count),
            "search_text": "",
            "output": "atom",
        }
        if ticker:
            params["company"] = ticker.upper()
            params["CIK"] = ""

        try:
            text = await self._request(
                EDGAR_RSS,
                params=params,
                accept="application/atom+xml",
                cache_key=f"edgar_rss:{ticker}:{count}",
                cache_ttl=300,
            )
            return self._parse_rss_entries(text)
        except Exception as exc:
            logger.error("EDGAR RSS feed failed: {}", exc)
            return []

    @staticmethod
    def _parse_rss_entries(xml_text: str) -> list[dict]:
        """Parse Atom/RSS feed entries into a list of filing metadata."""
        entries = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.debug("Failed to parse EDGAR RSS XML: {}", exc)
            return []

        # Handle Atom namespace
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall(".//atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            updated_el = entry.find("atom:updated", ns)
            link_el = entry.find("atom:link", ns)
            summary_el = entry.find("atom:summary", ns)
            category_el = entry.find("atom:category", ns)

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            updated = updated_el.text.strip() if updated_el is not None and updated_el.text else ""
            link = link_el.get("href", "") if link_el is not None else ""
            summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""

            # Parse the title for insider name and company
            # Typical format: "4 - Company Name (0001234567) (Insider Name)"
            insider_name = ""
            company = ""
            ticker = ""

            # Extract CIK from the link
            cik_match = re.search(r"CIK=(\d+)", link)
            accession_match = re.search(r"accession=([0-9-]+)", link)

            # Try to extract from title
            title_match = re.match(r"4\s*-\s*(.+?)(?:\s*\((\d+)\))?\s*(?:\((.+?)\))?$", title)
            if title_match:
                company = title_match.group(1).strip()
                insider_name = title_match.group(3).strip() if title_match.group(3) else company

            entries.append({
                "insider": insider_name or "Unknown",
                "company": company,
                "ticker": ticker or "N/A",
                "transaction_type": "Form 4 Filing",
                "shares": 0,
                "price": 0.0,
                "date": updated[:10] if updated else "",
                "title": title,
                "link": link,
                "accession_number": accession_match.group(1) if accession_match else "",
            })

        return entries

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_recent_filings(self, days: int = 30) -> pd.DataFrame:
        """
        Get recent insider Form 4 filings.

        Returns DataFrame: ``[insider, ticker, transaction_type, shares, price, date, title]``

        Checks in order: in-memory cache -> SQLite cache -> EDGAR API -> mock fallback.
        """
        if self.use_mock:
            return _generate_mock_filings(days=days)

        # Check in-memory cache
        mem_key = f"insider_recent:{days}"
        cached = self._cache.get(mem_key)
        if cached is not None:
            return cached

        # Check SQLite persistent cache
        db_cached = self._db.get_cached_filings(max_age_seconds=600)
        if db_cached is not None:
            cutoff = pd.Timestamp(date.today() - timedelta(days=days), tz=None)
            filtered = db_cached[db_cached["date"] >= cutoff].reset_index(drop=True)
            if not filtered.empty:
                self._cache.set(mem_key, filtered, 600)
                logger.debug("Served {} insider filings from SQLite cache", len(filtered))
                return filtered

        # Fetch from EDGAR EFTS
        try:
            hits = await self._search_form4(ticker=None, days=days)
            if not hits:
                logger.warning("No EDGAR Form 4 results; returning mock data")
                return _generate_mock_filings(days=days)

            df = await self._fetch_and_parse_filings(hits)
            if df.empty:
                logger.warning("No transactions parsed from Form 4 filings; returning mock data")
                return _generate_mock_filings(days=days)

            # Persist to SQLite
            self._db.store_filings(df)

            # Memory cache
            self._cache.set(mem_key, df, 600)
            logger.info("Fetched and parsed {} insider transactions from EDGAR (last {} days)", len(df), days)
            return df

        except Exception as exc:
            logger.error("get_recent_filings failed: {} -- returning mock", exc)
            return _generate_mock_filings(days=days)

    async def get_filings_by_ticker(self, symbol: str) -> pd.DataFrame:
        """Get insider filings for a specific ticker."""
        ticker = symbol.upper()

        if self.use_mock:
            mock = _generate_mock_filings(days=90, count=100)
            return mock[mock["ticker"] == ticker].reset_index(drop=True)

        # Check in-memory cache
        mem_key = f"insider_ticker:{ticker}"
        cached = self._cache.get(mem_key)
        if cached is not None:
            return cached

        # Check SQLite persistent cache
        db_cached = self._db.get_cached_by_ticker(ticker, max_age_seconds=600)
        if db_cached is not None and not db_cached.empty:
            self._cache.set(mem_key, db_cached, 600)
            logger.debug("Served {} filings for {} from SQLite cache", len(db_cached), ticker)
            return db_cached

        # Fetch from EDGAR
        try:
            hits = await self._search_form4(ticker=ticker, days=90)
            if not hits:
                logger.warning("No EDGAR Form 4 results for {}; returning mock", ticker)
                mock = _generate_mock_filings(days=90, count=100)
                return mock[mock["ticker"] == ticker].reset_index(drop=True)

            df = await self._fetch_and_parse_filings(hits)
            if df.empty:
                mock = _generate_mock_filings(days=90, count=100)
                return mock[mock["ticker"] == ticker].reset_index(drop=True)

            # Persist to SQLite
            self._db.store_ticker_filings(ticker, df)

            # Memory cache
            self._cache.set(mem_key, df, 600)
            logger.info("Fetched {} insider filings for {} from EDGAR", len(df), ticker)
            return df

        except Exception as exc:
            logger.error("get_filings_by_ticker failed for {}: {}", ticker, exc)
            return pd.DataFrame(columns=FILING_COLUMNS)

    async def detect_clusters(
        self,
        symbol: str,
        min_insiders: int = 2,
        days: int = 30,
    ) -> dict:
        """
        Detect insider trading clusters for a symbol.

        A cluster is multiple insiders buying or selling within the same window.

        Returns dict: ``{is_cluster, direction, total_value, insiders, trade_count}``
        """
        filings = await self.get_filings_by_ticker(symbol)
        if filings.empty:
            return {
                "is_cluster": False,
                "direction": "neutral",
                "total_value": 0.0,
                "insiders": [],
                "trade_count": 0,
            }

        cutoff = pd.Timestamp(date.today() - timedelta(days=days))
        recent = filings[filings["date"] >= cutoff].copy() if not filings["date"].isna().all() else filings

        # Separate buys and sells
        buys = recent[recent["transaction_type"].isin(["Purchase"])]
        sells = recent[recent["transaction_type"].isin(["Sale", "Disposition (gift)"])]

        buy_insiders = buys["insider"].nunique()
        sell_insiders = sells["insider"].nunique()

        buy_value = (buys["shares"] * buys["price"]).sum()
        sell_value = (sells["shares"] * sells["price"]).sum()

        if buy_insiders >= min_insiders and buy_insiders > sell_insiders:
            direction = "buy"
            cluster_insiders = sorted(buys["insider"].unique().tolist())
            total_value = buy_value
            count = len(buys)
            is_cluster = True
        elif sell_insiders >= min_insiders:
            direction = "sell"
            cluster_insiders = sorted(sells["insider"].unique().tolist())
            total_value = sell_value
            count = len(sells)
            is_cluster = True
        else:
            direction = "neutral"
            cluster_insiders = []
            total_value = 0.0
            count = 0
            is_cluster = False

        result = {
            "is_cluster": is_cluster,
            "direction": direction,
            "total_value": round(total_value, 2),
            "insiders": cluster_insiders,
            "trade_count": count,
            "buy_insiders": buy_insiders,
            "sell_insiders": sell_insiders,
            "buy_value": round(buy_value, 2),
            "sell_value": round(sell_value, 2),
        }

        if is_cluster:
            logger.info("Insider cluster detected for {}: {}", symbol, result)
        return result

    @staticmethod
    def classify_transaction(filing: dict) -> str:
        """
        Classify a single insider transaction.

        Parameters
        ----------
        filing : dict
            A row from the filings DataFrame (as dict).

        Returns
        -------
        str
            One of ``"routine"``, ``"significant"``, ``"cluster"``.
        """
        tx_type = filing.get("transaction_type", "")
        shares = filing.get("shares", 0)
        price = filing.get("price", 0)
        title = filing.get("title", "").lower()
        value = shares * price

        # Automatic/routine: tax withholding, option exercises for small amounts, gifts
        if tx_type in ("Tax withholding", "Award", "Gift", "Disposition (gift)"):
            return "routine"

        # C-suite or director with large transactions = significant
        is_senior = any(t in title for t in ("ceo", "cfo", "coo", "cto", "president", "director", "chairman"))

        if tx_type == "Purchase" and is_senior and value > 100_000:
            return "significant"

        if tx_type == "Sale" and value > 1_000_000:
            return "significant"

        if tx_type == "Purchase" and value > 500_000:
            return "significant"

        # Option exercises that are immediately sold (common) are routine
        if tx_type == "Option exercise":
            return "routine"

        # Default to routine for small amounts
        if value < 50_000:
            return "routine"

        return "significant"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.debug("InsiderFeed HTTP client closed")

    async def __aenter__(self) -> "InsiderFeed":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
