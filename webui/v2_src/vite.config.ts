import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import path from 'node:path';

// [B-2/REV-2] Vite base 는 Flask static_url_path='/static' 와 매핑된다.
// 빌드 산출물은 webui/static/v2/dist/ 에 위치하며, asset URL 은 /static/v2/dist/assets/...
export default defineConfig({
  base: '/static/v2/dist/',
  plugins: [
    svelte({
      onwarn: (warning, handler) => {
        if (
          warning.code === 'a11y_no_redundant_roles' ||
          warning.code === 'a11y_click_events_have_key_events' ||
          warning.code === 'a11y_no_noninteractive_element_interactions'
        ) {
          return;
        }
        handler(warning);
      },
    }),
  ],
  build: {
    outDir: path.resolve(__dirname, '../static/v2/dist'),
    emptyOutDir: true,
    sourcemap: true,
    target: 'es2020',
    chunkSizeWarningLimit: 1400,
  },
  server: {
    port: 5173,
    strictPort: false,
    // [REV-2] 학습 디렉터리는 watch 제외 — finetune outputs 의 jsonl append 가 dev HMR 을 폭주시키는 것을 차단
    watch: {
      ignored: [
        '**/finetune/outputs/**',
        '**/_database/**',
        '**/checkpoints/**',
        '**/logs/**',
        '**/webui/prediction_results/**',
        '**/webui/stom_predictions/**',
        '**/*.db',
      ],
    },
  },
  resolve: {
    alias: {
      $lib: path.resolve(__dirname, 'src/lib'),
      $widgets: path.resolve(__dirname, 'src/widgets'),
      $tabs: path.resolve(__dirname, 'src/tabs'),
      $layout: path.resolve(__dirname, 'src/layout'),
    },
  },
});
