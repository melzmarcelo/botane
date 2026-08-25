/**
 * O que a tela de compras conhece de uma nota.
 *
 * Vive fora das páginas porque a lista, a visualização e a correção falam da
 * mesma nota — e três cópias do mesmo tipo divergem no primeiro campo novo.
 */

export type Nota = {
  id: number;
  chave_nfe: string | null;
  numero: string | null;
  nome_emitente: string | null;
  fornecedor: string | null;
  data_emissao: string | null;
  valor_total: number;
  status: string;
  itens: number;
  pendentes: number;
};

export type ItemNota = {
  id: number;
  seq: number;
  descricao_fornecedor: string;
  codigo_fornecedor: string | null;
  codigo_barras: string | null;
  quantidade: number;
  um_nota: string | null;
  valor_unitario: number;
  valor_total: number;
  valor_frete_rateado: number;
  valor_outros_rateado: number;
  quantidade_convertida: number | null;
  custo_aquisicao_unitario: number | null;
  variacao_preco_pct: number | null;
  id_produto: number | null;
  produto: string | null;
  um_estoque: string | null;
  local_destino: string | null;
  sugestao_produto: number | null;
  sugestao_nome: string | null;
  sugestao_score: number | null;
  ignorado: boolean;
  lote_nf: string | null;
  validade_nf: string | null;
  valor_desconto: number;
  valor_acrescimo: number;
};

/** O cabeçalho inteiro: é dele que a visualização e a correção se enchem. */
export type NotaDetalhe = Omit<Nota, "itens"> & {
  itens: ItemNota[];
  origem: string;
  id_fornecedor: number | null;
  cnpj_emitente: string | null;
  serie: string | null;
  data_entrada: string | null;
  valor_produtos: number;
  valor_frete: number;
  valor_desconto: number;
  valor_outros: number;
  id_local: number | null;
  lancada_em: string | null;
  tem_xml: boolean;
};

export const CORES: Record<string, "erva" | "alerta" | "neutro"> = {
  LANCADA: "erva",
  CONCILIADA: "alerta",
  IMPORTADA: "neutro",
};

export const ORIGENS: Record<string, string> = {
  XML: "XML da NF-e",
  MANUAL: "digitada",
  OMIE: "Omie",
};

export const dataBr = (d: string | null | undefined) =>
  d ? new Date(d.slice(0, 10) + "T12:00:00").toLocaleDateString("pt-BR") : "—";
