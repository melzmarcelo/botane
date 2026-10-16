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

import type { CartaoFeed, ItemFeed, SecaoFeed } from "@/lib/cardapio-vivo";

type CategoriaFeed = SecaoFeed & { subcategorias: SecaoFeed[] };

export type Passo =
  | { tipo: "prato"; chave: string; id_categoria: number; item: ItemFeed }
  | { tipo: "cartao"; chave: string; id_categoria: number | null; cartao: CartaoFeed }
  | { tipo: "secao"; chave: string; id_categoria: number; id_subcategoria: number | null;
      secao: SecaoFeed; dentroDe: string | null };

const lista = (cat: number | null, sub: number | null) => `${cat ?? 0}:${sub ?? 0}`;
const temAbertura = (s: SecaoFeed | undefined) => !!s && !!(s.foto || s.video);

export function montarSequencia(itens: ItemFeed[], categorias: CategoriaFeed[], cartoes: CartaoFeed[],
                                comConteudo: boolean): Passo[] {
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
  return seq;
}
