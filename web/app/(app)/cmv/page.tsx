"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hoje } from "@/lib/datas";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { nomeTipo, reais } from "@/lib/cadastros";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import RelatoriosDono from "./relatorios-dono";
import Movimentacao from "./movimentacao";

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
  ciclo: string;
  rotulo: string | null;
  grupos?: {
    nome: string;
    cmv: number;
    compras: number;
    produtos: number;
    tipos: string[];
    considerar_no_cmv: boolean;
  }[];
  tipos_fora_do_cmv?: string[];
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

type Periodo = {
  inicio: string;
  fim: string;
  rotulo: string;
  corrente: boolean;
  status: string | null;
  fechavel: boolean;
};

type Ciclo = { ciclo: string; descricao: string; periodos: Periodo[] };

type Fechamento = {
  id: number;
  competencia: string;
  inicio: string;
  fim: string;
  rotulo: string | null;
  ciclo: string;
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

export default function PaginaCmv() {
  const aviso = useAviso();
  const { pode } = useSessao();
  // ⚠️ **Quem diz qual é o período é o servidor.** A casa pode fechar por dia,
  // por semana ou por mês, e a semana que fecha na quarta não se calcula com
  // `primeiroDiaDoMes()`. Enquanto o ciclo não chega, as datas ficam vazias e a
  // apuração não é pedida — um flash com o mês do calendário numa casa que
  // fecha por semana já seria um número errado na tela.
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [ciclo, setCiclo] = useState<Ciclo | null>(null);
  const [a, setA] = useState<Apuracao | null>(null);
  const [abc, setAbc] = useState<LinhaAbc[] | null>(null);
  const [margem, setMargem] = useState<LinhaMargem[] | null>(null);
  const [fechamentos, setFechamentos] = useState<Fechamento[]>([]);
  // Fechar e reabrir mês são as duas ações que mudam o que já foi contado ao
  // dono — as duas perguntam antes.
  const [confirmando, setConfirmando] = useState<
    { tipo: "fechar" } | { tipo: "reabrir"; id: number; competencia: string } | null
  >(null);
  const [aba, setAba] = useState<"abc" | "margem" | "movimentacao" | "dono">("abc");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  // O ciclo é pedido uma vez: ele muda na tela de Lojas, não aqui.
  useEffect(() => {
    api
      .get<Ciclo>("/cmv/periodos?quantos=12")
      .then((c) => {
        setCiclo(c);
        const atual = c.periodos.find((p) => p.corrente) ?? c.periodos[0];
        if (atual) {
          setInicio(atual.inicio);
          // O período corrente ainda não acabou: mostrar até hoje, não até o
          // fim que ainda vai acontecer.
          setFim(atual.fim > hoje() ? hoje() : atual.fim);
        }
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, []);

  const carregar = useCallback(async () => {
    if (!inicio || !fim) return;
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
    try {
      const r = await api.post<{ rotulo: string; variancia: number }>("/cmv/fechamentos", {
        competencia: inicio,
      });
      aviso.sucesso(
        `Período de ${r.rotulo} fechado. A partir de agora, lançamento com data dentro dele exige permissão de retroativo.`,
      );
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível fechar");
    } finally {
      setOcupado(false);
    }
  }

  async function reabrir(id: number) {
    setErro("");
    try {
      await api.post(`/cmv/fechamentos/${id}/reabrir`);
      aviso.sucesso("Período reaberto — e isso ficou registrado na auditoria.");
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reabrir");
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
        <div className="nao-imprimir flex flex-wrap items-end gap-2">
          <BotaoExportar relatorio="cmv" iniciais={{ inicio, fim }} />
          {/* ⚠️ Continua existindo: o Ctrl+P imprime a TELA como ela está, com
              os cartões e os gráficos. O PDF da janela é a tabela do relatório
              — são duas coisas, e quem quer uma raramente quer a outra. */}
          <button className="btn btn-secundario" onClick={() => window.print()}>
            Imprimir a tela
          </button>
          {/* ⚠️ Escolher o período pronto vem ANTES de escolher datas soltas: é o
              que a casa usa todo dia, e digitar "17/08 a 23/08" à mão é onde o
              engano entra — um dia a mais e a apuração deixa de bater com o
              fechamento. As datas continuam ali para o recorte fora do ritmo. */}
          {ciclo && ciclo.periodos.length > 0 && (
            <label>
              <span className="rotulo">Período</span>
              <select
                className="campo mt-1.5"
                value={
                  ciclo.periodos.find((p) => p.inicio === inicio && p.fim === fim)?.inicio ?? ""
                }
                onChange={(e) => {
                  const p = ciclo.periodos.find((x) => x.inicio === e.target.value);
                  if (!p) return;
                  setInicio(p.inicio);
                  setFim(p.fim > hoje() ? hoje() : p.fim);
                }}
              >
                <option value="">outro recorte</option>
                {ciclo.periodos.map((p) => (
                  <option key={p.inicio} value={p.inicio}>
                    {p.rotulo}
                    {p.corrente ? " (em curso)" : p.status === "FECHADO" ? " · fechado" : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
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

          {/* ⚠️ O aviso vem ANTES da conta, não depois: quem compara o CMV
              deste mês com o do mês passado precisa saber que a régua mudou. */}
          {(a.tipos_fora_do_cmv?.length ?? 0) > 0 && (
            <Aviso tipo="info">
              {(a.grupos ?? [])
                .filter((g) => !g.considerar_no_cmv)
                .map((g) => g.nome)
                .join(", ") || "Um grupo"}{" "}
              está <b>fora do CMV real</b>: o custo de{" "}
              {(a.tipos_fora_do_cmv ?? []).map(nomeTipo).join(", ").toLowerCase()} não entra na
              conta abaixo nem no food cost. Ele continua à vista, em linha própria — quem
              quiser somá-lo, soma.{" "}
              <Link href="/cadastros?aba=grupos-cmv" className="underline">
                mudar isso
              </Link>
            </Aviso>
          )}

          <Cartao
            titulo="Como o CMV se formou"
            descricao="A conta aberta, para conferir de onde cada real veio."
            acao={
              a.fechado ? (
                <Etiqueta cor="erva">período fechado</Etiqueta>
              ) : pode("cmv.fechamento") ? (
                <button
                  className="btn btn-secundario"
                  onClick={() => setConfirmando({ tipo: "fechar" })}
                  disabled={ocupado}
                >
                  Fechar {a.rotulo ? `— ${a.rotulo}` : "o período"}
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
                    // ⚠️ **Duas naturezas de linha de grupo.** A que está
                    // DENTRO explica o CMV real, como Perdas: o custo já está
                    // no total, e a linha diz quanto do total é aquilo. A que
                    // está FORA mostra um valor que NÃO está no total — foi
                    // tirado do estoque inicial, das compras e do final. Sem a
                    // frase dizendo qual é qual, a conta parece não fechar.
                    ...(a.grupos ?? []).map((g) => [
                      g.nome,
                      g.cmv,
                      `${g.tipos.map(nomeTipo).join(" e ")} — ${
                        g.considerar_no_cmv ? "dentro do CMV real" : "FORA do CMV real"
                      }`,
                    ] as [string, number, string]),
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
            {(["abc", "margem", "movimentacao", "dono"] as const).map((x) => (
              <button
                key={x}
                onClick={() => setAba(x)}
                className={`-mb-px border-b-2 px-3 py-2 text-[14.5px] ${
                  aba === x
                    ? "border-erva font-semibold text-erva"
                    : "border-transparent text-suave hover:text-tinta"
                }`}
              >
                {x === "abc"
                  ? "Curva ABC de insumos"
                  : x === "margem"
                    ? "Margem por prato"
                    : x === "movimentacao"
                      ? "Movimentação do estoque"
                      : "Onde pesa e o que subiu"}
              </button>
            ))}
            <BotaoExportar
              className="link-acao nao-imprimir ml-auto self-center"
              rotulo="baixar esta tabela"
              relatorio={
                aba === "abc"
                  ? "abc"
                  : aba === "movimentacao"
                    ? "movimentacao"
                    : aba === "dono"
                      ? "precos"
                      : "cmv"
              }
              iniciais={{ inicio, fim }}
            />
          </nav>

          {aba === "movimentacao" && <Movimentacao inicio={inicio} fim={fim} />}

          {aba === "dono" && <RelatoriosDono inicio={inicio} fim={fim} />}

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
            titulo="Períodos fechados"
            descricao="Fechar congela o período: depois disso, lançar com data de trás exige permissão."
          >
            {!fechamentos.length ? (
              <Vazio>Nenhum período fechado ainda.</Vazio>
            ) : (
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Período</th>
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
                        {/* ⚠️ O nome do período vem do servidor. Ele é o único
                            que sabe se "01/08" é o mês de agosto ou a semana que
                            começou nele — a coluna `ciclo` é quem responde, e
                            remontar a frase aqui daria duas versões da mesma
                            verdade. */}
                        <td>{f.rotulo ?? `${f.inicio} a ${f.fim}`}</td>
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
                              className="link-acao link-acao-erro"
                              onClick={() =>
                                setConfirmando({ tipo: "reabrir", id: f.id,
                                                 competencia: f.rotulo ?? f.competencia })
                              }
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

      {confirmando?.tipo === "fechar" && (
        <Confirmacao
          titulo="Fechar o período"
          rotuloConfirmar="Fechar"
          ocupado={ocupado}
          aoCancelar={() => setConfirmando(null)}
          aoConfirmar={() => {
            setConfirmando(null);
            void fechar();
          }}
        >
          <p>
            Fechar a apuração de <b>{a?.rotulo ?? `${inicio} a ${fim}`}</b> e congelar os
            números?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            A movimentação por produto é congelada junto, e movimento com data dentro do
            período passa a ser recusado — só quem tem a permissão de lançamento retroativo
            passa.
          </p>
        </Confirmacao>
      )}

      {confirmando?.tipo === "reabrir" && (
        <Confirmacao
          titulo="Reabrir o período"
          rotuloConfirmar="Reabrir"
          perigo
          ocupado={ocupado}
          aoCancelar={() => setConfirmando(null)}
          aoConfirmar={() => {
            const alvo = confirmando;
            setConfirmando(null);
            void reabrir(alvo.id);
          }}
        >
          <p>
            Reabrir o período de <b>{confirmando.competencia}</b>?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            O período volta a aceitar lançamento retroativo — e o número que já foi levado ao
            dono pode mudar. Fechar de novo recalcula tudo.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
