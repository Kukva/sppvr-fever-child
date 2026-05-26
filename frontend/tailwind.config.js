/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        medical: {
          blue: '#0066CC',
          lightblue: '#E6F3FF',
          green: '#00A652',
          lightgreen: '#E6F7ED',
          red: '#DC3545',
          lightred: '#FDE8E9',
          gray: '#6C757D',
          lightgray: '#F8F9FA',
        },
        /* Стартовая страница — светлая голубая тема по макету */
        start: {
          blue: '#B8D4E8',
          blueLight: '#E8F4FC',
          blueHover: '#9EC4E0',
        },
        /* Figma: блок ввода (node 69:305), шапка */
        figma: {
          ink: '#001D35',
          inkMuted: 'rgba(0, 29, 53, 0.35)',
          hint: 'rgba(0, 0, 0, 0.7)',
          accent: '#1D66A2',
          accentSoft: 'rgba(29, 102, 162, 0.5)',
          accentBorder: 'rgba(29, 102, 162, 0.6)',
          gradFrom: 'rgba(120, 194, 255, 0.35)',
          gradTo: 'rgba(42, 159, 255, 0.35)',
          actionGlass: 'rgba(255, 119, 162, 0.25)',
          actionInset: 'rgba(222, 37, 96, 0.19)',
        },
      },
      boxShadow: {
        'figma-card': '0 4px 30px 0 rgba(29, 102, 162, 0.3)',
        'figma-card-inset': 'inset 0 0 29.2px 0 rgba(255, 255, 255, 0.95)',
        'figma-action-inset': 'inset 0 0 5px 0 rgba(222, 37, 96, 0.19)',
      },
      fontFamily: {
        /* По брендбуку Yandex Cloud; Onest — fallback с кириллицей */
        sans: ['Yandex Sans', 'Yandex Sans Text', 'Onest', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}