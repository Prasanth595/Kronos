<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    activeTab,
    trainingStatus,
    lastUpdatedAt,
    sidebarCollapsed,
    sidebarMobileOpen,
    theme,
    toggleTheme,
  } from '$lib/stores';
  import { ICONS } from '$lib/icons';
  import { fmt } from '$lib/format';

  const tabLabels: Record<string, string> = {
    'live-training': '실시간 학습',
    forecast: '예측 워크벤치',
    stom: '예측 진단',
    rl: 'RL Trading',
    'daily-ohlcv': 'Daily OHLCV',
    'daily-rl-guide': '일봉 RL 설명서',
    artifacts: '아티팩트 & 모델',
    history: '기록 & 런',
    'system-health': '시스템 상태',
    settings: '설정',
    docs: '문서 · Wiki',
  };

  let tab = $state('live-training');
  activeTab.subscribe((v) => (tab = v));
  let status = $state<any>(null);
  trainingStatus.subscribe((v) => (status = v));
  let last = $state('-');
  lastUpdatedAt.subscribe((v) => (last = v));
  let currentTheme = $state<'light' | 'dark'>('light');
  theme.subscribe((v) => (currentTheme = v));

  let now = $state(fmt.kstTime(Date.now()));
  let timer: number | undefined;
  onMount(() => {
    timer = window.setInterval(() => (now = fmt.kstTime(Date.now())), 1000);
  });
  onDestroy(() => {
    if (timer != null) clearInterval(timer);
  });

  function toggleSidebar(): void {
    if (window.matchMedia('(max-width: 900px)').matches) {
      sidebarMobileOpen.update((v) => !v);
    } else {
      sidebarCollapsed.update((v) => !v);
    }
  }
</script>

<header class="header">
  <button
    type="button"
    class="btn icon ghost"
    aria-label="사이드바 토글"
    onclick={toggleSidebar}
    title="사이드바 토글"
  >
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">{@html ICONS.menu}</svg>
  </button>

  <div class="crumb">
    <span class="crumb-root">Kronos</span>
    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true" class="crumb-sep">{@html ICONS.chevron_right}</svg>
    <span class="crumb-current">{tabLabels[tab] ?? tab}</span>
  </div>

  <div class="header-meta">
    {#if status?.readiness?.level}
      <span
        class="signal"
        data-level={status.readiness.level === 'ready' ? 'live' : status.readiness.level === 'training' ? 'live' : 'waiting'}
      >
        <span class="light"></span>
        <span>{status.readiness.label ?? status.readiness.level}</span>
      </span>
    {/if}
  </div>

  <div class="header-actions">
    <span class="header-stat" title="현재 시각 (KST)">
      <span class="header-stat-dot live"></span>
      <span class="text-mono tnum">{now}</span>
    </span>
    <span class="header-stat text-caption" title="마지막 갱신">
      갱신 <span class="text-mono">{last}</span>
    </span>
    <button
      type="button"
      class="btn icon ghost"
      data-theme-toggle
      onclick={toggleTheme}
      aria-label="테마 토글"
      title="라이트/다크 전환"
    >
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" style:display={currentTheme === 'dark' ? 'none' : ''}>
        {@html ICONS.sun}
      </svg>
      <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" style:display={currentTheme === 'dark' ? '' : 'none'}>
        {@html ICONS.moon}
      </svg>
    </button>
  </div>
</header>

<style>
  .crumb {
    display: flex;
    align-items: center;
    gap: 8px;
    font: 600 15px/1.3 var(--font-display);
    color: var(--fg);
    flex: 1;
    min-width: 0;
  }
  .crumb-root {
    color: var(--muted);
    font-weight: 500;
  }
  .crumb-sep {
    color: var(--faint);
    flex-shrink: 0;
  }
  .crumb-current {
    color: var(--fg-strong);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .header-meta {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .header-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
  }
  .header-stat {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: var(--r-pill);
    background: var(--surface-sunken);
    color: var(--fg);
    font-size: 12px;
  }
  .header-stat-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--muted);
  }
  .header-stat-dot.live {
    background: var(--success);
    box-shadow: 0 0 6px var(--success);
  }
  @media (max-width: 640px) {
    .header-stat.text-caption {
      display: none;
    }
  }
</style>
