import { nacional, historiaCompleta } from "../../lib/dados";

/** A série nacional dos 30 anos, um ano por linha — para reutilização. */
export function GET() {
  const nac = nacional();
  const hist = historiaCompleta();
  const colunas = [
    "ano", "vagas_1f", "colocados_1f", "colocados_2f", "colocados_3f", "colocados_total", "pares",
    "esgotados_1f", "sobras_1f", "nota_p10", "nota_p50", "nota_p90", "cursos_nota_170_ou_mais",
    "cursos_nota_abaixo_100", "vagas_universitario", "vagas_politecnico", "nascidos_18_anos_antes",
  ];
  const linhas = Object.keys(nac.anos)
    .map(Number)
    .sort((a, b) => a - b)
    .map((ano) => {
      const n = nac.anos[String(ano)];
      const h = hist.anos[String(ano)];
      return [
        ano, n.vagas_f1, n.colocados_f1, n.colocados_f2, n.colocados_f3, n.colocados, n.pares,
        h?.esgotados ?? "", h?.sobras_f1 ?? "", n.notas?.p10 ?? "", n.notas?.p50 ?? "", n.notas?.p90 ?? "",
        n.notas?.acima_170 ?? "", n.notas?.abaixo_100 ?? "", n.vagas_universitario, n.vagas_politecnico,
        hist.nascimentos.anos[String(ano - 18)] ?? "",
      ].join(",");
    });
  return new Response([colunas.join(","), ...linhas].join("\n") + "\n", {
    headers: { "Content-Type": "text/csv; charset=utf-8" },
  });
}
