"use client";

/** Tipos e rótulos compartilhados pelas telas de cadastro. */

export type Setor = { id: number; nome: string; cor: string | null; ordem: number; ativo: boolean };
export type Local = {
  id: number;
  id_unidade: number;
  nome: string;
  tipo: string;
  principal: boolean;
  ativo: boolean;
};
export type Categoria = {
  id: number;
  id_pai: number | null;
  nome: string;
  caminho: string;
  nivel: number;
  tipo: string;
  ordem: number;
  ativo: boolean;
  produtos: number;
};
export type UnidadeMedida = {
  sigla: string;
  nome: string;
  grandeza: string;
  fator_base: number;
  ativo: boolean;
};
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
];

export const TIPOS_LOCAL = ["SECO", "RESFRIADO", "CONGELADO", "BAR"];
export const TIPOS_CATEGORIA = ["INSUMO", "REVENDA", "PRODUZIDO", "EMBALAGEM"];
export const GRANDEZAS = ["MASSA", "VOLUME", "UNIDADE"];

export const nomeTipo = (t: string) =>
  TIPOS_PRODUTO.find((x) => x.valor === t)?.nome ?? t.toLowerCase();

export const reais = (v: number | null | undefined) =>
  v === null || v === undefined
    ? "—"
    : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export function mascaraCnpj(valor: string) {
  const d = valor.replace(/\D/g, "").slice(0, 14);
  return d
    .replace(/^(\d{2})(\d)/, "$1.$2")
    .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
    .replace(/\.(\d{3})(\d)/, ".$1/$2")
    .replace(/(\d{4})(\d)/, "$1-$2");
}
