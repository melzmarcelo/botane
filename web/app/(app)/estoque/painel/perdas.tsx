"use client";

import { Cartao, Etiqueta, Vazio } from "@/components/ui";
import { inteiro, pct, qtd, reais } from "@/lib/numeros";
import type { GrupoPerda, PainelPerdas } from "@/lib/estoque-painel";

import { BarrasDeitadas, eixoReais, GraficoBarras } from "../../vendas/painel/graficos";
import { dataBr, rotuloDoPonto, tituloDoPonto } from "../../vendas/painel/periodo";

/**
 * As perdas: quanto, onde, por quê — e o que some SEM motivo.
 *
 * 🔑 **Clicar num motivo, categoria, setor ou prateleira filtra a aba inteira** por ele,
 * como no painel de vendas: "a quebra, onde acontece?" é um clique no motivo e um olhar nos
 * setores. E clicar num produto abre o andamento dele.
 * 🔑 **A falta da contagem fica ao lado da perda registrada.** A perda tem nome e motivo;
 * a falta do inventário é mercadoria que sumiu sem ninguém ver — quando ela é maior que a
 * perda, o problema não é o desperdício conhecido.
 */

export type Recorte = "motivo" | "categoria" | "setor" | "local";

function Numero({ rotulo, valor, sub, tom }: {
  rotulo: string; valor: string; sub?: React.ReactNode; tom?: "alerta";
}) {
  return (
    <div className="min-w-0" data-numero-perdas={rotulo}>
      <p className="rotulo">{rotulo}</p>
      <p className={`mono mt-1 text-[22px] font-bold leading-none ${tom === "alerta" ? "text-alerta" : ""}`}>{valor}</p>
      {sub && <p className="mt-1 text-[12.5px] leading-snug text-suave">{sub}</p>}
    </div>
  );
}

function Grupo({ titulo, explica, linhas, ativo, aoClicar, id }: {
  titulo: string;
  explica: string;
  linhas: GrupoPerda[];
  ativo: number | null;
  aoClicar?: (id: number | null) => void;
  id: string;
}) {
  return (
    <Cartao>
      <h2 className="text-[15px] font-bold">{titulo}</h2>
      <p className="mb-2 text-[12.5px] text-suave">{explica}</p>
      {linhas.length ? (
        <div id={id}>
          <BarrasDeitadas
            ativo={ativo}
            aoClicar={aoClicar}
            valor={reais}
            linhas={linhas.slice(0, 10).map((g) => ({
              chave: String(g.id ?? "sem"),
              // ⚠️ "Sem categoria" e "sem setor" não filtram: o servidor não tem como pedir
              // "o nulo" desses dois. O "sem motivo" filtra (é o id 0).
              id: typeof g.id === "number" ? g.id : null,
              nome: g.nome, valor: g.valor,
              detalhe: `${pct(g.participacao_pct)} · ${inteiro(g.ocorrencias)} registro(s)`,
            }))}
          />
        </div>
      ) : (
        <Vazio>Nenhuma perda no recorte.</Vazio>
      )}
    </Cartao>
  );
}

