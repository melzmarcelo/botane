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
  /** O que o cliente respondeu ao lembrete do WhatsApp (099). */
  presenca?: "CONFIRMADA" | "CANCELOU" | null;
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

/** Um cliente cadastrado pelo site (a rede inteira — o cadastro é único). */
export type Cliente = {
  id: number;
  nome: string;
  telefone: string;
  genero: string | null;
  cidade: string | null;
  nascimento: string | null;
  criado_em: string;
  /** Onde se cadastrou. */
  loja: string | null;
  /** Reservas que valeram (sem canceladas e não-comparecimentos). */
  reservas: number;
  canceladas: number;
  ultima: string | null;
  termo_aceito_em: string | null;
  termo_versao: string | null;
  /** Visitas no cartão de fidelidade atual (091) e prêmios já ganhos. */
  no_cartao: number;
  premios: number;
};

/** `parametros` vem de `usePaginacao` (limite, offset e o pedido de total). */
export const listarClientes = (parametros: Record<string, string>, busca: string) => {
  const q = new URLSearchParams(parametros);
  if (busca.trim()) q.set("busca", busca.trim());
  return api.listar<Cliente>(`/reservas/clientes?${q}`);
};

// ── Plano de ação (30/10/2026) ───────────────────────────────────────────────

/** Uma pessoa a chamar de volta. A pessoa é o TELEFONE (balcão e site juntos). */
export type PessoaDoPlano = {
  telefone: string;
  nome: string | null;
  /** O cadastro do site, quando há. */
  id_cliente: number | null;
  /** Reservas que contaram como visita (sem canceladas e faltas). */
  reservas: number;
  /** Delas, quantas foram grupo grande. */
  grupos: number;
  pessoas: number;
  maior_grupo: number;
  faltas: number;
  /** Última visita (AAAA-MM-DD) e há quantos dias. */
  ultima: string;
  dias: number;
  /** Respondeu "PARAR" ao WhatsApp da casa: não se manda mensagem. */
  nao_quer_whatsapp: boolean;
};

export type CriteriosDoPlano = {
  vip_reservas: number;
  vip_dias: number;
  grupo_pessoas: number;
  grupo_reservas: number;
  grupo_dias: number;
  adormecido_max: number;
  adormecido_dias: number;
};

export type ListaDoPlano = "vips" | "organizadores" | "adormecidos";

export type PlanoDeAcao = {
  loja: string | null;
  criterios: CriteriosDoPlano;
  resumo: { total: number } & Record<ListaDoPlano, number>;
} & Record<ListaDoPlano, PessoaDoPlano[]>;

/** Critério que não vem fica no padrão do servidor. */
export const verPlanoDeAcao = (criterios: Partial<CriteriosDoPlano> = {}) => {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(criterios)) if (v) q.set(k, String(v));
  return api.get<PlanoDeAcao>(`/reservas/plano-de-acao${q.size ? `?${q}` : ""}`);
};

// ── Painel das reservas (30/10/2026) ─────────────────────────────────────────

/** Uma fatia do painel: reservas válidas, pessoas que passaram e faltas. */
export type ContaDoPainel = { reservas: number; pessoas: number; faltas: number };

export type PainelReservas = {
  de: string;
  ate: string;
  meses: number;
  grupo_pessoas: number;
  resumo: ContaDoPainel & { clientes: number; canceladas: number };
  grupos: { reservas: number; pessoas: number; maior: number; faltas: number };
  por_dia_semana: (ContaDoPainel & { dia: number; nome: string })[];
  /** Todos os meses do período, com zero onde não houve reserva. */
  por_mes: (ContaDoPainel & { mes: string; parcial: boolean; grupos: number; grupos_pessoas: number })[];
  por_objetivo: (ContaDoPainel & { objetivo: string })[];
  por_hora: (ContaDoPainel & { hora: number })[];
};

export const verPainelReservas = (meses: number, grupoPessoas = 6) =>
  api.get<PainelReservas>(`/reservas/painel?meses=${meses}&grupo_pessoas=${grupoPessoas}`);

// ── Importação do LeadsFood (30/10/2026) ─────────────────────────────────────

export type ArquivoLeadsfood = "contatos" | "reservas" | "selos" | "premios";

export type ResultadoLeadsfood = {
  clientes: { novos: number; completados: number; iguais: number };
  reservas?: { novas: number; atualizadas: number; iguais: number };
  selos?: { clientes: number; selos: number; dias: number; ja_tinham: number; retirados: number; conflitos: number };
  premios?: { novos: number; atualizados: number; iguais: number; abertos: number };
  recusados: { arquivo: ArquivoLeadsfood; linha: number; nome: string | null; motivo: string }[];
  linhas: Partial<Record<ArquivoLeadsfood, number>>;
  aplicado: boolean;
};

/** Qualquer combinação dos quatro arquivos. `simular` (o padrão do servidor) não grava nada. */
export function importarLeadsfood(arquivos: Partial<Record<ArquivoLeadsfood, File>>, simular: boolean) {
  const f = new FormData();
  for (const [k, v] of Object.entries(arquivos)) if (v) f.append(k, v);
  return api.upload<ResultadoLeadsfood>(`/reservas/importar-leadsfood?simular=${simular}`, f);
}
