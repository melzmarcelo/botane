/**
 * O que as telas de vendas conhecem de uma venda.
 *
 * Vive fora das páginas porque a lista, o detalhe e o lançamento falam da mesma
 * venda — e três cópias do mesmo tipo divergem no primeiro campo novo.
 */

export type Venda = {
  id: number;
  data: string;
  origem: string;
  canal: string | null;
  documento: string | null;
  valor_total: number;
  cancelada: boolean;
  itens: number;
  sem_custo: number;
};

export type ItemVenda = {
  id: number;
  codigo_pdv: string | null;
  descricao_pdv: string | null;
  id_produto: number | null;
  quantidade: number;
  valor_unitario: number;
  valor_total: number;
  /** ⚠️ CONGELADO no momento da importação — não é o custo de hoje. */
  custo_ficha_unitario: number | null;
  origem_custo: string | null;
  produto: string | null;
  produto_codigo: string | null;
  tipo: string | null;
  categoria: string | null;
  setor: string | null;
};

/** O movimento de estoque que a venda causou — e o que o estorno devolveu. */
export type MovimentoDaVenda = {
  id: number;
  tipo: string;
  quantidade: number;
  custo_total: number | null;
  data_movimento: string;
  id_estorno_de: number | null;
  produto: string;
  local: string | null;
};

export type VendaDetalhe = {
  id: number;
  data: string;
  hora: string | null;
  origem: string;
  canal: string | null;
  documento: string | null;
  id_externo: string | null;
  mesa: string | null;
  valor_total: number;
  desconto: number;
  cancelada: boolean;
  importada_em: string | null;
  usuario: string | null;
  itens: ItemVenda[];
  movimentos: MovimentoDaVenda[];
  receita: number;
  custo_teorico: number;
  itens_sem_custo: number;
  itens_sem_vinculo: number;
};

export const ORIGENS: Record<string, string> = {
  PDV_LEGAL: "PDV Legal",
  PLANILHA: "planilha",
  MANUAL: "lançada à mão",
};

export const CANAIS: Record<string, string> = {
  BALCAO: "balcão",
  SALAO: "salão",
  DELIVERY: "delivery",
  EVENTO: "evento",
};

/**
 * Por que este item não tem custo — dito em português.
 *
 * ⚠️ A origem do custo é o que separa "a ficha diz isto" de "não sabemos": sem
 * a frase, um custo em branco parece defeito da tela quando na verdade é o
 * cadastro que está incompleto, e é lá que alguém precisa ir.
 */
export const ORIGEM_CUSTO: Record<string, string> = {
  ficha: "ficha técnica",
  ficha_parcial: "ficha com insumo sem custo",
  ficha_sem_custo: "a ficha existe, mas nenhum insumo tem custo",
  kit: "composição do combo",
  kit_parcial: "combo com componente sem custo",
  custo_medio: "custo médio do estoque",
  ultima_compra: "último preço de compra",
  sem_produto: "o item não achou produto no cadastro",
  sem_custo: "o produto não tem ficha técnica",
};

export const dataBr = (d: string | null | undefined) =>
  d ? new Date(d.slice(0, 10) + "T12:00:00").toLocaleDateString("pt-BR") : "—";

/**
 * Lê a planilha colada (ou o CSV do PDV) e devolve as linhas.
 *
 * Aceita ponto e vírgula, vírgula ou tabulação, e número no formato brasileiro.
 * Mora aqui porque a página de lançamento a usa e a prévia mostra o resultado
 * antes de mandar — quem cola vê o que o sistema entendeu.
 */
export type LinhaPlanilha = {
  codigo: string;
  descricao: string;
  quantidade: number;
  valor_unitario: number;
};

export function lerPlanilha(texto: string): { linhas: LinhaPlanilha[]; erros: string[] } {
  const linhas: LinhaPlanilha[] = [];
  const erros: string[] = [];
  texto
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .forEach((bruta, i) => {
      const partes = bruta.split(/[;\t]|,(?=\s*[^\d])/).map((p) => p.trim());
      if (partes.length < 3) {
        erros.push(`linha ${i + 1}: esperava código; descrição; quantidade; valor`);
        return;
      }
      const [codigo, descricao, q, v] = [
        partes[0],
        partes[1] ?? "",
        partes[2] ?? "",
        partes[3] ?? "0",
      ];
      const numero = (s: string) => Number(s.replace(/\./g, "").replace(",", ".")) || 0;
      const quantidade = numero(q);
      if (!quantidade) {
        erros.push(`linha ${i + 1}: quantidade inválida (${q})`);
        return;
      }
      linhas.push({ codigo, descricao, quantidade, valor_unitario: numero(v) });
    });
  return { linhas, erros };
}
