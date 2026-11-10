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
/** 156 — a situação da garantia, calculada pelo servidor (`garantia_ate` contra hoje). */
export const COR_GARANTIA: Record<string, "alerta" | "erva" | "neutro"> = {
  ATIVA: "erva", VENCE_30: "alerta", FORA: "neutro", SEM: "neutro",
};
/** 157 — de quem é a garantia. */
export const GARANTIA_TIPOS: Record<string, string> = { FABRICA: "Fábrica", ESTENDIDA: "Estendida", LOJA: "Loja" };
/** A periodicidade da preventiva pelo nome; o resto é "a cada N meses". */
export const PERIODICIDADES: Record<string, string> = {
  "1": "Mensal", "2": "Bimestral", "3": "Trimestral", "6": "Semestral", "12": "Anual",
};
export const periodicidade = (meses: number | null) =>
  !meses ? "Sem plano" : PERIODICIDADES[String(meses)] ?? `A cada ${meses} meses`;

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
  /** 141 — em anos; vazia = o padrão (10). */
  vida_util_anos: number | null;
  /** 141 — quando saiu da casa (o banco põe hoje se a baixa vier sem data). */
  data_baixa: string | null;
  /** 157 — quem responde pelo bem (texto livre). */
  responsavel: string | null;
  /** 157 — o prazo em meses e o tipo; a data final sai da compra + meses. */
  garantia_meses: number | null;
  garantia_tipo: string | null;
  garantia_tipo_txt: string | null;
  /** 157 — os itens a verificar em cada preventiva. */
  preventiva_checklist: string[];
  proxima_preventiva: string | null;
  status_preventiva: string;
  em_garantia: boolean;
  /** 156 — ATIVA, VENCE_30, FORA ou SEM. */
  status_garantia: string;
  garantia_txt: string;
  /** Dias até o fim da garantia (negativo = já venceu). */
  garantia_dias: number | null;
  /** Dias até a próxima preventiva (negativo = atrasada). */
  preventiva_dias: number | null;
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
  /** 156 — o que gerou a visita e se a garantia cobriu. */
  causa: string | null;
  coberta_garantia: boolean;
  registrado_por: string | null;
  /** 157 — a nota da visita e o checklist como foi marcado ("4 de 5 itens"). */
  nota_fiscal: string | null;
  checklist: { item: string; feito: boolean }[] | null;
  checklist_txt: string | null;
};

/** 157 — uma foto ou um documento (PDF) do bem, guardado no banco. */
export type Anexo = {
  id: number;
  tipo: "FOTO" | "DOCUMENTO";
  nome: string;
  url: string;
  bytes: number;
  criado_em: string;
  enviado_por: string | null;
};

/** 156 — a aba Custos, calculada pelo servidor das manutenções. */
export type CustosDoBem = {
  compra: number | null;
  preventivas: number;
  corretivas: number;
  manutencao: number;
  total: number;
  /** Quanto a manutenção já representa sobre a compra (nula sem valor de compra). */
  manutencao_pct: number | null;
  extrato: { chave: string; data: string | null; o_que: string; detalhe: string | null; garantia?: boolean;
             valor: number | null; saldo: number }[];
};

export type BemDetalhe = Bem & {
  manutencoes: Manutencao[];
  anexos: Anexo[];
  custo_manutencao: number;
  /** O estoque guardado no local do bem (a câmara fria). Valor só para quem vê estoque. */
  estoque_no_local: { produtos: number; valor: number | null } | null;
  /** 141 — a depreciação até hoje (ou até a baixa), a mesma conta do relatório do valor. */
  valor: Depreciacao;
  custos: CustosDoBem;
  /** As próximas visitas da preventiva (a próxima e as seguintes). */
  agenda_preventiva: string[];
  manutencoes_recentes: number;
  recente_dias: number;
  /** A prévia da plaqueta: o QR (linhas de 0 e 1) e o tamanho do rolo configurado. */
  plaqueta: { link: string; qr: string[]; largura_mm: number; altura_mm: number };
};

