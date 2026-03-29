# LUMARE — Revenue Model

---

## Subscription Tiers (Consumer)

| Tier | Price | Features |
|------|-------|----------|
| **Core** | $0/mo | Portfolio tracker, basic markets view, limited analysis, basic financial planning |
| **Wealth** | $49/mo | Full Intel (all 7 analysis modules), options flow, AI analysis, copy trading, macro dashboard, Risk War Room, Strategy Marketplace access |
| **Private** | $199/mo | Everything in Wealth + dedicated advisor access, 1:1 portfolio reviews, custom entry mapping, priority research queue, advanced Portfolio Builder |

---

## B2B / Institutional

| Product | Price | Description |
|---------|-------|-------------|
| **RIA Seat** | $500–2,000/mo | Multi-client portfolio dashboards, white-label option, compliance tools, client-facing reports |

---

## AUM-Based Revenue

| Product | Fee | Description |
|---------|-----|-------------|
| **Managed** | 0.75% AUM annually | Lumare manages the user's portfolio using platform intelligence + trading algorithm. User opts in, Lumare handles allocation, rebalancing, and execution |

---

## Platform Revenue

| Product | Fee | Description |
|---------|-----|-------------|
| **Strategy Marketplace** | 20% take rate | When a strategy creator publishes a signal stream and users subscribe, Lumare takes 20% of the subscription fee. Creator keeps 80% |

---

## Endgame Revenue

| Product | Fee | Description |
|---------|-----|-------------|
| **Proprietary Fund** | 2% management + 20% performance | Lumare runs the trading bot on its own capital (or pooled investor capital). Traditional hedge fund structure. Requires regulatory licensing |

---

## Revenue Flywheel

```
Free users → Wealth subscribers → Managed AUM → Strategy publishers
     ↓              ↓                    ↓                ↓
  User data    Recurring SaaS      AUM fees      Marketplace take rate
     ↓              ↓                    ↓                ↓
  Better AI    Fund platform        Scale capital    Network effects
                                         ↓
                                  Proprietary Fund (2/20)
```

---

## API Cost Structure

| Service | Monthly Cost | Notes |
|---------|-------------|-------|
| Polygon.io | $29/mo | Market data |
| Unusual Whales | $50/mo | Options flow |
| Quiver Quant | Free | Congressional trades |
| FRED | Free | Macro data |
| Anthropic Claude | Usage-based (~$50-200/mo early) | AI analysis engine |
| Supabase | Free tier → $25/mo | Auth + database |
| Vercel | Free tier → $20/mo | Hosting |
| **Total early-stage** | **~$175–325/mo** | Before meaningful user load |

---

## Break-Even Analysis

At $49/mo Wealth tier:
- 7 Wealth subscribers = covers all API costs
- 50 Wealth subscribers = $2,450 MRR
- 200 Wealth subscribers = $9,800 MRR
- 1,000 Wealth subscribers = $49,000 MRR

At $199/mo Private tier:
- 2 Private subscribers = covers all API costs
- 50 Private subscribers = $9,950 MRR

Managed AUM at 0.75%:
- $1M AUM = $7,500/yr
- $10M AUM = $75,000/yr
- $100M AUM = $750,000/yr
