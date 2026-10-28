import { api } from "@/lib/api";
import { lembrarModo, palpiteDireta } from "@/lib/etiquetas";

/**
 * Patrimônio: os bens da casa, um registro por item físico, e a manutenção deles.
 * Ver `api/services/patrimonio.py` (migração 139, pedido do dono de 27/10/2026).
 */

export const SITUACOES: Record<string, string> = {
  A_CONFIRMAR: "A confirmar", EM_USO: "Em uso", EM_MANUTENCAO: "Em manutenção",
  PARADO: "Parado", DESATIVADO: "Desativado", BAIXADO: "Baixado",
};
export const CRITICIDADES: Record<string, string> = { ALTA: "Alta", MEDIA: "Média", BAIXA: "Baixa" };
export const TENSOES: Record<string, string> = {
  "110V": "110 V", "220V": "220 V", "380V": "380 V", GAS: "Gás", NA: "Não se aplica",
};
/** O status da preventiva, na ordem de urgência — calculado pelo servidor. */
export const PREVENTIVA: Record<string, string> = {
  VENCIDA: "Vencida", VENCE_30: "Vence em 30 dias", SEM_REGISTRO: "Sem a data da última",
  EM_DIA: "Em dia", SEM_PLANO: "Sem plano", FORA: "Fora de uso",
};
export const COR_PREVENTIVA: Record<string, "alerta" | "erva" | "neutro"> = {
  VENCIDA: "alerta", VENCE_30: "alerta", EM_DIA: "erva",
};

export type Bem = {
  id: number;
  codigo: string;
  apelido: string | null;
  id_unidade: number;
  descricao: string;
  id_produto: number | null;
  produto: string | null;
  id_setor: number | null;
  setor: string | null;
  id_local: number | null;
  local: string | null;
  marca: string | null;
  modelo: string | null;
  numero_serie: string | null;
  tensao: string | null;
  data_compra: string | null;
  valor_compra: number | string | null;
  fornecedor: string | null;
  nota_fiscal: string | null;
  garantia_ate: string | null;
  assistencia: string | null;
  assistencia_contato: string | null;
  criticidade: string | null;
  situacao: string;
  motivo_baixa: string | null;
  preventiva_meses: number | null;
  ultima_preventiva: string | null;
  observacao: string | null;
  /** A última conferência (fechada) em que o bem foi VISTO. */
  conferido_em: string | null;
  proxima_preventiva: string | null;
  status_preventiva: string;
  em_garantia: boolean;
  situacao_txt: string;
  criticidade_txt: string | null;
  preventiva_txt: string;
};

export type Manutencao = {
  id: number;
  tipo: "PREVENTIVA" | "CORRETIVA";
  tipo_txt: string;
  data: string;
  executado_por: string | null;
  custo: number | string | null;
  descricao: string | null;
  registrado_por: string | null;
};

export type BemDetalhe = Bem & {
  manutencoes: Manutencao[];
  custo_manutencao: number;
  /** O estoque guardado no local do bem (a câmara fria). Valor só para quem vê estoque. */
  estoque_no_local: { produtos: number; valor: number | null } | null;
};

export type ResumoSetor = {
  setor: string;
  id_setor: number | null;
  bens: number;
  criticidade_alta: number;
  parados: number;
  vencidas: number;
  vencendo: number;
  sem_plano: number;
  a_confirmar: number;
  valor_compra: number;
};
export type Resumo = { setores: ResumoSetor[]; total: Omit<ResumoSetor, "setor" | "id_setor"> };

export type Filtros = {
  busca: string;
  situacao: string[];
  preventiva: string[];
  criticidade: string[];
  setores: number[];
  id_produto?: number;
};

export function listar(parametros: Record<string, string>, f: Filtros) {
  const q = new URLSearchParams(parametros);
  if (f.busca) q.set("busca", f.busca);
  f.situacao.forEach((s) => q.append("situacao", s));
  f.preventiva.forEach((s) => q.append("preventiva", s));
  f.criticidade.forEach((s) => q.append("criticidade", s));
  f.setores.forEach((s) => q.append("setores", String(s)));
  if (f.id_produto) q.set("id_produto", String(f.id_produto));
  return api.listar<Bem>(`/patrimonio?${q}`);
}

export const resumo = () => api.get<Resumo>("/patrimonio/resumo");

/** O produto Patrimônio que entrou (tem saldo) e ainda não virou bem. */
export type ACadastrar = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  saldo: number;
  /** Onde está: "CAMARA FRIA (2), BAR (1)". */
  onde: string | null;
  bens: number;
  faltam: number;
};
export const aCadastrar = () => api.get<ACadastrar[]>("/patrimonio/a-cadastrar");

/** Os bens de um produto Patrimônio e a sugestão para o próximo (da última entrada). */
export type DoProduto = {
  produto: { id: number; codigo: string; nome: string; tipo: string; um_estoque: string | null };
  saldo: number;
  bens: Bem[];
  ativos: number;
  faltam: number;
  onde: string | null;
  sugestao: {
    descricao: string; id_produto: number; id_setor: number | null; id_local: number | null;
    data_compra?: string | null; fornecedor?: string | null; nota_fiscal?: string | null;
    valor_compra?: number | null;
  };
};
export const doProduto = (id: number) => api.get<DoProduto>(`/patrimonio/do-produto/${id}`);
export const obter = (id: number) => api.get<BemDetalhe>(`/patrimonio/${id}`);
export const porCodigo = (codigo: string) =>
  api.get<{ id: number; id_unidade: number; conferencia_aberta: number | null }>(
    `/patrimonio/codigo/${encodeURIComponent(codigo.trim())}`);

