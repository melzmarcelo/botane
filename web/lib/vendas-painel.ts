/**
 * Painel de vendas — camada de service (regra da casa: página não chama `api`).
 *
 * 🔑 O servidor manda tudo numa resposta só (`GET /vendas/painel`), e o arquivo
 * baixado (`/exportar/vendas`) sai da MESMA conta — por isso a tela e a planilha
 * batem número a número.
 */
import { api } from "@/lib/api";

export type Agrupar = "dia" | "semana" | "mes";
export type Ordem = "receita" | "quantidade";

export type Totais = {
  cupons: number;
  dias: number;
  itens: number;
  bruta: number;
  /** Nulo com recorte: o desconto é do cupom, não de um item. */
  desconto: number | null;
  receita: number;
  ticket_medio: number | null;
  media_por_dia: number | null;
};

export type PainelVendas = {
  inicio: string;
  fim: string;
  agrupar: Agrupar;
  ordem: Ordem;
  recorte: boolean;
  /** Com recorte, a receita é a BRUTA dos itens escolhidos. */
  bruta: boolean;
  totais: Totais;
  comparacao: {
    inicio: string; fim: string; rotulo: string;
    receita: number; cupons: number; ticket_medio: number | null;
    pct_receita: number | null; pct_cupons: number | null; pct_ticket: number | null;
  };
  canceladas: { cupons: number; valor: number } | null;
  serie: { periodo: string; cupons: number; receita: number; itens: number;
           ticket_medio: number | null }[];
  por_dia_semana: { dia_semana: number; nome: string; dias: number; cupons: number;
                    receita: number; media_receita: number; media_cupons: number }[];
  por_hora: { hora: number; cupons: number; receita: number }[];
  sem_hora: { cupons: number; receita: number } | null;
  por_categoria: Grupo[];
  por_setor: Grupo[];
  produtos: ProdutoVendido[];
  produtos_total: number;
};

export type Grupo = {
  id: number | null; nome: string; cupons: number; quantidade: number;
  receita: number; participacao_pct: number | null;
};

export type ProdutoVendido = {
  id_produto: number | null; codigo: string | null; produto: string;
  produto_curto: string | null; categoria: string | null; setor: string | null;
  cupons: number; quantidade: number; receita: number; preco_medio: number | null;
  participacao_pct: number | null;
};

export type FiltroPainel = {
  inicio?: string;
  fim?: string;
  agrupar?: Agrupar;
  ordem?: Ordem;
  limite?: number;
  categoria?: number | null;
  setor?: number | null;
};

export function pedirPainel(f: FiltroPainel) {
  const q = new URLSearchParams();
  if (f.inicio) q.set("inicio", f.inicio);
  if (f.fim) q.set("fim", f.fim);
  if (f.agrupar) q.set("agrupar", f.agrupar);
  if (f.ordem) q.set("ordem", f.ordem);
  if (f.limite) q.set("limite", String(f.limite));
  if (f.categoria) q.append("categorias", String(f.categoria));
  if (f.setor) q.append("setores", String(f.setor));
  const s = q.toString();
  return api.get<PainelVendas>(`/vendas/painel${s ? `?${s}` : ""}`);
}

/** `caminho` vem nas categorias, que são árvore ("BEBIDAS › CAFÉS"). */
export type Opcao = { id: number; nome: string; caminho?: string };

export const pedirCategorias = () => api.get<Opcao[]>("/categorias");
export const pedirSetores = () => api.get<Opcao[]>("/setores");
