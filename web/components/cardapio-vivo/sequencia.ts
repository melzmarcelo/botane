/**
 * A sequência do feed: os pratos com os cartões de conteúdo (120) entre eles.
 *
 * 🔑 Pedido do dono (16/10/2026): a introdução do cardápio, a abertura de cada seção e
 * cartões entre os pratos.
 * - **Abertura do cardápio**: os cartões sem seção, antes de tudo.
 * - **Abertura de seção, AUTOMÁTICA** (decisão do dono): toda seção (ou subdivisão) com foto
 *   ou vídeo ganha uma tela com o nome e a descrição dela, antes do primeiro prato.
 * - **Cartão entre pratos**: antes do prato `antes_do_item`; sem ele (ou o prato não está na
 *   tela — fora do horário, esgotado escondido), no fim da lista dele.
 * ⚠️ **Monta-se AQUI, e não no servidor**: os pratos chegam já filtrados e reordenados (o
 * vencedor de um teste A/B de ordem), e o cartão cola no prato que sobrou.
 * ⚠️ Com filtro de restrição ligado, só pratos: quem pediu "sem glúten" quer achar o prato.
 */

import type { Aberturas, AnuncioFeed, CartaoFeed, ItemFeed, RegrasAnuncioFeed, SecaoFeed } from "@/lib/cardapio-vivo";

type CategoriaFeed = SecaoFeed & { subcategorias: SecaoFeed[] };

export type Passo =
  | { tipo: "prato"; chave: string; id_categoria: number; item: ItemFeed }
  | { tipo: "cartao"; chave: string; id_categoria: number | null; cartao: CartaoFeed }
  | { tipo: "secao"; chave: string; id_categoria: number; id_subcategoria: number | null;
      secao: SecaoFeed; dentroDe: string | null }
  | { tipo: "anuncio"; chave: string; id_categoria: number | null; anuncio: AnuncioFeed };

/** O que a casa configurou para ESTE Cardápio Vivo (121). */
export type OpcoesDaSequencia = {
  aberturas?: Aberturas;
  anuncios?: AnuncioFeed[];
  regras?: RegrasAnuncioFeed | null;
  /** O id anônimo da sessão: o sorteio dos anúncios é o MESMO a cada desenho da tela. */
  semente?: string;
  /**
   * 125: como a pessoa reagiu a cada anúncio já visto — o ritmo que aprende. Só os VISTOS entram,
   * e eles estão antes de onde ela está: o que muda é só o que vem depois.
   */
  reacoes?: ReadonlyMap<number, ReacaoAoAnuncio>;
};

/** PULOU = passou em menos de 1,5 s; IGNOROU = parou e não tocou; TOCOU = tocou no botão. */
export type ReacaoAoAnuncio = "PULOU" | "IGNOROU" | "TOCOU";
/** O mesmo `PULOU_MS` do servidor (`cardapio_anuncios.py`): abaixo disto, não parou para ver. */
export const PULOU_MS = 1500;
/** 125: na seção em que combina, o anúncio pesa o triplo no sorteio. */
const PESO_DA_RELEVANCIA = 3;

const lista = (cat: number | null, sub: number | null) => `${cat ?? 0}:${sub ?? 0}`;
/**
 * 🔑 121: a casa escolhe por Cardápio Vivo — AUTOMATICA (foto ou vídeo), SO_VIDEO ou NUNCA — e
 * cada seção pode desligar a sua (`abertura` falso).
 */
const abre = (s: SecaoFeed | undefined, modo: Aberturas) =>
  !!s && s.abertura !== false && modo !== "NUNCA" && (modo === "SO_VIDEO" ? !!s.video : !!(s.foto || s.video));

export function montarSequencia(itens: ItemFeed[], categorias: CategoriaFeed[], cartoes: CartaoFeed[],
                                comConteudo: boolean, opcoes: OpcoesDaSequencia = {}): Passo[] {
  const modo = opcoes.aberturas ?? "AUTOMATICA";
  const temAbertura = (s: SecaoFeed | undefined) => abre(s, modo);
  const pratos = itens.map((item): Passo => ({ tipo: "prato", chave: `p${item.id}`, id_categoria: item.id_categoria, item }));
  if (!comConteudo) return pratos;

  const naTela = new Set(itens.map((i) => i.id));
  const cartao = (c: CartaoFeed): Passo => ({ tipo: "cartao", chave: `c${c.id}`, id_categoria: c.id_categoria, cartao: c });
  const doFim = (chave: string) => cartoes.filter((c) => c.id_categoria !== null
    && lista(c.id_categoria, c.id_subcategoria) === chave
    && (c.antes_do_item === null || !naTela.has(c.antes_do_item)));
  const porCategoria = new Map(categorias.map((c) => [c.id, c]));
  const comPratosDiretos = new Set(itens.filter((i) => i.id_subcategoria === null).map((i) => i.id_categoria));

  const seq: Passo[] = cartoes.filter((c) => c.id_categoria === null).map(cartao);
  let catAtual: number | null = null;
  let listaAtual: string | null = null;
  for (const item of itens) {
    const chave = lista(item.id_categoria, item.id_subcategoria);
    if (chave !== listaAtual) {
      if (listaAtual) seq.push(...doFim(listaAtual).map(cartao));
      const cat = porCategoria.get(item.id_categoria);
      if (item.id_categoria !== catAtual) {
        catAtual = item.id_categoria;
        if (cat && temAbertura(cat)) {
          seq.push({ tipo: "secao", chave: `s${cat.id}`, id_categoria: cat.id, id_subcategoria: null,
                     secao: cat, dentroDe: null });
        }
        // ⚠️ Seção sem prato direto (tudo nas subdivisões): o cartão "no fim" dela fica logo
        // depois da abertura — senão ele nunca apareceria.
        if (!comPratosDiretos.has(cat?.id ?? -1)) seq.push(...doFim(lista(item.id_categoria, null)).map(cartao));
      }
      const sub = cat?.subcategorias.find((s) => s.id === item.id_subcategoria);
      if (sub && temAbertura(sub)) {
        seq.push({ tipo: "secao", chave: `s${cat!.id}-${sub.id}`, id_categoria: cat!.id, id_subcategoria: sub.id,
                   secao: sub, dentroDe: cat!.nome });
      }
      listaAtual = chave;
    }
    seq.push(...cartoes.filter((c) => c.antes_do_item === item.id).map(cartao));
    seq.push({ tipo: "prato", chave: `p${item.id}`, id_categoria: item.id_categoria, item });
  }
  if (listaAtual) seq.push(...doFim(listaAtual).map(cartao));
  return intercalarAnuncios(seq, opcoes);
}

