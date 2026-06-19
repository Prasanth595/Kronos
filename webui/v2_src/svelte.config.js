import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  preprocess: vitePreprocess(),
  compilerOptions: {
    // Svelte 5 runes 모드 활성화 (점진 도입을 위해 자동 감지 허용)
    runes: undefined,
  },
};
