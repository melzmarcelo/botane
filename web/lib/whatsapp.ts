/**
 * WhatsApp da loja (API oficial da Meta) — camada de service (regra da casa).
 *
 * 🔑 Pedido do dono (28/09/2026): configurável por loja, numa aba do cadastro da loja; a
 * loja faz a validação com a Meta e só informa os dados aqui. Regra em
 * `api/services/whatsapp.py`, estudo em `docs/whatsapp-estudo.md`.
 */
import { api } from "@/lib/api";

export type AvisoWhatsapp = {
  evento: string;
  nome: string;
  quando: string;
  texto: string;
  variaveis: string[];
  botoes?: string[];
  categoria: string;
  unidade?: string;
  ativo: boolean;
  modelo: string;
  idioma: string;
  antecedencia: number | null;
};

export type WhatsappDaLoja = {
  ativa: boolean;
  modo: "simulado" | "real";
  phone_number_id: string | null;
  waba_id: string | null;
  numero: string | null;
  api_versao: string;
  verify_token: string;
  webhook_url: string;
  token_configurado: boolean;
  segredo_configurado: boolean;
  ultimo_status: string | null;
  ultima_mensagem: string | null;
  avisos: AvisoWhatsapp[];
};

export type GravarWhatsapp = {
  ativa: boolean;
  modo: "simulado" | "real";
  phone_number_id: string | null;
  waba_id: string | null;
  numero: string | null;
  api_versao: string;
  /** Em branco = mantém o que já está gravado. */
  token: string;
  app_secret: string;
  avisos: {
    evento: string;
    ativo: boolean;
    modelo: string;
    idioma: string;
    antecedencia: number | null;
  }[];
};

export type MensagemWhatsapp = {
  id: number;
  evento: string;
  aviso: string;
  telefone: string;
  nome: string | null;
  texto: string | null;
  status: "FILA" | "ENVIADA" | "ENTREGUE" | "LIDA" | "RESPONDIDA" | "FALHOU" | "SIMULADA" | "CANCELADA";
  agendada_para: string;
  enviada_em: string | null;
  erro: string | null;
  tentativas: number;
  resposta: string | null;
  respondida_em: string | null;
  criada_em: string;
  id_reserva: number | null;
};

export const obterWhatsapp = (idLoja: number) =>
  api.get<WhatsappDaLoja>(`/unidades/${idLoja}/whatsapp`);

export const gravarWhatsapp = (idLoja: number, corpo: GravarWhatsapp) =>
  api.put<WhatsappDaLoja & { message: string }>(`/unidades/${idLoja}/whatsapp`, corpo);

export const testarWhatsapp = (idLoja: number, telefone: string, evento: string) =>
  api.post<{ message: string }>(`/unidades/${idLoja}/whatsapp/teste`, { telefone, evento });

export const mensagensWhatsapp = (
  idLoja: number,
  parametros: Record<string, string>,
  status: string,
) => {
  const q = new URLSearchParams(parametros);
  if (status) q.set("status", status);
  return api.listar<MensagemWhatsapp>(`/unidades/${idLoja}/whatsapp/mensagens?${q}`);
};
