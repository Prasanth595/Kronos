import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';

const target = document.getElementById('app');
if (!target) {
  throw new Error('#app element missing — index.html 손상');
}

// SSR fallback marker 영역을 비우고 Svelte 마운트
target.innerHTML = '';

const app = mount(App, {
  target,
});

export default app;
