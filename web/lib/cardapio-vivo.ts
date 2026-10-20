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
  /** 120: o vídeo da abertura automática da seção (ganha da foto) e a capa dele. */
  video?: string | null; capa?: string | null;
  /** 121: a seção abre com tela própria (a casa pode desligar a de cada uma). */
  abertura?: boolean;
  fora_do_horario: boolean;
};

/** Um anúncio que vale AGORA neste Cardápio Vivo (121). Quem decide onde entra é a tela. */
export type AnuncioFeed = {
  id: number;
  origem: "CASA" | "EXTERNO";
  anunciante: string | null;
  peso: number;
  titulo: string | null;
  texto: string | null;
  midia: CartaoFeed["midia"];
  acao: { tipo: "NENHUMA" | "CATALOGO" | "PRATO" | "LINK"; rotulo: string | null; catalogo: number | null;
          slug: string | null; item: number | null; url: string | null };
  /** 125: a variação do texto que ESTA visita vê (nulo = a original) — vai nos eventos. */
  variante?: number | null;
  /** 125: as seções em que combina (nulo = todas): ali ele pesa mais no sorteio. */
  secoes?: number[] | null;
};

/** `recuo` (125): o ritmo que aprende — pulou dobra a distância; dois sem toque, acabou. */
export type RegrasAnuncioFeed = { depois_de: number; intervalo: number; maximo: number; recuo?: boolean };
/** 125: o grupo da visita nos anúncios. Nulo = fora da comparação (sem sessão, sem anúncio). */
export type GrupoAnuncio = "CONTROLE" | "EXPOSTO";
export type Aberturas = "AUTOMATICA" | "SO_VIDEO" | "NUNCA";

/**
 * Um cartão de conteúdo do feed (120): a abertura do cardápio (`id_categoria` nulo) ou um
 * cartão entre os pratos, ANTES do prato `antes_do_item` (nulo = no fim da lista dele).
 */
export type CartaoFeed = {
  id: number;
  id_categoria: number | null;
  id_subcategoria: number | null;
  antes_do_item: number | null;
  id_item_link: number | null;
  titulo: string | null;
  texto: string | null;
  midia: { tipo: "VIDEO"; video: string; capa: string | null } | { tipo: "FOTO"; foto: string } | { tipo: "NENHUMA" };
};

export type Feed = {
  loja: { id: number; nome: string; casa: string };
  marca: { cor_principal: string | null; cor_fundo: string | null; fonte: string; logo: string | null };
  mesa: { nome: string; salao: string } | null;
  cardapio: string;
  modo: "VITRINE" | "PEDIDO";
  aviso: string | null;
  chamar_garcom: boolean;
  /** Falso = só consulta (119): sem o botão de adicionar e sem a "minha seleção". */
  selecao: boolean;
  /** A tela de entrada (114): só o que a loja ligou E preencheu. Nulo = direto ao feed. */
  hub: { avaliacao: string | null; wifi: { rede: string; senha: string } | null } | null;
  previa: boolean;
  /** Sem mesa, o catálogo aceita pedido pelo site: a seleção vira encomenda (o catering). */
  encomenda: boolean;
  /** Qual Cardápio Vivo é este (117): o catálogo vai nos eventos. */
  vivo: { id_catalogo: number; slug: string | null; principal: boolean };
  /** Os cartões de conteúdo (120). Só no feed. */
  cartoes: CartaoFeed[];
  /** 121: quais seções abrem, os anúncios que valem agora e as regras de exibição da casa. */
  aberturas: Aberturas;
  anuncios: AnuncioFeed[];
  regras_anuncio: RegrasAnuncioFeed | null;
  grupo_anuncio?: GrupoAnuncio | null;
  categorias: (SecaoFeed & { subcategorias: SecaoFeed[] })[];
  itens: ItemFeed[];
  restricoes: { chave: string; nome: string }[];
};

export type Idioma = "pt" | "en" | "de";

/** O feed da mesa (token) ou da loja (sem mesa). `null` quando não existe (404). */
export async function buscarFeed(loja: number, token: string | null, idioma: Idioma,
                                 sessao: string | null = null, cardapio: string | null = null): Promise<
  { feed: Feed } | { erro: string; status: number }
