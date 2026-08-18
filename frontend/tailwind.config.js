/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // CSS 변수를 참조하도록 바꿔서 .dark 클래스 유무에 따라 값이 자동으로 바뀜
        // rgb(var(...) / <alpha-value>) 형태라야 기존 코드의 /30, /20 같은 투명도 문법이 그대로 동작함
        recall: {
          bg: "rgb(var(--recall-bg) / <alpha-value>)",
          bgSoft: "rgb(var(--recall-bg-soft) / <alpha-value>)",
          bgMain: "rgb(var(--recall-bg-main) / <alpha-value>)",
          accent: "rgb(var(--recall-accent) / <alpha-value>)",
          danger: "rgb(var(--recall-danger) / <alpha-value>)",
          text: "rgb(var(--recall-text) / <alpha-value>)",
          textMuted: "rgb(var(--recall-text-muted) / <alpha-value>)",
          border: "rgb(var(--recall-border) / <alpha-value>)",
        },
      },
      keyframes: {
        fadeSlideIn: {
          "0%": { opacity: "0", transform: "translateY(-8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
