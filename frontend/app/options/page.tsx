"use client";

import { useEffect, useState, useMemo } from "react";
import { Card } from "@/components/ui/Card";
import { PriceDisplay } from "@/components/ui/PriceDisplay";
import {
  Activity,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Layers,
  Target,
  ArrowUpRight,
  ArrowDownRight,
  ChevronDown,
  Filter,
  Zap,
  Shield,
  DollarSign,
  Clock,
  Star,
  Sparkles,
  Award,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Recommender types                                                  */
/* ------------------------------------------------------------------ */

interface RecPick {
  underlying: string;
  contract_id: string;
  occ_symbol: string;
  option_type: "CALL" | "PUT";
  strike: number;
  expiry: string;
  dte: number;
  last: number;
  bid: number;
  ask: number;
  mid: number;
  spread_pct: number;
  volume: number;
  open_interest: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  spot: number;
  is_itm: boolean;
  composite_score: number;
  components: {
    probability_of_profit: number;
    liquidity: number;
    spread: number;
    greek_fit: number;
    iv_value: number;
  };
  extras: {
    breakeven: number;
    max_loss_per_contract: number;
    premium: number;
    realised_vol: number;
    is_itm: boolean;
  };
}

interface RecExpiryBlock {
  expiry: string;
  dte: number;
  top_itm_calls: RecPick[];
  top_otm_calls: RecPick[];
  top_itm_puts: RecPick[];
  top_otm_puts: RecPick[];
}

interface RecSymbolBlock {
  underlying: string;
  spot: number;
  realised_vol_annualised: number;
  as_of: string;
  by_expiry: RecExpiryBlock[];
  overall_best: RecPick | null;
}

interface RecommendationResponse {
  generated_at: string;
  by_symbol: RecSymbolBlock[];
  overall_best_trade: RecPick | null;
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface OptionLeg {
  strike: number;
  last: number;
  change: number;
  bid: number;
  ask: number;
  volume: number;
  oi: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
}

interface FlowEntry {
  time: string;
  symbol: string;
  strike: number;
  exp: string;
  type: "Call" | "Put";
  side: "Buy" | "Sell";
  size: number;
  premium: number;
  spot: number;
  sentiment: "bullish" | "bearish";
}

interface Strategy {
  name: string;
  maxProfit: string;
  maxLoss: string;
  breakeven: string;
  pop: number; // probability of profit %
  description: string;
}

/* ------------------------------------------------------------------ */
/*  Config                                                             */
/* ------------------------------------------------------------------ */

const SYMBOLS: { value: string; label: string; spotPrice: number; strikeStep: number }[] = [
  { value: "SPY", label: "SPY", spotPrice: 568.42, strikeStep: 5 },
  { value: "AAPL", label: "AAPL", spotPrice: 214.85, strikeStep: 2.5 },
  { value: "TSLA", label: "TSLA", spotPrice: 178.30, strikeStep: 2.5 },
  { value: "NVDA", label: "NVDA", spotPrice: 924.60, strikeStep: 5 },
  { value: "QQQ", label: "QQQ", spotPrice: 489.15, strikeStep: 5 },
  { value: "AMZN", label: "AMZN", spotPrice: 186.42, strikeStep: 2.5 },
  { value: "META", label: "META", spotPrice: 512.80, strikeStep: 5 },
  { value: "MSFT", label: "MSFT", spotPrice: 428.65, strikeStep: 5 },
];

const EXPIRATIONS = [
  { value: "2026-03-27", label: "Mar 27 (2d)" },
  { value: "2026-04-03", label: "Apr 3 (9d)" },
  { value: "2026-04-11", label: "Apr 11 (17d)" },
  { value: "2026-04-17", label: "Apr 17 (23d)" },
  { value: "2026-05-16", label: "May 16 (52d)" },
  { value: "2026-06-19", label: "Jun 19 (86d)" },
];

/* ------------------------------------------------------------------ */
/*  Mock data generators                                               */
/* ------------------------------------------------------------------ */

function normalCdf(x: number): number {
  const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741, a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x) / Math.SQRT2;
  const t = 1.0 / (1.0 + p * ax);
  const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax);
  return 0.5 * (1.0 + sign * y);
}

function bsDelta(spot: number, strike: number, dte: number, iv: number, isCall: boolean): number {
  const t = dte / 365;
  if (t <= 0) return isCall ? (spot > strike ? 1 : 0) : (spot < strike ? -1 : 0);
  const d1 = (Math.log(spot / strike) + (0.05 + (iv * iv) / 2) * t) / (iv * Math.sqrt(t));
  return isCall ? normalCdf(d1) : normalCdf(d1) - 1;
}

function bsGamma(spot: number, strike: number, dte: number, iv: number): number {
  const t = dte / 365;
  if (t <= 0) return 0;
  const d1 = (Math.log(spot / strike) + (0.05 + (iv * iv) / 2) * t) / (iv * Math.sqrt(t));
  return Math.exp(-d1 * d1 / 2) / (Math.sqrt(2 * Math.PI) * spot * iv * Math.sqrt(t));
}

