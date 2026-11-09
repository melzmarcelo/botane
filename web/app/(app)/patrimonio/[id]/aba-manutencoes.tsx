"use client";

import { FormEvent, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo, CampoMoeda, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { hoje } from "@/lib/datas";
import { moedaParaNumero, plural, reais } from "@/lib/numeros";
import { SITUACOES, apagarManutencao, dataBr, registrarManutencao, type BemDetalhe } from "@/lib/patrimonio";

import { diasAte } from "./form";

type Filtro = "TODAS" | "PREVENTIVA" | "CORRETIVA" | "GARANTIA";
const FILTROS: [Filtro, string][] = [
  ["TODAS", "Todas"], ["PREVENTIVA", "Preventivas"], ["CORRETIVA", "Corretivas"], ["GARANTIA", "Na garantia"],
];
const NOVA = { tipo: "PREVENTIVA", data: "", executado_por: "", custo: "", causa: "", descricao: "",
               situacao_depois: "", coberta_garantia: false };

/**
 * Aba Manutenções: o histórico (filtro por tipo, as recentes em destaque) e, embaixo, o
 * registro de uma nova.
 * ⚠️ Os ids `manutencao-tipo`, `manutencao-descricao`, `manutencao-registrar` e
 * `manutencao-lista` são os da bateria do navegador.
 */
export default function AbaManutencoes({ bem, podeRegistrar, aoMudar }: {
  bem: BemDetalhe; podeRegistrar: boolean; aoMudar: () => void;
}) {
  const aviso = useAviso();
  const [filtro, setFiltro] = useState<Filtro>("TODAS");
  const [m, setM] = useState({ ...NOVA, data: hoje() });
  const [gravando, setGravando] = useState(false);
  const emGarantia = ["ATIVA", "VENCE_30"].includes(bem.status_garantia);

  const lista = bem.manutencoes.filter((x) =>
    filtro === "TODAS" || (filtro === "GARANTIA" ? x.coberta_garantia : x.tipo === filtro));
  const total = lista.reduce((s, x) => s + Number(x.custo ?? 0), 0);

  async function registrar(e: FormEvent) {
    e.preventDefault();
    setGravando(true);
    try {
      const r = await registrarManutencao(bem.id, {
        tipo: m.tipo, data: m.data, executado_por: m.executado_por.trim() || null,
        custo: m.custo ? moedaParaNumero(m.custo) : null, descricao: m.descricao.trim() || null,
        causa: m.causa.trim() || null, coberta_garantia: m.coberta_garantia,
        situacao_depois: m.situacao_depois || null,
      });
      aviso.sucesso(r.message);
      setM({ ...NOVA, tipo: m.tipo, data: m.data });
      aoMudar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível registrar");
    } finally {
      setGravando(false);
    }
  }

  async function tirar(id: number) {
    try {
      aviso.sucesso((await apagarManutencao(id)).message);
      aoMudar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível apagar");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Cartao titulo="Histórico de manutenção"
              descricao={bem.manutencoes.length
                ? `${plural(lista.length, "registro", "registros")} · ${reais(total)}`
                : "Nenhuma manutenção registrada ainda."}
              acao={bem.manutencoes.length ? (
                <div className="seg-grade" role="group" aria-label="filtrar por tipo">
                  {FILTROS.map(([v, n]) => (
                    <button key={v} type="button" aria-pressed={filtro === v} onClick={() => setFiltro(v)}>{n}</button>
                  ))}
                </div>
              ) : undefined}>
        {bem.manutencoes.length > 0 && (lista.length ? (
          <div className="grid-rolante">
            <table className="tabela" id="manutencao-lista">
              <thead>
                <tr>
                  <th>Data</th><th>Tipo</th><th>O que gerou</th><th>O que foi feito</th><th>Feito por</th>
                  <th className="num">Custo</th><th>Garantia</th><th>Registrado por</th>{podeRegistrar && <th />}
                </tr>
              </thead>
              <tbody>
                {lista.map((x) => {
                  const recente = diasAte(hoje(), x.data.slice(0, 10)) <= bem.recente_dias;
                  return (
                    <tr key={x.id} className={recente ? "bg-erva-claro/40" : undefined}>
                      <td className="whitespace-nowrap">
                        {dataBr(x.data)}{recente && <span className="ml-2"><Etiqueta cor="erva">recente</Etiqueta></span>}
                      </td>
                      <td>{x.tipo_txt}</td>
                      <td className="text-[13.5px]">{x.causa ?? "—"}</td>
                      <td className="text-[13.5px]">{x.descricao ?? "—"}</td>
                      <td>{x.executado_por ?? "—"}</td>
                      <td className="num">{x.custo !== null ? reais(x.custo) : "—"}</td>
                      <td>{x.coberta_garantia ? "Cobriu" : "—"}</td>
                      <td className="text-[13px] text-suave">{x.registrado_por ?? "—"}</td>
                      {podeRegistrar && (
                        <td><button type="button" className="link-acao text-[13px]" onClick={() => void tirar(x.id)}>apagar</button></td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : <Vazio>Nenhum registro deste tipo.</Vazio>)}
      </Cartao>

      {podeRegistrar && (
        <Cartao titulo="Registrar manutenção" descricao="O que FOI feito — a data não pode ser no futuro.">
          <form onSubmit={registrar} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" id="manutencao-form">
            <Campo rotulo="Tipo">
              <select className="campo" id="manutencao-tipo" value={m.tipo} onChange={(e) => setM({ ...m, tipo: e.target.value })}>
                <option value="PREVENTIVA">Preventiva</option>
                <option value="CORRETIVA">Corretiva</option>
              </select>
            </Campo>
            <Campo rotulo="Data">
              <input type="date" className="campo" id="manutencao-data" required max={hoje()} value={m.data}
                     onChange={(e) => setM({ ...m, data: e.target.value })} />
            </Campo>
            <Campo rotulo="O que gerou" opcional className="sm:col-span-2" dica="preventiva programada, parou de gelar, barulho…">
              <input className="campo" id="manutencao-causa" maxLength={120} value={m.causa}
                     onChange={(e) => setM({ ...m, causa: e.target.value })} />
            </Campo>
            <Campo rotulo="O que foi feito" opcional className="sm:col-span-2 lg:col-span-4">
              <input className="campo" id="manutencao-descricao" maxLength={500} value={m.descricao}
                     onChange={(e) => setM({ ...m, descricao: e.target.value })} />
            </Campo>
            <Campo rotulo="Feito por" opcional>
              <input className="campo" maxLength={120} value={m.executado_por}
                     onChange={(e) => setM({ ...m, executado_por: e.target.value })} />
            </Campo>
            <Campo rotulo="Custo" opcional dica="o que a casa pagou">
              <CampoMoeda valor={m.custo} aoMudar={(v) => setM({ ...m, custo: v })} />
            </Campo>
            <Campo rotulo="Depois da visita" opcional>
              <select className="campo" id="manutencao-situacao" value={m.situacao_depois}
                      onChange={(e) => setM({ ...m, situacao_depois: e.target.value })}>
                <option value="">não muda</option>
                {["EM_USO", "EM_MANUTENCAO", "PARADO", "DESATIVADO"].map((v) => <option key={v} value={v}>{SITUACOES[v]}</option>)}
              </select>
            </Campo>
            <label className="linha-interruptor self-end">
              <input type="checkbox" role="switch" className="interruptor" id="manutencao-garantia"
                     checked={m.coberta_garantia} onChange={(e) => setM({ ...m, coberta_garantia: e.target.checked })} />
              <span className="text-[14px] font-semibold">
                Garantia cobriu
                {emGarantia && <span className="block text-[12.5px] font-normal text-suave">em garantia até {dataBr(bem.garantia_ate)}</span>}
              </span>
            </label>
            <div className="sm:col-span-2 lg:col-span-4">
              <button type="submit" className="btn btn-primario" id="manutencao-registrar" disabled={gravando} aria-busy={gravando}>
                Registrar
              </button>
            </div>
          </form>
        </Cartao>
      )}
    </div>
  );
}
