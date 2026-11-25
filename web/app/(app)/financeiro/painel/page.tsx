"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import { dataBr, FORMAS, NumerosPainel, Painel, painelFinanceiro } from "@/lib/contas-pagar";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { reais } from "@/lib/numeros";
import { useSessao } from "@/lib/sessao";

/**
 * Painel do Financeiro (etapa 2 do módulo, 25/11/2026 — `docs/financeiro-estudo.md`).
 *
 * 🔑 Duas perguntas: "o que vem pela frente" (atrasado, próximos 14 dias, baixas automáticas a
 * conferir no banco — não depende do período) e "o mês" (pago × em aberto por categoria,
 * pessoa e forma). Mesma regra da tela de contas: pago pela data do pagamento, em aberto pelo
 * vencimento. Tudo sai de `GET /contas-pagar/painel`; o relatório `painel-financeiro` usa a
 * mesma função.
 */

const iso = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
function mes(desloca: number): [string, string] {
  const h = new Date();
  return [iso(new Date(h.getFullYear(), h.getMonth() + desloca, 1)),
          iso(new Date(h.getFullYear(), h.getMonth() + desloca + 1, 0))];
}
const SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const diaSemana = (s: string) => SEMANA[new Date(`${s}T12:00:00`).getDay()];

function Numero({ rotulo, valor, sub, tom, href }: {
  rotulo: string; valor: string; sub?: string; tom?: "alerta" | "erro"; href?: string;
}) {
  const corpo = (
    <>
      <p className="rotulo">{rotulo}</p>
      <p className={`mono mt-1 text-[20px] font-bold leading-none ${tom === "erro" ? "text-erro" : tom === "alerta" ? "text-alerta" : ""}`}>{valor}</p>
      {sub && <p className="mt-1 text-[12.5px] text-suave">{sub}</p>}
    </>
  );
  return href
    ? <Link href={href} className="min-w-0 rounded-lg hover:bg-erva-claro/40" data-numero-painel={rotulo}>{corpo}</Link>
    : <div className="min-w-0" data-numero-painel={rotulo}>{corpo}</div>;
}

/** Uma linha com a barra pago (cheia) + em aberto (clara), na escala do maior da lista. */
function Barra({ nome, n, maior }: { nome: string; n: NumerosPainel; maior: number }) {
  const largura = (v: number) => `${maior > 0 ? Math.max((v / maior) * 100, v > 0 ? 1 : 0) : 0}%`;
  return (
    <li className="py-2" data-linha-painel={nome}>
      <div className="flex flex-wrap items-baseline gap-x-3">
        <span className="min-w-0 flex-1 truncate font-semibold">{nome}</span>
        <span className="mono font-semibold">{reais(n.total)}</span>
      </div>
      <div className="mt-1 flex h-2.5 overflow-hidden rounded-full bg-linha/60">
        <span className="h-full bg-erva" style={{ width: largura(n.pago) }} />
        <span className="h-full bg-alerta" style={{ width: largura(n.em_aberto) }} />
      </div>
      <p className="mt-0.5 text-[12px] text-suave">
        pago {reais(n.pago)}{n.em_aberto > 0 && <> · em aberto {reais(n.em_aberto)}</>}
      </p>
    </li>
  );
}

