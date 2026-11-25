"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import { dataBr, DiaFluxo, Fluxo, fluxoDeCaixa } from "@/lib/contas-pagar";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { reais, textoParaNumero } from "@/lib/numeros";
import { useSessao } from "@/lib/sessao";

/**
 * Fluxo de caixa (etapa 4 do Financeiro, 25/11/2026 — `docs/financeiro-estudo.md`).
 *
 * 🔑 O que entra (vendas por forma, contas a receber recebidas, e a previsão de vendas) × o que
 * sai (contas pagas, a pagar, contas fixas que ainda vão nascer, taxas de cartão), dia a dia, com
 * o saldo acumulado. Nada se grava aqui: tudo sai de `GET /contas-pagar/fluxo`, e o relatório
 * `fluxo-caixa` usa a mesma função.
 * ⚠️ O saldo do banco não está no sistema: quem quiser o saldo de verdade digita o do início do
 * período; sem ele, o acumulado parte de zero (e a tela diz isso).
 */

const iso = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const somarDias = (n: number) => { const d = new Date(); d.setDate(d.getDate() + n); return iso(d); };
const inicioDoMes = (desloca = 0) => { const h = new Date(); return iso(new Date(h.getFullYear(), h.getMonth() + desloca, 1)); };
const fimDoMes = (desloca = 0) => { const h = new Date(); return iso(new Date(h.getFullYear(), h.getMonth() + desloca + 1, 0)); };
const SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const diaSemana = (s: string) => SEMANA[new Date(`${s}T12:00:00`).getDay()];

function Numero({ rotulo, valor, sub, tom }: { rotulo: string; valor: string; sub?: string; tom?: "erro" | "bom" }) {
  return (
    <div className="min-w-0" data-numero-fluxo={rotulo}>
      <p className="rotulo">{rotulo}</p>
      <p className={`mono mt-1 text-[20px] font-bold leading-none ${tom === "erro" ? "text-erro" : tom === "bom" ? "text-erva-escuro" : ""}`}>{valor}</p>
      {sub && <p className="mt-1 text-[12.5px] text-suave">{sub}</p>}
    </div>
  );
}

/** As partes de um lado do dia, em texto miúdo: "vendas 1.200 · recebido 80". */
function Partes({ itens }: { itens: [string, number][] }) {
  const v = itens.filter(([, n]) => n);
  if (!v.length) return null;
  return <p className="text-[11.5px] leading-tight text-suave">{v.map(([r, n]) => `${r} ${reais(n)}`).join(" · ")}</p>;
}

function LinhaDia({ d }: { d: DiaFluxo }) {
  const aPagar = `/financeiro/pagar?${new URLSearchParams({ aba: "A_PAGAR", de: d.data, ate: d.data })}`;
  return (
    <tr className={`align-top ${d.hoje ? "bg-alerta-claro/50" : d.passado ? "" : ""}`} data-dia-fluxo={d.data}>
      <td className="whitespace-nowrap py-2 pr-3">
        <b>{dataBr(d.data).slice(0, 5)}</b> <span className="text-suave">{diaSemana(d.data)}</span>
        {d.hoje && <span className="ml-1 text-alerta">hoje</span>}
        {!d.passado && !d.hoje && <span className="ml-1 text-[11px] text-suave">previsto</span>}
      </td>
      <td className="py-2 pr-3 text-right">
        <span className="mono font-semibold text-erva-escuro">{d.entradas ? reais(d.entradas) : "—"}</span>
        <Partes itens={[["vendas", d.vendas], ["previsão", d.vendas_previstas], ["recebido", d.receber]]} />
      </td>
      <td className="py-2 pr-3 text-right">
        <span className="mono font-semibold text-erro">{d.saidas ? reais(d.saidas) : "—"}</span>
        <Partes itens={[["pago", d.pago], ["a pagar", d.a_pagar], ["fixas", d.fixas], ["taxas", d.taxas]]} />
        {d.a_pagar > 0 && (
          <Link href={aPagar} className="text-[11.5px] text-erva-escuro underline">
            {d.n_a_pagar} conta(s){d.atrasado > 0 && <> · {reais(d.atrasado)} atrasado</>}
          </Link>
        )}
        {d.fixas_previstas.length > 0 && (
          <p className="text-[11.5px] text-suave" data-fixas-previstas={d.data}>
            {d.fixas_previstas.map((f) => f.descricao).join(", ")} (vai nascer)
          </p>
        )}
      </td>
      <td className={`mono py-2 pr-3 text-right ${d.saldo < 0 ? "text-erro" : ""}`}>{reais(d.saldo)}</td>
      <td className={`mono py-2 text-right font-semibold ${d.acumulado < 0 ? "text-erro" : ""}`}>{reais(d.acumulado)}</td>
    </tr>
  );
}

