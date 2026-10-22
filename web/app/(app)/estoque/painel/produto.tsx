"use client";

import Link from "next/link";

import LinkProduto from "@/components/link-produto";
import { Cartao, Etiqueta, Vazio } from "@/components/ui";
import { inteiro, pct, qtd, reais } from "@/lib/numeros";
import type { PainelProduto } from "@/lib/estoque-painel";

import { dataBr, rotuloDoPonto, tituloDoPonto } from "../../vendas/painel/periodo";
import { GraficoFluxo, GraficoSaldo, type Ponto } from "./graficos";

/**
 * Como anda o estoque de UM produto: o saldo no tempo, o que entrou e saiu, e os números
 * que respondem "preciso comprar?" — consumo por dia, em quantos dias acaba, quanto se perde.
 */

const eixo = (v: number) =>
  Math.abs(v) >= 1000 ? `${(v / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} mil`
                      : v.toLocaleString("pt-BR", { maximumFractionDigits: 1 });

function Numero({ rotulo, valor, sub, tom }: {
  rotulo: string; valor: string; sub?: React.ReactNode; tom?: "alerta";
}) {
  return (
    <div className="min-w-0" data-numero-produto={rotulo}>
      <p className="rotulo">{rotulo}</p>
      <p className={`mono mt-1 text-[20px] font-bold leading-none ${tom === "alerta" ? "text-alerta" : ""}`}>{valor}</p>
      {sub && <p className="mt-1 text-[12.5px] leading-snug text-suave">{sub}</p>}
    </div>
  );
}

