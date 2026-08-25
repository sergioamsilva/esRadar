/** Ficha completa de um par em JSON — alimenta o comparador e quem quiser
 * reutilizar os dados (mesmo conteúdo de data/out/par). */
import type { APIRoute } from "astro";
import { pares, par } from "../../lib/dados";

export function getStaticPaths() {
  return pares().map((p) => ({ params: { par: p.par } }));
}

export const GET: APIRoute = ({ params }) => {
  return new Response(JSON.stringify(par(params.par!)), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
};
