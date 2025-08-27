/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          50:  "#eef3ff",
          100: "#dbe7ff",
          200: "#b7ceff",
          300: "#8fb2ff",
          400: "#5e8cff",
          500: "#2f63ff",
          600: "#1d49d6",
          700: "#1739a8",
          800: "#122b7c",
          900: "#0d1e56",
          950: "#0a163f",
        },
        neutral: {
          25:  "#fcfcfd",
          50:  "#f9fafb",
          100: "#f2f4f7",
          200: "#e4e7ec",
          300: "#d0d5dd",
          400: "#98a2b3",
          500: "#667085",
          600: "#475467",
          700: "#344054",
          800: "#1d2939",
          900: "#101828",
        },
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,0.06), 0 4px 12px rgba(16,24,40,0.06)",
      },
      borderRadius: {
        xl: "0.9rem",
        "2xl": "1.2rem",
      },
    },
  },
  plugins: [],
};
