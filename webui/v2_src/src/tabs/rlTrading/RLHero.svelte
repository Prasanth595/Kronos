<script lang="ts">
  interface Props { readonly progressPct: number; readonly costGatePassCount: number }
  let { progressPct, costGatePassCount }: Props = $props();
</script>

<section class="page-hero" data-rl-trading-tab>
  <div class="row" style="gap:10px;flex-wrap:wrap">
    <span class="text-eyebrow">RULE / RL EVIDENCE · 정규 기능 · Kronos 비의존 · not live-ready</span>
    <span class="pill success"><span class="dot"></span>RULE MAINLINE</span>
    <span class="pill accent"><span class="dot"></span>RL EXPERIMENT</span>
    <span class="pill danger"><span class="dot"></span>NO-GO 공개</span>
    <span class="pill info"><span class="dot"></span>ts_imb RULE baseline · 23bp</span>
    <span class="pill {costGatePassCount ? 'success' : 'warn'}"><span class="dot"></span>23bp cost gate</span>
    <span class="pill {progressPct === 100 ? 'success' : 'warn'}"><span class="dot"></span>진행률 {Math.round(progressPct)}%</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">강화학습</h1>
  <p class="text-muted" style="margin-top:6px">
    ts_imb RULE baseline은 강화학습 모델이 아닌 RULE MAINLINE입니다. RL EXPERIMENT는 DQN/PPO와 호가창 실험을 비교·반증하는 연구 산출물이며, NO-GO와 not live-ready guardrail을 먼저 표시합니다.
  </p>
</section>
