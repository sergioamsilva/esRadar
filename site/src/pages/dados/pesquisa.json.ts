/** Índice leve para a paleta de pesquisa global — carregado sob demanda
 * na primeira abertura, nunca embebido em cada página (seriam ~80 KB). */
import type { APIRoute } from "astro";
import { cursos, ligacaoCurso } from "../../lib/dados";

export const GET: APIRoute = () => {
  const indice = cursos().map((c) => ({
    p: c.par,
    u: ligacaoCurso(c),
    c: c.curso,
    i: c.instituicao,
    g: c.grupo,
    d: c.distrito,
    n: c.nota_2026f1,
  }));
  return new Response(JSON.stringify(indice), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
};
