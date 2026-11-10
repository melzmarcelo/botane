"use client";

import { Campo, Cartao, Vazio } from "@/components/ui";
import { reais } from "@/lib/numeros";
import { GARANTIA_TIPOS, dataBr, type BemDetalhe } from "@/lib/patrimonio";

import { emDias, somarMeses, type Form, type Muda } from "./form";

/**
 * Aba Garantia: a barra com a situação, o prazo, a assistência e os acionamentos.
 * 🔑 **Acionamento é a manutenção marcada "garantia cobriu"** (156), não um cadastro à
 * parte: duas listas da mesma visita divergiriam no primeiro registro esquecido.
 * ⚠️ A situação da barra é a do que está SALVO (vem do servidor); mudar a data aqui só
 * muda a barra depois de salvar.
 */
export default function AbaGarantia({ f, setF, muda, travado, bem }: {
  f: Form; setF: (f: Form) => void; muda: Muda; travado: boolean; bem: BemDetalhe | null;
}) {
  // 157: os meses refazem a data final a partir da compra; a data continua editável.
  function mudarMeses(v: string) {
    const calculada = somarMeses(f.data_compra, v);
    setF({ ...f, garantia_meses: v, garantia_ate: calculada || f.garantia_ate });
  }
  const acionamentos = bem?.manutencoes.filter((m) => m.coberta_garantia) ?? [];
  return (
    <div className="flex flex-col gap-6">
      {bem && <BarraGarantia bem={bem} />}
      <Cartao titulo="Garantia e assistência">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Campo rotulo="Tipo de garantia" opcional>
            <select className="campo" id="bem-garantia-tipo" disabled={travado}
                    value={f.garantia_tipo ?? ""} onChange={muda("garantia_tipo")}>
              <option value="">—</option>
              {Object.entries(GARANTIA_TIPOS).map(([v, n]) => <option key={v} value={v}>{n}</option>)}
            </select>
          </Campo>
          <Campo rotulo="Prazo (meses)" opcional
                 dica={f.data_compra ? "conta da data de compra" : "preencha a data de compra (aba Dados) para calcular"}>
            <input type="number" min={1} max={240} className="campo" id="bem-garantia-meses" disabled={travado}
                   value={f.garantia_meses ?? ""} onChange={(e) => mudarMeses(e.target.value)} />
          </Campo>
          <Campo rotulo="Garantia até" opcional dica="calculada pelo prazo — dá para corrigir">
            <input type="date" className="campo" id="bem-garantia-ate" disabled={travado}
                   value={f.garantia_ate ?? ""} onChange={muda("garantia_ate")} />
          </Campo>
          <div className="hidden lg:block" />
          <Campo rotulo="Assistência técnica" opcional className="sm:col-span-2">
            <input className="campo" id="bem-assistencia" maxLength={120} disabled={travado}
                   value={f.assistencia ?? ""} onChange={muda("assistencia")} />
          </Campo>
          <Campo rotulo="Contato" opcional>
            <input className="campo" maxLength={80} disabled={travado}
                   value={f.assistencia_contato ?? ""} onChange={muda("assistencia_contato")} />
          </Campo>
        </div>
      </Cartao>
      {bem && (
        <Cartao titulo="Acionamentos na garantia"
                descricao="As manutenções em que a garantia cobriu — marque “garantia cobriu” ao registrar.">
          {acionamentos.length ? (
            <div className="grid-rolante">
              <table className="tabela" id="garantia-acionamentos">
                <thead><tr><th>Data</th><th>Tipo</th><th>O que gerou</th><th>O que foi feito</th>
                  <th>Feito por</th><th className="num">Custo para a casa</th></tr></thead>
                <tbody>
                  {acionamentos.map((m) => (
                    <tr key={m.id}>
                      <td>{dataBr(m.data)}</td><td>{m.tipo_txt}</td><td>{m.causa ?? "—"}</td>
                      <td className="text-[13.5px]">{m.descricao ?? "—"}</td><td>{m.executado_por ?? "—"}</td>
                      <td className="num">{m.custo !== null ? reais(m.custo) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Vazio>Nenhuma manutenção coberta pela garantia.</Vazio>}
        </Cartao>
      )}
    </div>
  );
}

function BarraGarantia({ bem }: { bem: BemDetalhe }) {
  const ate = dataBr(bem.garantia_ate);
  const [fundo, texto] = {
    ATIVA: ["bg-erva-claro border-erva", `Em garantia até ${ate} — vence ${emDias(bem.garantia_dias)}.`],
    VENCE_30: ["bg-alerta-claro border-alerta",
               `A garantia vence ${emDias(bem.garantia_dias)} (${ate}). Se há defeito, acione antes.`],
    FORA: ["bg-superficie2 border-linha2", `Fora de garantia desde ${ate}.`],
    SEM: ["bg-superficie2 border-linha2", "Sem garantia informada. Preencha a data para o sistema avisar antes de vencer."],
  }[bem.status_garantia] ?? ["bg-superficie2 border-linha2", bem.garantia_txt];
  return (
    <div role="status" id="bem-garantia-situacao"
         className={`rounded-xl border-l-4 px-5 py-4 text-[14.5px] font-semibold ${fundo}`}>
      {texto}
    </div>
  );
}
