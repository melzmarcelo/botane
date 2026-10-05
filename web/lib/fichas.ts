/**
 * Fichas técnicas — camada de service (regra da casa: página não chama `api`).
 * A tela nasceu chamando a API direto; o que entra novo mora aqui.
 */
import { api } from "@/lib/api";

export type ItemDaFila = {
  id_produto: number;
  codigo: string | null;
  nome: string;
  /** O que falta para este produto saber o próprio custo. */
  falta: "sem_ficha" | "ficha_sem_custo" | "sem_custo";
  id_ficha: number | null;
  quantidade: number;
  /** Nulo para quem não vê custo: a cozinha recebe a ordem e o percentual. */
  receita: number | null;
  participacao_pct: number;
  /** A cobertura que a casa teria resolvendo esta linha e todas as de cima. */
  cobertura_acumulada_pct: number;
};

export type FilaDeFichas = {
  dias: number;
  /** Quanto da receita do recorte já tem custo. Nulo sem venda nenhuma. */
  cobertura_pct: number | null;
  receita: number | null;
  /** Quantos produtos vendidos estão sem custo (a fila inteira, não só a página). */
  produtos: number;
  itens: ItemDaFila[];
};

/** Os produtos VENDIDOS sem custo, do que mais pesa na receita para o que menos. */
export const filaDeFichas = (dias = 30, limite = 10) =>
  api.get<FilaDeFichas>(`/fichas/fila?dias=${dias}&limite=${limite}`);
