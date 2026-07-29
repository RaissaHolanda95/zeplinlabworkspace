/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#16142c',
        brand: '#7257f2',
        lavender: '#f3f0ff',
      },
      boxShadow: { soft: '0 12px 35px rgba(41, 28, 111, 0.08)' },
    },
  },
  plugins: [],
}
