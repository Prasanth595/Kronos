<script lang="ts">
  import { onMount } from 'svelte';
  import { marked } from 'marked';
  import { fmt } from '$lib/format';
  import { ICONS } from '$lib/icons';
  import { activeTab } from '$lib/stores';

  interface DocItem {
    slug: string;
    name: string;
    title: string;
    size_bytes: number;
    modified_at: number;
    order: number;
  }

  let docs = $state<DocItem[]>([]);
  let loading = $state(false);
  let listError = $state<string | null>(null);

  let selectedSlug = $state<string>('00-index');
  let content = $state<string>('');
  let contentError = $state<string | null>(null);
  let loadingContent = $state(false);

  // marked 설정 — XSS 방지를 위해 HTML 렌더링은 안전한 옵션
  marked.setOptions({
    gfm: true,
    breaks: false,
  });

  async function loadList() {
    loading = true;
    listError = null;
    try {
      const r = await fetch('/api/docs/list');
      if (!r.ok) {
        listError = `HTTP ${r.status}`;
        return;
      }
      const d = await r.json();
      docs = Array.isArray(d.docs) ? d.docs : [];
      if (!d.available) listError = d.message ?? '문서가 없습니다';
    } catch (e: any) {
      listError = e?.message ?? '문서 목록 조회 실패';
    } finally {
      loading = false;
    }
  }

  async function loadDoc(slug: string) {
    selectedSlug = slug;
    loadingContent = true;
    contentError = null;
    content = '';
    try {
      const r = await fetch(`/api/docs/read?slug=${encodeURIComponent(slug)}`);
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        contentError = err?.error ?? `HTTP ${r.status}`;
        return;
      }
      const d = await r.json();
      content = d.content ?? '';
    } catch (e: any) {
      contentError = e?.message ?? '문서 조회 실패';
    } finally {
      loadingContent = false;
    }
  }

  onMount(async () => {
    await loadList();
    if (docs.length > 0) {
      // 00-index 우선, 없으면 첫 항목
      const idx = docs.find((d) => d.slug === '00-index') ?? docs[0];
      await loadDoc(idx.slug);
    }
  });

  // 카테고리 분류 (order prefix 기준)
  const categories: { label: string; range: [number, number] }[] = [
    { label: '🌅 기초', range: [0, 2] },
    { label: '📊 STOM 데이터', range: [3, 5] },
    { label: '🛠 운영', range: [6, 8] },
    { label: '🔌 레퍼런스', range: [9, 99] },
  ];

  // 카테고리별로 문서 그룹화
  let groupedDocs = $derived.by(() => {
    return categories.map((cat) => ({
      label: cat.label,
      docs: docs.filter((d) => d.order >= cat.range[0] && d.order <= cat.range[1]),
    })).filter((g) => g.docs.length > 0);
  });

  // 렌더링된 HTML (marked 결과). 내부 [텍스트](slug) 링크를 클릭 가능하게 처리
  let renderedHtml = $derived.by(() => {
    if (!content) return '';
    let html = marked.parse(content) as string;
    // 마크다운 내부의 [텍스트](XX-slug) 링크를 data-doc-slug 로 변환 (외부 URL 제외)
    html = html.replace(/<a href="([^"]+)">/g, (match, href) => {
      if (href.startsWith('http') || href.startsWith('/') || href.startsWith('#')) {
        return match;
      }
      // 마크다운 내부 링크 (예: 00-index, 01-overview.md)
      const slug = href.replace(/\.md$/, '');
      return `<a href="#" data-doc-slug="${slug}" class="docs-internal-link">`;
    });
    return html;
  });

  // 내부 링크 클릭 → loadDoc 호출
  function handleContentClick(e: MouseEvent) {
    const t = e.target as HTMLElement;
    const link = t.closest?.('a.docs-internal-link') as HTMLAnchorElement | null;
    if (link) {
      e.preventDefault();
      const slug = link.dataset.docSlug;
      if (slug) loadDoc(slug);
    }
  }

  let currentDoc = $derived(docs.find((d) => d.slug === selectedSlug));
</script>

