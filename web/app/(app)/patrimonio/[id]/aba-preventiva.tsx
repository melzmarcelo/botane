"use client";

import { useState } from "react";

import { Campo, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { hoje } from "@/lib/datas";
import { COR_PREVENTIVA, PERIODICIDADES, dataBr, periodicidade, type BemDetalhe } from "@/lib/patrimonio";

import { diasAte, emDias, type Form } from "./form";

/**
 * Aba Preventiva: se o bem exige, de quanto em quanto tempo, a última, a próxima e as
 * próximas visitas.
 * 🔑 **"Exige preventiva" desligado = sem intervalo** (`preventiva_meses` nulo): é o que o
 * servidor já entende por "sem plano". Não há um sim/não gravado à parte, que poderia dizer
 * "exige" com o intervalo vazio.
 * ⚠️ A próxima e a agenda são do SERVIDOR (última + intervalo): mudar aqui só as move depois
 * de salvar — a tela diz isso em vez de calcular uma segunda versão da regra.
 */
export default function AbaPreventiva({ f, setF, travado, bem }: {
  f: Form; setF: (f: Form) => void; travado: boolean; bem: BemDetalhe | null;
}) {
  const [exige, setExige] = useState(!!f.preventiva_meses);
  const [outro, setOutro] = useState(!!f.preventiva_meses && !PERIODICIDADES[f.preventiva_meses]);
  const mudou = bem && (String(bem.preventiva_meses ?? "") !== (f.preventiva_meses ?? "")
                        || (bem.ultima_preventiva ?? "") !== (f.ultima_preventiva ?? ""));

  function ligar(sim: boolean) {
    setExige(sim);
    // Desligar tira o intervalo; a data da última fica (é história, não plano).
    if (!sim) setF({ ...f, preventiva_meses: "" });
  }

  return (
    <div className="flex flex-col gap-6">
      <Cartao titulo="Plano de preventiva"
              descricao="Com o intervalo e a data da última, o sistema calcula a próxima e avisa quando vencer."
              acao={
                <label className="linha-interruptor">
                  <input type="checkbox" role="switch" className="interruptor" id="bem-exige-preventiva"
                         aria-label="Exige preventiva" disabled={travado}
                         checked={exige} onChange={(e) => ligar(e.target.checked)} />
                  <span className="text-[14px] font-semibold">{exige ? "Exige preventiva" : "Sem preventiva"}</span>
                </label>
              }>
        {exige ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Campo rotulo="Periodicidade" dica="o que o fabricante ou o técnico indica">
              <select className="campo" id="bem-periodicidade" disabled={travado}
                      value={outro ? "outro" : f.preventiva_meses ?? ""}
                      onChange={(e) => {
                        const v = e.target.value;
                        setOutro(v === "outro");
                        setF({ ...f, preventiva_meses: v === "outro" ? f.preventiva_meses : v });
                      }}>
                <option value="">escolha</option>
                {Object.entries(PERIODICIDADES).map(([m, n]) => <option key={m} value={m}>{n}</option>)}
                <option value="outro">Outro intervalo</option>
              </select>
            </Campo>
            {outro && (
              <Campo rotulo="A cada (meses)">
                <input type="number" min={1} max={120} className="campo" id="bem-preventiva-meses" disabled={travado}
                       value={f.preventiva_meses ?? ""} onChange={(e) => setF({ ...f, preventiva_meses: e.target.value })} />
              </Campo>
            )}
            <Campo rotulo="Última preventiva" opcional dica="registrar uma preventiva atualiza sozinho">
              <input type="date" className="campo" id="bem-ultima-preventiva" disabled={travado} max={hoje()}
                     value={f.ultima_preventiva ?? ""} onChange={(e) => setF({ ...f, ultima_preventiva: e.target.value })} />
            </Campo>
            {bem && (
              <div className="flex flex-col justify-end gap-1">
                <span className="text-[13px] font-semibold text-suave">Próxima</span>
                <span className="text-[15px] font-bold" id="bem-proxima-preventiva">
                  {bem.proxima_preventiva ? dataBr(bem.proxima_preventiva) : "—"}
                </span>
                {bem.status_preventiva !== "FORA" && (
                  <span><Etiqueta cor={COR_PREVENTIVA[bem.status_preventiva] ?? "neutro"}>{bem.preventiva_txt}</Etiqueta></span>
                )}
              </div>
            )}
          </div>
        ) : (
          <p className="text-[14px] text-suave">
            O bem não entra nos avisos de preventiva. Ligue se o fabricante ou o técnico pede visita periódica.
          </p>
        )}
        {mudou && <p className="mt-4 text-[13px] text-alerta">A próxima e a agenda se refazem ao salvar.</p>}
      </Cartao>

      {bem && exige && (
        <Cartao titulo="Próximas visitas"
                descricao={`${periodicidade(bem.preventiva_meses)}, contando da última preventiva.`}>
          {bem.agenda_preventiva.length ? (
            <ol className="flex flex-col divide-y divide-linha" id="preventiva-agenda">
              {bem.agenda_preventiva.map((d, i) => {
                const dias = diasAte(d, hoje());
                return (
                  <li key={d} className="flex items-center justify-between gap-3 py-2.5">
                    <span className="mono text-[15px] font-semibold">{dataBr(d)}</span>
                    <span className={`text-[13px] ${i === 0 && dias < 0 ? "font-semibold text-erro" : "text-suave"}`}>
                      {i === 0 && dias < 0 ? `atrasada ${emDias(dias)}` : emDias(dias)}
                    </span>
                  </li>
                );
              })}
            </ol>
          ) : (
            <Vazio>
              {bem.status_preventiva === "FORA"
                ? `Bem ${bem.situacao_txt.toLowerCase()}: não cobra preventiva.`
                : "Falta o intervalo ou a data da última para montar a agenda."}
            </Vazio>
          )}
        </Cartao>
      )}
    </div>
  );
}
