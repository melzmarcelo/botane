/**
 * As traduções do cardápio do site (inglês e alemão) — camada de service.
 *
 * 🔑 Pedido do dono (decidido em 29/09/2026): Claude Haiku, categorias também, site nos três
 * idiomas. Regra em `api/services/traducao.py`.
 */
import { api } from "@/lib/api";

export type TipoTraduzivel = "produto" | "categoria" | "subcategoria" | "catalogo";
export type Textos = { nome?: string | null; descricao?: string | null };

export type Traducao = {
  tipo: TipoTraduzivel;
  id: number;
  origem: Textos;
  en: Textos;
  de: Textos;
  /** As COLUNAS corrigidas à mão (ex.: "nome_catalogo_en"). */
  editada: string[];
  traduzida_em: string | null;
  desatualizada: boolean;
  campos: ("nome" | "descricao")[];
  colunas: Record<string, { en: string; de: string }>;
  ligada: boolean;
  modelo: string;
};

export const estado = () => api.get<{ ligada: boolean; modelo: string }>("/traducao/estado");
export const obter = (tipo: TipoTraduzivel, id: number) => api.get<Traducao>(`/traducao/${tipo}/${id}`);
export const corrigir = (tipo: TipoTraduzivel, id: number, corpo: { en?: Textos; de?: Textos }) =>
  api.put<Traducao & { message: string }>(`/traducao/${tipo}/${id}`, corpo);
export const gerar = (tipo: TipoTraduzivel, id: number) =>
  api.post<Traducao & { message: string }>(`/traducao/${tipo}/${id}/gerar`);
export const pendentesDoCatalogo = (id: number) =>
  api.get<{ pendentes: number; ligada: boolean }>(`/traducao/catalogo/${id}/pendentes`);
export const traduzirCatalogo = (id: number) =>
  api.post<{ traduzidos: number; pendentes: number; message: string }>(`/traducao/catalogo/${id}/traduzir`);

/** A chave da Anthropic da casa (Integrações ▸ Tradução). ⚠️ Volta só mascarada. */
export type ConfigTraducao = {
  ativa: boolean;
  ligada: boolean;
  chave: string | null;
  modelo: string;
  modelo_padrao: string;
  credencial_ilegivel: boolean;
  ultimo_status: string | null;
  ultima_mensagem: string | null;
};
export const verConfig = () => api.get<ConfigTraducao>("/traducao/config");
export const salvarConfig = (corpo: { chave?: string | null; modelo?: string | null; ativa: boolean }) =>
  api.put<ConfigTraducao & { message: string }>("/traducao/config", corpo);
export const removerChave = () => api.delete<ConfigTraducao & { message: string }>("/traducao/config/chave");
export const testarConfig = () => api.post<{ ok: boolean; message: string }>("/traducao/config/testar");
