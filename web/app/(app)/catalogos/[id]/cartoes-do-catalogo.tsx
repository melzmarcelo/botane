"use client";

/**
 * Os cartões de conteúdo do Cardápio Vivo (120) no editor do catálogo: a abertura do
 * cardápio e os cartões entre os pratos, na MESMA lista dos pratos — vê-se e arruma-se tudo
 * junto, na ordem em que o cliente vai ver.
 *
 * 🔑 Pedido do dono (16/10/2026). Só no feed: o site e o PDF continuam só com os pratos.
 * ⚠️ A posição é "antes do prato X" (ou o fim da lista): o cartão acompanha o prato quando
 * ele sobe ou desce pelas setas.
 */

import { useCallback, useEffect, useState } from "react";
import type * as cat from "@/lib/catalogos";
import { CartoesService, type AberturaMedida, type Cartao, type ListaDeCartoes, type PeriodoDaAtencao } from "@/lib/cartoes";

/** Os cartões do catálogo, com a atenção do período escolhido (30 dias, de partida). */
export function useCartoes(idCatalogo: number) {
  const [lista, setLista] = useState<ListaDeCartoes | null>(null);
  const [dias, setDias] = useState<PeriodoDaAtencao>(30);
  const recarregar = useCallback(async () => {
    try {
      setLista(await CartoesService.listar(idCatalogo, dias));
    } catch {
      setLista({ cartoes: [], aberturas: [], pratos_por_cartao: 4 });
    }
  }, [idCatalogo, dias]);
  useEffect(() => { void recarregar(); }, [recarregar]);
  return { lista, recarregar, dias, setDias };
}

export const NOME_DO_PERIODO: Record<PeriodoDaAtencao, string> = {
  30: "últimos 30 dias", 90: "últimos 90 dias", 365: "últimos 12 meses",
};

/** A atenção da abertura automática de UMA seção (ou subdivisão), em texto curto. */
export function atencaoDaAbertura(aberturas: AberturaMedida[] | undefined, idCategoria: number, idSubcategoria: number | null) {
  const a = aberturas?.find((x) => x.id_categoria === idCategoria && (x.id_subcategoria ?? null) === idSubcategoria);
  return a?.vistas ? `abertura vista ${a.vistas}× (${a.segundos ?? 0} s em média)` : "";
}

const descreverMidia = (c: Cartao) =>
  c.video_url ? `vídeo${c.video_segundos ? ` ${Number(c.video_segundos).toFixed(0)} s` : ""}` : c.foto_url ? "foto" : "só texto";

export function LinhaDoCartao({ cartao, aoAbrir }: { cartao: Cartao; aoAbrir: () => void }) {
  const vazio = !cartao.titulo && !cartao.texto && !cartao.foto_url && !cartao.video_url;
  return (
    <li className="flex items-center gap-3 bg-superficie2 px-3 py-2.5" data-cartao-editor={cartao.id}>
      <span aria-hidden className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-dashed border-linha text-[18px] text-suave">✦</span>
      <button type="button" onClick={aoAbrir} className="min-w-0 flex-1 text-left">
        <span className="block truncate text-[14px] font-semibold">
          {cartao.titulo || (cartao.texto ? cartao.texto.slice(0, 60) : "Cartão sem texto")}
        </span>
        <span className="block text-[12.5px] text-suave">
          Cartão · {descreverMidia(cartao)}
          {!cartao.ativo && " · desligado"}
          {vazio && " · vazio, não aparece"}
          {cartao.vistas ? ` · visto ${cartao.vistas}× (${cartao.segundos ?? 0} s em média)` : ""}
          {cartao.cliques ? ` · ${cartao.cliques} no “Ver o prato”` : ""}
        </span>
      </button>
      <button type="button" className="link-acao" onClick={aoAbrir}>editar</button>
    </li>
  );
}

/**
 * Os pratos de UMA lista com os cartões dela no lugar: antes do prato que cada um apresenta
 * e, por último, os do fim. Quem desenha o prato é a aba (as setas e a gaveta moram lá).
 */
