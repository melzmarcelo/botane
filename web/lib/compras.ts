/**
 * Compras — camada de service (regra da casa: página não chama `api`).
 * A tela de notas nasceu chamando a API direto; o que entra novo mora aqui.
 */
import { api } from "@/lib/api";

/** Em que pé a nota está para o lote. Quem decide é o servidor. */
export type SituacaoNoLote = "pronta" | "conferir" | "travada";

export type NotaDoLote = {
  id: number;
  numero: string | null;
  fornecedor: string | null;
  data: string | null;
  valor_total: number;
  itens: number;
  situacao: SituacaoNoLote;
  /** A frase do lançamento (travada) ou o que conferir. Nula na pronta. */
  motivo: string | null;
  /** Quanto entra no estoque — só na pronta. */
  valor_estoque?: number;
};

export type PreviaDoLote = {
  notas: NotaDoLote[];
  resumo: Record<SituacaoNoLote, { notas: number; valor: number }>;
  /** Os cadastros que seguram notas travadas, do que solta mais para o que solta menos. */
  destrava: {
    id: number;
    codigo: string | null;
    nome: string;
    causa: "sem_unidade" | "arquivado";
    notas: number;
  }[];
};

export type ResultadoDoLote = {
  lancadas: NotaDoLote[];
  /** As pedidas que não entraram, cada uma com o motivo. */
  fora: NotaDoLote[];
  notas: number;
  itens: number;
  valor: number;
  message: string;
};

/**
 * O que "lançar as conciliadas" faria — o lançamento de verdade, ensaiado e
 * desfeito no servidor. Não grava nada.
 */
export const previaDoLote = () => api.get<PreviaDoLote>("/notas/lote/previa");

/**
 * Lança as notas prontas de `ids`. ⚠️ A lista só RESTRINGE: o servidor
 * reclassifica cada nota na hora, e a que deixou de estar pronta volta em `fora`.
 */
export const lancarLote = (ids: number[]) =>
  api.post<ResultadoDoLote>("/notas/lote/lancar", { ids });
