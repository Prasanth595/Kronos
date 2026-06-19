// 공식 대시보드 디자인 시스템 — inline SVG icons (Lucide 풍, 24x24, stroke 1.7)
// 이모지 사용 금지 (anti-AI-slop 가이드)

export type IconName =
  | 'grid'
  | 'activity'
  | 'wand'
  | 'pulse'
  | 'package'
  | 'history'
  | 'cpu'
  | 'settings'
  | 'menu'
  | 'sun'
  | 'moon'
  | 'bell'
  | 'refresh'
  | 'chevron_right'
  | 'download'
  | 'play'
  | 'pause'
  | 'file'
  | 'chip'
  | 'check'
  | 'info'
  | 'warn'
  | 'arrow_up'
  | 'arrow_dn'
  | 'flame'
  | 'database'
  | 'rocket';

export const ICONS: Record<IconName, string> = {
  grid:    '<path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  activity:'<path d="M3 12h4l3-9 4 18 3-9h4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  wand:    '<path d="M5 19l8-8M14 4l1 3 3 1-3 1-1 3-1-3-3-1 3-1 1-3z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  pulse:   '<path d="M3 12h3l2-7 4 14 2-7h7" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  package: '<path d="M12 3l8 4-8 4-8-4 8-4zM4 7v10l8 4 8-4V7M12 11v10" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  cpu:     '<path d="M5 5h14v14H5z M9 9h6v6H9z M9 1v3 M15 1v3 M9 20v3 M15 20v3 M1 9h3 M1 15h3 M20 9h3 M20 15h3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  settings:'<path d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 0 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 0 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 0 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3h0a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 0 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9v0a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
  menu:    '<path d="M3 6h18M3 12h18M3 18h18" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  sun:     '<circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  moon:    '<path d="M20 14a8 8 0 1 1-9.8-9.8 7 7 0 0 0 9.8 9.8z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  bell:    '<path d="M6 8a6 6 0 1 1 12 0v5l1.5 3h-15L6 13V8zM10 19a2 2 0 0 0 4 0" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 15.5-6.3L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.5 6.3L3 16M3 21v-5h5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  chevron_right: '<path d="M9 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  download: '<path d="M12 3v12M7 11l5 5 5-5M5 21h14" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  play:    '<path d="M6 4l14 8-14 8z" fill="currentColor"/>',
  pause:   '<path d="M7 4h4v16H7zM13 4h4v16h-4z" fill="currentColor"/>',
  file:    '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  chip:    '<path d="M5 5h14v14H5z M9 9h6v6H9z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  check:   '<path d="M5 12l5 5 9-12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  info:    '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12 8v.5M12 11v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  warn:    '<path d="M12 4l10 16H2zM12 10v5M12 18v.5" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
  arrow_up:'<path d="M12 19V5M5 12l7-7 7 7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  arrow_dn:'<path d="M12 5v14M19 12l-7 7-7-7" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
  flame:   '<path d="M12 3c1 4 5 5 5 10a5 5 0 1 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3-1-3 0-6 1-9z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
  database:'<ellipse cx="12" cy="5" rx="8" ry="3" fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M4 5v14a8 3 0 0 0 16 0V5M4 12a8 3 0 0 0 16 0" fill="none" stroke="currentColor" stroke-width="1.7"/>',
  rocket:  '<path d="M5 13l4 4 7-7c3-3 5-6 5-9-3 0-6 2-9 5l-7 7z M5 13l-2 6 6-2 M14 7l3 3" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>',
};

export function svg(name: IconName, size: number = 18): string {
  const path = ICONS[name];
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${path}</svg>`;
}
