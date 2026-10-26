"use client";

/** Tipos e rótulos compartilhados pelas telas de cadastro. */

import { api } from "./api";

export type Setor = {
  id: number;
  nome: string;
  cor: string | null;
  ordem: number;
  ativo: boolean;
  /** O setor daqui é a IMPRESSORA do cardápio do PDV (VITRINE, BAR, COZINHA). */
  integrado_pdv: boolean;
  /** O "uso previsto" — a dica do campo Setor no cadastro do produto (133). */
  descricao?: string | null;
};
export type Local = {
  id: number;
  id_unidade: number;
  nome: string;
  tipo: string;
  principal: boolean;
  ativo: boolean;
  /** A que setor esta prateleira pertence. Nulo no estoque geral, que serve a
      todos os setores — e é a resposta certa para o Estoque Central. */
  id_setor?: number | null;
  setor?: string | null;
  /** O nome da loja dona da prateleira — importa quando há mais de uma. */
  loja?: string | null;
};
export type Categoria = {
  id: number;
  id_pai: number | null;
  nome: string;
  caminho: string;
  nivel: number;
  /** Opcional desde a 131: a categoria é independente do tipo. */
  tipo: string | null;
  ordem: number;
  ativo: boolean;
  /** A categoria daqui é o GRUPO do cardápio do PDV. */
  integrado_pdv: boolean;
  produtos: number;
  /** "Exemplos / abrangência" — a dica do campo Categoria no cadastro do produto (133). */
  descricao?: string | null;
};
export type UnidadeMedida = {
  sigla: string;
  nome: string;
  grandeza: string;
  fator_base: number;
  ativo: boolean;
};

/** O que juntar uma unidade em outra vai mexer (23/10/2026). */
export type PreviaJuntar = {
  absorvida: UnidadeMedida;
  principal: UnidadeMedida;
  produtos_estoque: number;
  produtos_compra: number;
  fichas: number;
  inventario: number;
  etiquetas: number;
  movimentos_no_razao: number;
  apelidos_que_mudam: string[];
  conflitos: { id: number; codigo: string; nome: string; fator_absorvida: number;
               fator_principal: number }[];
  pode: boolean;
};

export const previaJuntarUnidade = (absorvida: string, principal: string) =>
  api.get<PreviaJuntar>(
    `/unidades-medida/${encodeURIComponent(absorvida)}/juntar?em=${encodeURIComponent(principal)}`);

export const juntarUnidade = (absorvida: string, principal: string) =>
  api.post<{ message: string }>(
    `/unidades-medida/${encodeURIComponent(absorvida)}/juntar`, { em: principal });
export type Fornecedor = {
  id: number;
  nome: string;
  nome_fantasia: string | null;
  cnpj: string | null;
  email: string | null;
  telefone: string | null;
  whatsapp: string | null;
  contato: string | null;
  cidade: string | null;
  uf: string | null;
  prazo_entrega_dias: number | null;
  dias_entrega: string | null;
  pedido_minimo: number | null;
  observacao: string | null;
  ativo: boolean;
  produtos?: number;
  /**
   * Esta pessoa vende para a casa?
   *
   * ⚠️ **Opcional, e ausente quer dizer SIM.** A coluna nasceu em 04/09/2026
   * com padrão verdadeiro; um cadastro lido de uma resposta antiga não a traz, e
   * tratá-lo como "não é fornecedor" o sumiria dos seletores de compra.
   */
  fornecedor?: boolean;
  /** A base do cupom na venda lançada à mão: o preço de venda ou o custo. */
  cupom_base?: "VENDA" | "CUSTO";
  cupom_desconto_pct?: number;
  /** Quem entra no sistema como esta pessoa — nulo é o caso comum. */
  usuario?: string | null;
};

export type ProdutoResumo = {
  id: number;
  codigo: string;
  nome: string;
  tipo: string;
  categoria: string | null;
  setor: string | null;
  um_estoque: string | null;
  producao_propria: boolean;
  controla_estoque: boolean;
  controla_lote?: boolean;
  status: string;
  ativo: boolean;
  preco_venda: number | null;
};

