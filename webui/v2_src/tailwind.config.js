/** @type {import('tailwindcss').Config} */
// [AC-1] Tailwind prebuilt 강제 — Play CDN 사용 금지
// 공식 대시보드 디자인 시스템 — Tailwind 색상 토큰은 styles/core.css 의 CSS 변수를 참조
export default {
  content: ['./index.html', './src/**/*.{svelte,ts,js}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // styles/core.css :root 토큰 — light/dark 자동 전환
        bg: 'var(--bg)',
        surface: 'var(--surface)',
        'surface-raised': 'var(--surface-raised)',
        'surface-sunken': 'var(--surface-sunken)',
        'surface-elev': 'var(--surface-elev)',
        border: 'var(--border)',
        'border-strong': 'var(--border-strong)',
        'border-faint': 'var(--border-faint)',
        fg: 'var(--fg)',
        'fg-strong': 'var(--fg-strong)',
        muted: 'var(--muted)',
        dim: 'var(--dim)',
        faint: 'var(--faint)',
        accent: 'var(--accent)',
        'accent-strong': 'var(--accent-strong)',
        'accent-soft': 'var(--accent-soft)',
        'accent-tint': 'var(--accent-tint)',
        success: 'var(--success)',
        'success-soft': 'var(--success-soft)',
        warn: 'var(--warn)',
        'warn-soft': 'var(--warn-soft)',
        danger: 'var(--danger)',
        'danger-soft': 'var(--danger-soft)',
        info: 'var(--info)',
        'info-soft': 'var(--info-soft)',

        // 하위 호환 — 기존 컴포넌트의 alias 유지 (점진 마이그레이션용)
        card: 'var(--surface)',
        'card-raised': 'var(--surface-raised)',
        'border-muted': 'var(--border-faint)',
        text: 'var(--fg)',
        'text-muted': 'var(--muted)',
        'text-dim': 'var(--dim)',
        'text-faint': 'var(--faint)',
        'accent-subtle': 'var(--accent-strong)',
        'success-bg': 'var(--success-soft)',
        'warn-bg': 'var(--warn-soft)',
        'info-bg': 'var(--info-soft)',
      },
      fontFamily: {
        sans: ['Pretendard Variable', 'Pretendard', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Malgun Gothic', 'sans-serif'],
        mono: ["'JetBrains Mono'", "'D2Coding'", "'Consolas'", 'monospace'],
      },
      borderRadius: {
        sm: 'var(--r-sm)',
        md: 'var(--r-md)',
        lg: 'var(--r-lg)',
        xl: 'var(--r-xl)',
      },
      boxShadow: {
        xs: 'var(--shadow-xs)',
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)',
      },
      transitionDuration: {
        fast: '140ms',
        base: '220ms',
        slow: '400ms',
      },
    },
  },
  plugins: [],
};
