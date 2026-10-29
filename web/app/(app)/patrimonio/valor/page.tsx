"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import BotaoExportar from "@/components/exportar";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Campo, Carregando, Cartao, Vazio } from "@/components/ui";
import Voltar from "@/components/voltar";
import AbasDoPatrimonio from "../abas";
import { api } from "@/lib/api";
import type { Setor } from "@/lib/cadastros";
import { hoje } from "@/lib/datas";
import { reais } from "@/lib/numeros";
import { dataBr, valorDoPatrimonio, type ValorPatrimonio } from "@/lib/patrimonio";

/**
 * O valor do patrimônio — etapa 4 (migração 141).
 *
 * 🔑 **Pedido do dono (28/10/2026):** *"pode seguir com a etapa 4 do patrimônio"* — valor
 * patrimonial por setor e depreciação (valor de compra e vida útil, dando o valor atual),
 * só como relatório. ⚠️ A conta é do servidor (`services/patrimonio_valor.py`): a mesma da
 * ficha do bem e do relatório baixado.
 */
export default function PaginaValor() {
  const [data, setData] = useState(hoje());
  const [setor, setSetor] = useState("");
  const [setores, setSetores] = useState<Setor[]>([]);
  const [v, setV] = useState<ValorPatrimonio | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api.get<Setor[]>("/setores").then(setSetores).catch(() => {});
  }, []);

  useEffect(() => {
    if (!data) return;
    setV(null);
    valorDoPatrimonio(data, setor ? [Number(setor)] : [])
      .then((r) => { setV(r); setErro(""); })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, [data, setor]);

  const t = v?.total;
  return (
    <div className="flex flex-col gap-6">
      <header>
        <Voltar href="/patrimonio">patrimônio</Voltar>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Valor do patrimônio</h1>
        <ExplicaTela>
          Quanto valem os bens da loja numa data. Cada bem perde valor <strong>todo mês</strong>,
          em partes iguais, até o fim da vida útil (10 anos se não for dito outro na ficha —
          o padrão da Receita para máquinas e móveis). O que está <strong>a confirmar</strong> não
          conta; o baixado conta até a data da baixa. É só relatório: nada aqui vai para o CMV.
        </ExplicaTela>
      </header>

      <AbasDoPatrimonio />

      <div className="flex flex-wrap items-end gap-3">
        <Campo rotulo="Na data de">
          <input type="date" className="campo" id="valor-data" value={data}
                 onChange={(e) => setData(e.target.value)} />
        </Campo>
        <Campo rotulo="Setor">
          <select className="campo" id="valor-setor" value={setor} onChange={(e) => setSetor(e.target.value)}>
            <option value="">Todos</option>
            {setores.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
          </select>
        </Campo>
        <BotaoExportar relatorio="patrimonio-valor"
                       iniciais={{ data, setores: setor ? [Number(setor)] : undefined }} />
      </div>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!v || !t ? (!erro && <Carregando />) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3" id="valor-totais">
            <Total id="compra" rotulo="Valor de compra" valor={reais(t.valor_compra)}
                   sub={`${t.bens} ${t.bens === 1 ? "bem" : "bens"}${t.sem_valor ? ` · ${t.sem_valor} sem valor de compra` : ""}`} />
            <Total id="depreciacao" rotulo="Depreciação acumulada" valor={reais(t.depreciacao)}
                   sub={t.depreciados ? `${t.depreciados} já ${t.depreciados === 1 ? "totalmente depreciado" : "totalmente depreciados"}` : undefined} />
            <Total id="atual" rotulo={`Valor em ${dataBr(v.data)}`} valor={reais(t.valor_atual)}
                   sub={t.sem_data ? `${t.sem_data} sem data de compra — ${t.sem_data === 1 ? "conta" : "contam"} pelo valor de compra` : undefined} />
          </div>

          <Cartao titulo="Por setor">
            {!v.setores.length ? <Vazio>Nenhum bem com valor nesta data.</Vazio> : (
              <div className="grid-rolante">
                <table className="tabela" id="valor-setores">
                  <thead>
                    <tr><th>Setor</th><th className="num">Bens</th><th className="num">Compra</th>
                      <th className="num">Depreciação</th><th className="num">Valor atual</th></tr>
                  </thead>
                  <tbody>
                    {v.setores.map((s) => (
                      <tr key={s.setor}>
                        <td>{s.setor}</td>
                        <td className="num">{s.bens}</td>
                        <td className="num">{reais(s.valor_compra)}</td>
                        <td className="num">{reais(s.depreciacao)}</td>
                        <td className="num font-semibold">{reais(s.valor_atual)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Cartao>

          {v.bens.length > 0 && (
            <Cartao titulo="Bem a bem">
              <div className="grid-rolante">
                <table className="tabela" id="valor-bens">
                  <thead>
                    <tr><th>Código</th><th>Equipamento</th><th>Setor</th><th>Compra</th>
                      <th className="num">Valor de compra</th><th className="num">Vida útil</th>
                      <th className="num">Depreciação</th><th className="num">Valor atual</th></tr>
                  </thead>
                  <tbody>
                    {v.bens.map((b) => (
                      <tr key={b.id} data-codigo={b.codigo}>
                        <td className="mono whitespace-nowrap">
                          <Link href={`/patrimonio/${b.id}`} className="link-registro">{b.codigo}</Link>
                        </td>
                        <td>
                          {b.descricao}
                          {b.situacao !== "EM_USO" && (
                            <span className="block text-[12px] text-suave">{b.situacao_txt}</span>
                          )}
                        </td>
                        <td>{b.setor ?? "—"}</td>
                        <td className="whitespace-nowrap">{b.data_compra ? dataBr(b.data_compra) : "—"}</td>
                        <td className="num">{b.valor_compra !== null ? reais(b.valor_compra) : "—"}</td>
                        <td className="num whitespace-nowrap">
                          {b.vida_util} anos{b.vida_padrao && <span className="text-suave"> (padrão)</span>}
                        </td>
                        <td className="num">
                          {b.depreciacao !== null ? reais(b.depreciacao) : "—"}
                          {b.depreciado_pct !== null && (
                            <span className="block text-[12px] text-suave">{b.depreciado_pct.toLocaleString("pt-BR")}%</span>
                          )}
                        </td>
                        <td className="num font-semibold">
                          {b.valor_atual !== null ? reais(b.valor_atual) : "—"}
                          {(b.sem_valor || b.sem_data || b.depreciado_total) && (
                            <span className="block text-[12px] font-normal text-suave">
                              {b.sem_valor ? "sem valor de compra" : b.sem_data ? "sem data — não deprecia" : "totalmente depreciado"}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Cartao>
          )}
        </>
      )}
    </div>
  );
}

function Total({ id, rotulo, valor, sub }: { id: string; rotulo: string; valor: string; sub?: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-linha bg-superficie p-3" data-total={id}>
      <p className="rotulo">{rotulo}</p>
      <p className="mono mt-1 text-[22px] font-bold leading-none">{valor}</p>
      {sub && <p className="mt-1 text-[12.5px] leading-snug text-suave">{sub}</p>}
    </div>
  );
}
