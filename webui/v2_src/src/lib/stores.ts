// Svelte 5 runes 기반 reactive stores.
// state 단일 owner — App.svelte 에서 import 해서 모든 컴포넌트가 공유.

import { writable, type Writable, derived, type Readable } from 'svelte/store';
import type { TrainingStatus, HistoryResponse, ArtifactsResponse, GpuResponse, SystemResponse } from './api';

export const trainingStatus: Writable<TrainingStatus | null> = writable(null);
export const trainingHistory: Writable<HistoryResponse | null> = writable(null);
export const artifacts: Writable<ArtifactsResponse | null> = writable(null);
export const gpuStatus: Writable<GpuResponse | null> = writable(null);
export const systemStatus: Writable<SystemResponse | null> = writable(null);

// 사용자 설정 — refresh 주기, 활성 탭, 사이드바 collapse 상태
export const refreshSeconds: Writable<number> = writable(5);
export const activeTab: Writable<string> = writable('live-training');
export const sidebarCollapsed: Writable<boolean> = writable(false);
export const sidebarMobileOpen: Writable<boolean> = writable(false);

// ── 테마 (light/dark) — 공식 대시보드 디자인 시스템 ────────────────────
const THEME_KEY = 'kronos-theme';
type ThemeValue = 'light' | 'dark';

function readInitialTheme(): ThemeValue {
  if (typeof localStorage === 'undefined') return 'light';
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export const theme: Writable<ThemeValue> = writable<ThemeValue>(readInitialTheme());

// 테마 변경 시 documentElement[data-theme] 자동 갱신 + 이벤트 dispatch
if (typeof document !== 'undefined') {
  theme.subscribe((v) => {
    document.documentElement.setAttribute('data-theme', v);
    try {
      localStorage.setItem(THEME_KEY, v);
    } catch {}
    document.dispatchEvent(new CustomEvent('kronos:theme', { detail: { theme: v } }));
  });
}

export function toggleTheme(): void {
  theme.update((v) => (v === 'light' ? 'dark' : 'light'));
}

// 마지막 갱신 시각 표시
export const lastUpdatedAt: Writable<string> = writable('-');

// GPU ring buffer (720 points = 5초 * 720 = 1 시간)
export interface GpuRingPoint {
  util: number | null;
  temp: number | null;
  vram: number | null;
  ts: number;
}
export const gpuRing: Writable<GpuRingPoint[]> = writable([]);

export function pushGpuRing(point: GpuRingPoint): void {
  gpuRing.update((r) => {
    const next = [...r, point];
    return next.length > 720 ? next.slice(next.length - 720) : next;
  });
}

// CPU/RAM ring buffer — GPU 트렌드와 같은 시간축에서 host 상태를 함께 표시.
export interface SystemRingPoint {
  cpuUtil: number | null;
  cpuTemp: number | null;
  cpuTempPct: number | null;
  ram: number | null;
  ts: number;
}
export const systemRing: Writable<SystemRingPoint[]> = writable([]);

export function pushSystemRing(point: SystemRingPoint): void {
  systemRing.update((r) => {
    const next = [...r, point];
    return next.length > 720 ? next.slice(next.length - 720) : next;
  });
}

// Loss points ring buffer (max 1000)
export interface LossPoint {
  step: number;
  loss: number;
}
export const lossPoints: Writable<LossPoint[]> = writable([]);

function normalizeLossPoints(points: LossPoint[]): LossPoint[] {
  const byStep = new Map<number, LossPoint>();
  for (const p of points) {
    if (p.step != null && p.loss != null && Number.isFinite(p.step) && Number.isFinite(p.loss)) {
      byStep.set(p.step, { step: p.step, loss: p.loss });
    }
  }
  const merged = Array.from(byStep.values()).sort((a, b) => a.step - b.step);
  return merged.length > 1000 ? merged.slice(merged.length - 1000) : merged;
}

export function setLossPoints(newPts: LossPoint[]): void {
  lossPoints.set(normalizeLossPoints(newPts));
}

export function mergeLossPoints(newPts: LossPoint[]): void {
  lossPoints.update((existing) => {
    return normalizeLossPoints([...existing, ...newPts]);
  });
}

// Derived metrics — 컴포넌트가 직접 latest_point 를 읽지 않고 이 store 만 구독
export interface MetricsLatest {
  loss: number | null;
  samplesPerSec: number | null;
  learningRate: number | null;
  epoch: number | null;
  epochs: number | null;
  runName: string | null;
}
export const metricsLatest: Readable<MetricsLatest> = derived(trainingHistory, ($h) => {
  const lp: any = $h?.latest_point ?? {};
  const lpg: any = $h?.latest_progress ?? {};
  return {
    loss: lp.loss != null ? lp.loss : lpg.last_loss ?? null,
    samplesPerSec: lpg.samples_per_second ?? null,
    learningRate: lp.learning_rate ?? null,
    epoch: lp.epoch ?? null,
    epochs: lp.epochs ?? null,
    runName: $h?.run_name ?? null,
  };
});
