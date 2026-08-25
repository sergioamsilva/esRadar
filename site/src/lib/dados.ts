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
  candidatos_mulheres?: number;
  candidatos_homens?: number;
  colocados_1opcao?: number;
  colocados_mulheres?: number;
  colocados_homens?: number;
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
  /** Bloco do Infocursos (MECI), quando o par lá existe. */
  infocursos: {
    percentil_entrada?: Record<
      string,
      { percentil: number; nota_ingresso_media: number | null; matriculados: number | null }
    >;
    desemprego?: { taxa: number; diplomados: number | null; periodo: string | null };
    sexo?: {
      ano_letivo: string;
      inscritos: number | null;
      homens: number | null;
      mulheres: number | null;
    };
    apos_1_ano?: {
      coorte: string | null;
      novos_inscritos: number | null;
      fica: number;
      muda_curso: number;
      muda_estabelecimento: number;
      fora: number;
    };
    diplomados?: { nota_final_media: number; n: number | null; periodo: string | null };
  } | null;
  /** % de cursos do CNA com nota de corte abaixo da deste (2026, 1ª fase). */
  percentil_nota_2026?: number;
  /** % de cursos do CNA com desemprego IEFP abaixo do deste. */
  desemprego_percentil?: number;
  /** % dos colocados de 2025 que tinham este curso em 1ª opção. */
  pct_colocados_1opcao_2025?: number;
  /** Vizinhos na mesma área CNAEF, ordenados por nota. */
  semelhantes?: {
    par: string;
    curso: string;
    grupo: string;
    nota: number | null;
    vagas: number | null;
  }[];
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
  geo: { lat: number; lon: number } | null;
  n_cursos: number;
  vagas: number;
  colocados_f1: number;
  sobras_f1: number;
  ocupacao_f1: number | null;
};

export type Nacional = {
  fontes: string[];
  mediana_desemprego_cursos: number | null;
  anos: Record<string, { vagas_f1: number; colocados: number; pares: number }>;
};

export type Epoca = { ano: number; fases_arquivadas: number[] };

export type Genero = {
  ano: number;
  fase: number;
  nacional: {
    candidatos_mulheres: number;
    candidatos_homens: number;
    colocados_mulheres: number;
    colocados_homens: number;
  };
  areas: {
    area: string;
    candidatos_mulheres: number;
    candidatos_homens: number;
    colocados_mulheres: number;
    colocados_homens: number;
    cursos: number;
    pct_mulheres_colocadas: number;
  }[];
  cursos_mais_masculinos: { par: string; curso: string; grupo: string; colocados: number; pct_mulheres: number }[];
  cursos_mais_femininos: { par: string; curso: string; grupo: string; colocados: number; pct_mulheres: number }[];
};

function ler<T>(relativo: string): T {
  return JSON.parse(fs.readFileSync(path.join(RAIZ, relativo), "utf8")) as T;
}

export const cursos = (): Curso[] => ler<{ cursos: Curso[] }>("cursos.json").cursos;
export const instituicoes = (): Instituicao[] =>
  ler<{ instituicoes: Instituicao[] }>("instituicoes.json").instituicoes;
export const nacional = (): Nacional => ler<Nacional>("nacional.json");
export const epoca = (): Epoca => ler<Epoca>("epoca.json");
export const genero = (): Genero => ler<Genero>("genero.json");

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
