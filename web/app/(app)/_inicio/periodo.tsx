"use client";

import Link from "next/link";

import { reais } from "@/lib/cadastros";
import { pct } from "@/lib/numeros";

import type { Dinheiro, Periodo } from "./tipos";

/**
 * O período até agora: quatro números em colunas, e a confiança dentro do mesmo cartão.
 *
 * 🔑 Protótipo aprovado (29/09/2026). Eram quatro cartões grandes, cada um com uma nota; o
 * número é o mesmo, a explicação virou a linha de baixo.
 * 🔑 **A régua do food cost contra a META da loja** (migração 102): a marca mostra onde a
 * casa quer estar. Sem meta, a régua vem sem marca.
 * ⚠️ Os termos seguem o ritmo da loja ("do mês", "da semana"): numa casa que fecha toda
 * semana, falar em mês é número que ela nunca usou.
 */
function Coluna({ rotulo, valor, sub, tom, href, children }: {
  rotulo: string; valor: string; sub: string; tom?: "alerta" | "erro"; href: string; children?: React.ReactNode;
}) {
  return (
    <Link href={href} className="periodo-coluna group min-w-0 no-underline">
      <p className="rotulo">{rotulo}</p>
      {/* ⚠️ 18px, não 22: "R$ 1.142.446,49" em quatro colunas estourava a coluna (medido na
          foto da tela com a base de desenvolvimento). */}
      <p className={`mono mt-1 whitespace-nowrap text-[18px] font-bold leading-none tracking-tight group-hover:text-erva 2xl:text-[21px] ${
        tom === "alerta" ? "text-alerta" : tom === "erro" ? "text-erro" : ""}`}>{valor}</p>
      <p className="mt-1 text-[12.5px] leading-snug text-suave">{sub}</p>
      {children}
    </Link>
  );
}

export default function PeriodoAteAgora({ d, periodo }: { d: Dinheiro; periodo: Periodo }) {
  const fc = d.food_cost_pct;
  const meta = d.meta_food_cost_pct;
  // A régua vai até 60% (ou até a meta com folga): acima disso a casa tem outra conversa.
  const teto = Math.max(60, (meta ?? 0) * 1.5, fc ?? 0);
  const acimaDaMeta = fc !== null && meta !== null && fc > meta;

  return (
    <section className="cartao p-4" aria-label="período">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-bold">{periodo.rotulo} até agora</h2>
        <Link href="/cmv" className="link-acao text-[13px]">painel de CMV ›</Link>
      </div>
      <div className="periodo-colunas">
        <Coluna rotulo="Custo do que saiu" valor={reais(d.cmv_mes)} href="/cmv"
                sub={`CMV ${periodo.termos.do}`} />
        <Coluna rotulo="Food cost" valor={fc === null ? "—" : pct(fc)} href="/cmv"
                tom={acimaDaMeta ? "alerta" : undefined}
                sub={fc === null
                  ? `sem vendas importadas ${periodo.termos.neste}`
                  : `sobre ${reais(d.receita_mes)} de receita${meta !== null ? ` · meta ${pct(meta)}` : ""}`}>
          {fc !== null && (
            <span className="relative mt-2 block h-1.5 rounded bg-superficie2" aria-hidden="true">
              <i className={`absolute inset-y-0 left-0 rounded ${acimaDaMeta ? "bg-alerta" : "bg-erva"}`}
                 style={{ width: `${Math.min(100, (fc / teto) * 100)}%` }} />
              {meta !== null && (
                <b className="absolute -top-1 h-3.5 w-0.5 bg-tinta" style={{ left: `${(meta / teto) * 100}%` }}
                   title={`meta ${pct(meta)}`} />
              )}
            </span>
          )}
        </Coluna>
        <Coluna rotulo={`Perdas ${periodo.termos.do}`} valor={reais(d.perdas_mes)} href="/estoque"
                tom={d.perdas_mes > 0 ? "alerta" : undefined}
                sub={d.cmv_mes > 0 ? `${pct((d.perdas_mes / d.cmv_mes) * 100)} do custo` : "quebra, validade e cortesia"} />
        <Coluna rotulo="Parado no estoque" valor={reais(d.estoque_agora)} href="/estoque"
                sub={`compras ${periodo.termos.do}: ${reais(d.compras_mes)}`} />
      </div>
      {/* 🔑 A confiança DENTRO do cartão do número: com pouca ficha técnica, a comparação com
          o custo previsto fala do cadastro, não da cozinha. */}
      {d.vendas > 0 && d.cobertura_ficha_pct < 80 && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-alerta-claro px-3 py-2 text-[12.5px] text-suave">
          <span className="mt-1.5 inline-block h-2 w-2 flex-none rounded-full bg-alerta" />
          <span><b className="text-tinta">{pct(d.cobertura_ficha_pct)} das vendas têm ficha técnica</b> — a
            comparação com o custo previsto pelas receitas ainda é parcial.</span>
        </p>
      )}
    </section>
  );
}
