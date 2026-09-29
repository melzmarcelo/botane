"use client";

import Link from "next/link";

import type { Alerta } from "./tipos";

/**
 * "Precisa de atenção": uma linha por assunto, o número à esquerda.
 *
 * 🔑 Protótipo aprovado (29/09/2026): fica AO LADO do período, e não depois de rolar — é o
 * que pede ação. No celular sobe para logo abaixo do dia.
 */
export default function Atencao({ alertas, deste }: { alertas: Alerta[]; deste: string }) {
  return (
    <section className="cartao p-4" aria-label="atenção">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-bold">Precisa de atenção</h2>
        <Link href="/alertas" className="link-acao text-[13px]">todos ›</Link>
      </div>
      {/* ⚠️ "deste mês", "desta semana": os termos vêm do SERVIDOR, que sabe o ritmo da loja. */}
      <p className="-mt-1 mb-2 text-[12.5px] text-suave">O que muda o número {deste} se ficar sem resposta.</p>
      {!alertas.length ? (
        <p className="text-[14px] text-suave">Nada pendente agora.</p>
      ) : (
        <ul className="flex flex-col">
          {alertas.slice(0, 6).map((a) => (
            <li key={a.chave} className="border-t border-linha first:border-t-0">
              <Link href={a.href} className="flex items-baseline gap-2.5 py-2 text-[13.5px] no-underline hover:text-erva"
                    title={`${a.detalhe} — ${a.acao}`}>
                <span className={`inline-block h-2 w-2 flex-none -translate-y-px rounded-full ${
                  a.severidade === "critico" ? "bg-erro" : "bg-alerta"}`} />
                <span className={`mono w-7 flex-none text-right text-[13px] font-bold ${
                  a.severidade === "critico" ? "text-erro" : "text-alerta"}`}>{a.quantidade}</span>
                <span className="min-w-0 flex-1 truncate">{a.titulo}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