export default function Perdas({ d, filtros, aoFiltrar, aoVerProduto }: {
  d: PainelPerdas;
  filtros: Record<Recorte, number | null>;
  aoFiltrar: (r: Recorte, id: number | null) => void;
  aoVerProduto: (id: number) => void;
}) {
  const t = d.totais;
  const c = d.comparacao;
  const alternar = (r: Recorte) => (id: number | null) =>
    aoFiltrar(r, id === null || id === filtros[r] ? null : id);

  return (
    <div className="space-y-4">
      <Cartao>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5" id="painel-perdas-resumo">
          <Numero rotulo="Perdas registradas" valor={reais(t.valor)} tom={t.valor ? "alerta" : undefined}
                  sub={c.pct_valor === null ? "sem base para comparar"
                    : <span className={c.pct_valor > 0 ? "text-alerta" : "text-erva"}>
                        {c.pct_valor > 0 ? "+" : ""}{c.pct_valor.toLocaleString("pt-BR")}% sobre o período anterior
                      </span>} />
          <Numero rotulo="Registros" valor={inteiro(t.ocorrencias)} sub={`${inteiro(t.produtos)} produto(s)`} />
          <Numero rotulo="Do que saiu" valor={t.pct_do_consumo === null ? "—" : pct(t.pct_do_consumo)}
                  sub={`de ${reais(t.consumo_valor)} em venda, produção, consumo e perda`} />
          <Numero rotulo="Falta na contagem" valor={reais(t.faltas_inventario)}
                  tom={t.faltas_inventario > t.valor && t.faltas_inventario > 0 ? "alerta" : undefined}
                  sub="o que sumiu sem registro (ajuste de inventário)" />
          <Numero rotulo="Sobra na contagem" valor={reais(t.sobras_inventario)}
                  sub="o que apareceu a mais na contagem" />
        </div>
        <p className="mt-3 border-t border-dashed border-linha pt-2.5 text-[12.5px] text-suave">
          Comparado com {dataBr(c.inicio)} a {dataBr(c.fim)}: {reais(c.valor)} em {inteiro(c.ocorrencias)} registro(s).
          {" "}Perda estornada não conta. A falta da contagem não é perda registrada: é o que ninguém viu sair.
        </p>
      </Cartao>

      {d.serie.length > 1 && (
        <Cartao>
          <h2 className="mb-2 text-[15px] font-bold">Evolução das perdas</h2>
          <GraficoBarras
            altura={220}
            rotulo={`perdas por ${d.agrupar}, de ${dataBr(d.inicio)} a ${dataBr(d.fim)}`}
            noEixo={eixoReais}
            barras={d.serie.map((s) => ({
              chave: s.periodo,
              rotulo: rotuloDoPonto(d.agrupar, s.periodo),
              titulo: tituloDoPonto(d.agrupar, s.periodo),
              valor: s.valor,
              dica: [
                { rotulo: "perdido", valor: reais(s.valor) },
                { rotulo: "registros", valor: inteiro(s.ocorrencias) },
              ],
            }))}
          />
        </Cartao>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Grupo id="painel-perdas-motivos" titulo="Por motivo" explica="clique num motivo para ver só ele"
               linhas={d.por_motivo} ativo={filtros.motivo} aoClicar={alternar("motivo")} />
        <Grupo id="painel-perdas-setores" titulo="Por setor" explica="o setor de onde saiu (a prateleira), senão o do produto"
               linhas={d.por_setor} ativo={filtros.setor} aoClicar={alternar("setor")} />
        <Grupo id="painel-perdas-categorias" titulo="Por categoria" explica="a categoria do produto"
               linhas={d.por_categoria} ativo={filtros.categoria} aoClicar={alternar("categoria")} />
        <Grupo id="painel-perdas-locais" titulo="Por prateleira" explica="onde a mercadoria estava"
               linhas={d.por_local} ativo={filtros.local} aoClicar={alternar("local")} />
      </div>

      <Cartao>
        <h2 className="mb-2 text-[15px] font-bold">Os produtos que mais se perdem</h2>
        {d.produtos.length ? (
          <div className="overflow-x-auto">
            <table className="tabela w-full text-[13.5px]" id="painel-perdas-produtos">
              <thead>
                <tr>
                  <th className="w-8 text-right">#</th>
                  <th className="text-left">Produto</th>
                  <th className="text-right">Qtd</th>
                  <th className="text-right">Valor</th>
                  <th className="text-right">Registros</th>
                  <th className="text-left">Motivo principal</th>
                  <th className="text-right">Part.</th>
                </tr>
              </thead>
              <tbody>
                {d.produtos.map((p, i) => (
                  <tr key={p.id_produto}>
                    <td className="mono text-right text-suave">{i + 1}</td>
                    <td className="max-w-[18rem]">
                      <button type="button" className="link-registro text-left" title="ver o andamento deste produto"
                              onClick={() => aoVerProduto(p.id_produto)}>{p.produto}</button>
                    </td>
                    <td className="mono text-right">{qtd(p.qtd)} {p.um_estoque}</td>
                    <td className="mono text-right">{reais(p.valor)}</td>
                    <td className="mono text-right">{inteiro(p.ocorrencias)}</td>
                    <td className="text-suave">{p.motivo_principal ?? "—"}</td>
                    <td className="mono text-right">{pct(p.participacao_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {d.produtos_total > d.produtos.length && (
              <p className="mt-2 text-[12.5px] text-suave">
                Os {d.produtos.length} de maior valor, de {inteiro(d.produtos_total)} produtos.
              </p>
            )}
          </div>
        ) : (
          <Vazio>Nenhuma perda no recorte.</Vazio>
        )}
      </Cartao>

      <div className="grid gap-4 lg:grid-cols-3">
        <Cartao className="lg:col-span-1">
          <h2 className="text-[15px] font-bold">Por onde entrou</h2>
          <p className="mb-2 text-[12.5px] text-suave">a porta do registro</p>
          {d.por_origem.length ? (
            <BarrasDeitadas valor={reais} linhas={d.por_origem.map((o) => ({
              chave: String(o.id), id: null, nome: o.nome, valor: o.valor,
              detalhe: `${pct(o.participacao_pct)} · ${inteiro(o.ocorrencias)} registro(s)`,
            }))} />
          ) : (
            <Vazio>Nenhuma perda no recorte.</Vazio>
          )}
        </Cartao>

        <Cartao className="lg:col-span-2">
          <h2 className="mb-2 text-[15px] font-bold">Os registros mais recentes</h2>
          {d.recentes.length ? (
            <ul className="divide-y divide-linha text-[13.5px]" id="painel-perdas-recentes">
              {d.recentes.map((r) => (
                <li key={r.id} className="flex items-baseline justify-between gap-3 py-1.5">
                  <span className="min-w-0">
                    <button type="button" className="link-registro text-left" onClick={() => aoVerProduto(r.id_produto)}>
                      {r.produto}
                    </button>
                    {r.estorno && <> <Etiqueta>estorno</Etiqueta></>}
                    <span className="block text-[12px] text-suave">
                      {dataBr(r.data_movimento.slice(0, 10))} · {r.motivo} · {r.local} · {r.origem_rotulo}
                      {r.usuario && <> · {r.usuario}</>}
                      {r.observacao && <> — {r.observacao}</>}
                    </span>
                  </span>
                  <span className="mono shrink-0 text-right">
                    {qtd(r.qtd)} {r.um_estoque}
                    <span className="block text-[12px] text-suave">{reais(r.valor)}</span>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <Vazio>Nenhuma perda no recorte.</Vazio>
          )}
        </Cartao>
      </div>
    </div>
  );
}
