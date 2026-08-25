/**
 * Gera as imagens Open Graph (1200×630) para o site e para cada curso do
 * concurso — o cartão que aparece quando alguém partilha um link no
 * WhatsApp/X. SVG desenhado à mão → PNG via resvg (sem browser); corre
 * depois do `astro build` e escreve diretamente em dist/og/.
 */
import fs from "node:fs";
import path from "node:path";
import { Resvg } from "@resvg/resvg-js";

const RAIZ = path.resolve(process.cwd(), "..");
const DIST = path.join(process.cwd(), "dist", "og");
const cursos = JSON.parse(fs.readFileSync(path.join(RAIZ, "data", "out", "cursos.json"), "utf8")).cursos;

const FONTES = [
  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
].filter((f) => fs.existsSync(f));

const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/* Quebra o nome do curso em ≤2 linhas de ~26 caracteres. */
const linhas = (nome) => {
  if (nome.length <= 28) return [nome];
  const palavras = nome.split(" ");
  let a = "";
  let i = 0;
  while (i < palavras.length && (a + " " + palavras[i]).trim().length <= 28) {
    a = (a + " " + palavras[i]).trim();
    i++;
  }
  let b = palavras.slice(i).join(" ");
  if (b.length > 30) b = b.slice(0, 29).trimEnd() + "…";
  return b ? [a, b] : [a];
};

const fmt = (n) =>
  n == null ? null : n.toLocaleString("pt-PT", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const POS = (v) => 120 + ((Math.max(90, Math.min(200, v)) - 90) / 110) * 960;

const cartao = ({ titulo, subtitulo, nota, notaRotulo }) => {
  const t = linhas(titulo);
  const regua =
    nota != null
      ? `<line x1="120" y1="500" x2="1080" y2="500" stroke="rgba(255,255,255,.25)" stroke-width="6" stroke-linecap="round"/>
         <line x1="120" y1="500" x2="${POS(nota)}" y2="500" stroke="#7cc0ff" stroke-width="6" stroke-linecap="round"/>
         <circle cx="${POS(nota)}" cy="500" r="16" fill="#fff" stroke="#7cc0ff" stroke-width="6"/>
         ${[100, 120, 140, 160, 180, 200].map((v) => `<text x="${POS(v)}" y="545" font-size="20" fill="rgba(255,255,255,.5)" text-anchor="middle" font-family="DejaVu Sans">${v}</text>`).join("")}`
      : "";
  return `<svg width="1200" height="630" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="fundo" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0a1422"/><stop offset=".55" stop-color="#10233c"/><stop offset="1" stop-color="#0c1a2e"/>
    </linearGradient>
    <radialGradient id="brilho" cx=".85" cy="0" r=".9">
      <stop offset="0" stop-color="rgba(57,135,229,.45)"/><stop offset="1" stop-color="rgba(57,135,229,0)"/>
    </radialGradient>
    <linearGradient id="num" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#9ecbff"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#fundo)"/>
  <rect width="1200" height="630" fill="url(#brilho)"/>
  <circle cx="120" cy="96" r="10" fill="#3987e5"/>
  <text x="145" y="104" font-size="26" letter-spacing="4" fill="rgba(255,255,255,.65)" font-family="DejaVu Sans">ESRADAR · AS COLOCAÇÕES, CURSO A CURSO</text>
  ${t.map((l, i) => `<text x="120" y="${215 + i * 74}" font-size="64" font-weight="bold" fill="#ffffff" font-family="DejaVu Sans">${esc(l)}</text>`).join("")}
  <text x="120" y="${215 + t.length * 74 - 10}" font-size="30" fill="rgba(255,255,255,.75)" font-family="DejaVu Sans">${esc(subtitulo)}</text>
  ${
    nota != null
      ? `<text x="1080" y="435" font-size="110" font-weight="bold" fill="url(#num)" text-anchor="end" font-family="DejaVu Sans">${fmt(nota)}</text>
         <text x="1080" y="345" font-size="24" letter-spacing="3" fill="rgba(255,255,255,.6)" text-anchor="end" font-family="DejaVu Sans">${esc(notaRotulo)}</text>`
      : ""
  }
  ${regua}
  <text x="120" y="600" font-size="22" fill="rgba(255,255,255,.45)" font-family="DejaVu Sans">Dados DGES · 2018–2026 · não é um serviço oficial</text>
</svg>`;
};

const render = (svg, destino) => {
  const png = new Resvg(svg, { font: { fontFiles: FONTES, loadSystemFonts: false } }).render().asPng();
  fs.writeFileSync(destino, png);
};

fs.mkdirSync(DIST, { recursive: true });

render(
  cartao({
    titulo: "As colocações no ensino superior",
    subtitulo: "notas de corte, vagas, procura e sobras — 2018 a 2026",
    nota: null,
  }),
  path.join(process.cwd(), "dist", "og.png"),
);

let n = 0;
for (const c of cursos) {
  render(
    cartao({
      titulo: c.curso,
      subtitulo: c.grupo + (c.distrito ? ` · ${c.distrito}` : ""),
      nota: c.nota_2026f1,
      notaRotulo: "NOTA DO ÚLTIMO COLOCADO · 1ª FASE 2026",
    }),
    path.join(DIST, `${c.par}.png`),
  );
  n++;
}
console.log(`og: ${n} cartões de curso + og.png`);