export function PratosECartoes({ itens, idCategoria, idSubcategoria, cartoes, desenharPrato, aoAbrirCartao, pratosPorCartao }: {
  itens: cat.ItemDoCatalogo[];
  idCategoria: number;
  idSubcategoria: number | null;
  cartoes: Cartao[];
  desenharPrato: (item: cat.ItemDoCatalogo, n: number) => React.ReactNode;
  aoAbrirCartao: (c: Cartao) => void;
  pratosPorCartao: number;
}) {
  const daLista = cartoes.filter((c) => c.id_categoria === idCategoria && (c.id_subcategoria ?? null) === idSubcategoria);
  const naLista = new Set(itens.map((i) => i.id));
  const doFim = daLista.filter((c) => c.antes_do_item === null || !naLista.has(c.antes_do_item));
  // 🔑 A recomendação dada ao dono: um cartão a cada quatro pratos, no máximo. Avisa, não proíbe.
  const demais = daLista.filter((c) => c.ativo).length > Math.max(1, Math.ceil(itens.length / pratosPorCartao));
  if (!itens.length && !daLista.length) return null;
  return (
    <>
      {demais && (
        <p className="mt-2 rounded-md bg-alerta-claro px-3 py-2 text-[13px] text-alerta">
          Muitos cartões para poucos pratos: o recomendado é um a cada {pratosPorCartao}. Quem está na mesa quer achar o prato.
        </p>
      )}
      <ul className="mt-2 flex flex-col gap-px bg-linha">
        {itens.map((i, n) => (
          <PratoComCartoes key={i.id} antes={daLista.filter((c) => c.antes_do_item === i.id)} aoAbrirCartao={aoAbrirCartao}>
            {desenharPrato(i, n)}
          </PratoComCartoes>
        ))}
        {doFim.map((c) => <LinhaDoCartao key={`c${c.id}`} cartao={c} aoAbrir={() => aoAbrirCartao(c)} />)}
      </ul>
    </>
  );
}

function PratoComCartoes({ antes, aoAbrirCartao, children }: { antes: Cartao[]; aoAbrirCartao: (c: Cartao) => void; children: React.ReactNode }) {
  return (
    <>
      {antes.map((c) => <LinhaDoCartao key={`c${c.id}`} cartao={c} aoAbrir={() => aoAbrirCartao(c)} />)}
      {children}
    </>
  );
}

/** A abertura do cardápio: os cartões que vêm antes do primeiro prato, acima das seções. */
export function AberturaDoCardapio({ cartoes, podeEditar, aoNovo, aoAbrir, dias, aoDias, resumido }: {
  cartoes: Cartao[]; podeEditar: boolean; aoNovo: () => void; aoAbrir: (c: Cartao) => void;
  dias: PeriodoDaAtencao; aoDias: (d: PeriodoDaAtencao) => void; resumido?: ListaDeCartoes["resumido"];
}) {
  const abertura = cartoes.filter((c) => c.id_categoria === null);
  return (
    <section className="cartao px-5 py-4" aria-label="abertura do cardápio">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[15px] font-bold">Abertura no Cardápio Vivo</h2>
          <p className="text-[13px] text-suave">
            Um vídeo, uma foto ou um texto que apresenta o cardápio, antes do primeiro prato. As seções com foto
            ou vídeo já abrem sozinhas com o nome e a descrição delas. Só no Cardápio Vivo — o site e o PDF não mostram.
          </p>
        </div>
        <span className="flex flex-wrap items-center gap-2">
          {/* 🔑 1.1.111: de quando é a atenção que os cartões e as seções mostram. */}
          <label className="flex items-center gap-1.5 text-[13px] text-suave">
            Atenção dos
            <select id="cartoes-periodo" className="campo py-1 text-[13px]" value={dias}
                    onChange={(e) => aoDias(Number(e.target.value) as PeriodoDaAtencao)}>
              {([30, 90, 365] as const).map((d) => <option key={d} value={d}>{NOME_DO_PERIODO[d]}</option>)}
            </select>
          </label>
          {podeEditar && <button type="button" className="btn btn-secundario" onClick={aoNovo}>+ abertura</button>}
        </span>
      </div>
      {resumido && <p id="cartoes-resumido" className="mt-2 text-[12.5px] text-suave">{resumido.aviso}</p>}
      {abertura.length > 0 && (
        <ul className="mt-3 flex flex-col gap-px bg-linha">
          {abertura.map((c) => <LinhaDoCartao key={c.id} cartao={c} aoAbrir={() => aoAbrir(c)} />)}
        </ul>
      )}
    </section>
  );
}
