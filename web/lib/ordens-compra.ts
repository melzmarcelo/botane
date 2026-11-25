import { api } from "@/lib/api";

/**
 * Ordem de compra: o que falta comprar e o que já foi (migração 158, pedido do dono de
 * 23/11/2026). Comprado NÃO é recebido: o estoque só anda quando a nota é lançada.
 */

/**
 * 🔑 Aprovação (migração 165, pedido do dono de 25/11/2026): o pedido de quem não tem
 * `compras.ordem_aprovar` nasce em AGUARDANDO e só vai para A comprar quando é aprovado.
 */
export type AbaOrdem = "AGUARDANDO" | "A_COMPRAR" | "COMPRADO" | "RECUSADO";

export const ABAS_ORDEM: AbaOrdem[] = ["AGUARDANDO", "A_COMPRAR", "COMPRADO", "RECUSADO"];

/** Para quando o item precisa chegar (migração 159, modelo do dono de 24/11/2026). */
export type Urgencia = "PODE_ESPERAR" | "SEMANA" | "HOJE";

export const URGENCIAS: { valor: Urgencia; rotulo: string; dica: string }[] = [
  { valor: "PODE_ESPERAR", rotulo: "Pode esperar", dica: "Entra na próxima compra de rotina." },
  { valor: "SEMANA", rotulo: "Esta semana", dica: "Precisa chegar nos próximos dias." },
  { valor: "HOJE", rotulo: "Urgente — hoje", dica: "Falta para o serviço de hoje." },
];

export const rotuloUrgencia = (u: Urgencia) => URGENCIAS.find((x) => x.valor === u)?.rotulo ?? u;

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
  urgencia: Urgencia;
  id_item_origem: number | null;
  criado_em: string;
  criado_por: number;
  pedido_por: string | null;
  /** O setor de quem pediu ("Cozinha"); nulo quando a pessoa não tem setor. */
  setor_pedido: string | null;
  comprado_em: string | null;
  comprado_por_nome: string | null;
  fornecedor: string | null;
  aprovado_em: string | null;
  aprovado_por: number | null;
  aprovado_por_nome: string | null;
  recusado_em: string | null;
  recusado_por_nome: string | null;
  motivo_recusa: string | null;
};

export type OpcoesDoProduto = {
  id: number;
  nome: string;
  unidades: { um: string; fator: number | string }[];
  um_padrao: string | null;
  abertos: {
    id: number; quantidade: number | string; um: string; pedido_por: string | null;
    status: "AGUARDANDO" | "A_COMPRAR";
  }[];
};

export type NovoItem = {
  id_produto?: number;
  descricao_livre?: string;
  quantidade: number;
  um: string;
  observacao?: string | null;
  urgencia?: Urgencia;
  somar_em?: number;
};

/** Abaixo do mínimo e comprado, com a quantidade já na unidade de pedir (etapa 2). */
export type Sugestao = {
  id_produto: number;
  codigo: string | null;
  nome: string;
  um_estoque: string | null;
  saldo: number | string;
  estoque_minimo: number | string;
  repor_ate: number | string;
  ate_o_maximo: boolean;
  na_lista: { quantidade: number | string; um: string }[];
  faltam: number | string;
  um: string;
  fator: number | string;
  /** Zero quando o que já está na lista cobre a falta. */
  sugerida: number | string;
  unidades: { um: string; fator: number | string }[];
  fornecedor: string | null;
};

/**
 * 🔑 Só o que se COMPRA (pedido do dono, 24/11/2026): produzido e kit ficam fora da busca, e a
 * API recusa os dois de qualquer jeito.
 */
export const FILTRO_COMPRADOS = "comprado=true";

/** O painel de estoque e os alertas abrem a ordem de compra direto nas sugestões. */
export const LINK_SUGESTOES = "/compras/ordens?sugestoes=1";

type Resposta = { id: number; message: string; status?: AbaOrdem };
type RespostaLote = { ids: number[]; message: string };

export const listarOrdens = (aba: AbaOrdem, q: Record<string, string>) =>
  api.listar<OrdemItem>(`/ordens-compra?${new URLSearchParams({ status: aba, ...q })}`);

export const resumoOrdens = () =>
  api.get<{ a_comprar: number; aguardando: number }>("/ordens-compra/resumo");

export const opcoesDoProduto = (id: number) =>
  api.get<OpcoesDoProduto>(`/ordens-compra/produto/${id}`);

export const unidadesDeMedida = () =>
  api.get<{ sigla: string; nome: string }[]>("/unidades-medida");

export const pedirItem = (corpo: NovoItem) => api.post<Resposta>("/ordens-compra", corpo);

export const sugestoesOrdem = () => api.get<Sugestao[]>("/ordens-compra/sugestoes");

export const pedirLote = (itens: NovoItem[]) =>
  api.post<RespostaLote>("/ordens-compra/lote", { itens });

export const corrigirItem = (
  id: number,
  corpo: { quantidade: number; um: string; observacao: string | null; urgencia: Urgencia },
) => api.put<Resposta>(`/ordens-compra/${id}`, corpo);

export const cancelarItem = (id: number) =>
  api.post<Resposta>(`/ordens-compra/${id}/cancelar`, {});

export const marcarComprado = (
  itens: { id: number; quantidade: number }[],
  id_fornecedor: number | null,
) => api.post<RespostaLote>("/ordens-compra/comprar", { itens, id_fornecedor });

export const aprovarPedidos = (ids: number[]) =>
  api.post<RespostaLote>("/ordens-compra/aprovar", { ids });

export const recusarPedidos = (ids: number[], motivo: string | null) =>
  api.post<RespostaLote>("/ordens-compra/recusar", { ids, motivo });

export const voltarParaLista = (ids: number[]) =>
  api.post<RespostaLote>("/ordens-compra/voltar", { ids });

/** Quantidade para o campo de digitação: vírgula e sem zeros à toa. */
export const qtdParaCampo = (v: number | string) => String(Number(v)).replace(".", ",");
