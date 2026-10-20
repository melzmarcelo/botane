/**
 * Os anúncios do Cardápio Vivo (121, fase 1) — camada de service.
 *
 * 🔑 Pedido do dono (16/10/2026): anúncios da casa ou de outra marca no meio do cardápio, com
 * período, dias e links; regras de exibição ajustáveis; métricas e um RELATÓRIO para apresentar.
 */

import { api } from "@/lib/api";

export type OrigemAnuncio = "CASA" | "EXTERNO";
export type AcaoAnuncio = "NENHUMA" | "CATALOGO" | "PRATO" | "LINK";
export type CanalAnuncio = "AMBOS" | "MESA" | "LINK";
/** `COM_PROBLEMA` = ligado e no período, mas com destino quebrado ou sem onde aparecer (`avisos`). */
export type SituacaoAnuncio = "NO_AR" | "AGENDADO" | "ENCERRADO" | "DESLIGADO" | "COM_PROBLEMA";

export type Anuncio = {
  id: number;
  nome: string;
  origem: OrigemAnuncio;
  anunciante: string | null;
  titulo: string | null;
  texto: string | null;
  foto_url: string | null;
  video_url: string | null;
  video_capa_url: string | null;
  video_segundos: number | null;
  acao: AcaoAnuncio;
  acao_catalogo: number | null;
  acao_item: number | null;
  acao_url: string | null;
  acao_rotulo: string | null;
  inicio: string | null;
  fim: string | null;
  dias: number[] | null;
  hora_de: string | null;
  hora_ate: string | null;
  horario_especial: boolean;
  cardapios: number[] | null;
  canal: CanalAnuncio;
  peso: number;
  ativo: boolean;
  /** 125: as seções em que combina (nulo = todas) — ali ele pesa o triplo no sorteio. */
  secoes: number[] | null;
  /** 125: quantas variações do texto estão em teste (na lista). */
  variantes?: number;
  // Os últimos 30 dias (na lista).
  aparicoes?: number;
  sessoes?: number;
  segundos?: number | null;
  pulados?: number;
  toques?: number;
  sessoes_tocaram?: number;
  situacao?: SituacaoAnuncio;
  /** Por que não aparece, ou aparece pela metade (na lista). */
  avisos?: string[];
  /** No ar, mas fora do dia ou do horário neste momento. */
  fora_do_horario_agora?: boolean;
};

export type RegrasAnuncio = {
  anuncio_depois_de: number;
  anuncio_intervalo: number;
  anuncio_maximo: number;
  anuncio_maximo_mesa: number;
  /** 125: % das visitas que não vê anúncio nenhum (o grupo de controle). 0 desliga. */
  anuncio_controle: number;
  /** 125: o ritmo que aprende — pulou dobra a distância; dois sem toque, acabou na visita. */
  anuncio_recuo: boolean;
};

/** 125: uma variação do TEXTO do anúncio (a mídia e o destino são os do anúncio). */
export type Variante = { id: number; id_anuncio: number; titulo: string | null; texto: string | null;
                         acao_rotulo: string | null; ativo: boolean };
export type GravarVariante = Pick<Variante, "titulo" | "texto" | "acao_rotulo" | "ativo">;

type Conclusao = "AMOSTRA_PEQUENA" | "SEM_DIFERENCA" | "A_VENCE" | "B_VENCE";
export type LinhaDaVariante = {
  id_variante: number | null; rotulo: string; titulo: string | null; texto: string | null;
  sessoes: number; tocaram: number; taxa: number | null;
  comparacao: { p_valor: number | null; conclusao: Conclusao } | null;
  /** Falso = a variação já foi apagada ou aplicada; os números ficam. */
  existe: boolean;
};
export type VariantesDoRelatorio = {
  linhas: LinhaDaVariante[];
  vencedora: number | null;
  conclusao: "VARIACAO_VENCE" | "ORIGINAL_VENCE" | "AMOSTRA_PEQUENA" | "SEM_DIFERENCA";
  minimo_por_braco: number;
  em_teste: boolean;
};

type Grupo = { sessoes: number; engajadas: number; adicionaram: number; pratos_por_sessao: number | null };
/** 125: o grupo de controle (sem anúncio) × as expostas. Na ordem (controle, expostas): B = expostas. */
export type Efeito = {
  de: string; ate: string; controle: Grupo; expostas: Grupo; minimo_por_braco: number; percentual: number;
  adicao: { p_valor: number | null; conclusao: Conclusao };
  engajamento: { p_valor: number | null; conclusao: Conclusao };
};

