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

/** Um código da origem, como a prévia de "mover códigos" o descreve. */
export type CodigoMovivel = {
  sistema: string;
  codigo: string;
  id_fornecedor: number | null;
  fornecedor: string | null;
  descricao: string | null;
  /** "principal" (coluna do cadastro) · "vinculado" (apelido) · "fornecedor" (código no fornecedor) */
  onde: "principal" | "vinculado" | "fornecedor";
  fator: number | null;
  fator_confirmado: boolean;
  /** Decide a quantidade da nota: sem a conversão, não se move. */
  pede_fator: boolean;
  fator_sugerido: number | null;
  ultima_nota: { fator: number; um_nota: string | null; data: string | null } | null;
  bloqueio?: string;
};

type LadoDaMudanca = { id: number; codigo: string; nome: string; um_estoque: string | null; ativo: boolean };

export type PreviaDaMudanca = {
  origem: LadoDaMudanca;
  destino: LadoDaMudanca;
  mesma_unidade: boolean;
  impedimentos: string[];
  pode: boolean;
  codigos: CodigoMovivel[];
  itens_de_nota_abertos: number;
};

export const previaDaMudanca = (idOrigem: number, idDestino: number) =>
  api.get<PreviaDaMudanca>(`/produtos/${idOrigem}/codigos/mudanca/previa?id_destino=${idDestino}`);

export const moverCodigos = (
  idOrigem: number,
  idDestino: number,
  codigos: { sistema: string; codigo: string; id_fornecedor: number | null; fator: number | null }[],
) =>
  api.post<{ message: string; itens_de_nota: number }>(`/produtos/${idOrigem}/codigos/mover`, {
    id_destino: idDestino,
    codigos,
  });

/** Corrige só o texto do "O que é lá" — produto, fator e cascata não mudam. */
export const renomearCodigo = (idProduto: number, c: Linha, descricao: string) =>
  api.put<{ message: string }>(`/produtos/${idProduto}/codigos/descricao`, {
    sistema: c.sistema,
    codigo: c.codigo,
    id_fornecedor: c.id_fornecedor ?? null,
    descricao,
  });
