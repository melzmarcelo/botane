/**
 * Cardápio Vivo (113) — a camada de service: o feed público da mesa e a gestão.
 *
 * ⚠️ **As rotas públicas usam `fetch` direto, sem `api.get`**, como `lib/marca.ts`: a mesa
 * não tem sessão, e o cliente de API tentaria renovar um token que não existe.
 */

import { api, BASE_API, urlArquivo } from "@/lib/api";

export type Midia =
  | { tipo: "VIDEO"; video: string; capa: string | null }
  | { tipo: "FOTO"; foto: string; herdada: boolean }
  | { tipo: "NENHUMA"; foto: null; herdada: false };

export type OpcaoAdicional = { id: number; nome: string; preco: number | null };
export type GrupoAdicionalFeed = {
  id: number; nome: string; minimo: number; maximo: number; opcoes: OpcaoAdicional[];
};

export type ItemFeed = {
  id: number;
  id_categoria: number;
  id_subcategoria: number | null;
  nome: string;
  descricao: string | null;
  preco: number | null;
  restricoes: string[];
  destaque: boolean;
  esgotado: boolean;
  fora_do_horario: boolean;
  midia: Midia;
  adicionais: GrupoAdicionalFeed[];
};

export type SecaoFeed = {
  id: number; nome: string; descricao: string | null; foto: string | null;
  fora_do_horario: boolean;
};

export type Feed = {
  loja: { id: number; nome: string; casa: string };
  marca: { cor_principal: string | null; cor_fundo: string | null; fonte: string; logo: string | null };
  mesa: { nome: string; salao: string } | null;
  cardapio: string;
  modo: "VITRINE" | "PEDIDO";
  aviso: string | null;
  chamar_garcom: boolean;
  /** A tela de entrada (114): só o que a loja ligou E preencheu. Nulo = direto ao feed. */
  hub: { avaliacao: string | null; wifi: { rede: string; senha: string } | null } | null;
  previa: boolean;
  categorias: (SecaoFeed & { subcategorias: SecaoFeed[] })[];
  itens: ItemFeed[];
  restricoes: { chave: string; nome: string }[];
};

export type Idioma = "pt" | "en" | "de";

/** O feed da mesa (token) ou da loja (sem mesa). `null` quando não existe (404). */
export async function buscarFeed(loja: number, token: string | null, idioma: Idioma): Promise<
  { feed: Feed } | { erro: string; status: number }
> {
  const caminho = token ? `/publico/cardapio/mesa/${encodeURIComponent(token)}`
                        : `/publico/cardapio/loja/${loja}`;
  const q = idioma === "pt" ? "" : `?idioma=${idioma}`;
  try {
    const r = await fetch(`${BASE_API}${caminho}${q}`, { cache: "no-store" });
    const corpo = await r.json().catch(() => ({}));
    if (!r.ok) return { erro: corpo?.detail || "Cardápio indisponível.", status: r.status };
    // ⚠️ Um token de outra loja na URL (`/c/2/<token da loja 1>`): vale o token, que é o
    // segredo — mas a tela não deve fingir que é a loja 2.
    return { feed: corpo as Feed };
  } catch {
    return { erro: "Sem conexão. Tente de novo em instantes.", status: 0 };
  }
}

/** A prévia do cadastro — com login, inclui o que está fora do dia e do horário. */
export const previaFeed = (idCatalogo: number) =>
  api.get<Feed>(`/cardapio-vivo/previa?id_catalogo=${idCatalogo}`);

/** A imagem no tamanho da tela, em WebP (`?w=` da rota de arquivos). */
export function imagem(url: string | null | undefined, largura: number): string | null {
  const u = urlArquivo(url);
  if (!u) return null;
  return u.includes("/arquivos/") ? `${u}?w=${largura}` : u;
}

export function srcSet(url: string | null | undefined): string | undefined {
  const u = urlArquivo(url);
  if (!u || !u.includes("/arquivos/")) return undefined;
  return [480, 720, 960, 1280].map((w) => `${u}?w=${w} ${w}w`).join(", ");
}

export const enderecoEventos = () => `${BASE_API}/publico/cardapio/eventos`;

// ------------------------------------------------------------------ gestão

export type ConfigCardapio = {
  id_unidade: number;
  id_catalogo: number | null;
  modo: "VITRINE" | "PEDIDO";
  exige_confirmacao: boolean;
  pedido_hora_de: string | null;
  pedido_hora_ate: string | null;
  chamar_garcom: boolean;
  esconder_esgotado: boolean;
  cor_principal: string | null;
  cor_fundo: string | null;
  fonte: string;
  logo_url: string | null;
  retencao_meses: number;
  hub_avaliacao: boolean;
  hub_wifi: boolean;
};

