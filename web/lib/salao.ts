/**
 * O salão da casa: salões, mesas, características e a conferência do cadastro.
 *
 * 🔑 **Camada de service** — a tela do salão nasceu chamando a API direto; ao
 * ser refeita (06/10/2026, `docs/salao-estudo.md`) as chamadas vieram para cá.
 */
import { api } from "@/lib/api";

/** A lista FIXA da migração 106, com o rótulo que a tela mostra. */
export const CARACTERISTICAS = [
  { chave: "JANELA", rotulo: "janela" },
  { chave: "SOFA", rotulo: "sofá" },
  { chave: "ACESSIVEL", rotulo: "acessível" },
  { chave: "CADEIRAO", rotulo: "cadeirão" },
  { chave: "TOMADA", rotulo: "tomada" },
  { chave: "COBERTA", rotulo: "coberta" },
] as const;

export type Caracteristica = (typeof CARACTERISTICAS)[number]["chave"];

export const rotuloDaCaracteristica = (chave: string) =>
  CARACTERISTICAS.find((c) => c.chave === chave)?.rotulo ?? chave.toLowerCase();

/** O formato da mesa (migração 108) — só para desenhar a planta. */
export const FORMATOS = [
  { chave: "QUADRADA", rotulo: "quadrada" },
  { chave: "REDONDA", rotulo: "redonda" },
  { chave: "RETANGULAR", rotulo: "retangular" },
] as const;

export type Formato = (typeof FORMATOS)[number]["chave"];

/** Os dias da semana no formato do servidor: ISO, 1 = segunda … 7 = domingo. */
export const DIAS_DA_SEMANA = [
  { n: 1, curto: "seg", longo: "segunda" },
  { n: 2, curto: "ter", longo: "terça" },
  { n: 3, curto: "qua", longo: "quarta" },
  { n: 4, curto: "qui", longo: "quinta" },
  { n: 5, curto: "sex", longo: "sexta" },
  { n: 6, curto: "sáb", longo: "sábado" },
  { n: 7, curto: "dom", longo: "domingo" },
] as const;

export type Salao = {
  id: number;
  nome: string;
  ativo: boolean;
  ordem: number;
  /** Os dias em que o salão atende (migração 109). Nunca vazio. */
  dias_semana: number[];
  /** Falso = a recepção usa, mas o site não oferece as mesas deste salão. */
  aceita_site: boolean;
  mesas: number;
  lugares: number;
};

export type Mesa = {
  id: number;
  id_salao: number;
  nome: string;
  lugares: number;
  capacidade_max: number;
  ativo: boolean;
  caracteristicas: Caracteristica[];
  formato: Formato;
  /** Onde a mesa está na planta; nulo enquanto ninguém a posicionou. */
  pos_x: number | null;
  pos_y: number | null;
};

/** De 2 a 4 mesas que se juntam, com capacidade PRÓPRIA (migração 109). */
export type Conjunto = {
  id: number;
  /** O que a casa informou — é o número que a alocação usa. */
  capacidade: number;
  mesas: { id: number; nome: string; id_salao: number }[];
  /** A soma dos máximos das mesas, para a tela mostrar ao lado. */
  soma_maximos: number;
};

export type DadosDoSalao = {
  saloes: Salao[];
  mesas: Mesa[];
  conjuntos: Conjunto[];
  mesas_ativas: number;
  lugares: number;
  capacidade_max: number;
  maior_grupo: number;
  /** O maior grupo que o SITE consegue sentar: sem os salões fora do site. */
  maior_grupo_site: number;
  /** O maior grupo que o site aceita; nulo enquanto a loja não configurou. */
  teto_online: number | null;
};

/** Onde um grupo sentaria com o salão vazio — a conferência do cadastro. */
export type Simulacao = {
  pessoas: number;
  cabe: boolean;
  como: "mesa" | "junta" | null;
  mesas: { id: number; nome: string; salao: string | null; capacidade_max: number }[];
  capacidade: number;
  maior_grupo: number;
  teto_online: number | null;
};

type Recado = { message: string };

export const lerSalao = () => api.get<DadosDoSalao>("/reservas/salao");

/** `diaSemana` e `site` escolhem QUAIS salões entram — o mesmo filtro da disponibilidade. */
export const simularGrupo = (pessoas: number, diaSemana: number | null = null, site = false) =>
  api.get<Simulacao>(
    `/reservas/salao/simular?pessoas=${pessoas}` +
      (diaSemana ? `&dia_semana=${diaSemana}` : "") + (site ? "&site=true" : ""),
  );

export const criarSalao = (nome: string, ordem: number) =>
  api.post<Recado & { id: number }>("/reservas/saloes", { nome, ordem });

export const mudarSalao = (
  id: number,
  corpo: { nome?: string; ativo?: boolean; dias_semana?: number[]; aceita_site?: boolean },
) =>
  api.put<Recado>(`/reservas/saloes/${id}`, corpo);

export const excluirSalao = (id: number) => api.delete<Recado>(`/reservas/saloes/${id}`);

export const criarMesasEmLote = (corpo: Record<string, unknown>) =>
  api.post<Recado>("/reservas/mesas/em-lote", corpo);

export const mudarMesa = (
  id: number,
  corpo: {
    nome?: string;
    lugares?: number;
    capacidade_max?: number;
    ativo?: boolean;
    caracteristicas?: Caracteristica[];
    formato?: Formato;
  },
) => api.put<Recado>(`/reservas/mesas/${id}`, corpo);

/** A planta gravada de uma vez: arrastar é rascunho, e quem grava é o botão. */
export const gravarPlanta = (posicoes: { id: number; pos_x: number; pos_y: number }[]) =>
  api.put<Recado>("/reservas/salao/planta", { posicoes });

export const criarConjunto = (mesas: number[], capacidade: number) =>
  api.post<Recado & { id: number }>("/reservas/conjuntos", { mesas, capacidade });

export const mudarConjunto = (id: number, capacidade: number) =>
  api.put<Recado>(`/reservas/conjuntos/${id}`, { capacidade });

export const excluirConjunto = (id: number) => api.delete<Recado>(`/reservas/conjuntos/${id}`);

export const excluirMesa = (id: number) => api.delete<Recado>(`/reservas/mesas/${id}`);