export type GravarAnuncio = Omit<Anuncio, "id" | "foto_url" | "video_url" | "video_capa_url" | "video_segundos"
  | "aparicoes" | "sessoes" | "segundos" | "pulados" | "toques" | "sessoes_tocaram" | "situacao" | "avisos"
  | "fora_do_horario_agora" | "variantes">;

type Metricas = { aparicoes: number; sessoes: number; segundos: number | null; pulados: number; toques: number;
                  sessoes_tocaram: number };

export type Relatorio = {
  anuncio: Anuncio;
  de: string;
  ate: string;
  casa: string | null;
  total: Metricas & { taxa_toque: number | null; taxa_pulou: number | null };
  por_dia: (Metricas & { dia: string })[];
  por_canal: (Metricas & { canal: "MESA" | "LINK" })[];
  /** Em qual Cardápio Vivo (122). `cardapio` nulo = medido antes da 122, ou catálogo apagado. */
  por_cardapio: (Metricas & { id_catalogo: number | null; cardapio: string | null })[];
  por_hora: { hora: number; aparicoes: number }[];
  pulou_ms: number;
  /** 124: os dias que o bruto já não tinha vieram do resumo diário — e a frase que o diz. */
  resumido: { ate: string; dias: number; aviso: string } | null;
  /** 125: os números de cada texto, e a vencedora. Nulo = o anúncio nunca teve variação. */
  variantes: VariantesDoRelatorio | null;
};

const arquivo = (a: File) => {
  const f = new FormData();
  f.append("arquivo", a);
  return f;
};

export const AnunciosService = {
  listar: () => api.get<{ anuncios: Anuncio[]; regras: RegrasAnuncio; pulou_ms: number }>("/cardapio-vivo/anuncios"),
  criar: (corpo: GravarAnuncio) => api.post<Anuncio>("/cardapio-vivo/anuncios", corpo),
  atualizar: (id: number, corpo: GravarAnuncio) => api.put<Anuncio>(`/cardapio-vivo/anuncios/${id}`, corpo),
  remover: (id: number) => api.delete<{ message: string }>(`/cardapio-vivo/anuncios/${id}`),
  regras: (corpo: RegrasAnuncio) => api.put<RegrasAnuncio & { message: string }>("/cardapio-vivo/anuncios/regras", corpo),
  enviarFoto: (id: number, a: File) => api.upload<Anuncio>(`/cardapio-vivo/anuncios/${id}/foto`, arquivo(a)),
  enviarVideo: (id: number, a: File) =>
    api.upload<Anuncio & { message: string }>(`/cardapio-vivo/anuncios/${id}/video`, arquivo(a)),
  removerMidia: (id: number) => api.delete<Anuncio>(`/cardapio-vivo/anuncios/${id}/midia`),
  variantes: (id: number) => api.get<Variante[]>(`/cardapio-vivo/anuncios/${id}/variantes`),
  criarVariante: (id: number, corpo: GravarVariante) => api.post<Variante>(`/cardapio-vivo/anuncios/${id}/variantes`, corpo),
  atualizarVariante: (idVariante: number, corpo: GravarVariante) =>
    api.put<Variante>(`/cardapio-vivo/anuncios/variantes/${idVariante}`, corpo),
  removerVariante: (idVariante: number) => api.delete<{ message: string }>(`/cardapio-vivo/anuncios/variantes/${idVariante}`),
  aplicarVariante: (id: number, idVariante: number | null) =>
    api.post<Anuncio & { message: string }>(`/cardapio-vivo/anuncios/${id}/variantes/aplicar`, { id_variante: idVariante }),
  efeito: (de?: string, ate?: string) => {
    const q = new URLSearchParams();
    if (de) q.set("de", de);
    if (ate) q.set("ate", ate);
    return api.get<Efeito>(`/cardapio-vivo/anuncios/efeito${q.toString() ? `?${q}` : ""}`);
  },
  relatorio: (id: number, de?: string, ate?: string) => {
    const q = new URLSearchParams();
    if (de) q.set("de", de);
    if (ate) q.set("ate", ate);
    return api.get<Relatorio>(`/cardapio-vivo/anuncios/${id}/relatorio${q.toString() ? `?${q}` : ""}`);
  },
};

/** "12,5%" — ou um traço quando não há base. */
export const porcento = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(1).replace(".", ",")}%`;
