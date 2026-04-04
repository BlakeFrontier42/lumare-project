"use client";

import { useEffect, useState, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { API_BASE, apiFetch, setUserPreference } from "@/lib/api";
import {
  User,
  CandlestickChart,
  Key,
  Bell,
  Palette,
  ShieldAlert,
  Database,
  Eye,
  EyeOff,
  Save,
  Check,
  Loader2,
  Trash2,
  Download,
  AlertTriangle,
  X,
  Volume2,
  VolumeX,
  Monitor,
  Type,
  Minus,
  Plus,
} from "lucide-react";
import { clsx } from "clsx";

// ─── Types ────────────────────────────────────────────────

type TabId =
  | "profile"
  | "trading"
  | "api-keys"
  | "notifications"
  | "appearance"
  | "risk"
  | "data-privacy";

interface TabDef {
  id: TabId;
  label: string;
  icon: React.ElementType;
}

const TABS: TabDef[] = [
  { id: "profile", label: "Profile", icon: User },
  { id: "trading", label: "Trading", icon: CandlestickChart },
  { id: "api-keys", label: "API Keys", icon: Key },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "risk", label: "Risk Management", icon: ShieldAlert },
  { id: "data-privacy", label: "Data & Privacy", icon: Database },
];

const TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Anchorage",
  "America/Honolulu",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Tokyo",
  "Asia/Shanghai",
  "Asia/Singapore",
  "Asia/Kolkata",
  "Australia/Sydney",
  "Pacific/Auckland",
  "UTC",
];

// ─── Shared helpers ───────────────────────────────────────

function useSavePref() {
  const [saving, setSaving] = useState<Record<string, boolean>>({});
  const [saved, setSaved] = useState<Record<string, boolean>>({});

  const save = useCallback(async (key: string, value: unknown) => {
    setSaving((s) => ({ ...s, [key]: true }));
    await setUserPreference(key, value);
    setSaving((s) => ({ ...s, [key]: false }));
    setSaved((s) => ({ ...s, [key]: true }));
    setTimeout(() => setSaved((s) => ({ ...s, [key]: false })), 2000);
  }, []);

  return { saving, saved, save };
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-sm font-mono text-text-tertiary uppercase tracking-wider mb-4">
      {children}
    </h3>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-sm text-text-secondary mb-1.5">
      {children}
    </label>
  );
}

function TextInput({
  value,
  onChange,
  placeholder,
  type = "text",
  className,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  className?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={clsx(
        "w-full bg-bg-elevated border border-border rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-blue-500/50 transition-colors",
        className
      )}
    />
  );
}

