/**
 * O assistente pelo WhatsApp (etapa 1, migração 151): o número da casa (Integrações) e o vínculo
 * do próprio telefone (Perfil).
 *
 * 🔑 Pedido do dono (06/11/2026): vincular o telefone no usuário e conversar com o sistema pelo
 * WhatsApp — por UM número, compartilhado entre as lojas. Regra em `api/services/assistente.py`,
 * estudo em `docs/assistente-whatsapp-estudo.md`.
 * ⚠️ O código em claro só vem na resposta de `gerarCodigoAssistente` — o estado nunca o traz.
 * ⚠️ Token e segredo da Meta nunca voltam do servidor; em branco ao salvar, mantém.
 */
import { api } from "@/lib/api";

export type NumeroDoAssistente = {
  numero: string;
  digitos: string;
  /** Só na resposta de `gerarCodigoAssistente`: o wa.me com o texto do código pronto. */
  link?: string;
};

export type VinculoAssistente = {
  vinculado: boolean;
  telefone: string | null;
  verificado_em: string | null;
  codigo_pendente: boolean;
  codigo_expira_em: string | null;
  /** Nulo enquanto o número da casa não estiver ligado. */
  assistente: NumeroDoAssistente | null;
};

export type CodigoAssistente = VinculoAssistente & {
  codigo: string;
  mensagem: string;
  assistente: NumeroDoAssistente & { link: string };
};

export type ConfigAssistente = {
  ativa: boolean;
  modo: "simulado" | "real";
  numero: string;
  phone_number_id: string;
  waba_id: string;
  api_versao: string;
  verify_token: string;
  webhook_url: string;
  token_configurado: boolean;
  segredo_configurado: boolean;
  ultimo_status: string | null;
  ultima_mensagem: string | null;
  /** 152: a conversa. Em branco = `modelo_padrao`. */
  modelo: string;
  modelo_padrao: string;
  limite_diario: number;
  /** A chave da Anthropic é a da Tradução: aqui só se diz se existe. */
  chave_anthropic: boolean;
  /** 153: o áudio. Provedor vazio = não ouve áudio. A chave nunca volta. */
  transcricao_provedor: "" | "openai" | "groq";
  transcricao_modelo: string;
  transcricao_chave_configurada: boolean;
  provedores_transcricao: { id: "openai" | "groq"; nome: string; modelo: string }[];
};

export type GravarConfigAssistente = {
  ativa: boolean;
  modo: "simulado" | "real";
  numero: string;
  phone_number_id: string;
  waba_id: string;
  api_versao: string;
  /** Em branco = mantém o que já está gravado. */
  token: string;
  app_secret: string;
  modelo: string;
  limite_diario: number;
  transcricao_provedor: "" | "openai" | "groq";
  transcricao_modelo: string;
  /** Em branco = mantém a guardada. */
  transcricao_chave: string;
};

export const vinculoAssistente = () => api.get<VinculoAssistente>("/assistente/vinculo");
export const gerarCodigoAssistente = () => api.post<CodigoAssistente>("/assistente/vinculo/codigo", {});
export const desvincularAssistente = () =>
  api.delete<VinculoAssistente & { message: string }>("/assistente/vinculo");

export const verConfigAssistente = () => api.get<ConfigAssistente>("/assistente/config");
export const salvarConfigAssistente = (c: GravarConfigAssistente) =>
  api.put<ConfigAssistente & { message: string }>("/assistente/config", c);
