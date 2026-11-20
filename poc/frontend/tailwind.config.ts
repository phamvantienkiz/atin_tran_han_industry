import type { Config } from 'tailwindcss';

const rgb = (token: string) => `rgb(var(--${token}-rgb) / <alpha-value>)`;

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        surface: {
          page: rgb('surface-page'),
          card: rgb('surface-card'),
          subtle: rgb('surface-subtle'),
          'subtle-hover': rgb('surface-subtle-hover'),
          video: rgb('surface-video'),
          hud: 'var(--surface-hud)',
        },
        brand: {
          primary: rgb('brand-primary'),
          'primary-hover': rgb('brand-primary-hover'),
          deep: rgb('brand-deep'),
          warm: rgb('brand-warm'),
          ink: rgb('brand-ink'),
        },
        content: {
          heading: rgb('text-heading'),
          primary: rgb('text-primary'),
          secondary: rgb('text-secondary'),
          muted: rgb('text-muted'),
          'on-brand': rgb('text-on-brand'),
        },
        line: {
          DEFAULT: rgb('border-default'),
          muted: rgb('border-muted'),
          strong: rgb('border-strong'),
        },
        status: {
          present: rgb('status-present'),
          empty: rgb('status-empty'),
          alert: rgb('status-alert'),
          idle: rgb('status-idle'),
          outside: rgb('status-outside'),
        },
      },
      borderRadius: {
        xs: 'var(--radius-xs)',
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        card: 'var(--radius-card)',
        pill: 'var(--radius-pill)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        'card-hover': 'var(--shadow-card-hover)',
        control: 'var(--shadow-control)',
        brand: 'var(--shadow-brand)',
        'alert-ring': 'var(--shadow-alert-ring)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
};

export default config;
