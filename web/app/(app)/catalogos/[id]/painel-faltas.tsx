"use client";

/**
 * Peças da coluna das seções e o painel "O que falta" da aba Cardápio.
 *
 * 🔑 **"O que falta"** (reforma de 15/10/2026): os pratos sem foto, sem
 * descrição, sem preço ou inativos, de TODAS as seções, numa lista só. Quem
 * arruma o cardápio abre um, conserta, e ele sai da lista — sem caçar seção por
 * seção qual prato ainda está cru.
 */

import type { ItemDoCatalogo } from "@/lib/catalogos";
import LinhaDoPrato from "./linha-do-prato";

type Lista = { rotulo: string; id_categoria: number; id_subcategoria: number | null; itens: ItemDoCatalogo[] };

export function PainelFaltas({ listas: comFaltas, aoAbrir: setGaveta }: {
  listas: Lista[]; aoAbrir: (idItem: number) => void;
}) {
  return (
    <section className="cartao min-w-0" aria-label="o que falta">
      <header className="border-b border-linha px-5 py-4">
        <h2 className="text-[18px] font-bold tracking-tight">O que falta</h2>
        <p className="mt-0.5 text-[13.5px] text-suave">
          Pratos sem foto, sem descrição, sem preço ou inativos. Abra um, arrume, e ele sai daqui.
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
