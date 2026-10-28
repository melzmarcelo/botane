/**
 * Contas a receber do consumo — camada de service (regra da casa: página não chama `api`).
 *
 * 🔑 **Pedido do dono (22/10/2026):** sem período para abrir e fechar. O consumo
 * fica EM ABERTO até a casa gerar o LOTE de cobrança da pessoa; o lote fica EM
 * COBRANÇA até a baixa, e aí é RECEBIDO. Um lote é de uma pessoa só, e a baixa é
 * sempre do lote inteiro.
 */
import { api } from "@/lib/api";
import type { LinhaDocumento } from "@/app/(app)/vendas/por-pessoa/tabelas-documento";

export type FormaPagamento =
  | "PIX" | "DINHEIRO" | "CARTAO" | "TRANSFERENCIA" | "FOLHA" | "PERMUTA" | "OUTRO";

/** O rótulo de cada forma vem do servidor (`formas`); este é só o tipo. */
export type Formas = Record<FormaPagamento, string>;

export type SituacaoLote = "ABERTO" | "RECEBIDO" | "CANCELADO";

export const ROTULO_SITUACAO: Record<SituacaoLote, string> = {
  ABERTO: "em cobrança",
  RECEBIDO: "recebido",
  CANCELADO: "cancelado",
};

export type LinhaEmAberto = {
  id_pessoa: number;
  pessoa: string;
  cupom_base: string | null;
  cupons: number;
  itens: number;
  total_cheio: number;
  desconto: number;
  total: number;
  desde: string;
  ate: string;
  em_cobranca: number;
  lotes_em_cobranca: number;
};

export type EmAberto = {
  linhas: LinhaEmAberto[];
  total: number;
  total_cheio: number;
  desconto: number;
  em_cobranca: number;
  lotes_em_cobranca: number;
  formas: Formas;
};

export type Lote = {
  id: number;
  id_pessoa: number;
  pessoa: string;
  ate: string;
  desde: string | null;
  status: SituacaoLote;
  cupons: number;
  itens: number;
  total_cheio: number;
  desconto: number;
  total: number;
  criado_em: string;
  criou: string | null;
  observacao: string | null;
  recebido_em: string | null;
  forma_pagamento: FormaPagamento | null;
  baixado_em: string | null;
  baixou: string | null;
  observacao_baixa: string | null;
  cancelado_em: string | null;
  id_consumo_periodo: number | null;
};

export type Gerados = {
  lotes: { id: number; id_pessoa: number; cupons: number; total: number }[];
  total: number;
  message: string;
};

type Mensagem = { message: string };

function consulta(campos: Record<string, string | number | null | undefined>) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(campos)) if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? "?" + s : "";
}

/** O que cada pessoa deve e ainda não foi cobrado, no recorte de datas. */
export const emAberto = (de?: string, ate?: string) =>
  api.get<EmAberto>("/receber/em-aberto" + consulta({ de, ate }));

/** Os documentos em aberto de UMA pessoa, com os itens — para escolher o lote. */
export const documentosEmAberto = (idPessoa: number, de?: string, ate?: string) =>
  api.get<{ documentos: LinhaDocumento[]; total: number }>(
    `/receber/em-aberto/${idPessoa}` + consulta({ de, ate }));

export const lotes = (status?: SituacaoLote, idPessoa?: number) =>
  api.get<{ lotes: Lote[]; formas: Formas }>(
    "/receber/lotes" + consulta({ status, id_pessoa: idPessoa }));

export const lote = (id: number) =>
  api.get<{ lote: Lote; documentos: LinhaDocumento[]; formas: Formas }>(`/receber/lotes/${id}`);

export const gerarLotes = (corpo: {
  ate: string;
  de?: string | null;
  ids_pessoa?: number[] | null;
  ids_venda?: number[] | null;
  observacao?: string | null;
}) => api.post<Gerados>("/receber/lotes", corpo);

export const receberLote = (id: number, corpo: {
  recebido_em: string;
  forma_pagamento: FormaPagamento;
  observacao?: string | null;
}) => api.post<Mensagem>(`/receber/lotes/${id}/receber`, corpo);

export const estornarBaixa = (id: number) =>
  api.post<Mensagem>(`/receber/lotes/${id}/estornar-baixa`, {});

export const cancelarLote = (id: number) =>
  api.post<Mensagem>(`/receber/lotes/${id}/cancelar`, {});

export const tirarDocumento = (id: number, idVenda: number) =>
  api.delete<Mensagem & { cancelado: boolean }>(`/receber/lotes/${id}/documentos/${idVenda}`);

/** O documento do lote, para mandar à pessoa (PDF ou planilha). */
/** O PDF abre numa aba, para imprimir (28/10/2026, "Imprimir" no lugar de "Baixar");
 *  a planilha continua sendo arquivo. */
export const baixarLote = (id: number, formato: "pdf" | "csv") =>
  formato === "pdf" ? api.abrir(`/exportar/lote-consumo/${id}.pdf`)
                    : api.baixar(`/exportar/lote-consumo/${id}.csv`);

/** Todos os lotes em cobrança num PDF só — cada lote na sua página, por nome. */
export const baixarLotesAbertos = () => api.baixar("/exportar/lotes-consumo-abertos.pdf");
