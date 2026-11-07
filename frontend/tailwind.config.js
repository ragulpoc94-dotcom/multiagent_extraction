import animate from "tailwindcss-animate";

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "2rem" },
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        border: "hsl(var(--border) / <alpha-value>)",
        input: "hsl(var(--input) / <alpha-value>)",
        ring: "hsl(var(--ring) / <alpha-value>)",
        background: "hsl(var(--background) / <alpha-value>)",
        foreground: "hsl(var(--foreground) / <alpha-value>)",
        sidebar: { DEFAULT: "hsl(var(--sidebar) / <alpha-value>)", foreground: "hsl(var(--sidebar-foreground) / <alpha-value>)", muted: "hsl(var(--sidebar-muted) / <alpha-value>)" },
        primary: { DEFAULT: "hsl(var(--primary) / <alpha-value>)", foreground: "hsl(var(--primary-foreground) / <alpha-value>)" },
        secondary: { DEFAULT: "hsl(var(--secondary) / <alpha-value>)", foreground: "hsl(var(--secondary-foreground) / <alpha-value>)" },
        muted: { DEFAULT: "hsl(var(--muted) / <alpha-value>)", foreground: "hsl(var(--muted-foreground) / <alpha-value>)" },
        accent: { DEFAULT: "hsl(var(--accent) / <alpha-value>)", foreground: "hsl(var(--accent-foreground) / <alpha-value>)" },
        card: { DEFAULT: "hsl(var(--card) / <alpha-value>)", foreground: "hsl(var(--card-foreground) / <alpha-value>)" },
        popover: { DEFAULT: "hsl(var(--popover) / <alpha-value>)", foreground: "hsl(var(--popover-foreground) / <alpha-value>)" },
        success: "hsl(var(--success) / <alpha-value>)",
        warning: "hsl(var(--warning) / <alpha-value>)",
        danger: "hsl(var(--danger) / <alpha-value>)",
        m1: "hsl(var(--m1) / <alpha-value>)",
        m2: "hsl(var(--m2) / <alpha-value>)",
        m3: "hsl(var(--m3) / <alpha-value>)",
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
      },
      keyframes: {
        "cell-pulse": { "0%,100%": { opacity: "1" }, "50%": { opacity: ".55" } },
        "fill-in": { from: { transform: "scale(.97)", opacity: ".4" }, to: { transform: "scale(1)", opacity: "1" } },
      },
      animation: {
        "cell-pulse": "cell-pulse 1.6s ease-in-out infinite",
        "fill-in": "fill-in .35s cubic-bezier(.2,.8,.2,1)",
      },
    },
  },
  plugins: [animate],
};
