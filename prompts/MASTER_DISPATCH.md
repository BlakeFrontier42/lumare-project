# LUMARE — Master Dispatch Prompt

> Use this as the primary context prompt when starting a Claude Code session on the Lumare project.

---

## Project Overview

You are working on **Lumare** — a Capital Intelligence OS that combines Bloomberg Terminal-grade market intelligence with consumer-friendly design. It's a vertically integrated platform for portfolio tracking, AI-powered technical analysis, macro intelligence, copy trading, political alpha, strategy marketplace, risk management, financial planning, and automated trade execution.

## Project Structure

```
lumare-project/
├── README.md                    # Master index — read this first
├── docs/
│   ├── PRODUCT_SPEC.md          # Every feature, every screen, every detail
│   ├── ARCHITECTURE.md          # Tech stack, APIs, system design
│   ├── ALGORITHM.md             # Trading engine (MIE) full spec
│   ├── UI_DESIGN.md             # Design system + desktop improvement plan
│   ├── VISION.md                # Long-term product vision & moat
│   ├── REVENUE_MODEL.md         # Pricing tiers & revenue streams
│   └── ROADMAP.md               # Phased development plan
├── ui/
│   ├── ARTIFACTS_README.md      # Links to existing React mockups
│   ├── lumare_artifact_v1.jsx   # (USER MUST PASTE — see ARTIFACTS_README)
│   ├── lumare_artifact_v2.jsx   # (USER MUST PASTE — see ARTIFACTS_README)
│   └── lumare_artifact_v3.jsx   # (USER MUST PASTE — see ARTIFACTS_README)
├── prompts/
│   ├── MASTER_DISPATCH.md       # This file
│   ├── FRONTEND_ARCHITECT.md    # Prompt for frontend/UI work
│   └── QUANT_ARCHITECT.md       # Prompt for algorithm/engine work
├── backend/                     # MIE engine scaffold (empty — to be built)
│   ├── core/
│   ├── data/
│   ├── execution/
│   ├── backtest/
│   ├── live/
│   └── config/
├── config/
│   ├── env.example              # Template for environment variables
│   └── next.config.example.js   # Next.js config template
└── assets/
    └── lumare_investor_brief.pdf # One-page investor deck
```

## How to Start

### For Frontend Work:
1. Read `docs/PRODUCT_SPEC.md` + `docs/UI_DESIGN.md`
2. Load the prompt from `prompts/FRONTEND_ARCHITECT.md`
3. Check `ui/` for existing mockup code
4. Follow `docs/ROADMAP.md` Phase 0

### For Algorithm Work:
1. Read `docs/ALGORITHM.md` (this is the bible)
2. Load the prompt from `prompts/QUANT_ARCHITECT.md`
3. Follow the MANDATORY development order
4. Build in `backend/`

### For Full-Stack Integration:
1. Read `docs/ARCHITECTURE.md` for the system diagram
2. Read `docs/PRODUCT_SPEC.md` for what each API powers
3. Set up environment variables per `config/env.example`

## Critical Reminders

1. **Desktop UI needs elevation** — mobile is strong, desktop is weak. See UI_DESIGN.md.
2. **Plan tab is missing** — existed in earlier version, must be re-added.
3. **Macro portfolio builder is missing** — existed in earlier version, must be restored.
4. **All data is currently mock** — real APIs are documented but not integrated.
5. **Algorithm has MANDATORY build order** — do not skip steps.
6. **Design is STRICTLY monochrome** — no accent colors. Green/red only for P&L.
7. **The artifact JSX files need to be manually pasted** — links require auth.
