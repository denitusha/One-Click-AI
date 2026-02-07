/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        panel: {
          dark: "#0a0f1a",
          card: "#0f1623",
          border: "#1a2336",
          hover: "#151d2e",
        },
        accent: {
          green: "#00e676",
          cyan: "#00bcd4",
          purple: "#a855f7",
          gold: "#e2b93b",
          orange: "#ff9800",
          red: "#DC0000",
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
    },
  },
  plugins: [],
};
