import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";

/**
 * O Estúdio BI (migração 149, `api/routers/bi.py`, `api/services/bi.py`).
 *
 * 🔑 Layout novo, fase 4 (05/11/2026, pedido do dono): relatórios personalizados com ligações
 * configuráveis. ⚠️ A tela manda só NOMES da lista branca do servidor — quem monta o SQL é ele.
 */

export type CampoBI = { chave: string; rotulo: string; tipo: "dim" | "med"; formato: Formato };
export type FonteBI = {
  chave: string; rotulo: string; descricao: string; chaves: string[];
  tem_periodo: boolean; exige: string[]; campos: CampoBI[];
};
export type RelacaoBI = { id: string; a: string; ca: string; b: string; cb: string };
export type CatalogoBI = { fontes: FonteBI[]; relacoes: RelacaoBI[]; limite: number };

export type TipoLigacao = "INNER" | "LEFT" | "NENHUMA";
export type LigacaoManual = { a: string; ca: string; b: string; cb: string; tipo: "INNER" | "LEFT" };
export type Visual = "barras" | "tabela" | "indicadores";

export type DefinicaoBI = {
  fontes: string[];
  tipos: Record<string, TipoLigacao>;
  manuais: LigacaoManual[];
  dimensoes: string[];
  medidas: string[];
  de: string | null;
  ate: string | null;
  visual: Visual;
};

export type Formato = "texto" | "inteiro" | "reais" | "numero" | "data" | "mes";
export type ColunaBI = { chave: string; rotulo: string; tipo: "dim" | "med"; formato: Formato };
export type ResultadoBI = {
  colunas: ColunaBI[];
  linhas: (string | number | null)[][];
  limite: number;
  cortado: boolean;
  sql: string;
};

export type Visibilidade = "EU" | "TODOS" | "PAPEIS";
export type RelatorioBI = {
  id: number; nome: string; visibilidade: Visibilidade; papeis_vistos: number[]; no_menu: boolean;
  criado_por: string | null; atualizado_em: string; pode_editar: boolean;
};

export const DEFINICAO_VAZIA: DefinicaoBI = {
  fontes: [], tipos: {}, manuais: [], dimensoes: [], medidas: [], de: null, ate: null, visual: "barras",
};

export const catalogoBI = () => api.get<CatalogoBI>("/bi/fontes");
export const consultarBI = (d: DefinicaoBI) => api.post<ResultadoBI>("/bi/consultar", d);
export const relatoriosBI = () => api.get<RelatorioBI[]>("/bi/relatorios");
export const relatorioBI = (id: number) => api.get<RelatorioBI & { definicao: DefinicaoBI }>(`/bi/relatorios/${id}`);
export const executarBI = (id: number, periodo: { de?: string | null; ate?: string | null } = {}) =>
  api.post<ResultadoBI & { nome: string; visual: Visual }>(`/bi/relatorios/${id}/executar`, periodo);
export type SalvarBI = { nome: string; definicao: DefinicaoBI; visibilidade: Visibilidade; papeis_vistos: number[]; no_menu: boolean };
export const salvarBI = (corpo: SalvarBI, id?: number | null) =>
  id ? api.put<{ id: number }>(`/bi/relatorios/${id}`, corpo) : api.post<{ id: number }>("/bi/relatorios", corpo);
export const apagarBI = (id: number) => api.delete<{ ok: boolean }>(`/bi/relatorios/${id}`);

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

/** O valor de uma célula como se lê (o servidor manda número como texto, para não perder casas). */
export function formatar(v: string | number | null, f: Formato): string {
  if (v === null || v === undefined || v === "") return "—";
  if (f === "reais") return reais(Number(v));
  if (f === "inteiro") return Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  if (f === "numero") return Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 3 });
  if (f === "mes") {
    const [a, m] = String(v).split("-");
    return m ? `${MESES[Number(m) - 1]}/${a.slice(2)}` : String(v);
  }
  if (f === "data") return String(v).slice(0, 10).split("-").reverse().join("/");
  return String(v);
}
