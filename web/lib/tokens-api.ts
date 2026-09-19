"use client";

import { api, BASE_API } from "@/lib/api";

/** Chave de acesso de máquina — o que o conector do Claude usa para entrar.
 *
 * 🔑 A chave age COMO o usuário dono dela. O valor em claro só existe na
 * resposta da criação (`TokenApiCriado.token`); a lista nunca o traz.
 * Duas origens: `manual` (gerada na tela) e `oauth` (a pessoa conectou o Claude
 * pelo claude.ai — a chave se renova sozinha, então quem manda é `vence_em`).
 */
export type TokenApi = {
  id: number;
  nome: string;
  prefixo: string;
  somente_leitura: boolean;
  expira_em: string;
  vence_em: string;
  criado_em: string;
  criado_por: string | null;
  ultimo_uso_em: string | null;
  revogado_em: string | null;
  origem: "manual" | "oauth";
};

export type TokenApiCriado = TokenApi & { token: string };

/** O que o cartão precisa, venha a lista de um usuário (admin) ou da própria pessoa. */
export type FonteDeChaves = {
  listar: () => Promise<TokenApi[]>;
  revogar: (idToken: number) => Promise<{ message: string }>;
  criar?: (nome: string, dias: number) => Promise<TokenApiCriado>;
};

/** As chaves de um usuário, geridas por quem tem `admin.usuarios`. */
export const chavesDoUsuario = (idUsuario: number): FonteDeChaves => ({
  listar: () => api.get<TokenApi[]>(`/usuarios/${idUsuario}/tokens`),
  revogar: (idToken) => api.delete(`/usuarios/${idUsuario}/tokens/${idToken}`),
  criar: (nome, dias) =>
    api.post<TokenApiCriado>(`/usuarios/${idUsuario}/tokens`, { nome, dias }),
});

/** As da própria pessoa — ver e desconectar, sem precisar de administrador. */
export const minhasChaves: FonteDeChaves = {
  listar: () => api.get<TokenApi[]>("/auth/me/tokens"),
  revogar: (idToken) => api.delete(`/auth/me/tokens/${idToken}`),
};

/** O endereço que se cola no claude.ai (Configurações ▸ Conectores). */
export const URL_CONECTOR = `${BASE_API.replace(/\/$/, "")}/mcp`;

/** Viva, vencida ou revogada — a mesma leitura do servidor. */
export const situacaoDoToken = (t: TokenApi): "viva" | "vencida" | "revogada" =>
  t.revogado_em ? "revogada" : new Date(t.vence_em) <= new Date() ? "vencida" : "viva";
