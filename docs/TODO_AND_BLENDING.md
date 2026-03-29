# LUMARE — What Needs to Be Added, Blended & Fixed

This document is a running list of features, fixes, and integration tasks. Use this as a punch list when building.

---

## FEATURES TO RESTORE (existed in earlier versions, missing in current)

### 1. Plan Tab (Financial Planning)
- **Status**: Was in an earlier artifact, dropped in most recent
- **What it had**: Net worth unification, retirement modeling, goal tracking, budget tracking
- **Action**: Re-add to main navigation as 6th tab (Home, Markets, Intel, Macro, Plan, Profile)
- **Enhancements to add**: MoneyGuidePro integration option, Monte Carlo simulations, tax optimization

### 2. Macro Portfolio Builder
- **Status**: Earlier version had a macro aspect that allows building a portfolio. Disappeared in most recent.
- **Action**: Find in earlier artifact versions, restore, and blend with current Portfolio Builder
- **Where it fits**: Could live as a sub-feature within Macro tab or as part of Portfolio Builder step 3/4

---

## FEATURES TO ADD (new, not yet built)

### 3. Predictive Liquidity Mapping
- Dashboard tracking: Global M2, reverse repo, Treasury issuance, corporate debt maturity walls, FX flows, ETF flows
- Output: Liquidity Heatmap visualization
- Tab: New sub-tab within Macro, or standalone page

### 4. Smart Capital Rotation Engine
- Proactive rebalancing suggestions based on macro conditions
- Example: "Tech overextended vs liquidity. Rotate 12% to short-duration Treasuries."
- Tab: Integrates into Home dashboard as recommendation cards

### 5. Behavioral Guardrails
- Emotional trading pattern detection
- Risk profile deviation warnings
- Impulsive reallocation tracking
- Cooldown period suggestions
- Tab: Integrates into Profile → Settings and as overlay warnings

### 6. Capital Efficiency Optimization
- Tax efficiency suggestions (tax-loss harvesting)
- Margin efficiency tracking
- Capital velocity metrics
- Options overlay recommendations (covered calls, CSPs)
- Tab: Sub-section within Plan or Portfolio Builder output

### 7. Autonomous Capital Arm
- AI runs small % of capital autonomously
- Public performance scoring
- Transparent track record
- Tab: Part of Strategy Marketplace (Lumare's own bot card)

---

## DESKTOP UI FIXES (see UI_DESIGN.md for full spec)

### 8. Left Sidebar Navigation
- Replace bottom tabs with collapsible sidebar on desktop
- Icon-only by default (~64px), expands on hover (~240px)

### 9. Multi-Column Layouts
- Home: grid layout for net worth + allocation + actions
- Markets: split-pane (watchlist left, detail right)
- All data-heavy views: proper tables, not stacked cards

### 10. Data Tables
- Options flow → data table with sorting/filtering
- Congressional trades → data table
- Insider transactions → data table
- Strategy leaderboard → data table
- Positions → data table with real-time P&L

### 11. Keyboard Navigation
- `/` to search, `j/k` to navigate, `Enter` to open, `Esc` to close

### 12. Hover States & Micro-Interactions
- Card hover elevation
- Number ticking animations on price updates
- Smooth tab transitions

---

## API INTEGRATIONS (currently all mock data)

### 13. Polygon.io → Markets tab prices, Asset Detail charts
### 14. Claude API → Intel tab analysis, Portfolio Builder generation
### 15. Alpaca API → Trade tab execution (paper + live)
### 16. Unusual Whales → Flow tab options data
### 17. Quiver Quant → Alpha tab congressional trades
### 18. FRED API → Macro tab economic data
### 19. SEC EDGAR → Alpha tab insider transactions
### 20. Blowfin API → Crypto trading (MIE Phase 1)

---

## INFRASTRUCTURE (not yet built)

### 21. Supabase Auth (email/password + OAuth)
### 22. Stripe Billing (Core/Wealth/Private tiers)
### 23. Vercel Deployment
### 24. Domain Registration (lumare.app)
### 25. Waitlist Landing Page

---

## BLENDING NOTES

When combining the three artifact versions:
- **Take navigation structure from**: Latest version (most complete)
- **Take Plan tab from**: Earlier version that had it
- **Take Macro Portfolio Builder from**: Version that had macro-driven portfolio construction
- **Take mobile layout from**: Latest version (strongest)
- **Rebuild desktop layout**: Fresh, following UI_DESIGN.md specs
- **Merge all features**: Union of all features across all versions, nothing dropped
