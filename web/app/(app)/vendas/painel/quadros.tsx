"use client";

import LinkProduto from "@/components/link-produto";
import { Cartao, Vazio } from "@/components/ui";
import { inteiro, pct, plural, qtd, reais } from "@/lib/numeros";
import type { Ordem, PainelVendas } from "@/lib/vendas-painel";

import { BarrasDeitadas, eixoReais, GraficoBarras } from "./graficos";
import { dataBr, rotuloDoPonto, tituloDoPonto } from "./periodo";

function Variacao({ v, rotulo }: { v: number | null; rotulo: string }) {
  if (v === null) return <span>sem base para comparar</span>;
  return (
    <span className={v >= 0 ? "text-erva" : "text-alerta"}>
      {v >= 0 ? "+" : ""}{v.toLocaleString("pt-BR")}% sobre {rotulo}
    </span>
  );
}

function Numero({ rotulo, valor, sub }: { rotulo: string; valor: string; sub?: React.ReactNode }) {
  return (
    <div className="min-w-0" data-numero-painel={rotulo}>
      <p className="rotulo">{rotulo}</p>
      <p className="mono mt-1 text-[22px] font-bold leading-none">{valor}</p>
      {sub && <p className="mt-1 text-[12.5px] leading-snug text-suave">{sub}</p>}
    </div>
  );
}

/** Os números do recorte, cada um com a variação sobre o período anterior. */
export function Resumo({ p }: { p: PainelVendas }) {
  const t = p.totais;
  const c = p.comparacao;
  const sobre = `${c.rotulo} (${dataBr(c.inicio)}${c.inicio !== c.fim ? ` a ${dataBr(c.fim)}` : ""})`;
  return (
    <Cartao>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5" id="painel-vendas-resumo">
        <Numero rotulo={p.bruta ? "Receita do recorte" : "Faturado"} valor={reais(t.receita)}
                sub={<Variacao v={c.pct_receita} rotulo="o anterior" />} />
        <Numero rotulo="Cupons" valor={inteiro(t.cupons)}
                sub={<Variacao v={c.pct_cupons} rotulo="o anterior" />} />
        <Numero rotulo="Ticket médio" valor={reais(t.ticket_medio)}
                sub={<Variacao v={c.pct_ticket} rotulo="o anterior" />} />
        <Numero rotulo="Itens vendidos" valor={qtd(t.itens)}
                sub={t.cupons ? `${(t.itens / t.cupons).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} por cupom` : undefined} />
        {/* ⚠️ Num dia só, a média por dia repetia o faturado (auditoria de 29/10/2026):
            ali o cartão mostra o mesmo dia da semana passada, que é a régua do dia. */}
        {p.inicio === p.fim ? (
          <Numero rotulo="Mesmo dia, semana passada" valor={reais(c.receita)}
                  sub={`${dataBr(c.inicio)} · ${plural(c.cupons, "cupom", "cupons")}`} />
        ) : (
          <Numero rotulo="Média por dia" valor={reais(t.media_por_dia)}
                  sub={`${plural(t.dias, "dia", "dias")} com venda`} />
        )}
      </div>
      <p className="mt-3 border-t border-dashed border-linha pt-2.5 text-[12.5px] text-suave">
        Comparado com {sobre}: {reais(c.receita)} em {plural(c.cupons, "cupom", "cupons")}.
        {t.desconto !== null && t.desconto > 0 && <> Descontos dos cupons: {reais(t.desconto)} (já tirados do faturado).</>}
        {p.canceladas && p.canceladas.cupons > 0 && (
          <> {plural(p.canceladas.cupons, "cupom cancelado", "cupons cancelados")} no PDV, somando {reais(p.canceladas.valor)} — fora das somas.</>
        )}
        {/* ⚠️ Com recorte, a receita é a BRUTA dos itens escolhidos: o desconto é do
            cupom inteiro, e repartir entre os itens seria inventar. */}
        {p.bruta && <> Com recorte, a receita é a dos itens escolhidos, sem o desconto do cupom.</>}
      </p>
    </Cartao>
  );
}