export type RespostaConfig = {
  config: ConfigCardapio;
  catalogos: { id: number; nome: string; situacao: string }[];
  opcoes: { modos: string[]; modos_liberados: string[]; fontes: string[] };
  link_loja: string;
  sem_midia: { id: number; nome: string; id_produto: number; categoria: string }[];
  message?: string;
};

export type Excecao = {
  id: number; id_salao: number | null; id_mesa: number | null; modo: string | null;
  exige_confirmacao: boolean | null; pedido_hora_de: string | null; pedido_hora_ate: string | null;
  salao: string | null; mesa: string | null;
};

export type MesaAcesso = {
  id: number; nome: string; token: string; ativo: boolean; id_salao: number; salao: string; link: string;
};

export const CardapioVivoService = {
  config: () => api.get<RespostaConfig>("/cardapio-vivo/config"),
  salvarConfig: (c: Omit<ConfigCardapio, "id_unidade" | "logo_url">) =>
    api.put<RespostaConfig>("/cardapio-vivo/config", c),
  enviarLogo: (arquivo: File) => {
    const f = new FormData();
    f.append("arquivo", arquivo);
    return api.upload<RespostaConfig>("/cardapio-vivo/config/logo", f);
  },
  removerLogo: () => api.delete<RespostaConfig>("/cardapio-vivo/config/logo"),
  excecoes: () => api.get<Excecao[]>("/cardapio-vivo/excecoes"),
  salvarExcecao: (e: Partial<Excecao>) => api.put<{ id: number; message: string }>("/cardapio-vivo/excecoes", e),
  excluirExcecao: (id: number) => api.delete<{ message: string }>(`/cardapio-vivo/excecoes/${id}`),
  mesas: () => api.get<{ mesas: MesaAcesso[]; link_loja: string }>("/cardapio-vivo/mesas"),
  novoToken: (idMesa: number) =>
    api.post<{ link: string; message: string }>(`/cardapio-vivo/mesas/${idMesa}/token`),
  semMidia: (idCatalogo: number) =>
    api.get<RespostaConfig["sem_midia"]>(`/cardapio-vivo/sem-midia?id_catalogo=${idCatalogo}`),
  marcarItem: (idItem: number, marcas: { destaque?: boolean; esgotado?: boolean }) =>
    api.put<{ destaque: boolean; esgotado: boolean; message: string }>(`/catalogos/itens/${idItem}/marcas`, marcas),
  exibicaoSecao: (tipo: "categoria" | "subcategoria", id: number, dados: ExibicaoSecao) =>
    api.put<ExibicaoSecao & { message: string }>(`/catalogos/secoes/${tipo}/${id}/exibicao`, dados),
};

export type ExibicaoSecao = {
  dias: number[] | null; hora_de: string | null; hora_ate: string | null; horario_especial: boolean;
};

// ------------------------------------------------------------------ o produto

export type GrupoAdicionalCadastro = {
  id?: number; nome: string; minimo: number; maximo: number;
  opcoes: { id?: number; nome: string; preco: number | null; id_produto_ref: number | null;
            produto_ref?: string | null; ativo: boolean }[];
};

export type CardapioDoProduto = {
  video: { url: string; capa: string | null; nome: string | null; bytes: number; segundos: number | null } | null;
  restricoes: string[];
  opcoes_restricoes: { chave: string; nome: string }[];
  adicionais: GrupoAdicionalCadastro[];
};

export const ProdutoCardapioService = {
  obter: (id: number) => api.get<CardapioDoProduto>(`/produtos/${id}/cardapio`),
  enviarVideo: (id: number, arquivo: File) => {
    const f = new FormData();
    f.append("arquivo", arquivo);
    return api.upload<{ video: CardapioDoProduto["video"]; message: string }>(`/produtos/${id}/video`, f);
  },
  removerVideo: (id: number) => api.delete<{ message: string }>(`/produtos/${id}/video`),
  restricoes: (id: number, restricoes: string[]) =>
    api.put<{ restricoes: string[]; message: string }>(`/produtos/${id}/restricoes`, { restricoes }),
  adicionais: (id: number, grupos: GrupoAdicionalCadastro[]) =>
    api.put<{ adicionais: GrupoAdicionalCadastro[]; message: string }>(`/produtos/${id}/adicionais`, grupos),
};

/** O PDF dos cartões das mesas (todas, ou as escolhidas). Com token: baixa pelo cliente de API. */
export const baixarQrPdf = (ids?: number[], tamanho: "P" | "M" | "G" = "M") =>
  api.baixar(`/cardapio-vivo/mesas/qr.pdf?tamanho=${tamanho}${ids?.length ? `&ids=${ids.join(",")}` : ""}`);
export const baixarQrPng = (idMesa: number) => api.baixar(`/cardapio-vivo/mesas/${idMesa}/qr.png`);
