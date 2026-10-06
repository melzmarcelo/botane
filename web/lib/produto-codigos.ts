/**
 * Os códigos de fora que caem num produto: a conversão e o desvínculo.
 *
 * 🔑 **Camada de service** — o cartão de códigos nasceu chamando a API direto;
 * o que entrou com o desvincular (06/10/2026) já mora aqui.
 */
import { api } from "@/lib/api";

export type PreviaDoDesvinculo = {
  sistema: string;
  codigo: string;
  descricao: string | null;
  fornecedor: string | null;
  id_fornecedor: number | null;
  origem: string | null;
  /** O cadastro absorvido que volta a existir com este código, se der para saber. */
  devolve_para: { id: number; codigo: string; nome: string } | null;
  /** Itens de nota ainda não lançada apontando para este produto. */
  itens_de_nota_abertos: number;
};

type Linha = { sistema: string; codigo: string; id_fornecedor?: number | null };

export const previaDoDesvinculo = (idProduto: number, c: Linha) => {
  const q = new URLSearchParams({ sistema: c.sistema, codigo: c.codigo });
  if (c.id_fornecedor) q.set("id_fornecedor", String(c.id_fornecedor));
  return api.get<PreviaDoDesvinculo>(`/produtos/${idProduto}/codigos/desvinculo/previa?${q}`);
};

export const desvincularCodigo = (idProduto: number, c: Linha, devolver: boolean) =>
  api.post<{ message: string; devolvido_para: { id: number; nome: string } | null }>(
    `/produtos/${idProduto}/codigos/desvincular`,
    { sistema: c.sistema, codigo: c.codigo, id_fornecedor: c.id_fornecedor ?? null, devolver },
  );
