# LUMARE — UI Design System & Desktop Improvement Notes

---

## Current State

- Mobile UI: **Strong**. Clean, dark, minimal, well-structured.
- Desktop UI: **Needs significant elevation**. Looks low-quality compared to mobile.

## Goal

Make the desktop UI as clean and polished as the mobile version, but **unique in its own way** — not just a stretched mobile layout. Think Bloomberg Terminal meets Apple Design Language: information-dense but visually elegant.

---

## Design Tokens

### Typography
| Role | Font | Weight | Usage |
|------|------|--------|-------|
| Headings | Space Grotesk | 600–700 | Page titles, section headers, card titles |
| Body | Inter | 400–500 | Paragraphs, descriptions, labels |
| Numbers/Data | Space Mono | 400–500 | Prices, percentages, scores, metrics |

### Colors
| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#080808` | Page background |
| `--bg-card` | `#111111` | Card/panel background |
| `--bg-elevated` | `#1a1a1a` | Hover states, elevated surfaces |
| `--text-primary` | `#ffffff` | Primary text |
| `--text-secondary` | `#888888` | Secondary text, labels |
| `--text-tertiary` | `#555555` | Disabled, muted text |
| `--border` | `#1e1e1e` | Subtle borders |
| `--green` | `#22c55e` | Profit, buy signals, positive |
| `--red` | `#e05252` | Loss, sell signals, negative |
| `--accent` | None | No accent color. Monochrome only. |

**Rule**: Color is used ONLY for P&L signals (green/red). Everything else is grayscale.

### Spacing
- Base unit: 4px
- Common spacing: 8px, 12px, 16px, 24px, 32px, 48px
- Card padding: 20px–24px
- Section gaps: 24px–32px

### Border Radius
- Cards: 12px
- Buttons: 8px
- Chips/badges: 6px
- Inputs: 8px

---

## Desktop-Specific Design Principles

### 1. Information Density
Desktop users expect more data visible at once. Use multi-column layouts, side-by-side panels, and data tables. Don't just center a narrow column on a wide screen.

### 2. Sidebar Navigation
Replace bottom tab bar with a left sidebar on desktop:
- Collapsed by default (icon-only, ~64px wide)
- Expands on hover or click (~240px)
- Shows: Logo, nav items (Home, Markets, Intel, Macro, Plan), divider, Strategy Marketplace, Risk War Room, Portfolio Builder, divider, Profile, Settings

### 3. Dashboard Grid Layout
Home page on desktop should use a CSS Grid layout:
- Net worth hero card (spans full width)
- Asset allocation chart + breakdown (2 columns)
- Quick action cards (3 columns)
- Recent activity feed (right sidebar panel)

### 4. Split-Pane Views
For Markets → Asset Detail:
- Left panel: watchlist (persistent)
- Right panel: chart + analysis + trade (switches on asset click)
- No full-page navigation — stays in context

### 5. Data Tables
Desktop should use proper data tables (not stacked cards) for:
- Options flow
- Congressional trades
- Insider transactions
- Strategy leaderboard
- Portfolio positions

### 6. Keyboard Navigation
Support keyboard shortcuts:
- `/` to focus search
- `j/k` to navigate lists
- `Enter` to open detail
- `Esc` to close panels

### 7. Subtle Micro-Interactions
- Card hover: slight elevation (`translateY(-1px)`) + border glow (`border-color: #2a2a2a`)
- Data transitions: number ticking animations on price changes
- Tab switches: smooth fade/slide transitions
- Charts: crosshair cursor with data tooltip

---

## Desktop Layout Reference

```
┌──────┬──────────────────────────────────────────────┐
│      │                                               │
│  S   │              Main Content Area                │
│  I   │                                               │
│  D   │  ┌─────────────────┐  ┌──────────────────┐  │
│  E   │  │                 │  │                    │  │
│  B   │  │   Primary       │  │   Secondary        │  │
│  A   │  │   Panel         │  │   Panel            │  │
│  R   │  │                 │  │                    │  │
│      │  └─────────────────┘  └──────────────────────┘  │
│      │                                               │
│      │  ┌──────────┐ ┌──────────┐ ┌──────────┐     │
│      │  │ Card 1   │ │ Card 2   │ │ Card 3   │     │
│      │  └──────────┘ └──────────┘ └──────────┘     │
│      │                                               │
└──────┴──────────────────────────────────────────────┘
```

---

## What Needs to Change (Desktop vs Current)

| Area | Current Issue | Fix |
|------|--------------|-----|
| Navigation | Bottom tabs (mobile pattern) | Left sidebar with collapse |
| Layout | Single column, lots of whitespace | Multi-column grid, data-dense |
| Tables | Card-based stacked layout | Proper data tables with sort/filter |
| Asset Detail | Full-page takeover | Split-pane (watchlist + detail) |
| Typography | Same sizes as mobile | Slightly smaller, more information density |
| Spacing | Generous mobile padding | Tighter, more efficient use of space |
| Interactions | Tap-only | Hover states, keyboard nav, tooltips |
| Charts | Basic widget | Full charting library with overlays |

---

## Responsive Breakpoints

| Breakpoint | Layout |
|------------|--------|
| < 768px | Mobile (current — bottom tabs, stacked cards) |
| 768–1024px | Tablet (hybrid — collapsible sidebar, 2-column) |
| > 1024px | Desktop (full sidebar, multi-column, data tables) |
| > 1440px | Wide desktop (3-column layouts, expanded panels) |

---

## Inspiration References

- Bloomberg Terminal (information density)
- Linear.app (clean dark UI, sidebar nav, keyboard-first)
- Figma (split-pane layouts, contextual panels)
- Arc Browser (minimal chrome, elegant dark mode)
- Apple Finance/Stocks (clean data presentation)
