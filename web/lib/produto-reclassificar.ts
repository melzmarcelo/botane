import { api } from "@/lib/api";

/**
 * Reclassificar produtos por planilha: tipo, categoria, setor e local padrão.
 * Ver `api/services/reclassificacao.py`.
 */
export type ResultadoReclassificacao = {
  /** Os que mudam, com o de-para pelo NOME de cada campo. */
  mudam: {
    id: number;
    codigo: string;
    nome: string;
    de: Record<string, string | null>;
    para: Record<string, string | null>;
  }[];
  iguais: number;
  recusados: { linha: number; codigo: string; nome: string | null; motivo: string }[];
  linhas: number;
  aplicado: boolean;
  message: string;
};

export function reclassificar(arquivo: File, simular: boolean) {
  const f = new FormData();
  f.append("arquivo", arquivo);
  return api.upload<ResultadoReclassificacao>(
    `/produtos/reclassificar?simular=${simular ? "true" : "false"}`, f);
}
