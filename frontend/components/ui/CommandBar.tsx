"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import {
  MessageSquare,
  X,
  Send,
  Loader2,
  Brain,
  Search,
  ChevronRight,
  Mic,
  MicOff,
} from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────────

interface ResponseBlock {
  type: string;
  title: string | null;
  data: Record<string, any>;
  severity?: string;
  source?: string;
}

interface RoutingInfo {
  category: string;
  confidence: number;
  adapters_used: string[];
  slm_handled: boolean;
}

interface PolicyInfo {
  allowed: boolean;
  reason: string | null;
  severity: string;
}

interface OrchestratorResponse {
  request_id: string;
  routing: RoutingInfo;
  policy: PolicyInfo;
  blocks: ResponseBlock[];
  latency_ms: number;
  timestamp: string;
}

interface HistoryEntry {
  query: string;
  response: OrchestratorResponse | null;
  error: string | null;
  timestamp: Date;
}

// ── Web Speech API Types ──────────────────────────────────────────────────

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognitionInstance;
    webkitSpeechRecognition: new () => SpeechRecognitionInstance;
  }
}

// ── Voice Waveform Animation ──────────────────────────────────────────────

function VoiceWaveform() {
  return (
    <div className="flex items-center gap-[2px] h-4">
      {[0, 1, 2, 3, 4].map((i) => (
        <div
          key={i}
          className="w-[2px] bg-red-500 rounded-full animate-pulse"
          style={{
            height: `${8 + Math.random() * 8}px`,
            animationDelay: `${i * 0.15}s`,
            animationDuration: `${0.4 + i * 0.1}s`,
          }}
        />
      ))}
    </div>
  );
}

// ── Block Renderers ────────────────────────────────────────────────────────

function TextBlock({ block }: { block: ResponseBlock }) {
  return (
    <div className="space-y-1">
      {block.title && (
        <h4 className="text-sm font-heading font-semibold text-text-primary">
          {block.title}
        </h4>
      )}
      <p className="text-sm text-text-secondary leading-relaxed whitespace-pre-wrap">
        {block.data.body ?? block.data.text ?? JSON.stringify(block.data)}
      </p>
    </div>
  );
}

function MetricBlock({ block }: { block: ResponseBlock }) {
  const entries = block.data.metrics ?? [block.data];
  return (
    <div className="space-y-1">
      {block.title && (
        <h4 className="text-xs font-heading font-semibold text-text-secondary uppercase tracking-wider">
          {block.title}
        </h4>
      )}
      <div className="grid grid-cols-2 gap-2">
        {(Array.isArray(entries) ? entries : [entries]).map(
          (m: any, i: number) => (
            <div
              key={i}
              className="bg-bg-elevated border border-border rounded-chip px-3 py-2"
            >
              <div className="text-[10px] text-text-tertiary uppercase tracking-wider">
                {m.label ?? m.name ?? `Metric ${i + 1}`}
              </div>
              <div className="text-sm font-mono font-semibold text-text-primary">
                {m.value ?? m.amount ?? "—"}
              </div>
            </div>
          )
        )}
      </div>
    </div>
  );
}

