"use client";

import { Card } from "@/components/ui/Card";
import { PriceDisplay } from "@/components/ui/PriceDisplay";
import { Users, Trophy, TrendingUp, Copy, Star, Shield } from "lucide-react";

const MOCK_LEADERS = [
  { rank: 1, name: "QuantAlpha", return_pct: 47.2, sharpe: 3.1, dd: 8.2, followers: 1243, strategy: "Momentum + ICT" },
  { rank: 2, name: "MacroHunter", return_pct: 38.9, sharpe: 2.8, dd: 11.5, followers: 891, strategy: "Macro Regime" },
  { rank: 3, name: "StructureTrader", return_pct: 32.1, sharpe: 2.5, dd: 9.8, followers: 654, strategy: "Wyckoff" },
  { rank: 4, name: "FlowReader", return_pct: 28.7, sharpe: 2.2, dd: 13.1, followers: 432, strategy: "Options Flow" },
  { rank: 5, name: "TrendFollower", return_pct: 24.3, sharpe: 2.0, dd: 14.2, followers: 321, strategy: "Trend + EW" },
];

export default function CopyPage() {
  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-7xl mx-auto">
      <header>
        <div className="flex items-center gap-3 mb-1">
          <Users size={20} className="text-yellow-500" />
          <h1 className="font-heading text-2xl font-bold">Copy</h1>
        </div>
        <p className="text-text-secondary text-sm">
          Strategy leaderboard and one-click copy trading from verified performers
        </p>
      </header>

      {/* Leaderboard */}
      <section>
        <div className="flex items-center gap-2 mb-4">
          <Trophy size={16} className="text-yellow-500" />
          <h2 className="font-heading text-lg font-semibold">Leaderboard</h2>
        </div>
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-tertiary text-xs border-b border-border">
                  <th className="text-center py-2 pr-3 w-10">#</th>
                  <th className="text-left py-2 pr-4">Trader</th>
                  <th className="text-left py-2 pr-4">Strategy</th>
                  <th className="text-right py-2 pr-4">Return</th>
                  <th className="text-right py-2 pr-4">Sharpe</th>
                  <th className="text-right py-2 pr-4">Max DD</th>
                  <th className="text-right py-2 pr-4">Followers</th>
                  <th className="text-center py-2">Action</th>
                </tr>
              </thead>
              <tbody>
                {MOCK_LEADERS.map((leader) => (
                  <tr key={leader.rank} className="border-b border-border-subtle hover:bg-bg-elevated">
                    <td className="py-3 pr-3 text-center">
                      {leader.rank <= 3 ? (
                        <span className="text-yellow-500 font-bold">{leader.rank}</span>
                      ) : (
                        <span className="text-text-tertiary">{leader.rank}</span>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-accent flex items-center justify-center text-xs font-mono">
                          {leader.name[0]}
                        </div>
                        <span className="font-medium text-sm">{leader.name}</span>
                      </div>
                    </td>
                    <td className="py-3 pr-4 text-text-secondary text-xs">{leader.strategy}</td>
                    <td className="py-3 pr-4 text-right">
                      <span className="text-profit font-mono text-xs font-semibold">
                        +{leader.return_pct}%
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-xs">{leader.sharpe}</td>
                    <td className="py-3 pr-4 text-right font-mono text-xs text-loss">
                      {leader.dd}%
                    </td>
                    <td className="py-3 pr-4 text-right font-mono text-xs text-text-secondary">
                      {leader.followers.toLocaleString()}
                    </td>
                    <td className="py-3 text-center">
                      <button className="px-3 py-1.5 bg-accent hover:bg-accent-hover rounded text-xs font-medium transition-colors flex items-center gap-1 mx-auto">
                        <Copy size={12} />
                        Copy
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </section>

      {/* How it works */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">How Copy Trading Works</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { step: "1", title: "Browse Strategies", desc: "Filter by return, risk, methodology, and time horizon" },
            { step: "2", title: "Allocate Capital", desc: "Set your copy amount and risk limits independently" },
            { step: "3", title: "Auto-Mirror", desc: "Trades execute proportionally in your account with your stops" },
          ].map((item) => (
            <Card key={item.step}>
              <div className="flex items-start gap-3">
                <span className="w-7 h-7 rounded-full bg-yellow-500/10 text-yellow-500 flex items-center justify-center text-xs font-bold flex-shrink-0">
                  {item.step}
                </span>
                <div>
                  <h3 className="font-heading font-semibold text-sm">{item.title}</h3>
                  <p className="text-text-secondary text-xs mt-1">{item.desc}</p>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
