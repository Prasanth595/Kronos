<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import * as echarts from 'echarts';

  interface Props {
    option: any;
    height?: string;
    className?: string;
  }

  let { option, height = '320px', className = '' }: Props = $props();

  let container: HTMLDivElement | undefined = $state();
  let chart: echarts.ECharts | null = null;
  let observer: ResizeObserver | null = null;
  let frame: number | null = null;

  function hasRenderableOption(value: any): boolean {
    return value != null && typeof value === 'object' && Object.keys(value).length > 0;
  }

  async function applyOption(): Promise<void> {
    if (!chart || !container || !hasRenderableOption(option)) return;

    await tick();

    if (frame != null && typeof cancelAnimationFrame !== 'undefined') {
      cancelAnimationFrame(frame);
    }

    const render = () => {
      if (!chart || !container || !hasRenderableOption(option)) return;
      chart.resize();
      chart.setOption(option, {
        notMerge: false,
        lazyUpdate: true,
        replaceMerge: ['xAxis', 'yAxis', 'series', 'graphic'],
      });
    };

    if (typeof requestAnimationFrame === 'undefined') {
      render();
      return;
    }

    frame = requestAnimationFrame(render);
  }

  function onThemeChange(_e: Event) {
    // 옵션 자체는 CSS 변수를 참조하지 않고 그대로 들어오므로
    // 부모가 option 을 재계산해서 reactive 로 흘려보내면 자동 갱신됨.
    // 여기서는 레이아웃/옵션 재적용을 함께 트리거한다.
    void applyOption();
  }

  onMount(() => {
    if (!container) return;
    chart = echarts.init(container, null, { renderer: 'canvas' });
    observer = new ResizeObserver(() => void applyOption());
    observer.observe(container);
    document.addEventListener('kronos:theme', onThemeChange);
    void applyOption();
  });

  onDestroy(() => {
    if (frame != null && typeof cancelAnimationFrame !== 'undefined') {
      cancelAnimationFrame(frame);
    }
    observer?.disconnect();
    chart?.dispose();
    document.removeEventListener('kronos:theme', onThemeChange);
  });

  $effect(() => {
    void option;
    void applyOption();
  });
</script>

<div bind:this={container} class={className} style="width: 100%; height: {height};"></div>
