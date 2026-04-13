"""
Build a comprehensive options-tradable universe from public sources.

Sources:
  - S&P 500 (Wikipedia)
  - S&P 400 MidCap (Wikipedia)
  - S&P 600 SmallCap (Wikipedia)
  - Nasdaq 100 (Wikipedia)
  - Curated ETFs (broad, sector, bonds, commodities, vol, leveraged, thematic, crypto)
  - Curated extras (ADRs, crypto miners, EVs, recent IPOs, popular optionable names)

Output: frontend/lib/options-universe.json
Each entry: { symbol, name, sector }

Live fields (price, IV, float, etc.) are filled at runtime by the screener;
this file just provides the universe of tradable tickers.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (LumareUniverseBuilder/1.0)"}


def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def parse_wikipedia_constituents(html: str, sym_col: int = 0, name_col: int = 1, sector_col: int = 2) -> list[dict]:
    """Parse a Wikipedia constituents table by column index."""
    # Find the constituents table
    m = re.search(r'<table[^>]*id="constituents"[^>]*>(.*?)</table>', html, re.DOTALL)
    if not m:
        return []
    table_html = m.group(1)
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)
    out: list[dict] = []
    for row in rows:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.DOTALL)
        if len(cells) <= max(sym_col, name_col, sector_col):
            continue
        def clean(c: str) -> str:
            c = re.sub(r"<[^>]+>", "", c)
            c = c.replace("&amp;", "&").replace("&nbsp;", " ")
            return c.strip()
        sym = clean(cells[sym_col])
        name = clean(cells[name_col])
        sector = clean(cells[sector_col]) if sector_col < len(cells) else ""
        if not sym or len(sym) > 6 or not re.match(r"^[A-Z][A-Z.\-]*$", sym):
            continue
        out.append({"symbol": sym, "name": name, "sector": sector})
    return out


def get_sp500() -> list[dict]:
    html = fetch("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
    return parse_wikipedia_constituents(html, sym_col=0, name_col=1, sector_col=2)


def get_sp400() -> list[dict]:
    html = fetch("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies")
    return parse_wikipedia_constituents(html, sym_col=0, name_col=1, sector_col=2)


def get_sp600() -> list[dict]:
    html = fetch("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies")
    return parse_wikipedia_constituents(html, sym_col=0, name_col=1, sector_col=2)


def get_nasdaq100() -> list[dict]:
    html = fetch("https://en.wikipedia.org/wiki/Nasdaq-100")
    # Nasdaq-100 page table often has Ticker col 1, Name col 0 — try both layouts
    out = parse_wikipedia_constituents(html, sym_col=1, name_col=0, sector_col=2)
    if not out:
        out = parse_wikipedia_constituents(html, sym_col=0, name_col=1, sector_col=2)
    return out


# Curated ETFs — broad market, sector SPDRs, bonds, commodities, vol, leveraged, thematic
ETFS = [
    # Broad market
    ("SPY", "SPDR S&P 500 ETF", "ETF - Broad Market"),
    ("VOO", "Vanguard S&P 500 ETF", "ETF - Broad Market"),
    ("IVV", "iShares Core S&P 500 ETF", "ETF - Broad Market"),
    ("QQQ", "Invesco QQQ Trust", "ETF - Broad Market"),
    ("QQQM", "Invesco Nasdaq 100 ETF", "ETF - Broad Market"),
    ("DIA", "SPDR Dow Jones Industrial Avg", "ETF - Broad Market"),
    ("IWM", "iShares Russell 2000 ETF", "ETF - Broad Market"),
    ("IWB", "iShares Russell 1000 ETF", "ETF - Broad Market"),
    ("VTI", "Vanguard Total Stock Market", "ETF - Broad Market"),
    ("MDY", "SPDR S&P MidCap 400", "ETF - Broad Market"),
    ("RSP", "Invesco S&P 500 Equal Weight", "ETF - Broad Market"),
    # Sector SPDRs
    ("XLK", "Technology Select Sector SPDR", "ETF - Sector"),
    ("XLF", "Financial Select Sector SPDR", "ETF - Sector"),
    ("XLE", "Energy Select Sector SPDR", "ETF - Sector"),
    ("XLV", "Health Care Select Sector SPDR", "ETF - Sector"),
    ("XLI", "Industrial Select Sector SPDR", "ETF - Sector"),
    ("XLY", "Consumer Discretionary SPDR", "ETF - Sector"),
    ("XLP", "Consumer Staples SPDR", "ETF - Sector"),
    ("XLU", "Utilities Select Sector SPDR", "ETF - Sector"),
    ("XLB", "Materials Select Sector SPDR", "ETF - Sector"),
    ("XLRE", "Real Estate Select Sector SPDR", "ETF - Sector"),
    ("XLC", "Communication Services SPDR", "ETF - Sector"),
    ("SMH", "VanEck Semiconductor ETF", "ETF - Sector"),
    ("SOXX", "iShares Semiconductor ETF", "ETF - Sector"),
    ("KRE", "SPDR S&P Regional Banking", "ETF - Sector"),
    ("KBE", "SPDR S&P Bank ETF", "ETF - Sector"),
    ("XBI", "SPDR S&P Biotech ETF", "ETF - Sector"),
    ("IBB", "iShares Biotechnology ETF", "ETF - Sector"),
    ("ITB", "iShares Home Construction", "ETF - Sector"),
    ("XRT", "SPDR S&P Retail ETF", "ETF - Sector"),
    ("XOP", "SPDR S&P Oil and Gas E&P", "ETF - Sector"),
    ("OIH", "VanEck Oil Services ETF", "ETF - Sector"),
    ("XHB", "SPDR S&P Homebuilders", "ETF - Sector"),
    ("JETS", "US Global Jets ETF", "ETF - Sector"),
    # Bonds
    ("TLT", "iShares 20+ Year Treasury", "ETF - Bonds"),
    ("IEF", "iShares 7-10 Year Treasury", "ETF - Bonds"),
    ("SHY", "iShares 1-3 Year Treasury", "ETF - Bonds"),
    ("LQD", "iShares iBoxx Investment Grade", "ETF - Bonds"),
    ("HYG", "iShares iBoxx High Yield", "ETF - Bonds"),
    ("JNK", "SPDR Bloomberg High Yield", "ETF - Bonds"),
    ("AGG", "iShares Core US Aggregate Bond", "ETF - Bonds"),
    ("BND", "Vanguard Total Bond Market", "ETF - Bonds"),
    ("TIP", "iShares TIPS Bond ETF", "ETF - Bonds"),
    # Commodities and currency
    ("GLD", "SPDR Gold Shares", "ETF - Commodities"),
    ("IAU", "iShares Gold Trust", "ETF - Commodities"),
    ("SLV", "iShares Silver Trust", "ETF - Commodities"),
    ("USO", "United States Oil Fund", "ETF - Commodities"),
    ("UNG", "United States Natural Gas", "ETF - Commodities"),
    ("DBA", "Invesco DB Agriculture", "ETF - Commodities"),
    ("DBC", "Invesco DB Commodity Index", "ETF - Commodities"),
    ("UUP", "Invesco DB US Dollar Bullish", "ETF - Commodities"),
    ("FXE", "Invesco CurrencyShares Euro", "ETF - Commodities"),
    # Vol
    ("VXX", "iPath Series B S&P 500 VIX ST", "ETF - Volatility"),
    ("UVXY", "ProShares Ultra VIX ST Futures", "ETF - Volatility"),
    ("SVXY", "ProShares Short VIX ST Futures", "ETF - Volatility"),
    # Leveraged and inverse
    ("TQQQ", "ProShares UltraPro QQQ", "ETF - Leveraged"),
    ("SQQQ", "ProShares UltraPro Short QQQ", "ETF - Leveraged"),
    ("UPRO", "ProShares UltraPro S&P 500", "ETF - Leveraged"),
    ("SPXU", "ProShares UltraPro Short S&P", "ETF - Leveraged"),
    ("SPXL", "Direxion Daily S&P 500 Bull 3X", "ETF - Leveraged"),
    ("SPXS", "Direxion Daily S&P 500 Bear 3X", "ETF - Leveraged"),
    ("SOXL", "Direxion Daily Semis Bull 3X", "ETF - Leveraged"),
    ("SOXS", "Direxion Daily Semis Bear 3X", "ETF - Leveraged"),
    ("TNA", "Direxion Daily Sm Cap Bull 3X", "ETF - Leveraged"),
    ("TZA", "Direxion Daily Sm Cap Bear 3X", "ETF - Leveraged"),
    ("FAS", "Direxion Daily Financial Bull", "ETF - Leveraged"),
    ("FAZ", "Direxion Daily Financial Bear", "ETF - Leveraged"),
    ("LABU", "Direxion Daily Biotech Bull 3X", "ETF - Leveraged"),
    ("LABD", "Direxion Daily Biotech Bear 3X", "ETF - Leveraged"),
    ("TMF", "Direxion Daily 20+ Treasury 3X", "ETF - Leveraged"),
    ("TMV", "Direxion Daily 20+ Tsy Bear 3X", "ETF - Leveraged"),
    ("NUGT", "Direxion Daily Gold Miners Bull", "ETF - Leveraged"),
    ("DUST", "Direxion Daily Gold Miners Bear", "ETF - Leveraged"),
    ("JNUG", "Direxion Jr Gold Miners Bull", "ETF - Leveraged"),
    ("JDST", "Direxion Jr Gold Miners Bear", "ETF - Leveraged"),
    ("YINN", "Direxion Daily China Bull 3X", "ETF - Leveraged"),
    ("YANG", "Direxion Daily China Bear 3X", "ETF - Leveraged"),
    # Thematic
    ("ARKK", "ARK Innovation ETF", "ETF - Thematic"),
    ("ARKG", "ARK Genomic Revolution ETF", "ETF - Thematic"),
    ("ARKQ", "ARK Autonomous Tech and Robotics", "ETF - Thematic"),
    ("ARKW", "ARK Next Generation Internet", "ETF - Thematic"),
    ("ARKF", "ARK Fintech Innovation ETF", "ETF - Thematic"),
    ("ICLN", "iShares Global Clean Energy", "ETF - Thematic"),
    ("TAN", "Invesco Solar ETF", "ETF - Thematic"),
    ("LIT", "Global X Lithium and Battery", "ETF - Thematic"),
    ("PAVE", "Global X US Infrastructure", "ETF - Thematic"),
    ("BOTZ", "Global X Robotics and AI", "ETF - Thematic"),
    ("ROBO", "ROBO Global Robotics ETF", "ETF - Thematic"),
    ("AIQ", "Global X AI and Tech ETF", "ETF - Thematic"),
    ("HACK", "ETFMG Prime Cyber Security", "ETF - Thematic"),
    ("CIBR", "First Trust NASDAQ Cybersecurity", "ETF - Thematic"),
    ("FINX", "Global X Fintech ETF", "ETF - Thematic"),
    # International
    ("EEM", "iShares MSCI Emerging Markets", "ETF - International"),
    ("VWO", "Vanguard FTSE Emerging Mkts", "ETF - International"),
    ("EFA", "iShares MSCI EAFE", "ETF - International"),
    ("FXI", "iShares China Large-Cap", "ETF - International"),
    ("MCHI", "iShares MSCI China", "ETF - International"),
    ("EWZ", "iShares MSCI Brazil", "ETF - International"),
    ("EWJ", "iShares MSCI Japan", "ETF - International"),
    ("INDA", "iShares MSCI India", "ETF - International"),
    ("KWEB", "KraneShares CSI China Internet", "ETF - International"),
    # Crypto-related
    ("BITO", "ProShares Bitcoin Strategy", "ETF - Crypto"),
    ("IBIT", "iShares Bitcoin Trust", "ETF - Crypto"),
    ("FBTC", "Fidelity Wise Origin Bitcoin", "ETF - Crypto"),
    ("ETHE", "Grayscale Ethereum Trust", "ETF - Crypto"),
    ("GBTC", "Grayscale Bitcoin Trust", "ETF - Crypto"),
]

# Curated extras — popular optionable names not always in indexes
EXTRAS = [
    # Chinese ADRs
    ("BABA", "Alibaba Group", "Consumer Discretionary"),
    ("JD", "JD.com", "Consumer Discretionary"),
    ("PDD", "PDD Holdings", "Consumer Discretionary"),
    ("BIDU", "Baidu", "Communication Services"),
    ("NIO", "NIO Inc", "Consumer Discretionary"),
    ("LI", "Li Auto", "Consumer Discretionary"),
    ("XPEV", "XPeng", "Consumer Discretionary"),
    ("BILI", "Bilibili", "Communication Services"),
    ("TME", "Tencent Music", "Communication Services"),
    ("IQ", "iQIYI", "Communication Services"),
    # Crypto miners and infra
    ("MARA", "Marathon Digital", "Financials"),
    ("RIOT", "Riot Platforms", "Financials"),
    ("CLSK", "CleanSpark", "Financials"),
    ("HUT", "Hut 8 Mining", "Financials"),
    ("BITF", "Bitfarms", "Financials"),
    ("CIFR", "Cipher Mining", "Financials"),
    ("WULF", "TeraWulf", "Financials"),
    ("HIVE", "HIVE Digital", "Financials"),
    ("BTBT", "Bit Digital", "Financials"),
    ("COIN", "Coinbase Global", "Financials"),
    ("HOOD", "Robinhood Markets", "Financials"),
    ("MSTR", "MicroStrategy", "Technology"),
    # EV and clean energy
    ("RIVN", "Rivian Automotive", "Consumer Discretionary"),
    ("LCID", "Lucid Group", "Consumer Discretionary"),
    ("FSR", "Fisker", "Consumer Discretionary"),
    ("PLUG", "Plug Power", "Industrials"),
    ("FCEL", "FuelCell Energy", "Industrials"),
    ("BLNK", "Blink Charging", "Industrials"),
    ("CHPT", "ChargePoint", "Industrials"),
    ("QS", "QuantumScape", "Industrials"),
    # Recent IPOs and meme
    ("SOFI", "SoFi Technologies", "Financials"),
    ("AFRM", "Affirm Holdings", "Financials"),
    ("UPST", "Upstart Holdings", "Financials"),
    ("PATH", "UiPath", "Technology"),
    ("DKNG", "DraftKings", "Consumer Discretionary"),
    ("PENN", "PENN Entertainment", "Consumer Discretionary"),
    ("LYFT", "Lyft", "Industrials"),
    ("UBER", "Uber Technologies", "Industrials"),
    ("ABNB", "Airbnb", "Consumer Discretionary"),
    ("DASH", "DoorDash", "Consumer Discretionary"),
    ("RBLX", "Roblox", "Communication Services"),
    ("U", "Unity Software", "Technology"),
    ("PLTR", "Palantir Technologies", "Technology"),
    ("SNOW", "Snowflake", "Technology"),
    ("DDOG", "Datadog", "Technology"),
    ("NET", "Cloudflare", "Technology"),
    ("CRWD", "CrowdStrike", "Technology"),
    ("ZS", "Zscaler", "Technology"),
    ("OKTA", "Okta", "Technology"),
    ("MDB", "MongoDB", "Technology"),
    ("TEAM", "Atlassian", "Technology"),
    ("ZM", "Zoom Video", "Technology"),
    ("DOCU", "DocuSign", "Technology"),
    ("SHOP", "Shopify", "Technology"),
    ("SQ", "Block", "Technology"),
    ("PYPL", "PayPal", "Financials"),
    # Meme and high-vol
    ("GME", "GameStop", "Consumer Discretionary"),
    ("AMC", "AMC Entertainment", "Communication Services"),
    ("BB", "BlackBerry", "Technology"),
    ("BBBY", "Bed Bath and Beyond", "Consumer Discretionary"),
    ("NOK", "Nokia", "Technology"),
    ("SPCE", "Virgin Galactic", "Industrials"),
    # Cannabis
    ("TLRY", "Tilray Brands", "Consumer Staples"),
    ("CGC", "Canopy Growth", "Consumer Staples"),
    ("ACB", "Aurora Cannabis", "Consumer Staples"),
    ("CRON", "Cronos Group", "Consumer Staples"),
    ("SNDL", "SNDL Inc", "Consumer Staples"),
    # Big foreign listings
    ("TSM", "Taiwan Semiconductor", "Technology"),
    ("ASML", "ASML Holding", "Technology"),
    ("NVO", "Novo Nordisk", "Health Care"),
    ("SAP", "SAP SE", "Technology"),
    ("TM", "Toyota Motor", "Consumer Discretionary"),
    ("SHEL", "Shell plc", "Energy"),
    ("BP", "BP plc", "Energy"),
    ("HSBC", "HSBC Holdings", "Financials"),
    ("UL", "Unilever", "Consumer Staples"),
    # Streaming and media
    ("WBD", "Warner Bros Discovery", "Communication Services"),
    ("PARA", "Paramount Global", "Communication Services"),
    ("ROKU", "Roku", "Communication Services"),
    ("SPOT", "Spotify Technology", "Communication Services"),
    ("PINS", "Pinterest", "Communication Services"),
    ("SNAP", "Snap", "Communication Services"),
    # Misc popular optionable
    ("F", "Ford Motor", "Consumer Discretionary"),
    ("GM", "General Motors", "Consumer Discretionary"),
    ("BAC", "Bank of America", "Financials"),
    ("WFC", "Wells Fargo", "Financials"),
    ("C", "Citigroup", "Financials"),
    ("T", "AT&T", "Communication Services"),
    ("VZ", "Verizon", "Communication Services"),
    ("INTC", "Intel", "Technology"),
    ("AMD", "Advanced Micro Devices", "Technology"),
    ("MU", "Micron Technology", "Technology"),
    ("DELL", "Dell Technologies", "Technology"),
    ("HPQ", "HP Inc", "Technology"),
    ("ORCL", "Oracle", "Technology"),
    ("IBM", "IBM", "Technology"),
    ("CSCO", "Cisco Systems", "Technology"),
    # Recent AI darlings
    ("SMCI", "Super Micro Computer", "Technology"),
    ("ARM", "Arm Holdings", "Technology"),
    ("AI", "C3.ai", "Technology"),
    ("SOUN", "SoundHound AI", "Technology"),
    ("BBAI", "BigBear.ai", "Technology"),
]


def normalize(sym: str) -> str:
    return sym.replace(".", "-").upper().strip()


def main() -> int:
    universe: dict[str, dict] = {}

    sources = [
        ("S&P 500", get_sp500),
        ("S&P 400", get_sp400),
        ("S&P 600", get_sp600),
        ("Nasdaq 100", get_nasdaq100),
    ]

    for label, fn in sources:
        try:
            entries = fn()
            print(f"  {label}: {len(entries)} entries", file=sys.stderr)
            for e in entries:
                sym = normalize(e["symbol"])
                if sym not in universe:
                    universe[sym] = {"symbol": sym, "name": e["name"], "sector": e["sector"] or "Equity"}
        except Exception as exc:
            print(f"  {label} FAILED: {exc}", file=sys.stderr)

    for sym, name, sector in ETFS:
        sym = normalize(sym)
        if sym not in universe:
            universe[sym] = {"symbol": sym, "name": name, "sector": sector}

    for sym, name, sector in EXTRAS:
        sym = normalize(sym)
        if sym not in universe:
            universe[sym] = {"symbol": sym, "name": name, "sector": sector}

    out = sorted(universe.values(), key=lambda e: e["symbol"])
    print(f"  TOTAL: {len(out)} unique tickers", file=sys.stderr)

    out_path = Path(__file__).resolve().parents[1] / "frontend" / "lib" / "options-universe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"  wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
