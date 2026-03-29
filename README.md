# LUMARE — Capital Intelligence OS

> Bloomberg Terminal × Renaissance Technologies × Stripe for Capital Allocation

This is the complete project repository for **Lumare**, a vertically integrated private banking and market intelligence platform. This README is the master index for Claude Code or any developer to understand the full scope, current state, and next steps.

---

## Quick Links

| Document | Path | Description |
|----------|------|-------------|
| Product Spec | `docs/PRODUCT_SPEC.md` | Full feature spec for every tab/page |
| Architecture | `docs/ARCHITECTURE.md` | Tech stack, APIs, system design |
| Algorithm | `docs/ALGORITHM.md` | Trading engine spec (MIE) |
| UI Notes | `docs/UI_DESIGN.md` | Design system, desktop improvement notes |
| Revenue Model | `docs/REVENUE_MODEL.md` | Tiers, pricing, marketplace economics |
| Vision | `docs/VISION.md` | Long-term product vision & moat |
| Investor Brief | `assets/lumare_investor_brief.pdf` | One-page investor deck |
| Dev Roadmap | `docs/ROADMAP.md` | Phased build order |
| Prompts | `prompts/` | System prompts for Claude Code agents |
| UI Artifacts | `ui/` | Links & notes for existing React mockups |
| Backend Scaffold | `backend/` | MIE engine folder structure |
| Config | `config/` | Environment variables, settings templates |

---

## Current State

- **Frontend**: Single-file React JSX mockup (lumare_v3.jsx) with full navigation, mock data, and 5-tab layout. Mobile UI is strong. Desktop needs elevation.
- **Backend**: Not yet built. Architecture fully specced.
- **Algorithm**: Fully designed. Not yet coded. Phase 1 = crypto (Blowfin), Phase 2 = equities (Alpaca).
- **Data**: All mock. Real APIs identified and documented.
- **Auth/Payments**: Not yet built. Supabase + Stripe planned.

---

## How to Use This Repo with Claude Code

1. Read `README.md` (this file) for orientation
2. Read `docs/PRODUCT_SPEC.md` for what every screen does
3. Read `docs/ARCHITECTURE.md` for how it's built
4. Read `docs/ALGORITHM.md` for the trading engine
5. Read `docs/ROADMAP.md` for build order
6. Check `prompts/` for role-specific system prompts
7. Check `ui/` for existing artifact links and design notes
8. Start building per the roadmap phases
"# lumare-project" 
