/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Cocoa brown/amber palette — warm, derived from roasted cocoa tones.
        cocoa: {
          50: '#FAF6F1',
          100: '#F1E5D3',
          200: '#E3CCAB',
          300: '#CFAE7D',
          400: '#B88953',
          500: '#9C6B36',
          600: '#7E5429',
          700: '#5D3A1A',
          800: '#3F2810',
          900: '#261708',
        },
      },
    },
  },
  plugins: [],
}
