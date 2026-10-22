"use client";

import Link from "next/link";

import LinkProduto from "@/components/link-produto";
import { Cartao, Etiqueta, Vazio } from "@/components/ui";
import { inteiro, pct, qtd, reais } from "@/lib/numeros";
import { listaAbaixo, listaNegativos, type VisaoGeral } from "@/lib/estoque-painel";

import { BarrasDeitadas } from "../../vendas/painel/graficos";
import { dataBr } from "../../vendas/painel/periodo";

/**
 * A visão geral: os números que pedem decisão, e cada um leva para onde se age.
 *
 * 🔑 **O cartão leva à LISTAGEM** (pedido do dono: "que ao clicar, vá para a listagem para
 * poder tomar a melhor decisão"): negativos e abaixo do mínimo abrem Saldos já filtrado, e
 * o número do cartão é o tamanho daquela lista. Abaixo de cada cartão ficam os mais
 * urgentes, com o que ajuda a decidir — quanto falta, em quantos dias acaba, de quem comprar.
 */

function Indicador({ rotulo, valor, sub, href, aoClicar, tom, id }: {
  rotulo: string;
  valor: string;
  sub?: React.ReactNode;
  href?: string;
  aoClicar?: () => void;
  tom?: "alerta" | "erva" | "neutro";
  id: string;
}) {
  const cor = tom === "alerta" ? "border-alerta/50" : tom === "erva" ? "border-erva/40" : "border-linha";
  const corpo = (
    <>
      <p className="rotulo">{rotulo}</p>
      <p className={`mono mt-1 text-[22px] font-bold leading-none ${tom === "alerta" ? "text-alerta" : ""}`}>
        {valor}
      </p>
      {sub && <p className="mt-1 text-[12.5px] leading-snug text-suave">{sub}</p>}
      {(href || aoClicar) && <p className="mt-2 text-[12.5px] font-semibold text-erva">ver a lista →</p>}
    </>
  );
  const classe = `block min-w-0 rounded-lg border ${cor} bg-superficie p-3 text-left`;
  if (href) {
    return <Link href={href} className={`${classe} hover:bg-linha/30`} data-indicador={id}>{corpo}</Link>;
  }
  if (aoClicar) {
    return (
      <button type="button" className={`${classe} hover:bg-linha/30`} onClick={aoClicar} data-indicador={id}>
        {corpo}
      </button>
    );
  }
  return <div className={classe} data-indicador={id}>{corpo}</div>;
}

const dias = (n: number | null) =>
  n === null ? "—" : n < 1 ? "menos de 1 dia" : `${n.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} dia(s)`;