/** O corpo do cadastro: texto vazio vai como nulo. */
export type BemForm = Partial<Record<keyof Bem, string | number | null>>;
export const criar = (dados: BemForm) =>
  api.post<Bem & { message: string }>("/patrimonio", dados);
export const salvar = (id: number, dados: BemForm) =>
  api.put<Bem & { message: string }>(`/patrimonio/${id}`, dados);
export const apagar = (id: number) => api.delete<{ message: string }>(`/patrimonio/${id}`);

export const registrarManutencao = (id: number, dados: {
  tipo: string; data: string; executado_por?: string | null; custo?: number | null;
  descricao?: string | null; situacao_depois?: string | null;
}) => api.post<{ id: number; bem: Bem; message: string }>(`/patrimonio/${id}/manutencoes`, dados);
export const apagarManutencao = (id: number) =>
  api.delete<{ message: string }>(`/patrimonio/manutencoes/${id}`);

/** As plaquetas: o mesmo rolo e a mesma impressora das etiquetas de validade. */
export async function imprimirPlaquetas(ids: number[]): Promise<void> {
  const modo = await api.imprimir(`/patrimonio/plaquetas.pdf?ids=${ids.join(",")}`, palpiteDireta());
  lembrarModo(modo === "direta");
}

export type ResultadoImportacao = {
  novos: { aba: string; linha: number; descricao: string; apelido: string | null;
           codigo?: string; campos: Record<string, string | null> }[];
  mudam: { aba: string; linha: number; descricao: string; id: number; codigo: string;
           de: Record<string, string | null>; para: Record<string, string | null> }[];
  iguais: number;
  recusados: { aba: string; linha: number; descricao: string; motivo: string }[];
  sugestoes: number;
  linhas: number;
  aplicado: boolean;
  message: string;
};

export function importar(arquivo: File, simular: boolean, incluirSugestoes: boolean) {
  const f = new FormData();
  f.append("arquivo", arquivo);
  return api.upload<ResultadoImportacao>(
    `/patrimonio/importar?simular=${simular}&incluir_sugestoes=${incluirSugestoes}`, f);
}

/** "2026-10-27" → "27/10/2026". */
export const dataBr = (iso: string | null | undefined) =>
  iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—";

// ---------------------------------------------------------------- conferência (140)

/** Uma conferência na lista: quantos esperados, lidos, faltam e achados de outro setor. */
export type ConferenciaResumo = {
  id: number;
  id_setor: number | null;
  setor: string | null;
  escopo: string;
  status: "ABERTA" | "FECHADA" | "CANCELADA";
  status_txt: string;
  aberta_em: string;
  fechada_em: string | null;
  aberta_por_nome: string | null;
  esperados: number;
  lidos: number;
  faltam: number;
  de_fora: number;
};

export type ItemConferencia = {
  id: number;
  id_bem: number;
  esperado: boolean;
  lido_em: string | null;
  lido_por_nome: string | null;
  resultado: string | null;
  resultado_txt: string | null;
  situacao_antes: string;
  situacao_antes_txt: string;
  setor_antes: string | null;
  codigo: string;
  apelido: string | null;
  descricao: string;
  situacao: string;
  situacao_txt: string;
  criticidade: string | null;
  setor: string | null;
  local: string | null;
};

export type Conferencia = ConferenciaResumo & {
  observacao: string | null;
  fechada_por_nome: string | null;
  itens: ItemConferencia[];
  message?: string;
};

export type Leitura = {
  bem: { id: number; codigo: string; descricao: string };
  id_item: number;
  novo: boolean;
  ja_lido: boolean;
  de_fora: boolean;
  message: string;
  contagem: { esperados: number; lidos: number; faltam: number; de_fora: number };
};

export const conferencias = () => api.get<ConferenciaResumo[]>("/patrimonio/conferencias");
export const conferencia = (id: number) => api.get<Conferencia>(`/patrimonio/conferencias/${id}`);
export const abrirConferencia = (id_setor: number | null, observacao: string | null) =>
  api.post<Conferencia & { message: string }>("/patrimonio/conferencias", { id_setor, observacao });
export const lerPlaqueta = (id: number, texto: string) =>
  api.post<Leitura>(`/patrimonio/conferencias/${id}/leituras`, { texto });
export const desfazerLeitura = (id: number, idItem: number) =>
  api.delete<Conferencia & { message: string }>(`/patrimonio/conferencias/${id}/leituras/${idItem}`);
export const fecharConferencia = (id: number, corpo: {
  baixar: number[]; motivo_baixa: string | null; transferir: boolean; confirmar: boolean;
}) => api.post<Conferencia & { message: string }>(`/patrimonio/conferencias/${id}/fechar`, corpo);
export const cancelarConferencia = (id: number) =>
  api.post<Conferencia & { message: string }>(`/patrimonio/conferencias/${id}/cancelar`, {});

/**
 * 🔑 **"Este aparelho está conferindo"** — a câmera comum do celular abre a plaqueta em
 * `/patrimonio/b/…`, e é por esta marca que aquela tela conta a leitura em vez de abrir a
 * ficha. É conveniência DO APARELHO (quem abriu a conferência nele), por isso
 * `localStorage`: em outro celular a plaqueta continua abrindo a ficha.
 */
const CHAVE_CONFERINDO = "botane.patrimonio.conferindo";
export function marcarConferindo(id: number | null) {
  try {
    if (id) localStorage.setItem(CHAVE_CONFERINDO, String(id));
    else localStorage.removeItem(CHAVE_CONFERINDO);
  } catch { /* sem armazenamento: a plaqueta só abre a ficha */ }
}
export function conferindoAqui(): number | null {
  try {
    const v = Number(localStorage.getItem(CHAVE_CONFERINDO));
    return Number.isFinite(v) && v > 0 ? v : null;
  } catch {
    return null;
  }
}
