/** Índice leve para a paleta de pesquisa global — carregado sob demanda
 * na primeira abertura, nunca embebido em cada página (seriam ~80 KB).
 * Inclui cursos E instituições — «instituto superior técnico» tem de dar
 * a página da instituição, não só os cursos dela. */
import type { APIRoute } from "astro";
import { cursos, instituicoes, ligacaoCurso, ligacaoInstituicao } from "../../lib/dados";

export const GET: APIRoute = () => {
  const inst = instituicoes().map((i) => ({
    t: "i",
    u: ligacaoInstituicao(i),
    c: i.nome,
    i: `${i.n_cursos} cursos · ${i.vagas} vagas`,
    g: i.grupo,
    d: i.distrito,
    n: null,
  }));
  const cur = cursos().map((c) => ({
    t: "c",
    u: ligacaoCurso(c),
    c: c.curso,
    i: c.instituicao,
    g: c.grupo,
    d: c.distrito,
    n: c.nota_2026f1,
  }));
  return new Response(JSON.stringify([...inst, ...cur]), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
};
