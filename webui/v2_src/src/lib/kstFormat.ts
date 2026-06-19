// KST 포맷터 — eta_seconds, updated_at 등을 한국어 표시 계층에서만 변환.

export function toKst(isoOrTs: string | number | null | undefined): string {
  if (isoOrTs == null) return '-';
  try {
    const d = typeof isoOrTs === 'number' ? new Date(isoOrTs * 1000) : new Date(isoOrTs);
    if (isNaN(d.getTime())) return '-';
    return d.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
  } catch {
    return '-';
  }
}

export function nowKst(): string {
  return new Date().toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
}

// eta_seconds + 기준 시각 → 완료 예상 KST
export function finishKst(etaSeconds: number | null | undefined, baseIso?: string | null): string {
  if (etaSeconds == null || !(etaSeconds > 0)) return '-';
  const base = baseIso ? Date.parse(baseIso) : Date.now();
  const finishMs = (isNaN(base) ? Date.now() : base) + etaSeconds * 1000;
  return new Date(finishMs).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' });
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !(seconds > 0)) return '-';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}시간 ${m}분`;
}
