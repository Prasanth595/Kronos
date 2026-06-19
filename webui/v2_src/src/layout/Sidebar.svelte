<script lang="ts">
  import { activeTab, sidebarCollapsed, sidebarMobileOpen, trainingStatus, metricsLatest } from '$lib/stores';
  import { ICONS, type IconName } from '$lib/icons';
  import { fmt } from '$lib/format';

  interface NavItem {
    id: string;
    label: string;
    icon: IconName;
    badge?: string | null;
    status?: 'live' | 'warn' | null;
  }

  interface NavGroup {
    label: string;
    items: NavItem[];
  }

  const groups: NavGroup[] = [
    {
      label: '오버뷰',
      items: [
        { id: 'live-training', label: '실시간 학습', icon: 'activity', badge: 'LIVE', status: 'live' },
        { id: 'forecast', label: '예측 워크벤치', icon: 'wand', badge: null },
      ],
    },
    {
      label: '분석',
      items: [
        { id: 'stom', label: '예측 진단', icon: 'pulse', badge: null },
        { id: 'artifacts', label: '아티팩트 & 모델', icon: 'package', badge: null },
        { id: 'history', label: '기록 & 런', icon: 'history', badge: null },
      ],
    },
    {
      label: '시스템',
      items: [
        { id: 'system-health', label: '시스템 상태', icon: 'cpu', badge: null },
        { id: 'settings', label: '설정', icon: 'settings', badge: null },
      ],
    },
    {
      label: '도움말',
      items: [
        { id: 'docs', label: '문서 · Wiki', icon: 'file', badge: null },
      ],
    },
    {
      label: '트레이딩',
      items: [
        { id: 'rl', label: 'RL Trading', icon: 'rocket', badge: '정규' },
        { id: 'daily-ohlcv', label: 'Daily OHLCV', icon: 'database', badge: '일봉' },
        { id: 'daily-rl-guide', label: '일봉 RL 설명서', icon: 'file', badge: 'Guide' },
      ],
    },
  ];

  let current = $state('live-training');
  activeTab.subscribe((v) => (current = v));

  let collapsed = $state(false);
  sidebarCollapsed.subscribe((v) => (collapsed = v));

  let mobileOpen = $state(false);
  sidebarMobileOpen.subscribe((v) => (mobileOpen = v));

  let status = $state<any>(null);
  trainingStatus.subscribe((v) => (status = v));

  let m = $state<any>({});
  metricsLatest.subscribe((v) => (m = v));

  function pick(id: string) {
    activeTab.set(id);
    sidebarMobileOpen.set(false);
  }
</script>

<aside class="sidebar" data-sidebar-collapsed={collapsed} data-mobile-open={mobileOpen}>
  <div class="brand">
    <div class="brand-mark">
      <svg viewBox="0 0 24 24" aria-hidden="true">{@html ICONS.flame}</svg>
    </div>
    {#if !collapsed}
      <div class="brand-text">
        <span class="brand-name">Kronos 대시보드</span>
        <span class="brand-tag">official · operations</span>
      </div>
    {/if}
  </div>

  {#each groups as g}
    <div class="sidebar-section">
      {#if !collapsed}
        <div class="sidebar-section-label">{g.label}</div>
      {/if}
      <div class="nav-list">
        {#each g.items as item}
          <button
            type="button"
            class="nav-item"
            data-tab={item.id}
            data-active={current === item.id ? 'true' : 'false'}
            data-status={item.status ?? ''}
            aria-current={current === item.id ? 'page' : undefined}
            onclick={() => pick(item.id)}
            title={collapsed ? item.label : undefined}
          >
            <span class="nav-icon">
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">{@html ICONS[item.icon]}</svg>
            </span>
            {#if !collapsed}
              <span class="nav-label">{item.label}</span>
              {#if item.badge}
                <span class="nav-badge">{item.badge}</span>
              {/if}
            {/if}
          </button>
        {/each}
      </div>
    </div>
  {/each}

  {#if !collapsed}
    <div class="sidebar-footer">
      <div class="run-card">
        <div class="run-card-row">
          <span class="signal" data-level={status?.readiness?.level === 'ready' ? 'live' : status?.readiness?.level === 'training' ? 'live' : 'waiting'}>
            <span class="light"></span>
            <span>{status?.status ?? '확인 중'}</span>
          </span>
        </div>
        {#if m.runName}
          <div class="run-name" title={m.runName}>{m.runName}</div>
        {/if}
        <div class="run-meta">
          {#if status?.latest_stage?.train_stage}
            <span>{status.latest_stage.train_stage}</span>
          {/if}
          {#if status?.latest_stage?.overall_percent != null}
            <span>{fmt.pct(status.latest_stage.overall_percent, 1)}</span>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</aside>
