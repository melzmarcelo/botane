"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

/**
 * Os dois relatórios que o dono usa para decidir.
 *
 * **Onde pesa** responde "a cozinha está pesando mais que o bar?" — a mesma
 * conta do CMV, quebrada por setor ou categoria. A barra é proposital: a
 * participação de cada grupo se lê de relance, o número exato fica ao lado
 * para quem quiser conferir.
 *
 * **O que subiu** é o relatório de sentar com o fornecedor. Ordena pelo
 * impacto em reais, não pelo percentual: 8% num item que entra toda semana
 * dói mais que 60% no que se compra uma vez por trimestre.
 */

type Grupo = {
  grupo: string;
  estoque_inicial: number;
  compras: number;
  estoque_final: number;
  cmv: number;
  perdas: number;
  produtos: number;
  participacao_pct: number;
};

type Preco = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  compras: number;
  menor: number;
  maior: number;
  quantidade: number;
  primeiro: number;
  ultimo: number;
  variacao_pct: number;
  impacto: number;
  economia_possivel: number;
  data_ultimo: string | null;
  fornecedor_ultimo: string | null;
  fornecedor_mais_barato: string | null;
};

type Compra = {
  data: string;
  numero: string | null;
  fornecedor: string | null;
  quantidade: number;
  preco: number;
  variacao_pct: number | null;
};

const pct = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
const dataBr = (d: string) => new Date(d + "T00:00").toLocaleDateString("pt-BR");

export default function RelatoriosDono({ inicio, fim }: { inicio: string; fim: string }) {
  const [agrupar, setAgrupar] = useState<"setor" | "categoria">("setor");
  const [grupos, setGrupos] = useState<Grupo[] | null>(null);
  const [precos, setPrecos] = useState<Preco[] | null>(null);
  const [aberto, setAberto] = useState<number | null>(null);
  const [serie, setSerie] = useState<Compra[] | null>(null);

  const carregar = useCallback(async () => {
    setGrupos(null);
    setPrecos(null);
    const janela = `inicio=${inicio}&fim=${fim}`;
    const [g, p] = await Promise.all([
      api.get<Grupo[]>(`/cmv/por-grupo?${janela}&agrupar=${agrupar}`).catch(() => []),
      api.get<Preco[]>(`/cmv/precos?${janela}`).catch(() => []),
    ]);
    setGrupos(g);
    setPrecos(p);
  }, [inicio, fim, agrupar]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function abrir(id: number) {
    if (aberto === id) {
      setAberto(null);
      return;
    }
    setAberto(id);
    setSerie(null);
    setSerie(await api.get<Compra[]>(`/cmv/precos/${id}`).catch(() => []));
  }

  const maior = Math.max(1, ...(grupos ?? []).map((g) => Math.abs(Number(g.cmv))));

  return (
    <div className="flex flex-col gap-6">
      <Cartao
        titulo="Onde o custo pesa"
        descricao="A mesma conta do CMV, quebrada por grupo. A soma dos grupos é o CMV do período."
        acao={
          <div className="flex gap-1">
            {(["setor", "categoria"] as const).map((x) => (
              <button
                key={x}
                onClick={() => setAgrupar(x)}
                className={`rotulo px-2 py-1 ${
                  agrupar === x ? "text-erva" : "text-suave hover:text-tinta"
                }`}
              >
                por {x}
              </button>
            ))}
          </div>
        }
      >
        {!grupos ? (
          <Carregando />
        ) : !grupos.length ? (
          <Vazio>Nenhum movimento no período.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Grupo</th>
                  <th className="num">Estoque inicial</th>
                  <th className="num">Compras</th>
                  <th className="num">Estoque final</th>
                  <th className="num">CMV</th>
                  <th className="num">Perdas</th>
                  <th>Participação</th>
                </tr>
              </thead>
              <tbody>
                {grupos.map((g) => (
                  <tr key={g.grupo}>
                    <td>
                      <span className="font-semibold">{g.grupo}</span>
                      <span className="block text-[12.5px] text-suave">
                        {g.produtos} produto(s)
                      </span>
                    </td>
                    <td className="num mono text-suave">{reais(Number(g.estoque_inicial))}</td>
                    <td className="num mono text-suave">{reais(Number(g.compras))}</td>
                    <td className="num mono text-suave">{reais(Number(g.estoque_final))}</td>
                    <td className="num mono font-semibold">{reais(Number(g.cmv))}</td>
                    <td className="num mono">
                      {Number(g.perdas) > 0 ? (
                        <span className="text-erro">{reais(Number(g.perdas))}</span>
                      ) : (
                        <span className="text-suave">—</span>
                      )}
                    </td>
                    <td>
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-full max-w-[120px] rounded bg-superficie2">
                          <span
                            className="block h-2 rounded bg-erva"
                            style={{
                              width: `${Math.min(100, (Math.abs(Number(g.cmv)) / maior) * 100)}%`,
                            }}
                          />
                        </span>
                        <span className="mono text-[13px] text-suave">
                          {Number(g.participacao_pct).toFixed(1)}%
                        </span>
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      <Cartao
        titulo="O que subiu de preço"
        descricao="Ordenado pelo impacto em reais no volume comprado — não pelo percentual."
      >
        {!precos ? (
          <Carregando />
        ) : !precos.length ? (
          <Vazio>
            Nenhum insumo com duas compras ou mais no período — sem duas notas não há variação
            a mostrar.
          </Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th className="num">Compras</th>
                  <th className="num">De</th>
                  <th className="num">Para</th>
                  <th className="num">Variação</th>
                  <th className="num">Impacto</th>
                  <th>Mais barato com</th>
                </tr>
              </thead>
              <tbody>
                {precos.map((p) => (
                  <tr key={p.id_produto}>
                    <td>
                      <button className="text-left" onClick={() => void abrir(p.id_produto)}>
                        <span className="font-semibold hover:text-erva">{p.produto}</span>
                        <span className="block text-[12.5px] text-suave">
                          {aberto === p.id_produto ? "esconder as compras" : "ver cada compra"}
                        </span>
                      </button>
                      {aberto === p.id_produto && (
                        <div className="mt-2 border-l-2 border-linha pl-3">
                          {!serie ? (
                            <Carregando />
                          ) : (
                            <ul className="flex flex-col gap-1 text-[13px]">
                              {serie.map((c, i) => (
                                <li key={i} className="flex flex-wrap gap-x-3 text-suave">
                                  <span className="mono">{dataBr(c.data)}</span>
                                  <span className="mono">{reais(Number(c.preco))}</span>
                                  <span>{c.fornecedor ?? "—"}</span>
                                  {c.numero && <span className="mono">NF {c.numero}</span>}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="num mono text-suave">{p.compras}</td>
                    <td className="num mono text-suave">{reais(Number(p.primeiro))}</td>
                    <td className="num mono">{reais(Number(p.ultimo))}</td>
                    <td className="num">
                      <Etiqueta cor={Number(p.variacao_pct) > 0 ? "alerta" : "erva"}>
                        {pct(Number(p.variacao_pct))}
                      </Etiqueta>
                    </td>
                    <td
                      className={`num mono font-semibold ${
                        Number(p.impacto) > 0 ? "text-erro" : "text-erva"
                      }`}
                    >
                      {reais(Number(p.impacto))}
                    </td>
                    <td className="text-[13.5px]">
                      {p.fornecedor_mais_barato ?? "—"}
                      {Number(p.economia_possivel) > 0.5 && (
                        <span className="block text-[12.5px] text-suave">
                          daria {reais(Number(p.economia_possivel))} de economia
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>
    </div>
  );
}
