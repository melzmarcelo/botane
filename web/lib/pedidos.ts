/**
 * Pedidos pelo catálogo do site — camada de service (regra da casa).
 *
 * 🔑 Pedido do dono (28/09/2026): *"o cliente poder realizar pedidos diretamente na tela de
 * catálogo … uma tela com pedidos, um painel para acompanhar e aviso na tela inicial."*
 * Regra em `api/services/pedidos.py`; decisões em `docs/pedidos-estudo.md` (seção 0).
 */
import { api } from "@/lib/api";

export type Situacao = "NOVO" | "CONFIRMADO" | "ENTREGUE" | "RECUSADO" | "CANCELADO";
export type FormaPagamento = "RETIRADA" | "ENTREGA" | "WHATSAPP";

export type ConfigPedidos = {
  aceita: boolean;
  retirada: boolean;
  entrega: boolean;
  taxa_entrega: number;
  pedido_minimo: number;
  antecedencia_min: number;
  antecedencia_max_dias: number;
  pagamentos: FormaPagamento[];
  texto_pagamento: string | null;
};

export type PedidoResumo = {
  id: number;
  numero: number;
  nome: string;
  /** Nulo no pedido da MESA (Cardápio Vivo, 115): ele não pede telefone. */
  telefone: string | null;
  modo: "RETIRADA" | "ENTREGA" | "MESA";
  modo_rotulo: string;
  endereco: string | null;
  para_quando: string;
  forma_pagamento: FormaPagamento | null;
  pagamento_rotulo: string;
  total: number;
  situacao: Situacao;
  motivo: string | null;
  alterado: boolean;
  lancado_pdv_em: string | null;
  cupom_pdv: string | null;
  id_venda: number | null;
  pago_em: string | null;
  pago_como: string | null;
  entregue_em: string | null;
  criado_em: string;
  catalogo: string | null;
  itens: number;
  /** Cardápio Vivo (115): de onde veio e, se da mesa, qual. */
  origem?: "SITE" | "CARDAPIO";
  mesa?: string | null;
  salao?: string | null;
};

export type ItemDoPedido = {
  id: number;
  id_produto: number;
  nome: string;
  quantidade: number;
  preco_unitario: number;
  total: number;
  observacao: string | null;
  /** Os adicionais escolhidos na mesa, congelados no envio (115). */
  adicionais?: { nome: string; preco: number | null; quantidade?: number }[] | null;
};

export type PedidoCompleto = Omit<PedidoResumo, "itens"> & {
  observacao: string | null;
  subtotal: number;
  taxa_entrega: number;
  itens: ItemDoPedido[];
  historico: { acao: string; de: string | null; para: string | null; detalhe: Record<string, unknown> | null; criado_em: string; quem: string | null }[];
};

export type ItemDoCatalogo = { id_item: number; id_produto: number; nome: string; preco: number };

export type Chamado = { id: number; tipo: "GARCOM" | "CONTA"; criado_em: string; mesa: string; salao: string };

export type Painel = {
  novos: PedidoResumo[];
  sem_pdv: PedidoResumo[];
  confirmados: PedidoResumo[];
  /** Os pedidos da MESA em aberto (Cardápio Vivo, 115). */
  mesas: PedidoResumo[];
  chamados: Chamado[];
  agora: string;
};

export const ROTULO: Record<Situacao, string> = {
  NOVO: "novo", CONFIRMADO: "confirmado", ENTREGUE: "entregue", RECUSADO: "recusado",
  CANCELADO: "cancelado",
};
export const COR: Record<Situacao, "erva" | "alerta" | "neutro"> = {
  NOVO: "alerta", CONFIRMADO: "erva", ENTREGUE: "neutro", RECUSADO: "neutro", CANCELADO: "neutro",
};

export const obterConfig = (idCatalogo: number) =>
  api.get<ConfigPedidos>(`/pedidos/config/${idCatalogo}`);
export const salvarConfig = (idCatalogo: number, c: ConfigPedidos) =>
  api.put<ConfigPedidos & { message: string }>(`/pedidos/config/${idCatalogo}`, c);

export const listar = (parametros: Record<string, string>, filtros: {
  situacao: string; dia: string; busca: string;
}) => {
  const q = new URLSearchParams(parametros);
  q.set("situacao", filtros.situacao || "abertos");
  if (filtros.dia) q.set("dia", filtros.dia);
  if (filtros.busca) q.set("busca", filtros.busca);
  return api.listar<PedidoResumo>(`/pedidos?${q}`);
};

export const painel = () => api.get<Painel>("/pedidos/painel");
export const obter = (id: number) => api.get<PedidoCompleto>(`/pedidos/${id}`);
export const catalogoParaTroca = (id: number) => api.get<ItemDoCatalogo[]>(`/pedidos/${id}/catalogo`);

type Resposta = PedidoCompleto & { message: string };
export const confirmar = (id: number, itens?: {
  id_produto?: number | null; id_item_catalogo?: number | null; quantidade: number; observacao?: string | null;
}[]) => api.post<Resposta>(`/pedidos/${id}/confirmar`, itens ? { itens } : {});
export const recusar = (id: number, motivo: string) => api.post<Resposta>(`/pedidos/${id}/recusar`, { motivo });
export const cancelar = (id: number, motivo: string) => api.post<Resposta>(`/pedidos/${id}/cancelar`, { motivo });
export const lancadoNoPdv = (id: number, cupom: string) =>
  api.post<Resposta>(`/pedidos/${id}/lancado-pdv`, { cupom: cupom || null });
export const pago = (id: number, como: string) => api.post<Resposta>(`/pedidos/${id}/pago`, { como });
export const entregar = (id: number) => api.post<Resposta>(`/pedidos/${id}/entregar`);
export const imprimir = (id: number) => api.abrir(`/pedidos/${id}/pdf`);

export const reais = (v: number) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
export const quando = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
export const fone = (t: string | null) => {
  // Pedido da mesa (115) não tem telefone.
  if (!t) return "";
  const m = t.match(/^(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : t;
};
