"use client";

import { useState, useEffect, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { apiFetch, formatCurrency, formatNumber } from "@/lib/api";
import {
  Receipt,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Download,
  Calendar,
  DollarSign,
  Shield,
} from "lucide-react";
import { ExportMenu } from "@/components/ui/ExportMenu";

// ─── Types ───────────────────────────────────────────────

interface TaxLot {
  lot_id: string;
  symbol: string;
  quantity: number;
  entry_price: number;
  entry_date: string;
  side: string;
  exit_price: number | null;
  exit_date: string | null;
  status: string;
  gain_loss: number | null;
  term: string | null;
}

interface RealizedGains {
  short_term: number;
  long_term: number;
  total: number;
}

interface Liability {
  year: number;
  filing_status: string;
  short_term_gains: number;
  long_term_gains: number;
  total_gains: number;
  short_term_tax: number;
  long_term_tax: number;
  estimated_tax: number;
  effective_rate: number;
}

interface TaxSummaryResponse {
  year: number;
  realized_gains: RealizedGains;
  liability: Liability;
}

interface TaxLotsResponse {
  lots: TaxLot[];
  count: number;
}

interface HarvestCandidate {
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_loss: number;
  estimated_tax_savings: number;
  side: string;
}

interface HarvestResponse {
  candidates: HarvestCandidate[];
  count: number;
}

interface WashSaleFlag {
  lot_id: string;
  symbol: string;
  entry_date: string;
  quantity: number;
  entry_price: number;
  wash_sale_risk: boolean;
  loss_date: string;
  loss_lot_id: string;
  loss_amount: number;
}

interface WashSaleResponse {
  wash_sales: WashSaleFlag[];
  count: number;
}

// ─── Mock Data ───────────────────────────────────────────

const MOCK_SUMMARY: TaxSummaryResponse = {
  year: 2026,
  realized_gains: { short_term: 12_480.50, long_term: 34_210.75, total: 46_691.25 },
  liability: {
    year: 2026,
    filing_status: "single",
    short_term_gains: 12_480.50,
    long_term_gains: 34_210.75,
    total_gains: 46_691.25,
    short_term_tax: 2_745.71,
    long_term_tax: 0,
    estimated_tax: 2_745.71,
    effective_rate: 5.88,
  },
};

const MOCK_LOTS: TaxLot[] = [
  { lot_id: "a1b2c3", symbol: "AAPL", quantity: 50, entry_price: 168.22, entry_date: "2025-03-15", side: "long", exit_price: 192.40, exit_date: "2026-01-22", status: "closed", gain_loss: 1209.00, term: "short_term" },
  { lot_id: "d4e5f6", symbol: "NVDA", quantity: 30, entry_price: 420.50, entry_date: "2024-06-10", side: "long", exit_price: 890.30, exit_date: "2026-02-14", status: "closed", gain_loss: 14094.00, term: "long_term" },
  { lot_id: "g7h8i9", symbol: "TSLA", quantity: 25, entry_price: 245.80, entry_date: "2025-08-20", side: "long", exit_price: 210.15, exit_date: "2026-01-05", status: "closed", gain_loss: -891.25, term: "short_term" },
  { lot_id: "j1k2l3", symbol: "MSFT", quantity: 40, entry_price: 310.00, entry_date: "2024-01-12", side: "long", exit_price: 425.60, exit_date: "2026-03-01", status: "closed", gain_loss: 4624.00, term: "long_term" },
  { lot_id: "m4n5o6", symbol: "SPY", quantity: 100, entry_price: 450.00, entry_date: "2025-11-01", side: "long", exit_price: null, exit_date: null, status: "open", gain_loss: null, term: null },
  { lot_id: "p7q8r9", symbol: "AMZN", quantity: 20, entry_price: 178.50, entry_date: "2025-09-15", side: "long", exit_price: null, exit_date: null, status: "open", gain_loss: null, term: null },
  { lot_id: "s1t2u3", symbol: "QQQ", quantity: 60, entry_price: 390.20, entry_date: "2024-04-01", side: "long", exit_price: 445.80, exit_date: "2026-02-28", status: "closed", gain_loss: 3336.00, term: "long_term" },
  { lot_id: "v4w5x6", symbol: "META", quantity: 15, entry_price: 520.00, entry_date: "2025-12-01", side: "long", exit_price: 490.10, exit_date: "2026-03-10", status: "closed", gain_loss: -448.50, term: "short_term" },
];

const MOCK_HARVEST: HarvestCandidate[] = [
  { symbol: "AMZN", quantity: 20, entry_price: 178.50, current_price: 165.30, unrealized_loss: -264.00, estimated_tax_savings: 66.00, side: "long" },
  { symbol: "SPY", quantity: 100, entry_price: 450.00, current_price: 438.20, unrealized_loss: -1180.00, estimated_tax_savings: 295.00, side: "long" },
];

const MOCK_WASH_SALES: WashSaleFlag[] = [
  { lot_id: "ws001", symbol: "TSLA", entry_date: "2026-01-12", quantity: 25, entry_price: 215.40, wash_sale_risk: true, loss_date: "2026-01-05", loss_lot_id: "g7h8i9", loss_amount: -891.25 },
];

// ─── Helpers ─────────────────────────────────────────────

type FilingStatus = "single" | "married_filing_jointly" | "head_of_household";

const FILING_OPTIONS: { key: FilingStatus; label: string }[] = [
  { key: "single", label: "Single" },
  { key: "married_filing_jointly", label: "Married Filing Jointly" },
  { key: "head_of_household", label: "Head of Household" },
];

function holdingPeriodLabel(entryDate: string, exitDate: string | null): string {
  const entry = new Date(entryDate);
  const exit = exitDate ? new Date(exitDate) : new Date();
  const days = Math.floor((exit.getTime() - entry.getTime()) / 86_400_000);
  if (days < 30) return `${days}d`;
  if (days < 365) return `${Math.floor(days / 30)}mo`;
  const years = Math.floor(days / 365);
  const remainMonths = Math.floor((days % 365) / 30);
  return remainMonths > 0 ? `${years}y ${remainMonths}mo` : `${years}y`;
}

function exportCsv(lots: TaxLot[]) {
  const header = "Symbol,Quantity,Entry Price,Entry Date,Exit Price,Exit Date,Gain/Loss,Term,Status\n";
  const rows = lots.map((l) =>
    [
      l.symbol,
      l.quantity,
      l.entry_price,
      l.entry_date,
      l.exit_price ?? "",
      l.exit_date ?? "",
      l.gain_loss ?? "",
      l.term ?? "",
      l.status,
    ].join(",")
  ).join("\n");
  const blob = new Blob([header + rows], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `lumare_tax_lots_${new Date().getFullYear()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Component ───────────────────────────────────────────

export default function TaxesPage() {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [filingStatus, setFilingStatus] = useState<FilingStatus>("single");
  const [summary, setSummary] = useState<TaxSummaryResponse | null>(null);
  const [lots, setLots] = useState<TaxLot[]>([]);
  const [harvestCandidates, setHarvestCandidates] = useState<HarvestCandidate[]>([]);
  const [washSales, setWashSales] = useState<WashSaleFlag[]>([]);

  const fetchData = useCallback(async () => {
    const [sumRes, lotsRes, harvestRes, washRes] = await Promise.all([
      apiFetch<TaxSummaryResponse>(`/api/tax/summary?year=${year}&filing_status=${filingStatus}`),
      apiFetch<TaxLotsResponse>(`/api/tax/lots?year=${year}`),
      apiFetch<HarvestResponse>("/api/tax/harvest"),
      apiFetch<WashSaleResponse>("/api/tax/wash-sales"),
    ]);

    setSummary(sumRes ?? { ...MOCK_SUMMARY, year });
    setLots(lotsRes?.lots ?? MOCK_LOTS);
    setHarvestCandidates(harvestRes?.candidates ?? MOCK_HARVEST);
    setWashSales(washRes?.wash_sales ?? MOCK_WASH_SALES);
  }, [year, filingStatus]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const gains = summary?.realized_gains ?? MOCK_SUMMARY.realized_gains;
  const liability = summary?.liability ?? MOCK_SUMMARY.liability;

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Receipt size={20} className="text-blue-500" />
          <div>
            <h1 className="font-heading text-lg md:text-2xl font-bold">Tax Dashboard</h1>
            <p className="text-text-secondary text-xs">Capital gains tracking &amp; tax optimization</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Year selector */}
          <div className="flex items-center gap-2 bg-bg-card border border-border rounded-lg px-3 py-1.5">
            <Calendar size={14} className="text-text-tertiary" />
            <select
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="bg-transparent text-xs font-mono text-text-primary outline-none cursor-pointer"
            >
              {[currentYear, currentYear - 1, currentYear - 2, currentYear - 3].map((y) => (
                <option key={y} value={y} className="bg-[#0a0a0a] text-white">
                  {y}
                </option>
              ))}
            </select>
          </div>

          {/* Export button */}
          <button
            onClick={() => exportCsv(lots)}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-lg hover:bg-blue-500/20 transition-colors"
          >
            <Download size={14} />
            Export for TurboTax
          </button>
          <ExportMenu
            data={lots.map((l) => ({
              symbol: l.symbol,
              qty: l.quantity,
              costBasis: l.entry_price,
              exitPrice: l.exit_price ?? "",
              gainLoss: l.gain_loss ?? "",
              term: l.term ? (l.term === "long_term" ? "Long" : "Short") : "",
              status: l.status,
            } as Record<string, unknown>))}
            filename={`lumare_tax_lots_${year}`}
            title={`Tax Lots — ${year}`}
            columns={[
              { key: "symbol", label: "Symbol" },
              { key: "qty", label: "Qty" },
              { key: "costBasis", label: "Cost Basis" },
              { key: "exitPrice", label: "Exit Price" },
              { key: "gainLoss", label: "Gain/Loss" },
              { key: "term", label: "Term" },
              { key: "status", label: "Status" },
            ]}
          />
        </div>
      </header>

      {/* Filing Status Pills */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-text-tertiary text-xs font-mono mr-1">Filing Status:</span>
        {FILING_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            onClick={() => setFilingStatus(opt.key)}
            className={`px-4 py-1.5 text-xs font-mono rounded-full border transition-colors ${
              filingStatus === opt.key
                ? "bg-blue-500/15 text-blue-400 border-blue-500/30"
                : "bg-bg-card text-text-tertiary border-border hover:text-text-secondary hover:border-[#333]"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        <Card padding="sm">
          <div className="flex items-center gap-2 mb-1">
            <DollarSign size={14} className="text-text-tertiary" />
            <p className="text-text-tertiary text-[9px] uppercase tracking-wider">Total Realized</p>
          </div>
          <p className={`font-heading text-xl font-bold font-mono ${gains.total >= 0 ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
            {formatCurrency(gains.total)}
          </p>
        </Card>

        <Card padding="sm">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp size={14} className="text-[#ef4444]" />
            <p className="text-text-tertiary text-[9px] uppercase tracking-wider">Short-Term</p>
          </div>
          <p className={`font-heading text-xl font-bold font-mono ${gains.short_term >= 0 ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
            {formatCurrency(gains.short_term)}
          </p>
          <p className="text-text-tertiary text-[10px] font-mono mt-0.5">
            Tax: {formatCurrency(liability.short_term_tax)}
          </p>
        </Card>

        <Card padding="sm">
          <div className="flex items-center gap-2 mb-1">
            <TrendingDown size={14} className="text-[#22c55e]" />
            <p className="text-text-tertiary text-[9px] uppercase tracking-wider">Long-Term</p>
          </div>
          <p className={`font-heading text-xl font-bold font-mono ${gains.long_term >= 0 ? "text-[#22c55e]" : "text-[#ef4444]"}`}>
            {formatCurrency(gains.long_term)}
          </p>
          <p className="text-text-tertiary text-[10px] font-mono mt-0.5">
            Tax: {formatCurrency(liability.long_term_tax)}
          </p>
        </Card>

        <Card padding="sm">
          <div className="flex items-center gap-2 mb-1">
            <Shield size={14} className="text-[#3b82f6]" />
            <p className="text-text-tertiary text-[9px] uppercase tracking-wider">Est. Tax Liability</p>
          </div>
          <p className="font-heading text-xl font-bold font-mono text-[#3b82f6]">
            {formatCurrency(liability.estimated_tax)}
          </p>
        </Card>

        <Card padding="sm">
          <div className="flex items-center gap-2 mb-1">
            <Receipt size={14} className="text-[#f59e0b]" />
            <p className="text-text-tertiary text-[9px] uppercase tracking-wider">Effective Rate</p>
          </div>
          <p className="font-heading text-xl font-bold font-mono text-[#f59e0b]">
            {liability.effective_rate.toFixed(2)}%
          </p>
          <p className="text-text-tertiary text-[10px] font-mono mt-0.5">
            {filingStatus.replace(/_/g, " ")}
          </p>
        </Card>
      </div>

      {/* Wash Sale Alerts */}
      {washSales.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-heading text-sm font-semibold flex items-center gap-2 text-[#f59e0b]">
            <AlertTriangle size={16} />
            Wash Sale Alerts ({washSales.length})
          </h3>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {washSales.map((ws) => (
              <Card key={`${ws.lot_id}-${ws.loss_lot_id}`} className="!border-[#f59e0b]/30 !bg-[#f59e0b]/5">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <AlertTriangle size={14} className="text-[#f59e0b]" />
                      <span className="font-mono text-sm font-bold text-[#f59e0b]">{ws.symbol}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#f59e0b]/15 text-[#f59e0b]">
                        WASH SALE RISK
                      </span>
                    </div>
                    <p className="text-text-secondary text-xs mt-1">
                      Repurchased {ws.quantity} shares on {ws.entry_date} at ${formatNumber(ws.entry_price)}
                    </p>
                    <p className="text-text-tertiary text-[10px] mt-0.5">
                      Within 30-day window of loss realized on {ws.loss_date}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-[#ef4444] font-mono text-sm font-bold">
                      {formatCurrency(ws.loss_amount)}
                    </p>
                    <p className="text-text-tertiary text-[10px]">disallowed loss</p>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Tax Lots Table */}
      <Card padding="none">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h3 className="font-heading text-sm font-semibold">Tax Lots ({lots.length})</h3>
          <div className="flex gap-1 text-[10px] font-mono text-text-tertiary">
            <span className="px-2 py-0.5 rounded bg-[#22c55e]/10 text-[#22c55e]">
              {lots.filter((l) => l.status === "closed" && (l.gain_loss ?? 0) > 0).length} winners
            </span>
            <span className="px-2 py-0.5 rounded bg-[#ef4444]/10 text-[#ef4444]">
              {lots.filter((l) => l.status === "closed" && (l.gain_loss ?? 0) < 0).length} losers
            </span>
            <span className="px-2 py-0.5 rounded bg-[#3b82f6]/10 text-[#3b82f6]">
              {lots.filter((l) => l.status === "open").length} open
            </span>
          </div>
        </div>
        {lots.length === 0 ? (
          <div className="p-8 text-center text-text-tertiary text-sm">
            No tax lots recorded for {year}. Close paper trades to generate tax lots.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-text-tertiary">
                  <th className="text-left px-4 py-2 font-mono">Symbol</th>
                  <th className="text-right px-4 py-2 font-mono">Qty</th>
                  <th className="text-right px-4 py-2 font-mono">Cost Basis</th>
                  <th className="text-right px-4 py-2 font-mono">Exit Price</th>
                  <th className="text-right px-4 py-2 font-mono">Gain/Loss</th>
                  <th className="text-center px-4 py-2 font-mono">Holding</th>
                  <th className="text-center px-4 py-2 font-mono">Status</th>
                  <th className="text-center px-4 py-2 font-mono">Term</th>
                </tr>
              </thead>
              <tbody>
                {lots.map((lot) => {
                  const gl = lot.gain_loss ?? 0;
                  const isGain = gl > 0;
                  const isLoss = gl < 0;
                  return (
                    <tr key={lot.lot_id} className="border-b border-border/50 hover:bg-bg-elevated/50">
                      <td className="px-4 py-3 font-mono font-semibold">{lot.symbol}</td>
                      <td className="px-4 py-3 text-right font-mono">{lot.quantity}</td>
                      <td className="px-4 py-3 text-right font-mono">${formatNumber(lot.entry_price)}</td>
                      <td className="px-4 py-3 text-right font-mono">
                        {lot.exit_price != null ? `$${formatNumber(lot.exit_price)}` : "--"}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono font-bold ${isGain ? "text-[#22c55e]" : isLoss ? "text-[#ef4444]" : "text-text-tertiary"}`}>
                        {lot.status === "closed" ? formatCurrency(gl) : "--"}
                      </td>
                      <td className="px-4 py-3 text-center font-mono text-text-secondary">
                        {holdingPeriodLabel(lot.entry_date, lot.exit_date)}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase ${
                          lot.status === "open"
                            ? "bg-[#3b82f6]/10 text-[#3b82f6]"
                            : "bg-bg-elevated text-text-secondary"
                        }`}>
                          {lot.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        {lot.term ? (
                          <span className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                            lot.term === "long_term"
                              ? "bg-[#22c55e]/10 text-[#22c55e]"
                              : "bg-[#f59e0b]/10 text-[#f59e0b]"
                          }`}>
                            {lot.term === "long_term" ? "LONG" : "SHORT"}
                          </span>
                        ) : (
                          <span className="text-text-tertiary text-[10px]">--</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Tax Loss Harvesting */}
      <div className="space-y-2">
        <h3 className="font-heading text-sm font-semibold flex items-center gap-2">
          <TrendingDown size={16} className="text-[#22c55e]" />
          Tax Loss Harvesting Candidates
        </h3>
        {harvestCandidates.length === 0 ? (
          <Card>
            <p className="text-text-tertiary text-sm text-center py-4">
              No harvesting candidates — all open positions are in profit.
            </p>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {harvestCandidates.map((c) => (
              <Card key={c.symbol} className="!border-[#22c55e]/20">
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-sm font-bold">{c.symbol}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#ef4444]/10 text-[#ef4444]">
                        UNREALIZED LOSS
                      </span>
                    </div>
                    <p className="text-text-secondary text-xs">
                      {c.quantity} shares &middot; Entry ${formatNumber(c.entry_price)} &rarr; Current ${formatNumber(c.current_price)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-[#ef4444] font-mono text-sm font-bold">
                      {formatCurrency(c.unrealized_loss)}
                    </p>
                    <p className="text-[#22c55e] text-[10px] font-mono mt-0.5">
                      Save ~{formatCurrency(c.estimated_tax_savings)}
                    </p>
                  </div>
                </div>
                <div className="mt-3 h-1.5 rounded-full bg-bg-elevated overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[#ef4444]/60"
                    style={{ width: `${Math.min(Math.abs(c.unrealized_loss) / (c.entry_price * c.quantity) * 100 * 5, 100)}%` }}
                  />
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Footer note */}
      <div className="flex items-center gap-2 px-1 text-text-tertiary text-[10px] font-mono">
        <Shield size={12} />
        <span>Tax estimates are for informational purposes only. Consult a tax professional for filing advice.</span>
      </div>
    </div>
  );
}
