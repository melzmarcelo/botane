"use client";

/**
 * Peças da coluna das seções e o painel "O que falta" da aba Cardápio.
 *
 * 🔑 **"O que falta"** (reforma de 15/10/2026): os pratos sem foto, sem
 * descrição, sem preço ou inativos, de TODAS as seções, numa lista só. Quem
 * arruma o cardápio abre um, conserta, e ele sai da lista — sem caçar seção por
 * seção qual prato ainda está cru.
 * 🔑 **Desde a 1.1.109, também os cartões e as traduções**: o cartão que não aparece
 * (vazio) ou cujo botão leva a um prato inativo, e o que ainda está só em português —
 * prato, seção, cartão — com o caminho para a aba Idiomas.
 */

import type { ItemDoCatalogo } from "@/lib/catalogos";
import type { Cartao } from "@/lib/cartoes";
import LinhaDoPrato from "./linha-do-prato";

import { plural } from "@/lib/numeros";
type Lista = { rotulo: string; id_categoria: number; id_subcategoria: number | null; itens: ItemDoCatalogo[] };
export type CartaoComFalta = { cartao: Cartao; onde: string; faltas: string[] };
/** O que está sem tradução: os nomes, para a pessoa reconhecer. */
export type FaltaTraduzir = { pratos: string[]; secoes: string[]; cartoes: number; catalogo: boolean };

/** O que falta num cartão para ele funcionar no feed. */
export function faltasDoCartao(c: Cartao, pratos: ItemDoCatalogo[]): string[] {
  const f: string[] = [];
  if (!c.titulo && !c.texto && !c.foto_url && !c.video_url) f.push("vazio — não aparece");
  if (c.id_item_link) {
    const alvo = pratos.find((i) => i.id === c.id_item_link);
    if (alvo && !alvo.ativo) f.push("o botão leva a um prato inativo");
  }
  return f;
}

export const totalTraduzir = (t: FaltaTraduzir | null) =>
  t ? t.pratos.length + t.secoes.length + t.cartoes + (t.catalogo ? 1 : 0) : 0;

export function PainelFaltas({ listas: comFaltas, aoAbrir: setGaveta, cartoes = [], aoAbrirCartao,
                               traduzir = null, aoIdiomas }: {
  listas: Lista[]; aoAbrir: (idItem: number) => void;
  cartoes?: CartaoComFalta[]; aoAbrirCartao?: (c: CartaoComFalta) => void;
  traduzir?: FaltaTraduzir | null; aoIdiomas?: () => void;
}) {
  const nTraduzir = totalTraduzir(traduzir);
  return (
    <section className="cartao min-w-0" aria-label="o que falta">
      <header className="border-b border-linha px-5 py-4">
        <h2 className="text-[18px] font-bold tracking-tight">O que falta</h2>
        <p className="mt-0.5 text-[13.5px] text-suave">
          Pratos sem foto, sem descrição, sem preço ou inativos; cartões que não funcionam; e o que
          ainda está só em português. Abra um, arrume, e ele sai daqui.
        </p>
      </header>
      <div className="flex flex-col gap-5 p-5">
        {comFaltas.map((l) => (
          <div key={`${l.id_categoria}-${l.id_subcategoria ?? ""}`}>
            <span className="rotulo">{l.rotulo}</span>
            <ul className="mt-1 flex flex-col gap-px bg-linha">
              {l.itens.map((i) => (
                <LinhaDoPrato key={i.id} item={i} primeiro ultimo podeEditar={false}
                              aoAbrir={() => setGaveta(i.id)} aoMover={() => {}} />
              ))}
            </ul>
          </div>
        ))}
        {cartoes.length > 0 && (
          <div id="faltas-cartoes">
            <span className="rotulo">Cartões</span>
            <ul className="mt-1 flex flex-col divide-y divide-linha text-[14px]">
              {cartoes.map((c) => (
                <li key={c.cartao.id}>
                  <button type="button" className="flex w-full flex-wrap items-baseline gap-x-2 py-2 text-left hover:text-erva"
                          onClick={() => aoAbrirCartao?.(c)}>
                    <span className="font-medium">{c.cartao.titulo || "Cartão sem título"}</span>
                    <span className="text-[12.5px] text-suave">{c.onde}</span>
                    <span className="text-[12.5px] text-alerta">{c.faltas.join(" · ")}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {nTraduzir > 0 && traduzir && (
          <div id="faltas-traducao">
            <span className="rotulo">Só em português · {nTraduzir}</span>
            <p className="mt-1 text-[13.5px]">
              {[traduzir.catalogo && "o nome do catálogo",
                traduzir.secoes.length && `${plural(traduzir.secoes.length, "seção", "seções")}`,
                traduzir.pratos.length && `${plural(traduzir.pratos.length, "prato", "pratos")}`,
                traduzir.cartoes && `${plural(traduzir.cartoes, "cartão", "cartões")}`].filter(Boolean).join(", ")}
              {" "}ainda sem inglês e alemão (ou com o português mudado desde a tradução). No site em EN ou DE,
              o cliente lê o português.
            </p>
            {traduzir.pratos.length + traduzir.secoes.length > 0 && (
              <p className="mt-1 text-[12.5px] text-suave">
                {[...traduzir.secoes, ...traduzir.pratos].slice(0, 12).join(" · ")}
                {traduzir.pratos.length + traduzir.secoes.length > 12 && " …"}
              </p>
            )}
            {aoIdiomas && (
              <button type="button" className="link-acao mt-2" onClick={aoIdiomas}>Abrir a aba Idiomas</button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

export function BotaoSecao({ nome, total, ativo, sub, aoClicar }: {
  nome: string; total: number; ativo: boolean; sub?: boolean; aoClicar: () => void;
}) {
  return (
    <button type="button" onClick={aoClicar} aria-current={ativo ? "true" : undefined}
            className={`flex shrink-0 items-center justify-between gap-3 rounded-md border px-3 py-1.5 text-left text-[14px] md:w-full md:border-0 ${
              sub ? "md:pl-6 text-[13.5px]" : "font-semibold"} ${
              ativo ? "border-erva bg-erva-claro text-erva" : "border-linha text-tinta hover:bg-superficie2"}`}>
      <span className="truncate">{sub && <span className="text-suave">▸ </span>}{nome}</span>
      <span className="mono text-[12px] text-suave">{total}</span>
    </button>
  );
}
