/**
 * Ações sobre UMA venda já lançada.
 */
import { api } from "@/lib/api";

export type VendaAlterada = {
  id: number;
  data: string;
  documento: string;
  estornados: number;
  message: string;
};

/**
 * Data e/ou número de um documento lançado à mão (23/10/2026). O que vier nulo fica
 * como está; trocar a data refaz a baixa de estoque na data nova.
 */
export const alterarVenda = (id: number, corpo: { data?: string | null; documento?: string | null }) =>
  api.put<VendaAlterada>(`/vendas/${id}`, corpo);
