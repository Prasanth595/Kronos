<script lang="ts">
  import { refreshSeconds, theme, sidebarCollapsed } from '$lib/stores';

  let sec = $state(5);
  refreshSeconds.subscribe((v) => (sec = v));

  let currentTheme = $state<'light' | 'dark'>('light');
  theme.subscribe((v) => (currentTheme = v));

  let collapsed = $state(false);
  sidebarCollapsed.subscribe((v) => (collapsed = v));

  // 알림 권한 상태
  let notifPermission = $state<NotificationPermission | 'unsupported'>(
    typeof Notification !== 'undefined' ? Notification.permission : 'unsupported'
  );

  async function requestNotif() {
    if (typeof Notification === 'undefined') return;
    const p = await Notification.requestPermission();
    notifPermission = p;
  }

  function testNotif() {
    if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return;
    new Notification('Kronos 대시보드', {
      body: '알림 테스트입니다. 학습 단계 전환 시 이런 알림을 받습니다.',
      icon: undefined,
    });
  }

  const refreshOpts = [
    { v: 2, label: '2초', desc: '최소' },
    { v: 5, label: '5초', desc: '기본' },
    { v: 10, label: '10초', desc: '여유' },
    { v: 30, label: '30초', desc: '저빈도' },
    { v: 60, label: '60초', desc: '최대' },
  ];

  function setRefresh(v: number) {
    refreshSeconds.set(v);
  }

  function resetAll() {
    if (!confirm('모든 클라이언트 설정을 초기화합니다. 계속하시겠습니까?')) return;
    try {
      localStorage.removeItem('kronos-theme');
      theme.set('light');
      refreshSeconds.set(5);
      sidebarCollapsed.set(false);
    } catch {}
  }
</script>

<section class="page-hero">
  <div class="row" style="gap:10px">
    <span class="text-eyebrow">공식 기능</span>
    <span class="pill"><span class="dot" style="background:var(--info)"></span>클라이언트 저장 (localStorage)</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">설정</h1>
  <p class="text-muted" style="margin-top:6px">
    테마·새로고침 주기·알림 등 클라이언트 환경 설정. 모든 설정은 브라우저에 저장되며 서버 상태에 영향이 없습니다.
  </p>
</section>

<!-- ===== Appearance ===== -->
<section class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">APPEARANCE</div>
      <div class="card-title">외관</div>
    </div>
  </div>
  <div>
    <div class="lbl">테마</div>
    <div class="text-caption" style="margin-bottom:12px">우상단 헤더의 sun/moon 토글과 동일합니다.</div>
    <div class="grid-2-theme">
      <button class="theme-card" data-active={currentTheme === 'light' ? 'true' : 'false'} onclick={() => theme.set('light')}>
        <div class="theme-preview" style="background:#f8fafc;border:1px solid var(--border)">
          <div class="pv-side" style="background:#fff;border:1px solid #e5e7eb"></div>
          <div class="pv-main" style="background:#fff;border:1px solid #e5e7eb">
            <div class="pv-row" style="background:#cbd5e1;width:60%"></div>
            <div class="pv-row" style="background:oklch(56% 0.12 170);width:30%"></div>
            <div class="pv-row" style="background:#e2e8f0"></div>
          </div>
        </div>
        <div class="row spread" style="margin-top:8px">
          <span class="text-strong">라이트</span>
          <span class="text-caption">기본 · human-approachable</span>
        </div>
      </button>
      <button class="theme-card" data-active={currentTheme === 'dark' ? 'true' : 'false'} onclick={() => theme.set('dark')}>
        <div class="theme-preview" style="background:#0f172a;border:1px solid #1e293b">
          <div class="pv-side" style="background:#1e293b"></div>
          <div class="pv-main" style="background:#1e293b">
            <div class="pv-row" style="background:#475569;width:60%"></div>
            <div class="pv-row" style="background:oklch(72% 0.14 170);width:30%"></div>
            <div class="pv-row" style="background:#334155"></div>
          </div>
        </div>
        <div class="row spread" style="margin-top:8px">
          <span class="text-strong">다크</span>
          <span class="text-caption">학습 운영 / 야간</span>
        </div>
      </button>
    </div>
  </div>

  <div class="row-setting">
    <div>
      <div class="lbl">사이드바 기본 상태</div>
      <div class="desc">데스크탑(≥900px)에서 사이드바를 축소 상태로 시작</div>
    </div>
    <label class="switch">
      <input type="checkbox" checked={collapsed} onchange={(e) => sidebarCollapsed.set((e.currentTarget as HTMLInputElement).checked)} />
      <span class="switch-track"><span class="switch-thumb"></span></span>
    </label>
  </div>
</section>

