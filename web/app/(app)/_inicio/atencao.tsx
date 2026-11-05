"use client";

import Link from "next/link";

import type { Alerta } from "./tipos";

/**
 * "Precisa de atenção": uma linha por assunto, o número à esquerda.
 *
 * 🔑 Protótipo aprovado (29/09/2026): fica AO LADO do período, e não depois de rolar — é o
 * que pede ação. No celular sobe para logo abaixo do dia.
 * 🔑 **Layout novo (05/11/2026)**: as "Pendências" do protótipo — cada linha é um bloco com o
 * número num selo colorido (vermelho para crítico, âmbar para atenção), o título, o detalhe e a
 * seta. ⚠️ A cor nunca vai sozinha: o selo carrega o número e a linha o título.
 */
const SELO: Record<Alerta["severidade"], string> = {
  critico: "bg-erro-claro text-erro",
  atencao: "bg-alerta-claro text-alerta",
  aviso: "bg-[#e3ecf7] text-[#1f4c80]",
};

export default function Atencao({ alertas, deste }: { alertas: Alerta[]; deste: string }) {
  return (
    <section className="cartao flex h-full flex-col p-5" aria-label="atenção">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h2 className="text-[16px] font-bold">Precisa de atenção</h2>
        <Link href="/alertas" className="btn btn-terciario btn-pequeno">Todos</Link>
      </div>
      {/* ⚠️ "deste mês", "desta semana": os termos vêm do SERVIDOR, que sabe o ritmo da loja. */}
      <p className="mb-3 text-[12.5px] text-suave">O que muda o número {deste} se ficar sem resposta.</p>
      {!alertas.length ? (
        <p className="text-[14px] text-suave">Nada pendente agora.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {alertas.slice(0, 6).map((a) => (
            <li key={a.chave}>
              <Link href={a.href} title={`${a.detalhe} — ${a.acao}`}
                    className="flex items-center gap-3 rounded-xl border border-[#eef0ec] px-3 py-2.5 no-underline transition-colors hover:border-linha2 hover:bg-[#f8faf7]">
                <span className={`mono inline-flex h-9 min-w-9 flex-none items-center justify-center rounded-[10px] px-1.5 text-[14px] font-extrabold ${SELO[a.severidade] ?? SELO.atencao}`}>
                  {a.quantidade}
                </span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[14px] font-semibold">{a.titulo}</span>
                  <span className="truncate text-[12.5px] text-suave">{a.detalhe}</span>
                </span>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                     strokeLinecap="round" aria-hidden className="flex-none text-suave"><path d="M9 6l6 6-6 6" /></svg>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
