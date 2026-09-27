/**
 * O consumo de uma pessoa — camada de service (regra da casa: página não chama `api`).
 */
import { api } from "@/lib/api";
import type { LinhaDocumento } from "@/app/(app)/vendas/por-pessoa/tabelas-documento";

export type CicloDeConsumo = {
  id: number;
  nome: string | null;
  inicio: string;
  fim: string;
  status: "ABERTO" | "FECHADO";
};

export type ConsumoNoCiclo = {
  /** Nulo quando a loja não tem ciclo aberto. */
  periodo: CicloDeConsumo | null;
  documentos: LinhaDocumento[];
  total_cheio: number;
  desconto: number;
  total: number;
};

/** O que a pessoa consumiu no ciclo ABERTO, por documento e com os itens. */
export const consumoNoCicloAberto = (idPessoa: number) =>
  api.get<ConsumoNoCiclo>(`/vendas/por-pessoa/${idPessoa}/ciclo-aberto`);
