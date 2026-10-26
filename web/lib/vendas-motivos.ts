/**
 * Documentos por motivo — camada de service (regra da casa: página não chama `api`).
 *
 * 🔑 Pedido do dono (26/10/2026): filtros e quadros por motivo, com impressão e
 * comparativo. O servidor manda tudo numa resposta (`GET /vendas/motivos`), e o
 * arquivo (`/exportar/vendas-motivos`) sai da MESMA conta.
 */
import { api } from "@/lib/api";

export type AgruparMotivos = "dia" | "semana" | "mes";

export type LinhaMotivo = {
  motivo: string;
  rotulo: string;
  documentos: number;
  itens: number;
  /** O que SAIU DO ESTOQUE, líquido de estorno — a mesma conta do CMV. */
  custo: number;
  /** Congelado no item: o que não controla estoque não sai do razão. */
  custo_ficha: number;
  /** O preço digitado — fora da receita, só para informação. */
  referencia: number;
  anterior: { documentos: number; custo: number };
  /** Nulo sem base para comparar. */
  pct_custo: number | null;
};

export type DocumentoMotivo = {
  id: number; data: string; documento: string | null; motivo: string; rotulo: string;
  motivo_observacao: string | null; pessoa: string | null; motivo_perda: string | null;
  itens: number; custo: number; custo_ficha: number; referencia: number; sem_custo: number;
};

export type PainelMotivos = {
  inicio: string;
  fim: string;
  agrupar: AgruparMotivos;
  rotulos: Record<string, string>;
  totais: { documentos: number; itens: number; custo: number; custo_ficha: number;
            referencia: number };
  comparacao: { inicio: string; fim: string; rotulo: string; documentos: number;
                custo: number; pct_custo: number | null; pct_documentos: number | null };
  por_motivo: LinhaMotivo[];
  serie: { periodo: string; custo: number; documentos: number;
           por_motivo: Record<string, number> }[];
  produtos: { id_produto: number; codigo: string | null; produto: string;
              um_estoque: string | null; quantidade: number; custo: number;
              documentos: number }[];
  pessoas: { id_pessoa: number | null; nome: string; documentos: number; custo: number;
             referencia: number }[];
  motivos_perda: { id: number | null; nome: string; documentos: number; custo: number }[];
  documentos: DocumentoMotivo[];
  documentos_cortados: boolean;
  /** A perda lançada em Ajustes — referência, só sem pessoa e com a Perda no filtro. */
  perdas_ajuste: { custo: number; anterior: number; pct_custo: number | null } | null;
};

export type FiltroMotivos = {
  inicio?: string;
  fim?: string;
  motivos?: string[];
  idPessoa?: number | null;
  agrupar?: AgruparMotivos;
};

export function pedirMotivos(f: FiltroMotivos) {
  const q = new URLSearchParams();
  if (f.inicio) q.set("inicio", f.inicio);
  if (f.fim) q.set("fim", f.fim);
  for (const m of f.motivos ?? []) q.append("motivos", m);
  if (f.idPessoa) q.set("id_pessoa", String(f.idPessoa));
  if (f.agrupar) q.set("agrupar", f.agrupar);
  return api.get<PainelMotivos>(`/vendas/motivos?${q}`);
}
