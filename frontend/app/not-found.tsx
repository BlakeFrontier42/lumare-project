import { Search, LayoutDashboard, TrendingUp, Briefcase } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-screen p-6 bg-bg-primary">
      <div className="w-full max-w-md text-center">
        {/* Icon */}
        <div className="flex items-center justify-center w-16 h-16 rounded-full bg-bg-elevated border border-border mb-6 mx-auto">
          <Search className="w-7 h-7 text-text-tertiary" />
        </div>

        {/* Heading */}
        <h1 className="text-4xl font-heading font-bold text-text-primary mb-2">
          404
        </h1>
        <p className="text-lg font-heading text-text-secondary mb-2">
          Page Not Found
        </p>
        <p className="text-sm text-text-tertiary mb-10 max-w-sm mx-auto">
          The page you are looking for does not exist or has been moved.
        </p>

        {/* Navigation links */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="/"
            className="flex items-center gap-2 px-5 py-2.5 bg-white text-black text-sm font-medium rounded-button hover:bg-white/90 transition-colors w-full sm:w-auto justify-center"
          >
            <LayoutDashboard className="w-4 h-4" />
            Dashboard
          </a>
          <a
            href="/trade"
            className="flex items-center gap-2 px-5 py-2.5 bg-bg-card border border-border text-text-secondary text-sm font-medium rounded-button hover:text-text-primary hover:border-accent transition-colors w-full sm:w-auto justify-center"
          >
            <TrendingUp className="w-4 h-4" />
            Trade
          </a>
          <a
            href="/portfolio"
            className="flex items-center gap-2 px-5 py-2.5 bg-bg-card border border-border text-text-secondary text-sm font-medium rounded-button hover:text-text-primary hover:border-accent transition-colors w-full sm:w-auto justify-center"
          >
            <Briefcase className="w-4 h-4" />
            Portfolio
          </a>
        </div>
      </div>
    </div>
  );
}
