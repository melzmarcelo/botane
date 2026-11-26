"use client";

import Link from "next/link";
import { Fragment } from "react";

import { Cartao, Etiqueta, Vazio } from "@/components/ui";
import type { ItemEntrada, PainelEntradas } from "@/lib/estoque-painel";
import { inteiro, qtd, reais } from "@/lib/numeros";

import { dataBr } from "../../vendas/painel/periodo";

/**
 * Entradas por nota (pedido do dono, 26/11/2026): os itens das notas de entrada do período,
 * divididos pela situação da nota — a conciliar, conciliada, recebida (e quem recebeu) e
 * lançada — com o número da nota de cada um.
 *
 * 🔑 **Duas leituras do mesmo recorte**: por PRODUTO ("o que está entrando, e por qual nota") e
 * por NOTA ("o que veio nesta nota"). Clicar na nota abre a nota; no produto, o andamento dele.
 * 🔑 As abas de situação mostram o total de cada uma no período inteiro (com a busca), e
 * clicar filtra a lista — clicar de novo volta a todas.
 */

export type Leitura = "produto" | "nota";

const COR: Record<string, "erva" | "alerta" | "neutro"> = {
  LANCADA: "erva", RECEBIDA: "erva", CONCILIADA: "alerta", IMPORTADA: "neutro",
};

function Situacao({ i }: { i: ItemEntrada }) {
  const nome = { IMPORTADA: "a conciliar", CONCILIADA: "conciliada", RECEBIDA: "recebida",
                 LANCADA: "lançada" }[i.situacao] ?? i.situacao.toLowerCase();
  return <Etiqueta cor={COR[i.situacao]}>{nome}</Etiqueta>;
}

function Recebido({ i }: { i: ItemEntrada }) {
  return i.recebido_por ? (
    <span data-recebido-por title={i.recebido_em ? `marcada em ${dataBr(i.recebido_em.slice(0, 10))}` : undefined}>
      {i.recebido_por}
    </span>
  ) : <span className="text-suave">—</span>;
}

function nomeDoItem(i: ItemEntrada) {
  return i.produto ?? i.descricao_fornecedor;
}

