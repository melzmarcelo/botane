"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

type Apuracao = {
  inicio: string;
  fim: string;
  estoque_inicial: number;
  compras: number;
  estoque_final: number;
  cmv_real: number;
  cmv_teorico: number;
  variancia: number;
  variancia_pct: number | null;
  perdas: number;
  consumo_interno: number;
  ajustes: number;
  receita: number;
  vendas: number;
  itens_sem_custo: number;
  cobertura_ficha_pct: number;
  food_cost_pct: number | null;
  fechado: boolean;
};

type LinhaAbc = {
  id_produto: number;
  codigo: string;
  produto: string;
  quantidade: number;
  valor: number;
  participacao_pct: number;
  acumulada_pct: number;
  classe: string;
};

type LinhaMargem = {
  id_produto: number | null;
  produto: string;
  quantidade: number;
  receita: number;
  custo: number;
  margem: number;
  margem_pct: number | null;
  food_cost_pct: number | null;
  sem_custo: boolean;
};

type Fechamento = {
  id: number;
  competencia: string;
  cmv_real: number;
  cmv_teorico: number;
  variancia: number;
  receita: number;
  food_cost_pct: number | null;
  status: string;
  fechado_por: string | null;
};

const pct = (v: number | null | undefined, casas = 1) =>
  v === null || v === undefined ? "—" : `${Number(v).toFixed(casas).replace(".", ",")}%`;

const primeiroDiaDoMes = () => {
  const d = new Date();
  return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
};

