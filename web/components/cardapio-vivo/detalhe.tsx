"use client";

/**
 * O detalhe do prato: a descrição inteira, os adicionais e a quantidade.
 *
 * ⚠️ **O mínimo e o máximo de cada grupo são cobrados aqui E no servidor** (fase 2, no
 * pedido). Na VITRINE não há servidor no meio — a seleção é do aparelho —, mas mostrar
 * ao garçom uma escolha que a cozinha não aceita seria pior que não deixar escolher.
 */

import { useMemo, useState } from "react";
import { imagem, type Idioma, type ItemFeed } from "@/lib/cardapio-vivo";
import type { EscolhaAdicional } from "./selecao";
import { moeda, nomeRestricao, type Textos } from "./textos";

type Props = {
  item: ItemFeed;
  t: Textos;
  idioma: Idioma;
  aoFechar: () => void;
  /** Ausente = só consulta (119): a janela mostra o prato e o preço, sem adicionar. */
  aoAdicionar?: (quantidade: number, adicionais: EscolhaAdicional[]) => void;
  /** Cada opção MARCADA vira um `escolheu_opcao` (114). */
  aoEscolher?: () => void;
};

export default function Detalhe({ item, t, idioma, aoFechar, aoAdicionar, aoEscolher }: Props) {
  const [quantidade, setQuantidade] = useState(1);
  const [marcados, setMarcados] = useState<Record<number, number[]>>({});

  const alternar = (grupo: number, opcao: number, maximo: number) => {
    if (!(marcados[grupo] ?? []).includes(opcao)) aoEscolher?.();
    setMarcados((atual) => {
      const ja = atual[grupo] ?? [];
      if (ja.includes(opcao)) return { ...atual, [grupo]: ja.filter((x) => x !== opcao) };
      // Grupo de UMA escolha troca a marcada; com mais, para no máximo.
      if (maximo === 1) return { ...atual, [grupo]: [opcao] };
      if (ja.length >= maximo) return atual;
      return { ...atual, [grupo]: [...ja, opcao] };
    });
  };

  const faltando = item.adicionais.filter((g) => (marcados[g.id]?.length ?? 0) < g.minimo);
  const escolhas: EscolhaAdicional[] = useMemo(
    () => item.adicionais.flatMap((g) =>
      g.opcoes.filter((o) => marcados[g.id]?.includes(o.id)).map((o) => ({ id: o.id, nome: o.nome, preco: o.preco }))),
    [item.adicionais, marcados]);
  const unitario = item.preco === null ? null : item.preco + escolhas.reduce((s, e) => s + (e.preco ?? 0), 0);
  const capa = item.midia.tipo === "VIDEO" ? item.midia.capa : item.midia.tipo === "FOTO" ? item.midia.foto : null;

  return (
    <div className="fixed inset-0 z-40 flex items-end bg-black/50" onClick={aoFechar} role="dialog" aria-modal
         aria-label={item.nome}>
      <div className="max-h-[88dvh] w-full overflow-y-auto rounded-t-3xl bg-[var(--cv-fundo)] text-[var(--cv-tinta)] shadow-2xl"
           onClick={(e) => e.stopPropagation()}>
        {capa && (
          <img src={imagem(capa, 720) ?? undefined} alt="" className="h-52 w-full rounded-t-3xl object-cover" />
        )}
        <div className="px-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] pt-4">
          <div className="flex items-start justify-between gap-3">
            <h2 className="cv-serif text-[1.7rem] leading-tight">{item.nome}</h2>
            <button type="button" onClick={aoFechar} aria-label={t.fechar}
                    className="-mr-2 rounded-full px-3 py-1 text-2xl leading-none opacity-60">×</button>
          </div>
          {item.restricoes.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {item.restricoes.map((r) => (
                <span key={r} className="rounded-full border border-current/30 px-2.5 py-0.5 text-xs opacity-80">
                  {nomeRestricao(idioma, r)}
                </span>
              ))}
            </div>
          )}
          {item.descricao && <p className="mt-3 whitespace-pre-line text-[15px] leading-relaxed opacity-85">{item.descricao}</p>}

          {item.adicionais.map((g) => (
            <fieldset key={g.id} className="mt-5">
              <legend className="flex w-full items-baseline justify-between text-sm font-semibold">
                <span>{g.nome}</span>
                <span className="text-xs font-normal opacity-60">
                  {t.escolha(g.minimo, g.maximo)}{g.minimo > 0 ? ` · ${t.obrigatorio}` : ""}
                </span>
              </legend>
              <div className="mt-2 divide-y divide-current/10 rounded-2xl border border-current/15">
                {g.opcoes.map((o) => {
                  const marcado = marcados[g.id]?.includes(o.id) ?? false;
                  return (
                    <label key={o.id} className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3">
                      <span className="flex items-center gap-3">
                        <input
                          type={g.maximo === 1 ? "radio" : "checkbox"}
                          name={`grupo-${g.id}`}
                          checked={marcado}
                          onChange={() => alternar(g.id, o.id, g.maximo)}
                          className="h-5 w-5 accent-[var(--cv-principal)]"
                        />
                        {o.nome}
                      </span>
                      {o.preco ? <span className="text-sm tabular-nums opacity-75">+ {moeda(o.preco)}</span> : null}
                    </label>
                  );
                })}
              </div>
            </fieldset>
          ))}

          {!aoAdicionar ? (
            unitario !== null && <p className="cv-mono mt-6 text-xl">{moeda(unitario)}</p>
          ) : (
          <div className="mt-6 flex items-center gap-3">
            <div className="flex items-center rounded-full border border-current/20" aria-label={t.quantidade}>
              <button type="button" className="px-4 py-2.5 text-lg" onClick={() => setQuantidade((q) => Math.max(1, q - 1))}
                      aria-label="−">−</button>
              <span className="w-6 text-center tabular-nums">{quantidade}</span>
              <button type="button" className="px-4 py-2.5 text-lg" onClick={() => setQuantidade((q) => Math.min(20, q + 1))}
                      aria-label="+">+</button>
            </div>
            <button
              type="button"
              disabled={item.esgotado || faltando.length > 0}
              onClick={() => aoAdicionar(quantidade, escolhas)}
              className="flex-1 rounded-full bg-[var(--cv-principal)] px-4 py-3 font-semibold text-white disabled:opacity-40"
            >
              {item.esgotado ? t.esgotado : (
                <>
                  {t.adicionarSelecao}
                  {unitario !== null && <span className="ml-2 tabular-nums opacity-90">{moeda(unitario * quantidade)}</span>}
                </>
              )}
            </button>
          </div>
          )}
        </div>
      </div>
    </div>
  );
}