<section class="page-hero">
  <div class="row" style="gap:10px;flex-wrap:wrap">
    <span class="text-eyebrow">공식 문서</span>
    <span class="pill"><span class="dot" style="background:var(--info)"></span>/api/docs/* · read-only</span>
    <span class="pill"><span class="dot" style="background:var(--success)"></span>{docs.length} 개 문서</span>
  </div>
  <h1 class="text-h2" style="margin-top:8px">문서 · Wiki</h1>
  <p class="text-muted" style="margin-top:6px">
    Kronos 프로젝트의 모든 노하우와 시행착오를 모은 살아있는 wiki. 마크다운 원본은 <code class="text-mono">docs/wiki/</code> 에 보관되며,
    파일을 직접 수정하면 새로고침으로 즉시 반영됩니다.
  </p>
</section>

<section class="docs-layout">
  <!-- ── Left: 문서 목록 ── -->
  <aside class="docs-nav">
    {#if loading}
      <div class="text-muted" style="padding:24px 12px;text-align:center">목록 불러오는 중...</div>
    {:else if listError}
      <div class="card" style="padding:12px;border-color:var(--danger-soft)">
        <div class="text-caption" style="color:var(--danger)">⚠ {listError}</div>
        <button class="btn sm" onclick={loadList} style="margin-top:8px">다시 시도</button>
      </div>
    {:else}
      {#each groupedDocs as group}
        <div class="docs-nav-group">
          <div class="docs-nav-label">{group.label}</div>
          {#each group.docs as d}
            <button
              type="button"
              class="docs-nav-item"
              data-active={selectedSlug === d.slug ? 'true' : 'false'}
              onclick={() => loadDoc(d.slug)}
              title={d.name}
            >
              <span class="docs-nav-num text-mono">{String(d.order).padStart(2, '0')}</span>
              <span class="docs-nav-title">{d.title}</span>
            </button>
          {/each}
        </div>
      {/each}
      <div class="docs-nav-footer">
        <button class="btn ghost sm" onclick={loadList} style="width:100%">
          <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">{@html ICONS.refresh}</svg>
          목록 갱신
        </button>
      </div>
    {/if}
  </aside>

  <!-- ── Right: 문서 본문 ── -->
  <main class="docs-content card">
    {#if loadingContent}
      <div class="text-muted" style="padding:40px;text-align:center">문서 불러오는 중...</div>
    {:else if contentError}
      <div class="text-caption" style="color:var(--danger);padding:20px">⚠ {contentError}</div>
    {:else if !content}
      <div class="text-muted" style="padding:40px;text-align:center">좌측에서 문서를 선택하세요</div>
    {:else}
      <div class="docs-meta">
        {#if currentDoc}
          <span class="card-eyebrow">{currentDoc.slug}</span>
          <span class="text-caption">
            {fmt.bytes(currentDoc.size_bytes / 1024)} ·
            {fmt.relative(currentDoc.modified_at * 1000)} 수정
          </span>
        {/if}
      </div>
      <article class="markdown-body" role="article" onclick={handleContentClick}>
        {@html renderedHtml}
      </article>
    {/if}
  </main>
</section>

<style>
  .page-hero { padding: 8px 0; }

  .docs-layout {
    display: grid;
    grid-template-columns: 260px minmax(0, 1fr);
    gap: 16px;
    align-items: start;
  }
  @media (max-width: 900px) {
    .docs-layout { grid-template-columns: 1fr; }
  }

  .docs-nav {
    position: sticky;
    top: 80px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    padding: 12px 8px;
    max-height: calc(100vh - 120px);
    overflow-y: auto;
  }
  @media (max-width: 900px) {
    .docs-nav { position: static; max-height: none; }
  }
  .docs-nav-group {
    margin-bottom: 12px;
  }
  .docs-nav-label {
    font: 600 11px/1.2 var(--font-display);
    color: var(--muted);
    padding: 6px 10px;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .docs-nav-item {
    display: flex;
    gap: 10px;
    width: 100%;
    padding: 8px 10px;
    border-radius: var(--r-sm);
    background: transparent;
    border: 1px solid transparent;
    cursor: pointer;
    text-align: left;
    font-size: 13px;
    color: var(--fg);
    transition: background var(--d-fast), border-color var(--d-fast);
    align-items: flex-start;
    line-height: 1.35;
  }
  .docs-nav-item:hover { background: var(--surface-sunken); }
  .docs-nav-item[data-active="true"] {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent-strong);
    font-weight: 600;
  }
  .docs-nav-num {
    color: var(--muted);
    font-size: 11px;
    flex-shrink: 0;
    padding-top: 1px;
  }
  .docs-nav-title { flex: 1; min-width: 0; }
  .docs-nav-footer {
    padding-top: 8px;
    border-top: 1px solid var(--border-faint);
    margin-top: 8px;
  }

  .docs-content {
    padding: 24px 32px 48px;
  }
  @media (max-width: 640px) {
    .docs-content { padding: 16px 16px 32px; }
  }
  .docs-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    padding-bottom: 12px;
    margin-bottom: 16px;
    border-bottom: 1px solid var(--border-faint);
    flex-wrap: wrap;
  }

  /* ── Markdown body ─────────────────────────────────────────── */
  .markdown-body {
    color: var(--fg);
    line-height: 1.7;
    font-size: 14.5px;
  }
  .markdown-body :global(h1) {
    font: 700 30px/1.25 var(--font-display);
    letter-spacing: -0.02em;
    color: var(--fg-strong);
    margin: 0 0 16px;
    padding-bottom: 10px;
    border-bottom: 1px solid var(--border-faint);
  }
  .markdown-body :global(h2) {
    font: 700 22px/1.3 var(--font-display);
    letter-spacing: -0.012em;
    color: var(--fg-strong);
    margin: 28px 0 12px;
  }
  .markdown-body :global(h3) {
    font: 600 17px/1.35 var(--font-display);
    color: var(--fg-strong);
    margin: 22px 0 10px;
  }
  .markdown-body :global(h4) {
    font: 600 15px/1.35 var(--font-display);
    color: var(--fg-strong);
    margin: 18px 0 8px;
  }
  .markdown-body :global(p) {
    margin: 10px 0;
  }
  .markdown-body :global(ul),
  .markdown-body :global(ol) {
    padding-left: 22px;
    margin: 10px 0;
  }
  .markdown-body :global(li) {
    margin: 4px 0;
    list-style: disc;
  }
  .markdown-body :global(ol li) {
    list-style: decimal;
  }
  .markdown-body :global(a) {
    color: var(--accent-strong);
    text-decoration: underline;
    text-decoration-color: var(--accent-soft);
    text-underline-offset: 3px;
  }
  .markdown-body :global(a:hover) {
    text-decoration-color: var(--accent);
  }
  .markdown-body :global(code) {
    font-family: var(--font-mono);
    font-size: 0.9em;
    background: var(--surface-sunken);
    padding: 2px 6px;
    border-radius: 4px;
    color: var(--accent-strong);
  }
  .markdown-body :global(pre) {
    background: var(--surface-sunken);
    border: 1px solid var(--border-faint);
    border-radius: var(--r-md);
    padding: 14px 16px;
    overflow-x: auto;
    margin: 12px 0;
    font-size: 12.5px;
    line-height: 1.55;
  }
  .markdown-body :global(pre code) {
    background: none;
    padding: 0;
    color: var(--fg);
  }
  .markdown-body :global(blockquote) {
    border-left: 3px solid var(--accent);
    background: var(--accent-soft);
    padding: 10px 16px;
    margin: 14px 0;
    border-radius: 0 var(--r-sm) var(--r-sm) 0;
    color: var(--fg);
  }
  .markdown-body :global(blockquote p) {
    margin: 4px 0;
  }
  .markdown-body :global(table) {
    width: 100%;
    border-collapse: collapse;
    margin: 14px 0;
    font-size: 13px;
  }
  .markdown-body :global(th),
  .markdown-body :global(td) {
    padding: 8px 12px;
    border-bottom: 1px solid var(--border-faint);
    text-align: left;
  }
  .markdown-body :global(th) {
    background: var(--surface-sunken);
    font-weight: 600;
    color: var(--fg-strong);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .markdown-body :global(hr) {
    border: none;
    border-top: 1px solid var(--border-faint);
    margin: 24px 0;
  }
  .markdown-body :global(strong) {
    font-weight: 700;
    color: var(--fg-strong);
  }
  .markdown-body :global(.docs-internal-link) {
    color: var(--accent-strong);
    cursor: pointer;
  }
</style>
