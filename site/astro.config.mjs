// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

/**
 * Servido pelo GitHub Pages em https://sergioamsilva.github.io/esRadar/ —
 * numa subpasta. `base` aplica-se também em desenvolvimento, de propósito:
 * qualquer diferença entre os dois ambientes esconde 404s (lição do snsRadar).
 * Nenhuma ligação interna é escrita à mão com o prefixo — passam todas pelo
 * ajudante `ligacao()` de `src/lib/dados.ts`.
 */
export default defineConfig({
  site: 'https://sergioamsilva.github.io',
  base: '/esRadar',
  integrations: [sitemap()],
});
