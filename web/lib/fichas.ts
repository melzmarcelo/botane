/**
 * Fichas técnicas — camada de service (regra da casa: página não chama `api`).
 * A tela nasceu chamando a API direto; o que entra novo mora aqui.
 */
import { api } from "@/lib/api";

/** Uma versão da ficha de um produto, como `GET /fichas?id_produto=` devolve. */
export type FichaDoProduto = {
  id: number;
  versao: number;
  status: "RASCUNHO" | "HOMOLOGADA" | "ARQUIVADA" | string;
  itens: number;
};

/** Todas as versões da ficha deste produto, da mais nova para a mais velha. */
export const fichasDoProduto = (idProduto: number) =>
  api.get<FichaDoProduto[]>(`/fichas?id_produto=${idProduto}&limite=50`);

/**
 * O livro de fichas: todas as homologadas num PDF só, uma por página (23/10/2026).
 * Sai na versão da COZINHA (sem custos) — é o papel que fica no fichário.
 */
export const baixarLivroDeFichas = () => api.baixar("/exportar/livro-de-fichas.pdf");
