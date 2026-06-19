<script lang="ts">
  import type { DailyDbSummaryResponse } from '$lib/dailyOhlcvApi';

  interface Props { summary: DailyDbSummaryResponse | null }
  let { summary }: Props = $props();
  const fmtNum = (v: unknown) => typeof v === 'number' ? v.toLocaleString('ko-KR') : '—';
</script>

<section class="panel" data-daily-ohlcv-db-card>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">D0 DB Analysis</div>
      <h2 class="text-h3">일봉 DB 분석 탭</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{summary?.decision_grade_status ?? 'WATCH'}</span>
  </div>
  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">테이블</div><div class="metric-value tnum">{fmtNum(summary?.table_count)}</div></div>
    <div class="metric"><div class="metric-label">총 행</div><div class="metric-value tnum">{fmtNum(summary?.total_rows)}</div></div>
    <div class="metric"><div class="metric-label">최초/최신</div><div class="metric-value tnum" style="font-size:20px">{summary?.first_date ?? '—'} → {summary?.latest_date ?? '—'}</div></div>
    <div class="metric"><div class="metric-label">가격 기준</div><div class="metric-value" style="font-size:22px">{summary?.price_basis ?? 'unknown'}</div></div>
    <div class="metric"><div class="metric-label">보정 확정</div><div class="metric-value" style="font-size:18px">{summary?.price_basis_status ?? 'UNKNOWN_CONFIRMED'}</div></div>
    <div class="metric"><div class="metric-label">수익률 라벨</div><div class="metric-value" style="font-size:16px">{summary?.decision_grade_return_status ?? 'BLOCKED_UNTIL_PRICE_BASIS_VERIFIED'}</div></div>
  </div>
  <div class="notice warn" style="margin-top:14px">
    <strong>가격 보정 상태:</strong> {summary?.price_basis_evidence ?? '원천 DB에 수정주가/원시가 여부가 명시되지 않아 decision-grade 수익률은 WATCH입니다.'}
    <br />
    <strong>차단 의미:</strong> adjusted/raw, split, dividend 기준이 증명되기 전 decision-grade return label과 model_build_allowed는 잠금 상태입니다.
  </div>
  <div class="split" data-daily-price-basis-usage style="margin-top:14px">
    <div>
      <h3 class="text-h4">가격 기준 사용 안내</h3>
      <div class="table-wrap mini">
        <table>
          <thead><tr><th>section</th><th>can do</th><th>must not do</th><th>next</th></tr></thead>
          <tbody>
            {#each summary?.price_basis_user_guidance ?? [] as row}
              <tr>
                <td>{row.section ?? 'D0'}</td>
                <td>{row.can_do ?? 'read-only evidence inspection'}</td>
                <td>{row.must_not_do ?? 'decision-grade return/model promotion'}</td>
                <td>{row.next_action ?? 'verify adjusted/raw/split/dividend policy'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
    <div>
      <h3 class="text-h4">허용/차단 용도</h3>
      <div class="notice" style="margin-top:8px">
        <strong>allowed:</strong> {(summary?.price_basis_allowed_uses ?? []).join(' · ') || 'read_only_db_coverage_and_quality_inspection'}
        <br />
        <strong>blocked:</strong> {(summary?.price_basis_blocked_uses ?? []).join(' · ') || 'decision_grade_return_labels · model_build_or_candidate_promotion'}
        <br />
        <strong>required evidence:</strong> {(summary?.price_basis_required_evidence ?? []).join(' · ') || 'official adjusted/raw/split/dividend policy evidence'}
      </div>
    </div>
  </div>
  <div class="split" style="margin-top:14px">
    <div>
      <h3 class="text-h4">분할/급등락 의심 창</h3>
      <p class="text-muted" style="margin:4px 0 8px">대표 split-like/discontinuity evidence입니다. corporate action proof가 아니며 price_basis UNKNOWN_CONFIRMED를 지지하는 WATCH 근거입니다.</p>
      <div class="table-wrap mini">
        <table>
          <thead><tr><th>table</th><th>date</th><th>ratio</th></tr></thead>
          <tbody>
            {#each summary?.material_unknown_adjustment_windows ?? [] as row}
              <tr>
                <td>{row.table}</td>
                <td>{row.previous_date} → {row.date}</td>
                <td>{Number(row.open_to_previous_close_ratio ?? 0).toFixed(2)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
    <div>
      <h3 class="text-h4">품질 플래그</h3>
      <div class="table-wrap mini">
        <table>
          <thead><tr><th>table</th><th>flag</th><th>value</th></tr></thead>
          <tbody>
            {#each summary?.quality_flags ?? [] as row}
              <tr><td>{row.table}</td><td>{row.flag}</td><td>{row.value}</td></tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</section>

<style>
  .split { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:16px; }
  .mini { max-height:260px; overflow:auto; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th, td { border-bottom:1px solid var(--border-faint); padding:6px; text-align:left; }
</style>
