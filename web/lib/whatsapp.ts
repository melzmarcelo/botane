/**
 * WhatsApp da loja (API oficial da Meta) — camada de service (regra da casa).
 *
 * 🔑 Pedido do dono (28/09/2026): configurável por loja, numa aba do cadastro da loja; a
 * loja faz a validação com a Meta e só informa os dados aqui. Desde a 146 (30/10/2026) a
 * conexão é de cada NÚMERO da loja, e cada aviso diz por qual número sai. Regra em
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

/** Um número da loja e a conexão dele com a Meta (146). */
export type NumeroDoWhatsapp = {
  id: number;
  rotulo: string;
  numero: string;
  principal: boolean;
  conectado: boolean;
  modo: "simulado" | "real";
  phone_number_id: string | null;
  waba_id: string | null;
  api_versao: string;
  verify_token: string;
  conta_do_principal: boolean;
  token_configurado: boolean;
  segredo_configurado: boolean;
  ultimo_status: string | null;
  ultima_mensagem: string | null;
};

export type WhatsappDaLoja = {
  webhook_url: string;
  numeros: NumeroDoWhatsapp[];
  avisos: (AvisoWhatsapp & { id_whatsapp: number | null })[];
};

/** O número como a tela o edita. `chave`: o id, ou "novo-N" antes de gravar (é por ela que
 * um aviso aponta para um número que ainda não tem id). */
export type NumeroEmEdicao = {
  id: number | null;
  chave: string;
  rotulo: string;
  numero: string;
  principal: boolean;
  conectado: boolean;
  modo: "simulado" | "real";
  phone_number_id: string;
  waba_id: string;
  api_versao: string;
  /** Em branco = mantém o que já está gravado. */
  token: string;
  app_secret: string;
  conta_do_principal: boolean;
};

export type GravarWhatsapp = {
  numeros: NumeroEmEdicao[];
  avisos: {
    evento: string;
    ativo: boolean;
    modelo: string;
    idioma: string;
    antecedencia: number | null;
    /** A `chave` do número por onde sai; nulo = o principal. */
    whatsapp: string | null;
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
  id_whatsapp: number | null;
  whatsapp_rotulo: string | null;
  whatsapp_numero: string | null;
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
