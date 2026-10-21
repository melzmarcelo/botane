/**
 * As contas de data do painel de vendas — a janela de cada modo e o andar das setas.
 *
 * ⚠️ `new Date("AAAA-MM-DD")` é meia-noite UTC — em Brasília, o dia ANTERIOR a partir
 * das 21h. Tudo aqui monta a data local ao meio-dia, e devolve texto AAAA-MM-DD.
 */
export type Modo = "dia" | "semana" | "mes" | "periodo";

export const MODOS: { valor: Modo; nome: string }[] = [
  { valor: "dia", nome: "Dia" },
  { valor: "semana", nome: "Semana" },
  { valor: "mes", nome: "Mês" },
  { valor: "periodo", nome: "Período" },
];

const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
  "setembro", "outubro", "novembro", "dezembro"];
const SEMANA_CURTA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];

export const local = (iso: string) => {
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(a, m - 1, d, 12);
};
export const iso = (d: Date) => d.toLocaleDateString("sv-SE");
const mais = (s: string, dias: number) => {
  const d = local(s);
  d.setDate(d.getDate() + dias);
  return iso(d);
};

/** A janela que o modo cobre em torno de uma data. */
export function janela(modo: Modo, ancora: string, de?: string, ate?: string): [string, string] {
  const d = local(ancora);
  if (modo === "dia") return [ancora, ancora];
  if (modo === "semana") {
    // A semana da casa começa na SEGUNDA, como o `date_trunc('week')` do servidor.
    const seg = mais(ancora, -((d.getDay() + 6) % 7));
    return [seg, mais(seg, 6)];
  }
  if (modo === "mes") {
    return [iso(new Date(d.getFullYear(), d.getMonth(), 1, 12)),
            iso(new Date(d.getFullYear(), d.getMonth() + 1, 0, 12))];
  }
  return [de ?? ancora, ate ?? ancora];
}

/** Um passo das setas: um dia, uma semana, um mês — ou o tamanho do período. */
export function andar(modo: Modo, de: string, ate: string, sentido: 1 | -1): [string, string] {
  if (modo === "dia") return janela("dia", mais(de, sentido));
  if (modo === "semana") return janela("semana", mais(de, 7 * sentido));
  if (modo === "mes") {
    const d = local(de);
    return janela("mes", iso(new Date(d.getFullYear(), d.getMonth() + sentido, 1, 12)));
  }
  const n = Math.round((local(ate).getTime() - local(de).getTime()) / 86400000) + 1;
  return [mais(de, n * sentido), mais(ate, n * sentido)];
}

export const dataCurta = (s: string) => {
  const [, m, d] = s.split("-");
  return `${d}/${m}`;
};
export const dataBr = (s: string) => s.split("-").reverse().join("/");

/** O nome do recorte, por extenso — é o título do painel. */
export function nomeDoRecorte(modo: Modo, de: string, ate: string) {
  const d = local(de);
  if (modo === "dia") return `${SEMANA_CURTA[d.getDay()]}, ${dataBr(de)}`;
  if (modo === "mes") return `${MESES[d.getMonth()]} de ${d.getFullYear()}`;
  return `${dataBr(de)} a ${dataBr(ate)}`;
}

/** O rótulo de um ponto da evolução, conforme o agrupamento. */
export function rotuloDoPonto(agrupar: string, periodo: string) {
  if (agrupar === "mes") {
    const d = local(periodo);
    return `${MESES[d.getMonth()].slice(0, 3)}/${String(d.getFullYear()).slice(2)}`;
  }
  if (agrupar === "semana") return `sem ${dataCurta(periodo)}`;
  return dataCurta(periodo);
}

export function tituloDoPonto(agrupar: string, periodo: string) {
  if (agrupar === "mes") return nomeDoRecorte("mes", periodo, periodo);
  if (agrupar === "semana") return `semana de ${dataBr(periodo)} a ${dataBr(mais(periodo, 6))}`;
  return nomeDoRecorte("dia", periodo, periodo);
}