export function Evolucao({ p }: { p: PainelVendas }) {
  return (
    <Cartao>
      <h2 className="mb-2 text-[15px] font-bold">Evolução do faturado</h2>
      <GraficoBarras
        altura={240}
        rotulo={`faturado por ${p.agrupar}, de ${dataBr(p.inicio)} a ${dataBr(p.fim)}`}
        noEixo={eixoReais}
        barras={p.serie.map((s) => ({
          chave: s.periodo,
          rotulo: rotuloDoPonto(p.agrupar, s.periodo),
          titulo: tituloDoPonto(p.agrupar, s.periodo),
          valor: s.receita,
          dica: [
            { rotulo: "faturado", valor: reais(s.receita) },
            { rotulo: "cupons", valor: inteiro(s.cupons) },
            { rotulo: "ticket", valor: reais(s.ticket_medio) },
          ],
        }))}
      />
    </Cartao>
  );
}

export function DiaDaSemana({ p }: { p: PainelVendas }) {
  // Segunda primeiro, como a casa conta a semana.
  const ordem = [...p.por_dia_semana].sort((a, b) => ((a.dia_semana + 6) % 7) - ((b.dia_semana + 6) % 7));
  return (
    <Cartao>
      <h2 className="text-[15px] font-bold">Por dia da semana</h2>
      {/* ⚠️ MÉDIA por dia, não soma: um mês com cinco sábados não faz o sábado melhor. */}
      <p className="mb-2 text-[12.5px] text-suave">faturado médio por dia que teve venda</p>
      <GraficoBarras
        altura={220}
        W={540}
        rotulo="faturado médio por dia da semana"
        noEixo={eixoReais}
        barras={ordem.map((d) => ({
          chave: String(d.dia_semana),
          rotulo: d.nome.slice(0, 3),
          titulo: d.nome,
          valor: d.media_receita,
          dica: [
            { rotulo: "média", valor: reais(d.media_receita) },
            { rotulo: "cupons por dia", valor: d.media_cupons.toLocaleString("pt-BR", { maximumFractionDigits: 1 }) },
            { rotulo: "dias", valor: inteiro(d.dias) },
          ],
        }))}
      />
    </Cartao>
  );
}

export function PorHora({ p, largo }: { p: PainelVendas; largo?: boolean }) {
  return (
    <Cartao>
      <h2 className="text-[15px] font-bold">Por hora do cupom</h2>
      <p className="mb-2 text-[12.5px] text-suave">faturado somado em cada hora</p>
      {p.por_hora.length ? (
        <GraficoBarras
          altura={largo ? 240 : 220}
          W={largo ? 1080 : 540}
          rotulo="faturado por hora do cupom"
          noEixo={eixoReais}
          barras={p.por_hora.map((h) => ({
            chave: String(h.hora),
            rotulo: `${h.hora}h`,
            titulo: `das ${h.hora}h às ${h.hora + 1}h`,
            valor: h.receita,
            dica: [
              { rotulo: "faturado", valor: reais(h.receita) },
              { rotulo: "cupons", valor: inteiro(h.cupons) },
            ],
          }))}
        />
      ) : (
        <Vazio>Nenhum cupom com hora no recorte.</Vazio>
      )}
      {/* ⚠️ Venda digitada não tem hora — contada à parte, nunca na meia-noite. */}
      {p.sem_hora && (
        <p className="mt-2 text-[12.5px] text-suave">
          {plural(p.sem_hora.cupons, "cupom", "cupons")} sem hora (lançados à mão), somando {reais(p.sem_hora.receita)}.
        </p>
      )}
    </Cartao>
  );
}