function SignalBlock({ block }: { block: ResponseBlock }) {
  const d = block.data;
  const isLong = (d.direction ?? "").toUpperCase() === "LONG";
  return (
    <div className="bg-bg-elevated border border-border rounded-chip p-3 space-y-2">
      {block.title && (
        <h4 className="text-xs font-heading font-semibold text-text-secondary uppercase tracking-wider">
          {block.title}
        </h4>
      )}
      <div className="flex items-center justify-between">
        <span className="font-mono font-bold text-text-primary text-sm">
          {d.symbol ?? "—"}
        </span>
        <span
          className={`text-xs font-bold px-2 py-0.5 rounded-chip ${
            isLong
              ? "bg-profit/15 text-profit"
              : "bg-loss/15 text-loss"
          }`}
        >
          {(d.direction ?? "—").toUpperCase()}
        </span>
      </div>
      {d.score != null && (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-bg-primary rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${isLong ? "bg-profit" : "bg-loss"}`}
              style={{ width: `${Math.min(Math.max(Number(d.score) * 100, 0), 100)}%` }}
            />
          </div>
          <span className="text-[10px] font-mono text-text-tertiary">
            {(Number(d.score) * 100).toFixed(0)}%
          </span>
        </div>
      )}
      <div className="grid grid-cols-3 gap-2 text-[10px]">
        {d.entry != null && (
          <div>
            <span className="text-text-tertiary">Entry</span>
            <div className="font-mono text-text-primary">{d.entry}</div>
          </div>
        )}
        {d.stop != null && (
          <div>
            <span className="text-text-tertiary">Stop</span>
            <div className="font-mono text-loss">{d.stop}</div>
          </div>
        )}
        {d.targets != null && (
          <div>
            <span className="text-text-tertiary">Targets</span>
            <div className="font-mono text-profit">
              {Array.isArray(d.targets) ? d.targets.join(", ") : d.targets}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function RiskAlertBlock({ block }: { block: ResponseBlock }) {
  const sev = (block.severity ?? block.data.severity ?? "warning").toLowerCase();
  const isCritical = sev === "critical" || sev === "high";
  return (
    <div
      className={`rounded-chip p-3 border ${
        isCritical
          ? "bg-loss/10 border-loss/30 text-loss"
          : "bg-yellow-500/10 border-yellow-500/30 text-yellow-400"
      }`}
    >
      {block.title && (
        <h4 className="text-xs font-heading font-bold uppercase tracking-wider mb-1">
          {block.title}
        </h4>
      )}
      <p className="text-sm leading-relaxed">
        {block.data.message ?? block.data.body ?? JSON.stringify(block.data)}
      </p>
    </div>
  );
}

function CitationBlock({ block }: { block: ResponseBlock }) {
  const sources = block.data.sources ?? block.data.citations ?? [block.data];
  return (
    <div className="space-y-1">
      {block.title && (
        <h4 className="text-xs font-heading font-semibold text-text-secondary uppercase tracking-wider">
          {block.title}
        </h4>
      )}
      <ul className="space-y-1">
        {(Array.isArray(sources) ? sources : [sources]).map(
          (s: any, i: number) => (
            <li key={i} className="flex items-start gap-1.5 text-xs text-text-secondary">
              <ChevronRight className="w-3 h-3 mt-0.5 text-text-tertiary shrink-0" />
              {s.url ? (
                <a
                  href={s.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-text-primary underline underline-offset-2 transition-colors"
                >
                  {s.title ?? s.label ?? s.url}
                </a>
              ) : (
                <span>{s.title ?? s.label ?? JSON.stringify(s)}</span>
              )}
            </li>
          )
        )}
      </ul>
    </div>
  );
}

function ErrorBlock({ block }: { block: ResponseBlock }) {
  return (
    <div className="bg-loss/10 border border-loss/30 rounded-chip p-3">
      {block.title && (
        <h4 className="text-xs font-bold text-loss uppercase tracking-wider mb-1">
          {block.title}
        </h4>
      )}
      <p className="text-sm text-loss">
        {block.data.message ?? block.data.error ?? JSON.stringify(block.data)}
      </p>
    </div>
  );
}

function BlockRenderer({ block }: { block: ResponseBlock }) {
  switch (block.type) {
    case "text":
      return <TextBlock block={block} />;
    case "metric":
    case "metrics_group":
      return <MetricBlock block={block} />;
    case "signal":
      return <SignalBlock block={block} />;
    case "risk_alert":
      return <RiskAlertBlock block={block} />;
    case "citation":
      return <CitationBlock block={block} />;
    case "error":
      return <ErrorBlock block={block} />;
    default:
      return <TextBlock block={block} />;
  }
}

// ── Routing Footer ─────────────────────────────────────────────────────────

function RoutingFooter({
  routing,
  latency,
}: {
  routing: RoutingInfo;
  latency: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border text-[10px] text-text-tertiary">
      <span className="bg-bg-elevated border border-border rounded-chip px-1.5 py-0.5 font-mono uppercase">
        {routing.category}
      </span>
      <span>{(routing.confidence * 100).toFixed(0)}% conf</span>
      {routing.adapters_used.length > 0 && (
        <span className="truncate max-w-[140px]">
          {routing.adapters_used.join(", ")}
        </span>
      )}
      <span className="ml-auto font-mono">{latency}ms</span>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────

export function CommandBar() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [isListening, setIsListening] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [autoSendOnSilence, setAutoSendOnSilence] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Check for Speech API support on mount
  useEffect(() => {
    const supported =
      typeof window !== "undefined" &&
      ("SpeechRecognition" in window || "webkitSpeechRecognition" in window);
    setSpeechSupported(supported);
  }, []);

  // Cleanup recognition on unmount
  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
        recognitionRef.current = null;
      }
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
      }
    };
  }, []);

  const startListening = useCallback(() => {
    if (!speechSupported || isListening) return;

    const SpeechRecognitionAPI =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognitionAPI();

    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onstart = () => {
      setIsListening(true);
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let finalTranscript = "";
      let interimTranscript = "";

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcript;
        } else {
          interimTranscript += transcript;
        }
      }

      const text = finalTranscript || interimTranscript;
      setQuery(text);

      // Reset silence timer on each result
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
      }

      // Auto-send after 1.5s of silence if preference is set and we have final text
      if (finalTranscript && autoSendOnSilence) {
        silenceTimerRef.current = setTimeout(() => {
          setQuery((currentQuery) => {
            if (currentQuery.trim()) {
              // Trigger submit by dispatching the action after state update
              setTimeout(() => {
                const form = document.querySelector(
                  "[data-command-bar-submit]"
                ) as HTMLButtonElement;
                form?.click();
              }, 0);
            }
            return currentQuery;
          });
        }, 1500);
      }
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      // Silently handle errors - no-speech and aborted are expected
      if (event.error !== "no-speech" && event.error !== "aborted") {
        console.warn("Speech recognition error:", event.error);
      }
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
      recognitionRef.current = null;
      // Focus back to input so user can edit or send
      setTimeout(() => inputRef.current?.focus(), 100);
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, [speechSupported, isListening, autoSendOnSilence]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
    setIsListening(false);
  }, []);

  const toggleVoice = useCallback(() => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  }, [isListening, startListening, stopListening]);

  // Keyboard shortcut: Cmd+K / Ctrl+K
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Auto-focus input when opened
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  // Auto-scroll to bottom on new entries
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history, loading]);

  const submit = useCallback(async () => {
    const trimmed = query.trim();
    if (!trimmed || loading) return;

    setQuery("");
    setLoading(true);

    const entry: HistoryEntry = {
      query: trimmed,
      response: null,
      error: null,
      timestamp: new Date(),
    };

    try {
      const res = await fetch("/api/orchestrator/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: trimmed, user_id: "default" }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }

      const data: OrchestratorResponse = await res.json();
      entry.response = data;
    } catch (err: any) {
      entry.error = err.message ?? "Request failed";
    } finally {
      setHistory((prev) => [...prev, entry]);
      setLoading(false);
    }
  }, [query, loading]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <>
      {/* Toggle Button */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 bg-bg-card border border-border rounded-full px-4 py-3 shadow-2xl hover:border-text-tertiary transition-colors group"
          aria-label="Open command bar"
        >
          <Brain className="w-5 h-5 text-text-secondary group-hover:text-text-primary transition-colors" />
          <span className="text-sm text-text-secondary group-hover:text-text-primary transition-colors hidden sm:inline">
            Ask Lumare
          </span>
          <kbd className="hidden sm:inline text-[10px] text-text-tertiary bg-bg-elevated border border-border rounded px-1.5 py-0.5 font-mono">
            {typeof navigator !== "undefined" &&
            /Mac/i.test(navigator.userAgent)
              ? "\u2318K"
              : "Ctrl+K"}
          </kbd>
        </button>
      )}

      {/* Command Bar Panel */}
      {open && (
        <div className="fixed bottom-6 right-6 z-50 w-[95vw] sm:w-[420px] max-w-2xl flex flex-col bg-bg-card border border-border rounded-card shadow-2xl overflow-hidden max-h-[600px]">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <div className="flex items-center gap-2">
              <Brain className="w-4 h-4 text-text-secondary" />
              <span className="text-sm font-heading font-semibold text-text-primary">
                Lumare AI
              </span>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="p-1 rounded hover:bg-bg-elevated transition-colors"
              aria-label="Close command bar"
            >
              <X className="w-4 h-4 text-text-tertiary hover:text-text-primary" />
            </button>
          </div>

          {/* Scrollable History */}
          <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto px-4 py-3 space-y-4 min-h-[200px] max-h-[440px]"
          >
            {history.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center h-full text-center py-8 space-y-3">
                <Search className="w-8 h-8 text-text-tertiary" />
                <div className="space-y-1">
                  <p className="text-sm text-text-secondary">
                    Ask anything about your portfolio
                  </p>
                  <div className="flex flex-wrap justify-center gap-1.5 pt-1">
                    {[
                      "analyze NVDA",
                      "backtest BTC",
                      "show my risk",
                      "macro outlook",
                    ].map((s) => (
                      <button
                        key={s}
                        onClick={() => {
                          setQuery(s);
                          setTimeout(() => inputRef.current?.focus(), 0);
                        }}
                        className="text-[11px] text-text-tertiary bg-bg-elevated border border-border rounded-chip px-2 py-1 hover:text-text-secondary hover:border-text-tertiary transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {history.map((entry, idx) => (
              <div key={idx} className="space-y-2">
                {/* User query */}
                <div className="flex items-start gap-2">
                  <MessageSquare className="w-3.5 h-3.5 mt-0.5 text-text-tertiary shrink-0" />
                  <p className="text-sm text-text-primary font-medium">
                    {entry.query}
                  </p>
                </div>

                {/* Response */}
                {entry.error && (
                  <div className="bg-loss/10 border border-loss/30 rounded-chip p-3 ml-5">
                    <p className="text-sm text-loss">{entry.error}</p>
                  </div>
                )}

                {entry.response && (
                  <div className="ml-5 space-y-2">
                    {entry.response.blocks.map((block, bi) => (
                      <BlockRenderer key={bi} block={block} />
                    ))}
                    <RoutingFooter
                      routing={entry.response.routing}
                      latency={entry.response.latency_ms}
                    />
                  </div>
                )}
              </div>
            ))}

            {/* Loading indicator */}
            {loading && (
              <div className="flex items-center gap-2 ml-5 py-2">
                <Loader2 className="w-4 h-4 text-text-tertiary animate-spin" />
                <span className="text-xs text-text-tertiary">Thinking...</span>
              </div>
            )}
          </div>

          {/* Voice Recording Indicator */}
          {isListening && (
            <div className="flex items-center gap-2 px-4 py-1.5 border-t border-border bg-red-500/5">
              <span className="relative flex h-2.5 w-2.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-75" />
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500" />
              </span>
              <VoiceWaveform />
              <span className="text-[11px] text-red-400 font-medium">
                Listening...
              </span>
              <button
                onClick={stopListening}
                className="ml-auto text-[10px] text-text-tertiary hover:text-text-secondary transition-colors"
              >
                Cancel
              </button>
            </div>
          )}

          {/* Input */}
          <div className="border-t border-border px-3 py-2.5">
            <div className="flex items-center gap-2 bg-bg-elevated border border-border rounded-button px-3 py-2 focus-within:border-text-tertiary transition-colors">
              <Search className="w-4 h-4 text-text-tertiary shrink-0" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={
                  isListening
                    ? "Speak now..."
                    : "Ask Lumare anything..."
                }
                className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary outline-none"
                disabled={loading}
              />
              {speechSupported && (
                <button
                  onClick={toggleVoice}
                  disabled={loading}
                  className={`p-1 rounded transition-colors disabled:opacity-30 ${
                    isListening
                      ? "bg-red-500/15 hover:bg-red-500/25 text-red-500"
                      : "hover:bg-bg-card text-text-secondary"
                  }`}
                  aria-label={isListening ? "Stop voice input" : "Start voice input"}
                  title={isListening ? "Stop listening" : "Voice input"}
                >
                  {isListening ? (
                    <MicOff className="w-4 h-4" />
                  ) : (
                    <Mic className="w-4 h-4" />
                  )}
                </button>
              )}
              <button
                onClick={submit}
                disabled={!query.trim() || loading}
                className="p-1 rounded hover:bg-bg-card transition-colors disabled:opacity-30"
                aria-label="Send query"
                data-command-bar-submit
              >
                <Send className="w-4 h-4 text-text-secondary" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
