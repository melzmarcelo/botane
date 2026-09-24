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
  usado_em: string | null;
  loja: string | null;
  loja_uso: string | null;
  entregue_por: string | null;
  consumo: string;
  status: "DISPONIVEL" | "USADO" | "VENCIDO";
  /** Disponível e hoje é dia de consumo. */
  pode_hoje: boolean;
};

export type ImpressaoQr = {
  quantidade: number;
  tamanho: "P" | "M" | "G";
  titulo: string;
  chamada: string;
  extra: string;
  numerar: boolean;
  primeira_mesa: number;
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

export const salvarConfig = (c: Omit<FidelidadeConfig, "ligada" | "link">) =>
  api.put<FidelidadeConfig & { message: string }>("/fidelidade/configuracao", c);

export const trocarToken = () =>
  api.post<FidelidadeConfig & { message: string }>("/fidelidade/token");

export function baixarQrCodes(p: ImpressaoQr) {
  const q = new URLSearchParams({
    quantidade: String(p.quantidade),
    tamanho: p.tamanho,
    titulo: p.titulo,
    chamada: p.chamada,
    extra: p.extra,
    numerar: String(p.numerar),
    primeira_mesa: String(p.primeira_mesa),
  });
  return api.baixar(`/fidelidade/qrcodes.pdf?${q}`);
}

export const listarPremios = (
  parametros: Record<string, string>,
  filtros: { status: string; busca: string },
) => {
  const q = new URLSearchParams(parametros);
  if (filtros.status) q.set("status", filtros.status);
  if (filtros.busca.trim()) q.set("busca", filtros.busca.trim());
  return api.listar<Premio>(`/fidelidade/premios?${q}`);
};

export const entregarPremio = (codigo: string) =>
  api.post<{ message: string }>("/fidelidade/premios/entregar", { codigo });