function Toggle({
  enabled,
  onChange,
  label,
  description,
}: {
  enabled: boolean;
  onChange: (v: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <p className="text-sm text-text-primary">{label}</p>
        {description && (
          <p className="text-xs text-text-tertiary mt-0.5">{description}</p>
        )}
      </div>
      <button
        onClick={() => onChange(!enabled)}
        className={clsx(
          "relative w-11 h-6 rounded-full transition-colors duration-200",
          enabled ? "bg-blue-500" : "bg-bg-elevated border border-border"
        )}
      >
        <span
          className={clsx(
            "absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform duration-200",
            enabled ? "translate-x-[22px]" : "translate-x-0.5"
          )}
        />
      </button>
    </div>
  );
}

function SaveButton({
  onClick,
  saving,
  saved,
  className,
}: {
  onClick: () => void;
  saving: boolean;
  saved: boolean;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={saving}
      className={clsx(
        "flex items-center gap-2 px-4 py-2 rounded-button text-sm font-medium transition-colors",
        saved
          ? "bg-profit/20 text-profit"
          : "bg-blue-500/20 text-blue-400 hover:bg-blue-500/30",
        className
      )}
    >
      {saving ? (
        <Loader2 size={14} className="animate-spin" />
      ) : saved ? (
        <Check size={14} />
      ) : (
        <Save size={14} />
      )}
      {saving ? "Saving..." : saved ? "Saved" : "Save"}
    </button>
  );
}

// ─── Confirmation Modal ───────────────────────────────────

function ConfirmModal({
  open,
  title,
  message,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-bg-card border border-border rounded-card p-6 max-w-md w-full mx-4">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 rounded-full bg-loss/10">
            <AlertTriangle size={20} className="text-loss" />
          </div>
          <h3 className="text-lg font-heading font-semibold text-text-primary">
            {title}
          </h3>
        </div>
        <p className="text-sm text-text-secondary mb-6">{message}</p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-button text-sm text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 rounded-button text-sm bg-loss/20 text-loss hover:bg-loss/30 transition-colors font-medium"
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Tab: Profile ─────────────────────────────────────────

function ProfileTab() {
  const { saving, saved, save } = useSavePref();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [initials, setInitials] = useState("BL");
  const [timezone, setTimezone] = useState("America/New_York");

  useEffect(() => {
    apiFetch<{ preferences: Record<string, unknown> }>(
      "/api/orchestrator/memory/preferences"
    ).then((data) => {
      if (!data?.preferences) return;
      const p = data.preferences;
      if (typeof p.display_name === "string") setDisplayName(p.display_name);
      if (typeof p.email === "string") setEmail(p.email);
      if (typeof p.avatar_initials === "string") setInitials(p.avatar_initials);
      if (typeof p.timezone === "string") setTimezone(p.timezone);
    });
  }, []);

  const handleSave = async () => {
    await save("display_name", displayName);
    await save("email", email);
    await save("avatar_initials", initials);
    await save("timezone", timezone);
  };

  return (
    <div className="space-y-6">
      <SectionTitle>User Profile</SectionTitle>

      {/* Avatar */}
      <div className="flex items-center gap-4 mb-6">
        <div className="w-16 h-16 rounded-full bg-blue-500/20 border border-blue-500/30 flex items-center justify-center text-blue-400 text-xl font-heading font-bold">
          {initials || "?"}
        </div>
        <div>
          <p className="text-text-primary font-medium">
            {displayName || "User"}
          </p>
          <p className="text-xs text-text-tertiary">{email || "No email set"}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <FieldLabel>Display Name</FieldLabel>
          <TextInput
            value={displayName}
            onChange={setDisplayName}
            placeholder="Your name"
          />
        </div>
        <div>
          <FieldLabel>Email</FieldLabel>
          <TextInput
            value={email}
            onChange={setEmail}
            placeholder="you@example.com"
            type="email"
          />
        </div>
        <div>
          <FieldLabel>Avatar Initials</FieldLabel>
          <TextInput
            value={initials}
            onChange={(v) => setInitials(v.toUpperCase().slice(0, 2))}
            placeholder="BL"
            className="w-24"
          />
        </div>
        <div>
          <FieldLabel>Timezone</FieldLabel>
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded-button px-3 py-2 text-sm text-text-primary focus:outline-none focus:border-blue-500/50 transition-colors"
          >
            {TIMEZONES.map((tz) => (
              <option key={tz} value={tz}>
                {tz.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
      </div>

      <SaveButton
        onClick={handleSave}
        saving={!!saving["timezone"]}
        saved={!!saved["timezone"]}
      />
    </div>
  );
}

// ─── Tab: Trading ─────────────────────────────────────────

function TradingTab() {
  const { saving, saved, save } = useSavePref();
  const [orderSize, setOrderSize] = useState("1000");
  const [slPct, setSlPct] = useState("2");
  const [tpPct, setTpPct] = useState("4");
  const [maxPosition, setMaxPosition] = useState("10000");
  const [paperMode, setPaperMode] = useState(true);
  const [watchlist, setWatchlist] = useState("SPY,QQQ,AAPL,BTCUSDT,ETHUSDT");

  useEffect(() => {
    apiFetch<{ preferences: Record<string, unknown> }>(
      "/api/orchestrator/memory/preferences"
    ).then((data) => {
      if (!data?.preferences) return;
      const p = data.preferences;
      if (p.default_order_size != null) setOrderSize(String(p.default_order_size));
      if (p.default_sl_pct != null) setSlPct(String(p.default_sl_pct));
      if (p.default_tp_pct != null) setTpPct(String(p.default_tp_pct));
      if (p.max_position_size != null) setMaxPosition(String(p.max_position_size));
      if (typeof p.paper_mode === "boolean") setPaperMode(p.paper_mode);
      if (typeof p.watchlist === "string") setWatchlist(p.watchlist);
    });
  }, []);

  const handleSave = async () => {
    await save("default_order_size", Number(orderSize));
    await save("default_sl_pct", Number(slPct));
    await save("default_tp_pct", Number(tpPct));
    await save("max_position_size", Number(maxPosition));
    await save("paper_mode", paperMode);
    await save("watchlist", watchlist);
  };

  return (
    <div className="space-y-6">
      <SectionTitle>Trading Defaults</SectionTitle>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <FieldLabel>Default Order Size ($)</FieldLabel>
          <TextInput
            value={orderSize}
            onChange={setOrderSize}
            placeholder="1000"
            type="number"
          />
        </div>
        <div>
          <FieldLabel>Max Position Size ($)</FieldLabel>
          <TextInput
            value={maxPosition}
            onChange={setMaxPosition}
            placeholder="10000"
            type="number"
          />
        </div>
        <div>
          <FieldLabel>Default Stop Loss (%)</FieldLabel>
          <TextInput
            value={slPct}
            onChange={setSlPct}
            placeholder="2"
            type="number"
          />
        </div>
        <div>
          <FieldLabel>Default Take Profit (%)</FieldLabel>
          <TextInput
            value={tpPct}
            onChange={setTpPct}
            placeholder="4"
            type="number"
          />
        </div>
      </div>

      <div className="border-t border-border pt-4">
        <FieldLabel>Preferred Watchlist Symbols</FieldLabel>
        <TextInput
          value={watchlist}
          onChange={setWatchlist}
          placeholder="SPY,QQQ,AAPL,BTCUSDT"
        />
        <p className="text-xs text-text-tertiary mt-1">
          Comma-separated list of symbols
        </p>
      </div>

      <div className="border-t border-border pt-4">
        <Toggle
          enabled={paperMode}
          onChange={setPaperMode}
          label="Paper Trading Mode"
          description="Execute trades in simulation mode with virtual capital"
        />
        {!paperMode && (
          <div className="flex items-center gap-2 mt-2 px-3 py-2 bg-loss/10 border border-loss/20 rounded-button">
            <AlertTriangle size={14} className="text-loss shrink-0" />
            <p className="text-xs text-loss">
              Live trading is active. Real capital will be used for order
              execution.
            </p>
          </div>
        )}
      </div>

      <SaveButton
        onClick={handleSave}
        saving={!!saving["watchlist"]}
        saved={!!saved["watchlist"]}
      />
    </div>
  );
}

// ─── Tab: API Keys ────────────────────────────────────────

interface ApiKeyField {
  key: string;
  label: string;
  placeholder: string;
}

const API_KEY_FIELDS: ApiKeyField[] = [
  {
    key: "api_key_polygon",
    label: "Polygon.io API Key",
    placeholder: "Enter Polygon API key",
  },
  {
    key: "api_key_perplexity",
    label: "Perplexity API Key",
    placeholder: "Enter Perplexity API key",
  },
  {
    key: "api_key_anthropic",
    label: "Anthropic API Key",
    placeholder: "Enter Anthropic API key",
  },
  {
    key: "api_key_alpha_vantage",
    label: "Alpha Vantage API Key",
    placeholder: "Enter Alpha Vantage API key",
  },
];

function ApiKeysTab() {
  const { saving, saved, save } = useSavePref();
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});

  useEffect(() => {
    apiFetch<{ preferences: Record<string, unknown> }>(
      "/api/orchestrator/memory/preferences"
    ).then((data) => {
      if (!data?.preferences) return;
      const loaded: Record<string, string> = {};
      for (const field of API_KEY_FIELDS) {
        const val = data.preferences[field.key];
        if (typeof val === "string") loaded[field.key] = val;
      }
      setKeys(loaded);
    });
  }, []);

  return (
    <div className="space-y-6">
      <SectionTitle>API Keys</SectionTitle>
      <p className="text-xs text-text-tertiary -mt-2 mb-4">
        Keys are stored server-side and used for data feeds and AI services.
      </p>

      <div className="space-y-5">
        {API_KEY_FIELDS.map((field) => (
          <div key={field.key}>
            <FieldLabel>{field.label}</FieldLabel>
            <div className="flex gap-2">
              <div className="relative flex-1">
                <input
                  type={visible[field.key] ? "text" : "password"}
                  value={keys[field.key] || ""}
                  onChange={(e) =>
                    setKeys((k) => ({ ...k, [field.key]: e.target.value }))
                  }
                  placeholder={field.placeholder}
                  className="w-full bg-bg-elevated border border-border rounded-button px-3 py-2 pr-10 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-blue-500/50 transition-colors font-mono"
                />
                <button
                  onClick={() =>
                    setVisible((v) => ({
                      ...v,
                      [field.key]: !v[field.key],
                    }))
                  }
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-secondary transition-colors"
                >
                  {visible[field.key] ? (
                    <EyeOff size={16} />
                  ) : (
                    <Eye size={16} />
                  )}
                </button>
              </div>
              <SaveButton
                onClick={() => save(field.key, keys[field.key] || "")}
                saving={!!saving[field.key]}
                saved={!!saved[field.key]}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Tab: Notifications ───────────────────────────────────

function NotificationsTab() {
  const { saving, saved, save } = useSavePref();
  const [signalAlerts, setSignalAlerts] = useState(true);
  const [slTpHits, setSlTpHits] = useState(true);
  const [priceAlerts, setPriceAlerts] = useState(true);
  const [systemNotifs, setSystemNotifs] = useState(true);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [desktopPermission, setDesktopPermission] = useState<
    "default" | "granted" | "denied"
  >("default");

  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setDesktopPermission(
        Notification.permission as "default" | "granted" | "denied"
      );
    }

    apiFetch<{ preferences: Record<string, unknown> }>(
      "/api/orchestrator/memory/preferences"
    ).then((data) => {
      if (!data?.preferences) return;
      const p = data.preferences;
      if (typeof p.notif_signal_alerts === "boolean")
        setSignalAlerts(p.notif_signal_alerts);
      if (typeof p.notif_sl_tp_hits === "boolean")
        setSlTpHits(p.notif_sl_tp_hits);
      if (typeof p.notif_price_alerts === "boolean")
        setPriceAlerts(p.notif_price_alerts);
      if (typeof p.notif_system === "boolean")
        setSystemNotifs(p.notif_system);
      if (typeof p.notif_sound === "boolean")
        setSoundEnabled(p.notif_sound);
    });
  }, []);

  const requestDesktopPermission = async () => {
    if (typeof window !== "undefined" && "Notification" in window) {
      const result = await Notification.requestPermission();
      setDesktopPermission(result as "default" | "granted" | "denied");
    }
  };

  const handleSave = async () => {
    await save("notif_signal_alerts", signalAlerts);
    await save("notif_sl_tp_hits", slTpHits);
    await save("notif_price_alerts", priceAlerts);
    await save("notif_system", systemNotifs);
    await save("notif_sound", soundEnabled);
  };

  return (
    <div className="space-y-6">
      <SectionTitle>Notification Preferences</SectionTitle>

      <div className="space-y-1">
        <Toggle
          enabled={signalAlerts}
          onChange={setSignalAlerts}
          label="Signal Alerts"
          description="Get notified when new trading signals fire"
        />
        <Toggle
          enabled={slTpHits}
          onChange={setSlTpHits}
          label="SL/TP Hits"
          description="Alerts when stop-loss or take-profit levels are triggered"
        />
        <Toggle
          enabled={priceAlerts}
          onChange={setPriceAlerts}
          label="Price Alerts"
          description="Custom price level notifications"
        />
        <Toggle
          enabled={systemNotifs}
          onChange={setSystemNotifs}
          label="System Notifications"
          description="Platform updates, maintenance, and status changes"
        />
      </div>

      <div className="border-t border-border pt-4 space-y-3">
        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-3">
            {soundEnabled ? (
              <Volume2 size={18} className="text-text-secondary" />
            ) : (
              <VolumeX size={18} className="text-text-tertiary" />
            )}
            <div>
              <p className="text-sm text-text-primary">Sound Effects</p>
              <p className="text-xs text-text-tertiary">
                Play audio on notifications
              </p>
            </div>
          </div>
          <button
            onClick={() => setSoundEnabled(!soundEnabled)}
            className={clsx(
              "relative w-11 h-6 rounded-full transition-colors duration-200",
              soundEnabled
                ? "bg-blue-500"
                : "bg-bg-elevated border border-border"
            )}
          >
            <span
              className={clsx(
                "absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform duration-200",
                soundEnabled ? "translate-x-[22px]" : "translate-x-0.5"
              )}
            />
          </button>
        </div>

        <div className="flex items-center justify-between py-2">
          <div className="flex items-center gap-3">
            <Monitor size={18} className="text-text-secondary" />
            <div>
              <p className="text-sm text-text-primary">Desktop Notifications</p>
              <p className="text-xs text-text-tertiary">
                {desktopPermission === "granted"
                  ? "Enabled"
                  : desktopPermission === "denied"
                  ? "Blocked by browser"
                  : "Not yet requested"}
              </p>
            </div>
          </div>
          {desktopPermission !== "granted" && (
            <button
              onClick={requestDesktopPermission}
              disabled={desktopPermission === "denied"}
              className="px-3 py-1.5 rounded-button text-xs bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {desktopPermission === "denied" ? "Blocked" : "Enable"}
            </button>
          )}
          {desktopPermission === "granted" && (
            <div className="flex items-center gap-1.5 text-profit text-xs">
              <Check size={14} />
              Enabled
            </div>
          )}
        </div>
      </div>

      <SaveButton
        onClick={handleSave}
        saving={!!saving["notif_sound"]}
        saved={!!saved["notif_sound"]}
      />
    </div>
  );
}

// ─── Tab: Appearance ──────────────────────────────────────

function AppearanceTab() {
  const { saving, saved, save } = useSavePref();
  const [fontSize, setFontSize] = useState(14);
  const [compactMode, setCompactMode] = useState(false);

  useEffect(() => {
    apiFetch<{ preferences: Record<string, unknown> }>(
      "/api/orchestrator/memory/preferences"
    ).then((data) => {
      if (!data?.preferences) return;
      const p = data.preferences;
      if (typeof p.font_size === "number") setFontSize(p.font_size);
      if (typeof p.compact_mode === "boolean") setCompactMode(p.compact_mode);
    });
  }, []);

  const handleSave = async () => {
    await save("font_size", fontSize);
    await save("compact_mode", compactMode);
    await save("theme", "dark");
  };

  return (
    <div className="space-y-6">
      <SectionTitle>Appearance</SectionTitle>

      {/* Theme */}
      <div>
        <FieldLabel>Theme</FieldLabel>
        <div className="grid grid-cols-2 gap-3 max-w-sm">
          <div className="relative border-2 border-blue-500 rounded-card p-3 cursor-pointer">
            <div className="absolute top-2 right-2">
              <Check size={14} className="text-blue-400" />
            </div>
            <div className="w-full h-16 rounded bg-[#080808] border border-[#1a1a1a] mb-2 flex items-end p-1.5 gap-1">
              <div className="w-3 h-6 bg-blue-500/30 rounded-sm" />
              <div className="w-3 h-10 bg-blue-500/50 rounded-sm" />
              <div className="w-3 h-4 bg-blue-500/20 rounded-sm" />
              <div className="w-3 h-8 bg-blue-500/40 rounded-sm" />
            </div>
            <p className="text-xs text-text-primary text-center">Dark</p>
          </div>
          <div className="relative border border-border rounded-card p-3 cursor-not-allowed opacity-40">
            <div className="w-full h-16 rounded bg-gray-100 border border-gray-300 mb-2 flex items-end p-1.5 gap-1">
              <div className="w-3 h-6 bg-blue-400/30 rounded-sm" />
              <div className="w-3 h-10 bg-blue-400/50 rounded-sm" />
              <div className="w-3 h-4 bg-blue-400/20 rounded-sm" />
              <div className="w-3 h-8 bg-blue-400/40 rounded-sm" />
            </div>
            <p className="text-xs text-text-tertiary text-center">
              Light (Soon)
            </p>
          </div>
        </div>
      </div>

      {/* Font size */}
      <div className="border-t border-border pt-4">
        <FieldLabel>Font Size</FieldLabel>
        <div className="flex items-center gap-4 max-w-sm">
          <button
            onClick={() => setFontSize(Math.max(10, fontSize - 1))}
            className="p-1.5 rounded-button bg-bg-elevated border border-border hover:border-blue-500/50 transition-colors text-text-secondary"
          >
            <Minus size={14} />
          </button>
          <div className="flex-1">
            <input
              type="range"
              min={10}
              max={20}
              value={fontSize}
              onChange={(e) => setFontSize(Number(e.target.value))}
              className="w-full accent-blue-500"
            />
          </div>
          <button
            onClick={() => setFontSize(Math.min(20, fontSize + 1))}
            className="p-1.5 rounded-button bg-bg-elevated border border-border hover:border-blue-500/50 transition-colors text-text-secondary"
          >
            <Plus size={14} />
          </button>
          <span className="text-sm text-text-secondary font-mono w-10 text-right">
            {fontSize}px
          </span>
        </div>
        <p className="text-xs text-text-tertiary mt-1.5">
          Base font size for the application (10px - 20px)
        </p>
      </div>

      {/* Compact mode */}
      <div className="border-t border-border pt-4">
        <Toggle
          enabled={compactMode}
          onChange={setCompactMode}
          label="Compact Mode"
          description="Reduce spacing and padding throughout the interface"
        />
      </div>

      <SaveButton
        onClick={handleSave}
        saving={!!saving["theme"]}
        saved={!!saved["theme"]}
      />
    </div>
  );
}

// ─── Tab: Risk Management ─────────────────────────────────

function RiskTab() {
  const { saving, saved, save } = useSavePref();
  const [maxDailyLoss, setMaxDailyLoss] = useState("5");
  const [maxDrawdown, setMaxDrawdown] = useState("15");
  const [maxHeat, setMaxHeat] = useState("30");
  const [maxCorrelated, setMaxCorrelated] = useState("3");
  const [leverageLimit, setLeverageLimit] = useState("2");

  useEffect(() => {
    apiFetch<{ preferences: Record<string, unknown> }>(
      "/api/orchestrator/memory/preferences"
    ).then((data) => {
      if (!data?.preferences) return;
      const p = data.preferences;
      if (p.risk_max_daily_loss != null)
        setMaxDailyLoss(String(p.risk_max_daily_loss));
      if (p.risk_max_drawdown != null)
        setMaxDrawdown(String(p.risk_max_drawdown));
      if (p.risk_max_heat != null) setMaxHeat(String(p.risk_max_heat));
      if (p.risk_max_correlated != null)
        setMaxCorrelated(String(p.risk_max_correlated));
      if (p.risk_leverage_limit != null)
        setLeverageLimit(String(p.risk_leverage_limit));
    });
  }, []);

  const handleSave = async () => {
    await save("risk_max_daily_loss", Number(maxDailyLoss));
    await save("risk_max_drawdown", Number(maxDrawdown));
    await save("risk_max_heat", Number(maxHeat));
    await save("risk_max_correlated", Number(maxCorrelated));
    await save("risk_leverage_limit", Number(leverageLimit));
  };

  return (
    <div className="space-y-6">
      <SectionTitle>Risk Management Limits</SectionTitle>
      <p className="text-xs text-text-tertiary -mt-2 mb-4">
        Configure guardrails that the algorithm enforces before entering
        positions.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <FieldLabel>Max Daily Loss (%)</FieldLabel>
          <TextInput
            value={maxDailyLoss}
            onChange={setMaxDailyLoss}
            placeholder="5"
            type="number"
          />
          <p className="text-xs text-text-tertiary mt-1">
            Trading halts if daily P&L drops below this
          </p>
        </div>
        <div>
          <FieldLabel>Max Drawdown (%)</FieldLabel>
          <TextInput
            value={maxDrawdown}
            onChange={setMaxDrawdown}
            placeholder="15"
            type="number"
          />
          <p className="text-xs text-text-tertiary mt-1">
            Maximum peak-to-trough decline allowed
          </p>
        </div>
        <div>
          <FieldLabel>Max Portfolio Heat (%)</FieldLabel>
          <TextInput
            value={maxHeat}
            onChange={setMaxHeat}
            placeholder="30"
            type="number"
          />
          <p className="text-xs text-text-tertiary mt-1">
            Sum of all position risk as % of equity
          </p>
        </div>
        <div>
          <FieldLabel>Max Correlated Positions</FieldLabel>
          <TextInput
            value={maxCorrelated}
            onChange={setMaxCorrelated}
            placeholder="3"
            type="number"
          />
          <p className="text-xs text-text-tertiary mt-1">
            Max open positions with &gt;0.7 correlation
          </p>
        </div>
        <div>
          <FieldLabel>Leverage Limit</FieldLabel>
          <TextInput
            value={leverageLimit}
            onChange={setLeverageLimit}
            placeholder="2"
            type="number"
          />
          <p className="text-xs text-text-tertiary mt-1">
            Maximum leverage multiplier (1 = no leverage)
          </p>
        </div>
      </div>

      <SaveButton
        onClick={handleSave}
        saving={!!saving["risk_leverage_limit"]}
        saved={!!saved["risk_leverage_limit"]}
      />
    </div>
  );
}

// ─── Tab: Data & Privacy ──────────────────────────────────

function DataPrivacyTab() {
  const [confirmModal, setConfirmModal] = useState<
    null | "trades" | "preferences"
  >(null);
  const [clearing, setClearing] = useState(false);

  const handleExport = () => {
    const url = `${API_BASE}/api/orchestrator/memory/preferences?export=true`;
    window.open(url, "_blank");
  };

  const handleClear = async (target: "trades" | "preferences") => {
    setClearing(true);
    const endpoint =
      target === "trades"
        ? "/api/orchestrator/memory/trades"
        : "/api/orchestrator/memory/preferences";
    await apiFetch(endpoint, { method: "DELETE" });
    setClearing(false);
    setConfirmModal(null);
  };

  return (
    <div className="space-y-6">
      <SectionTitle>Data & Privacy</SectionTitle>

      <div className="space-y-4">
        {/* Export */}
        <div className="flex items-center justify-between p-4 bg-bg-elevated rounded-card border border-border">
          <div>
            <p className="text-sm text-text-primary font-medium">Export Data</p>
            <p className="text-xs text-text-tertiary mt-0.5">
              Download all your settings and preferences as JSON
            </p>
          </div>
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 rounded-button text-sm bg-blue-500/20 text-blue-400 hover:bg-blue-500/30 transition-colors"
          >
            <Download size={14} />
            Export
          </button>
        </div>

        {/* Clear trade history */}
        <div className="flex items-center justify-between p-4 bg-bg-elevated rounded-card border border-border">
          <div>
            <p className="text-sm text-text-primary font-medium">
              Clear Trade History
            </p>
            <p className="text-xs text-text-tertiary mt-0.5">
              Permanently delete all recorded trades and P&L data
            </p>
          </div>
          <button
            onClick={() => setConfirmModal("trades")}
            className="flex items-center gap-2 px-4 py-2 rounded-button text-sm bg-loss/10 text-loss hover:bg-loss/20 transition-colors"
          >
            <Trash2 size={14} />
            Clear
          </button>
        </div>

        {/* Clear preferences */}
        <div className="flex items-center justify-between p-4 bg-bg-elevated rounded-card border border-border">
          <div>
            <p className="text-sm text-text-primary font-medium">
              Reset Preferences
            </p>
            <p className="text-xs text-text-tertiary mt-0.5">
              Reset all settings to their default values
            </p>
          </div>
          <button
            onClick={() => setConfirmModal("preferences")}
            className="flex items-center gap-2 px-4 py-2 rounded-button text-sm bg-loss/10 text-loss hover:bg-loss/20 transition-colors"
          >
            <Trash2 size={14} />
            Reset
          </button>
        </div>
      </div>

      <ConfirmModal
        open={confirmModal === "trades"}
        title="Clear Trade History"
        message="This will permanently delete all trade records, P&L history, and performance metrics. This action cannot be undone."
        onConfirm={() => handleClear("trades")}
        onCancel={() => setConfirmModal(null)}
      />
      <ConfirmModal
        open={confirmModal === "preferences"}
        title="Reset All Preferences"
        message="This will reset all your settings, API keys, risk parameters, and notification preferences to defaults. This action cannot be undone."
        onConfirm={() => handleClear("preferences")}
        onCancel={() => setConfirmModal(null)}
      />
    </div>
  );
}

// ─── Main Settings Page ───────────────────────────────────

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>("profile");

  const renderTab = () => {
    switch (activeTab) {
      case "profile":
        return <ProfileTab />;
      case "trading":
        return <TradingTab />;
      case "api-keys":
        return <ApiKeysTab />;
      case "notifications":
        return <NotificationsTab />;
      case "appearance":
        return <AppearanceTab />;
      case "risk":
        return <RiskTab />;
      case "data-privacy":
        return <DataPrivacyTab />;
    }
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-heading font-semibold text-text-primary">
          Settings
        </h1>
        <p className="text-sm text-text-secondary mt-1">
          Configure your trading environment, API connections, and risk
          parameters.
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Tab list */}
        <div className="lg:w-56 shrink-0">
          <Card padding="sm" className="lg:sticky lg:top-6">
            <nav className="space-y-0.5">
              {TABS.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={clsx(
                      "flex items-center gap-3 w-full px-3 py-2 rounded-button text-sm transition-colors",
                      isActive
                        ? "bg-bg-elevated text-text-primary"
                        : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated/50"
                    )}
                  >
                    <Icon size={16} strokeWidth={1.5} className="shrink-0" />
                    {tab.label}
                  </button>
                );
              })}
            </nav>
          </Card>
        </div>

        {/* Active tab content */}
        <div className="flex-1 min-w-0">
          <Card padding="lg">{renderTab()}</Card>
        </div>
      </div>
    </div>
  );
}
