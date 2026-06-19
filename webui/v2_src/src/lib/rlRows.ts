import { fmt } from './format';
import type { JsonValue, RlRunRecord, RlTableRow } from './rlApi';

export function cell(row: RlTableRow | null | undefined, key: string): JsonValue | undefined {
  return row?.[key];
}

export function text(row: RlTableRow | null | undefined, key: string, fallback = '-'): string {
  const value = cell(row, key);
  if (value === null || value === undefined || typeof value === 'object') return fallback;
  return String(value);
}

export function numberValue(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function rowNumber(row: RlTableRow | null | undefined, key: string, fallback = 0): number {
  return numberValue(cell(row, key), fallback);
}

export function rowBool(row: RlTableRow | null | undefined, key: string): boolean {
  return cell(row, key) === true || cell(row, key) === 'True' || cell(row, key) === 'true';
}

export function pct(value: unknown, digits = 2): string {
  const n = Number(value);
  return Number.isFinite(n) ? fmt.pct(n, digits) : '-';
}

export function num(value: unknown, digits = 2): string {
  const n = Number(value);
  return Number.isFinite(n) ? fmt.num(n, digits) : '-';
}

export function runLabel(run: RlRunRecord): string {
  return run.name.replace(/^stom_1s_2025_/, '');
}

export function typeLabel(type: string | undefined): string {
  switch (type) {
    case 'baseline': return 'RULE baseline';
    case 'sb3_smoke': return 'SB3 smoke';
    case 'contextual_bandit': return 'RL experiment';
    case 'cost_gate': return 'Cost gate';
    case 'performance_leaderboard': return 'Performance leaderboard';
    case 'portfolio_paper': return 'Portfolio paper';
    case 'opening_30m_rule_filter': return 'RULE filter evidence';
    case 'orderbook_rl_readiness': return 'RL readiness';
    default: return type ?? 'unknown';
  }
}

export function typeTone(type: string | undefined): string {
  if (type === 'baseline') return 'success';
  if (type === 'opening_30m_rule_filter') return 'success';
  if (type === 'cost_gate' || type === 'performance_leaderboard') return 'info';
  if (type === 'sb3_smoke' || type === 'contextual_bandit' || type === 'portfolio_paper') return 'accent';
  if (type === 'orderbook_rl_readiness') return 'warn';
  return '';
}

export function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
