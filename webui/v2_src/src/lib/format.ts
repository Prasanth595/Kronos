// 공식 대시보드 디자인 시스템 — 한국어 우선 포맷터.
// kstFormat.ts 를 흡수하면서 정수/실수/퍼센트/바이트/duration/상대시간 추가.

export const fmt = {
  int(v: number | null | undefined): string {
    if (v == null || isNaN(v)) return '-';
    return new Intl.NumberFormat('ko-KR').format(Math.round(v));
  },
  num(v: number | null | undefined, d: number = 2): string {
    if (v == null || isNaN(v)) return '-';
    return new Intl.NumberFormat('ko-KR', {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    }).format(v);
  },
  pct(v: number | null | undefined, d: number = 1): string {
    if (v == null || isNaN(v)) return '-';
    return new Intl.NumberFormat('ko-KR', {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    }).format(v) + '%';
  },
  bytes(mib: number | null | undefined): string {
    if (mib == null || isNaN(mib)) return '-';
    if (mib >= 1024) return (mib / 1024).toFixed(2) + ' GiB';
    return mib.toFixed(0) + ' MiB';
  },
  duration(seconds: number | null | undefined): string {
    if (seconds == null || !(seconds > 0)) return '-';
    const s = Math.max(0, Math.floor(seconds));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    if (h > 0) return `${h}시간 ${m}분`;
    if (m > 0) return `${m}분 ${ss}초`;
    return `${ss}초`;
  },
  durationCompact(seconds: number | null | undefined): string {
    if (seconds == null || !(seconds > 0)) return '-';
    const s = Math.max(0, Math.floor(seconds));
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const ss = s % 60;
    if (h > 0) return `${h}h ${m.toString().padStart(2, '0')}m`;
    if (m > 0) return `${m}m ${ss.toString().padStart(2, '0')}s`;
    return `${ss}s`;
  },
  kst(ts: string | number | Date | null | undefined): string {
    if (ts == null) return '-';
    const d = ts instanceof Date ? ts : new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
    if (isNaN(d.getTime())) return '-';
    return d.toLocaleString('ko-KR', {
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Seoul',
    });
  },
  kstShort(ts: string | number | Date | null | undefined): string {
    if (ts == null) return '-';
    const d = ts instanceof Date ? ts : new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
    if (isNaN(d.getTime())) return '-';
    return d.toLocaleString('ko-KR', {
      hour12: false,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Seoul',
    });
  },
  kstTime(ts: string | number | Date | null | undefined): string {
    if (ts == null) return '-';
    const d = ts instanceof Date ? ts : new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
    if (isNaN(d.getTime())) return '-';
    return d.toLocaleTimeString('ko-KR', { hour12: false, timeZone: 'Asia/Seoul' });
  },
  relative(ts: string | number | Date | null | undefined): string {
    if (ts == null) return '-';
    const d = ts instanceof Date ? ts : new Date(typeof ts === 'number' && ts < 1e12 ? ts * 1000 : ts);
    if (isNaN(d.getTime())) return '-';
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return `${Math.floor(diff)}초 전`;
    if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
    return `${Math.floor(diff / 86400)}일 전`;
  },
  finishKst(etaSeconds: number | null | undefined, baseIso?: string | null): string {
    if (etaSeconds == null || !(etaSeconds > 0)) return '-';
    const base = baseIso ? Date.parse(baseIso) : Date.now();
    const finishMs = (isNaN(base) ? Date.now() : base) + etaSeconds * 1000;
    return new Date(finishMs).toLocaleString('ko-KR', {
      hour12: false,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      timeZone: 'Asia/Seoul',
    });
  },
};

// 하위 호환 — 기존 kstFormat.ts 의 export 이름 유지
export const toKst = fmt.kst;
export const nowKst = () => fmt.kst(Date.now());
export const finishKst = fmt.finishKst;
export const formatDuration = fmt.duration;
