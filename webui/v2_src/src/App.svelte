<script lang="ts">
  import { onMount } from 'svelte';
  import Sidebar from '$layout/Sidebar.svelte';
  import Header from '$layout/Header.svelte';
  import HeroStrip from '$layout/HeroStrip.svelte';
  import LiveTrainingTab from '$tabs/LiveTrainingTab.svelte';
  import ForecastWorkbenchTab from '$tabs/ForecastWorkbenchTab.svelte';
  import StomDiagnosticsTab from '$tabs/StomDiagnosticsTab.svelte';
  import RLTradingTab from '$tabs/RLTradingTab.svelte';
  import DailyOhlcvTab from '$tabs/DailyOhlcvTab.svelte';
  import DailyRlGuideTab from '$tabs/DailyRlGuideTab.svelte';
  import ArtifactsModelsTab from '$tabs/ArtifactsModelsTab.svelte';
  import HistoryRunsTab from '$tabs/HistoryRunsTab.svelte';
  import SystemHealthTab from '$tabs/SystemHealthTab.svelte';
  import SettingsTab from '$tabs/SettingsTab.svelte';
  import DocsTab from '$tabs/DocsTab.svelte';
  import { activeTab, sidebarCollapsed } from '$lib/stores';
  import { installPollingWatcher, startPolling } from '$lib/polling';

  function routeTab(): string | null {
    if (typeof window === 'undefined') return null;
    const requested = new URLSearchParams(window.location.search).get('tab');
    if (requested === 'rl-lab' || requested === 'rl-trading') return 'rl';
    if (requested) return requested;
    const path = window.location.pathname.replace(/\/+$/, '');
    if (path === '/daily-rl-guide' || path === '/daily-ohlcv/rl-guide') return 'daily-rl-guide';
    if (path === '/daily-ohlcv' || path === '/daily') return 'daily-ohlcv';
    if (path === '/rl' || path === '/rl-lab' || path === '/v2/rl-trading' || path === '/v2/rl-lab') return 'rl';
    if (path === '/training' || path === '/dashboard') return 'live-training';
    return null;
  }

  onMount(() => {
    const requestedTab = routeTab();
    if (requestedTab) activeTab.set(requestedTab);
    installPollingWatcher();
    startPolling();
  });

  let tab = $state('live-training');
  activeTab.subscribe((v) => (tab = v));
  let collapsed = $state(false);
  sidebarCollapsed.subscribe((v) => (collapsed = v));
</script>

<div class="app-shell" data-sidebar={collapsed ? 'collapsed' : 'expanded'}>
  <Sidebar />
  <div class="main">
    <Header />
    <div class="page">
      {#if tab === 'live-training'}
        <HeroStrip />
        <LiveTrainingTab />
      {:else if tab === 'forecast'}
        <ForecastWorkbenchTab />
      {:else if tab === 'stom'}
        <StomDiagnosticsTab />
      {:else if tab === 'rl'}
        <RLTradingTab />
      {:else if tab === 'daily-ohlcv'}
        <DailyOhlcvTab />
      {:else if tab === 'daily-rl-guide'}
        <DailyRlGuideTab />
      {:else if tab === 'artifacts'}
        <ArtifactsModelsTab />
      {:else if tab === 'history'}
        <HistoryRunsTab />
      {:else if tab === 'system-health'}
        <SystemHealthTab />
      {:else if tab === 'settings'}
        <SettingsTab />
      {:else if tab === 'docs'}
        <DocsTab />
      {/if}
    </div>
  </div>
</div>

<style>
  .page {
    max-width: var(--content-max);
    margin: 0 auto;
    padding: 24px 28px 64px;
    display: flex;
    flex-direction: column;
    gap: 24px;
    width: 100%;
  }
  @media (max-width: 900px) {
    .page {
      padding: 16px 16px 48px;
      gap: 16px;
    }
  }
</style>
