/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        gray: {
          900: '#1c1a1a',
          800: '#161616',
          700: '#1e1e1e',
          600: '#2a2a2a',
        }
      }
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}