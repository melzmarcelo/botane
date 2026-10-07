"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Modal } from "@/components/ui";
import { numero, usarParte, type Etiqueta } from "@/lib/etiquetas";
import { textoParaNumero } from "@/lib/numeros";

/**
 * "Usei uma parte" — a janela que o painel e a tela do QR dividem.
 *
 * 🔑 **Pedido do dono (06/10/2026):** *"temos somente como descartar ou baixar
 * tudo, tem como consumir partes?"* O pote de 2 kg do qual se tirou 300 g não
 * tinha o que dizer: a etiqueta só saía inteira.
 *
 * 🔑 **Dá para dizer QUANTO SAIU ou QUANTO SOBROU** — as duas contas existem na
 * bancada: quem pesou o que tirou sabe a primeira; quem pôs o pote de volta na
 * balança sabe a segunda. O servidor recebe sempre o que saiu.
 *
 * ⚠️ **Não mexe no estoque** e **não renova a validade**: o consumo já entra pela
 * venda ou pela produção que usou o pote. O que muda é a quantidade da etiqueta.
 * ⚠️ **Tirar tudo encerra a etiqueta** — e a janela diz isso antes do botão.
 */
export default function UsoParcial({
  etiqueta,
  aoFechar,
  aoConcluir,
}: {
  etiqueta: Etiqueta;
  aoFechar: () => void;
  aoConcluir: (e: Etiqueta) => void;
}) {
  const aviso = useAviso();
  const tem = Number(etiqueta.quantidade ?? 0);
  const um = etiqueta.um ?? "";
  const [modo, setModo] = useState<"saiu" | "sobrou">("saiu");
  const [valor, setValor] = useState("");
  const [observacao, setObservacao] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const digitado = textoParaNumero(valor);
  // O que vai ao servidor é sempre o que SAIU.
  const saiu = digitado === null ? null : modo === "saiu" ? digitado : tem - digitado;
  const resta = saiu === null ? null : Math.round((tem - saiu) * 10000) / 10000;
  const erro =
    digitado === null ? null
      : digitado < 0 ? "A quantidade não pode ser negativa."
      : modo === "saiu" && digitado === 0 ? "Informe quanto saiu."
      : modo === "sobrou" && digitado === tem ? "Se sobrou tudo, nada saiu."
      : saiu !== null && saiu > tem + 1e-9
        ? `O pote tem ${numero(tem)} ${um} — não dá para tirar mais que isso.`
      : modo === "sobrou" && digitado > tem
        ? `O pote tinha ${numero(tem)} ${um} — não pode ter sobrado mais.`
      : null;
  const pode = saiu !== null && saiu > 0 && !erro;

  async function confirmar() {
    if (!pode || saiu === null) return;
    setOcupado(true);
    try {
      const r = await usarParte(etiqueta.id, Math.round(saiu * 10000) / 10000,
                                observacao.trim() || undefined);
      aviso.sucesso(r.message);
      aoConcluir(r);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível registrar o uso");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal
      titulo={`Usei uma parte — ${etiqueta.codigo}`}
      descricao={`${etiqueta.produto} · o pote tem ${numero(tem)} ${um}`.trim()}
      aoFechar={aoFechar}
      largura="480px"
      rodape={
        <div className="flex justify-end gap-2">
          <button className="btn btn-secundario" onClick={aoFechar}>Voltar</button>
          <button className="btn btn-primario" disabled={ocupado || !pode} aria-busy={ocupado}
                  onClick={() => void confirmar()}>
            {ocupado ? "…" : "Registrar"}
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="inline-flex self-start overflow-hidden rounded-[9px] border border-linha2"
             role="group" aria-label="como informar">
          {([["saiu", "Quanto saiu"], ["sobrou", "Quanto sobrou"]] as const).map(([v, r]) => (
            <button key={v} type="button" aria-pressed={modo === v}
                    className={`px-3.5 py-2 text-[13.5px] ${
                      modo === v ? "bg-erva text-white" : "text-suave"}`}
                    onClick={() => setModo(v)}>
              {r}
            </button>
          ))}
        </div>
        <Campo rotulo={`${modo === "saiu" ? "Quanto saiu" : "Quanto sobrou"}${um ? ` (${um})` : ""}`}
               erro={erro}>
          <input className="campo mono" inputMode="decimal" autoFocus
                 aria-label={modo === "saiu" ? "quanto saiu do pote" : "quanto sobrou no pote"}
                 value={valor} onChange={(e) => setValor(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && pode) void confirmar(); }} />
        </Campo>
        {pode && resta !== null && (
          <p className="text-[14px]" role="status">
            {resta === 0 ? (
              <>O pote <b>acaba</b>: a etiqueta sai das ativas, como em “usei tudo”.</>
            ) : (
              <>
                Saem <b>{numero(saiu)} {um}</b> e ficam <b>{numero(resta)} {um}</b> no pote. A
                validade continua a mesma.
              </>
            )}
          </p>
        )}
        <Campo rotulo="Observação" opcional>
          <input className="campo" maxLength={200} value={observacao}
                 placeholder="ex.: para o molho do almoço"
                 onChange={(e) => setObservacao(e.target.value)} />
        </Campo>
        <p className="text-[12.5px] text-suave">
          Não mexe no estoque: o consumo já entra pela venda ou pela produção que usou o pote.
        </p>
      </div>
    </Modal>
  );
}
