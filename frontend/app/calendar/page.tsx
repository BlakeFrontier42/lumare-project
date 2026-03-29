"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import {
  Calendar,
  Clock,
  ChevronLeft,
  ChevronRight,
  Filter,
  TrendingUp,
  Briefcase,
  DollarSign,
  BarChart3,
  AlertTriangle,
  Flame,
  Zap,
  Target,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type Impact = "High" | "Medium" | "Low";
type Category = "Fed" | "Employment" | "Inflation" | "Growth" | "Earnings";

interface EconEvent {
  id: string;
  date: string;          // YYYY-MM-DD
  time: string;          // HH:mm ET
  name: string;
  impact: Impact;
  category: Category;
  previous: string;
  forecast: string;
  actual: string;
}

interface EarningsEvent {
  id: string;
  date: string;
  time: "BMO" | "AMC" | "DMH";   // before/after market, during hours
  ticker: string;
  company: string;
  epsEstimate: string;
  revenueEstimate: string;
  epsActual: string;
  revenueActual: string;
}

/* ------------------------------------------------------------------ */
/*  Static Data — 3 weeks of events relative to 2026-03-26             */
/* ------------------------------------------------------------------ */

const ECON_EVENTS: EconEvent[] = [
  // Week of Mar 23–27, 2026
  { id: "e1",  date: "2026-03-23", time: "10:00", name: "Existing Home Sales",       impact: "Low",    category: "Growth",     previous: "4.08M",  forecast: "4.14M",  actual: "4.12M" },
  { id: "e2",  date: "2026-03-24", time: "09:45", name: "S&P Global PMI Flash",      impact: "Medium", category: "Growth",     previous: "51.6",   forecast: "51.8",   actual: "52.0" },
  { id: "e3",  date: "2026-03-24", time: "10:00", name: "New Home Sales",            impact: "Medium", category: "Growth",     previous: "657K",   forecast: "680K",   actual: "674K" },
  { id: "e4",  date: "2026-03-25", time: "10:00", name: "Consumer Confidence",       impact: "High",   category: "Growth",     previous: "98.3",   forecast: "99.0",   actual: "100.1" },
  { id: "e5",  date: "2026-03-25", time: "10:00", name: "Richmond Fed Mfg Index",    impact: "Low",    category: "Growth",     previous: "-4",     forecast: "-2",     actual: "-1" },
  { id: "e6",  date: "2026-03-26", time: "08:30", name: "Durable Goods Orders",      impact: "Medium", category: "Growth",     previous: "3.2%",   forecast: "-1.0%",  actual: "" },
  { id: "e7",  date: "2026-03-26", time: "08:30", name: "Initial Jobless Claims",    impact: "High",   category: "Employment", previous: "223K",   forecast: "220K",   actual: "" },
  { id: "e8",  date: "2026-03-26", time: "10:00", name: "Pending Home Sales",        impact: "Medium", category: "Growth",     previous: "-4.6%",  forecast: "1.5%",   actual: "" },
  { id: "e9",  date: "2026-03-27", time: "08:30", name: "PCE Price Index",           impact: "High",   category: "Inflation",  previous: "2.5%",   forecast: "2.5%",   actual: "" },
  { id: "e10", date: "2026-03-27", time: "08:30", name: "Core PCE Price Index",      impact: "High",   category: "Inflation",  previous: "2.6%",   forecast: "2.7%",   actual: "" },
  { id: "e11", date: "2026-03-27", time: "08:30", name: "Personal Income",           impact: "Medium", category: "Growth",     previous: "0.9%",   forecast: "0.4%",   actual: "" },
  { id: "e12", date: "2026-03-27", time: "10:00", name: "Michigan Consumer Sent.",    impact: "Medium", category: "Growth",     previous: "57.9",   forecast: "57.9",   actual: "" },

  // Week of Mar 30 – Apr 3, 2026
  { id: "e13", date: "2026-03-30", time: "10:30", name: "Dallas Fed Mfg Index",      impact: "Low",    category: "Growth",     previous: "-8.3",   forecast: "-6.0",   actual: "" },
  { id: "e14", date: "2026-03-31", time: "09:00", name: "S&P/CS Home Price Index",   impact: "Low",    category: "Growth",     previous: "4.5%",   forecast: "4.7%",   actual: "" },
  { id: "e15", date: "2026-03-31", time: "10:00", name: "Consumer Confidence",       impact: "High",   category: "Growth",     previous: "100.1",  forecast: "99.5",   actual: "" },
  { id: "e16", date: "2026-04-01", time: "10:00", name: "ISM Manufacturing PMI",     impact: "High",   category: "Growth",     previous: "50.3",   forecast: "50.5",   actual: "" },
  { id: "e17", date: "2026-04-01", time: "10:00", name: "JOLTS Job Openings",        impact: "High",   category: "Employment", previous: "7.74M",  forecast: "7.70M",  actual: "" },
  { id: "e18", date: "2026-04-02", time: "08:15", name: "ADP Employment Change",     impact: "High",   category: "Employment", previous: "77K",    forecast: "120K",   actual: "" },
  { id: "e19", date: "2026-04-02", time: "08:30", name: "Initial Jobless Claims",    impact: "High",   category: "Employment", previous: "220K",   forecast: "218K",   actual: "" },
  { id: "e20", date: "2026-04-03", time: "10:00", name: "ISM Services PMI",          impact: "High",   category: "Growth",     previous: "53.5",   forecast: "53.0",   actual: "" },
  { id: "e21", date: "2026-04-03", time: "08:30", name: "Nonfarm Payrolls",          impact: "High",   category: "Employment", previous: "151K",   forecast: "140K",   actual: "" },
  { id: "e22", date: "2026-04-03", time: "08:30", name: "Unemployment Rate",         impact: "High",   category: "Employment", previous: "4.1%",   forecast: "4.1%",   actual: "" },

  // Week of Apr 6–10, 2026
  { id: "e23", date: "2026-04-07", time: "15:00", name: "Consumer Credit",           impact: "Low",    category: "Growth",     previous: "$18.1B", forecast: "$15.0B", actual: "" },
  { id: "e24", date: "2026-04-08", time: "06:00", name: "NFIB Small Business Index", impact: "Medium", category: "Growth",     previous: "100.7",  forecast: "101.0",  actual: "" },
  { id: "e25", date: "2026-04-09", time: "08:30", name: "Initial Jobless Claims",    impact: "High",   category: "Employment", previous: "218K",   forecast: "215K",   actual: "" },
  { id: "e26", date: "2026-04-09", time: "14:00", name: "FOMC Minutes",              impact: "High",   category: "Fed",        previous: "—",      forecast: "—",      actual: "" },
  { id: "e27", date: "2026-04-10", time: "08:30", name: "CPI (YoY)",                 impact: "High",   category: "Inflation",  previous: "2.8%",   forecast: "2.6%",   actual: "" },
  { id: "e28", date: "2026-04-10", time: "08:30", name: "Core CPI (YoY)",            impact: "High",   category: "Inflation",  previous: "3.1%",   forecast: "3.0%",   actual: "" },
  { id: "e29", date: "2026-04-10", time: "08:30", name: "PPI (MoM)",                 impact: "Medium", category: "Inflation",  previous: "0.0%",   forecast: "0.3%",   actual: "" },
];

