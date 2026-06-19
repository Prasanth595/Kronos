import { tooltipLines, tooltipText, tooltipTitle } from '$lib/safeHtml';
import { pct, rowBool, rowNumber, text } from '$lib/rlRows';
import type { RlTableRow } from '$lib/rlApi';

type Option = Record<string, unknown>;
type DataParam = { readonly dataIndex?: number; readonly value?: unknown };

function isDataParam(value: unknown): value is DataParam {
  return typeof value === 'object' && value !== null;
}

function firstParam(value: unknown): DataParam | null {
  if (Array.isArray(value)) return isDataParam(value[0]) ? value[0] : null;
  return isDataParam(value) ? value : null;
}

function colorByValue(value: unknown): string {
  return Number(value) >= 0 ? '#16a34a' : '#dc2626';
}

export function leaderboardChartOption(rows: readonly RlTableRow[]): Option {
  const sample = rows.slice(0, 12);
  if (!sample.length) return {};
  return {
    backgroundColor: 'transparent', grid: { left: 58, right: 28, top: 42, bottom: 48 },
    tooltip: { trigger: 'axis', formatter: (params: unknown) => {
      const row = sample[firstParam(params)?.dataIndex ?? 0];
      return tooltipLines([tooltipTitle(text(row, 'model', text(row, 'policy'))), tooltipText(`source ${text(row, 'source')}`), tooltipText(`net evidence ${pct(rowNumber(row, 'avg_episode_net_return_pct'), 3)}`), tooltipText(`MDD ${pct(rowNumber(row, 'max_drawdown_pct'), 2)}`)]);
    } },
    xAxis: { type: 'category', data: sample.map((row) => text(row, 'model', text(row, 'policy'))), axisLabel: { color: '#64748b', rotate: 20 } },
    yAxis: { type: 'value', name: 'net/MDD %', axisLabel: { formatter: '{value}%', color: '#64748b' } },
    series: [
      { name: 'avg episode net', type: 'bar', data: sample.map((row) => rowNumber(row, 'avg_episode_net_return_pct')), itemStyle: { color: '#0f766e', borderRadius: [5, 5, 0, 0] } },
      { name: 'MDD', type: 'bar', data: sample.map((row) => rowNumber(row, 'max_drawdown_pct')), itemStyle: { color: '#ef4444', borderRadius: [5, 5, 0, 0] } },
    ],
  };
}

export function costGateChartOption(rows: readonly RlTableRow[]): Option {
  if (!rows.length) return {};
  return {
    backgroundColor: 'transparent', grid: { left: 58, right: 28, top: 42, bottom: 48 }, tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rows.map((row) => text(row, 'policy')), axisLabel: { color: '#64748b', rotate: 20 } },
    yAxis: { type: 'value', name: 'net %', axisLabel: { formatter: '{value}%', color: '#64748b' } },
    series: [{ name: '23bp cost gate', type: 'bar', data: rows.map((row) => rowNumber(row, 'avg_episode_net_return_pct')), itemStyle: { color: (param: unknown) => colorByValue(firstParam(param)?.value), borderRadius: [5, 5, 0, 0] } }],
  };
}

export function equityChartOption(rows: readonly RlTableRow[]): Option {
  if (!rows.length) return {};
  const useCandidateNetReturn = rows.some((row) => 'net_return_pct' in row);
  return {
    backgroundColor: 'transparent', grid: { left: 58, right: 24, top: 30, bottom: 38 }, tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: rows.map((row, idx) => text(row, 'timestamp', text(row, 'step', String(idx + 1))).slice(0, 19)), axisLabel: { color: '#64748b' } },
    yAxis: { type: 'value', name: 'net evidence %', axisLabel: { formatter: '{value}%', color: '#64748b' } },
    series: [{ name: 'Time equity curve', type: 'line', smooth: 0.2, symbol: 'none', data: rows.map((row) => useCandidateNetReturn ? rowNumber(row, 'net_return_pct') : (rowNumber(row, 'equity', 1) - 1) * 100), lineStyle: { color: '#0f766e', width: 2.4 } }],
  };
}

export function actionPnlChartOption(actions: readonly RlTableRow[], episodes: readonly RlTableRow[], selectedName: string): Option {
  if (!actions.length) return {};
  const baselineByEpisode = new Map<string, number>();
  for (const row of episodes) baselineByEpisode.set(text(row, 'episode_id', ''), rowNumber(row, 'baseline_net_return_pct'));
  let cumulativeRewardPct = 0;
  let previousEpisodeId = '';
  const rows = actions.map((row, idx) => {
    const episodeId = text(row, 'episode_id', '');
    const boundary = Boolean(episodeId && previousEpisodeId && episodeId !== previousEpisodeId);
    previousEpisodeId = episodeId || previousEpisodeId;
    cumulativeRewardPct += rowNumber(row, 'reward') * 100;
    return { row, idx, episodeId, boundary, cumulativeRewardPct, baseline: baselineByEpisode.get(episodeId) ?? null };
  });
  return {
    backgroundColor: 'transparent', grid: { left: 64, right: 34, top: 42, bottom: 48 },
    tooltip: { trigger: 'axis', formatter: (params: unknown) => {
      const point = rows[firstParam(params)?.dataIndex ?? 0];
      return tooltipLines([tooltipTitle(`${point?.episodeId || selectedName} #${(point?.idx ?? 0) + 1}`), tooltipText(`reward evidence ${pct(point?.cumulativeRewardPct, 3)}`), tooltipText(`action ${text(point?.row, 'action_name', text(point?.row, 'action'))}`)]);
    } },
    xAxis: { type: 'category', data: rows.map((point) => String(point.idx + 1)), axisLabel: { color: '#64748b' } },
    yAxis: { type: 'value', name: 'cumulative reward %', axisLabel: { formatter: '{value}%', color: '#64748b' } },
    series: [
      { name: 'model cumulative reward', type: 'line', symbol: 'none', data: rows.map((point) => point.cumulativeRewardPct), lineStyle: { color: '#7c3aed', width: 2.4 }, markLine: { silent: true, symbol: 'none', label: { show: false }, data: rows.filter((point) => point.boundary).map((point) => ({ xAxis: point.idx })) } },
      { name: 'ts_imb baseline', type: 'line', symbol: 'none', data: rows.map((point) => point.baseline), lineStyle: { color: '#f59e0b', type: 'dashed', width: 2 } },
    ],
  };
}

export function tradeChartOption(rows: readonly RlTableRow[]): Option {
  const sample = rows.slice(0, 80);
  if (!sample.length) return {};
  return {
    backgroundColor: 'transparent', grid: { left: 58, right: 24, top: 30, bottom: 46 }, tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: sample.map((row, idx) => text(row, 'symbol', text(row, 'policy', String(idx + 1)))), axisLabel: { color: '#64748b', rotate: sample.length > 18 ? 40 : 0 } },
    yAxis: { type: 'value', name: 'trade net %', axisLabel: { formatter: '{value}%', color: '#64748b' } },
    series: [{ name: 'Net return evidence', type: 'bar', data: sample.map((row) => rowNumber(row, 'net_return_pct')), itemStyle: { color: (param: unknown) => colorByValue(firstParam(param)?.value), borderRadius: [4, 4, 0, 0] } }],
  };
}

export function costGatePassCount(rows: readonly RlTableRow[]): number {
  return rows.filter((row) => rowBool(row, 'passes_cost_gate')).length;
}
