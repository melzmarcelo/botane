"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { type Barra, eixoReais, GraficoBarras } from "@/app/(app)/vendas/painel/graficos";
import { reais } from "@/lib/cadastros";
import { inteiro } from "@/lib/numeros";
import { pedirPainel, type PainelVendas } from "@/lib/vendas-painel";

/**
 * 🔑 **Faturamento por dia e Mais vendidos** (layout novo — protótipo aprovado em 05/11/2026,
 * `apresentacao/novo-layout/`): os dois quadros de baixo do Início no protótipo. Vêm do mesmo
 * painel de vendas (`/vendas/painel`), terminando no dia da faixa (o da última venda).
 * ⚠️ Só para quem vê dinheiro: o Início passa `fim` nulo para quem não vê, e nada é pedido.
 */
const PERIODOS = [7, 14, 30] as const;

function menosDias(iso: string, n: number) {
  const [a, m, d] = iso.split("-").map(Number);
  const dt = new Date(a, m - 1, d - n);
  return dt.toLocaleDateString("sv-SE");
}

function useSerie(fim: string, dias: number) {
  const [p, setP] = useState<PainelVendas | null>(null);
  useEffect(() => {
    let vivo = true;
    setP(null);
    pedirPainel({ inicio: menosDias(fim, dias - 1), fim, agrupar: "dia", limite: 1 })
      .then((r) => vivo && setP(r)).catch(() => {});
    return () => { vivo = false; };
  }, [fim, dias]);
  return p;
}

function useMaisVendidos(fim: string) {
  const [p, setP] = useState<PainelVendas | null>(null);
  useEffect(() => {
    let vivo = true;
    pedirPainel({ inicio: fim, fim, limite: 5 }).then((r) => vivo && setP(r)).catch(() => {});
    return () => { vivo = false; };
  }, [fim]);
  return p;
}

export function FaturamentoPorDia({ fim }: { fim: string }) {
  const [dias, setDias] = useState<(typeof PERIODOS)[number]>(14);
  const p = useSerie(fim, dias);
  const porDia = new Map((p?.serie ?? []).map((s) => [s.periodo.slice(0, 10), s]));
  const barras: Barra[] = Array.from({ length: dias }, (_, i) => {
    const d = menosDias(fim, dias - 1 - i);
    const s = porDia.get(d);
    const rotulo = `${d.slice(8, 10)}/${d.slice(5, 7)}`;
    return {
      chave: d, rotulo, valor: s?.receita ?? 0, titulo: rotulo,
      dica: [{ rotulo: "Faturado", valor: reais(s?.receita ?? 0) }, { rotulo: "Vendas", valor: inteiro(s?.cupons ?? 0) }],
    };
  });
  return (
    <section className="cartao min-w-0 p-5" id="inicio-faturamento-dias">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[16px] font-bold">Faturamento por dia</h2>
          <p className="text-[12.5px] text-suave">Últimos {dias} dias até {fim.slice(8, 10)}/{fim.slice(5, 7)} · passe o cursor sobre a barra</p>
        </div>
        <div className="seg-grade" role="group" aria-label="Período do gráfico">
          {PERIODOS.map((n) => (
            <button key={n} type="button" aria-pressed={dias === n} onClick={() => setDias(n)}>{n} dias</button>
          ))}
        </div>
      </div>
      {!p ? <div className="h-[220px] animate-pulse rounded-xl bg-superficie2" />
        : <GraficoBarras barras={barras} altura={230} W={720} noEixo={eixoReais} maxRotulos={dias > 14 ? 10 : 7}
                         rotulo={`Faturamento por dia, últimos ${dias} dias`}
                         aoClicar={(b) => { window.location.href = `/vendas/painel?modo=dia&de=${b.chave}&ate=${b.chave}`; }} />}
    </section>
  );
}

export function MaisVendidos({ fim }: { fim: string }) {
  const mais = useMaisVendidos(fim);
  return (
    <section className="cartao min-w-0 p-5" id="inicio-mais-vendidos">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-[16px] font-bold">Mais vendidos no dia</h2>
        <Link href={`/vendas/painel?modo=dia&de=${fim}&ate=${fim}`} className="btn btn-terciario btn-pequeno">Ver no painel</Link>
      </div>
      {!mais ? <div className="h-[180px] animate-pulse rounded-xl bg-superficie2" />
        : !mais.produtos.length ? <p className="py-6 text-[14px] text-suave">Nenhuma venda neste dia.</p> : (
          <div className="overflow-x-auto">
            <table className="tabela tabela-compacta">
              <thead><tr><th>Produto</th><th>Categoria</th><th className="num">Quantidade</th><th className="num">Faturamento</th></tr></thead>
              <tbody>
                {mais.produtos.map((x) => (
                  <tr key={`${x.id_produto}-${x.produto}`}>
                    <td className="font-semibold">{x.produto_curto || x.produto}</td>
                    <td className="text-suave">{x.categoria ?? "—"}</td>
                    <td className="num mono">{inteiro(x.quantidade)}</td>
                    <td className="num mono">{reais(x.receita)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </section>
  );
}

type Atalho = { href: string; rotulo: string; d: string; pode: boolean };

/** Os atalhos do protótipo, cada um só para quem pode usar a tela. */
export function Atalhos({ pode }: { pode: (k: string) => boolean }) {
  const lista: Atalho[] = ([
    { href: "/compras", rotulo: "Lançar nota", d: "M3 6h11v10H3z M14 10h4l3 3v3h-7 M7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4 M17 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4", pode: pode("compras.notas") },
    { href: "/producao", rotulo: "Registrar produção", d: "M12 3c1 3 4 4.5 4 8a4 4 0 0 1-8 0c0-1.5.7-2.5 1.5-3.3C10 9.5 11 8 12 3z M8 21h8", pode: pode("producao.agenda") || pode("estoque.saidas") },
    { href: "/produtos/novo", rotulo: "Novo produto", d: "M4 5h16 M4 12h16 M4 19h10", pode: pode("cadastros.produtos") },
    { href: "/inventario", rotulo: "Inventário", d: "M21 8 12 3 3 8v8l9 5 9-5z M3 8l9 5 9-5 M12 13v8", pode: pode("estoque.inventario") },
    { href: "/relatorios", rotulo: "Relatórios", d: "M6 3h9l4 4v14H6z M14 3v5h5 M9 13h6 M9 17h6", pode: true },
    { href: "/bi", rotulo: "Nova análise", d: "M4 20V10 M10 20V4 M16 20v-7 M22 20H2", pode: pode("bi.estudio") },
  ] as Atalho[]).filter((a) => a.pode).slice(0, 4);
  if (!lista.length) return null;
  return (
    <section className="cartao p-5" id="inicio-atalhos">
      <h2 className="mb-3.5 text-[16px] font-bold">Atalhos</h2>
      <div className="grid grid-cols-2 gap-2.5">
        {lista.map((a) => (
          <Link key={a.href} href={a.href} className="btn btn-secundario min-h-[52px] justify-start text-left leading-tight">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9"
                 strokeLinecap="round" strokeLinejoin="round" aria-hidden className="shrink-0 text-erva"><path d={a.d} /></svg>
            <span>{a.rotulo}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
