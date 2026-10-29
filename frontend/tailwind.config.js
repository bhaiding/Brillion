/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#141128',
        cream: '#fff9ee',
        electric: '#6c47ff',
        coral: '#ff6b57',
        mint: '#7ce7c2',
        sun: '#ffd45b',
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', 'system-ui', 'sans-serif'],
        body: ['"DM Sans"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        chunky: '0 8px 0 #141128',
      },
    },
  },
  plugins: [],
}

