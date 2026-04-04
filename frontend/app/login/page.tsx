"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, register } from "@/lib/auth";
import { Lock, Mail, User, ArrowRight, Eye, EyeOff } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPass, setShowPass] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        if (!name.trim()) { setError("Name is required"); setLoading(false); return; }
        await register(email, password, name);
      }
      router.push("/");
    } catch (err: any) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: "#050505" }}>
      {/* Subtle gradient background */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "radial-gradient(ellipse at 50% 0%, rgba(59,130,246,0.06) 0%, transparent 60%)",
        }}
      />

      <div className="relative w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-10">
          <h1 className="font-heading text-4xl font-bold tracking-tight text-text-primary">
            LUMARE
          </h1>
          <p className="text-text-tertiary text-sm mt-2">Capital Intelligence Platform</p>
        </div>

        {/* Card */}
        <div
          className="rounded-2xl p-8"
          style={{
            background: "#0a0a0a",
            border: "1px solid #1a1a1a",
            boxShadow: "0 0 60px rgba(0,0,0,0.5)",
          }}
        >
          {/* Mode toggle */}
          <div className="flex mb-8 rounded-lg overflow-hidden" style={{ background: "#0d0d0d", border: "1px solid #1a1a1a" }}>
            {(["login", "register"] as const).map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); setError(""); }}
                className="flex-1 py-2.5 text-sm font-medium transition-all capitalize"
                style={{
                  background: mode === m ? "#151515" : "transparent",
                  color: mode === m ? "#e0e0e0" : "#666",
                  borderBottom: mode === m ? "2px solid #3b82f6" : "2px solid transparent",
                }}
              >
                {m === "login" ? "Sign In" : "Create Account"}
              </button>
            ))}
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "register" && (
              <div className="relative">
                <User size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Full name"
                  className="w-full pl-10 pr-4 py-3 rounded-lg text-sm bg-[#0d0d0d] border border-[#1a1a1a] text-text-primary placeholder-text-tertiary focus:outline-none focus:border-blue-500 transition-colors"
                />
              </div>
            )}

            <div className="relative">
              <Mail size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email address"
                required
                className="w-full pl-10 pr-4 py-3 rounded-lg text-sm bg-[#0d0d0d] border border-[#1a1a1a] text-text-primary placeholder-text-tertiary focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>

            <div className="relative">
              <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
              <input
                type={showPass ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
                required
                minLength={6}
                className="w-full pl-10 pr-10 py-3 rounded-lg text-sm bg-[#0d0d0d] border border-[#1a1a1a] text-text-primary placeholder-text-tertiary focus:outline-none focus:border-blue-500 transition-colors"
              />
              <button
                type="button"
                onClick={() => setShowPass(!showPass)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-secondary"
              >
                {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>

            {error && (
              <div className="text-sm text-red-400 bg-red-400/10 rounded-lg px-4 py-2.5 border border-red-400/20">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg text-sm font-semibold transition-all flex items-center justify-center gap-2 disabled:opacity-50"
              style={{
                background: "linear-gradient(135deg, #3b82f6, #2563eb)",
                color: "white",
              }}
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  {mode === "login" ? "Sign In" : "Create Account"}
                  <ArrowRight size={16} />
                </>
              )}
            </button>
          </form>

          {mode === "login" && (
            <p className="text-center text-text-tertiary text-xs mt-6">
              Demo credentials: <span className="text-text-secondary font-mono">demo@lumare.com</span> / <span className="text-text-secondary font-mono">demo123</span>
            </p>
          )}
        </div>

        <p className="text-center text-text-tertiary text-[10px] mt-8 font-mono">
          LUMARE CAPITAL INTELLIGENCE v0.1.0
        </p>
      </div>
    </div>
  );
}
