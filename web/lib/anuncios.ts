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
};

export type GravarAnuncio = Omit<Anuncio, "id" | "foto_url" | "video_url" | "video_capa_url" | "video_segundos"
  | "aparicoes" | "sessoes" | "segundos" | "pulados" | "toques" | "sessoes_tocaram" | "situacao" | "avisos"
  | "fora_do_horario_agora">;

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
