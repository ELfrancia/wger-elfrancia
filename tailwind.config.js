/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./wger/**/templates/**/*.html",
    "./wger/**/static/**/*.js",
    "./wger/**/*.py"
  ],
  theme: {
    extend: {
      colors: {
        background: "#08090A",
        surface: "#101114",
        "surface-card": "#16171A",
        "surface-container": "#1D1E22",
        "surface-container-low": "#161616",
        "surface-container-high": "#262626",
        "surface-container-highest": "#333333",
        primary: "#caf300",
        "primary-fixed": "#caf300",
        "on-primary": "#000000",
        secondary: "#94A3B8",
        outline: "#222429",
        "on-surface-variant": "#c5c9ac",
        error: "#ffb4ab"
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
        display: ["Outfit", "sans-serif"]
      }
    }
  },
  plugins: [
    require('@tailwindcss/forms'),
    require('@tailwindcss/container-queries')
  ]
};