> {
  const caminho = token ? `/publico/cardapio/mesa/${encodeURIComponent(token)}`
                        : `/publico/cardapio/loja/${loja}`;
  // A sessão anônima sorteia o braço dos testes A/B (116); sem ela, ninguém entra em teste.
  const params = new URLSearchParams();
  if (idioma !== "pt") params.set("idioma", idioma);
  if (sessao) params.set("sessao", sessao);
  if (cardapio && !token) params.set("cardapio", cardapio);
  const q = params.toString() ? `?${params}` : "";
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

/**
 * A página inicial do site da casa (15/10/2026): no domínio `reservas.*` é a raiz; nos
 * outros (o do sistema, e em casa) é `/portal`. O feed e o site são o MESMO app.
 */
export function enderecoDoSite(): string {
  if (typeof window === "undefined") return "/portal";
  return window.location.hostname.startsWith("reservas.") ? "/" : "/portal";
}

/** A prévia do cadastro — com login, inclui o que está fora do dia e do horário. */
export const previaFeed = (idCatalogo: number, comAnuncios = false) =>
  api.get<Feed>(`/cardapio-vivo/previa?id_catalogo=${idCatalogo}${comAnuncios ? "&anuncios=true" : ""}`);

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

/** O que é da CASA (117): a aparência do site inteiro, o Hub, esgotado e retenção. */
export type ConfigCardapio = {
  id_unidade: number;
  /** O catálogo do Cardápio Vivo PRINCIPAL (o da mesa) — calculado, só leitura. */
  id_catalogo: number | null;
  esconder_esgotado: boolean;
  cor_principal: string | null;
  cor_fundo: string | null;
  fonte: string;
  logo_url: string | null;
  retencao_meses: number;
  hub_avaliacao: boolean;
  hub_wifi: boolean;
};

/** Um Cardápio Vivo (117): o catálogo, o nome no link, se é o da mesa e o comportamento. */
export type VivoCardapio = {
  id_catalogo: number;
  nome: string;
  situacao: string;
  slug: string;
  principal: boolean;
  modo: "VITRINE" | "PEDIDO";
  exige_confirmacao: boolean;
  pedido_hora_de: string | null;
  pedido_hora_ate: string | null;
  chamar_garcom: boolean;
  /** Na vitrine, falso = só consulta (119). */
  selecao: boolean;
  /** 121: quais seções abrem com tela própria no feed. */
  aberturas: "AUTOMATICA" | "SO_VIDEO" | "NUNCA";
  /** O link sem mesa — o principal sem `?cardapio=`. */
  link: string;
};

export type GravarVivo = Omit<VivoCardapio, "id_catalogo" | "nome" | "situacao" | "link" | "slug"> & {
  slug: string | null;
};

export type RespostaConfig = {
  config: ConfigCardapio;
  vivos: VivoCardapio[];
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

/** 20/10/2026: quanto da medição existe num período (a prévia do apagar). */
export type MedicaoDoPeriodo = {
  de: string; ate: string; eventos: number; sessoes: number;
  agregados_dia: number; resumo_dia: number; conteudo_dia: number; vazio: boolean;
};

export const CardapioVivoService = {
  medicao: (de: string, ate: string) =>
    api.get<MedicaoDoPeriodo>(`/cardapio-vivo/medicao?de=${de}&ate=${ate}`),
  apagarMedicao: (de: string, ate: string) =>
    api.post<MedicaoDoPeriodo & { message: string; sessoes_apagadas: number }>("/cardapio-vivo/medicao/apagar", { de, ate }),
  config: () => api.get<RespostaConfig>("/cardapio-vivo/config"),
  salvarConfig: (c: Omit<ConfigCardapio, "id_unidade" | "logo_url" | "id_catalogo">) =>
    api.put<RespostaConfig>("/cardapio-vivo/config", c),
  /** Liga o catálogo como Cardápio Vivo, ou regrava o comportamento dele (117). */
  salvarVivo: (idCatalogo: number, v: GravarVivo) =>
    api.put<RespostaConfig>(`/cardapio-vivo/vivos/${idCatalogo}`, v),
  removerVivo: (idCatalogo: number) =>
    api.delete<RespostaConfig>(`/cardapio-vivo/vivos/${idCatalogo}`),
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
  marcarItem: (idItem: number, marcas: { destaque?: boolean; esgotado?: boolean;
                                         /** 123: quando o esgotado volta sozinho. */
                                         esgotado_volta?: "AMANHA" | "MANUAL"; objetivo?: string;
                                         margem_nivel?: string }) =>
    api.put<{ destaque: boolean; esgotado: boolean; esgotado_ate: string | null; objetivo: string | null;
              margem_nivel: string | null; message: string }>(`/catalogos/itens/${idItem}/marcas`, marcas),
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

// ------------------------------------------------------------------ fase 2 (115): a mesa

export type PedidoPublico = {
  numero: number;
  situacao: "NOVO" | "CONFIRMADO" | "ENTREGUE" | "RECUSADO" | "CANCELADO";
  motivo: string | null;
  mesa: string | null;
  total: number;
  criado_em: string;
  itens: { nome: string; quantidade: number; total: number; observacao: string | null;
           adicionais: { nome: string; preco: number | null }[] | null }[];
  repetido?: boolean;
};

export type RespostaIdentificacao = {
  nome: string;
  novo: boolean;
  telefone: string;
  fidelidade: null | { precisa_termo?: boolean; metodo?: "QRCODE_MESA" | "CODIGO_CAIXA";
                       marcou?: boolean; aguardando_codigo?: boolean; motivo?: string;
                       visitas?: number; faltam?: number; premio_novo?: unknown };
};

/** As rotas públicas da mesa: `fetch` direto, devolvendo o status para a tela decidir. */
async function publico<T>(metodo: string, caminho: string, corpo?: unknown): Promise<
  { ok: true; dados: T } | { ok: false; status: number; erro: string }
> {
  try {
    const r = await fetch(`${BASE_API}${caminho}`, {
      method: metodo,
      headers: corpo === undefined ? undefined : { "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
      cache: "no-store",
    });
    const dados = await r.json().catch(() => ({}));
    if (!r.ok) {
      const d = dados?.detail;
      return { ok: false, status: r.status, erro: typeof d === "string" ? d : "Não foi possível agora." };
    }
    return { ok: true, dados: dados as T };
  } catch {
    return { ok: false, status: 0, erro: "Sem conexão. Tente de novo em instantes." };
  }
}

export const MesaService = {
  enviarPedido: (token: string, corpo: {
    sessao: string; chave: string; observacao?: string | null; telefone?: string | null;
    itens: { item: number; quantidade: number; adicionais: number[]; observacao?: string | null }[];
  }) => publico<PedidoPublico>("POST", `/publico/cardapio/mesa/${encodeURIComponent(token)}/pedido`, corpo),
  pedidos: (token: string, sessao: string) =>
    publico<PedidoPublico[]>("GET", `/publico/cardapio/mesa/${encodeURIComponent(token)}/pedidos?sessao=${sessao}`),
  chamar: (token: string, tipo: "GARCOM" | "CONTA", sessao: string) =>
    publico<{ novo: boolean; message: string }>("POST", `/publico/cardapio/mesa/${encodeURIComponent(token)}/chamado`,
                                                { tipo, sessao }),
  identificar: (token: string, corpo: Record<string, unknown>) =>
    publico<RespostaIdentificacao>("POST", `/publico/cardapio/mesa/${encodeURIComponent(token)}/identificar`, corpo),
  confirmarCodigo: (loja: number, telefone: string, codigo: string) =>
    publico<{ visitas?: number }>("POST", `/publico/${loja}/fidelidade/codigo/confirmar`, { telefone, codigo }),
  termo: (loja: number) =>
    publico<{ versao: string; titulo: string; secoes: { titulo?: string; paragrafos: string[] }[] }>(
      "GET", `/publico/${loja}/termo`),
};

// ------------------------------------------------------------------ o painel Atenção × Vendas

export type ItemAtencao = {
  id_item: number; id_produto: number; nome: string; secao: string; destaque: boolean;
  tem_video: boolean; objetivo: string | null; objetivo_rotulo: string | null;
  visualizacoes: number; atencao_ms: number; atencao_media_ms: number | null;
  taxa_adicao: number | null; desistencia: number | null; quase_pediu: number;
  favoritos: number; deslizes_tras: number; vendas_qtd: number; receita: number;
  margem_pct: number | null; margem_alvo_pct: number | null; margem_nivel: string | null;
  margem_calculada: string | null; margem_manual: string | null;
  quadrante: string; sugestao: string | null; sugestao_rotulo: string | null; prioridade: number;
};

export type CardapioDoPainel = { id_catalogo: number; nome: string; principal: boolean };

export type PainelAtencao = {
  /** O Cardápio Vivo medido (1.1.109) e os outros da loja, para escolher. */
  cardapio: CardapioDoPainel | null;
  cardapios: CardapioDoPainel[];
  definicoes: Record<string, string>;
  topo: { sessoes: number; engajadas: number; hubs: number; cliques_avaliacao: number; cliques_wifi: number };
  funil: { sessoes: number; viram: number; adicionaram: number; enviaram: number };
  bruto_desde: string | null;
  itens: ItemAtencao[];
  midia: Partial<Record<"VIDEO" | "FOTO", { visualizacoes: number; atencao_media_ms: number | null; taxa_adicao: number | null }>>;
  mapa: { mesa: string; salao: string; hora: number; sessoes: number }[];
  chamados: Partial<Record<"GARCOM" | "CONTA", { total: number; atendidos: number; tempo_medio_min: number | null }>>;
  avisos: string[];
};

export const AtencaoService = {
  painel: (f: { de: string; ate: string; id_salao?: number | null; dias?: number[]; hora_de?: string; hora_ate?: string;
           id_catalogo?: number | null }) => {
    const q = new URLSearchParams({ de: f.de, ate: f.ate });
    if (f.id_catalogo) q.set("id_catalogo", String(f.id_catalogo));
    if (f.id_salao) q.set("id_salao", String(f.id_salao));
    if (f.dias?.length) q.set("dias", f.dias.join(","));
    if (f.hora_de && f.hora_ate) { q.set("hora_de", f.hora_de); q.set("hora_ate", f.hora_ate); }
    return api.get<PainelAtencao>(`/cardapio-vivo/atencao?${q}`);
  },
  atenderChamado: (id: number) => api.post<{ message: string }>(`/cardapio-vivo/chamados/${id}/atender`),
};

// ------------------------------------------------------------------ fase 3 (116): testes A/B e destaque

export type BracoTeste = { rotulo: string; sessoes: number; adicionaram: number };
export type TesteAB = {
  id: number;
  tipo: "MIDIA" | "ORDEM";
  nome: string;
  id_produto: number | null;
  id_catalogo: number;
  /** O nome do Cardápio Vivo do teste. */
  cardapio: string | null;
  inicio: string;
  encerrado_em: string | null;
  vencedor: "A" | "B" | null;
  aplicado_em: string | null;
  aberto: boolean;
  resultado: {
    A: BracoTeste; B: BracoTeste; minimo_por_braco: number;
    taxa_a: number | null; taxa_b: number | null; p_valor: number | null;
    conclusao: "AMOSTRA_PEQUENA" | "SEM_DIFERENCA" | "A_VENCE" | "B_VENCE";
  };
};
export type SugestaoDestaque = { id_item: number; nome: string; acao: "POR" | "TIRAR"; motivo: string; prioridade: number };

export const TestesService = {
  listar: () => api.get<TesteAB[]>("/cardapio-vivo/testes"),
  criar: (tipo: "MIDIA" | "ORDEM", idItem?: number, idCatalogo?: number | null) =>
    api.post<TesteAB & { message: string }>("/cardapio-vivo/testes",
                                            { tipo, id_item: idItem ?? null, id_catalogo: idCatalogo ?? null }),
  encerrar: (id: number) => api.post<TesteAB & { message: string }>(`/cardapio-vivo/testes/${id}/encerrar`),
  aplicar: (id: number, variante: "A" | "B") =>
    api.post<TesteAB & { message: string }>(`/cardapio-vivo/testes/${id}/aplicar`, { variante }),
  sugestoes: (de: string, ate: string, idCatalogo?: number | null) =>
    api.get<SugestaoDestaque[]>(`/cardapio-vivo/destaques/sugestoes?de=${de}&ate=${ate}`
                                + (idCatalogo ? `&id_catalogo=${idCatalogo}` : "")),
  aplicarDestaques: (escolhas: { id_item: number; destaque: boolean }[]) =>
    api.post<{ message: string }>("/cardapio-vivo/destaques/aplicar", escolhas),
};
