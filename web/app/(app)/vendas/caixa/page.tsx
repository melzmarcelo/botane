"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import { conferenciaCaixa, gravarContado, type ConferenciaCaixa, type DiaCaixa } from "@/lib/caixa";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { moedaParaNumero, reais } from "@/lib/numeros";

/**
 * A conferência do caixa (migração 161, etapa 3 das finalizadoras, pedido do dono de 24/11/2026).
 *
 * 🔑 **O esperado vem das finalizadoras do PDV**: dinheiro recebido − troco. Quem fecha o caixa
 * conta a gaveta, digita o contado, e a diferença aparece na hora (sobra positiva, falta
 * negativa). Só o contado é gravado, com quem conferiu.
 * ⚠️ Dia com venda sem forma de pagamento tem o esperado incompleto, e a linha diz isso.
 */

const hoje = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const diasAtras = (n: number) => {
  const d = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
};
const dataBr = (s: string) => {
  const d = new Date(`${s}T12:00:00`);
  return d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
};
const paraCampo = (v: number | null) => (v === null ? "" : v.toFixed(2).replace(".", ","));

function Linha({ d, aoGravar }: { d: DiaCaixa; aoGravar: () => void }) {
  const aviso = useAviso();
  const [contado, setContado] = useState(paraCampo(d.contado));
  const [obs, setObs] = useState(d.observacao ?? "");
  const [ocupado, setOcupado] = useState(false);
  const n = moedaParaNumero(contado);
  const diferenca = n === null ? null : Math.round((n - d.esperado) * 100) / 100;
  const mudou = (n ?? null) !== d.contado || (obs.trim() || null) !== (d.observacao || null);

  async function gravar() {
    if (n === null || n < 0) return aviso.erro("Digite quanto havia na gaveta.");
    setOcupado(true);
    try {
      const r = await gravarContado(d.data, n, obs.trim() || null);
      aviso.sucesso(r.message);
      aoGravar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <li className="grid gap-2 py-3 md:grid-cols-[7rem_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_8rem_minmax(0,1fr)_minmax(0,1.6fr)_auto] md:items-center md:gap-3"
        data-caixa-dia={d.data}>
      <span className="font-semibold capitalize">{dataBr(d.data)}</span>
      <span className="text-[13.5px]"><span className="text-suave md:hidden">recebido </span>{reais(d.recebido)}</span>
      <span className="text-[13.5px]"><span className="text-suave md:hidden">troco </span>{reais(d.troco)}</span>
      <span className="font-semibold">
        <span className="font-normal text-suave md:hidden">esperado </span>{reais(d.esperado)}
        {d.sem_forma > 0 && (
          <span className="block text-[12px] font-normal text-alerta">
            {d.sem_forma} venda(s) sem forma: esperado incompleto
          </span>
        )}
      </span>
      <input className="campo text-right" inputMode="decimal" aria-label={`contado em ${d.data}`}
             data-caixa-contado placeholder="contado" value={contado}
             onFocus={(e) => e.target.select()} onChange={(e) => setContado(e.target.value)} />
      <span className={`font-semibold tabular-nums ${diferenca === null ? "text-suave"
        : Math.abs(diferenca) < 0.005 ? "text-erva" : "text-erro"}`} data-caixa-diferenca>
        {diferenca === null ? "—" : Math.abs(diferenca) < 0.005 ? "bateu"
          : `${diferenca > 0 ? "sobra" : "falta"} ${reais(Math.abs(diferenca))}`}
      </span>
      <input className="campo" maxLength={300} aria-label={`observação de ${d.data}`}
             placeholder="observação (opcional)" value={obs} onChange={(e) => setObs(e.target.value)} />
      <span className="flex items-center justify-end gap-2">
        {d.conferido_por && !mudou && (
          <span className="text-[12px] text-suave" title={d.conferido_em ?? undefined}>por {d.conferido_por}</span>
        )}
        <button type="button" className={`btn btn-pequeno ${mudou ? "btn-primario" : "btn-secundario"}`}
                data-caixa-gravar disabled={ocupado || !mudou} onClick={() => void gravar()}>
          {d.contado === null ? "Conferir" : "Corrigir"}
        </button>
      </span>
    </li>
  );
}

export default function PaginaCaixa() {
  const [inicio, setInicio] = useEstadoNaUrl<string>("de", "", { atraso: 0 });
  const [fim, setFim] = useEstadoNaUrl<string>("ate", "", { atraso: 0 });
  const de = inicio || diasAtras(13);
  const ate = fim || hoje();
  const [dados, setDados] = useState<ConferenciaCaixa | null>(null);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    setErro("");
    try {
      setDados(await conferenciaCaixa(de, ate));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o caixa");
    }
  }, [de, ate]);

  useEffect(() => { void carregar(); }, [carregar]);
  const t = dados?.totais;

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela caminho="Vendas" titulo="Conferência do caixa"
                     explica={<>O dinheiro que devia estar na gaveta em cada dia, pelas formas de
                       pagamento do PDV (recebido menos o troco). Conte a gaveta, digite o valor e a
                       diferença aparece na hora.</>}
                     acoes={<BotaoExportar relatorio="caixa" iniciais={{ inicio: de, fim: ate }} />} />

      <Cartao>
        <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
          <span className="text-suave">de</span>
          <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="de"
                 value={de} max={ate} onChange={(e) => setInicio(e.target.value)} />
          <span className="text-suave">até</span>
          <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="até"
                 value={ate} min={de} max={hoje()} onChange={(e) => setFim(e.target.value)} />
          {t && (
            <span className="ml-auto flex flex-wrap gap-x-4 gap-y-1" id="caixa-totais">
              <span>esperado <b>{reais(t.esperado)}</b></span>
              <span>{t.conferidos} conferido(s)</span>
              {t.a_conferir > 0 && <span className="text-alerta">{t.a_conferir} a conferir</span>}
              {t.conferidos > 0 && (
                <span className={Math.abs(t.diferenca) < 0.005 ? "text-erva" : "text-erro"}>
                  diferença {reais(t.diferenca)}
                </span>
              )}
            </span>
          )}
        </div>
      </Cartao>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao>
        {!dados ? (
          <Carregando />
        ) : !dados.dias.length ? (
          <Vazio>Nenhuma venda no período.</Vazio>
        ) : (
          <>
            <div className="hidden border-b border-linha pb-2 text-[12.5px] font-semibold text-suave md:grid md:grid-cols-[7rem_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_8rem_minmax(0,1fr)_minmax(0,1.6fr)_auto] md:gap-3"
                 aria-hidden>
              <span>Dia</span><span>Recebido</span><span>Troco</span><span>Esperado</span>
              <span>Contado</span><span>Diferença</span><span>Observação</span><span />
            </div>
            <ul className="divide-y divide-[var(--borda)]" id="caixa-dias">
              {dados.dias.map((d) => (
                <Linha key={`${d.data}-${d.contado}-${d.observacao}`} d={d} aoGravar={() => void carregar()} />
              ))}
            </ul>
          </>
        )}
      </Cartao>
    </div>
  );
}
