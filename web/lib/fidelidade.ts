/**
 * A fidelidade do Portal de Clientes — o cartão de visitas com check-in por QR.
 *
 * 🔑 Camada de service (regra da casa): as telas de Fidelidade não chamam `api`
 * direto. A regra mora em `api/services/fidelidade.py`.
 */
import { api } from "@/lib/api";

export type FidelidadeConfig = {
  visitas: number;
  premio: string;
  validade_dias: number;
  /** ISO: 1 = segunda … 7 = domingo. */
  dias_pontua: number[];
  dias_consumo: number[];
  so_no_horario: boolean;
  site_url: string;
  /** Como a visita se confirma (097): QR na mesa, ou código que o caixa passa. */
  metodo: "QRCODE_MESA" | "CODIGO_CAIXA";
  /** Por quantos minutos o código do caixa vale. */
  codigo_validade_min: number;
  /** O check-in só conta perto da loja (092). */
  exige_local: boolean;
  raio_m: number;
  /** As coordenadas da loja ATUAL; nulas = ainda não configuradas. */
  local: { latitude: number; longitude: number } | null;
  /** A loja ATUAL participa (Portal de Clientes → Configuração). */
  ligada: boolean;
  /** O que o QR desta loja abre. */
  link: string;
};

export type Premio = {
  id: number;
  codigo: string;
  premio: string;
  visitas: number;
  nome: string;
  telefone: string;
  emitido_em: string;
  vence_em: string;
  /** Vale da próxima visita em diante (093): o dia seguinte ao do 10º check-in. */
  vale_de: string;
  usado_em: string | null;
  loja: string | null;
  loja_uso: string | null;
  entregue_por: string | null;
  consumo: string;
  status: "DISPONIVEL" | "USADO" | "VENCIDO";
  /** Disponível, já valendo (`vale_de`) e hoje é dia de consumo. */
  pode_hoje: boolean;
};


export const DIAS = [
  { v: 1, r: "Seg" },
  { v: 2, r: "Ter" },
  { v: 3, r: "Qua" },
  { v: 4, r: "Qui" },
  { v: 5, r: "Sex" },
  { v: 6, r: "Sáb" },
  { v: 7, r: "Dom" },
];

export const obterConfig = () => api.get<FidelidadeConfig>("/fidelidade/configuracao");

export const salvarConfig = (c: Omit<FidelidadeConfig, "ligada" | "link" | "local">) =>
  api.put<FidelidadeConfig & { message: string }>("/fidelidade/configuracao", c);

export const definirLocal = (latitude: number, longitude: number) =>
  api.put<FidelidadeConfig & { message: string }>("/fidelidade/localizacao", {
    latitude,
    longitude,
  });

export const trocarToken = () =>
  api.post<FidelidadeConfig & { message: string }>("/fidelidade/token");


export const listarPremios = (
  parametros: Record<string, string>,
  filtros: { status: string; busca: string },
) => {
  const q = new URLSearchParams(parametros);
  if (filtros.status) q.set("status", filtros.status);
  if (filtros.busca.trim()) q.set("busca", filtros.busca.trim());
  return api.listar<Premio>(`/fidelidade/premios?${q}`);
};

/** Um pedido de código no caixa (097): o código só existe nesta tela. */
export type PedidoDeCodigo = {
  id: number;
  codigo: string;
  selos: number;
  status: "PENDENTE" | "CONFIRMADA";
  criada_em: string;
  expira_em: string;
  confirmada_em: string | null;
  tentativas: number;
  nome: string;
  telefone: string;
};

export type CodigosDoCaixa = {
  pendentes: PedidoDeCodigo[];
  confirmados: PedidoDeCodigo[];
  metodo: FidelidadeConfig["metodo"];
  ligada: boolean;
};

export const codigosDoCaixa = () => api.get<CodigosDoCaixa>("/fidelidade/codigos");

export const selosDoPedido = (id: number, selos: number) =>
  api.put<{ message: string }>(`/fidelidade/codigos/${id}`, { selos });

export const cancelarPedido = (id: number) =>
  api.delete<{ message: string }>(`/fidelidade/codigos/${id}`);

export const entregarPremio = (codigo: string) =>
  api.post<{ message: string }>("/fidelidade/premios/entregar", { codigo });

// ---------------------------------------------------------------- o painel (098)

export type ResumoFidelidade = {
  participantes: number;
  selos_abertos: number;
  premios_disponiveis: number;
  vencendo_7_dias: number;
  premios_vencidos: number;
  entregues_no_mes: number;
  visitas_hoje: number;
  visitas_por_premio: number;
  premio: string;
  metodo: FidelidadeConfig["metodo"];
};

export type Participante = {
  id: number;
  nome: string;
  telefone: string;
  no_cartao: number;
  visitas: number;
  ultima_visita: string | null;
  disponiveis: number;
  vencidos: number;
  usados: number;
  proximo_vencimento: string | null;
};

export type LancamentoDeSelos = {
  id: number;
  data: string;
  parte: number;
  selos: number;
  origem: "VISITA" | "QRCODE" | "CODIGO" | "MANUAL";
  motivo: string | null;
  distancia_m: number | null;
  criado_em: string | null;
  id_premio: number | null;
  premio_codigo: string | null;
  loja: string | null;
  concedido_por: string | null;
};

export type PremioDaFicha = Premio & { vale_de: string; vencimento_original: string | null };

export type FichaFidelidade = {
  cliente: { id: number; nome: string; telefone: string };
  cartao: {
    visitas: number;
    premio: string;
    no_cartao: number;
    faltam: number;
    pontua: string;
    consumo: string;
    validade_dias: number;
  };
  visitas: LancamentoDeSelos[];
  premios: PremioDaFicha[];
  pedidos: {
    id: number;
    status: string;
    selos: number;
    criada_em: string;
    confirmada_em: string | null;
    tentativas: number;
    loja: string | null;
  }[];
};

export const resumoFidelidade = () =>
  api.get<ResumoFidelidade>("/fidelidade/painel/resumo");

export const listarParticipantes = (
  parametros: Record<string, string>,
  filtros: { busca: string; filtro: string },
) => {
  const q = new URLSearchParams(parametros);
  if (filtros.busca.trim()) q.set("busca", filtros.busca.trim());
  if (filtros.filtro) q.set("filtro", filtros.filtro);
  return api.listar<Participante>(`/fidelidade/participantes?${q}`);
};

export const fichaFidelidade = (idCliente: number) =>
  api.get<FichaFidelidade>(`/fidelidade/participantes/${idCliente}`);

export const darSelos = (idCliente: number, selos: number, motivo: string) =>
  api.post<FichaFidelidade & { message: string }>(
    `/fidelidade/participantes/${idCliente}/selos`, { selos, motivo });

export const retirarSelos = (idLancamento: number) =>
  api.delete<FichaFidelidade & { message: string }>(`/fidelidade/selos/${idLancamento}`);

export const ajustarVencimento = (idPremio: number, venceEm: string) =>
  api.put<{ message: string }>(`/fidelidade/premios/${idPremio}/vencimento`, {
    vence_em: venceEm,
  });
