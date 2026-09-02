/**
 * Gates de qualidade sobre o site construído, antes de publicar:
 * - axe (WCAG 2.1 AA) numa amostra de páginas, nos dois temas;
 * - sem transbordo horizontal a 390 px (regra do AGENTS.md).
 * Sai com código ≠0 à primeira violação. Corre contra um servidor local
 * do dist (astro preview) cuja base é /esRadar.
 */
import { chromium } from "playwright";
import { AxeBuilder } from "@axe-core/playwright";

const BASE = process.env.BASE_URL ?? "http://localhost:4321/esRadar";
const PAGINAS = [
  "/",
  "/trinta-anos/",
  "/cursos/",
  "/curso/6800-9081-economia/",
  "/comparar/",
  "/genero/",
  "/instituicoes/",
  "/distritos/",
  "/areas/",
  "/area/enfermagem/",
  "/distrito/lisboa/",
  "/metodologia/",
];

const browser = await chromium.launch();
let falhas = 0;

for (const tema of ["light", "dark"]) {
  const ctx = await browser.newContext({ colorScheme: tema, viewport: { width: 1280, height: 900 } });
  const p = await ctx.newPage();
  for (const caminho of PAGINAS) {
    await p.goto(BASE + caminho, { waitUntil: "networkidle" });
    const resultados = await new AxeBuilder({ page: p })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    for (const v of resultados.violations) {
      falhas++;
      console.error(`axe [${tema}] ${caminho}: ${v.id} — ${v.help} (${v.nodes.length} nós)`);
    }
  }
  await ctx.close();
}

const movel = await browser.newContext({ viewport: { width: 390, height: 844 } });
const pm = await movel.newPage();
for (const caminho of PAGINAS) {
  await pm.goto(BASE + caminho, { waitUntil: "networkidle" });
  const transbordo = await pm.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  if (transbordo > 1) {
    falhas++;
    console.error(`largura ${caminho}: transbordo horizontal de ${transbordo}px a 390px`);
  }
}
await movel.close();
await browser.close();

if (falhas) {
  console.error(`verificar: ${falhas} violações`);
  process.exit(1);
}
console.log(`verificar: ${PAGINAS.length} páginas × 2 temas + 390px — tudo limpo`);
