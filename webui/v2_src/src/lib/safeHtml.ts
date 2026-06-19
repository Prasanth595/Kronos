export function escapeHtml(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function tooltipTitle(value: unknown): string {
  return `<strong>${escapeHtml(value)}</strong>`;
}

export function tooltipText(value: unknown): string {
  return escapeHtml(value);
}

export function tooltipLines(lines: Array<string | false | null | undefined>): string {
  return lines.filter((line): line is string => Boolean(line)).join('<br/>');
}