<!-- ===== Refresh ===== -->
<section class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">REFRESH</div>
      <div class="card-title">새로고침 주기</div>
    </div>
    <span class="pill"><span class="dot"></span>현재 {sec}초</span>
  </div>
  <div class="text-caption" style="margin-bottom:8px">
    /api/training/status, /api/training/history, /api/training/gpu 폴링 간격. artifacts 폴링은 30초 고정.
  </div>
  <div class="row" style="gap:8px;flex-wrap:wrap">
    {#each refreshOpts as opt}
      <button
        type="button"
        class="seg-btn"
        data-active={sec === opt.v ? 'true' : 'false'}
        onclick={() => setRefresh(opt.v)}
      >
        <div class="text-mono" style="font-weight:600;font-size:14px">{opt.label}</div>
        <div class="text-caption" style="font-size:10px">{opt.desc}</div>
      </button>
    {/each}
  </div>
</section>

<!-- ===== Notifications ===== -->
<section class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">NOTIFICATIONS</div>
      <div class="card-title">브라우저 알림</div>
    </div>
    {#if notifPermission === 'granted'}
      <span class="pill success"><span class="dot"></span>허용됨</span>
    {:else if notifPermission === 'denied'}
      <span class="pill danger"><span class="dot"></span>차단됨</span>
    {:else if notifPermission === 'unsupported'}
      <span class="pill"><span class="dot"></span>미지원</span>
    {:else}
      <span class="pill warn"><span class="dot"></span>미설정</span>
    {/if}
  </div>
  <p class="text-muted" style="font-size:13px;line-height:1.55">
    학습 단계 전환 (tokenizer→predictor), checkpoint 생성, 학습 종료 시 브라우저 알림을 받습니다.
    탭이 백그라운드일 때만 발송됩니다.
  </p>
  <div class="row" style="gap:8px;flex-wrap:wrap;margin-top:10px">
    {#if notifPermission === 'default'}
      <button class="btn primary" onclick={requestNotif}>알림 허용 요청</button>
    {:else if notifPermission === 'granted'}
      <button class="btn" onclick={testNotif}>테스트 알림 보내기</button>
    {:else if notifPermission === 'denied'}
      <span class="text-caption">브라우저 설정에서 알림 권한을 다시 활성화하세요</span>
    {:else}
      <span class="text-caption">현재 브라우저가 Notification API 를 지원하지 않습니다</span>
    {/if}
  </div>
</section>

<!-- ===== Reset ===== -->
<section class="card">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">RESET</div>
      <div class="card-title">설정 초기화</div>
    </div>
  </div>
  <p class="text-muted" style="font-size:13px;line-height:1.55">
    저장된 모든 클라이언트 설정(테마·새로고침 주기·사이드바 상태)을 기본값으로 되돌립니다.
    학습 데이터와 서버 상태에는 영향이 없습니다.
  </p>
  <div style="margin-top:10px">
    <button class="btn danger" onclick={resetAll}>모든 설정 초기화</button>
  </div>
</section>

<!-- ===== P2+ Roadmap ===== -->
<section class="card" style="background:var(--surface-sunken);border-color:var(--border-faint)">
  <div class="card-header">
    <div>
      <div class="card-eyebrow">ROADMAP</div>
      <div class="card-title">차후 추가 예정 설정</div>
    </div>
    <span class="pill warn"><span class="dot"></span>계획</span>
  </div>
  <ul class="text-caption" style="line-height:1.8;padding-left:18px;margin:0">
    <li>언어 / 지역 (한국어 ↔ English)</li>
    <li>데이터 표시 정밀도 (loss 소수점 자릿수, KST 12/24h)</li>
    <li>예측 기본값 (lookback / pred_len / temperature / top_p 기본값 저장)</li>
    <li>고급 / 진단 (디버그 패널, 캐시 강제 갱신, dist 파일 hash 표시)</li>
  </ul>
</section>

<style>
  .page-hero { padding: 8px 0; }
  .lbl { font: 600 14px/1.3 var(--font-display); color: var(--fg-strong); }
  .desc { font-size: 12.5px; color: var(--muted); margin-top: 4px; max-width: 56ch; }
  .row-setting {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 18px;
    padding: 16px 0;
    align-items: center;
    border-top: 1px solid var(--border-faint);
    margin-top: 8px;
  }

  .grid-2-theme {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }
  @media (max-width: 640px) {
    .grid-2-theme { grid-template-columns: 1fr; }
  }
  .theme-card {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px;
    border-radius: 12px;
    border: 1.5px solid var(--border);
    background: var(--surface);
    cursor: pointer;
    transition: border-color var(--d-fast), transform var(--d-fast);
    text-align: left;
    width: 100%;
  }
  .theme-card:hover { transform: translateY(-1px); }
  .theme-card[data-active="true"] { border-color: var(--accent); box-shadow: var(--shadow-glow); }
  .theme-preview {
    height: 80px;
    border-radius: 8px;
    padding: 8px;
    display: flex;
    gap: 6px;
  }
  .theme-preview .pv-side { flex: 0 0 24%; border-radius: 6px; }
  .theme-preview .pv-main { flex: 1; border-radius: 6px; padding: 6px; display: flex; flex-direction: column; gap: 4px; }
  .theme-preview .pv-row { height: 6px; border-radius: 3px; }

  .switch {
    position: relative;
    display: inline-flex;
    align-items: center;
    cursor: pointer;
  }
  .switch input { position: absolute; opacity: 0; width: 0; height: 0; }
  .switch-track {
    width: 40px;
    height: 22px;
    border-radius: var(--r-pill);
    background: var(--surface-sunken);
    border: 1px solid var(--border);
    position: relative;
    transition: background var(--d-fast) var(--ease-out);
  }
  .switch-thumb {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--surface);
    box-shadow: var(--shadow-sm);
    transition: transform var(--d-fast) var(--ease-out);
  }
  .switch input:checked + .switch-track {
    background: var(--accent);
    border-color: var(--accent);
  }
  .switch input:checked + .switch-track .switch-thumb {
    transform: translateX(18px);
    background: white;
  }

  .seg-btn {
    flex: 0 0 auto;
    min-width: 80px;
    padding: 10px 14px;
    border-radius: var(--r-sm);
    border: 1.5px solid var(--border);
    background: var(--surface);
    cursor: pointer;
    transition: border-color var(--d-fast), background var(--d-fast);
    text-align: center;
  }
  .seg-btn:hover { border-color: var(--border-strong); }
  .seg-btn[data-active="true"] {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--accent-strong);
  }
</style>
