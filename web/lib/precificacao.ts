/**
 * Precificação — camada de service (regra da casa: página não chama `api`).
 * A conta mora no servidor (`api/services/precificacao.py`); o estudo, em
 * `docs/precificacao-estudo.md`.
 */
import { api } from "@/lib/api";

export type TipoDeLinha = "PERCENTUAL" | "VALOR" | "MARGEM";
export type Alcance = "TUDO" | "CATEGORIA" | "SETOR";
export type Arredondamento = "NOVENTA" | "MEIO" | "NENHUM";

/** Uma linha da configuração: percentual da venda, valor por unidade ou a margem. */
export type Linha = {
  nome: string;
  tipo: TipoDeLinha;
  valor: number;
  alcance: Alcance;
  id_categoria: number | null;
  id_setor: number | null;
  categoria?: string | null;
  setor?: string | null;
};

export type ConfigDePrecificacao = {
  id_unidade: number;
  /** Esta loja SEGUE outra: aqui é só consulta, e é lá que se edita. */
  somente_leitura: boolean;
  id_unidade_origem: number | null;
  origem: string | null;
  seguida_por: { id: number; nome: string }[];
  arredondamento: Arredondamento;
  linhas: Linha[];
  /** Há ao menos um percentual ou margem: sem isso a análise não tem o que calcular. */
  configurada: boolean;
};

export type Situacao = "prejuizo" | "abaixo" | "sem_preco" | "sem_custo" | "sem_conta" | "na_margem";

export type ItemDaAnalise = {
  id_produto: number;
  codigo: string | null;
  nome: string;
  categoria: string | null;
  setor: string | null;
  origem_custo: string | null;
  custo_direto: number | null;
  preco: number | null;
  /** O PISO que entrega a margem — não um alvo. */
  sugerido: number | null;
  margem_alvo_pct: number | null;
  soma_pct: number | null;
  lucro: number | null;
  lucro_pct: number | null;
  /** Positiva: falta para o piso. Negativa: é a folga. */
  diferenca: number | null;
  vendido: number;
  /** Só para quem está abaixo do piso: diferença × quantidade vendida. */
  impacto: number | null;
  situacao: Situacao;
};

export type Analise = {
  dias: number;
  configurada: boolean;
  somente_leitura: boolean;
  origem: string | null;
  resumo: {
    produtos: number;
    abaixo: number;
    prejuizo: number;
    sem_custo: number;
    com_conta: number;
    impacto: number;
  };
  itens: ItemDaAnalise[];
};

export type Simulacao = {
  id_produto: number;
  preco: number;
  origem_custo: string | null;
  custo_direto: number;
  sugerido: number | null;
  margem_alvo_pct: number;
  lucro: number;
  lucro_pct: number;
  food_cost_pct: number;
  /** Para onde vai cada real desta venda. A soma é o preço. */
  partes: { nome: string; tipo: "percentual" | "custo" | "lucro" | "prejuizo"; pct: number | null; valor: number }[];
  valores_por_unidade: { nome: string; valor: number }[];
};

export type ResultadoDeAplicar = {
  aplicados: { id_produto: number; nome: string; de: number | null; para: number; da_loja: boolean }[];
  sem_mudanca: number;
  integrados_ao_pdv: number;
  envia_ao_pdv: boolean;
  message: string;
};

export const lerConfig = () => api.get<ConfigDePrecificacao>("/precificacao/config");

/** ⚠️ Substitui a configuração INTEIRA da loja atual. */
export const gravarConfig = (corpo: {
  id_unidade_origem: number | null;
  arredondamento: Arredondamento;
  linhas: Omit<Linha, "categoria" | "setor">[];
}) => api.put<ConfigDePrecificacao & { message: string }>("/precificacao/config", corpo);

/** O faturamento dos últimos meses fechados — base da calculadora do custo operacional. */
export const faturamentoRecente = () =>
  api.get<{ mes: string; receita: number }[]>("/precificacao/faturamento");

export const analisar = (dias = 30) => api.get<Analise>(`/precificacao/analise?dias=${dias}`);

/** A decomposição de UMA venda a um dado preço. Não grava nada. */
export const simular = (idProduto: number, preco: number) =>
  api.post<Simulacao>("/precificacao/simular", { id_produto: idProduto, preco });

export const aplicarPrecos = (itens: { id_produto: number; preco: number }[]) =>
  api.post<ResultadoDeAplicar>("/precificacao/aplicar", { itens });

/**
 * Alíquota efetiva do Simples Nacional, Anexo I (comércio) — LC 123/2006:
 * (RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12.
 *
 * ⚠️ É uma CALCULADORA de apoio para preencher o campo de imposto, não regra do
 * sistema: o percentual que vale é o que a casa gravar, e ele deve ser
 * confirmado com a contabilidade. Nula acima do teto do Simples.
 */
export function simplesEfetivo(rbt12: number): number | null {
  const faixas: [number, number, number][] = [
    [180_000, 4, 0], [360_000, 7.3, 5_940], [720_000, 9.5, 13_860],
    [1_800_000, 10.7, 22_500], [3_600_000, 14.3, 87_300], [4_800_000, 19, 378_000],
  ];
  const faixa = faixas.find((f) => rbt12 <= f[0]);
  return faixa && rbt12 > 0 ? ((rbt12 * faixa[1]) / 100 - faixa[2]) / rbt12 * 100 : null;
}

/** As categorias e os setores em que uma linha pode valer. */
export const listarCategorias = () => api.get<{ id: number; nome: string }[]>("/categorias");
export const listarSetores = () => api.get<{ id: number; nome: string }[]>("/setores");