export function Grupos({ titulo, linhas, ativo, aoClicar }: {
  titulo: string;
  linhas: PainelVendas["por_categoria"];
  ativo: number | null;
  aoClicar: (id: number | null) => void;
}) {
  return (
    <Cartao>
      <h2 className="text-[15px] font-bold">{titulo}</h2>
      {/* ⚠️ O desconto é do CUPOM inteiro: repartir entre categorias seria inventar. Por isso
          a soma do quadro passa do Faturado, e o quadro diz que é o valor bruto (auditoria de 29/10/2026). */}
      <p className="mb-2 text-[12.5px] text-suave">valor dos itens, antes do desconto do cupom · clique num grupo para filtrar o painel por ele</p>
      {linhas.length ? (
        <BarrasDeitadas
          ativo={ativo}
          aoClicar={aoClicar}
          valor={reais}
          linhas={linhas.slice(0, 12).map((g) => ({
            chave: String(g.id ?? "sem"), id: g.id, nome: g.nome, valor: g.receita,
            detalhe: `${pct(g.participacao_pct)} · ${qtd(g.quantidade)} ${Number(g.quantidade) === 1 ? "item" : "itens"} · ${plural(g.cupons, "cupom", "cupons")}`,
          }))}
        />
      ) : (
        <Vazio>Nada vendido no recorte.</Vazio>
      )}
      {linhas.length > 12 && (
        <p className="mt-2 text-[12.5px] text-suave">e mais {linhas.length - 12} — todos vão no relatório.</p>
      )}
    </Cartao>
  );
}

export function Produtos({ p, ordem, aoOrdenar, limite, aoLimitar }: {
  p: PainelVendas;
  ordem: Ordem;
  aoOrdenar: (o: Ordem) => void;
  limite: number;
  aoLimitar: (n: number) => void;
}) {
  return (
    <Cartao>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[15px] font-bold">Mais vendidos</h2>
        <div className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-suave">por</span>
          {(["receita", "quantidade"] as Ordem[]).map((o) => (
            <button key={o} type="button" data-ordem={o}
                    className={`btn ${ordem === o ? "btn-primario" : "btn-secundario"} px-3 py-1`}
                    onClick={() => aoOrdenar(o)}>
              {o === "receita" ? "faturado" : "quantidade"}
            </button>
          ))}
          <select className="campo py-1" style={{ width: "auto" }} aria-label="quantos produtos mostrar" id="painel-vendas-limite"
                  value={limite} onChange={(e) => aoLimitar(Number(e.target.value))}>
            {[10, 20, 50, 100].map((n) => <option key={n} value={n}>{n} primeiros</option>)}
          </select>
        </div>
      </div>
      {p.produtos.length ? (
        <div className="overflow-x-auto">
          <table className="tabela w-full text-[13.5px]" id="painel-vendas-produtos">
            <thead>
              <tr>
                <th className="w-8 text-right">#</th>
                <th className="text-left">Produto</th>
                <th className="text-left">Categoria</th>
                <th className="text-right">Qtd</th>
                <th className="text-right">Cupons</th>
                <th className="text-right">Faturado</th>
                <th className="text-right">Preço médio</th>
                <th className="text-right">Part.</th>
              </tr>
            </thead>
            <tbody>
              {p.produtos.map((l, i) => (
                <tr key={`${l.id_produto ?? "x"}-${l.codigo ?? i}`}>
                  <td className="mono text-right text-suave">{i + 1}</td>
                  <td className="max-w-[18rem]">
                    {l.id_produto ? (
                      <LinkProduto id={l.id_produto}>{l.produto_curto || l.produto}</LinkProduto>
                    ) : (
                      <span title="item do PDV sem produto vinculado">{l.produto} <span className="text-suave">(sem vínculo)</span></span>
                    )}
                  </td>
                  <td className="text-suave">{l.categoria ?? "—"}</td>
                  <td className="mono text-right">{qtd(l.quantidade)}</td>
                  <td className="mono text-right">{inteiro(l.cupons)}</td>
                  <td className="mono text-right">{reais(l.receita)}</td>
                  <td className="mono text-right">{reais(l.preco_medio)}</td>
                  <td className="mono text-right">{pct(l.participacao_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Vazio>Nenhum produto vendido no recorte.</Vazio>
      )}
      {p.produtos_total > p.produtos.length && (
        <p className="mt-2 text-[12.5px] text-suave">
          Mostrando {p.produtos.length} de {inteiro(p.produtos_total)} produtos — o relatório leva todos.
          {" "}Faturado por produto é o dos itens, antes do desconto do cupom.
        </p>
      )}
    </Cartao>
  );
}