export default function PaginaCmv() {
  const { pode } = useSessao();
  const [inicio, setInicio] = useState(primeiroDiaDoMes());
  const [fim, setFim] = useState(new Date().toISOString().slice(0, 10));
  const [a, setA] = useState<Apuracao | null>(null);
  const [abc, setAbc] = useState<LinhaAbc[] | null>(null);
  const [margem, setMargem] = useState<LinhaMargem[] | null>(null);
  const [fechamentos, setFechamentos] = useState<Fechamento[]>([]);
  const [aba, setAba] = useState<"abc" | "margem">("abc");
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    const q = `inicio=${inicio}&fim=${fim}`;
    try {
      const [ap, cur, mar, fec] = await Promise.all([
        api.get<Apuracao>(`/cmv/apuracao?${q}`),
        api.get<LinhaAbc[]>(`/cmv/abc?${q}&limite=30`),
        api.get<LinhaMargem[]>(`/cmv/margem?${q}&limite=30`),
        api.get<Fechamento[]>("/cmv/fechamentos"),
      ]);
      setA(ap);
      setAbc(cur);
      setMargem(mar);
      setFechamentos(fec);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [inicio, fim]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function fechar() {
    setOcupado(true);
    setErro("");
    setOk("");
    try {
      const r = await api.post<{ competencia: string; variancia: number }>("/cmv/fechamentos", {
        competencia: inicio,
      });
      setOk(
        `Período de ${r.competencia} fechado. A partir de agora, lançamento com data dentro dele exige permissão de retroativo.`,
      );
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível fechar");
    } finally {
      setOcupado(false);
    }
  }

  async function reabrir(id: number) {
    setErro("");
    setOk("");
    try {
      await api.post(`/cmv/fechamentos/${id}/reabrir`);
      setOk("Período reaberto — e isso ficou registrado na auditoria.");
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível reabrir");
    }
  }

  const variânciaAlta = a && a.cmv_teorico > 0 && Math.abs(a.variancia_pct ?? 0) > 5;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">CMV</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Quanto custou o que você vendeu
          </h1>
          <p className="mt-1 max-w-[64ch] text-suave">
            O real vem do estoque; o teórico, das fichas técnicas com as vendas do período. A
            diferença entre os dois é o número que vale olhar todo dia.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label>
            <span className="rotulo">De</span>
            <input
              className="campo mt-1.5"
              type="date"
              value={inicio}
              onChange={(e) => setInicio(e.target.value)}
            />
          </label>
          <label>
            <span className="rotulo">Até</span>
            <input
              className="campo mt-1.5"
              type="date"
              value={fim}
              onChange={(e) => setFim(e.target.value)}
            />
          </label>
        </div>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {ok && <Aviso tipo="ok">{ok}</Aviso>}

      {!a ? (
        <Carregando />
      ) : (
        <>
          <div className="grid gap-px overflow-hidden rounded border border-linha bg-linha sm:grid-cols-2 lg:grid-cols-4">
            {[
              { r: "CMV real", v: reais(a.cmv_real), d: "estoque inicial + compras − final" },
              { r: "CMV teórico", v: reais(a.cmv_teorico), d: "vendas × custo da ficha" },
              {
                r: "Variância",
                v: reais(a.variancia),
                d: pct(a.variancia_pct) + " do teórico",
                destaque: true,
              },
              {
                r: "Food cost",
                v: pct(a.food_cost_pct),
                d: `sobre ${reais(a.receita)} de receita`,
              },
            ].map((c) => (
              <div key={c.r} className="bg-superficie p-4">
                <p className="rotulo">{c.r}</p>
                <p
                  className={`mono mt-1 text-[22px] ${
                    c.destaque
                      ? a.variancia > 0
                        ? "font-bold text-erro"
                        : "font-bold text-erva"
                      : ""
                  }`}
                >
                  {c.v}
                </p>
                <p className="mt-0.5 text-[12.5px] text-suave">{c.d}</p>
              </div>
            ))}
          </div>

          {a.cobertura_ficha_pct < 95 && a.receita > 0 && (
            <Aviso tipo="info">
              Só {pct(a.cobertura_ficha_pct)} da receita está com prato vinculado a uma ficha —
              o CMV teórico acima é dessa fatia, não do faturamento inteiro.{" "}
              <Link href="/vendas" className="underline">
                ver itens sem vínculo
              </Link>
            </Aviso>
          )}

          {variânciaAlta && (
            <Aviso tipo={a.variancia > 0 ? "erro" : "info"}>
              {a.variancia > 0
                ? `Saiu ${reais(a.variancia)} a mais do estoque do que as receitas justificam. Olhe perdas (${reais(a.perdas)}), porção fora do padrão e desvio.`
                : `O estoque consumiu ${reais(Math.abs(a.variancia))} a menos que o teórico — costuma ser prato vendido sem ficha ou ficha exagerada.`}
            </Aviso>
          )}

          <Cartao
            titulo="Como o CMV se formou"
            descricao="A conta aberta, para conferir de onde cada real veio."
            acao={
              a.fechado ? (
                <Etiqueta cor="erva">período fechado</Etiqueta>
              ) : pode("cmv.fechamento") ? (
                <button className="btn btn-secundario" onClick={fechar} disabled={ocupado}>
                  Fechar o mês
                </button>
              ) : undefined
            }
          >
            <div className="overflow-x-auto">
              <table className="tabela">
                <tbody>
                  {[
                    ["Estoque inicial", a.estoque_inicial, "o que havia no começo"],
                    ["+ Compras", a.compras, "entradas por nota e manuais"],
                    ["− Estoque final", -a.estoque_final, "o que sobrou no fim"],
                    ["= CMV real", a.cmv_real, "o que de fato saiu", true],
                    ["Perdas", a.perdas, "quebra, validade, cortesia — dentro do CMV real"],
                    ["Consumo interno", a.consumo_interno, "equipe e degustação"],
                    ["Ajustes de inventário", a.ajustes, "diferença apurada na contagem"],
                  ].map(([rotulo, valor, ajuda, forte]) => (
                    <tr key={String(rotulo)}>
                      <td className={forte ? "font-bold" : ""}>{rotulo}</td>
                      <td className="text-[13px] text-suave">{ajuda}</td>
                      <td className={`num ${forte ? "font-bold" : ""}`}>
                        {reais(Number(valor))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[13px] text-suave">
              {a.vendas} venda(s) no período
              {a.itens_sem_custo > 0 && ` · ${a.itens_sem_custo} item(ns) vendido(s) sem custo conhecido`}
            </p>
          </Cartao>

          <nav className="flex gap-1 border-b border-linha">
            {(["abc", "margem"] as const).map((x) => (
              <button
                key={x}
                onClick={() => setAba(x)}
                className={`-mb-px border-b-2 px-3 py-2 text-[14.5px] ${
                  aba === x
                    ? "border-erva font-semibold text-erva"
                    : "border-transparent text-suave hover:text-tinta"
                }`}
              >
                {x === "abc" ? "Curva ABC de insumos" : "Margem por prato"}
              </button>
            ))}
          </nav>

          {aba === "abc" && (
            <Cartao
              titulo="Onde o dinheiro foi parar"
              descricao="Classe A = os 80% do valor consumido. É neles que negociar preço muda o mês."
            >
              {!abc ? (
                <Carregando />
              ) : !abc.length ? (
                <Vazio>Nenhum consumo no período.</Vazio>
              ) : (
                <div className="overflow-x-auto">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Insumo</th>
                        <th className="num">Consumo</th>
                        <th className="num">Valor</th>
                        <th className="num">Participação</th>
                        <th className="num">Acumulado</th>
                        <th>Classe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {abc.map((l) => (
                        <tr key={l.id_produto}>
                          <td>
                            <span className="font-semibold">{l.produto}</span>
                            <span className="mono ml-2 text-[12px] text-suave">{l.codigo}</span>
                          </td>
                          <td className="num text-suave">
                            {Number(l.quantidade).toLocaleString("pt-BR", {
                              maximumFractionDigits: 2,
                            })}
                          </td>
                          <td className="num font-semibold">{reais(l.valor)}</td>
                          <td className="num">{pct(l.participacao_pct)}</td>
                          <td className="num text-suave">{pct(l.acumulada_pct)}</td>
                          <td>
                            <Etiqueta cor={l.classe === "A" ? "erva" : l.classe === "B" ? "alerta" : "neutro"}>
                              {l.classe}
                            </Etiqueta>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Cartao>
          )}

          {aba === "margem" && (
            <Cartao
              titulo="O que cada prato deixa"
              descricao="Receita menos o custo da ficha. É a base da engenharia de cardápio."
            >
              {!margem ? (
                <Carregando />
              ) : !margem.length ? (
                <Vazio>Nenhuma venda no período.</Vazio>
              ) : (
                <div className="overflow-x-auto">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Prato</th>
                        <th className="num">Vendidos</th>
                        <th className="num">Receita</th>
                        <th className="num">Custo</th>
                        <th className="num">Margem</th>
                        <th className="num">Food cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {margem.map((l, i) => (
                        <tr key={l.id_produto ?? `sem-${i}`}>
                          <td>
                            <span className="font-semibold">{l.produto}</span>
                            {l.sem_custo && (
                              <span className="ml-2">
                                <Etiqueta cor="alerta">sem custo</Etiqueta>
                              </span>
                            )}
                          </td>
                          <td className="num text-suave">
                            {Number(l.quantidade).toLocaleString("pt-BR", {
                              maximumFractionDigits: 2,
                            })}
                          </td>
                          <td className="num">{reais(l.receita)}</td>
                          <td className="num">{reais(l.custo)}</td>
                          <td className="num font-semibold">{reais(l.margem)}</td>
                          <td
                            className={`num ${
                              (l.food_cost_pct ?? 0) > 40 ? "text-erro" : "text-suave"
                            }`}
                          >
                            {pct(l.food_cost_pct)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Cartao>
          )}

          <Cartao
            titulo="Meses fechados"
            descricao="Fechar congela o período: depois disso, lançar com data de trás exige permissão."
          >
            {!fechamentos.length ? (
              <Vazio>Nenhum mês fechado ainda.</Vazio>
            ) : (
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Competência</th>
                      <th className="num">CMV real</th>
                      <th className="num">Teórico</th>
                      <th className="num">Variância</th>
                      <th className="num">Food cost</th>
                      <th>Situação</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {fechamentos.map((f) => (
                      <tr key={f.id}>
                        <td className="mono">
                          {new Date(f.competencia + "T12:00:00").toLocaleDateString("pt-BR", {
                            month: "2-digit",
                            year: "numeric",
                          })}
                        </td>
                        <td className="num">{reais(f.cmv_real)}</td>
                        <td className="num">{reais(f.cmv_teorico)}</td>
                        <td className={`num ${f.variancia > 0 ? "text-erro" : "text-erva"}`}>
                          {reais(f.variancia)}
                        </td>
                        <td className="num">{pct(f.food_cost_pct)}</td>
                        <td>
                          <Etiqueta cor={f.status === "FECHADO" ? "erva" : "alerta"}>
                            {f.status.toLowerCase()}
                          </Etiqueta>
                        </td>
                        <td className="text-right">
                          {f.status === "FECHADO" && pode("cmv.reabrir") && (
                            <button
                              className="rotulo hover:text-erro"
                              onClick={() => void reabrir(f.id)}
                            >
                              reabrir
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Cartao>
        </>
      )}
    </div>
  );
}
