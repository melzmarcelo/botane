"use client";

import Link from "next/link";

import { reais } from "@/lib/cadastros";
import { inteiro } from "@/lib/numeros";

import type { Painel, Periodo } from "./tipos";

/**
 * "Onde o custo pesa" (barras em duas colunas) e "A casa" (contadores em grade).
 *
 * 🔑 Protótipo aprovado (29/09/2026): "A casa" era uma linha inteira por número — seis linhas
 * para seis contadores. Virou uma grade de caixinhas.
 */
export function OndeOCustoPesa({ pesos, periodo, compras }: {
  pesos: Painel["pesos"]; periodo: Periodo; compras: number;
}) {
  return (
    <section className="cartao p-4" aria-label="onde o custo pesa">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-bold">Onde o custo pesa</h2>
        <Link href="/cmv" className="link-acao text-[13px]">quebra no CMV ›</Link>
      </div>
      {!pesos.length ? (
        <p className="text-[14px] text-suave">
          Ainda não há custo apurado {periodo.termos.neste}. Assim que houver compra e consumo, o peso de
          cada setor aparece aqui.
        </p>
      ) : (
        <ul className="grid gap-x-6 gap-y-2.5 sm:grid-cols-2">
          {pesos.map((g) => (
            <li key={g.grupo}>
              <div className="flex items-baseline justify-between gap-3 text-[13.5px]">
                <span className="truncate font-semibold">{g.grupo}</span>
                <span className="mono text-[12.5px] text-suave">
                  {reais(g.cmv)} · {Math.round(g.participacao_pct)}%
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded bg-superficie2">
                <div className="h-1.5 rounded bg-erva" style={{ width: `${Math.min(100, Math.abs(g.participacao_pct))}%` }} />
              </div>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-[12.5px] text-suave">
        Compras {periodo.termos.do}: <b className="mono">{reais(compras)}</b>
      </p>
    </section>
  );
}

export function ACasa({ o, etiquetasHoje }: { o: Painel["operacao"]; etiquetasHoje: number | null }) {
  const caixas = [
    { rotulo: "produtos", valor: o.produtos, href: "/produtos", pede: false },
    { rotulo: "fichas prontas", valor: o.fichas, href: "/fichas", pede: false },
    { rotulo: "notas a conferir", valor: o.notas_abertas, href: "/compras", pede: true },
    { rotulo: "itens a vincular", valor: o.itens_a_vincular, href: "/compras", pede: true },
    { rotulo: "lotes vencendo em 7 dias", valor: o.vencendo, href: "/alertas", pede: true },
    etiquetasHoje !== null
      ? { rotulo: "etiquetas vencem hoje", valor: etiquetasHoje, href: "/etiquetas/painel?situacao=hoje", pede: true }
      : { rotulo: "abaixo do mínimo", valor: o.abaixo_minimo, href: "/alertas", pede: true },
  ];
  return (
    <section className="cartao p-4" aria-label="a casa">
      <h2 className="mb-3 text-[15px] font-bold">A casa</h2>
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
        {caixas.map((c) => (
          <Link key={c.rotulo} href={c.href} className="rounded-lg bg-superficie2 px-3 py-2.5 no-underline hover:ring-1 hover:ring-erva">
            <b className={`mono block text-[18px] ${c.valor === 0 ? "font-medium text-suave"
              : c.pede ? "text-alerta" : ""}`}>{inteiro(c.valor)}</b>
            <span className="text-[12px] leading-tight text-suave">{c.rotulo}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
