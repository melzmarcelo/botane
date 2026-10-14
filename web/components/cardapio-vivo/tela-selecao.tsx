"use client";

/**
 * O resumo da seleção, para MOSTRAR AO GARÇOM — letra grande, a mesa no topo.
 * 🔑 Não envia nada: é a VITRINE. O garçom anota (ou lança no PDV) como sempre.
 */

import { precoDaLinha, type LinhaSelecao } from "./selecao";
import { moeda, type Textos } from "./textos";

type Props = {
  linhas: LinhaSelecao[];
  total: number;
  algumSemPreco: boolean;
  mesa: string | null;
  t: Textos;
  aoRemover: (linha: LinhaSelecao) => void;
  aoLimpar: () => void;
  aoFechar: () => void;
};

export default function TelaSelecao({ linhas, total, algumSemPreco, mesa, t, aoRemover, aoLimpar, aoFechar }: Props) {
  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-[var(--cv-fundo)] text-[var(--cv-tinta)]" role="dialog" aria-modal
         aria-label={t.minhaSelecao}>
      <header className="flex items-center justify-between border-b border-current/10 px-5 pb-3 pt-[max(1rem,env(safe-area-inset-top))]">
        <div>
          <h2 className="cv-serif text-2xl">{t.minhaSelecao}</h2>
          <p className="text-sm opacity-70">{mesa ? `${mesa} · ` : ""}{t.mostrarGarcom}</p>
        </div>
        <button type="button" onClick={aoFechar} className="rounded-full px-3 py-1 text-3xl leading-none opacity-60"
                aria-label={t.fechar}>×</button>
      </header>

      <div className="flex-1 overflow-y-auto px-5">
        {linhas.length === 0 ? (
          <p className="mt-10 text-center opacity-70">{t.vazia}</p>
        ) : (
          <ul className="divide-y divide-current/10">
            {linhas.map((l) => {
              const preco = precoDaLinha(l);
              return (
                <li key={l.chave} className="flex items-start justify-between gap-3 py-4">
                  <div>
                    <p className="text-lg font-semibold leading-snug">
                      <span className="mr-2 tabular-nums">{l.quantidade}×</span>{l.nome}
                    </p>
                    {l.adicionais.length > 0 && (
                      <p className="mt-0.5 text-sm opacity-75">{l.adicionais.map((a) => a.nome).join(" · ")}</p>
                    )}
                    <button type="button" onClick={() => aoRemover(l)} className="mt-1 text-sm underline opacity-60">
                      {t.remover}
                    </button>
                  </div>
                  <span className="shrink-0 tabular-nums">{preco !== null ? moeda(preco) : t.semPreco}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {linhas.length > 0 && (
        <footer className="border-t border-current/10 px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
          <div className="flex items-baseline justify-between text-lg font-semibold">
            <span>{t.total}</span>
            <span className="tabular-nums">{moeda(total)}{algumSemPreco ? " +" : ""}</span>
          </div>
          <p className="mt-1 text-xs opacity-60">{t.precosSujeitos}</p>
          <button type="button" onClick={aoLimpar} className="mt-3 w-full rounded-full border border-current/25 py-2.5 text-sm">
            {t.limpar}
          </button>
        </footer>
      )}
    </div>
  );
}
