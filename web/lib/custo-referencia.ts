import { api } from "@/lib/api";

/** Uma linha da conferência do custo de referência.
 *
 * `confianca: "alta"` é quando duas coisas independentes concordam (o razão e a
 * embalagem, ou o razão e o preço) — a tela traz marcada. O resto é palpite. */
export type CustoSuspeito = {
  id_produto: number;
  codigo: string | null;
  produto: string;
  um: string | null;
  um_omie: string | null;
  referencia: number;
  desde: string | null;
  origem: string | null;
  razao: number | null;
  preco: number | null;
  sugerido: number | null;
  motivo: string;
  confianca: "alta" | "conferir";
};

export type ConferenciaDeReferencia = {
  analisados: number;
  suspeitos: number;
  certos: number;
  linhas: CustoSuspeito[];
};

export const conferirReferencia = () =>
  api.get<ConferenciaDeReferencia>("/ajustes/custo-referencia/previa");

export const corrigirReferencia = (itens: { id_produto: number; custo: number }[]) =>
  api.post<{ corrigidos: number; vendas_recalculadas: number; message: string }>(
    "/ajustes/custo-referencia",
    { itens },
  );