export default function PaginaPainelFinanceiro() {
  const { unidade } = useSessao();
  const [esteDe, esteAte] = mes(0);
  const [de, setDe] = useEstadoNaUrl<string>("de", esteDe, { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", esteAte, { atraso: 0 });
  const [dados, setDados] = useState<Painel | null>(null);
  const [erro, setErro] = useState("");
  const ultimo = useRef(0);

  const carregar = useCallback(async () => {
    const pedido = ++ultimo.current;
    setErro("");
    try {
      const d = await painelFinanceiro(de, ate);
      if (pedido === ultimo.current) setDados(d);
    } catch (e) {
      if (pedido !== ultimo.current) return;
      setDados(null);
      setErro(e instanceof Error ? e.message : "Falha ao carregar o painel");
    }
  }, [de, ate, unidade]);
  useEffect(() => { void carregar(); }, [carregar]);

  const escolherMes = (desloca: number) => { const [a, b] = mes(desloca); setDe(a); setAte(b); };
  const r = dados?.resumo;
  const maiorCat = Math.max(0, ...(dados?.por_categoria ?? []).map((c) => c.total));
  const maiorPessoa = Math.max(0, ...(dados?.por_pessoa ?? []).map((c) => c.total));
  const maiorDia = Math.max(0, ...(dados?.agenda ?? []).map((a) => a.valor));
  const pagar = (q: Record<string, string>) => `/financeiro/pagar?${new URLSearchParams(q)}`;

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela caminho="Financeiro" titulo="Painel"
                     explica={<>O que vence pela frente e como fica o mês: quanto já foi pago e quanto
                       ainda está em aberto, por categoria, pessoa e forma. As baixas automáticas dos
                       últimos dias ficam à vista para alguém conferir no banco.</>}
                     acoes={<BotaoExportar relatorio="painel-financeiro" iniciais={{ inicio: de, fim: ate }} />} />

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!dados && !erro && <Carregando />}

      {dados && r && (
        <>
          <Cartao>
            <h2 className="mb-3 font-bold">Pela frente</h2>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4" id="painel-frente">
              <Numero rotulo="Atrasado" valor={reais(r.atrasado)} sub={`${r.n_atrasado} conta(s)`}
                      tom={r.n_atrasado ? "erro" : undefined} href={pagar({ aba: "A_PAGAR" })} />
              <Numero rotulo="Vence hoje" valor={reais(r.hoje)} sub={`${r.n_hoje} conta(s)`}
                      tom={r.n_hoje ? "alerta" : undefined}
                      href={pagar({ aba: "A_PAGAR", de: dados.hoje, ate: dados.hoje })} />
              <Numero rotulo="Próximos 7 dias" valor={reais(r.semana)} />
              <Numero rotulo="Agendado" valor={reais(r.agendado)} sub={`${r.n_agendado} conta(s)`}
                      href={pagar({ aba: "AGENDADO" })} />
            </div>

            <h3 className="mb-1 mt-5 text-[14px] font-semibold">Próximos 14 dias</h3>
            {!dados.agenda.length ? <Vazio>Nada vence nos próximos 14 dias.</Vazio> : (
              <ul className="divide-y divide-[var(--borda)]" id="painel-agenda">
                {dados.agenda.map((a) => (
                  <li key={a.data} data-dia-painel={a.data}>
                    <Link href={pagar({ aba: a.agendado >= a.valor ? "AGENDADO" : "A_PAGAR", de: a.data, ate: a.data })}
                          className="flex items-center gap-3 py-2 hover:bg-erva-claro/40">
                      <span className="w-24 shrink-0 text-[13.5px]">
                        <b>{dataBr(a.data).slice(0, 5)}</b> <span className="text-suave">{diaSemana(a.data)}</span>
                        {a.data === dados.hoje && <span className="ml-1 text-alerta">hoje</span>}
                      </span>
                      <span className="hidden h-2 flex-1 overflow-hidden rounded-full bg-linha/60 sm:flex">
                        <span className="h-full bg-erva" style={{ width: `${maiorDia ? (a.agendado / maiorDia) * 100 : 0}%` }} />
                        <span className="h-full bg-alerta" style={{ width: `${maiorDia ? ((a.valor - a.agendado) / maiorDia) * 100 : 0}%` }} />
                      </span>
                      <span className="ml-auto text-[12.5px] text-suave sm:ml-0">
                        {a.contas} conta(s){a.agendado > 0 && <> · {reais(a.agendado)} agendado</>}
                      </span>
                      <span className="mono w-28 text-right font-semibold">{reais(a.valor)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}

            {dados.baixadas_sozinhas.length > 0 && (
              <div className="mt-5 rounded-lg bg-alerta-claro/60 p-3" id="painel-sozinhas">
                <h3 className="text-[14px] font-semibold">Baixadas sozinhas nos últimos 7 dias</h3>
                <p className="text-[12.5px] text-suave">A baixa automática não confere o banco. Se algum
                  pagamento não saiu, estorne a baixa em Contas a pagar ▸ Pagos.</p>
                <ul className="mt-2 divide-y divide-[var(--borda)]">
                  {dados.baixadas_sozinhas.map((s) => (
                    <li key={s.id} className="flex flex-wrap items-center gap-x-3 py-1.5 text-[13.5px]" data-sozinha={s.id}>
                      <span className="w-12 text-suave">{dataBr(s.pago_em).slice(0, 5)}</span>
                      <span className="min-w-0 flex-1"><b>{s.pessoa}</b> · {s.descricao}
                        {s.forma && <span className="text-suave"> ({FORMAS[s.forma]})</span>}</span>
                      <span className="mono font-semibold">{reais(s.valor)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Cartao>

          <Cartao>
            <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
              <h2 className="mr-2 font-bold">Período</h2>
              <button type="button" className={`btn btn-pequeno ${de === esteDe && ate === esteAte ? "btn-primario" : "btn-secundario"}`}
                      id="painel-este-mes" onClick={() => escolherMes(0)}>Este mês</button>
              <button type="button" className={`btn btn-pequeno ${de === mes(-1)[0] && ate === mes(-1)[1] ? "btn-primario" : "btn-secundario"}`}
                      id="painel-mes-passado" onClick={() => escolherMes(-1)}>Mês passado</button>
              <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="de" value={de}
                     onChange={(e) => setDe(e.target.value)} />
              <span className="text-suave">até</span>
              <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="até" value={ate}
                     onChange={(e) => setAte(e.target.value)} />
            </div>

            <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3" id="painel-periodo">
              <Numero rotulo="Pago" valor={reais(dados.periodo.pago)} sub={`${dados.periodo.n_pago} conta(s)`}
                      href={pagar({ aba: "PAGO", de: dados.de, ate: dados.ate })} />
              <Numero rotulo="Em aberto" valor={reais(dados.periodo.em_aberto)} sub={`${dados.periodo.n_em_aberto} conta(s)`}
                      tom={dados.periodo.em_aberto ? "alerta" : undefined}
                      href={pagar({ aba: "A_PAGAR", de: dados.de, ate: dados.ate })} />
              <Numero rotulo="Total do período" valor={reais(dados.periodo.total)} />
            </div>
            <p className="mt-3 flex items-center gap-3 text-[12px] text-suave">
              <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-erva" /> pago</span>
              <span className="inline-flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-full bg-alerta" /> em aberto</span>
              <span>· pago pela data do pagamento, em aberto pelo vencimento</span>
            </p>

            {!dados.periodo.total ? <Vazio>Nenhuma conta no período.</Vazio> : (
              <div className="mt-4 grid gap-6 lg:grid-cols-2">
                <section>
                  <h3 className="text-[14px] font-semibold">Por categoria</h3>
                  <ul id="painel-categorias">
                    {dados.por_categoria.map((c) => <Barra key={c.categoria} nome={c.categoria} n={c} maior={maiorCat} />)}
                  </ul>
                </section>
                <section>
                  <h3 className="text-[14px] font-semibold">Por pessoa</h3>
                  <ul id="painel-pessoas">
                    {dados.por_pessoa.slice(0, 10).map((p) => <Barra key={p.id_pessoa} nome={p.pessoa} n={p} maior={maiorPessoa} />)}
                  </ul>
                  {dados.por_pessoa.length > 10 && (
                    <p className="mt-1 text-[12.5px] text-suave">e mais {dados.por_pessoa.length - 10} pessoa(s) no relatório</p>
                  )}
                </section>
                {dados.por_forma.length > 0 && (
                  <section className="lg:col-span-2">
                    <h3 className="text-[14px] font-semibold">Pago por forma</h3>
                    <ul className="mt-1 flex flex-wrap gap-2" id="painel-formas">
                      {dados.por_forma.map((f) => (
                        <li key={f.forma} className="rounded-lg border border-linha px-3 py-2" data-forma-painel={f.forma}>
                          <p className="rotulo">{f.rotulo}</p>
                          <p className="mono font-semibold">{reais(f.valor)}</p>
                          <p className="text-[12px] text-suave">{f.contas} conta(s)</p>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>
            )}
          </Cartao>
        </>
      )}
    </div>
  );
}
