import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#080808",
          card: "#111111",
          elevated: "#1a1a1a",
        },
        text: {
          primary: "#ffffff",
          secondary: "#888888",
          tertiary: "#555555",
        },
        border: {
          DEFAULT: "#1e1e1e",
        },
        accent: "#333333",
        profit: "#22c55e",
        loss: "#e05252",
      },
      fontFamily: {
        heading: ["var(--font-space-grotesk)", "sans-serif"],
        body: ["var(--font-inter)", "sans-serif"],
        mono: ["var(--font-space-mono)", "monospace"],
      },
      borderRadius: {
        card: "12px",
        button: "8px",
        chip: "6px",
      },
      spacing: {
        "18": "4.5rem",
        "88": "22rem",
      },
    },
  },
  plugins: [],
};

export default config;
