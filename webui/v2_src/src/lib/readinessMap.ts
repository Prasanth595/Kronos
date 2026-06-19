// readiness.level → 색상/카피/Tailwind class 매핑.
// API 응답이 라벨/메시지를 이미 한국어로 보내지만, level 별 시각화 결정은 프론트엔드 책임.

export type ReadinessLevel = 'waiting' | 'training' | 'ready' | string;

interface ReadinessVisual {
  dotClass: 'lit-red' | 'lit-yellow' | 'lit-green';
  bgClass: string;
  textClass: string;
  shortLabel: string;
}

export function readinessVisual(level: ReadinessLevel | undefined): ReadinessVisual {
  switch (level) {
    case 'ready':
      return {
        dotClass: 'lit-green',
        bgClass: 'bg-success-bg',
        textClass: 'text-[#dcfce7]',
        shortLabel: '준비 완료',
      };
    case 'training':
      return {
        dotClass: 'lit-yellow',
        bgClass: 'bg-info-bg',
        textClass: 'text-[#93c5fd]',
        shortLabel: '학습 진행',
      };
    case 'waiting':
    default:
      return {
        dotClass: 'lit-red',
        bgClass: 'bg-warn-bg',
        textClass: 'text-[#fde68a]',
        shortLabel: '대기',
      };
  }
}
