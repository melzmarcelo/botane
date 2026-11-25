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
  /** Etapa 3 (migração 167): a conta gerada por uma conta fixa, ou a parcela (2 de 3). */
  id_conta_fixa: number | null;
  parcela: number | null;
  parcelas: number | null;
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
  /** Com 2 ou mais, `valor` é o TOTAL e `vencimento` o da primeira parcela (167). */
  parcelas?: number;
};

/** A conta fixa (167): o molde que gera a conta de cada mês. */
export type ContaFixa = {
  id: number; id_pessoa: number; pessoa: string; id_categoria: number | null; categoria: string | null;
  descricao: string; valor: number | string; valor_variavel: boolean; dia_vencimento: number;
  inicio: string; fim: string | null; antecedencia_dias: number; agendar: boolean; forma: Forma | null;
  observacao: string | null; ativo: boolean; ultimo_mes: string | null; em_aberto: number;
  proxima: { mes: string; vencimento: string; gera_em: string } | null;
};
export type NovaContaFixa = {
  id_pessoa: number; id_categoria: number | null; descricao: string; valor: number;
  valor_variavel: boolean; dia_vencimento: number; inicio: string; fim: string | null;
  antecedencia_dias: number; agendar: boolean; forma: Forma | null; observacao: string | null;
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
/** Um dia do fluxo de caixa (etapa 4): entradas × saídas e o saldo acumulado. */
export type DiaFluxo = {
  data: string; passado: boolean; hoje: boolean;
  vendas: number; formas: Record<string, number>; vendas_previstas: number; receber: number;
  pago: number; n_pago: number; a_pagar: number; n_a_pagar: number; atrasado: number;
  fixas: number; fixas_previstas: { descricao: string; valor: number }[]; taxas: number;
  entradas: number; saidas: number; saldo: number; acumulado: number;
};
export type Fluxo = {
  hoje: string; de: string; ate: string; previsao: boolean; saldo_inicial: number;
  dias: DiaFluxo[];
  totais: { vendas: number; vendas_previstas: number; receber: number; pago: number; a_pagar: number;
            fixas: number; taxas: number; entradas: number; saidas: number; saldo: number; saldo_final: number };
  por_forma: { forma: string; rotulo: string; valor: number }[];
  atrasado: { valor: number; contas: number };
  sem_forma: { cupons: number; valor: number };
  a_receber_sem_data: { em_cobranca: number; lotes: number; sem_lote: number; pessoas: number };
  taxas_configuradas: boolean; semanas_da_previsao: number;
};
export const fluxoDeCaixa = (de: string, ate: string, previsao: boolean, saldoInicial: number) => {
  const q = new URLSearchParams({ previsao: String(previsao) });
  if (de) q.set("de", de);
  if (ate) q.set("ate", ate);
  if (saldoInicial) q.set("saldo_inicial", String(saldoInicial));
  return api.get<Fluxo>(`/contas-pagar/fluxo?${q}`);
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

export const listarFixas = (encerradas: boolean) =>
  api.get<ContaFixa[]>(`/contas-pagar/fixas${encerradas ? "?encerradas=true" : ""}`);
export const criarFixa = (c: NovaContaFixa) => api.post<Msg & { id: number; geradas: number[] }>("/contas-pagar/fixas", c);
export const alterarFixa = (id: number, c: NovaContaFixa) => api.put<Msg>(`/contas-pagar/fixas/${id}`, c);
export const encerrarFixa = (id: number, cancelar_abertas: boolean) =>
  api.post<Msg>(`/contas-pagar/fixas/${id}/encerrar`, { cancelar_abertas });
export const reativarFixa = (id: number) => api.post<Msg>(`/contas-pagar/fixas/${id}/reativar`, {});

/**
 * O total em `n` parcelas, em centavos, a sobra nas primeiras — o espelho de
 * `contas_pagar.ratear` da API, para a prévia mostrar o que vai ser gravado.
 */
export function ratear(total: number, n: number): number[] {
  const centavos = Math.round(total * 100);
  const base = Math.floor(centavos / n);
  const sobra = centavos - base * n;
  return Array.from({ length: n }, (_, i) => (base + (i < sobra ? 1 : 0)) / 100);
}

/** O mesmo dia `n` meses depois; 31 em fevereiro vira o último dia (espelho de `somar_meses`). */
export function somarMeses(iso: string, n: number): string {
  const [a, m, d] = iso.split("-").map(Number);
  const total = a * 12 + (m - 1) + n;
  const ano = Math.floor(total / 12);
  const mes = (total % 12) + 1;
  const ultimo = new Date(ano, mes, 0).getDate();
  return `${ano}-${String(mes).padStart(2, "0")}-${String(Math.min(d, ultimo)).padStart(2, "0")}`;
}

export const hojeIso = () =>
  new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
export const dataBr = (s: string | null) => (s ? s.split("-").reverse().join("/") : "—");