export default function Geral({ g, aoVerPerdas, aoVerProduto }: {
  g: VisaoGeral;
  aoVerPerdas: () => void;
  aoVerProduto: (id: number) => void;
}) {
  const neg = g.negativos;
  const ab = g.abaixo_do_minimo;
  const pm = g.perdas_mes;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6" id="painel-estoque-indicadores">
        <Indicador id="valor" rotulo="Valor em estoque" valor={reais(g.valor_estoque)}
                   sub={<>{inteiro(g.produtos_com_saldo)} produto(s) com saldo
                     {g.valor_inativos > 0 && <> · {reais(g.valor_inativos)} em produtos inativos</>}</>} />
        <Indicador id="negativos" rotulo="Saldo negativo" valor={inteiro(neg.prateleiras)}
                   tom={neg.prateleiras ? "alerta" : "erva"} href={neg.prateleiras ? listaNegativos : undefined}
                   sub={neg.prateleiras ? `prateleira(s), em ${inteiro(neg.produtos)} produto(s)` : "nenhuma prateleira"} />
        <Indicador id="minimo" rotulo="Abaixo do mínimo" valor={inteiro(ab.produtos)}
                   tom={ab.produtos ? "alerta" : "erva"} href={ab.produtos ? listaAbaixo : undefined}
                   sub={ab.produtos ? `repor custa cerca de ${reais(ab.valor_repor)}` : "nenhum produto"} />
        <Indicador id="parados" rotulo={`Parado há ${g.parados.dias} dias`} valor={reais(g.parados.valor)}
                   sub={`${inteiro(g.parados.produtos)} produto(s) com saldo e sem saída`} />
        <Indicador id="validade" rotulo="Validade" valor={inteiro(g.validade.vencidos)}
                   tom={g.validade.vencidos ? "alerta" : "neutro"} href="/alertas"
                   sub={<>lote(s) vencido(s) ({reais(g.validade.valor_vencidos)}); {inteiro(g.validade.vencendo)} vence(m) em {g.validade.dias} dias</>} />
        <Indicador id="perdas" rotulo="Perdas no mês" valor={reais(pm.valor)} aoClicar={aoVerPerdas}
                   tom={pm.valor ? "alerta" : "neutro"}
                   sub={<>
                     {inteiro(pm.ocorrencias)} registro(s)
                     {pm.pct_variacao !== null && (
                       <> · <span className={pm.pct_variacao > 0 ? "text-alerta" : "text-erva"}>
                         {pm.pct_variacao > 0 ? "+" : ""}{pm.pct_variacao.toLocaleString("pt-BR")}%
                       </span> sobre os dias anteriores</>
                     )}
                   </>} />
      </div>

      {/* 🔑 O que acaba primeiro vem primeiro: a menor cobertura em dias. */}
      <Cartao>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-[15px] font-bold">Abaixo do mínimo — o que acaba primeiro</h2>
          {ab.produtos > 0 && (
            <Link href={listaAbaixo} className="link-acao text-[13px]">
              ver os {inteiro(ab.produtos)} na lista de saldos →
            </Link>
          )}
        </div>
        {ab.lista.length ? (
          <div className="overflow-x-auto">
            <table className="tabela w-full text-[13.5px]" id="painel-estoque-abaixo">
              <thead>
                <tr>
                  <th className="text-left">Produto</th>
                  <th className="text-right">Saldo</th>
                  <th className="text-right">Mínimo</th>
                  <th className="text-right">Faltam</th>
                  <th className="text-right" title="consumo médio dos últimos 30 dias">Consumo/dia</th>
                  <th className="text-right" title="saldo ÷ consumo por dia">Acaba em</th>
                  <th className="text-right">Repor</th>
                  <th className="text-left">De quem</th>
                </tr>
              </thead>
              <tbody>
                {ab.lista.map((a) => (
                  <tr key={a.id_produto}>
                    <td className="max-w-[16rem]">
                      <button type="button" className="link-registro text-left" title="ver o andamento deste produto"
                              onClick={() => aoVerProduto(a.id_produto)}>{a.produto}</button>
                    </td>
                    <td className={`mono text-right ${a.saldo < 0 ? "text-alerta" : ""}`}>{qtd(a.saldo)} {a.um_estoque}</td>
                    <td className="mono text-right">{qtd(a.estoque_minimo)}</td>
                    <td className="mono text-right">{qtd(a.faltam)}</td>
                    <td className="mono text-right">{a.consumo_dia === null ? "—" : qtd(a.consumo_dia)}</td>
                    <td className={`mono text-right ${a.cobertura_dias !== null && a.cobertura_dias < 3 ? "font-bold text-alerta" : ""}`}>
                      {a.cobertura_dias === null ? "sem consumo" : dias(a.cobertura_dias)}
                    </td>
                    <td className="mono text-right">{a.valor_repor === null ? "—" : reais(a.valor_repor)}</td>
                    <td className="text-suave">
                      {a.acao === "produzir"
                        ? <Etiqueta>a casa produz</Etiqueta>
                        : a.fornecedor ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Vazio>Nenhum produto abaixo do mínimo. Os que têm mínimo cadastrado estão cobertos.</Vazio>
        )}
      </Cartao>

      <div className="grid gap-4 lg:grid-cols-2">
        <Cartao>
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[15px] font-bold">Saldo negativo</h2>
            {neg.prateleiras > 0 && (
              <Link href={listaNegativos} className="link-acao text-[13px]">ver todas na lista →</Link>
            )}
          </div>
          {/* ⚠️ Negativo é dívida, não mercadoria: saiu mais do que entrou. O conserto é
              lançar a entrada que faltou (a nota) ou contar a prateleira. */}
          <p className="mb-2 text-[12.5px] text-suave">
            Saiu mais do que entrou: falta lançar uma entrada (a nota) ou contar a prateleira.
          </p>
          {neg.lista.length ? (
            <ul className="divide-y divide-linha text-[13.5px]" id="painel-estoque-negativos">
              {neg.lista.map((n) => (
                <li key={`${n.id_produto}-${n.id_local}`} className="flex items-baseline justify-between gap-3 py-1.5">
                  <span className="min-w-0">
                    <button type="button" className="link-registro text-left" onClick={() => aoVerProduto(n.id_produto)}>
                      {n.produto}
                    </button>
                    <span className="block text-[12px] text-suave">
                      {n.local}{n.ultimo_movimento && <> · último movimento {dataBr(n.ultimo_movimento.slice(0, 10))}</>}
                    </span>
                  </span>
                  <span className="mono shrink-0 text-alerta">{qtd(n.quantidade)} {n.um_estoque}</span>
                </li>
              ))}
            </ul>
          ) : (
            <Vazio>Nenhuma prateleira negativa.</Vazio>
          )}
        </Cartao>

        <Cartao>
          <h2 className="text-[15px] font-bold">Onde está o dinheiro</h2>
          <p className="mb-2 text-[12.5px] text-suave">o valor em estoque por categoria do produto</p>
          {g.por_categoria.length ? (
            <BarrasDeitadas
              valor={reais}
              linhas={g.por_categoria.slice(0, 10).map((c) => ({
                // ⚠️ "Sem categoria" e "Produtos inativos" têm os dois id nulo: o nome desempata.
                chave: `${c.id ?? "sem"}-${c.nome}`, id: null, nome: c.nome, valor: c.valor,
                detalhe: `${pct(c.participacao_pct)} · ${inteiro(c.produtos)} produto(s)`,
              }))}
            />
          ) : (
            <Vazio>Nada em estoque.</Vazio>
          )}
        </Cartao>
      </div>

      <Cartao>
        <h2 className="text-[15px] font-bold">Parado há mais de {g.parados.dias} dias</h2>
        {/* 🔑 Dinheiro que não gira: tem saldo e não saiu nem em venda, nem em produção,
            nem em perda. Ou se usa, ou se para de comprar. */}
        <p className="mb-2 text-[12.5px] text-suave">
          Tem saldo e não teve venda, produção, consumo nem perda no período: ou se usa, ou se para de comprar.
        </p>
        {g.parados.lista.length ? (
          <div className="overflow-x-auto">
            <table className="tabela w-full text-[13.5px]" id="painel-estoque-parados">
              <thead>
                <tr>
                  <th className="text-left">Produto</th>
                  <th className="text-right">Saldo</th>
                  <th className="text-right">Valor</th>
                  <th className="text-left">Última saída</th>
                </tr>
              </thead>
              <tbody>
                {g.parados.lista.map((p) => (
                  <tr key={p.id_produto}>
                    <td><LinkProduto id={p.id_produto}>{p.produto}</LinkProduto></td>
                    <td className="mono text-right">{qtd(p.quantidade)} {p.um_estoque}</td>
                    <td className="mono text-right">{reais(p.valor)}</td>
                    <td className="text-suave">{p.ultima_saida ? dataBr(p.ultima_saida.slice(0, 10)) : "nunca saiu"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {g.parados.produtos > g.parados.lista.length && (
              <p className="mt-2 text-[12.5px] text-suave">
                Os {g.parados.lista.length} de maior valor, de {inteiro(g.parados.produtos)}.
              </p>
            )}
          </div>
        ) : (
          <Vazio>Nada parado: tudo o que tem saldo saiu nos últimos {g.parados.dias} dias.</Vazio>
        )}
      </Cartao>
    </div>
  );
}
