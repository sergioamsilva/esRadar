import { historiaCompleta } from "../../lib/dados";

/** Os agregados históricos completos (anos, famílias, regiões, rotação, nascimentos). */
export function GET() {
  return new Response(JSON.stringify(historiaCompleta()), {
    headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}
