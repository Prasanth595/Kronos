<script lang="ts">
  import type { DailyUniverseResponse } from '$lib/dailyOhlcvApi';

  interface Props {
    universe: DailyUniverseResponse | null;
    onSymbolSelect?: (code: string) => void;
  }
  let { universe, onSymbolSelect }: Props = $props();
  const fmtNum = (v: unknown) => typeof v === 'number' ? v.toLocaleString('ko-KR') : '—';
  const defaultAllowedUses = ['research_universe_preview', 'exclusion_reason_review', 'quarantine_backlog_triage', 'dashboard_evidence_navigation'];
  const defaultBlockedUses = ['model_build_or_candidate_promotion', 'paper_forward_or_live_readiness_claims', 'official_common_equity_certification_claims'];
  const defaultRequiredEvidence = [
    'official_or_manual_krx_csv_with_code_name_market_instrument_type',
    'six_character_string_codes_preserving_leading_zeros',
    'kospi_kosdaq_common_equity_instrument_type_review',
    'quarantine_artifact_for_unmatched_or_excluded_symbols',
    'dated_manifest_with_metadata_sha_and_review_status',
  ];
  const listOrFallback = (values: readonly string[] | undefined, fallback: readonly string[]) => values?.length ? values : fallback;
  const guidanceValue = (row: Readonly<Record<string, unknown>>, key: string) => typeof row[key] === 'string' ? row[key] : String(row[key] ?? '—');
</script>

<!-- Universe verdict marker: WATCH_HEURISTIC_UNIVERSE -->
<section class="panel" data-daily-ohlcv-universe-card>
  <div class="panel-head">
    <div>
      <div class="text-eyebrow">D1 Universe Management</div>
      <h2 class="text-h3">코스피·코스닥 보통주 유니버스</h2>
    </div>
    <span class="pill warn"><span class="dot"></span>{universe?.verdict ?? 'WATCH'}</span>
  </div>
  <p class="text-muted" style="margin-top:8px">ETF/ETN/펀드/스팩/리츠/우선주/미확인/Q상품은 기본 제외합니다. 공식 KRX 또는 수동 검토 전까지 포함 유니버스도 WATCH입니다.</p>
  <div class="grid-4-kpi" style="margin-top:16px">
    <div class="metric"><div class="metric-label">포함</div><div class="metric-value tnum">{fmtNum(universe?.include_count)}</div></div>
    <div class="metric"><div class="metric-label">제외</div><div class="metric-value tnum">{fmtNum(universe?.exclude_count)}</div></div>
    <div class="metric"><div class="metric-label">stockinfo 매칭</div><div class="metric-value tnum">{fmtNum(universe?.stockinfo_matched_table_count)}</div></div>
    <div class="metric"><div class="metric-label">미매칭 격리</div><div class="metric-value tnum">{fmtNum(universe?.unmatched_quarantine_count)}</div></div>
    <div class="metric"><div class="metric-label">공식 메타데이터</div><div class="metric-value" style="font-size:18px">{universe?.official_metadata_status ?? 'MISSING'}</div></div>
    <div class="metric"><div class="metric-label">공식 미매칭</div><div class="metric-value tnum">{fmtNum(universe?.official_metadata_unmatched_table_count)}</div></div>
    <div class="metric"><div class="metric-label">격리 artifact</div><div class="metric-value tnum">{fmtNum(universe?.quarantine_artifact_count)}</div></div>
    <div class="metric"><div class="metric-label">공식 coverage</div><div class="metric-value" style="font-size:18px">{universe?.official_metadata_coverage_status ?? 'MISSING'}</div></div>
    <div class="metric"><div class="metric-label">검증 확정</div><div class="metric-value" style="font-size:18px">{universe?.universe_certification_status ?? 'BLOCKED'}</div></div>
  </div>
  <div class="notice warn" style="margin-top:14px">
    <strong>공식 검증:</strong> KRX/manual CSV ingestion contract는 <code>code,name,market,instrument_type</code>입니다. 현재 공식 메타데이터가 없으면 <code>WATCH_HEURISTIC_UNIVERSE</code>와 quarantine evidence를 유지합니다.
  </div>
  <div class="usage-grid" data-daily-universe-review-contract>
    <div class="notice">
      <strong>허용 사용</strong>
      <ul>
        {#each listOrFallback(universe?.universe_allowed_uses, defaultAllowedUses) as item}
          <li>{item}</li>
        {/each}
      </ul>
    </div>
    <div class="notice warn">
      <strong>차단 사용</strong>
      <ul>
        {#each listOrFallback(universe?.universe_blocked_uses, defaultBlockedUses) as item}
          <li>{item}</li>
        {/each}
      </ul>
    </div>
    <div class="notice">
      <strong>필수 증거</strong>
      <ul>
        {#each listOrFallback(universe?.universe_required_evidence, defaultRequiredEvidence) as item}
          <li>{item}</li>
        {/each}
      </ul>
    </div>
  </div>
  <div class="table-wrap mini" style="margin-top:12px" data-daily-universe-user-guidance>
    <table>
      <thead><tr><th>section</th><th>meaning</th><th>action</th></tr></thead>
      <tbody>
        {#each universe?.universe_user_guidance ?? [] as row}
          <tr>
            <td>{guidanceValue(row, 'section')}</td>
            <td>{guidanceValue(row, 'meaning')}</td>
            <td>{guidanceValue(row, 'action')}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  <div class="split" style="margin-top:14px">
    <div>
      <h3 class="text-h4">제외 사유</h3>
      <div class="reason-grid">
        {#each Object.entries(universe?.counts_by_exclusion_reason ?? {}) as [reason, count]}
          <div class="reason"><span>{reason}</span><b class="tnum">{fmtNum(count)}</b></div>
        {/each}
      </div>
    </div>
    <div>
      <h3 class="text-h4">미리보기</h3>
      <div class="table-wrap mini">
        <table>
          <thead><tr><th>code</th><th>name</th><th>type</th><th>include</th><th>review</th><th>drilldown</th></tr></thead>
          <tbody>
            {#each universe?.symbols ?? [] as row}
              <tr>
                <td class="tnum">{row.code}</td>
                <td>{row.name ?? '—'}</td>
                <td>{row.instrument_type}</td>
                <td>{row.include ? 'IN' : 'OUT'}</td>
                <td>{row.review_status}</td>
                <td>
                  <button
                    type="button"
                    class="link-button"
                    data-daily-symbol-drilldown
                    onclick={() => onSymbolSelect?.(String(row.code ?? ''))}
                  >
                    상세
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</section>

<style>
  .split { display:grid; grid-template-columns: minmax(260px, 0.8fr) minmax(320px, 1.2fr); gap:16px; }
  .usage-grid { display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap:12px; margin-top:12px; }
  .reason-grid { display:grid; gap:8px; }
  .reason { display:flex; justify-content:space-between; gap:12px; border:1px solid var(--border-faint); border-radius:var(--r-md); padding:8px 10px; font-size:12px; }
  .mini { max-height:320px; overflow:auto; }
  table { width:100%; border-collapse:collapse; font-size:12px; }
  th, td { border-bottom:1px solid var(--border-faint); padding:6px; text-align:left; }
  .link-button { border:0; background:transparent; color:var(--info); padding:0; font:inherit; cursor:pointer; }
  @media (max-width: 900px) { .split { grid-template-columns:1fr; } }
  @media (max-width: 1100px) { .usage-grid { grid-template-columns:1fr; } }
</style>
