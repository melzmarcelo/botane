/**
 * Os cartões de conteúdo do Cardápio Vivo (120) e o vídeo da abertura de seção.
 *
 * 🔑 Pedido do dono (16/10/2026): a introdução do cardápio, a abertura de cada seção e
 * cartões entre os pratos — vídeo, foto ou texto —, só no feed.
 * `id_categoria` nulo = abertura do cardápio; `antes_do_item` nulo = no fim da lista.
 */

import { api } from "@/lib/api";
import type { TipoDeSecao } from "@/lib/catalogos";

export type Cartao = {
  id: number;
  id_catalogo: number;
  id_categoria: number | null;
  id_subcategoria: number | null;
  antes_do_item: number | null;
  titulo: string | null;
  texto: string | null;
  foto_url: string | null;
  video_url: string | null;
  video_capa_url: string | null;
  video_segundos: number | null;
  id_item_link: number | null;
  ativo: boolean;
  /** Atenção no período da lista (`dias`). */
  vistas?: number;
  segundos?: number | null;
  cliques?: number;
};

export type AberturaMedida = { id_categoria: number; id_subcategoria: number | null; vistas: number; segundos: number | null };

/** 🔑 1.1.111: o período é escolhido; o que passou da retenção vem do resumo do dia (124). */
export type PeriodoDaAtencao = 30 | 90 | 365;

export type ListaDeCartoes = {
  cartoes: Cartao[];
  aberturas: AberturaMedida[];
  pratos_por_cartao: number;
  dias?: PeriodoDaAtencao;
  resumido?: { ate: string; aviso: string } | null;
};

export type GravarCartao = Pick<Cartao, "id_categoria" | "id_subcategoria" | "antes_do_item" | "titulo"
  | "texto" | "id_item_link" | "ativo">;

const arquivo = (a: File) => {
  const f = new FormData();
  f.append("arquivo", a);
  return f;
};

export const CartoesService = {
  listar: (idCatalogo: number, dias: PeriodoDaAtencao = 30) =>
    api.get<ListaDeCartoes>(`/catalogos/${idCatalogo}/cartoes?dias=${dias}`),
  criar: (idCatalogo: number, corpo: GravarCartao) => api.post<Cartao>(`/catalogos/${idCatalogo}/cartoes`, corpo),
  atualizar: (id: number, corpo: GravarCartao) => api.put<Cartao>(`/catalogos/cartoes/${id}`, corpo),
  remover: (id: number) => api.delete<{ message: string }>(`/catalogos/cartoes/${id}`),
  enviarFoto: (id: number, a: File) => api.upload<Cartao>(`/catalogos/cartoes/${id}/foto`, arquivo(a)),
  enviarVideo: (id: number, a: File) =>
    api.upload<Cartao & { message: string }>(`/catalogos/cartoes/${id}/video`, arquivo(a)),
  removerMidia: (id: number) => api.delete<Cartao>(`/catalogos/cartoes/${id}/midia`),
  enviarVideoDaSecao: (tipo: TipoDeSecao, id: number, a: File) =>
    api.upload<{ video_url: string; message: string }>(`/catalogos/secoes/${tipo}/${id}/video`, arquivo(a)),
  removerVideoDaSecao: (tipo: TipoDeSecao, id: number) =>
    api.delete<{ video_url: null }>(`/catalogos/secoes/${tipo}/${id}/video`),
};