export default function Produto({ d }: { d: PainelProduto }) {
  const p = d.produto;
  const um = p.um_estoque ?? "";
  const ind = d.indicadores;
  const pontos: Ponto[] = d.serie.map((s) => ({
    chave: s.periodo,
    rotulo: rotuloDoPonto(d.agrupar, s.periodo),
    titulo: tituloDoPonto(d.agrupar, s.periodo),
    dica: [
      { rotulo: "saldo ao fim", valor: `${qtd(s.saldo)} ${um}` },
      { rotulo: "entrou", valor: `${qtd(s.entradas)} (${reais(s.valor_entradas)})` },
      { rotulo: "saiu", valor: `${qtd(s.saidas)} (${reais(s.valor_saidas)})` },
      ...(s.custo_medio !== null ? [{ rotulo: "custo médio", valor: reais(s.custo_medio) }] : []),
    ],
  }));
  const razao = `/estoque?aba=movimentos&id_produto=${p.id}&produto=${encodeURIComponent(p.nome)}`;

  return (
    <div className="space-y-4">
      <Cartao>
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h2 className="text-[17px] font-bold">
              <LinkProduto id={p.id}>{p.nome}</LinkProduto>
              {!p.ativo && <> <Etiqueta>inativo</Etiqueta></>}
              {p.status === "RASCUNHO" && <> <Etiqueta cor="alerta">rascunho</Etiqueta></>}
            </h2>
            <p className="text-[12.5px] text-suave">
              {[p.codigo, p.categoria, p.setor, um && `em ${um}`].filter(Boolean).join(" · ")}
              {!p.controla_estoque && " · não controla estoque"}
            </p>
          </div>
          <Link href={razao} className="link-acao text-[13px]">ver no razão →</Link>
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6" id="painel-produto-numeros">
          <Numero rotulo="Saldo hoje" valor={`${qtd(d.atual.saldo)} ${um}`}
                  tom={d.atual.saldo < 0 || d.atual.abaixo_do_minimo ? "alerta" : undefined}
                  sub={p.estoque_minimo !== null
                    ? <>mínimo {qtd(p.estoque_minimo)}{d.atual.abaixo_do_minimo && <> · <b className="text-alerta">abaixo</b></>}</>
                    : "sem mínimo cadastrado"} />
          <Numero rotulo="Valor" valor={reais(d.atual.valor)}
                  sub={d.atual.custo_medio !== null ? `custo médio ${reais(d.atual.custo_medio)}` : "sem custo"} />
          <Numero rotulo="Consumo por dia" valor={ind.consumo_dia === null ? "—" : `${qtd(ind.consumo_dia)} ${um}`}
                  sub={`${qtd(ind.consumo)} ${um} em ${inteiro(d.dias)} dia(s)`} />
          <Numero rotulo="Acaba em" valor={ind.cobertura_dias === null ? "—" : `${ind.cobertura_dias.toLocaleString("pt-BR")} dia(s)`}
                  tom={ind.cobertura_dias !== null && ind.cobertura_dias < 3 ? "alerta" : undefined}
                  sub={ind.cobertura_dias === null ? "sem consumo no período" : "no ritmo do período"} />
          <Numero rotulo="Comprado" valor={`${qtd(ind.compras)} ${um}`} sub={reais(ind.compras_valor)} />
          <Numero rotulo="Perdido" valor={`${qtd(ind.perda)} ${um}`}
                  tom={ind.perda > 0 ? "alerta" : undefined}
                  sub={ind.perda > 0
                    ? <>{reais(ind.perda_valor)}{ind.perda_pct_do_consumo !== null && <> · {pct(ind.perda_pct_do_consumo)} do que saiu</>}</>
                    : "nenhuma perda"} />
        </div>
        {ind.ultima_entrada && (
          <p className="mt-3 border-t border-dashed border-linha pt-2.5 text-[12.5px] text-suave">
            Última entrada: {ind.ultima_entrada.rotulo.toLowerCase()} em {dataBr(ind.ultima_entrada.data_movimento.slice(0, 10))},
            {" "}{qtd(ind.ultima_entrada.quantidade)} {um} a {reais(ind.ultima_entrada.custo_unitario)}
            {ind.ultima_entrada.documento && <> (documento {ind.ultima_entrada.documento})</>}.
          </p>
        )}
      </Cartao>

      <Cartao>
        <h2 className="text-[15px] font-bold">Saldo no período</h2>
        <p className="mb-2 text-[12.5px] text-suave">
          o saldo ao fim de cada {d.agrupar === "mes" ? "mês" : d.agrupar}, somando as prateleiras
          {p.estoque_minimo !== null && " — a linha tracejada é o mínimo"}
        </p>
        <GraficoSaldo pontos={pontos} valores={d.serie.map((s) => s.saldo)} minimo={p.estoque_minimo}
                      rotulo={`saldo de ${p.nome} de ${dataBr(d.inicio)} a ${dataBr(d.fim)}`} noEixo={eixo} />
      </Cartao>

      <Cartao>
        <h2 className="text-[15px] font-bold">Entrou e saiu</h2>
        <p className="mb-2 text-[12.5px] text-suave">
          entradas para cima, saídas para baixo, em {um || "unidades"} — o estorno desfaz o movimento que ele corrige
        </p>
        <GraficoFluxo pontos={pontos} entradas={d.serie.map((s) => s.entradas)} saidas={d.serie.map((s) => s.saidas)}
                      rotulo={`entradas e saídas de ${p.nome}`} noEixo={eixo} />
      </Cartao>

      <div className="grid gap-4 lg:grid-cols-2">
        <Cartao>
          <h2 className="mb-2 text-[15px] font-bold">Por tipo de movimento</h2>
          {d.por_tipo.length ? (
            <table className="tabela w-full text-[13.5px]" id="painel-produto-tipos">
              <thead>
                <tr>
                  <th className="text-left">Movimento</th>
                  <th className="text-right">Quantidade</th>
                  <th className="text-right">Valor</th>
                  <th className="text-right">Vezes</th>
                </tr>
              </thead>
              <tbody>
                {d.por_tipo.map((t) => (
                  <tr key={t.tipo}>
                    <td>{t.rotulo}</td>
                    <td className={`mono text-right ${t.entrada ? "text-erva" : ""}`}>{t.entrada ? "+" : "−"}{qtd(t.quantidade)}</td>
                    <td className="mono text-right">{reais(t.valor)}</td>
                    <td className="mono text-right">{inteiro(t.vezes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <Vazio>Nenhum movimento no período.</Vazio>
          )}
          <p className="mt-2 text-[12.5px] text-suave">
            Saldo no início do período: {qtd(ind.saldo_inicial)} {um}. Valores líquidos de estorno.
          </p>
        </Cartao>

        <Cartao>
          <h2 className="mb-2 text-[15px] font-bold">Onde está</h2>
          {d.atual.locais.length ? (
            <ul className="divide-y divide-linha text-[13.5px]">
              {d.atual.locais.map((l) => (
                <li key={l.id_local} className="flex items-baseline justify-between gap-3 py-1.5">
                  <span>{l.local}{l.setor && <span className="text-suave"> · {l.setor}</span>}</span>
                  <span className={`mono ${l.quantidade < 0 ? "text-alerta" : ""}`}>
                    {qtd(l.quantidade)} {um} <span className="text-suave">({reais(l.valor)})</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <Vazio>Este produto não mora em prateleira nenhuma desta loja.</Vazio>
          )}
        </Cartao>
      </div>

      <Cartao>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-[15px] font-bold">Últimos movimentos do período</h2>
          {d.movimentos_no_periodo > d.ultimos.length && (
            <Link href={razao} className="link-acao text-[13px]">
              os {inteiro(d.movimentos_no_periodo)} no razão →
            </Link>
          )}
        </div>
        {d.ultimos.length ? (
          <div className="overflow-x-auto">
            <table className="tabela w-full text-[13.5px]" id="painel-produto-ultimos">
              <thead>
                <tr>
                  <th className="text-left">Quando</th>
                  <th className="text-left">Movimento</th>
                  <th className="text-left">Onde</th>
                  <th className="text-right">Qtd</th>
                  <th className="text-right">Valor</th>
                  <th className="text-right">Saldo depois</th>
                  <th className="text-left">Documento / motivo</th>
                </tr>
              </thead>
              <tbody>
                {d.ultimos.map((m) => (
                  <tr key={m.id}>
                    <td className="mono whitespace-nowrap">{dataBr(m.data_movimento.slice(0, 10))} {m.data_movimento.slice(11, 16)}</td>
                    <td>{m.rotulo}{m.estorno && <> <Etiqueta>estorno</Etiqueta></>}</td>
                    <td className="text-suave">{m.local}</td>
                    <td className={`mono text-right ${m.quantidade > 0 ? "text-erva" : ""}`}>{m.quantidade > 0 ? "+" : ""}{qtd(m.quantidade)}</td>
                    <td className="mono text-right">{reais(m.valor)}</td>
                    <td className="mono text-right">{qtd(m.saldo_apos)}</td>
                    <td className="max-w-[16rem] truncate text-suave" title={m.observacao ?? undefined}>
                      {[m.documento, m.motivo, m.observacao].filter(Boolean).join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Vazio>Nenhum movimento no período.</Vazio>
        )}
      </Cartao>
    </div>
  );
}