/**
 * 🔑 **Os anúncios entram pelas regras da casa** (121; o dono: "nada pesado, algo orgânico"):
 * o primeiro só depois do N-ésimo prato, pelo menos M pratos entre um e outro, no máximo K por
 * visita (menos na mesa) e nunca o mesmo duas vezes. Qual entra é sorteado pelo PESO, com a
 * sessão como semente: a mesma pessoa vê a mesma ordem enquanto rola, sem pular.
 * ⚠️ Entra sempre ANTES de um prato — nunca colado no fim, onde ninguém chega.
 * 🔑 **125, o ritmo que aprende** (`regras.recuo`): pulou → a distância até o próximo DOBRA;
 * dois vistos sem toque → acabaram os anúncios desta visita. A reação só existe para o anúncio já
 * visto, e ele está antes de onde a pessoa está — refazer a lista muda só o que vem depois.
 * 🔑 **125, a relevância**: na seção em que combina (`secoes`, ou a do prato que o botão mostra), o
 * anúncio pesa o triplo no sorteio.
 */
function intercalarAnuncios(seq: Passo[], { anuncios = [], regras, semente = "", reacoes }: OpcoesDaSequencia): Passo[] {
  if (!regras || regras.maximo <= 0 || !anuncios.length) return seq;
  const sortear = gerador(semente);
  const restantes = [...anuncios];
  const secaoDoPrato = new Map(seq.flatMap((p) => (p.tipo === "prato" ? [[p.item.id, p.id_categoria] as const] : [])));
  const saida: Passo[] = [];
  let pratos = 0;
  let desdeOUltimo = -Infinity;
  let postos = 0;
  let intervalo = regras.intervalo;
  let ignorados = 0;
  let acabou = false;
  for (const passo of seq) {
    if (passo.tipo === "prato") {
      const chegou = postos === 0 ? pratos >= regras.depois_de : pratos - desdeOUltimo >= intervalo;
      if (!acabou && chegou && postos < regras.maximo && restantes.length) {
        const combina = (a: AnuncioFeed) => (a.secoes?.includes(passo.id_categoria) ?? false)
          || (a.acao.tipo === "PRATO" && a.acao.item !== null && secaoDoPrato.get(a.acao.item) === passo.id_categoria);
        const escolhido = escolherPorPeso(restantes, sortear, combina);
        restantes.splice(restantes.indexOf(escolhido), 1);
        saida.push({ tipo: "anuncio", chave: `a${escolhido.id}`, id_categoria: passo.id_categoria, anuncio: escolhido });
        postos += 1;
        desdeOUltimo = pratos;
        const reacao = regras.recuo ? reacoes?.get(escolhido.id) : undefined;
        if (reacao === "PULOU") intervalo *= 2;
        if (reacao === "IGNOROU" && ++ignorados >= 2) acabou = true;
      }
      pratos += 1;
    }
    saida.push(passo);
  }
  return saida;
}

function escolherPorPeso(lista: AnuncioFeed[], sortear: () => number, combina: (a: AnuncioFeed) => boolean): AnuncioFeed {
  const peso = (a: AnuncioFeed) => Math.max(1, a.peso) * (combina(a) ? PESO_DA_RELEVANCIA : 1);
  const total = lista.reduce((t, a) => t + peso(a), 0);
  let ponto = sortear() * total;
  for (const a of lista) {
    ponto -= peso(a);
    if (ponto < 0) return a;
  }
  return lista[lista.length - 1];
}

/** Um sorteio repetível a partir de um texto (mulberry32 sobre um hash simples). */
function gerador(texto: string): () => number {
  let h = 1779033703 ^ texto.length;
  for (let i = 0; i < texto.length; i++) {
    h = Math.imul(h ^ texto.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  let a = h >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
