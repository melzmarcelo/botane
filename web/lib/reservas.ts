/**
 * A agenda de reservas — o calendário do mês, o dia e a mudança de status.
 *
 * 🔑 **Camada de service, e não `api.get` solto na página** — regra da casa. A
 * tela da agenda nasceu chamando a API direto; o que entrou com a visão de
 * calendário (24/09/2026) já mora aqui, e as chamadas antigas vêm para cá à
 * medida que a tela for tocada.
 */
import { api } from "@/lib/api";

export type Reserva = {
  id: number;
  hora: string;
  sai_por_volta: string | null;
  pessoas: number;
  status: string;
  origem: string;
  nome: string;
  telefone: string | null;
  objetivo: string | null;
  observacao_cliente: string | null;
  observacao_interna: string | null;
  mesas: string;
};

export type Agenda = {
  data: string;
  reservas: Reserva[];
  esperados: number;
  ativas: number;
  aberta: boolean;
  bloqueio: string | null;
  lugares: number;
  /** A janela do dia, para a linha do tempo. Nulos com a casa fechada. */
  abre: string | null;
  fecha: string | null;
  ultima_reserva: string | null;
  passo: number;
  /** Horário próprio desta data (abre fora do padrão da semana). */
  especial: (Janela & { motivo: string | null }) | null;
  /** O período do bloqueio que cobre o dia — "fechado de 10 a 20". */
  bloqueio_de: string | null;
  bloqueio_ate: string | null;
  /** O padrão da semana para este dia, o que volta a valer sem exceção. */
  padrao: (Janela & { aberto: boolean }) | null;
};

export type Janela = { abre: string; fecha: string; ultima_reserva: string };

export type DiaDoCalendario = {
  data: string;
  /** O dia da semana está aberto na configuração. */
  aberta: boolean;
  /** Motivo do bloqueio pontual (feriado, evento), se houver. */
  bloqueio: string | null;
  /** Dia que abre fora do padrão, com o horário dele. */
  especial: { abre: string; fecha: string; motivo: string | null } | null;
  /** Só as VIVAS — cancelada não enche o dia. */
  reservas: number;
  pessoas: number;
  /** Aguardando a casa confirmar: o que a recepção ainda precisa resolver. */
  pendentes: number;
};

export type Calendario = { mes: string; dias: DiaDoCalendario[]; lugares: number };

/** Status que seguram mesa — espelha `VIVOS` no servidor. */
export const VIVOS = ["PENDENTE", "CONFIRMADA", "CHEGOU", "ENCERRADA"];

export const agendaDoDia = (dia: string) => api.get<Agenda>(`/reservas/agenda?data=${dia}`);

/** `mes` no formato AAAA-MM. */
export const calendario = (mes: string) =>
  api.get<Calendario>(`/reservas/calendario?mes=${mes}`);

export const mudarStatus = (id: number, status: string) =>
  api.put<{ message: string }>(`/reservas/${id}/status`, { status });

/** Um dia da semana na configuração — de onde a exceção copia o horário. */
export type DiaDaSemana = Janela & { dia_semana: number; nome: string; aberto: boolean };

export const semanaDaCasa = () =>
  api.get<{ horarios: DiaDaSemana[] }>("/reservas/configuracao").then((c) => c.horarios);

export type ModoDoDia = "PADRAO" | "ESPECIAL" | "FECHADO";

/** A exceção de uma data: volta ao padrão, abre com horário próprio ou fecha. */
export const definirDia = (
  dia: string,
  corpo: { modo: ModoDoDia; motivo?: string | null } & Partial<Janela>,
) => api.put<{ message: string; reservas_fora: number }>(`/reservas/dias/${dia}`, corpo);
