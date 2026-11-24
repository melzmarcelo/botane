import { api } from "@/lib/api";

/** Conferência do caixa e taxas por forma de pagamento (migração 161). */

export type DiaCaixa = {
  data: string;
  cupons: number;
  cupons_dinheiro: number;
  sem_forma: number;
  recebido: number;
  troco: number;
  esperado: number;
  contado: number | null;
  diferenca: number | null;
  observacao: string | null;
  conferido_por: string | null;
  conferido_em: string | null;
};

export type ConferenciaCaixa = {
  inicio: string;
  fim: string;
  dias: DiaCaixa[];
  totais: { esperado: number; conferidos: number; a_conferir: number; diferenca: number };
};

export type TaxasPagamento = {
  linhas: { grupo: string; rotulo: string; taxa_pct: number | null; peso_pct: number | null }[];
  dias_do_mix: number;
  taxa_media_real: number | null;
  configuradas: boolean;
};

export const conferenciaCaixa = (inicio: string, fim: string) =>
  api.get<ConferenciaCaixa>(`/caixa/conferencia?${new URLSearchParams({ inicio, fim })}`);

export const gravarContado = (dia: string, contado: number, observacao: string | null) =>
  api.put<{ message: string }>(`/caixa/conferencia/${dia}`, { contado, observacao });

export const taxasPagamento = () => api.get<TaxasPagamento>("/caixa/taxas");

export const gravarTaxas = (itens: { grupo: string; taxa_pct: number | null }[]) =>
  api.put<TaxasPagamento & { message: string }>("/caixa/taxas", { itens });