export const TIPOS_PRODUTO = [
  { valor: "INSUMO", nome: "Insumo", ajuda: "Entra por nota e sai pela ficha técnica" },
  { valor: "PRODUZIDO", nome: "Produzido", ajuda: "Nasce de uma ficha e é o que se vende" },
  { valor: "REVENDA", nome: "Revenda", ajuda: "Compra e vende inteiro, sem receita" },
  { valor: "KIT", nome: "Kit", ajuda: "Conjunto de outros produtos" },
  { valor: "EMBALAGEM", nome: "Embalagem", ajuda: "Copo, sacola, marmita" },
  // 🔑 Reestruturação de 23/10/2026 (documento da casa, migração 131): o antigo
  // "Material de limpeza" virou o consumível da rotina inteira, e entraram
  // Patrimônio e Serviço. ⚠️ Espelha `TIPOS` de api/models/produtos.py.
  {
    valor: "MATERIAL_OPERACIONAL",
    nome: "Material operacional",
    ajuda:
      "Consumível da rotina: limpeza, descartável, escritório, a copa — " +
      "fica fora do custo dos produtos",
  },
  {
    valor: "UTENSILIO",
    nome: "Utensílios",
    ajuda:
      "Prato, talher, taça, panela, avental — não é consumido pela receita: " +
      "quebra, some e é reposto. Fica fora do CMV real",
  },
  {
    valor: "PATRIMONIO",
    nome: "Patrimônio",
    ajuda: "Bem durável — processador, batedeira, móvel. Controle patrimonial, fora do CMV",
  },
  {
    valor: "SERVICO",
    nome: "Serviço",
    ajuda: "Não é físico — taxa de entrega. Nunca controla estoque",
  },
];

/** A explicação que a CASA deu a um tipo (133). A lista de tipos é do sistema. */
export type TipoDescricao = { tipo: string; descricao: string | null };

export const listarDescricoesDeTipo = () => api.get<TipoDescricao[]>("/tipos-produto");
export const gravarDescricaoDeTipo = (tipo: string, descricao: string) =>
  api.put<{ message: string }>(`/tipos-produto/${encodeURIComponent(tipo)}`, { descricao });

/**
 * O que a dica do Tipo diz: a descrição da casa, se houver; senão a ajuda do código.
 * ⚠️ A ajuda do código fica como reserva de propósito — base sem a migração 133, ou
 * descrição apagada na tela, não deixa o campo sem explicação nenhuma.
 */
export const explicacaoDoTipo = (tipo: string, descricoes: TipoDescricao[]) =>
  descricoes.find((d) => d.tipo === tipo)?.descricao
  ?? TIPOS_PRODUTO.find((t) => t.valor === tipo)?.ajuda
  ?? "";

export const TIPOS_LOCAL = ["SECO", "RESFRIADO", "CONGELADO", "BAR"];
// 🔑 O tipo da categoria é OPCIONAL desde a 131 ("Tipo, Categoria e Setor são campos
// independentes", documento da casa). Quando preenchido, é um dos tipos de produto —
// a mesma lista, para não haver uma segunda que esqueça um tipo.
export const TIPOS_CATEGORIA = TIPOS_PRODUTO.map((t) => t.valor);
export const GRANDEZAS = ["MASSA", "VOLUME", "UNIDADE"];

export const nomeTipo = (t: string) =>
  TIPOS_PRODUTO.find((x) => x.valor === t)?.nome ?? t.toLowerCase();

// ⚠️ **A implementação mora em `lib/numeros.ts`**, junto das outras três
// famílias de número (custo unitário, quantidade, percentual) — separá-las
// seria voltar a ter duas versões da mesma regra. Reexportado aqui porque
// trinta e cinco telas já pedem `reais` deste arquivo; código novo importa de
// `@/lib/numeros`.
export { reais } from "./numeros";

export function mascaraCnpj(valor: string) {
  const d = valor.replace(/\D/g, "").slice(0, 14);
  return d
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d)/, "$1-$2");
}
