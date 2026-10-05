/**
 * Preços — camada de service da Precificação (regra da casa: página não chama `api`).
 * O estudo está em `docs/precificacao-estudo.md`.
 */
import { api } from "@/lib/api";

/** Uma data em que o preço ou o custo MUDOU (ou uma ponta da janela). */
export type PontoPrecoCusto = {
  data: string;
  /** Nulo: o produto não tinha preço de venda cadastrado naquele dia. */
  preco: number | null;
  /** Nulo: o sistema não sabia o custo naquele dia — nunca zero. */
  custo: number | null;
  margem_pct: number | null;
};

export type EvolucaoPrecoCusto = {
  produto: { id: number; codigo: string | null; nome: string; um_estoque: string | null; tem_ficha: boolean };
  inicio: string;
  fim: string;
  meses: number;
  /**
   * De onde veio a linha do custo: `vendas` é o custo da ficha congelado em
   * cada venda; `razao` é o custo médio do estoque. Nulo: sem custo nenhum.
   */
  fonte_custo: "vendas" | "razao" | null;
  /** Em degraus: cada valor vale até o ponto seguinte. */
  pontos: PontoPrecoCusto[];
  mudancas_de_preco: string[];
  /** O preço médio realmente cobrado na janela, com desconto dentro. */
  praticado: { quantidade: number; preco_medio: number | null };
};

/** A evolução de preço × custo de um produto nos últimos `meses`. */
export const evolucaoPrecoCusto = (idProduto: number, meses: number) =>
  api.get<EvolucaoPrecoCusto>(`/cmv/preco-custo/${idProduto}?meses=${meses}`);
