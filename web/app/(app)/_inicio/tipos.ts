/**
 * O que `GET /inicio` devolve — os blocos da tela inicial.
 *
 * ⚠️ Cada bloco que depende de módulo ou permissão vem NULO quando não se aplica (sem Portal,
 * sem permissão, sem dinheiro para quem não vê valores): a tela não desenha o cartão, em vez
 * de desenhar um cartão vazio que se leria como "não houve nada".
 */
import type { PedidosDoInicio } from "./listas";

export type Alerta = {
  chave: string;
  severidade: "critico" | "atencao" | "aviso";
  titulo: string;
  quantidade: number;
  detalhe: string;
  acao: string;
  href: string;
};

export type Dia = {
  data: string;
  vendas: number;
  canceladas: number;
  valor_cancelado: number;
  itens: number;
  receita: number;
  ticket_medio: number | null;
  anterior: string | null;
  proximo: string | null;
  /** O mesmo dia da semana anterior (até a mesma hora, se o dia é hoje). */
  comparacao: { data: string; receita: number; ate_hora: string | null; pct: number | null } | null;
};

export type Periodo = {
  inicio: string;
  fim: string;
  rotulo: string;
  ciclo: string;
  termos: { o: string; do: string; deste: string; neste: string };
};

export type Dinheiro = {
  estoque_agora: number;
  compras_mes: number;
  cmv_mes: number;
  perdas_mes: number;
  receita_mes: number;
  vendas: number;
  food_cost_pct: number | null;
  variancia: number | null;
  cobertura_ficha_pct: number;
  cmv_teorico: number;
  meta_food_cost_pct: number | null;
};

export type Producao = {
  linhas: {
    id: number;
    id_produto: number;
    produto: string;
    um_estoque: string | null;
    data_prevista: string;
    quantidade: number;
    setor: string | null;
    atrasada: boolean;
  }[];
  total: number;
  atrasadas: number;
  hoje: number;
  todos_setores: boolean;
  setores: string[];
};

export type Reservas = {
  linhas: {
    id: number;
    data: string;
    hora: string;
    pessoas: number;
    nome: string;
    status: "PENDENTE" | "CONFIRMADA";
    origem: string;
  }[];
  total: number;
  hoje: number;
  pessoas_hoje: number;
  pendentes: number;
};

export type Painel = {
  periodo: Periodo;
  operacao: {
    produtos: number;
    fichas: number;
    notas_abertas: number;
    itens_a_vincular: number;
    vencendo: number;
    abaixo_minimo: number;
    movimentos_mes: number;
  };
  alertas: Alerta[];
  dinheiro: Dinheiro | null;
  dia: Dia | null;
  pesos: { grupo: string; cmv: number; participacao_pct: number }[];
  producao: Producao | null;
  reservas: Reservas | null;
  pedidos?: PedidosDoInicio | null;
  etiquetas?: { vencidas: number; hoje: number } | null;
};

/** "2026-09-29" → "29/09". */
export const diaCurto = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
