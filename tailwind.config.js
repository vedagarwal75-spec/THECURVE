/**
 * Tailwind config — used to pre-build static/app.css so the site does not
 * depend on a CDN at runtime.  Rebuild after editing templates:
 *     npm run build:css
 */
module.exports = {
  content: ['./templates/**/*.html'],

  // Classes produced by Jinja interpolation (e.g. `text-{{ tone }}`) can't be
  // seen by the scanner, so they're listed explicitly.
  safelist: [
    'text-up', 'text-gold', 'text-sea', 'text-paper', 'text-down', 'text-paper-mute',
    'bg-up', 'bg-gold', 'bg-sea', 'bg-paper-mute', 'bg-down',
  ],

  theme: {
    extend: {
      fontFamily: {
        display: ['Newsreader', 'Georgia', 'serif'],
        sans:    ['Inter', 'system-ui', 'sans-serif'],
        mono:    ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        ink:   { 950:'#080B0F', 900:'#0B0F14', 850:'#0F141A', 800:'#131A22', 700:'#1B242E' },
        paper: { DEFAULT:'#ECEAE6', dim:'#AEB7C2', mute:'#7C8794', faint:'#5A6470' },
        gold:  { DEFAULT:'#DFAE44', soft:'#F0CB7D' },
        sea:   { DEFAULT:'#7FA8D9' },
        up:    { DEFAULT:'#6BBF8A' },
        down:  { DEFAULT:'#D9705F' },
      },
      animation: { marquee: 'marquee 45s linear infinite' },
      keyframes: {
        marquee: { '0%': { transform:'translateX(0)' }, '100%': { transform:'translateX(-50%)' } },
      },
    },
  },
  plugins: [],
};
