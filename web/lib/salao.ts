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

export type Salao = {
  id: number;
  nome: string;
  ativo: boolean;
  ordem: number;
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
  junta_com: number | null;
  junta_com_nome: string | null;
};

export type DadosDoSalao = {
  saloes: Salao[];
  mesas: Mesa[];
  mesas_ativas: number;
  lugares: number;
  capacidade_max: number;
  maior_grupo: number;
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

export const simularGrupo = (pessoas: number) =>
  api.get<Simulacao>(`/reservas/salao/simular?pessoas=${pessoas}`);

export const criarSalao = (nome: string, ordem: number) =>
  api.post<Recado & { id: number }>("/reservas/saloes", { nome, ordem });

export const mudarSalao = (id: number, corpo: { nome?: string; ativo?: boolean }) =>
  api.put<Recado>(`/reservas/saloes/${id}`, corpo);

export const excluirSalao = (id: number) => api.delete<Recado>(`/reservas/saloes/${id}`);

export const criarMesasEmLote = (corpo: Record<string, unknown>) =>
  api.post<Recado>("/reservas/mesas/em-lote", corpo);

/** ⚠️ `junta_com` só vai quando MUDOU: ausente é "não falei da junta", e nulo é
 * "desfaça" — o servidor separa os dois, e mandar sempre soltaria o par à toa. */
export const mudarMesa = (
  id: number,
  corpo: {
    nome?: string;
    lugares?: number;
    capacidade_max?: number;
    ativo?: boolean;
    caracteristicas?: Caracteristica[];
    junta_com?: number | null;
  },
) => api.put<Recado>(`/reservas/mesas/${id}`, corpo);

export const excluirMesa = (id: number) => api.delete<Recado>(`/reservas/mesas/${id}`);