const EARNINGS_EVENTS: EarningsEvent[] = [
  { id: "er1",  date: "2026-03-25", time: "AMC", ticker: "GME",  company: "GameStop",       epsEstimate: "-0.03", revenueEstimate: "$1.28B", epsActual: "0.01",  revenueActual: "$1.28B" },
  { id: "er2",  date: "2026-03-26", time: "BMO", ticker: "DRI",  company: "Darden Restaurants", epsEstimate: "2.80", revenueEstimate: "$3.17B", epsActual: "",     revenueActual: "" },
  { id: "er3",  date: "2026-03-27", time: "BMO", ticker: "LULU", company: "Lululemon",      epsEstimate: "5.85",  revenueEstimate: "$3.61B", epsActual: "",      revenueActual: "" },
  { id: "er4",  date: "2026-04-01", time: "AMC", ticker: "PVH",  company: "PVH Corp",       epsEstimate: "3.22",  revenueEstimate: "$2.37B", epsActual: "",      revenueActual: "" },
  { id: "er5",  date: "2026-04-23", time: "AMC", ticker: "TSLA", company: "Tesla",           epsEstimate: "0.45",  revenueEstimate: "$25.3B", epsActual: "",      revenueActual: "" },
  { id: "er6",  date: "2026-04-23", time: "AMC", ticker: "META", company: "Meta Platforms",  epsEstimate: "5.28",  revenueEstimate: "$41.2B", epsActual: "",      revenueActual: "" },
  { id: "er7",  date: "2026-04-24", time: "AMC", ticker: "MSFT", company: "Microsoft",       epsEstimate: "3.22",  revenueEstimate: "$68.4B", epsActual: "",      revenueActual: "" },
  { id: "er8",  date: "2026-04-24", time: "AMC", ticker: "GOOG", company: "Alphabet",        epsEstimate: "2.12",  revenueEstimate: "$89.1B", epsActual: "",      revenueActual: "" },
  { id: "er9",  date: "2026-04-30", time: "AMC", ticker: "AAPL", company: "Apple",           epsEstimate: "1.62",  revenueEstimate: "$94.5B", epsActual: "",      revenueActual: "" },
  { id: "er10", date: "2026-04-30", time: "AMC", ticker: "AMZN", company: "Amazon",          epsEstimate: "1.36",  revenueEstimate: "$155B",  epsActual: "",      revenueActual: "" },
  { id: "er11", date: "2026-05-01", time: "BMO", ticker: "NVDA", company: "NVIDIA",          epsEstimate: "0.89",  revenueEstimate: "$43.2B", epsActual: "",      revenueActual: "" },
  { id: "er12", date: "2026-04-15", time: "BMO", ticker: "JPM",  company: "JPMorgan Chase",  epsEstimate: "4.61",  revenueEstimate: "$44.2B", epsActual: "",      revenueActual: "" },
  { id: "er13", date: "2026-04-15", time: "BMO", ticker: "WFC",  company: "Wells Fargo",     epsEstimate: "1.24",  revenueEstimate: "$20.8B", epsActual: "",      revenueActual: "" },
  { id: "er14", date: "2026-04-16", time: "BMO", ticker: "UNH",  company: "UnitedHealth",    epsEstimate: "7.29",  revenueEstimate: "$111B",  epsActual: "",      revenueActual: "" },
  { id: "er15", date: "2026-04-17", time: "BMO", ticker: "NFLX", company: "Netflix",         epsEstimate: "5.71",  revenueEstimate: "$10.5B", epsActual: "",      revenueActual: "" },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

const TODAY = "2026-03-26";

const IMPACT_STYLES: Record<Impact, { dot: string; badge: string; border: string }> = {
  High:   { dot: "bg-red-500",    badge: "bg-red-500/15 text-red-400 border border-red-500/30",    border: "border-red-500/60" },
  Medium: { dot: "bg-yellow-500", badge: "bg-yellow-500/15 text-yellow-400 border border-yellow-500/30", border: "border-yellow-500/60" },
  Low:    { dot: "bg-blue-500",   badge: "bg-blue-500/15 text-blue-400 border border-blue-500/30", border: "border-blue-500/60" },
};

const CATEGORY_ICONS: Record<Category, typeof Calendar> = {
  Fed: AlertTriangle,
  Employment: Briefcase,
  Inflation: Flame,
  Growth: BarChart3,
  Earnings: DollarSign,
};

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function getMonday(dateStr: string): Date {
  const d = new Date(dateStr + "T12:00:00");
  const day = d.getDay();
  const diff = d.getDate() - day + (day === 0 ? -6 : 1);
  return new Date(d.getFullYear(), d.getMonth(), diff);
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

function fmt(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function fmtShort(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return `${MONTH_NAMES[d.getMonth()]} ${d.getDate()}`;
}

function fmtWeekday(dateStr: string): string {
  const d = new Date(dateStr + "T12:00:00");
  return DAY_NAMES[d.getDay()];
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function CalendarPage() {
  const [tab, setTab] = useState<"economic" | "earnings">("economic");
  const [weekOffset, setWeekOffset] = useState(0);
  const [impactFilter, setImpactFilter] = useState<Impact | "All">("All");
  const [categoryFilter, setCategoryFilter] = useState<Category | "All">("All");
  const [countdown, setCountdown] = useState({ d: 0, h: 0, m: 0, s: 0 });
  const [now, setNow] = useState(Date.now());

  // Live ticker
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  // Countdown to next high-impact event
  const nextHighEvent = useMemo(() => {
    const current = new Date();
    return ECON_EVENTS
      .filter((e) => e.impact === "High" && !e.actual)
      .map((e) => ({ ...e, ts: new Date(`${e.date}T${e.time}:00`).getTime() }))
      .filter((e) => e.ts > current.getTime())
      .sort((a, b) => a.ts - b.ts)[0] ?? null;
  }, [now]);

  useEffect(() => {
    if (!nextHighEvent) return;
    const diff = Math.max(0, nextHighEvent.ts - now);
    const s = Math.floor(diff / 1000);
    setCountdown({
      d: Math.floor(s / 86400),
      h: Math.floor((s % 86400) / 3600),
      m: Math.floor((s % 3600) / 60),
      s: s % 60,
    });
  }, [now, nextHighEvent]);

  // Week range
  const monday = useMemo(() => {
    const base = getMonday(TODAY);
    return addDays(base, weekOffset * 7);
  }, [weekOffset]);
  const friday = addDays(monday, 4);
  const weekDates = Array.from({ length: 5 }, (_, i) => fmt(addDays(monday, i)));

  // Filtered events
  const weekEvents = useMemo(() => {
    return ECON_EVENTS.filter((e) => {
      if (e.date < weekDates[0] || e.date > weekDates[4]) return false;
      if (impactFilter !== "All" && e.impact !== impactFilter) return false;
      if (categoryFilter !== "All" && categoryFilter !== "Earnings" && e.category !== categoryFilter) return false;
      return true;
    });
  }, [weekDates, impactFilter, categoryFilter]);

  const todayEvents = ECON_EVENTS.filter((e) => e.date === TODAY);
  const todayEarnings = EARNINGS_EVENTS.filter((e) => e.date === TODAY);

  // Earnings filtered by week
  const weekEarnings = useMemo(() => {
    return EARNINGS_EVENTS.filter((e) => e.date >= weekDates[0] && e.date <= weekDates[4]);
  }, [weekDates]);

  const pad = (n: number) => String(n).padStart(2, "0");

  const ImpactBadge = ({ impact }: { impact: Impact }) => (
    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${IMPACT_STYLES[impact].badge}`}>
      {impact}
    </span>
  );

  const CategoryIcon = ({ category }: { category: Category }) => {
    const Icon = CATEGORY_ICONS[category] ?? BarChart3;
    return <Icon className="w-3.5 h-3.5 text-text-tertiary" />;
  };

  return (
    <div className="min-h-screen bg-[#080808] text-white px-6 py-8 max-w-[1400px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-heading text-2xl font-bold flex items-center gap-3">
            <Calendar className="w-6 h-6 text-cyan-400" />
            Economic Calendar
          </h1>
          <p className="text-text-tertiary text-sm mt-1">
            Market-moving events & earnings — week of {fmtShort(fmt(monday))} to {fmtShort(fmt(friday))}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-text-tertiary" />
          <span className="font-mono text-xs text-text-tertiary">
            {new Date(now).toLocaleTimeString("en-US", { hour12: true, hour: "2-digit", minute: "2-digit", second: "2-digit" })} ET
          </span>
        </div>
      </div>

      {/* Countdown + Today Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
        {/* Countdown */}
        <Card className="lg:col-span-1">
          <div className="text-text-tertiary text-xs uppercase tracking-wider mb-2 flex items-center gap-2">
            <Zap className="w-3.5 h-3.5 text-red-400" />
            Next High-Impact Event
          </div>
          {nextHighEvent ? (
            <>
              <div className="font-mono text-3xl font-bold text-cyan-400 mb-2">
                {pad(countdown.d)}<span className="text-text-tertiary text-lg">d </span>
                {pad(countdown.h)}<span className="text-text-tertiary text-lg">h </span>
                {pad(countdown.m)}<span className="text-text-tertiary text-lg">m </span>
                {pad(countdown.s)}<span className="text-text-tertiary text-lg">s</span>
              </div>
              <div className="flex items-center gap-2">
                <ImpactBadge impact="High" />
                <span className="text-sm font-medium">{nextHighEvent.name}</span>
              </div>
              <p className="text-text-tertiary text-xs mt-1 font-mono">
                {fmtWeekday(nextHighEvent.date)}, {fmtShort(nextHighEvent.date)} at {nextHighEvent.time} ET
              </p>
            </>
          ) : (
            <p className="text-text-tertiary text-sm">No upcoming high-impact events</p>
          )}
        </Card>

        {/* Today's Events */}
        <Card className="lg:col-span-2">
          <div className="text-text-tertiary text-xs uppercase tracking-wider mb-3 flex items-center gap-2">
            <Target className="w-3.5 h-3.5 text-cyan-400" />
            Today&apos;s Events — {fmtShort(TODAY)}
          </div>
          {todayEvents.length === 0 && todayEarnings.length === 0 ? (
            <p className="text-text-tertiary text-sm">No events today</p>
          ) : (
            <div className="space-y-2">
              {todayEvents.map((ev) => (
                <div key={ev.id} className={`flex items-center gap-3 px-3 py-2 rounded-lg bg-white/[0.02] border-l-2 ${IMPACT_STYLES[ev.impact].border}`}>
                  <span className="font-mono text-xs text-text-tertiary w-12">{ev.time}</span>
                  <CategoryIcon category={ev.category} />
                  <span className="text-sm font-medium flex-1">{ev.name}</span>
                  <ImpactBadge impact={ev.impact} />
                  <span className="font-mono text-xs text-text-tertiary w-16 text-right">F: {ev.forecast}</span>
                  {ev.actual ? (
                    <span className="font-mono text-xs text-cyan-400 w-16 text-right">A: {ev.actual}</span>
                  ) : (
                    <span className="font-mono text-xs text-text-tertiary/40 w-16 text-right">Pending</span>
                  )}
                </div>
              ))}
              {todayEarnings.map((er) => (
                <div key={er.id} className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/[0.02] border-l-2 border-purple-500/60">
                  <span className="font-mono text-xs text-text-tertiary w-12">{er.time}</span>
                  <DollarSign className="w-3.5 h-3.5 text-purple-400" />
                  <span className="text-sm font-bold text-purple-300 w-14">{er.ticker}</span>
                  <span className="text-sm text-text-secondary flex-1">{er.company}</span>
                  <span className="font-mono text-xs text-text-tertiary">EPS: {er.epsEstimate}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Tabs + Filters */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-4">
        {/* Tabs */}
        <div className="flex gap-1 bg-[#0d0d0d] border border-[#1a1a1a] rounded-lg p-1">
          {(["economic", "earnings"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                tab === t ? "bg-white/10 text-white" : "text-text-tertiary hover:text-white"
              }`}
            >
              {t === "economic" ? "Economic" : "Earnings"}
            </button>
          ))}
        </div>

        {/* Filters + Week Nav */}
        <div className="flex items-center gap-3 flex-wrap">
          {tab === "economic" && (
            <>
              <div className="flex items-center gap-1.5">
                <Filter className="w-3.5 h-3.5 text-text-tertiary" />
                {(["All", "High", "Medium", "Low"] as const).map((level) => (
                  <button
                    key={level}
                    onClick={() => setImpactFilter(level)}
                    className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                      impactFilter === level
                        ? level === "All"
                          ? "bg-white/10 text-white"
                          : IMPACT_STYLES[level as Impact].badge
                        : "text-text-tertiary hover:text-white"
                    }`}
                  >
                    {level}
                  </button>
                ))}
              </div>
              <div className="w-px h-5 bg-[#1a1a1a]" />
              <div className="flex items-center gap-1.5">
                {(["All", "Fed", "Employment", "Inflation", "Growth"] as const).map((cat) => (
                  <button
                    key={cat}
                    onClick={() => setCategoryFilter(cat)}
                    className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                      categoryFilter === cat ? "bg-white/10 text-white" : "text-text-tertiary hover:text-white"
                    }`}
                  >
                    {cat}
                  </button>
                ))}
              </div>
            </>
          )}
          <div className="w-px h-5 bg-[#1a1a1a]" />
          <div className="flex items-center gap-1">
            <button onClick={() => setWeekOffset((w) => w - 1)} className="p-1.5 rounded hover:bg-white/5 text-text-tertiary hover:text-white transition-colors">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setWeekOffset(0)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${weekOffset === 0 ? "bg-cyan-500/15 text-cyan-400" : "text-text-tertiary hover:text-white"}`}
            >
              This Week
            </button>
            <button onClick={() => setWeekOffset((w) => w + 1)} className="p-1.5 rounded hover:bg-white/5 text-text-tertiary hover:text-white transition-colors">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Visual Timeline */}
      <Card className="mb-6" padding="sm">
        <div className="grid grid-cols-5 gap-px">
          {weekDates.map((date) => {
            const isToday = date === TODAY;
            const dayEvents = tab === "economic"
              ? weekEvents.filter((e) => e.date === date)
              : weekEarnings.filter((e) => e.date === date);
            return (
              <div key={date} className={`px-3 py-2.5 rounded-lg ${isToday ? "bg-cyan-500/5 ring-1 ring-cyan-500/20" : "bg-white/[0.01]"}`}>
                <div className="flex items-center justify-between mb-2">
                  <span className={`text-xs font-medium ${isToday ? "text-cyan-400" : "text-text-tertiary"}`}>
                    {fmtWeekday(date)}
                  </span>
                  <span className={`text-xs font-mono ${isToday ? "text-cyan-400" : "text-text-tertiary"}`}>
                    {fmtShort(date)}
                  </span>
                </div>
                <div className="space-y-1">
                  {dayEvents.length === 0 && (
                    <span className="text-[10px] text-text-tertiary/30">No events</span>
                  )}
                  {dayEvents.slice(0, 4).map((ev) => (
                    <div key={ev.id} className="flex items-center gap-1.5">
                      <div className={`w-1.5 h-1.5 rounded-full ${
                        tab === "economic"
                          ? IMPACT_STYLES[(ev as EconEvent).impact].dot
                          : "bg-purple-500"
                      }`} />
                      <span className="text-[10px] text-text-secondary truncate">
                        {tab === "economic" ? (ev as EconEvent).name : (ev as EarningsEvent).ticker}
                      </span>
                    </div>
                  ))}
                  {dayEvents.length > 4 && (
                    <span className="text-[10px] text-text-tertiary">+{dayEvents.length - 4} more</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Main Content */}
      {tab === "economic" ? (
        <Card padding="none">
          {/* Table Header */}
          <div className="grid grid-cols-[80px_1fr_80px_100px_80px_80px_80px] gap-2 px-4 py-3 border-b border-[#1a1a1a] text-[10px] text-text-tertiary uppercase tracking-wider font-semibold">
            <span>Time (ET)</span>
            <span>Event</span>
            <span>Impact</span>
            <span>Category</span>
            <span className="text-right">Previous</span>
            <span className="text-right">Forecast</span>
            <span className="text-right">Actual</span>
          </div>
          {/* Grouped by day */}
          {weekDates.map((date) => {
            const dayEvs = weekEvents.filter((e) => e.date === date);
            if (dayEvs.length === 0) return null;
            const isToday = date === TODAY;
            return (
              <div key={date}>
                <div className={`px-4 py-2 text-xs font-semibold border-b border-[#1a1a1a] flex items-center gap-2 ${
                  isToday ? "bg-cyan-500/5 text-cyan-400" : "bg-white/[0.02] text-text-tertiary"
                }`}>
                  <Calendar className="w-3 h-3" />
                  {fmtWeekday(date)}, {fmtShort(date)}
                  {isToday && <span className="px-1.5 py-0.5 rounded bg-cyan-500/20 text-[9px] uppercase tracking-wider">Today</span>}
                </div>
                {dayEvs.map((ev) => (
                  <div
                    key={ev.id}
                    className={`grid grid-cols-[80px_1fr_80px_100px_80px_80px_80px] gap-2 px-4 py-2.5 border-b border-[#1a1a1a]/50 border-l-2 ${IMPACT_STYLES[ev.impact].border} hover:bg-white/[0.02] transition-colors`}
                  >
                    <span className="font-mono text-xs text-text-tertiary">{ev.time}</span>
                    <div className="flex items-center gap-2">
                      <CategoryIcon category={ev.category} />
                      <span className="text-sm font-medium">{ev.name}</span>
                    </div>
                    <div><ImpactBadge impact={ev.impact} /></div>
                    <span className="text-xs text-text-tertiary flex items-center gap-1.5">
                      <CategoryIcon category={ev.category} />
                      {ev.category}
                    </span>
                    <span className="font-mono text-xs text-text-tertiary text-right">{ev.previous}</span>
                    <span className="font-mono text-xs text-yellow-400/80 text-right">{ev.forecast}</span>
                    <span className={`font-mono text-xs text-right ${ev.actual ? "text-cyan-400 font-semibold" : "text-text-tertiary/30"}`}>
                      {ev.actual || "—"}
                    </span>
                  </div>
                ))}
              </div>
            );
          })}
          {weekEvents.length === 0 && (
            <div className="px-4 py-12 text-center text-text-tertiary text-sm">
              No events match your filters for this week.
            </div>
          )}
        </Card>
      ) : (
        /* Earnings Tab */
        <Card padding="none">
          <div className="grid grid-cols-[80px_80px_1fr_100px_110px_100px_110px] gap-2 px-4 py-3 border-b border-[#1a1a1a] text-[10px] text-text-tertiary uppercase tracking-wider font-semibold">
            <span>Date</span>
            <span>Time</span>
            <span>Company</span>
            <span className="text-right">EPS Est.</span>
            <span className="text-right">Rev. Est.</span>
            <span className="text-right">EPS Act.</span>
            <span className="text-right">Rev. Act.</span>
          </div>
          {weekEarnings.length === 0 ? (
            <div className="px-4 py-12 text-center text-text-tertiary text-sm">
              No earnings this week. Try navigating to a different week.
            </div>
          ) : (
            weekEarnings
              .sort((a, b) => a.date.localeCompare(b.date))
              .map((er) => (
                <div
                  key={er.id}
                  className="grid grid-cols-[80px_80px_1fr_100px_110px_100px_110px] gap-2 px-4 py-2.5 border-b border-[#1a1a1a]/50 border-l-2 border-purple-500/60 hover:bg-white/[0.02] transition-colors"
                >
                  <span className="font-mono text-xs text-text-tertiary">{fmtShort(er.date)}</span>
                  <span className={`text-xs font-semibold ${er.time === "BMO" ? "text-yellow-400" : er.time === "AMC" ? "text-blue-400" : "text-text-tertiary"}`}>
                    {er.time === "BMO" ? "Pre-Mkt" : er.time === "AMC" ? "After-Mkt" : "Intraday"}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-purple-300">{er.ticker}</span>
                    <span className="text-sm text-text-secondary">{er.company}</span>
                  </div>
                  <span className="font-mono text-xs text-text-tertiary text-right">${er.epsEstimate}</span>
                  <span className="font-mono text-xs text-text-tertiary text-right">{er.revenueEstimate}</span>
                  <span className={`font-mono text-xs text-right ${er.epsActual ? "text-cyan-400 font-semibold" : "text-text-tertiary/30"}`}>
                    {er.epsActual ? `$${er.epsActual}` : "—"}
                  </span>
                  <span className={`font-mono text-xs text-right ${er.revenueActual ? "text-cyan-400 font-semibold" : "text-text-tertiary/30"}`}>
                    {er.revenueActual || "—"}
                  </span>
                </div>
              ))
          )}
        </Card>
      )}

      {/* Footer legend */}
      <div className="flex items-center gap-6 mt-4 text-[10px] text-text-tertiary">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-red-500" /> High Impact
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-yellow-500" /> Medium Impact
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-blue-500" /> Low Impact
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-purple-500" /> Earnings
        </div>
        <span className="ml-auto">All times Eastern (ET) | Data refreshes automatically</span>
      </div>
    </div>
  );
}
