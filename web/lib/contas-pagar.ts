import { api } from "@/lib/api";

/**
 * Contas a pagar (migração 163, módulo Financeiro, pedido do dono de 24/11/2026): lançar,
 * agendar, pagar com comprovante, estornar e cancelar. O agendado é baixado sozinho na data.
 */

export type SituacaoConta = "A_PAGAR" | "AGENDADO" | "PAGO" | "CANCELADO";
export type Forma = "PIX" | "TRANSFERENCIA" | "BOLETO" | "DINHEIRO" | "CARTAO" | "OUTRO";

export const SITUACOES: Record<SituacaoConta, string> = {
  A_PAGAR: "A pagar", AGENDADO: "Agendado", PAGO: "Pago", CANCELADO: "Cancelado",
};
export const FORMAS: Record<Forma, string> = {
  PIX: "Pix", TRANSFERENCIA: "Transferência", BOLETO: "Boleto", DINHEIRO: "Dinheiro",
  CARTAO: "Cartão", OUTRO: "Outro",
};

export type Conta = {
  id: number;
  id_pessoa: number;
  pessoa: string;
  chave_pix: string | null;
  documento: string | null;
  id_categoria: number | null;
  categoria: string | null;
  descricao: string;
  funcao: string | null;
  competencia: string;
  vencimento: string;
  valor: number | string;
  observacao: string | null;
  status: SituacaoConta;
  agendado_para: string | null;
  forma: Forma | null;
  baixa_automatica: boolean;
  pago_em: string | null;
  valor_pago: number | string | null;
  baixado_automaticamente: boolean;
  tem_comprovante: boolean;
  lote: string | null;
  atrasada: boolean;
  criado_por_nome: string | null;
  pago_por_nome: string | null;
};

export type Resumo = {
  atrasado: number; n_atrasado: number; hoje: number; n_hoje: number; semana: number;
  a_pagar: number; n_a_pagar: number; agendado: number; n_agendado: number;
  pagos_sozinhos_hoje: number;
};

export type Categoria = { id: number; nome: string; ativo: boolean };

/** Pago (pela data do pagamento) × em aberto (pelo vencimento) num recorte do painel. */
export type NumerosPainel = { pago: number; n_pago: number; em_aberto: number; n_em_aberto: number; total: number };
export type Painel = {
  hoje: string; de: string; ate: string; resumo: Resumo;
  agenda: { data: string; contas: number; valor: number; agendado: number }[];
  baixadas_sozinhas: { id: number; pessoa: string; descricao: string; valor: number; pago_em: string; forma: Forma | null }[];
  periodo: NumerosPainel;
  por_categoria: (NumerosPainel & { categoria: string })[];
  por_pessoa: (NumerosPainel & { id_pessoa: number; pessoa: string })[];
  por_forma: { forma: Forma; rotulo: string; contas: number; valor: number }[];
};

export type NovaConta = {
  id_pessoa: number; id_categoria: number | null; descricao: string; funcao: string | null;
  competencia: string; vencimento: string; valor: number; observacao: string | null;
};

type Msg = { message: string };

export const listarContas = (q: URLSearchParams) =>
  api.get<{ itens: Conta[]; totais: { contas: number; valor: number; atrasadas: number } }>(
    `/contas-pagar?${q}`);
export const resumoContas = () => api.get<Resumo>("/contas-pagar/resumo");
export const painelFinanceiro = (de: string, ate: string) => {
  const q = new URLSearchParams();
  if (de) q.set("de", de);
  if (ate) q.set("ate", ate);
  return api.get<Painel>(`/contas-pagar/painel?${q}`);
};
export const categoriasFinanceiro = () => api.get<Categoria[]>("/contas-pagar/categorias");
export const criarCategoria = (nome: string) => api.post<Msg>("/contas-pagar/categorias", { nome });
export const alterarCategoria = (id: number, nome: string, ativo: boolean) =>
  api.put<Msg>(`/contas-pagar/categorias/${id}`, { nome, ativo });
export const ultimoDaPessoa = (id: number) =>
  api.get<{ valor?: number; funcao?: string | null; id_categoria?: number | null }>(
    `/contas-pagar/pessoa/${id}/ultimo`);
export const lancarConta = (c: NovaConta) => api.post<Msg & { id: number }>("/contas-pagar", c);
export const corrigirConta = (id: number, c: NovaConta) => api.put<Msg>(`/contas-pagar/${id}`, c);
export const lancarEquipe = (corpo: {
  data: string; vencimento: string; id_categoria: number | null; descricao: string;
  itens: { id_pessoa: number; valor: number; funcao: string | null }[];
}) => api.post<Msg & { ids: number[] }>("/contas-pagar/equipe", corpo);
export const agendarContas = (ids: number[], data: string, forma: Forma, baixa_automatica: boolean) =>
  api.post<Msg>("/contas-pagar/agendar", { ids, data, forma, baixa_automatica });
export const pagarContas = (ids: number[], pago_em: string, forma: Forma, valor_pago: number | null) =>
  api.post<Msg>("/contas-pagar/pagar", { ids, pago_em, forma, valor_pago });
export const estornarContas = (ids: number[]) => api.post<Msg>("/contas-pagar/estornar", { ids });
export const cancelarContas = (ids: number[]) => api.post<Msg>("/contas-pagar/cancelar", { ids });
export function anexarComprovante(ids: number[], arquivo: File) {
  const fd = new FormData();
  fd.append("ids", ids.join(","));
  fd.append("arquivo", arquivo);
  return api.upload<Msg>("/contas-pagar/comprovante", fd);
}
export const comprovanteDaConta = (id: number) => api.imagem(`/contas-pagar/${id}/comprovante`);

export const hojeIso = () =>
  new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
export const dataBr = (s: string | null) => (s ? s.split("-").reverse().join("/") : "—");