/** A conta da depreciação de um bem (linear, por mês inteiro) — feita pelo servidor. */
export type Depreciacao = {
  vida_util: number;
  vida_padrao: boolean;
  sem_valor: boolean;
  sem_data: boolean;
  meses: number | null;
  quota_mensal: number | null;
  depreciacao: number | null;
  valor_atual: number | null;
  depreciado_pct: number | null;
  depreciado_total: boolean;
  fim_vida: string | null;
};

export type BemValor = Depreciacao & {
  id: number; codigo: string; apelido: string | null; descricao: string;
  situacao: string; situacao_txt: string; id_setor: number | null; setor: string | null;
  local: string | null; data_compra: string | null; valor_compra: number | null;
  vida_util_anos: number | null; data_baixa: string | null;
};
export type SomaValor = {
  bens: number; sem_valor: number; sem_data: number; depreciados: number;
  valor_compra: number; depreciacao: number; valor_atual: number;
};
export type ValorPatrimonio = {
  data: string;
  vida_util_padrao: number;
  setores: (SomaValor & { setor: string; id_setor: number | null })[];
  total: SomaValor;
  bens: BemValor[];
};

/** 141 — o valor do patrimônio numa data (hoje, sem data). */
export function valorDoPatrimonio(data: string, setores: number[]) {
  const q = new URLSearchParams();
  if (data) q.set("data", data);
  setores.forEach((s) => q.append("setores", String(s)));
  return api.get<ValorPatrimonio>(`/patrimonio/valor?${q}`);
}

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
export type BemForm = Partial<Record<keyof Bem, string | number | string[] | null>>;
export const criar = (dados: BemForm) =>
  api.post<Bem & { message: string }>("/patrimonio", dados);
export const salvar = (id: number, dados: BemForm) =>
  api.put<Bem & { message: string }>(`/patrimonio/${id}`, dados);
export const apagar = (id: number) => api.delete<{ message: string }>(`/patrimonio/${id}`);

export const registrarManutencao = (id: number, dados: {
  tipo: string; data: string; executado_por?: string | null; custo?: number | null;
  descricao?: string | null; situacao_depois?: string | null;
  causa?: string | null; coberta_garantia?: boolean;
  nota_fiscal?: string | null; checklist?: { item: string; feito: boolean }[] | null;
}) => api.post<{ id: number; bem: Bem; message: string }>(`/patrimonio/${id}/manutencoes`, dados);
export const apagarManutencao = (id: number) =>
  api.delete<{ message: string }>(`/patrimonio/manutencoes/${id}`);

/** 157 — anexa uma foto (PNG, JPG, WEBP até 2 MB) ou um PDF (até 10 MB). */
export function anexar(id: number, arquivo: File) {
  const f = new FormData();
  f.append("arquivo", arquivo);
  return api.upload<Anexo & { message: string }>(`/patrimonio/${id}/anexos`, f);
}
export const apagarAnexo = (id: number) => api.delete<{ message: string }>(`/patrimonio/anexos/${id}`);

/** 157 — a situação no Omie de cada lançamento de custo (só leitura, consultada na hora). */
export type LinhaOmie = {
  chave: string;
  o_que: string;
  data: string | null;
  valor: number | null;
  nota_fiscal: string | null;
  fornecedor: string | null;
  codigo_omie: string | null;
  situacao: "PAGO" | "ABERTO" | "ATRASADO" | "CANCELADO" | "NAO_ACHADO" | "SEM_FORNECEDOR" | "SEM_NOTA";
  situacao_txt: string;
  detalhe: string | null;
  parcelas?: number;
  pagas?: number;
  valor_omie?: number;
  proximo_vencimento?: string | null;
};
export type SituacaoOmie = {
  codigo: string; modo: "real" | "simulado"; linhas: LinhaOmie[];
  pagos: number; em_aberto: number; atrasados: number;
};
export const situacaoNoOmie = (id: number) => api.get<SituacaoOmie>(`/patrimonio/${id}/omie`);

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