function generateChain(spot: number, strikeStep: number, dte: number): { calls: OptionLeg[]; puts: OptionLeg[]; strikes: number[] } {
  const atmStrike = Math.round(spot / strikeStep) * strikeStep;
  const strikes: number[] = [];
  for (let i = -10; i <= 10; i++) {
    strikes.push(atmStrike + i * strikeStep);
  }

  const t = dte / 365;
  const calls: OptionLeg[] = [];
  const puts: OptionLeg[] = [];

  strikes.forEach((k) => {
    const moneyness = Math.abs(k - spot) / spot;
    // IV smile: higher IV for OTM options
    const baseIV = 0.28 + moneyness * 0.4 + (k < spot ? 0.05 : 0); // put skew
    const iv = parseFloat((baseIV + (Math.random() - 0.5) * 0.02).toFixed(4));

    const callDelta = bsDelta(spot, k, dte, iv, true);
    const putDelta = bsDelta(spot, k, dte, iv, false);
    const gamma = bsGamma(spot, k, dte, iv);
    const theta = -(spot * iv * Math.exp(-((Math.log(spot / k)) ** 2) / (2 * iv * iv * t)) / (2 * Math.sqrt(2 * Math.PI * t))) / 365;
    const vega = spot * Math.sqrt(t) * Math.exp(-((Math.log(spot / k)) ** 2) / (2 * iv * iv * Math.max(t, 0.001))) / (Math.sqrt(2 * Math.PI)) / 100;

    // Rough price from intrinsic + time value
    const callIntrinsic = Math.max(spot - k, 0);
    const putIntrinsic = Math.max(k - spot, 0);
    const timeValue = spot * iv * Math.sqrt(t) * 0.4 * Math.exp(-moneyness * 3);

    const callLast = parseFloat(Math.max(callIntrinsic + timeValue, 0.01).toFixed(2));
    const putLast = parseFloat(Math.max(putIntrinsic + timeValue, 0.01).toFixed(2));

    const callChange = parseFloat(((Math.random() - 0.45) * callLast * 0.08).toFixed(2));
    const putChange = parseFloat(((Math.random() - 0.55) * putLast * 0.08).toFixed(2));

    const spreadPct = 0.02 + moneyness * 0.05;
    const callBid = parseFloat(Math.max(callLast - callLast * spreadPct / 2, 0.01).toFixed(2));
    const callAsk = parseFloat((callLast + callLast * spreadPct / 2).toFixed(2));
    const putBid = parseFloat(Math.max(putLast - putLast * spreadPct / 2, 0.01).toFixed(2));
    const putAsk = parseFloat((putLast + putLast * spreadPct / 2).toFixed(2));

    const baseVol = Math.floor(500 + Math.random() * 8000 * Math.exp(-moneyness * 5));
    const baseOI = Math.floor(2000 + Math.random() * 40000 * Math.exp(-moneyness * 4));

    calls.push({
      strike: k,
      last: callLast,
      change: callChange,
      bid: callBid,
      ask: callAsk,
      volume: baseVol + Math.floor(Math.random() * 500),
      oi: baseOI + Math.floor(Math.random() * 1000),
      iv: parseFloat((iv * 100).toFixed(1)),
      delta: parseFloat(callDelta.toFixed(4)),
      gamma: parseFloat(gamma.toFixed(5)),
      theta: parseFloat(theta.toFixed(3)),
      vega: parseFloat(Math.abs(vega).toFixed(3)),
    });

    puts.push({
      strike: k,
      last: putLast,
      change: putChange,
      bid: putBid,
      ask: putAsk,
      volume: baseVol + Math.floor(Math.random() * 500),
      oi: baseOI + Math.floor(Math.random() * 1000),
      iv: parseFloat((iv * 100).toFixed(1)),
      delta: parseFloat(putDelta.toFixed(4)),
      gamma: parseFloat(gamma.toFixed(5)),
      theta: parseFloat(theta.toFixed(3)),
      vega: parseFloat(Math.abs(vega).toFixed(3)),
    });
  });

  return { calls, puts, strikes };
}

function generateFlow(symbol: string, spot: number, strikeStep: number): FlowEntry[] {
  const entries: FlowEntry[] = [];
  const now = new Date();
  for (let i = 0; i < 15; i++) {
    const isCall = Math.random() > 0.45;
    const isBuy = Math.random() > 0.5;
    const otm = Math.floor(Math.random() * 8) * strikeStep;
    const strike = isCall ? Math.round(spot / strikeStep) * strikeStep + otm : Math.round(spot / strikeStep) * strikeStep - otm;
    const size = Math.floor(100 + Math.random() * 2000);
    const premium = parseFloat((size * (2 + Math.random() * 15) * 100).toFixed(0));
    const time = new Date(now.getTime() - i * 180_000);
    const sentiment: "bullish" | "bearish" = (isCall && isBuy) || (!isCall && !isBuy) ? "bullish" : "bearish";

    entries.push({
      time: time.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }),
      symbol,
      strike,
      exp: EXPIRATIONS[Math.floor(Math.random() * 3)].label.split(" (")[0],
      type: isCall ? "Call" : "Put",
      side: isBuy ? "Buy" : "Sell",
      size,
      premium,
      spot: parseFloat((spot + (Math.random() - 0.5) * 2).toFixed(2)),
      sentiment,
    });
  }
  return entries;
}

/* ------------------------------------------------------------------ */
/*  Strategies                                                         */
/* ------------------------------------------------------------------ */

