import fs from "node:fs";
import path from "node:path";

const RAIZ = path.resolve(process.cwd(), "..", "data", "out");

/** Registo de um par instituição/curso num ano×fase. Campos ausentes = null. */
export type Registo = {
  vagas?: number;
  colocados?: number;
  nota_ultimo?: number;
  sobras?: number;
  candidatos?: number;
  candidatos_1opcao?: number;
  colocados_1opcao?: number;
  media_candidatura?: number;
  media_provas?: number;
  media_secundario?: number;
};

/** Ficha completa de um par (data/out/par/{code}-{codc}.json). */
export type Par = {
  par: string;
  code: string;
  codc: string;
  curso: string;
  instituicao: string;
  grupo: string;
  subsistema: "universitario" | "politecnico" | null;
  ativo: boolean;
  grau: string | null;
  cnaef: string | null;
  cnaef_nome: string | null;
  duracao: string | null;
  ects: number | null;
  tipo_ensino: string | null;
  provas_ingresso: string | null;
  formula: string | null;
  minimo_candidatura: number | null;
  minimo_provas: number | null;
  vagas_2026: number | null;
  /** Chaves «{ano}f{fase}», ex. «2025f1». */
  series: Record<string, Registo>;
};

/** Linha do índice plano (data/out/cursos.json) — só pares ativos. */
export type Curso = {
  par: string;
  curso: string;
  instituicao: string;
  grupo: string;
  subsistema: string | null;
  grau: string | null;
  cnaef: string | null;
  cnaef_nome: string | null;
  vagas: number | null;
  nota_2026f1: number | null;
  nota_2025f1: number | null;
  colocados_2026f1: number | null;
  sobras_2026f1: number | null;
  candidatos_1opcao_2025f1: number | null;
  racio_procura: number | null;
};

export type Instituicao = {
  code: string;
  nome: string;
  grupo: string;
  subsistema: string | null;
  distrito: string | null;
  n_cursos: number;
  vagas: number;
  colocados_f1: number;
  sobras_f1: number;
  ocupacao_f1: number | null;
};

export type Nacional = {
  fontes: string[];
  anos: Record<string, { vagas_f1: number; colocados: number; pares: number }>;
};

export type Epoca = { ano: number; fases_arquivadas: number[] };

function ler<T>(relativo: string): T {
  return JSON.parse(fs.readFileSync(path.join(RAIZ, relativo), "utf8")) as T;
}

export const cursos = (): Curso[] => ler<{ cursos: Curso[] }>("cursos.json").cursos;
export const instituicoes = (): Instituicao[] =>
  ler<{ instituicoes: Instituicao[] }>("instituicoes.json").instituicoes;
export const nacional = (): Nacional => ler<Nacional>("nacional.json");
export const epoca = (): Epoca => ler<Epoca>("epoca.json");

export const pares = (): Par[] =>
  fs
    .readdirSync(path.join(RAIZ, "par"))
    .filter((f) => f.endsWith(".json"))
    .map((f) => ler<Par>(path.join("par", f)));

export const par = (id: string): Par => ler<Par>(path.join("par", `${id}.json`));

/** Todas as ligações internas passam por aqui — nunca escrever o base à mão. */
export const ligacao = (caminho: string): string =>
  `${import.meta.env.BASE_URL.replace(/\/$/, "")}${caminho}`;

export function formatarNota(valor: number | null | undefined): string {
  if (valor == null) return "—";
  return valor.toLocaleString("pt-PT", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

export function formatarInteiro(valor: number | null | undefined): string {
  if (valor == null) return "—";
  return valor.toLocaleString("pt-PT");
}

/** Série ordenada de um campo ao longo dos anos, para uma fase fixa. */
export function serieAnual(
  p: Par,
  campo: keyof Registo,
  fase: 1 | 2 | 3 = 1,
): { ano: number; valor: number }[] {
  const pontos: { ano: number; valor: number }[] = [];
  for (const [chave, registo] of Object.entries(p.series)) {
    if (!chave.endsWith(`f${fase}`)) continue;
    const valor = registo[campo];
    if (valor != null) pontos.push({ ano: Number(chave.slice(0, 4)), valor });
  }
  return pontos.sort((a, b) => a.ano - b.ano);
}
