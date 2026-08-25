// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';
import fs from 'node:fs';
import path from 'node:path';

/* Os URLs de cursos e instituições levam o nome no caminho (indexação);
   os antigos, só com o código, redirecionam. O mapa vem do build
   (data/out/redirects.json, sem base) — o base entra aqui, porque o Astro
   não o aplica aos destinos dos redirects. */
const BASE = '/esRadar';
const redirects = Object.fromEntries(
  Object.entries(
    JSON.parse(fs.readFileSync(path.resolve('..', 'data', 'out', 'redirects.json'), 'utf8')),
  ).map(([de, para]) => [de, `${BASE}${para}`]),
);

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
  redirects,
  integrations: [sitemap()],
});