function getStrategies(spot: number, step: number): Strategy[] {
  const atm = Math.round(spot / step) * step;
  const u1 = atm + step;
  const u2 = atm + 2 * step;
  const d1 = atm - step;
  const d2 = atm - 2 * step;
  return [
    {
      name: "Bull Call Spread",
      maxProfit: `$${(step * 100 - 280).toFixed(0)}`,
      maxLoss: "$280",
      breakeven: `$${(atm + 2.80).toFixed(2)}`,
      pop: 48,
      description: `Buy ${atm}C / Sell ${u1}C`,
    },
    {
      name: "Bear Put Spread",
      maxProfit: `$${(step * 100 - 310).toFixed(0)}`,
      maxLoss: "$310",
      breakeven: `$${(atm - 3.10).toFixed(2)}`,
      pop: 46,
      description: `Buy ${atm}P / Sell ${d1}P`,
    },
    {
      name: "Iron Condor",
      maxProfit: "$185",
      maxLoss: `$${(step * 100 - 185).toFixed(0)}`,
      breakeven: `$${(d1 + 1.85).toFixed(2)} / $${(u1 - 1.85).toFixed(2)}`,
      pop: 62,
      description: `Sell ${d1}P/${u1}C, Buy ${d2}P/${u2}C`,
    },
    {
      name: "Straddle",
      maxProfit: "Unlimited",
      maxLoss: `$${(spot * 0.035 * 200).toFixed(0)}`,
      breakeven: `$${(atm - spot * 0.035).toFixed(2)} / $${(atm + spot * 0.035).toFixed(2)}`,
      pop: 38,
      description: `Buy ${atm}C + Buy ${atm}P`,
    },
    {
      name: "Strangle",
      maxProfit: "Unlimited",
      maxLoss: `$${(spot * 0.022 * 200).toFixed(0)}`,
      breakeven: `$${(d1 - spot * 0.022).toFixed(2)} / $${(u1 + spot * 0.022).toFixed(2)}`,
      pop: 34,
      description: `Buy ${u1}C + Buy ${d1}P`,
    },
    {
      name: "Butterfly",
      maxProfit: `$${(step * 100 - 120).toFixed(0)}`,
      maxLoss: "$120",
      breakeven: `$${(atm - step + 1.20).toFixed(2)} / $${(atm + step - 1.20).toFixed(2)}`,
      pop: 28,
      description: `Buy ${d1}C / Sell 2x ${atm}C / Buy ${u1}C`,
    },
  ];
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function fmtK(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toLocaleString();
}

function fmtDollar(n: number): string {
  return "$" + n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function OptionsPage() {
  const [selectedSymbol, setSelectedSymbol] = useState("SPY");
  const [selectedExp, setSelectedExp] = useState(EXPIRATIONS[2].value);
  const [tick, setTick] = useState(0);
  const [showGreeks, setShowGreeks] = useState(true);
  const [symbolDropdownOpen, setSymbolDropdownOpen] = useState(false);
  const [expDropdownOpen, setExpDropdownOpen] = useState(false);

  // Recommendations from the backend
  const [recs, setRecs] = useState<RecommendationResponse | null>(null);
  const [recsLoading, setRecsLoading] = useState(false);
  const [recsError, setRecsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchRecs = async () => {
      setRecsLoading(true);
      setRecsError(null);
      try {
        const resp = await fetch(
          "/api/options/recommendations?symbols=SPY,QQQ,AAPL,NVDA,TSLA,MSFT,META&weeks=3"
        );
        const data = await resp.json();
        if (!cancelled) setRecs(data);
      } catch (e) {
        if (!cancelled) setRecsError(String(e));
      } finally {
        if (!cancelled) setRecsLoading(false);
      }
    };
    fetchRecs();
    const id = setInterval(fetchRecs, 60_000); // refresh every minute
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const recsForSelected = useMemo(
    () => recs?.by_symbol.find((s) => s.underlying === selectedSymbol),
    [recs, selectedSymbol]
  );

  const symbolConfig = SYMBOLS.find((s) => s.value === selectedSymbol) ?? SYMBOLS[0];
  const expConfig = EXPIRATIONS.find((e) => e.value === selectedExp) ?? EXPIRATIONS[2];

  // DTE calc
  const dte = useMemo(() => {
    const exp = new Date(selectedExp + "T16:00:00");
    const now = new Date();
    return Math.max(Math.ceil((exp.getTime() - now.getTime()) / 86_400_000), 1);
  }, [selectedExp]);

  // Drift spot
  const spot = useMemo(() => {
    const d = symbolConfig.spotPrice * 0.0002 * Math.sin(Date.now() * 0.0005 + symbolConfig.spotPrice);
    return parseFloat((symbolConfig.spotPrice + d).toFixed(2));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, selectedSymbol]);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 2_000);
    return () => clearInterval(id);
  }, []);

  const chain = useMemo(() => generateChain(spot, symbolConfig.strikeStep, dte), [spot, symbolConfig.strikeStep, dte]);
  const flow = useMemo(() => generateFlow(selectedSymbol, spot, symbolConfig.strikeStep), [selectedSymbol, spot, symbolConfig.strikeStep]);
  const strategies = useMemo(() => getStrategies(spot, symbolConfig.strikeStep), [spot, symbolConfig.strikeStep]);

  const atmStrike = Math.round(spot / symbolConfig.strikeStep) * symbolConfig.strikeStep;

  // Aggregated flow
  const totalCallPremium = flow.filter((f) => f.type === "Call").reduce((s, f) => s + f.premium, 0);
  const totalPutPremium = flow.filter((f) => f.type === "Put").reduce((s, f) => s + f.premium, 0);
  const pcRatio = totalCallPremium > 0 ? (totalPutPremium / totalCallPremium).toFixed(2) : "N/A";

  // Hypothetical portfolio Greeks
  const portfolioGreeks = useMemo(() => {
    // Simulate a small portfolio: long 5 ATM calls, short 3 OTM puts
    const atmIdx = chain.strikes.indexOf(atmStrike);
    const otmPutIdx = Math.max(atmIdx - 3, 0);
    const longCall = chain.calls[atmIdx >= 0 ? atmIdx : 10];
    const shortPut = chain.puts[otmPutIdx];
    if (!longCall || !shortPut) return { delta: 0, gamma: 0, theta: 0, vega: 0 };
    return {
      delta: parseFloat((5 * longCall.delta * 100 + 3 * shortPut.delta * 100).toFixed(1)),
      gamma: parseFloat((5 * longCall.gamma * 100 + 3 * shortPut.gamma * 100).toFixed(2)),
      theta: parseFloat((5 * longCall.theta * 100 + 3 * shortPut.theta * 100).toFixed(1)),
      vega: parseFloat((5 * longCall.vega * 100 + 3 * shortPut.vega * 100).toFixed(1)),
    };
  }, [chain, atmStrike]);

  // IV term structure
  const termStructure = useMemo(() => {
    return EXPIRATIONS.map((exp) => {
      const d = Math.max(Math.ceil((new Date(exp.value + "T16:00:00").getTime() - Date.now()) / 86_400_000), 1);
      const iv = 25 + 8 * Math.exp(-d / 60) + (Math.random() - 0.5) * 2;
      return { label: exp.label.split(" (")[0], dte: d, iv: parseFloat(iv.toFixed(1)) };
    });
  }, [tick]);

  return (
    <div className="min-h-screen bg-bg-primary">
      {/* ---- Header / Selectors ---- */}
      <div className="border-b border-border bg-bg-card">
        <div className="max-w-[1800px] mx-auto px-4 py-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-heading text-text-primary">Options</h1>
              <p className="text-sm text-text-secondary mt-1">Chain analysis, flow, Greeks &amp; strategy builder</p>
            </div>

            <div className="flex items-center gap-3">
              {/* Symbol Selector */}
              <div className="relative">
                <button
                  onClick={() => { setSymbolDropdownOpen(!symbolDropdownOpen); setExpDropdownOpen(false); }}
                  className="flex items-center gap-2 px-4 py-2 rounded-button bg-bg-elevated border border-border text-sm text-text-primary hover:border-text-tertiary transition-colors"
                >
                  <span className="font-heading">{selectedSymbol}</span>
                  <span className="text-text-tertiary font-mono">${spot.toFixed(2)}</span>
                  <ChevronDown className="w-3.5 h-3.5 text-text-tertiary" />
                </button>
                {symbolDropdownOpen && (
                  <div className="absolute top-full mt-1 right-0 bg-bg-elevated border border-border rounded-card shadow-xl z-50 min-w-[180px]">
                    {SYMBOLS.map((s) => (
                      <button
                        key={s.value}
                        onClick={() => { setSelectedSymbol(s.value); setSymbolDropdownOpen(false); }}
                        className={`w-full text-left px-4 py-2 text-sm hover:bg-bg-card transition-colors flex justify-between ${s.value === selectedSymbol ? "text-text-primary" : "text-text-secondary"}`}
                      >
                        <span className="font-heading">{s.label}</span>
                        <span className="font-mono text-text-tertiary">${s.spotPrice.toFixed(2)}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Expiration Selector */}
              <div className="relative">
                <button
                  onClick={() => { setExpDropdownOpen(!expDropdownOpen); setSymbolDropdownOpen(false); }}
                  className="flex items-center gap-2 px-4 py-2 rounded-button bg-bg-elevated border border-border text-sm text-text-primary hover:border-text-tertiary transition-colors"
                >
                  <Clock className="w-3.5 h-3.5 text-text-tertiary" />
                  <span>{expConfig.label}</span>
                  <ChevronDown className="w-3.5 h-3.5 text-text-tertiary" />
                </button>
                {expDropdownOpen && (
                  <div className="absolute top-full mt-1 right-0 bg-bg-elevated border border-border rounded-card shadow-xl z-50 min-w-[180px]">
                    {EXPIRATIONS.map((e) => (
                      <button
                        key={e.value}
                        onClick={() => { setSelectedExp(e.value); setExpDropdownOpen(false); }}
                        className={`w-full text-left px-4 py-2 text-sm hover:bg-bg-card transition-colors ${e.value === selectedExp ? "text-text-primary" : "text-text-secondary"}`}
                      >
                        {e.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Greeks toggle */}
              <button
                onClick={() => setShowGreeks(!showGreeks)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-button border text-xs transition-colors ${showGreeks ? "bg-bg-elevated border-text-tertiary text-text-primary" : "border-border text-text-tertiary hover:text-text-secondary"}`}
              >
                <Activity className="w-3.5 h-3.5" />
                Greeks
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* close dropdowns on click away */}
      {(symbolDropdownOpen || expDropdownOpen) && (
        <div className="fixed inset-0 z-40" onClick={() => { setSymbolDropdownOpen(false); setExpDropdownOpen(false); }} />
      )}

      <div className="max-w-[1800px] mx-auto px-4 py-6 space-y-6">
        {/* ---- Best Plays Recommender (top of page) ---- */}
        <Card padding="none">
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-heading text-text-primary">Best Plays — Live Recommender</span>
              <span className="text-[10px] text-text-tertiary ml-2">
                Top 2 ITM / OTM per expiry • scored 0-100 (POP + liquidity + spread + greek fit + IV value)
              </span>
            </div>
            <div className="text-[10px] text-text-tertiary font-mono">
              {recsLoading ? "refreshing…" : recs ? `as of ${new Date(recs.generated_at).toLocaleTimeString()}` : ""}
            </div>
          </div>

          {/* Overall Best across the universe */}
          {recs?.overall_best_trade && (
            <div className="px-5 py-4 bg-gradient-to-r from-amber-500/10 via-amber-400/5 to-transparent border-b border-amber-400/30">
              <div className="flex items-center gap-2 mb-2">
                <Award className="w-4 h-4 text-amber-300" />
                <span className="text-[11px] font-heading uppercase tracking-wider text-amber-300">
                  Overall Best Trade (cross-universe)
                </span>
              </div>
              <div className="flex items-center flex-wrap gap-x-6 gap-y-2">
                <div>
                  <div className="text-lg font-heading text-text-primary">
                    {recs.overall_best_trade.contract_id}
                  </div>
                  <div className="text-[11px] text-text-tertiary font-mono">
                    {recs.overall_best_trade.occ_symbol}
                  </div>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono">
                  <div>
                    <div className="text-text-tertiary text-[10px] uppercase tracking-wider">Premium</div>
                    <div className="text-text-primary">${recs.overall_best_trade.mid.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-text-tertiary text-[10px] uppercase tracking-wider">Breakeven</div>
                    <div className="text-text-primary">${recs.overall_best_trade.extras.breakeven.toFixed(2)}</div>
                  </div>
                  <div>
                    <div className="text-text-tertiary text-[10px] uppercase tracking-wider">POP</div>
                    <div className="text-profit">{recs.overall_best_trade.components.probability_of_profit.toFixed(0)}%</div>
                  </div>
                  <div>
                    <div className="text-text-tertiary text-[10px] uppercase tracking-wider">Delta</div>
                    <div className="text-text-primary">{recs.overall_best_trade.delta.toFixed(3)}</div>
                  </div>
                  <div>
                    <div className="text-text-tertiary text-[10px] uppercase tracking-wider">IV</div>
                    <div className="text-text-primary">{recs.overall_best_trade.iv.toFixed(1)}%</div>
                  </div>
                  <div>
                    <div className="text-text-tertiary text-[10px] uppercase tracking-wider">Max Loss/Contract</div>
                    <div className="text-loss">${recs.overall_best_trade.extras.max_loss_per_contract.toFixed(0)}</div>
                  </div>
                </div>
                <div className="ml-auto">
                  <div className="text-[10px] text-text-tertiary uppercase tracking-wider">Composite</div>
                  <div className="text-2xl font-heading text-amber-300">
                    {recs.overall_best_trade.composite_score.toFixed(1)}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Per-symbol best plays for the currently selected ticker */}
          <div className="p-5">
            <div className="flex items-center gap-2 mb-3">
              <Star className="w-3.5 h-3.5 text-text-secondary" />
              <span className="text-xs font-heading text-text-primary">
                Best Plays for {selectedSymbol}
              </span>
              {recsForSelected && (
                <span className="text-[10px] text-text-tertiary">
                  · realised vol {(recsForSelected.realised_vol_annualised * 100).toFixed(1)}%
                </span>
              )}
            </div>

            {recsError && (
              <div className="text-xs text-loss font-mono">{recsError}</div>
            )}

            {!recsError && !recsForSelected && (
              <div className="text-xs text-text-tertiary">
                {recsLoading ? "Loading recommendations…" : `No data for ${selectedSymbol} yet — try SPY, QQQ, AAPL, NVDA, TSLA, MSFT, or META.`}
              </div>
            )}

            {recsForSelected?.by_expiry.map((exp) => (
              <div key={exp.expiry} className="mb-5 last:mb-0">
                <div className="text-[11px] font-heading text-text-secondary mb-2">
                  Expiry {exp.expiry} ({exp.dte}d)
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  {[
                    { label: "Top ITM Calls", picks: exp.top_itm_calls, accent: "border-emerald-500/40 bg-emerald-500/5" },
                    { label: "Top OTM Calls", picks: exp.top_otm_calls, accent: "border-sky-500/40 bg-sky-500/5" },
                    { label: "Top ITM Puts",  picks: exp.top_itm_puts,  accent: "border-fuchsia-500/40 bg-fuchsia-500/5" },
                    { label: "Top OTM Puts",  picks: exp.top_otm_puts,  accent: "border-rose-500/40 bg-rose-500/5" },
                  ].map((g) => (
                    <div key={g.label} className={`rounded-card border ${g.accent} p-3`}>
                      <div className="text-[10px] font-heading uppercase tracking-wider text-text-secondary mb-2">
                        {g.label}
                      </div>
                      {g.picks.length === 0 ? (
                        <div className="text-[10px] text-text-tertiary">no picks</div>
                      ) : (
                        <div className="space-y-2">
                          {g.picks.map((p, i) => (
                            <div key={p.occ_symbol} className="text-[11px] font-mono">
                              <div className="flex items-center justify-between">
                                <span className="text-text-primary">
                                  {i === 0 && <span className="text-amber-300 mr-1">★</span>}
                                  {p.option_type === "CALL" ? "C" : "P"} {p.strike}
                                </span>
                                <span className="text-text-secondary">{p.composite_score.toFixed(1)}</span>
                              </div>
                              <div className="flex items-center justify-between text-text-tertiary">
                                <span>${p.mid.toFixed(2)}</span>
                                <span>Δ {p.delta.toFixed(2)}</span>
                                <span>POP {p.components.probability_of_profit.toFixed(0)}%</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* ---- Options Chain Table ---- */}
        <Card padding="none">
          <div className="px-5 py-4 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-text-secondary" />
              <span className="text-sm font-heading text-text-primary">Options Chain</span>
              <span className="text-xs text-text-tertiary ml-2">{selectedSymbol} &middot; {expConfig.label} &middot; {dte} DTE</span>
            </div>
            <div className="text-xs text-text-tertiary font-mono">ATM: ${atmStrike.toFixed(2)}</div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="border-b border-border text-text-tertiary">
                  {/* Calls */}
                  <th className="px-2 py-2 text-right font-normal">Last</th>
                  <th className="px-2 py-2 text-right font-normal">Chg</th>
                  <th className="px-2 py-2 text-right font-normal">Bid</th>
                  <th className="px-2 py-2 text-right font-normal">Ask</th>
                  <th className="px-2 py-2 text-right font-normal">Vol</th>
                  <th className="px-2 py-2 text-right font-normal">OI</th>
                  <th className="px-2 py-2 text-right font-normal">IV</th>
                  {showGreeks && (
                    <>
                      <th className="px-2 py-2 text-right font-normal">Delta</th>
                      <th className="px-2 py-2 text-right font-normal">Gamma</th>
                      <th className="px-2 py-2 text-right font-normal">Theta</th>
                      <th className="px-2 py-2 text-right font-normal">Vega</th>
                    </>
                  )}
                  {/* Strike */}
                  <th className="px-3 py-2 text-center font-heading font-semibold text-text-primary bg-bg-elevated">Strike</th>
                  {/* Puts */}
                  {showGreeks && (
                    <>
                      <th className="px-2 py-2 text-right font-normal">Delta</th>
                      <th className="px-2 py-2 text-right font-normal">Gamma</th>
                      <th className="px-2 py-2 text-right font-normal">Theta</th>
                      <th className="px-2 py-2 text-right font-normal">Vega</th>
                    </>
                  )}
                  <th className="px-2 py-2 text-right font-normal">IV</th>
                  <th className="px-2 py-2 text-right font-normal">OI</th>
                  <th className="px-2 py-2 text-right font-normal">Vol</th>
                  <th className="px-2 py-2 text-right font-normal">Ask</th>
                  <th className="px-2 py-2 text-right font-normal">Bid</th>
                  <th className="px-2 py-2 text-right font-normal">Chg</th>
                  <th className="px-2 py-2 text-right font-normal">Last</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {chain.strikes.map((strike, idx) => {
                  const call = chain.calls[idx];
                  const put = chain.puts[idx];
                  const isAtm = strike === atmStrike;
                  const callItm = strike < spot;
                  const putItm = strike > spot;
                  return (
                    <tr key={strike} className={`hover:bg-bg-elevated/50 transition-colors ${isAtm ? "bg-bg-elevated/30" : ""}`}>
                      {/* CALLS */}
                      <td className={`px-2 py-1.5 text-right ${callItm ? "bg-profit/5" : ""}`}>{call.last.toFixed(2)}</td>
                      <td className={`px-2 py-1.5 text-right ${callItm ? "bg-profit/5" : ""} ${call.change >= 0 ? "text-profit" : "text-loss"}`}>{call.change >= 0 ? "+" : ""}{call.change.toFixed(2)}</td>
                      <td className={`px-2 py-1.5 text-right text-text-secondary ${callItm ? "bg-profit/5" : ""}`}>{call.bid.toFixed(2)}</td>
                      <td className={`px-2 py-1.5 text-right text-text-secondary ${callItm ? "bg-profit/5" : ""}`}>{call.ask.toFixed(2)}</td>
                      <td className={`px-2 py-1.5 text-right text-text-tertiary ${callItm ? "bg-profit/5" : ""}`}>{fmtK(call.volume)}</td>
                      <td className={`px-2 py-1.5 text-right text-text-tertiary ${callItm ? "bg-profit/5" : ""}`}>{fmtK(call.oi)}</td>
                      <td className={`px-2 py-1.5 text-right ${callItm ? "bg-profit/5" : ""}`}>{call.iv.toFixed(1)}%</td>
                      {showGreeks && (
                        <>
                          <td className={`px-2 py-1.5 text-right text-text-secondary ${callItm ? "bg-profit/5" : ""}`}>{call.delta.toFixed(3)}</td>
                          <td className={`px-2 py-1.5 text-right text-text-tertiary ${callItm ? "bg-profit/5" : ""}`}>{call.gamma.toFixed(4)}</td>
                          <td className={`px-2 py-1.5 text-right text-loss ${callItm ? "bg-profit/5" : ""}`}>{call.theta.toFixed(2)}</td>
                          <td className={`px-2 py-1.5 text-right text-text-secondary ${callItm ? "bg-profit/5" : ""}`}>{call.vega.toFixed(2)}</td>
                        </>
                      )}
                      {/* STRIKE */}
                      <td className={`px-3 py-1.5 text-center font-heading bg-bg-elevated ${isAtm ? "text-text-primary font-semibold" : "text-text-secondary"}`}>
                        {strike.toFixed(2)}
                        {isAtm && <span className="ml-1 text-[9px] text-text-tertiary">ATM</span>}
                      </td>
                      {/* PUTS */}
                      {showGreeks && (
                        <>
                          <td className={`px-2 py-1.5 text-right text-text-secondary ${putItm ? "bg-loss/5" : ""}`}>{put.delta.toFixed(3)}</td>
                          <td className={`px-2 py-1.5 text-right text-text-tertiary ${putItm ? "bg-loss/5" : ""}`}>{put.gamma.toFixed(4)}</td>
                          <td className={`px-2 py-1.5 text-right text-loss ${putItm ? "bg-loss/5" : ""}`}>{put.theta.toFixed(2)}</td>
                          <td className={`px-2 py-1.5 text-right text-text-secondary ${putItm ? "bg-loss/5" : ""}`}>{put.vega.toFixed(2)}</td>
                        </>
                      )}
                      <td className={`px-2 py-1.5 text-right ${putItm ? "bg-loss/5" : ""}`}>{put.iv.toFixed(1)}%</td>
                      <td className={`px-2 py-1.5 text-right text-text-tertiary ${putItm ? "bg-loss/5" : ""}`}>{fmtK(put.oi)}</td>
                      <td className={`px-2 py-1.5 text-right text-text-tertiary ${putItm ? "bg-loss/5" : ""}`}>{fmtK(put.volume)}</td>
                      <td className={`px-2 py-1.5 text-right text-text-secondary ${putItm ? "bg-loss/5" : ""}`}>{put.ask.toFixed(2)}</td>
                      <td className={`px-2 py-1.5 text-right text-text-secondary ${putItm ? "bg-loss/5" : ""}`}>{put.bid.toFixed(2)}</td>
                      <td className={`px-2 py-1.5 text-right ${putItm ? "bg-loss/5" : ""} ${put.change >= 0 ? "text-profit" : "text-loss"}`}>{put.change >= 0 ? "+" : ""}{put.change.toFixed(2)}</td>
                      <td className={`px-2 py-1.5 text-right ${putItm ? "bg-loss/5" : ""}`}>{put.last.toFixed(2)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        {/* ---- Middle row: Flow + Greeks + IV ---- */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Flow Panel */}
          <Card padding="none" className="lg:col-span-2">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-text-secondary" />
                <span className="text-sm font-heading text-text-primary">Unusual Flow</span>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-profit" />
                  <span className="text-text-secondary">Call Premium</span>
                  <span className="font-mono text-text-primary">{fmtDollar(totalCallPremium)}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-loss" />
                  <span className="text-text-secondary">Put Premium</span>
                  <span className="font-mono text-text-primary">{fmtDollar(totalPutPremium)}</span>
                </div>
                <div className="text-text-tertiary">P/C: <span className="font-mono text-text-primary">{pcRatio}</span></div>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-border text-text-tertiary">
                    <th className="px-3 py-2 text-left font-normal">Time</th>
                    <th className="px-3 py-2 text-left font-normal">Strike</th>
                    <th className="px-3 py-2 text-left font-normal">Exp</th>
                    <th className="px-3 py-2 text-left font-normal">Type</th>
                    <th className="px-3 py-2 text-left font-normal">Side</th>
                    <th className="px-3 py-2 text-right font-normal">Size</th>
                    <th className="px-3 py-2 text-right font-normal">Premium</th>
                    <th className="px-3 py-2 text-right font-normal">Spot</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {flow.map((f, i) => (
                    <tr key={i} className={`hover:bg-bg-elevated/50 transition-colors ${f.sentiment === "bullish" ? "border-l-2 border-l-profit" : "border-l-2 border-l-loss"}`}>
                      <td className="px-3 py-1.5 text-text-tertiary">{f.time}</td>
                      <td className="px-3 py-1.5 text-text-primary">${f.strike}</td>
                      <td className="px-3 py-1.5 text-text-secondary">{f.exp}</td>
                      <td className={`px-3 py-1.5 ${f.type === "Call" ? "text-profit" : "text-loss"}`}>{f.type}</td>
                      <td className="px-3 py-1.5 text-text-secondary">{f.side}</td>
                      <td className="px-3 py-1.5 text-right text-text-primary">{f.size.toLocaleString()}</td>
                      <td className="px-3 py-1.5 text-right text-text-primary">{fmtDollar(f.premium)}</td>
                      <td className="px-3 py-1.5 text-right text-text-tertiary">${f.spot.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Greeks Summary + IV */}
          <div className="space-y-6">
            {/* Greeks Summary */}
            <Card padding="none">
              <div className="px-5 py-4 border-b border-border flex items-center gap-2">
                <Shield className="w-4 h-4 text-text-secondary" />
                <span className="text-sm font-heading text-text-primary">Portfolio Greeks</span>
              </div>
              <div className="p-5">
                <p className="text-[10px] text-text-tertiary mb-3 uppercase tracking-wider">Hypothetical: Long 5 ATM Calls, Short 3 OTM Puts</p>
                <div className="grid grid-cols-2 gap-4">
                  {[
                    { label: "Net Delta", value: portfolioGreeks.delta, fmt: (v: number) => (v >= 0 ? "+" : "") + v.toFixed(1) },
                    { label: "Net Gamma", value: portfolioGreeks.gamma, fmt: (v: number) => v.toFixed(2) },
                    { label: "Net Theta", value: portfolioGreeks.theta, fmt: (v: number) => (v >= 0 ? "+" : "") + "$" + Math.abs(v).toFixed(1) + "/day" },
                    { label: "Net Vega", value: portfolioGreeks.vega, fmt: (v: number) => "$" + v.toFixed(1) + "/1% IV" },
                  ].map((g) => (
                    <div key={g.label} className="bg-bg-elevated rounded-card p-3">
                      <div className="text-[10px] text-text-tertiary uppercase tracking-wider mb-1">{g.label}</div>
                      <div className={`text-sm font-mono ${g.label === "Net Theta" && g.value < 0 ? "text-loss" : g.label === "Net Delta" && g.value > 0 ? "text-profit" : "text-text-primary"}`}>
                        {g.fmt(g.value)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Card>

            {/* IV Term Structure */}
            <Card padding="none">
              <div className="px-5 py-4 border-b border-border flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-text-secondary" />
                <span className="text-sm font-heading text-text-primary">IV Term Structure</span>
              </div>
              <div className="divide-y divide-border/50">
                {termStructure.map((ts) => (
                  <div key={ts.label} className="flex items-center justify-between px-5 py-2.5">
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-text-secondary w-16">{ts.label}</span>
                      <span className="text-[10px] text-text-tertiary font-mono">{ts.dte}d</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-24 h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                        <div className="h-full bg-text-secondary/50 rounded-full" style={{ width: `${Math.min(ts.iv / 45 * 100, 100)}%` }} />
                      </div>
                      <span className="text-xs font-mono text-text-primary w-12 text-right">{ts.iv}%</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            {/* IV Skew for selected expiration */}
            <Card padding="none">
              <div className="px-5 py-4 border-b border-border flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-text-secondary" />
                <span className="text-sm font-heading text-text-primary">IV Skew</span>
                <span className="text-xs text-text-tertiary ml-1">({expConfig.label})</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs font-mono">
                  <thead>
                    <tr className="border-b border-border text-text-tertiary">
                      <th className="px-3 py-2 text-right font-normal">Strike</th>
                      <th className="px-3 py-2 text-right font-normal">Call IV</th>
                      <th className="px-3 py-2 text-right font-normal">Put IV</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/50">
                    {chain.strikes.filter((_, i) => i % 2 === 0).map((strike, idx) => {
                      const ci = chain.strikes.indexOf(strike);
                      return (
                        <tr key={strike} className={`${strike === atmStrike ? "bg-bg-elevated/30" : ""}`}>
                          <td className="px-3 py-1.5 text-right text-text-secondary">{strike.toFixed(2)}{strike === atmStrike ? " ATM" : ""}</td>
                          <td className="px-3 py-1.5 text-right text-text-primary">{chain.calls[ci].iv.toFixed(1)}%</td>
                          <td className="px-3 py-1.5 text-right text-text-primary">{chain.puts[ci].iv.toFixed(1)}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </div>

        {/* ---- Strategy Builder ---- */}
        <Card padding="none">
          <div className="px-5 py-4 border-b border-border flex items-center gap-2">
            <Target className="w-4 h-4 text-text-secondary" />
            <span className="text-sm font-heading text-text-primary">Strategy Builder</span>
            <span className="text-xs text-text-tertiary ml-2">{selectedSymbol} @ ${spot.toFixed(2)}</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 p-5">
            {strategies.map((strat) => (
              <div key={strat.name} className="bg-bg-elevated rounded-card p-4 border border-border/50 hover:border-text-tertiary transition-colors">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-heading text-text-primary">{strat.name}</span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-chip bg-bg-card text-text-secondary">{strat.pop}% PoP</span>
                </div>
                <p className="text-xs text-text-tertiary mb-3 font-mono">{strat.description}</p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-text-tertiary">Max Profit</span>
                    <div className="text-profit font-mono">{strat.maxProfit}</div>
                  </div>
                  <div>
                    <span className="text-text-tertiary">Max Loss</span>
                    <div className="text-loss font-mono">{strat.maxLoss}</div>
                  </div>
                  <div className="col-span-2">
                    <span className="text-text-tertiary">Breakeven</span>
                    <div className="text-text-primary font-mono">{strat.breakeven}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
