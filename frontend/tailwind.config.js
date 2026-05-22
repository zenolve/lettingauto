/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Cream "paper" palette — the new base background and card surface.
        cream: {
          50: "#fdfaf3",  // page background
          100: "#faf7f2", // alt surface
          200: "#f5efe5", // hover / muted
          300: "#e9e2d4", // hairline (subtle)
          400: "#cdc4b2", // hairline (visible)
        },
        // Navy — primary brand. Slight desaturation for cream surfaces.
        navy: {
          50: "#eef3fb",
          100: "#cfdcf4",
          200: "#9fb8e8",
          300: "#6f95dc",
          400: "#3f72d0",
          500: "#1d57bc",
          600: "#004AAD",
          700: "#003c8c",
          800: "#002d6a",
          900: "#001f48",
        },
        gold: {
          200: "#ecd9a8",
          300: "#dcc07e",
          400: "#cda757",
          500: "#C9A24C",
          600: "#a98538",
          700: "#7e6126",
        },
        ink: {
          DEFAULT: "#15171a",
          soft:    "#3a3f47",
          muted:   "#7b7f87",
        },
      },
      fontFamily: {
        // Body — Inter throughout.
        sans: ["Inter", "system-ui", "Arial", "sans-serif"],
        // Headings — Fraunces (variable serif, editorial signature).
        serif: ["Fraunces", "Charter", "Iowan Old Style", "Georgia", "serif"],
      },
      fontSize: {
        // Tighter ramp to make the Fraunces headings sing.
        "display": ["44px", { lineHeight: "1.05", letterSpacing: "-0.01em" }],
        "h1":      ["32px", { lineHeight: "1.1",  letterSpacing: "-0.01em" }],
        "h2":      ["22px", { lineHeight: "1.2",  letterSpacing: "-0.005em" }],
      },
      letterSpacing: {
        kicker: "0.18em",
      },
      boxShadow: {
        // Soft, paper-y shadow — for hero cards.
        paper: "0 1px 0 rgba(0,0,0,0.02), 0 8px 24px rgba(20, 15, 5, 0.05)",
      },
    },
  },
  plugins: [],
};
