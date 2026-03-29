"use client";

import { useState, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import {
  Target,
  PiggyBank,
  TrendingUp,
  Calculator,
  Calendar,
  Wallet,
  ArrowLeft,
  ArrowRight,
  Plus,
  Check,
  Sparkles,
  Save,
  Zap,
  Info,
} from "lucide-react";

// ─── Types ───────────────────────────────────────────────

interface WizardState {
  riskProfile: string | null;
  capitalRange: string | null;
  themes: string[];
  framework: string | null;
  portfolioSize: string | null;
  experience: string | null;
}

interface GeneratedPosition {
  symbol: string;
  name: string;
  allocation: number;
  type: "Core" | "Growth" | "Satellite" | "Index" | "Reserve";
  theme: string;
  entryZone: string;
  conviction: number;
}

// ─── Configuration ───────────────────────────────────────

const RISK_PROFILES = [
  { id: "conservative", label: "Conservative", desc: "Capital preservation, low volatility.", color: "#3b82f6" },
  { id: "moderate", label: "Moderate", desc: "Balanced growth and protection.", color: "#8b5cf6" },
  { id: "aggressive", label: "Aggressive", desc: "Max growth, higher drawdowns.", color: "#22c55e" },
  { id: "speculative", label: "Speculative", desc: "High-conviction concentrated bets.", color: "#f59e0b" },
];

const EXPERIENCE_LEVELS = [
  { id: "beginner", label: "New to investing", desc: "Learning the ropes." },
  { id: "intermediate", label: "1-3 years", desc: "Comfortable with basics." },
  { id: "advanced", label: "3-10 years", desc: "Active portfolio management." },
  { id: "expert", label: "10+ years", desc: "Professional-grade strategies." },
];

const THEMES = [
  "AI & Machine Learning",
  "Semiconductors",
  "Space Economy",
  "Cybersecurity",
  "Energy & Commodities",
  "Digital Assets",
  "Biotech & Healthcare",
  "Macro & Global",
  "Clean Energy",
  "Fintech",
];

const FRAMEWORKS = [
  { id: "druckenmiller", label: "Druckenmiller", desc: "Macro conviction, concentrated bets." },
  { id: "oneil", label: "O'Neil / CAN SLIM", desc: "Stage 2 leaders, breakouts." },
  { id: "burry", label: "Michael Burry", desc: "Deep value, contrarian." },
  { id: "dalio", label: "Ray Dalio", desc: "All-weather, balanced risk." },
  { id: "custom", label: "Custom Framework", desc: "Build your own." },
];

const PORTFOLIO_SIZES = [
  { id: "under25k", label: "Under $25K", desc: "Concentrated plays." },
  { id: "25k_100k", label: "$25K - $100K", desc: "Balanced diversification." },
  { id: "100k_500k", label: "$100K - $500K", desc: "Full institutional allocation." },
  { id: "500k_plus", label: "$500K+", desc: "Multi-strategy." },
];

// ─── Portfolio Generation Logic ──────────────────────────

function generatePortfolio(state: WizardState): GeneratedPosition[] {
  const positions: GeneratedPosition[] = [];
  const themes = state.themes;
  const isAggressive = state.riskProfile === "aggressive" || state.riskProfile === "speculative";
  const isConservative = state.riskProfile === "conservative";

  // Theme -> Position mapping
  const themePositions: Record<string, GeneratedPosition[]> = {
    "AI & Machine Learning": [
      { symbol: "NVDA", name: "Nvidia Corp.", allocation: 12, type: "Core", theme: "AI & Semis", entryZone: "$114-$118", conviction: 95 },
      { symbol: "PLTR", name: "Palantir Tech.", allocation: 8, type: "Core", theme: "AI Platform", entryZone: "$72-$80", conviction: 88 },
      { symbol: "MSFT", name: "Microsoft", allocation: 6, type: "Core", theme: "AI Platform", entryZone: "$380-$400", conviction: 86 },
    ],
    "Semiconductors": [
      { symbol: "AVGO", name: "Broadcom Inc.", allocation: 8, type: "Core", theme: "Semis Infra", entryZone: "$165-$180", conviction: 87 },
      { symbol: "AMD", name: "AMD Inc.", allocation: 6, type: "Growth", theme: "AI Compute", entryZone: "$145-$160", conviction: 82 },
      { symbol: "TSM", name: "TSMC", allocation: 5, type: "Core", theme: "Foundry", entryZone: "$160-$170", conviction: 90 },
    ],
    "Cybersecurity": [
      { symbol: "CRWD", name: "CrowdStrike", allocation: 7, type: "Core", theme: "Cybersecurity", entryZone: "$385-$410", conviction: 85 },
      { symbol: "PANW", name: "Palo Alto Networks", allocation: 5, type: "Growth", theme: "Cybersecurity", entryZone: "$175-$190", conviction: 80 },
    ],
    "Space Economy": [
      { symbol: "LMT", name: "Lockheed Martin", allocation: 5, type: "Core", theme: "Defense/Space", entryZone: "$440-$460", conviction: 78 },
      { symbol: "RKLB", name: "Rocket Lab", allocation: 4, type: "Satellite", theme: "Space Launch", entryZone: "$22-$26", conviction: 72 },
    ],
    "Energy & Commodities": [
      { symbol: "XOM", name: "ExxonMobil", allocation: 6, type: "Core", theme: "Energy", entryZone: "$105-$115", conviction: 79 },
      { symbol: "GLD", name: "SPDR Gold Trust", allocation: 5, type: "Core", theme: "Commodities", entryZone: "$215-$225", conviction: 82 },
    ],
    "Digital Assets": [
      { symbol: "BTCUSDT", name: "Bitcoin", allocation: 8, type: "Core", theme: "Digital Assets", entryZone: "$65K-$70K", conviction: 88 },
      { symbol: "ETHUSDT", name: "Ethereum", allocation: 5, type: "Growth", theme: "DeFi/L1", entryZone: "$2,000-$2,200", conviction: 80 },
      { symbol: "SOLUSDT", name: "Solana", allocation: 3, type: "Satellite", theme: "Alt L1", entryZone: "$85-$95", conviction: 74 },
    ],
    "Biotech & Healthcare": [
      { symbol: "LLY", name: "Eli Lilly", allocation: 7, type: "Core", theme: "GLP-1 / Pharma", entryZone: "$750-$800", conviction: 91 },
      { symbol: "ISRG", name: "Intuitive Surgical", allocation: 5, type: "Growth", theme: "MedTech", entryZone: "$520-$550", conviction: 83 },
    ],
    "Macro & Global": [
      { symbol: "TLT", name: "20+ Year Treasury", allocation: 6, type: "Core", theme: "Duration", entryZone: "$85-$92", conviction: 75 },
      { symbol: "EEM", name: "Emerging Markets", allocation: 4, type: "Satellite", theme: "EM Equity", entryZone: "$40-$43", conviction: 68 },
    ],
    "Clean Energy": [
      { symbol: "ENPH", name: "Enphase Energy", allocation: 5, type: "Growth", theme: "Solar", entryZone: "$68-$80", conviction: 76 },
      { symbol: "NEE", name: "NextEra Energy", allocation: 5, type: "Core", theme: "Renewables", entryZone: "$72-$78", conviction: 80 },
    ],
    "Fintech": [
      { symbol: "SQ", name: "Block Inc.", allocation: 5, type: "Growth", theme: "Payments", entryZone: "$68-$78", conviction: 77 },
      { symbol: "COIN", name: "Coinbase", allocation: 4, type: "Satellite", theme: "Crypto Infra", entryZone: "$195-$220", conviction: 73 },
    ],
  };

  // Always include broad market
  positions.push({
    symbol: "SPY",
    name: "S&P 500 ETF",
    allocation: isConservative ? 25 : isAggressive ? 10 : 15,
    type: "Index",
    theme: "Broad Market",
    entryZone: "$550-$570",
    conviction: 90,
  });

  // Add theme positions
  for (const theme of themes) {
    const tp = themePositions[theme];
    if (tp) {
      for (const pos of tp) {
        positions.push({ ...pos });
      }
    }
  }

  // Always add cash
  positions.push({
    symbol: "CASH",
    name: "Cash / T-Bills",
    allocation: 0, // Will be calculated
    type: "Reserve",
    theme: "Liquidity",
    entryZone: "-",
    conviction: 100,
  });

  // Normalize allocations to 100%
  const cashIdx = positions.findIndex((p) => p.symbol === "CASH");
  const totalNonCash = positions.filter((p) => p.symbol !== "CASH").reduce((s, p) => s + p.allocation, 0);

  if (totalNonCash >= 95) {
    // Scale down proportionally, keep min 5% cash
    const scale = 90 / totalNonCash;
    for (const pos of positions) {
      if (pos.symbol !== "CASH") {
        pos.allocation = Math.round(pos.allocation * scale);
      }
    }
    positions[cashIdx].allocation = 100 - positions.filter((p) => p.symbol !== "CASH").reduce((s, p) => s + p.allocation, 0);
  } else {
    positions[cashIdx].allocation = 100 - totalNonCash;
  }

  // Sort by allocation descending (cash last)
  return positions.sort((a, b) => {
    if (a.symbol === "CASH") return 1;
    if (b.symbol === "CASH") return -1;
    return b.allocation - a.allocation;
  });
}

// ─── Wizard Steps ────────────────────────────────────────

function StepExperience({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-text-secondary text-xs uppercase tracking-wider mb-1">Portfolio Builder</p>
        <h2 className="font-heading text-2xl font-bold">What's your experience level?</h2>
        <p className="text-text-secondary text-sm mt-1">This shapes position sizing and complexity.</p>
      </div>
      <div className="space-y-3">
        {EXPERIENCE_LEVELS.map((opt) => (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className={`w-full text-left p-4 rounded-card border transition-all ${
              value === opt.id
                ? "border-profit bg-profit/5"
                : "border-border hover:border-text-tertiary"
            }`}
          >
            <div className="flex items-center gap-3">
              <div
                className={`w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all ${
                  value === opt.id ? "border-profit" : "border-text-tertiary"
                }`}
              >
                {value === opt.id && <div className="w-2 h-2 rounded-full bg-profit" />}
              </div>
              <div>
                <p className="font-heading font-semibold text-sm">{opt.label}</p>
                <p className="text-text-secondary text-xs">{opt.desc}</p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepRisk({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-text-secondary text-xs uppercase tracking-wider mb-1">Portfolio Builder</p>
        <h2 className="font-heading text-2xl font-bold">What's your risk tolerance?</h2>
        <p className="text-text-secondary text-sm mt-1">Determines allocation balance and hedge sizing.</p>
      </div>
      <div className="space-y-3">
        {RISK_PROFILES.map((opt) => (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className={`w-full text-left p-4 rounded-card border transition-all ${
              value === opt.id
                ? "border-profit bg-profit/5"
                : "border-border hover:border-text-tertiary"
            }`}
          >
            <div className="flex items-center gap-3">
              <div
                className={`w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all ${
                  value === opt.id ? "border-profit" : "border-text-tertiary"
                }`}
              >
                {value === opt.id && <div className="w-2 h-2 rounded-full bg-profit" />}
              </div>
              <div>
                <p className="font-heading font-semibold text-sm">{opt.label}</p>
                <p className="text-text-secondary text-xs">{opt.desc}</p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepThemes({
  value,
  onChange,
}: {
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const toggle = (theme: string) => {
    if (value.includes(theme)) {
      onChange(value.filter((t) => t !== theme));
    } else {
      onChange([...value, theme]);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <p className="text-text-secondary text-xs uppercase tracking-wider mb-1">Portfolio Builder</p>
        <h2 className="font-heading text-2xl font-bold">Select your conviction themes</h2>
        <p className="text-text-secondary text-sm mt-1">Choose all that apply</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {THEMES.map((theme) => {
          const selected = value.includes(theme);
          return (
            <button
              key={theme}
              onClick={() => toggle(theme)}
              className={`text-left p-4 rounded-card border transition-all ${
                selected
                  ? "border-profit bg-profit/5"
                  : "border-border hover:border-text-tertiary"
              }`}
            >
              <div className="flex items-center gap-2">
                <div
                  className={`w-4 h-4 rounded flex items-center justify-center transition-all ${
                    selected ? "bg-profit" : "border border-text-tertiary"
                  }`}
                >
                  {selected && <Check size={10} className="text-black" />}
                </div>
                <span className="font-heading text-sm font-medium">{theme}</span>
              </div>
            </button>
          );
        })}
      </div>
      <p className="text-text-tertiary text-xs text-center">{value.length} themes selected</p>
    </div>
  );
}

function StepFramework({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-text-secondary text-xs uppercase tracking-wider mb-1">Portfolio Builder</p>
        <h2 className="font-heading text-2xl font-bold">Whose playbook inspires you?</h2>
        <p className="text-text-secondary text-sm mt-1">We blend their strategic DNA into your portfolio</p>
      </div>
      <div className="space-y-3">
        {FRAMEWORKS.map((opt) => (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className={`w-full text-left p-4 rounded-card border transition-all ${
              value === opt.id
                ? "border-profit bg-profit/5"
                : "border-border hover:border-text-tertiary"
            }`}
          >
            <div className="flex items-center gap-3">
              <div
                className={`w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all ${
                  value === opt.id ? "border-profit" : "border-text-tertiary"
                }`}
              >
                {value === opt.id && <div className="w-2 h-2 rounded-full bg-profit" />}
              </div>
              <div>
                <p className="font-heading font-semibold text-sm">{opt.label}</p>
                <p className="text-text-secondary text-xs">{opt.desc}</p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepSize({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-text-secondary text-xs uppercase tracking-wider mb-1">Portfolio Builder</p>
        <h2 className="font-heading text-2xl font-bold">Portfolio size?</h2>
        <p className="text-text-secondary text-sm mt-1">Determines min position sizes</p>
      </div>
      <div className="space-y-3">
        {PORTFOLIO_SIZES.map((opt) => (
          <button
            key={opt.id}
            onClick={() => onChange(opt.id)}
            className={`w-full text-left p-4 rounded-card border transition-all ${
              value === opt.id
                ? "border-profit bg-profit/5"
                : "border-border hover:border-text-tertiary"
            }`}
          >
            <div className="flex items-center gap-3">
              <div
                className={`w-4 h-4 rounded-full border-2 flex items-center justify-center transition-all ${
                  value === opt.id ? "border-profit" : "border-text-tertiary"
                }`}
              >
                {value === opt.id && <div className="w-2 h-2 rounded-full bg-profit" />}
              </div>
              <div>
                <p className="font-heading font-semibold text-sm">{opt.label}</p>
                <p className="text-text-secondary text-xs">{opt.desc}</p>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Generated Portfolio View ────────────────────────────

function PortfolioResult({
  state,
  positions,
  onBack,
}: {
  state: WizardState;
  positions: GeneratedPosition[];
  onBack: () => void;
}) {
  const riskLabel = RISK_PROFILES.find((r) => r.id === state.riskProfile)?.label ?? "";
  const frameworkLabel = FRAMEWORKS.find((f) => f.id === state.framework)?.label ?? "";
  const totalPositions = positions.filter((p) => p.symbol !== "CASH").length;
  const avgConviction = Math.round(
    positions.filter((p) => p.symbol !== "CASH").reduce((s, p) => s + p.conviction, 0) / totalPositions
  );
  const cashAlloc = positions.find((p) => p.symbol === "CASH")?.allocation ?? 0;
  const themes = [...new Set(positions.map((p) => p.theme))].length;

  // Allocation strip colors
  const stripColors = [
    "#22c55e", "#3b82f6", "#8b5cf6", "#f59e0b", "#ef4444",
    "#06b6d4", "#f97316", "#10b981", "#ec4899", "#6366f1",
    "#14b8a6", "#a855f7", "#eab308",
  ];

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-3 h-3 rounded-full bg-profit animate-pulse" />
        <span className="text-text-secondary text-xs uppercase tracking-wider">Portfolio Generated</span>
      </div>

      <div>
        <h2 className="font-heading text-2xl font-bold">Your Lumare Portfolio</h2>
        <p className="text-text-secondary text-sm mt-1">
          {totalPositions} positions &middot; {riskLabel.toLowerCase()} risk &middot; {frameworkLabel.toLowerCase()} framework
        </p>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-3">
        <Card padding="sm">
          <p className="font-heading text-xl font-bold text-center">{totalPositions}</p>
          <p className="text-text-secondary text-[10px] text-center uppercase">Positions</p>
        </Card>
        <Card padding="sm">
          <p className="font-heading text-xl font-bold text-center">{themes}</p>
          <p className="text-text-secondary text-[10px] text-center uppercase">Themes</p>
        </Card>
        <Card padding="sm">
          <p className="font-heading text-xl font-bold text-center text-profit">{avgConviction}%</p>
          <p className="text-text-secondary text-[10px] text-center uppercase">Avg Conv.</p>
        </Card>
        <Card padding="sm">
          <p className="font-heading text-xl font-bold text-center">{cashAlloc}%</p>
          <p className="text-text-secondary text-[10px] text-center uppercase">Cash</p>
        </Card>
      </div>

      {/* Allocation Strip */}
      <div>
        <p className="text-text-secondary text-[10px] uppercase tracking-widest mb-2">Allocation Strip</p>
        <div className="flex h-4 rounded-full overflow-hidden gap-px">
          {positions.map((p, i) => (
            <div
              key={p.symbol}
              style={{
                width: `${p.allocation}%`,
                backgroundColor: p.symbol === "CASH" ? "#333" : stripColors[i % stripColors.length],
              }}
              title={`${p.symbol} ${p.allocation}%`}
              className="transition-all hover:opacity-80"
            />
          ))}
        </div>
      </div>

      {/* Positions */}
      <div>
        <p className="text-text-secondary text-[10px] uppercase tracking-widest mb-3">Positions & Entry Zones</p>
        <div className="space-y-3">
          {positions.map((pos) => (
            <Card key={pos.symbol} padding="md">
              <div className="flex items-start gap-4">
                {/* Symbol badge */}
                <div className="w-12 h-12 rounded-lg bg-bg-elevated border border-border flex items-center justify-center shrink-0">
                  <span className="font-mono text-xs font-bold">{pos.symbol.length > 5 ? pos.symbol.slice(0, 4) : pos.symbol}</span>
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-heading font-bold text-sm">{pos.symbol}</p>
                      <p className="text-text-secondary text-xs">{pos.name}</p>
                    </div>
                    <div className="text-right">
                      <p className="font-heading font-bold text-sm">{pos.allocation}%</p>
                      <p className="text-text-secondary text-xs">{pos.type}</p>
                    </div>
                  </div>

                  {/* Tags */}
                  <div className="flex gap-2 mt-3">
                    <div className="bg-bg-elevated rounded-chip px-3 py-1.5">
                      <p className="text-text-tertiary text-[10px] uppercase">Theme</p>
                      <p className="font-mono text-xs font-medium">{pos.theme}</p>
                    </div>
                    <div className="bg-bg-elevated rounded-chip px-3 py-1.5">
                      <p className="text-text-tertiary text-[10px] uppercase">Entry Zone</p>
                      <p className="font-mono text-xs font-medium">{pos.entryZone}</p>
                    </div>
                    <div className="bg-bg-elevated rounded-chip px-3 py-1.5">
                      <p className="text-text-tertiary text-[10px] uppercase">Conviction</p>
                      <p className={`font-mono text-xs font-medium ${pos.conviction >= 85 ? "text-profit" : pos.conviction >= 70 ? "text-text-primary" : "text-text-secondary"}`}>
                        {pos.conviction}%
                      </p>
                    </div>
                  </div>

                  {/* Conviction bar */}
                  <div className="mt-2 h-1 bg-bg-elevated rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${pos.conviction}%`,
                        backgroundColor: pos.conviction >= 85 ? "#22c55e" : pos.conviction >= 70 ? "#3b82f6" : "#555",
                      }}
                    />
                  </div>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 sticky bottom-4">
        <button
          onClick={onBack}
          className="flex-1 flex items-center justify-center gap-2 py-3 rounded-card border border-border text-text-secondary hover:border-text-tertiary transition-colors"
        >
          <Save size={16} />
          Save & Exit
        </button>
        <button className="flex-1 flex items-center justify-center gap-2 py-3 rounded-card bg-white text-black font-heading font-semibold hover:bg-gray-200 transition-colors">
          <Zap size={16} />
          Activate Portfolio
        </button>
      </div>
    </div>
  );
}

// ─── Wizard Container ────────────────────────────────────

function PortfolioBuilderWizard({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const [state, setState] = useState<WizardState>({
    riskProfile: null,
    capitalRange: null,
    themes: [],
    framework: null,
    portfolioSize: null,
    experience: null,
  });
  const [generated, setGenerated] = useState<GeneratedPosition[] | null>(null);

  const TOTAL_STEPS = 6; // 5 wizard steps + 1 result

  const canNext = (() => {
    switch (step) {
      case 0: return !!state.experience;
      case 1: return !!state.riskProfile;
      case 2: return state.themes.length > 0;
      case 3: return !!state.framework;
      case 4: return !!state.portfolioSize;
      default: return false;
    }
  })();

  const handleNext = () => {
    if (step === 4) {
      // Generate portfolio
      const positions = generatePortfolio(state);
      setGenerated(positions);
      setStep(5);
    } else {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    if (step === 5) {
      setGenerated(null);
      setStep(4);
    } else if (step > 0) {
      setStep(step - 1);
    }
  };

  // Result view
  if (step === 5 && generated) {
    return (
      <div className="max-w-2xl mx-auto">
        <PortfolioResult state={state} positions={generated} onBack={onClose} />
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto">
      {/* Progress bar */}
      <div className="h-1 bg-bg-elevated rounded-full mb-6 overflow-hidden">
        <div
          className="h-full bg-white rounded-full transition-all duration-300"
          style={{ width: `${((step + 1) / (TOTAL_STEPS - 1)) * 100}%` }}
        />
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between mb-6">
        <button
          onClick={step === 0 ? onClose : handleBack}
          className="flex items-center gap-1 text-text-secondary text-sm hover:text-text-primary transition-colors"
        >
          <ArrowLeft size={14} />
          Back
        </button>
        <span className="text-text-tertiary text-sm font-mono">{step + 1} / {TOTAL_STEPS - 1}</span>
      </div>

      {/* Step Content */}
      <div className="mb-8">
        {step === 0 && (
          <StepExperience
            value={state.experience}
            onChange={(v) => setState((s) => ({ ...s, experience: v }))}
          />
        )}
        {step === 1 && (
          <StepRisk
            value={state.riskProfile}
            onChange={(v) => setState((s) => ({ ...s, riskProfile: v }))}
          />
        )}
        {step === 2 && (
          <StepThemes
            value={state.themes}
            onChange={(v) => setState((s) => ({ ...s, themes: v }))}
          />
        )}
        {step === 3 && (
          <StepFramework
            value={state.framework}
            onChange={(v) => setState((s) => ({ ...s, framework: v }))}
          />
        )}
        {step === 4 && (
          <StepSize
            value={state.portfolioSize}
            onChange={(v) => setState((s) => ({ ...s, portfolioSize: v }))}
          />
        )}
      </div>

      {/* Continue Button */}
      <button
        onClick={handleNext}
        disabled={!canNext}
        className={`w-full py-3.5 rounded-card font-heading font-semibold text-sm flex items-center justify-center gap-2 transition-all ${
          canNext
            ? "bg-white text-black hover:bg-gray-200"
            : "bg-bg-elevated text-text-tertiary cursor-not-allowed"
        }`}
      >
        {step === 4 ? (
          <>
            <Sparkles size={16} />
            Generate Portfolio
          </>
        ) : (
          <>
            Continue
            <ArrowRight size={14} />
          </>
        )}
      </button>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────

export default function PlanPage() {
  const [showBuilder, setShowBuilder] = useState(false);

  if (showBuilder) {
    return (
      <div className="p-4 lg:p-8 max-w-7xl mx-auto animate-fade-in">
        <PortfolioBuilderWizard onClose={() => setShowBuilder(false)} />
      </div>
    );
  }

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-7xl mx-auto animate-fade-in">
      <header>
        <div className="flex items-center gap-3 mb-1">
          <Target size={20} className="text-emerald-500" />
          <h1 className="font-heading text-2xl font-bold">Plan</h1>
        </div>
        <p className="text-text-secondary text-sm">
          Portfolio builder, goal tracking, and projection modeling
        </p>
      </header>

      {/* Portfolio Builder CTA */}
      <Card
        className="border-profit/30 hover:border-profit/60 transition-colors cursor-pointer group"
        onClick={() => setShowBuilder(true)}
      >
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-xl bg-profit/10 flex items-center justify-center group-hover:bg-profit/20 transition-colors">
            <Sparkles size={24} className="text-profit" />
          </div>
          <div className="flex-1">
            <h2 className="font-heading text-lg font-bold">Portfolio Builder</h2>
            <p className="text-text-secondary text-sm">
              Create a personalized portfolio based on your risk profile, conviction themes, and favorite investor frameworks
            </p>
          </div>
          <ArrowRight size={20} className="text-text-tertiary group-hover:text-profit transition-colors" />
        </div>
      </Card>

      {/* Quick Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <Wallet size={14} className="text-emerald-500" />
            <p className="text-text-secondary text-xs uppercase">Net Worth</p>
          </div>
          <p className="font-heading text-2xl font-bold font-mono">--</p>
        </Card>
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <PiggyBank size={14} className="text-blue-500" />
            <p className="text-text-secondary text-xs uppercase">Savings Rate</p>
          </div>
          <p className="font-heading text-2xl font-bold font-mono">--</p>
        </Card>
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp size={14} className="text-profit" />
            <p className="text-text-secondary text-xs uppercase">Projected CAGR</p>
          </div>
          <p className="font-heading text-2xl font-bold font-mono">--</p>
        </Card>
        <Card>
          <div className="flex items-center gap-2 mb-2">
            <Calendar size={14} className="text-purple-500" />
            <p className="text-text-secondary text-xs uppercase">FI Target Date</p>
          </div>
          <p className="font-heading text-2xl font-bold font-mono">--</p>
        </Card>
      </div>

      {/* Goal Planning */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">Financial Goals</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            { title: "Emergency Fund", target: "$30,000", current: "$0", pct: 0, icon: PiggyBank, color: "text-blue-500" },
            { title: "Retirement (FIRE)", target: "$2,500,000", current: "$0", pct: 0, icon: Target, color: "text-emerald-500" },
            { title: "Real Estate Down Payment", target: "$100,000", current: "$0", pct: 0, icon: Wallet, color: "text-purple-500" },
            { title: "Investment Portfolio", target: "$500,000", current: "$0", pct: 0, icon: TrendingUp, color: "text-profit" },
          ].map((goal) => {
            const Icon = goal.icon;
            return (
              <Card key={goal.title}>
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Icon size={16} className={goal.color} />
                    <h3 className="font-heading font-semibold text-sm">{goal.title}</h3>
                  </div>
                  <div className="flex items-baseline justify-between">
                    <span className="font-mono text-xs text-text-secondary">{goal.current}</span>
                    <span className="font-mono text-xs text-text-tertiary">{goal.target}</span>
                  </div>
                  <div className="h-2 bg-bg-elevated rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{
                        width: `${goal.pct}%`,
                        backgroundColor: goal.pct > 50 ? "#22c55e" : "#3b82f6",
                      }}
                    />
                  </div>
                  <p className="text-text-tertiary text-[10px]">{goal.pct}% complete</p>
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Tools */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">Planning Tools</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { name: "Compound Calculator", desc: "Project growth with varying contribution and return rates", icon: Calculator },
            { name: "Tax Optimizer", desc: "Minimize tax drag with harvest strategies and account placement", icon: Target },
            { name: "Monte Carlo Sim", desc: "1000-run simulation of portfolio outcomes with confidence intervals", icon: TrendingUp },
          ].map((tool) => {
            const Icon = tool.icon;
            return (
              <Card key={tool.name} className="hover:border-accent-hover transition-colors cursor-pointer">
                <div className="space-y-2">
                  <Icon size={20} className="text-emerald-500" />
                  <h3 className="font-heading font-semibold text-sm">{tool.name}</h3>
                  <p className="text-text-secondary text-xs">{tool.desc}</p>
                </div>
              </Card>
            );
          })}
        </div>
      </section>
    </div>
  );
}
