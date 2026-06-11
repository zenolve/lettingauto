/** @type {import('tailwindcss').Config} */
// Design language: "Editorial Mesh" (landing variation F) — warm paper, ink
// type, Fraunces serif display with italic accents, pastel mesh gradients,
// ink pill buttons, hairline rules. Tokens are SEMANTIC: pages reference
// cream/navy/gold/ink names, so the whole app restyles from here.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Warm paper — page background and surfaces.
        cream: {
          50: "#faf8f4",  // page background (F paper)
          100: "#f5f1e9", // alt surface
          200: "#eee8dc", // hover / muted fill
          300: "#e4dccd", // hairline (subtle)
          400: "#cbc1ae", // hairline (visible)
        },
        // Historically "navy" — now the warm-ink ramp F headlines use.
        // Existing pages say text-navy-700 / bg-navy-600 etc.; remapping the
        // values here flips the whole app from blue to editorial ink.
        navy: {
          50: "#f3f1ea",
          100: "#e7e3d8",
          200: "#cfc8b8",
          300: "#a49d8c",
          400: "#76705f",
          500: "#4a463c",
          600: "#262419",
          700: "#1a1a18",
          800: "#131311",
          900: "#0c0c0b",
        },
        // Honey gold — warm accent for underlines, highlights, merge tokens.
        gold: {
          200: "#f0e2bb",
          300: "#e3cd92",
          400: "#d4b56a",
          500: "#C9A24C",
          600: "#a07d33",
          700: "#7a5e24",
        },
        ink: {
          DEFAULT: "#1a1a18",
          soft:    "#4a463d",
          muted:   "#6f6a60", // 5.5:1 on cream-50 — AA for body text
        },
        // F's pastel mesh palette — decorative gradients only, never text.
        mesh: {
          peach:    "#ffd9c4",
          lavender: "#ddd6fe",
          mint:     "#d1f5e4",
          butter:   "#fdf3c9",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "Arial", "sans-serif"],
        serif: ["Fraunces", "Charter", "Iowan Old Style", "Georgia", "serif"],
      },
      fontSize: {
        display: ["48px", { lineHeight: "1.04", letterSpacing: "-0.015em" }],
        h1:      ["34px", { lineHeight: "1.08", letterSpacing: "-0.012em" }],
        h2:      ["23px", { lineHeight: "1.18", letterSpacing: "-0.006em" }],
      },
      letterSpacing: {
        kicker: "0.18em",
      },
      borderRadius: {
        // Organic "hand-drawn" radius for decorative cards (F's paper stack).
        blob: "58% 42% 56% 44% / 48% 55% 45% 52%",
      },
      boxShadow: {
        // Layered warm paper shadow — cards at rest.
        paper: "0 1px 0 rgba(26,26,24,0.03), 0 6px 18px rgba(63,48,21,0.06)",
        // Hover lift for interactive cards / the ink pill.
        lift:  "0 2px 4px rgba(26,26,24,0.06), 0 14px 34px rgba(63,48,21,0.11)",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.22, 1, 0.36, 1)", // ease-out-quint — entrances
      },
    },
  },
  plugins: [],
};
