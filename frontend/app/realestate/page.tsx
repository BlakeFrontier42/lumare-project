"use client";

import { useState, useEffect, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { apiFetch, formatCurrency } from "@/lib/api";
import {
  Home,
  Building,
  Building2,
  DollarSign,
  TrendingUp,
  Plus,
  MapPin,
  Key,
  Percent,
  X,
} from "lucide-react";

/* ─── Types ──────────────────────────────────────────────── */

interface Property {
  id: string;
  address: string;
  city: string;
  state: string;
  zip: string;
  type: string;
  purchase_price: number;
  purchase_date: string;
  current_value: number;
  monthly_rent: number;
  monthly_expenses: number;
  mortgage_balance: number;
  mortgage_rate: number;
  mortgage_payment: number;
  sqft: number;
  bedrooms: number;
  bathrooms: number;
  notes: string;
  status: string;
  created_at: string;
}

interface PropertyMetrics {
  property_id: string;
  noi: number;
  cap_rate: number;
  cash_on_cash: number;
  grm: number;
  dscr: number;
  equity: number;
  ltv: number;
  appreciation: number;
  appreciation_pct: number;
  monthly_cashflow: number;
  annual_cashflow: number;
}

interface PortfolioSummary {
  total_value: number;
  total_equity: number;
  total_monthly_cashflow: number;
  avg_cap_rate: number;
  total_appreciation: number;
  total_appreciation_pct: number;
  property_count: number;
}

interface Allocation {
  type: string;
  value: number;
  percentage: number;
}

/* ─── Mock Data ──────────────────────────────────────────── */

const MOCK_PROPERTIES: Property[] = [
  {
    id: "demo-1",
    address: "1245 Oak Ridge Drive",
    city: "Austin",
    state: "TX",
    zip: "78704",
    type: "SFH",
    purchase_price: 425000,
    purchase_date: "2022-06-15",
    current_value: 510000,
    monthly_rent: 2800,
    monthly_expenses: 650,
    mortgage_balance: 320000,
    mortgage_rate: 5.25,
    mortgage_payment: 1766,
    sqft: 2100,
    bedrooms: 3,
    bathrooms: 2,
    notes: "Recently renovated kitchen, strong rental market",
    status: "Active",
    created_at: "2022-06-15T00:00:00",
  },
  {
    id: "demo-2",
    address: "88 Harbor View Ct, Unit 4",
    city: "Miami",
    state: "FL",
    zip: "33131",
    type: "Multi-Family",
    purchase_price: 780000,
    purchase_date: "2021-03-20",
    current_value: 920000,
    monthly_rent: 6200,
    monthly_expenses: 1800,
    mortgage_balance: 585000,
    mortgage_rate: 4.75,
    mortgage_payment: 3051,
    sqft: 3400,
    bedrooms: 6,
    bathrooms: 4,
    notes: "4-unit building, fully occupied",
    status: "Active",
    created_at: "2021-03-20T00:00:00",
  },
  {
    id: "demo-3",
    address: "500 Commerce Blvd",
    city: "Denver",
    state: "CO",
    zip: "80202",
    type: "Commercial",
    purchase_price: 1250000,
    purchase_date: "2020-11-01",
    current_value: 1480000,
    monthly_rent: 11500,
    monthly_expenses: 3200,
    mortgage_balance: 875000,
    mortgage_rate: 5.5,
    mortgage_payment: 4969,
    sqft: 8500,
    bedrooms: 0,
    bathrooms: 4,
    notes: "NNN lease, two tenants, 5-year terms",
    status: "Active",
    created_at: "2020-11-01T00:00:00",
  },
];

function calcMetrics(p: Property): PropertyMetrics {
  const annualRent = p.monthly_rent * 12;
  const annualExpenses = p.monthly_expenses * 12;
  const noi = annualRent - annualExpenses;
  const purchasePrice = p.purchase_price || 1;
  const currentValue = p.current_value || purchasePrice;
  const annualDebtService = p.mortgage_payment * 12;
  const capRate = currentValue ? (noi / currentValue) * 100 : 0;
  const downPayment = purchasePrice - p.mortgage_balance > 0 ? purchasePrice - p.mortgage_balance : purchasePrice;
  const annualCashflow = noi - annualDebtService;
  const cashOnCash = downPayment ? (annualCashflow / downPayment) * 100 : 0;
  const grm = annualRent ? currentValue / annualRent : 0;
  const dscr = annualDebtService ? noi / annualDebtService : 0;
  const equity = currentValue - p.mortgage_balance;
  const ltv = currentValue ? (p.mortgage_balance / currentValue) * 100 : 0;
  const appreciation = currentValue - purchasePrice;
  const appreciationPct = purchasePrice ? (appreciation / purchasePrice) * 100 : 0;
  const monthlyCashflow = p.monthly_rent - p.monthly_expenses - p.mortgage_payment;

  return {
    property_id: p.id,
    noi: Math.round(noi * 100) / 100,
    cap_rate: Math.round(capRate * 100) / 100,
    cash_on_cash: Math.round(cashOnCash * 100) / 100,
    grm: Math.round(grm * 100) / 100,
    dscr: Math.round(dscr * 100) / 100,
    equity: Math.round(equity * 100) / 100,
    ltv: Math.round(ltv * 100) / 100,
    appreciation: Math.round(appreciation * 100) / 100,
    appreciation_pct: Math.round(appreciationPct * 100) / 100,
    monthly_cashflow: Math.round(monthlyCashflow * 100) / 100,
    annual_cashflow: Math.round(annualCashflow * 100) / 100,
  };
}

function calcSummary(props: Property[]): PortfolioSummary {
  if (!props.length) return { total_value: 0, total_equity: 0, total_monthly_cashflow: 0, avg_cap_rate: 0, total_appreciation: 0, total_appreciation_pct: 0, property_count: 0 };
  let totalValue = 0, totalEquity = 0, totalCashflow = 0, totalAppreciation = 0, totalPurchase = 0;
  const capRates: number[] = [];
  for (const p of props) {
    const m = calcMetrics(p);
    totalValue += p.current_value;
    totalEquity += m.equity;
    totalCashflow += m.monthly_cashflow;
    totalAppreciation += m.appreciation;
    totalPurchase += p.purchase_price;
    if (m.cap_rate > 0) capRates.push(m.cap_rate);
  }
  return {
    total_value: totalValue,
    total_equity: totalEquity,
    total_monthly_cashflow: totalCashflow,
    avg_cap_rate: capRates.length ? capRates.reduce((a, b) => a + b, 0) / capRates.length : 0,
    total_appreciation: totalAppreciation,
    total_appreciation_pct: totalPurchase ? (totalAppreciation / totalPurchase) * 100 : 0,
    property_count: props.length,
  };
}

function calcAllocation(props: Property[]): Allocation[] {
  if (!props.length) return [];
  const totals: Record<string, number> = {};
  let grand = 0;
  for (const p of props) {
    totals[p.type] = (totals[p.type] || 0) + p.current_value;
    grand += p.current_value;
  }
  return Object.entries(totals)
    .sort((a, b) => b[1] - a[1])
    .map(([type, value]) => ({ type, value, percentage: grand ? (value / grand) * 100 : 0 }));
}

/* ─── Constants ──────────────────────────────────────────── */

const TYPE_COLORS: Record<string, string> = {
  SFH: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  "Multi-Family": "bg-purple-500/20 text-purple-400 border-purple-500/30",
  Commercial: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  Land: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
};

const TYPE_BAR_COLORS: Record<string, string> = {
  SFH: "#3b82f6",
  "Multi-Family": "#8b5cf6",
  Commercial: "#f59e0b",
  Land: "#22c55e",
};

const STATUS_STYLES: Record<string, string> = {
  Active: "bg-green-500/20 text-green-400",
  "Under Contract": "bg-amber-500/20 text-amber-400",
  Sold: "bg-neutral-500/20 text-neutral-400",
};

const EMPTY_FORM = {
  address: "",
  city: "",
  state: "",
  zip: "",
  type: "SFH",
  purchase_price: "",
  current_value: "",
  purchase_date: "",
  monthly_rent: "",
  monthly_expenses: "",
  mortgage_balance: "",
  mortgage_rate: "",
  sqft: "",
  bedrooms: "",
  bathrooms: "",
  notes: "",
};

/* ─── Component ──────────────────────────────────────────── */

export default function RealEstatePage() {
  const [properties, setProperties] = useState<Property[]>([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [useMock, setUseMock] = useState(false);

  const fetchData = useCallback(async () => {
    const res = await apiFetch<{ properties: Property[] }>("/api/realestate/properties");
    if (res?.properties) {
      setProperties(res.properties);
      setUseMock(false);
    } else {
      setProperties(MOCK_PROPERTIES);
      setUseMock(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSeed = async () => {
    const res = await apiFetch<{ properties: Property[] }>("/api/realestate/seed", { method: "POST" });
    if (res?.properties) {
      setProperties(res.properties);
      setUseMock(false);
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    const payload = {
      address: form.address,
      city: form.city,
      state: form.state,
      zip: form.zip,
      type: form.type,
      purchase_price: parseFloat(form.purchase_price) || 0,
      current_value: parseFloat(form.current_value) || 0,
      purchase_date: form.purchase_date,
      monthly_rent: parseFloat(form.monthly_rent) || 0,
      monthly_expenses: parseFloat(form.monthly_expenses) || 0,
      mortgage_balance: parseFloat(form.mortgage_balance) || 0,
      mortgage_rate: parseFloat(form.mortgage_rate) || 0,
      sqft: parseFloat(form.sqft) || 0,
      bedrooms: parseInt(form.bedrooms) || 0,
      bathrooms: parseFloat(form.bathrooms) || 0,
      notes: form.notes,
    };
    const res = await apiFetch<Property>("/api/realestate/property", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (res) {
      await fetchData();
    }
    setForm(EMPTY_FORM);
    setShowModal(false);
    setSubmitting(false);
  };

  const summary = calcSummary(properties);
  const allocation = calcAllocation(properties);
  const totalIncome = properties.reduce((s, p) => s + p.monthly_rent, 0);
  const totalExpenses = properties.reduce((s, p) => s + p.monthly_expenses + p.mortgage_payment, 0);
  const netCashflow = totalIncome - totalExpenses;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Home size={20} className="text-blue-500" />
          <div>
            <h1 className="font-heading text-lg md:text-2xl font-bold">Real Estate Portfolio</h1>
            <p className="text-text-secondary text-xs">
              {useMock ? "Demo Mode — API offline" : `${summary.property_count} properties tracked`}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {properties.length === 0 && !useMock && (
            <button
              onClick={handleSeed}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-500/20 text-blue-400 border border-blue-500/30 hover:bg-blue-500/30 transition-colors"
            >
              <Key size={14} />
              Load Demo Properties
            </button>
          )}
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/30 transition-colors"
          >
            <Plus size={14} />
            Add Property
          </button>
        </div>
      </header>

      {/* ── Portfolio Overview Hero ────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        <HeroCard
          label="Total Portfolio Value"
          value={formatCurrency(summary.total_value)}
          icon={<Building2 size={16} className="text-blue-400" />}
          color="text-white"
        />
        <HeroCard
          label="Total Equity"
          value={formatCurrency(summary.total_equity)}
          icon={<DollarSign size={16} className="text-green-400" />}
          color={summary.total_equity >= 0 ? "text-green-400" : "text-red-400"}
        />
        <HeroCard
          label="Monthly Cashflow"
          value={formatCurrency(summary.total_monthly_cashflow)}
          icon={<DollarSign size={16} className="text-emerald-400" />}
          color={summary.total_monthly_cashflow >= 0 ? "text-green-400" : "text-red-400"}
        />
        <HeroCard
          label="Avg Cap Rate"
          value={`${summary.avg_cap_rate.toFixed(2)}%`}
          icon={<Percent size={16} className="text-amber-400" />}
          color="text-amber-400"
        />
        <HeroCard
          label="Total Appreciation"
          value={`${summary.total_appreciation_pct >= 0 ? "+" : ""}${summary.total_appreciation_pct.toFixed(1)}%`}
          icon={<TrendingUp size={16} className="text-blue-400" />}
          color={summary.total_appreciation_pct >= 0 ? "text-green-400" : "text-red-400"}
        />
      </div>

      {/* ── Properties Grid ───────────────────────────────── */}
      <section>
        <h2 className="text-sm font-semibold text-text-secondary mb-3">Properties</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {properties.map((p) => {
            const m = calcMetrics(p);
            return <PropertyCard key={p.id} property={p} metrics={m} />;
          })}
        </div>
      </section>

      {/* ── Bottom Row: Allocation + Cashflow ─────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Portfolio Allocation */}
        <Card>
          <h3 className="text-sm font-semibold text-text-secondary mb-4 flex items-center gap-2">
            <Building size={14} className="text-blue-400" />
            Portfolio Allocation
          </h3>
          <div className="space-y-3">
            {allocation.map((a) => (
              <div key={a.type}>
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="text-neutral-300">{a.type}</span>
                  <span className="font-mono text-neutral-400">
                    {formatCurrency(a.value)} ({a.percentage.toFixed(1)}%)
                  </span>
                </div>
                <div className="h-2 bg-[#1a1a1a] rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${a.percentage}%`,
                      backgroundColor: TYPE_BAR_COLORS[a.type] || "#6b7280",
                    }}
                  />
                </div>
              </div>
            ))}
            {allocation.length === 0 && (
              <p className="text-xs text-neutral-500 text-center py-4">No properties to display</p>
            )}
          </div>
        </Card>

        {/* Monthly Cashflow Summary */}
        <Card>
          <h3 className="text-sm font-semibold text-text-secondary mb-4 flex items-center gap-2">
            <DollarSign size={14} className="text-green-400" />
            Monthly Cashflow Summary
          </h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-400">Total Rental Income</span>
              <span className="font-mono text-sm text-green-400">
                {formatCurrency(totalIncome)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-neutral-400">Total Expenses + Mortgage</span>
              <span className="font-mono text-sm text-red-400">
                {formatCurrency(totalExpenses)}
              </span>
            </div>
            <div className="border-t border-[#1a1a1a] pt-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-neutral-200">Net Cashflow</span>
                <span
                  className={`font-mono text-lg font-bold ${
                    netCashflow >= 0 ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {formatCurrency(netCashflow)}
                  <span className="text-xs text-neutral-500 ml-1">/mo</span>
                </span>
              </div>
            </div>
            {/* Per-property breakdown */}
            <div className="border-t border-[#1a1a1a] pt-3 space-y-2">
              {properties.map((p) => {
                const cf = p.monthly_rent - p.monthly_expenses - p.mortgage_payment;
                return (
                  <div key={p.id} className="flex items-center justify-between text-xs">
                    <span className="text-neutral-500 truncate max-w-[60%]">
                      {p.address}
                    </span>
                    <span className={`font-mono ${cf >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {formatCurrency(cf)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      </div>

      {/* ── Add Property Modal ────────────────────────────── */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-[#0a0a0a] border border-[#1a1a1a] rounded-xl w-[95vw] md:w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b border-[#1a1a1a]">
              <h2 className="text-lg font-bold">Add Property</h2>
              <button
                onClick={() => setShowModal(false)}
                className="p-1 rounded hover:bg-white/10 transition-colors"
              >
                <X size={18} className="text-neutral-400" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {/* Address row */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <FormField label="Address" value={form.address} onChange={(v) => setForm({ ...form, address: v })} />
                <FormField label="City" value={form.city} onChange={(v) => setForm({ ...form, city: v })} />
              </div>
              <div className="grid grid-cols-3 gap-3">
                <FormField label="State" value={form.state} onChange={(v) => setForm({ ...form, state: v })} />
                <FormField label="ZIP" value={form.zip} onChange={(v) => setForm({ ...form, zip: v })} />
                <div>
                  <label className="block text-xs text-neutral-400 mb-1">Property Type</label>
                  <select
                    value={form.type}
                    onChange={(e) => setForm({ ...form, type: e.target.value })}
                    className="w-full bg-[#111] border border-[#222] rounded-lg px-3 py-2 text-sm text-neutral-200 outline-none focus:border-blue-500/50"
                  >
                    <option value="SFH">SFH</option>
                    <option value="Multi-Family">Multi-Family</option>
                    <option value="Commercial">Commercial</option>
                    <option value="Land">Land</option>
                  </select>
                </div>
              </div>
              {/* Financial row */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <FormField label="Purchase Price" value={form.purchase_price} onChange={(v) => setForm({ ...form, purchase_price: v })} type="number" />
                <FormField label="Current Value" value={form.current_value} onChange={(v) => setForm({ ...form, current_value: v })} type="number" />
                <FormField label="Purchase Date" value={form.purchase_date} onChange={(v) => setForm({ ...form, purchase_date: v })} type="date" />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <FormField label="Monthly Rent" value={form.monthly_rent} onChange={(v) => setForm({ ...form, monthly_rent: v })} type="number" />
                <FormField label="Monthly Expenses" value={form.monthly_expenses} onChange={(v) => setForm({ ...form, monthly_expenses: v })} type="number" />
                <FormField label="Mortgage Balance" value={form.mortgage_balance} onChange={(v) => setForm({ ...form, mortgage_balance: v })} type="number" />
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <FormField label="Mortgage Rate %" value={form.mortgage_rate} onChange={(v) => setForm({ ...form, mortgage_rate: v })} type="number" />
                <FormField label="Sqft" value={form.sqft} onChange={(v) => setForm({ ...form, sqft: v })} type="number" />
                <FormField label="Bedrooms" value={form.bedrooms} onChange={(v) => setForm({ ...form, bedrooms: v })} type="number" />
                <FormField label="Bathrooms" value={form.bathrooms} onChange={(v) => setForm({ ...form, bathrooms: v })} type="number" />
              </div>
              <div>
                <label className="block text-xs text-neutral-400 mb-1">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  rows={2}
                  className="w-full bg-[#111] border border-[#222] rounded-lg px-3 py-2 text-sm text-neutral-200 outline-none focus:border-blue-500/50 resize-none"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 p-5 border-t border-[#1a1a1a]">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-sm rounded-lg text-neutral-400 hover:text-neutral-200 hover:bg-white/5 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={submitting || !form.address || !form.city || !form.state}
                className="px-4 py-2 text-sm font-medium rounded-lg bg-green-500/20 text-green-400 border border-green-500/30 hover:bg-green-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {submitting ? "Adding..." : "Add Property"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Sub-components ─────────────────────────────────────── */

function HeroCard({
  label,
  value,
  icon,
  color,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  color: string;
}) {
  return (
    <Card>
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-[10px] uppercase tracking-wider text-neutral-500">{label}</span>
      </div>
      <p className={`font-mono text-lg font-bold ${color}`}>{value}</p>
    </Card>
  );
}

function PropertyCard({ property: p, metrics: m }: { property: Property; metrics: PropertyMetrics }) {
  const typeStyle = TYPE_COLORS[p.type] || "bg-neutral-500/20 text-neutral-400 border-neutral-500/30";
  const statusStyle = STATUS_STYLES[p.status] || STATUS_STYLES["Active"];

  return (
    <Card className="space-y-3">
      {/* Top row: address + badges */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-neutral-100 truncate">{p.address}</h3>
          <p className="text-xs text-neutral-500 flex items-center gap-1 mt-0.5">
            <MapPin size={10} />
            {p.city}, {p.state} {p.zip}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className={`text-[10px] font-medium px-2 py-0.5 rounded border ${typeStyle}`}>
            {p.type}
          </span>
          <span className={`text-[10px] font-medium px-2 py-0.5 rounded ${statusStyle}`}>
            {p.status}
          </span>
        </div>
      </div>

      {/* Value + Rent */}
      <div className="flex items-end justify-between">
        <div>
          <span className="text-[10px] uppercase tracking-wider text-neutral-500">Current Value</span>
          <p className="font-mono text-lg font-bold text-neutral-100">{formatCurrency(p.current_value)}</p>
          <span
            className={`text-xs font-mono ${m.appreciation_pct >= 0 ? "text-green-400" : "text-red-400"}`}
          >
            {m.appreciation_pct >= 0 ? "+" : ""}
            {m.appreciation_pct.toFixed(1)}% since purchase
          </span>
        </div>
        <div className="text-right">
          <span className="text-[10px] uppercase tracking-wider text-neutral-500">Monthly Rent</span>
          <p className="font-mono text-lg font-bold text-green-400">{formatCurrency(p.monthly_rent)}</p>
        </div>
      </div>

      {/* Metrics row */}
      <div className="grid grid-cols-3 gap-2 pt-2 border-t border-[#1a1a1a]">
        <MetricPill label="Cap Rate" value={`${m.cap_rate.toFixed(2)}%`} />
        <MetricPill label="Cash-on-Cash" value={`${m.cash_on_cash.toFixed(1)}%`} />
        <MetricPill label="LTV" value={`${m.ltv.toFixed(1)}%`} />
      </div>
    </Card>
  );
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-center">
      <p className="text-[10px] text-neutral-500">{label}</p>
      <p className="font-mono text-xs font-semibold text-neutral-300">{value}</p>
    </div>
  );
}

function FormField({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div>
      <label className="block text-xs text-neutral-400 mb-1">{label}</label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-[#111] border border-[#222] rounded-lg px-3 py-2 text-sm text-neutral-200 outline-none focus:border-blue-500/50"
      />
    </div>
  );
}
