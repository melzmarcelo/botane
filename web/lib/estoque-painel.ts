/**
 * Painel de estoque — camada de service (regra da casa: página não chama `api`).
 *
 * 🔑 Três perguntas, três rotas: a visão geral (`/estoque/painel`), um produto
 * (`/estoque/painel/produto/{id}`) e as perdas (`/estoque/painel/perdas`). As contagens
 * da visão geral são as MESMAS do alerta da tela inicial e das listas de Saldos — o
 * cartão leva para a lista, e a lista tem o que o cartão contou.
 */
import { api } from "@/lib/api";

export type Agrupar = "dia" | "semana" | "mes";

export type Negativo = {
  id_produto: number; codigo: string; produto: string; um_estoque: string | null;
  id_local: number; local: string; quantidade: number; custo_medio: number; valor: number;
  ultimo_movimento: string | null;
};

export type Abaixo = {
  id_produto: number; codigo: string; produto: string; um_estoque: string | null;
  estoque_minimo: number; saldo: number; faltam: number; custo: number | null;
  consumo_dia: number | null; cobertura_dias: number | null; valor_repor: number | null;
  fornecedor: string | null; acao: "comprar" | "produzir";
};

export type Parado = {
  id_produto: number; codigo: string; produto: string; um_estoque: string | null;
  quantidade: number; valor: number; ultima_saida: string | null;
};

export type VisaoGeral = {
  hoje: string;
  valor_estoque: number;
  /** A parte do valor que é de produto INATIVO com saldo — as listas de Saldos não a mostram. */
  valor_inativos: number;
  produtos_com_saldo: number;
  negativos: { prateleiras: number; produtos: number; lista: Negativo[] };
  abaixo_do_minimo: { produtos: number; valor_repor: number; lista: Abaixo[] };
  validade: { dias: number; vencidos: number; valor_vencidos: number; vencendo: number;
              valor_vencendo: number };
  parados: { dias: number; produtos: number; valor: number; lista: Parado[] };
  perdas_mes: { inicio: string; fim: string; valor: number; ocorrencias: number;
                valor_anterior: number; pct_variacao: number | null };
  por_categoria: { id: number | null; nome: string; valor: number; produtos: number;
                   participacao_pct: number | null }[];
};

export type PontoProduto = {
  periodo: string; entradas: number; saidas: number; valor_entradas: number;
  valor_saidas: number; saldo: number; custo_medio: number | null;
};

export type PainelProduto = {
  produto: {
    id: number; codigo: string; nome: string; nome_curto: string | null;
    um_estoque: string | null; estoque_minimo: number | null; controla_estoque: boolean;
    producao_propria: boolean; ativo: boolean; status: string;
    categoria: string | null; setor: string | null;
  };
  inicio: string; fim: string; agrupar: Agrupar; dias: number;
  atual: {
    saldo: number; custo_medio: number | null; valor: number; abaixo_do_minimo: boolean;
    locais: { id_local: number; local: string; setor: string | null; quantidade: number;
              custo_medio: number; valor: number }[];
  };
  indicadores: {
    saldo_inicial: number; consumo: number; consumo_valor: number;
    consumo_dia: number | null; cobertura_dias: number | null;
    compras: number; compras_valor: number; perda: number; perda_valor: number;
    perda_pct_do_consumo: number | null;
    ultima_entrada: { data_movimento: string; rotulo: string; quantidade: number;
                      custo_unitario: number; documento: string | null } | null;
  };
  serie: PontoProduto[];
  por_tipo: { tipo: string; rotulo: string; entrada: boolean; quantidade: number;
              valor: number; vezes: number }[];
  ultimos: { id: number; data_movimento: string; rotulo: string; quantidade: number;
             valor: number; local: string; saldo_apos: number; documento: string | null;
             motivo: string | null; observacao: string | null; estorno: boolean }[];
  movimentos_no_periodo: number;
};

export type GrupoPerda = {
  id: number | string | null; nome: string; valor: number; qtd: number;
  ocorrencias: number; participacao_pct: number | null;
};

export type PainelPerdas = {
  inicio: string; fim: string; agrupar: Agrupar; recorte: boolean;
  totais: {
    valor: number; ocorrencias: number; produtos: number; consumo_valor: number;
    pct_do_consumo: number | null; faltas_inventario: number; sobras_inventario: number;
  };
  comparacao: { inicio: string; fim: string; valor: number; ocorrencias: number;
                pct_valor: number | null };
  serie: { periodo: string; valor: number; ocorrencias: number }[];
  por_motivo: GrupoPerda[];
  por_categoria: GrupoPerda[];
  por_setor: GrupoPerda[];
  por_local: GrupoPerda[];
  por_origem: GrupoPerda[];
  produtos: { id_produto: number; codigo: string; produto: string; um_estoque: string | null;
              valor: number; qtd: number; ocorrencias: number; motivo_principal: string | null;
              participacao_pct: number | null }[];
  produtos_total: number;
  recentes: { id: number; data_movimento: string; id_produto: number; produto: string;
              um_estoque: string | null; qtd: number; valor: number; local: string;
              motivo: string; observacao: string | null; origem_rotulo: string;
              usuario: string | null; estorno: boolean }[];
};

export type FiltrosPerdas = {
  inicio?: string; fim?: string; agrupar: Agrupar;
  motivo?: number | null; categoria?: number | null; setor?: number | null;
  local?: number | null; produto?: number | null; limite?: number;
};

export function pedirVisaoGeral(): Promise<VisaoGeral> {
  return api.get<VisaoGeral>("/estoque/painel");
}

export function pedirProduto(id: number, inicio: string | undefined, fim: string | undefined,
                             agrupar: Agrupar): Promise<PainelProduto> {
  const q = new URLSearchParams({ agrupar });
  if (inicio) q.set("inicio", inicio);
  if (fim) q.set("fim", fim);
  return api.get<PainelProduto>(`/estoque/painel/produto/${id}?${q}`);
}

export function pedirPerdas(f: FiltrosPerdas): Promise<PainelPerdas> {
  const q = new URLSearchParams({ agrupar: f.agrupar, limite: String(f.limite ?? 20) });
  if (f.inicio) q.set("inicio", f.inicio);
  if (f.fim) q.set("fim", f.fim);
  if (f.motivo !== null && f.motivo !== undefined) q.set("id_motivo", String(f.motivo));
  if (f.categoria) q.set("id_categoria", String(f.categoria));
  if (f.setor) q.set("id_setor", String(f.setor));
  if (f.local) q.set("id_local", String(f.local));
  if (f.produto) q.set("id_produto", String(f.produto));
  return api.get<PainelPerdas>(`/estoque/painel/perdas?${q}`);
}

/** O endereço da listagem de Saldos já filtrada — é para onde os cartões levam. */
export const listaNegativos = "/estoque?visao=prateleira&situacao=negativo&comSaldo=false";
export const listaAbaixo = "/estoque?visao=produto&situacao=minimo&comSaldo=false";