export default function PaginaFluxoDeCaixa() {
  const { unidade } = useSessao();
  const padraoDe = inicioDoMes(), padraoAte = somarDias(30);
  const [de, setDe] = useEstadoNaUrl<string>("de", padraoDe, { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", padraoAte, { atraso: 0 });
  const [previsao, setPrevisao] = useEstadoNaUrl<boolean>("previsao", true, { atraso: 0 });
  const [saldoTexto, setSaldoTexto] = useEstadoNaUrl<string>("saldo", "");
  const [todos, setTodos] = useState(false);
  const [dados, setDados] = useState<Fluxo | null>(null);
  const [erro, setErro] = useState("");
  const ultimo = useRef(0);
  const saldoInicial = textoParaNumero(saldoTexto) ?? 0;

  const carregar = useCallback(async () => {
    const pedido = ++ultimo.current;
    setErro("");
    try {
      const d = await fluxoDeCaixa(de, ate, previsao, saldoInicial);
      if (pedido === ultimo.current) setDados(d);
    } catch (e) {
      if (pedido !== ultimo.current) return;
      setDados(null);
      setErro(e instanceof Error ? e.message : "Falha ao carregar o fluxo de caixa");
    }
  }, [de, ate, previsao, saldoInicial, unidade]);
  useEffect(() => { void carregar(); }, [carregar]);

  const escolher = (a: string, b: string) => { setDe(a); setAte(b); };
  const ativo = (a: string, b: string) => (de === a && ate === b ? "btn-primario" : "btn-secundario");
  // O dia em que o caixa fica mais baixo: é a pergunta de quem olha um fluxo.
  const menor = useMemo(() => (dados?.dias ?? []).reduce<DiaFluxo | null>(
    (m, d) => (!m || d.acumulado < m.acumulado ? d : m), null), [dados]);
  const visiveis = (dados?.dias ?? []).filter((d) => todos || d.hoje || d.entradas || d.saidas);
  const t = dados?.totais;
  const semData = dados ? dados.a_receber_sem_data.em_cobranca + dados.a_receber_sem_data.sem_lote : 0;

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela caminho="Financeiro" titulo="Fluxo de caixa"
                     explica={<>O que entra (vendas por forma de pagamento e contas a receber) e o que sai
                       (contas pagas, a pagar, contas fixas e taxas de cartão), dia a dia, com o saldo
                       acumulado. Do dia de hoje em diante é previsão.</>}
                     acoes={<BotaoExportar relatorio="fluxo-caixa" iniciais={{ inicio: de, fim: ate }} />} />

      <Cartao>
        <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
          <button type="button" className={`btn btn-pequeno ${ativo(padraoDe, padraoAte)}`} id="fluxo-padrao"
                  onClick={() => escolher(padraoDe, padraoAte)}>Este mês + 30 dias</button>
          <button type="button" className={`btn btn-pequeno ${ativo(somarDias(0), somarDias(30))}`} id="fluxo-proximos"
                  onClick={() => escolher(somarDias(0), somarDias(30))}>Próximos 30 dias</button>
          <button type="button" className={`btn btn-pequeno ${ativo(inicioDoMes(-1), fimDoMes(-1))}`} id="fluxo-mes-passado"
                  onClick={() => escolher(inicioDoMes(-1), fimDoMes(-1))}>Mês passado</button>
          <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="de" id="fluxo-de" value={de}
                 onChange={(e) => setDe(e.target.value)} />
          <span className="text-suave">até</span>
          <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="até" id="fluxo-ate" value={ate}
                 onChange={(e) => setAte(e.target.value)} />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13.5px]">
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" className="h-4 w-4" id="fluxo-previsao" checked={previsao}
                   onChange={(e) => setPrevisao(e.target.checked)} />
            Contar a previsão de vendas
            <span className="text-suave">(média do mesmo dia da semana nas últimas {dados?.semanas_da_previsao ?? 4} semanas)</span>
          </label>
          <label className="inline-flex items-center gap-2">
            Saldo no início do período
            <input className="campo mono py-1" style={{ width: "9rem" }} inputMode="decimal" id="fluxo-saldo-inicial"
                   placeholder="0,00" value={saldoTexto} onChange={(e) => setSaldoTexto(e.target.value)} />
          </label>
        </div>
      </Cartao>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!dados && !erro && <Carregando />}

      {dados && t && (
        <>
          <Cartao>
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4" id="fluxo-totais">
              <Numero rotulo="Entradas" valor={reais(t.entradas)}
                      sub={t.vendas_previstas ? `${reais(t.vendas_previstas)} de previsão` : undefined} tom="bom" />
              <Numero rotulo="Saídas" valor={reais(t.saidas)}
                      sub={t.a_pagar + t.fixas ? `${reais(t.a_pagar + t.fixas)} ainda a pagar` : undefined} />
              <Numero rotulo="Saldo do período" valor={reais(t.saldo)} tom={t.saldo < 0 ? "erro" : undefined} />
              {menor && (
                <Numero rotulo="Menor saldo" valor={reais(menor.acumulado)} tom={menor.acumulado < 0 ? "erro" : undefined}
                        sub={`em ${dataBr(menor.data).slice(0, 5)}${dados.saldo_inicial ? "" : " · acumulado a partir de zero"}`} />
              )}
            </div>

            <div className="mt-4 flex flex-col gap-2">
              {dados.atrasado.contas > 0 && (
                <Aviso tipo="erro"><span id="fluxo-atrasado">{dados.atrasado.contas} conta(s) atrasada(s), {reais(dados.atrasado.valor)}:
                  entram como saída de hoje.</span></Aviso>
              )}
              {dados.sem_forma.cupons > 0 && (
                <Aviso tipo="info"><span id="fluxo-sem-forma">{dados.sem_forma.cupons} venda(s) sem forma de pagamento
                  ({reais(dados.sem_forma.valor)}) entram como “não informado”. Em Integrações ▸ PDV Legal dá para reler
                  as formas do PDV.</span></Aviso>
              )}
              {!dados.taxas_configuradas && (
                <p className="text-[12.5px] text-suave" id="fluxo-sem-taxas">As taxas de cartão não estão configuradas
                  nesta loja (Vendas ▸ Caixa): o fluxo não desconta o que a maquininha leva.</p>
              )}
              {semData > 0 && (
                <p className="text-[12.5px] text-suave" id="fluxo-sem-data">
                  Fora do fluxo, por não ter data: {reais(semData)} a receber
                  ({reais(dados.a_receber_sem_data.em_cobranca)} em cobrança e {reais(dados.a_receber_sem_data.sem_lote)} de
                  consumo ainda não cobrado). <Link href="/receber" className="text-erva-escuro underline">Contas a receber</Link>
                </p>
              )}
              <p className="text-[12px] text-suave">O cartão conta no dia da venda, não no dia do depósito. Venda com pessoa
                entra quando o lote é recebido; vale-presente, permuta e desconto em folha não entram.</p>
            </div>

            {dados.por_forma.length > 0 && (
              <ul className="mt-4 flex flex-wrap gap-2" id="fluxo-formas">
                {dados.por_forma.map((f) => (
                  <li key={f.forma} className="rounded-lg border border-linha px-3 py-2" data-forma-fluxo={f.forma}>
                    <p className="rotulo">{f.rotulo}</p>
                    <p className="mono font-semibold">{reais(f.valor)}</p>
                  </li>
                ))}
              </ul>
            )}
          </Cartao>

          <Cartao>
            <div className="mb-2 flex flex-wrap items-center gap-3">
              <h2 className="font-bold">Dia a dia</h2>
              <label className="ml-auto inline-flex items-center gap-2 text-[13px]">
                <input type="checkbox" className="h-4 w-4" id="fluxo-todos" checked={todos}
                       onChange={(e) => setTodos(e.target.checked)} />
                Mostrar os dias sem movimento
              </label>
            </div>
            {!visiveis.length ? <Vazio>Nada entra nem sai no período.</Vazio> : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-[13.5px]" id="fluxo-dias">
                  <thead>
                    <tr className="border-b border-linha text-left text-[12px] text-suave">
                      <th className="py-1 pr-3 font-semibold">Dia</th>
                      <th className="py-1 pr-3 text-right font-semibold">Entradas</th>
                      <th className="py-1 pr-3 text-right font-semibold">Saídas</th>
                      <th className="py-1 pr-3 text-right font-semibold">Saldo do dia</th>
                      <th className="py-1 text-right font-semibold">Acumulado</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--borda)]">
                    {visiveis.map((d) => <LinhaDia key={d.data} d={d} />)}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-linha font-semibold" id="fluxo-rodape">
                      <td className="py-2 pr-3">Período</td>
                      <td className="mono py-2 pr-3 text-right text-erva-escuro">{reais(t.entradas)}</td>
                      <td className="mono py-2 pr-3 text-right text-erro">{reais(t.saidas)}</td>
                      <td className="mono py-2 pr-3 text-right">{reais(t.saldo)}</td>
                      <td className="mono py-2 text-right">{reais(t.saldo_final)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </Cartao>
        </>
      )}
    </div>
  );
}
