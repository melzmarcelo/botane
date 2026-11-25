import { api } from "@/lib/api";

/**
 * Recebimento de notas (migração 162, pedido do dono de 24/11/2026): registrar que a nota
 * chegou — número, fornecedor, data e foto opcional — e ver se ela já está no sistema.
 */

export type SituacaoRecebimento = "LANCADA" | "NO_SISTEMA" | "FALTA";

export const SITUACOES: Record<SituacaoRecebimento, string> = {
  FALTA: "Não chegou ao sistema",
  NO_SISTEMA: "No sistema, falta lançar",
  LANCADA: "Lançada",
};

export type Recebimento = {
  id: number;
  numero_nota: string;
  id_fornecedor: number | null;
  fornecedor: string | null;
  data_nota: string;
  observacao: string | null;
  tem_foto: boolean;
  recebido_por: number | null;
  recebido_por_nome: string | null;
  registrado_em: string;
  id_nota: number | null;
  situacao: SituacaoRecebimento;
};

export const listarRecebimentos = (q: Record<string, string>) =>
  api.listar<Recebimento>(`/recebimentos?${new URLSearchParams(q)}`);

export const resumoRecebimentos = () => api.get<{ faltam: number }>("/recebimentos/resumo");

export const registrarRecebimento = (corpo: FormData) =>
  api.upload<{ id: number; message: string }>("/recebimentos", corpo);

export const fotoDoRecebimento = (id: number) => api.imagem(`/recebimentos/${id}/foto`);

export const excluirRecebimento = (id: number) =>
  api.delete<{ message: string }>(`/recebimentos/${id}`);
