// design_spec §3 - Theme tokens owner.
// ECharts 와 Plotly 가 동일 토큰을 사용하도록 한 파일에서 옵션을 만든다.

export const theme = {
  colors: {
    bg: '#0f172a',
    card: '#111827',
    cardRaised: '#0b1120',
    border: '#243244',
    borderMuted: '#1e293b',
    text: '#e2e8f0',
    textMuted: '#94a3b8',
    textDim: '#64748b',
    textFaint: '#475569',
    accent: '#38bdf8',
    accentDim: 'rgba(56,189,248,.12)',
    accentHover: 'rgba(56,189,248,.08)',
    accentSubtle: '#bfdbfe',
    success: '#22c55e',
    successBg: '#14532d',
    successText: '#dcfce7',
    warn: '#f59e0b',
    warnBg: '#422006',
    warnText: '#fde68a',
    danger: '#ef4444',
    info: '#93c5fd',
    infoBg: '#0c4a6e',
  },
  typography: {
    fontBase: "'Segoe UI','Malgun Gothic',sans-serif",
    fontMono: "'Consolas','D2Coding',monospace",
  },
} as const;

// CSS 변수를 :root 에 set — Tailwind 와 별개로 ECharts/Plotly 가 직접 읽을 수 있게.
export function applyThemeToDocument(): void {
  if (typeof document === 'undefined') return;
  const r = document.documentElement;
  r.style.setProperty('--chart-color-primary', theme.colors.accent);
  r.style.setProperty('--chart-color-secondary', theme.colors.success);
  r.style.setProperty('--chart-color-warn', theme.colors.warn);
  r.style.setProperty('--chart-color-danger', theme.colors.danger);
  r.style.setProperty('--chart-bg', theme.colors.card);
  r.style.setProperty('--chart-grid', theme.colors.border);
  r.style.setProperty('--chart-font-family', theme.typography.fontBase);
}

// ECharts 공통 옵션 베이스 (각 차트가 deep-merge 해서 사용)
export function getEChartsBase() {
  return {
    backgroundColor: 'transparent',
    textStyle: {
      color: theme.colors.text,
      fontFamily: theme.typography.fontBase,
    },
    tooltip: {
      backgroundColor: theme.colors.card,
      borderColor: theme.colors.border,
      textStyle: {
        color: theme.colors.text,
        fontSize: 12,
      },
    },
    axisLineColor: theme.colors.borderMuted,
    splitLineColor: theme.colors.borderMuted,
    labelColor: theme.colors.textDim,
  };
}

// Plotly layout 베이스 (P4 STOM Diagnostics 에서 dynamic import)
export function getPlotlyLayoutBase() {
  return {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: {
      color: theme.colors.text,
      family: theme.typography.fontBase,
    },
    xaxis: { gridcolor: theme.colors.borderMuted, linecolor: theme.colors.border, tickcolor: theme.colors.textDim },
    yaxis: { gridcolor: theme.colors.borderMuted, linecolor: theme.colors.border, tickcolor: theme.colors.textDim },
  };
}
