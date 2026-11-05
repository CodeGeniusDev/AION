import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        primary: {
          DEFAULT: "var(--primary)",
          hover: "var(--primary-hover)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        surface: "var(--surface)",
        sidebar: "var(--sidebar)",
        shell: "var(--app-shell)",
        navy: "var(--navy)",
        avatar: {
          navy: "var(--avatar-navy)",
          blue: "var(--avatar-blue)",
          teal: "var(--avatar-teal)",
          violet: "var(--avatar-violet)",
          amber: "var(--avatar-amber)",
          rose: "var(--avatar-rose)",
        },
        "aion-text": "var(--text)",
        "muted-text": "var(--muted-text)",
        "soft-blue": "var(--soft-blue)",
        "soft-peach": "var(--soft-peach)",
        "soft-grey": "var(--soft-grey)",
        "soft-green": "var(--soft-green)",
        "surface-2": "var(--surface-2)",
        success: {
          soft: "var(--success-soft)",
          text: "var(--success-text)",
          border: "var(--success-border)",
          solid: "var(--success-solid)",
        },
        warning: {
          soft: "var(--warning-soft)",
          text: "var(--warning-text)",
          border: "var(--warning-border)",
          solid: "var(--warning-solid)",
        },
        danger: {
          soft: "var(--danger-soft)",
          text: "var(--danger-text)",
          border: "var(--danger-border)",
          solid: "var(--danger-solid)",
        },
        info: {
          soft: "var(--info-soft)",
          text: "var(--info-text)",
          border: "var(--info-border)",
        },
        "neutral-solid": "var(--neutral-solid)",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
} satisfies Config;
