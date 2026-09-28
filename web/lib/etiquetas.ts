/**
 * Etiquetas de validade — camada de service (regra da casa).
 *
 * 🔑 Pedido do dono (28/09/2026): *"um novo módulo, o de Etiquetas … para controlar
 * validade, quantidade e demais coisas úteis, em produtos produzidos e abertos para
 * consumo."* Regra em `api/services/etiquetas.py`, estudo em `docs/etiquetas-estudo.md`.
 */
import { api } from "@/lib/api";

export type Evento = "PRODUCAO" | "ABERTURA" | "DESCONGELAMENTO";
export type Conservacao = "REFRIGERADO" | "CONGELADO" | "AMBIENTE";

export const EVENTOS: { v: Evento; r: string; verbo: string }[] = [
  { v: "PRODUCAO", r: "Produção", verbo: "Produzi" },
  { v: "ABERTURA", r: "Abertura", verbo: "Abri" },
  { v: "DESCONGELAMENTO", r: "Descongelamento", verbo: "Descongelei" },
];
export const CONSERVACOES: { v: Conservacao; r: string }[] = [
  { v: "REFRIGERADO", r: "Refrigerado" },
  { v: "CONGELADO", r: "Congelado" },
  { v: "AMBIENTE", r: "Ambiente" },
];
export const rotuloEvento = (e: Evento) => EVENTOS.find((x) => x.v === e)?.r ?? e;
export const rotuloConservacao = (c: Conservacao) => CONSERVACOES.find((x) => x.v === c)?.r ?? c;

export type Regra = {
  evento: Evento;
  conservacao: Conservacao;
  prazo: number;
  unidade: "HORAS" | "DIAS";
  padrao: boolean;
};

export type Situacao = "EM_DIA" | "HOJE" | "AMANHA" | "VENCIDA" | "USADA" | "DESCARTADA" | "SUBSTITUIDA";

export type Etiqueta = {
  id: number;
  codigo: string;
  id_unidade: number;
  id_produto: number;
  produto_codigo: string;
  produto: string;
  evento: Evento;
  conservacao: Conservacao;
  feito_em: string;
  vence_em: string;
  quantidade: string | null;
  um: string | null;
  id_producao: number | null;
  id_local: number | null;
  local: string | null;
  lote: string | null;
  validade_lote: string | null;
  validade_fabricante: string | null;
  id_origem: number | null;
  responsavel: string;
  observacao: string | null;
  status: "ATIVA" | "USADA" | "DESCARTADA" | "SUBSTITUIDA";
  baixada_em: string | null;
  baixada_por: string | null;
  motivo: string | null;
  id_movimento: number | null;
  impressoes: number;
  situacao: Situacao;
  alergenos?: string | null;
  pode_descartar?: boolean;
};

export type Sugestao = {
  produto: { id: number; codigo: string; nome: string; um_estoque: string | null };
  evento: Evento;
  conservacao: Conservacao;
  regras: Regra[];
  vence_em: string | null;
  origem: "regra" | "cadastro" | "fabricante" | "informada" | null;
  alergenos: string | null;
};

export type DaProducao = {
  id: number;
  id_produto: number;
  produto: string;
  um_estoque: string | null;
  quantidade: string;
  data: string;
  local: string | null;
  lote: string | null;
  validade_lote: string | null;
  etiquetas: number;
};

export type Emissao = {
  id_produto?: number | null;
  evento: Evento;
  conservacao?: Conservacao | null;
  copias: number;
  quantidade?: number | null;
  id_producao?: number | null;
  id_origem?: number | null;
  lote?: string | null;
  validade_fabricante?: string | null;
  vence_em?: string | null;
  responsavel?: string | null;
  observacao?: string | null;
};

export type ConfigEtiqueta = {
  tamanho: "40x40" | "50x30" | "60x40" | "100x50" | "A4";
  mostrar_alergenos: boolean;
  mostrar_lote: boolean;
  mostrar_quantidade: boolean;
  mostrar_qr: boolean;
  texto_extra: string | null;
};

