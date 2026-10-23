/**
 * O consumo de uma pessoa — camada de service (regra da casa: página não chama `api`).
 */
import { api } from "@/lib/api";
import type { LinhaDocumento } from "@/app/(app)/vendas/por-pessoa/tabelas-documento";

export type ConsumoEmAberto = {
  documentos: LinhaDocumento[];
  total_cheio: number;
  desconto: number;
  total: number;
  /** O que já foi mandado em lote e ainda não voltou. */
  lotes_em_cobranca: number;
  em_cobranca: number;
};

/** O que a pessoa consumiu e ainda não foi cobrado, por documento e com os itens. */
export const consumoEmAberto = (idPessoa: number) =>
  api.get<ConsumoEmAberto>(`/vendas/por-pessoa/${idPessoa}/em-aberto`);
