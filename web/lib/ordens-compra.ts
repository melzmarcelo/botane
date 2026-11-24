import { api } from "@/lib/api";

/**
 * Ordem de compra: o que falta comprar e o que já foi (migração 158, pedido do dono de
 * 23/11/2026). Comprado NÃO é recebido: o estoque só anda quando a nota é lançada.
 */

export type AbaOrdem = "A_COMPRAR" | "COMPRADO";

export type OrdemItem = {
  id: number;
  id_produto: number | null;
  item: string;
  codigo: string | null;
  fora_do_cadastro: boolean;
  quantidade: number | string;
  quantidade_pedida: number | string | null;
  um: string;
  observacao: string | null;
  status: AbaOrdem;
  id_item_origem: number | null;
  criado_em: string;
  criado_por: number;
  pedido_por: string | null;
  comprado_em: string | null;
  comprado_por_nome: string | null;
  fornecedor: string | null;
};

export type OpcoesDoProduto = {
  id: number;
  nome: string;
  unidades: { um: string; fator: number | string }[];
  um_padrao: string | null;
  produzido: boolean;
  abertos: { id: number; quantidade: number | string; um: string; pedido_por: string | null }[];
};

export type NovoItem = {
  id_produto?: number;
  descricao_livre?: string;
  quantidade: number;
  um: string;
  observacao?: string | null;
  somar_em?: number;
};

type Resposta = { id: number; message: string };
type RespostaLote = { ids: number[]; message: string };

export const listarOrdens = (aba: AbaOrdem, q: Record<string, string>) =>
  api.listar<OrdemItem>(`/ordens-compra?${new URLSearchParams({ status: aba, ...q })}`);

export const resumoOrdens = () => api.get<{ a_comprar: number }>("/ordens-compra/resumo");

export const opcoesDoProduto = (id: number) =>
  api.get<OpcoesDoProduto>(`/ordens-compra/produto/${id}`);

export const unidadesDeMedida = () =>
  api.get<{ sigla: string; nome: string }[]>("/unidades-medida");

export const pedirItem = (corpo: NovoItem) => api.post<Resposta>("/ordens-compra", corpo);

export const corrigirItem = (
  id: number,
  corpo: { quantidade: number; um: string; observacao: string | null },
) => api.put<Resposta>(`/ordens-compra/${id}`, corpo);

export const cancelarItem = (id: number) =>
  api.post<Resposta>(`/ordens-compra/${id}/cancelar`, {});

export const marcarComprado = (
  itens: { id: number; quantidade: number }[],
  id_fornecedor: number | null,
) => api.post<RespostaLote>("/ordens-compra/comprar", { itens, id_fornecedor });

export const voltarParaLista = (ids: number[]) =>
  api.post<RespostaLote>("/ordens-compra/voltar", { ids });

/** Quantidade para o campo de digitação: vírgula e sem zeros à toa. */
export const qtdParaCampo = (v: number | string) => String(Number(v)).replace(".", ",");
