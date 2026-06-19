// 폴링 유틸리티 — refreshSeconds 가 바뀌면 자동 재시작.

import { get } from 'svelte/store';
import { refreshSeconds, trainingStatus, trainingHistory, artifacts, gpuStatus, systemStatus, lastUpdatedAt, mergeLossPoints, setLossPoints, pushGpuRing, pushSystemRing } from './stores';
import { api } from './api';

let timers: number[] = [];
let lossContextKey: string | null = null;

function clearTimers(): void {
  for (const t of timers) clearInterval(t);
  timers = [];
}

async function pollStatus(): Promise<void> {
  const d = await api.status();
  if (d) {
    trainingStatus.set(d);
    lastUpdatedAt.set(new Date().toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul' }));
  }
}

async function pollHistory(): Promise<void> {
  const d = await api.history(200);
  if (d) {
    trainingHistory.set(d);
    if (Array.isArray(d.points)) {
      const nextPoints = d.points.map((p) => ({ step: p.step, loss: p.loss }));
      const nextContextKey = [d.run_name, d.stage, d.source_log_path].filter(Boolean).join('|') || null;
      if (nextContextKey !== lossContextKey) {
        lossContextKey = nextContextKey;
        setLossPoints(nextPoints);
      } else {
        mergeLossPoints(nextPoints);
      }
    }
  }
}

async function pollArtifacts(): Promise<void> {
  const d = await api.artifacts();
  if (d) artifacts.set(d);
}

async function pollGpu(): Promise<void> {
  const d = await api.gpu();
  if (!d) return;
  gpuStatus.set(d);
  const g = d.gpus?.[0];
  if (g) {
    pushGpuRing({
      util: g.utilization_gpu_percent ?? null,
      temp: g.temperature_c ?? null,
      vram: g.memory_used_percent ?? null,
      ts: Date.now(),
    });
  }
}

async function pollSystem(): Promise<void> {
  const d = await api.system();
  if (!d) return;
  systemStatus.set(d);
  pushSystemRing({
    cpuUtil: d.cpu?.utilization_percent ?? null,
    cpuTemp: d.cpu?.temperature_c ?? null,
    cpuTempPct: d.cpu?.temperature_percent ?? null,
    ram: d.memory?.used_percent ?? null,
    ts: Date.now(),
  });
}

export function startPolling(): void {
  clearTimers();
  const sec = get(refreshSeconds);

  // 즉시 1회 실행
  pollStatus();
  pollHistory();
  pollArtifacts();
  pollGpu();
  pollSystem();

  timers.push(
    window.setInterval(pollStatus, sec * 1000),
    window.setInterval(pollHistory, sec * 1000),
    window.setInterval(pollArtifacts, 30000),
    window.setInterval(pollGpu, sec * 1000),
    window.setInterval(pollSystem, sec * 1000),
  );
}

export function stopPolling(): void {
  clearTimers();
}

// refreshSeconds 변화에 자동 재시작
let unsub: (() => void) | null = null;
export function installPollingWatcher(): void {
  unsub?.();
  unsub = refreshSeconds.subscribe(() => {
    startPolling();
  });
}
