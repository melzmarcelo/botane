"use client";

import { Etiqueta, Modal } from "@/components/ui";
import type { Reserva } from "@/lib/reservas";

import { ADIANTE, COR, ROTULO, podeRemarcar } from "./status";

/**
 * Uma reserva inteira, aberta a partir da linha do tempo.
 *
 * 🔑 **As MESMAS ações da lista**, pelas mesmas funções da página: confirmar,
 * remarcar, cancelar. Uma segunda implementação aqui divergiria na primeira
 * regra nova — e a recepção veria um botão que a lista não tem.
 */
export default function DetalheDaReserva({
  reserva: r,
  dia,
  podeEditar,
  ocupado,
  aoMudar,
  aoRemarcar,
  aoFechar,
}: {
  reserva: Reserva;
  dia: string;
  podeEditar: boolean;
  ocupado: boolean;
  aoMudar: (r: Reserva, para: string, rotulo: string) => void;
  aoRemarcar: (r: Reserva) => void;
  aoFechar: () => void;
}) {
  const linha = (rotulo: string, valor: React.ReactNode) =>
    valor ? (
      <div className="grid grid-cols-[130px_1fr] gap-3 border-b border-[var(--color-linha)] py-2 last:border-b-0">
        <span className="text-[13px] text-suave">{rotulo}</span>
        <span className="text-[14.5px]">{valor}</span>
      </div>
    ) : null;

  const acoes = podeEditar ? [
    ...(podeRemarcar(r.status)
      ? [{ chave: "remarcar", rotulo: "remarcar", perigo: false, fazer: () => aoRemarcar(r) }]
      : []),
    ...(ADIANTE[r.status] ?? []).map((a) => ({
      chave: a.para, rotulo: a.rotulo, perigo: !!a.perigo, fazer: () => aoMudar(r, a.para, a.rotulo),
    })),
  ] : [];

  return (
    <Modal
      titulo={r.nome}
      descricao={`${dia.split("-").reverse().join("/")} às ${r.hora}`}
      aoFechar={aoFechar}
      largura="520px"
      rodape={
        acoes.length ? (
          <div className="flex flex-wrap justify-end gap-2">
            {acoes.map((a) => (
              <button
                key={a.chave}
                type="button"
                className={`btn ${a.perigo ? "btn-secundario text-[var(--color-erro)]" : "btn-secundario"}`}
                aria-busy={ocupado}
                disabled={ocupado}
                onClick={a.fazer}
              >
                {a.rotulo}
              </button>
            ))}
          </div>
        ) : undefined
      }
    >
      <div className="flex flex-col">
        {linha("Situação", <Etiqueta cor={COR[r.status]}>{ROTULO[r.status] ?? r.status}</Etiqueta>)}
        {linha("Horário", (
          <span className="mono">
            {r.hora}
            {r.sai_por_volta && <span className="text-suave"> — sai por volta de {r.sai_por_volta}</span>}
          </span>
        ))}
        {linha("Pessoas", <span className="mono">{r.pessoas}</span>)}
        {linha("Mesa", r.mesas ? <span className="mono">{r.mesas}</span> : "—")}
        {linha("Telefone", r.telefone && <span className="mono">{r.telefone}</span>)}
        {linha("Ocasião", r.objetivo)}
        {linha("Do cliente", r.observacao_cliente)}
        {linha("Interno", r.observacao_interna)}
        {linha("Origem", r.origem === "SITE" ? "pelo site" : "balcão")}
      </div>
    </Modal>
  );
}
