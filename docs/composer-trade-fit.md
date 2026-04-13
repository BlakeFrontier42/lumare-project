# Composer.trade — Fit Assessment for Lumare

**Author:** Lumare engineering
**Date:** 2026-04-08
**Question:** Should Lumare integrate with, compete against, or ignore Composer.trade?

---

## What Composer is

Composer is a **no-code, visual algo-trading platform for US equities and ETFs.**
Users drag-and-drop "blocks" (`if RSI < 30 → buy SPY`, `sort top 5 by 1-year
momentum`, etc.) into a decision tree called a *symphony*. Composer then:

1. Executes the symphony at market close (or intraday in some tiers) through
   its own brokerage relationship — **Composer is a registered broker-dealer**,
   so trades happen inside user accounts on Composer's books, not forwarded
   to a third party.
2. Offers a public marketplace where users can browse and one-click-clone
   other people's symphonies.
3. Charges a flat monthly subscription (~$20–$80/mo in 2025) with no per-trade
   fees.

**What it does well:**
- Frictionless onboarding for non-coders who already understand technical
  signals.
- Real, audited execution with no "paper-only" asterisk.
- Public symphony marketplace generates organic discovery and social proof.

**What it does poorly:**
- No shorting, no options, no crypto, no futures. US equities and ETFs only.
- No regime awareness. Symphonies re-evaluate at rebalance time; there is
  no concept of "the macro backdrop changed, reduce gross exposure."
- No proprietary alpha feeds — everything is derived from public OHLCV.
  No insider filings, no congressional trades, no float/short data, no
  macro compass.
- No discretionary layer. You cannot override the bot with a manual trade
  while keeping the bot running on everything else.
- Tree logic tops out around 5–6 levels deep before becoming unreadable.
  Complex strategies get pushed into code regardless.

---

## Where Lumare sits relative to Composer

|                              | Composer                              | Lumare                                               |
|------------------------------|---------------------------------------|------------------------------------------------------|
| Target user                  | Retail, no-code                       | Prosumer / semi-pro, some code literacy              |
| Asset classes                | US equities + ETFs                    | Equities, crypto (Blowfin), options screener, FX    |
| Strategy authoring           | Visual symphony (drag-drop)           | Python agents + config + backtest replay            |
| Execution                    | Composer's own BD, real $             | Paper engine + Blowfin crypto live + IB pipe        |
| Alpha feeds                  | OHLCV-derived only                    | Insider (EDGAR), Congress (Quiver), Float, Macro, Perplexity research, options flow |
| Regime / macro overlay       | None                                  | Agent-spine Macro Compass (WIP Phase 5)              |
| Shorts                       | No                                    | Yes (in scoring engine, gated by regime)             |
| Backtest depth               | Rebalance-level, daily bars           | 5-min bars, full tick replay, walk-forward eval     |
| Social marketplace           | Yes (symphonies)                      | No                                                   |
| Price                        | ~$20–80/mo                            | TBD                                                   |

The overlap is real but partial: **Composer is a product for people who
don't want to run code; Lumare is a product for people who want institutional
feeds without setting up a Bloomberg terminal.** Different users, different
value props.

---

## Options

### A. Ignore

Composer doesn't touch crypto, options, shorts, or macro regime gating —
i.e. most of Lumare's differentiators. A retail stock-ETF user on Composer
is not a Lumare user today. **Low risk, zero cost, loses nothing.**

### B. Compete head-on

Build a visual symphony editor inside Lumare. *Don't do this.* Composer has a
four-year head start on the UX, a live-trading brokerage relationship, and
a marketplace network effect. Re-implementing it burns a year of engineering
for no edge.

### C. Integrate — "Composer symphonies as a Lumare signal source"

This is the interesting option. Treat Composer's public marketplace as a
**crowd-sourced alpha feed**:

- Scrape or API-ingest the top-performing public symphonies.
- Track which symphonies are currently holding which tickers.
- Surface "Composer Top 20 symphony consensus longs" as a new panel on the
  Alpha page, alongside the congressional-trade and insider feeds.
- Use symphony position changes as a **sentiment signal** for the Macro Compass.
  If 15 of the top 20 symphonies just rotated from SPY to TLT, that's a
  retail-quant risk-off cue.

This positions Lumare one layer *above* Composer — "we ingest Composer as one
of 8 feeds, not as the thing you're interacting with." Composer users are
not cannibalized; Lumare users get a differentiated social-signal lens on
a platform they already know.

### D. Clone Composer's symphony format as a *strategy import path*

Allow users to paste a Composer symphony JSON into Lumare and have Lumare's
backtest engine replay it on 5-min bars. This is a migration magnet — "you
already built this on Composer, here's how it looks on 5-min data with our
risk engine on top." Low implementation cost (~1 week for a symphony→Python
transpiler for the common block types) and it gives curious Composer users
a concrete reason to try Lumare.

---

## Recommendation

**Do (C) + (D), skip (A) and (B).**

1. **Now (Phase 5, ~3 days):** Add a `ComposerFeed` adapter under
   `backend/data/` that pulls the public marketplace leaderboard and
   serializes the top-N symphonies' current positions as a new alpha stream.
   Wire it into the Alpha page as a fourth tab.

2. **Next (Phase 6, ~1 week):** Write a Composer symphony → Lumare strategy
   transpiler that handles the ~80% of blocks people actually use
   (moving-average cross, RSI, sort-by-momentum, allocate-equal-weight).
   Stub the long tail. Use it as an onboarding funnel: "Paste your Composer
   symphony here to see it run on 5-minute bars with our risk overlay."

3. **Never:** Build a visual symphony editor inside Lumare. That's their
   product. We win on depth-of-signal and cross-asset breadth, not on
   no-code authoring.

---

## Why this works

- Composer's defensive moat is marketplace + no-code UX. We don't attack
  either. They have no reason to retaliate.
- Lumare's defensive moat is proprietary alpha feeds (insider, congress,
  float, macro, options flow, Perplexity research) and regime-aware risk.
  Ingesting Composer as a *signal* deepens that moat instead of diluting it.
- The transpiler converts Composer's users into our users without requiring
  them to throw away what they've built — the textbook "Compatibility
  pricing" move from Carl Shapiro's *Information Rules*.
- We stay out of the broker-dealer regulatory burden Composer has to carry.
  Lumare remains a signal + paper + third-party-broker platform, which is
  a 10x cheaper regulatory posture.

---

## Open questions

- Does Composer have an official API for symphony metadata, or do we need
  to scrape? (Affects whether (C) is 3 days or 3 weeks.)
- How strict is Composer's ToS on automated scraping of public symphonies?
- Which symphony block types make up ~80% of published symphonies? We need
  this to scope the transpiler (D).

All three are answered with 1–2 days of research on composer.trade + its
developer docs before writing any code.