export type PainelEtiquetas = {
  ativas: number;
  vencidas: number;
  hoje: number;
  amanha: number;
  descartadas_30d: number;
  valor_descartado_30d: number;
};

export type ProdutoComValidade = {
  id: number;
  codigo: string;
  nome: string;
  um_estoque: string | null;
  regras: Regra[];
};

export const sugestao = (idProduto: number, evento: Evento, conservacao?: Conservacao | null) => {
  const q = new URLSearchParams({ id_produto: String(idProduto), evento });
  if (conservacao) q.set("conservacao", conservacao);
  return api.get<Sugestao>(`/etiquetas/sugestao?${q}`);
};

export const daProducao = (id: number) => api.get<DaProducao>(`/etiquetas/producao/${id}`);

export const emitir = (corpo: Emissao) =>
  api.post<{ etiquetas: Etiqueta[]; ids: number[]; message: string }>("/etiquetas", corpo);

export const imprimir = (ids: number[], reimpressao = false) =>
  api.abrir(`/etiquetas/pdf?ids=${ids.join(",")}${reimpressao ? "&reimpressao=true" : ""}`);

export const painel = () => api.get<PainelEtiquetas>("/etiquetas/painel");

export const listar = (parametros: Record<string, string>, filtros: {
  situacao: string; busca: string; evento: string;
}) => {
  const q = new URLSearchParams(parametros);
  q.set("situacao", filtros.situacao || "ativas");
  if (filtros.busca) q.set("busca", filtros.busca);
  if (filtros.evento) q.set("evento", filtros.evento);
  return api.listar<Etiqueta>(`/etiquetas?${q}`);
};

export const porCodigo = (codigo: string) =>
  api.get<Etiqueta>(`/etiquetas/codigo/${encodeURIComponent(codigo.trim())}`);

export const usar = (id: number, observacao?: string) =>
  api.post<Etiqueta & { message: string }>(`/etiquetas/${id}/usar`, { observacao });

export const descartar = (id: number, corpo: {
  quantidade?: number | null; id_motivo_perda?: number | null; motivo?: string; lancar_perda: boolean;
}) => api.post<Etiqueta & { message: string }>(`/etiquetas/${id}/descartar`, corpo);

export const motivosDePerda = () => api.get<{ id: number; nome: string }[]>("/estoque/motivos-perda");

export const obterConfig = () => api.get<ConfigEtiqueta>("/etiquetas/configuracao");
export const salvarConfig = (c: ConfigEtiqueta) =>
  api.put<ConfigEtiqueta & { message: string }>("/etiquetas/configuracao", c);

export const validades = (idProduto: number) => api.get<Regra[]>(`/etiquetas/validades/${idProduto}`);
export const salvarValidades = (idProduto: number, regras: Regra[]) =>
  api.put<{ regras: Regra[]; message: string }>(`/etiquetas/validades/${idProduto}`, { regras });

export const produtosComValidade = (parametros: Record<string, string>, busca: string) => {
  const q = new URLSearchParams(parametros);
  if (busca) q.set("busca", busca);
  return api.listar<ProdutoComValidade>(`/etiquetas/produtos-com-validade?${q}`);
};

/** "01/10 13:58" — a validade como a etiqueta imprime. */
export const dataHora = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleString("pt-BR", {
        day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
      })
    : "—";

export const numero = (v: string | number | null) =>
  v === null || v === undefined ? "" : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 4 });

export const COR_SITUACAO: Record<Situacao, "erva" | "alerta" | "neutro"> = {
  EM_DIA: "erva", AMANHA: "neutro", HOJE: "alerta", VENCIDA: "alerta",
  USADA: "neutro", DESCARTADA: "neutro", SUBSTITUIDA: "neutro",
};
export const ROTULO_SITUACAO: Record<Situacao, string> = {
  EM_DIA: "em dia", AMANHA: "vence amanhã", HOJE: "vence hoje", VENCIDA: "vencida",
  USADA: "usada", DESCARTADA: "descartada", SUBSTITUIDA: "substituída",
};