export default function Entradas({ d, situacao, aoSituacao, leitura, aoLeitura, busca, aoBusca, aoVerProduto }: {
  d: PainelEntradas;
  situacao: string;
  aoSituacao: (s: string) => void;
  leitura: Leitura;
  aoLeitura: (l: Leitura) => void;
  busca: string;
  aoBusca: (b: string) => void;
  aoVerProduto: (id: number) => void;
}) {
  const todas = d.por_situacao.reduce(
    (s, x) => ({ itens: s.itens + x.itens, valor: s.valor + x.valor }), { itens: 0, valor: 0 });

  // Os grupos da leitura escolhida, na ordem em que o servidor mandou (produto, data, nota).
  const grupos = new Map<string, ItemEntrada[]>();
  for (const i of d.itens) {
    const chave = leitura === "produto"
      ? (i.id_produto ? `p${i.id_produto}` : `d${i.descricao_fornecedor}`)
      : `n${i.id_nota}`;
    grupos.set(chave, [...(grupos.get(chave) ?? []), i]);
  }
  const lista = [...grupos.entries()];
  if (leitura === "nota") {
    lista.sort(([, a], [, b]) => (b[0].data ?? "").localeCompare(a[0].data ?? "")
      || a[0].nota.localeCompare(b[0].nota));
  }

  return (
    <div className="space-y-4">
      <Cartao>
        <div className="flex flex-wrap gap-2" id="entradas-situacoes" role="group" aria-label="situação">
          <button type="button" data-situacao=""
                  className={`btn btn-pequeno ${situacao === "" ? "btn-primario" : "btn-secundario"}`}
                  onClick={() => aoSituacao("")}>
            Todas <span className="mono ml-1 opacity-80">{inteiro(todas.itens)}</span>
          </button>
          {d.por_situacao.map((s) => (
            <button key={s.situacao} type="button" data-situacao={s.situacao}
                    className={`btn btn-pequeno ${situacao === s.situacao ? "btn-primario" : "btn-secundario"}`}
                    title={`${inteiro(s.notas)} nota(s) · ${reais(s.valor)}`}
                    onClick={() => aoSituacao(situacao === s.situacao ? "" : s.situacao)}>
              {s.nome} <span className="mono ml-1 opacity-80">{inteiro(s.itens)}</span>
            </button>
          ))}
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <input id="entradas-busca" className="campo py-1 sm:max-w-[22rem]" placeholder="buscar produto, nota, fornecedor…" title="produto, código, nota, fornecedor ou quem recebeu"
                 aria-label="buscar" value={busca} onChange={(e) => aoBusca(e.target.value)} />
          <div className="flex overflow-hidden rounded-lg border border-linha" role="group" aria-label="leitura">
            {(["produto", "nota"] as Leitura[]).map((l) => (
              <button key={l} type="button" data-leitura={l}
                      className={`px-3 py-1.5 text-[13.5px] ${leitura === l ? "bg-erva font-bold text-white" : "hover:bg-linha/40"}`}
                      onClick={() => aoLeitura(l)}>
                por {l}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-4 border-t border-dashed border-linha pt-3 sm:grid-cols-4" id="entradas-totais">
          <div data-numero-entradas="Itens"><p className="rotulo">Itens</p>
            <p className="mono mt-1 text-[20px] font-bold leading-none">{inteiro(d.totais.itens)}</p></div>
          <div data-numero-entradas="Produtos"><p className="rotulo">Produtos</p>
            <p className="mono mt-1 text-[20px] font-bold leading-none">{inteiro(d.totais.produtos)}</p></div>
          <div data-numero-entradas="Notas"><p className="rotulo">Notas</p>
            <p className="mono mt-1 text-[20px] font-bold leading-none">{inteiro(d.totais.notas)}</p></div>
          <div data-numero-entradas="Custo"><p className="rotulo">Custo de entrada</p>
            <p className="mono mt-1 text-[20px] font-bold leading-none">{reais(d.totais.valor)}</p></div>
        </div>
        <p className="mt-2 text-[12.5px] text-suave">
          Pela data de entrada da nota (ou a de emissão). Fora: nota cancelada ou excluída no Omie e
          item marcado como fora do estoque. A quantidade é a do estoque quando o item tem produto.
        </p>
      </Cartao>

      {d.cortado && (
        <p className="text-[13px] text-alerta">
          Mostrando os primeiros {inteiro(d.limite)} itens — estreite o período ou use a busca.
        </p>
      )}

      <Cartao>
        {lista.length ? (
          <div className="overflow-x-auto">
            <table className="tabela w-full text-[13.5px]" id="entradas-itens">
              <thead>
                <tr>
                  {leitura === "produto"
                    ? <><th className="text-left">Nota</th><th className="text-left">Fornecedor</th></>
                    : <th className="text-left">Produto</th>}
                  <th className="text-left">Entrada</th>
                  <th className="text-left">Situação</th>
                  <th className="text-left">Recebido por</th>
                  <th className="text-right">Qtd</th>
                  <th className="text-right">Custo</th>
                </tr>
              </thead>
              <tbody>
                {lista.map(([chave, itens]) => {
                  const p = itens[0];
                  const soma = itens.reduce((s, i) => s + i.custo, 0);
                  const mesmaUm = itens.every((i) => i.um === p.um);
                  const somaQtd = itens.reduce((s, i) => s + i.quantidade, 0);
                  return (
                    <Fragment key={chave}>
                      <tr className="bg-superficie" data-grupo-entrada={chave}>
                        <td colSpan={leitura === "produto" ? 5 : 4} className="font-bold">
                          {leitura === "produto" ? (
                            p.id_produto ? (
                              <button type="button" className="link-registro text-left" title="ver o andamento deste produto"
                                      onClick={() => aoVerProduto(p.id_produto!)}>
                                {p.codigo && <span className="mono font-normal text-suave">{p.codigo} · </span>}{p.produto}
                              </button>
                            ) : (
                              <span>{p.descricao_fornecedor} <Etiqueta cor="alerta">sem produto</Etiqueta></span>
                            )
                          ) : (
                            <span>
                              <Link href={`/compras/${p.id_nota}`} className="link-registro">NF {p.nota}</Link>
                              <span className="font-normal text-suave"> · {p.fornecedor ?? "—"} · {p.data ? dataBr(p.data) : "—"}</span>
                              {" "}<Situacao i={p} />
                              {p.recebido_por && <span className="font-normal text-suave"> · recebida por {p.recebido_por}</span>}
                            </span>
                          )}
                          <span className="ml-2 text-[12px] font-normal text-suave">
                            {leitura === "produto" ? `${inteiro(itens.length)} entrada(s)` : `${inteiro(itens.length)} item(ns)`}
                          </span>
                        </td>
                        <td className="mono text-right font-bold">{leitura === "produto" && mesmaUm ? `${qtd(somaQtd)} ${p.um}` : ""}</td>
                        <td className="mono text-right font-bold">{reais(soma)}</td>
                      </tr>
                      {itens.map((i) => (
                        <tr key={i.id} data-item-entrada={i.id}>
                          {leitura === "produto" ? (
                            <>
                              <td><Link href={`/compras/${i.id_nota}`} className="link-registro mono">NF {i.nota}</Link></td>
                              <td className="max-w-[16rem] truncate">{i.fornecedor ?? "—"}</td>
                            </>
                          ) : (
                            <td className="max-w-[20rem]">
                              {i.id_produto ? (
                                <button type="button" className="link-registro text-left" onClick={() => aoVerProduto(i.id_produto!)}>
                                  {nomeDoItem(i)}
                                </button>
                              ) : <span>{nomeDoItem(i)} <Etiqueta cor="alerta">sem produto</Etiqueta></span>}
                            </td>
                          )}
                          <td className="mono">{i.data ? dataBr(i.data) : "—"}</td>
                          <td><Situacao i={i} /></td>
                          <td><Recebido i={i} /></td>
                          <td className="mono text-right">{qtd(i.quantidade)} {i.um}</td>
                          <td className="mono text-right">{reais(i.custo)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Vazio>Nenhum item de nota no recorte.</Vazio>
        )}
      </Cartao>
    </div>
  );
}
