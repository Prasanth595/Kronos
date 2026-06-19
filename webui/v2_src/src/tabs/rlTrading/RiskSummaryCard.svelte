<script lang="ts">
  import { num } from '$lib/rlRows';
  import type { RlRiskPolicySummary, RlRunRecord } from '$lib/rlApi';

  interface Props { readonly ruleRun: RlRunRecord | null; readonly selectedLabel: string }
  let { ruleRun, selectedLabel }: Props = $props();
  const risk = $derived<RlRiskPolicySummary>(ruleRun?.strategy_context?.risk_policy_summary ?? {});
</script>

<section class="card" data-rl-rule-risk-card>
  <div class="card-header">
    <div><div class="card-eyebrow">RULE MAINLINE RISK</div><div class="card-title">ts_imb RULE baseline sizing</div></div>
    <span class="pill success"><span class="dot"></span>{selectedLabel || 'RULE / RL separation'}</span>
  </div>
  <div class="mini-grid">
    <div><span>f</span><strong>{num(risk.per_trade_fraction_pct, 1)}%</strong></div>
    <div><span>K</span><strong>{num(risk.max_concurrent, 0)}</strong></div>
    <div><span>Daily loss</span><strong>{num(risk.daily_loss_limit_pct, 1)}%</strong></div>
    <div><span>Cost</span><strong>{num(risk.cost_bps, 0)}bp</strong></div>
    <div><span>TP / SL</span><strong>TP{num(risk.tp_pct, 0)} / SL{num(risk.sl_pct, 0)}</strong></div>
    <div><span>Risk unit</span><strong>{num(risk.risk_unit_account_pct, 3)}%</strong></div>
  </div>
  <p class="text-caption">이 정책은 RULE mainline 기준 노출값입니다. RL 결과가 이 값을 대체하거나 live-ready/profit model임을 뜻하지 않습니다.</p>
</section>
