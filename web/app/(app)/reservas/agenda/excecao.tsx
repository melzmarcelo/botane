"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Modal } from "@/components/ui";
import {
  definirDia,
  semanaDaCasa,
  type Agenda,
  type DiaDaSemana,
  type ModoDoDia,
} from "@/lib/reservas";

/**
 * A exceção de um dia — feita na própria agenda, sem ir à configuração.
 *
 * 🔑 **Pedido do dono (24/09/2026):** *"dia 12 de outubro é feriado e segunda, que
 * não atende, mas nesta segunda vamos abrir … colocamos horário de sábado. Ou tal
 * dia não abriremos, motivo X. Na reserva, ao selecionar este dia, mostramos o
 * motivo."* Três respostas: o horário normal da semana, um horário especial
 * (copiado de outro dia da semana ou digitado) ou fechado, com motivo.
 *
 * ⚠️ **Não mexe nas reservas já marcadas.** A resposta diz quantas ficaram fora do
 * novo horário — a casa liga para cada uma, como no bloqueio.
 */

const OPCOES: { v: ModoDoDia; r: string; d: string }[] = [
  { v: "PADRAO", r: "Horário normal", d: "Vale o que a semana diz para este dia." },
  { v: "ESPECIAL", r: "Horário especial", d: "Abre neste dia com um horário próprio." },
  { v: "FECHADO", r: "Fechado", d: "Não abre. O motivo aparece para o cliente no site." },
];

export default function ExcecaoDoDia({
  agenda,
  nomeDoDia,
  aoFechar,
  aoSalvar,
}: {
  agenda: Agenda;
  nomeDoDia: string;
  aoFechar: () => void;
  aoSalvar: () => Promise<void>;
}) {
  const aviso = useAviso();
  const inicial: ModoDoDia = agenda.bloqueio ? "FECHADO" : agenda.especial ? "ESPECIAL" : "PADRAO";
  const base = agenda.especial ?? agenda.padrao;
  const [modo, setModo] = useState<ModoDoDia>(inicial);
  const [abre, setAbre] = useState(base?.abre ?? "09:00");
  const [fecha, setFecha] = useState(base?.fecha ?? "18:00");
  const [ultima, setUltima] = useState(base?.ultima_reserva ?? "17:00");
  const [motivo, setMotivo] = useState(agenda.bloqueio ?? agenda.especial?.motivo ?? "");
  const [semana, setSemana] = useState<DiaDaSemana[]>([]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    // ⚠️ Sem a semana a janela funciona igual — só perde o atalho de copiar.
    semanaDaCasa().then(setSemana).catch(() => setSemana([]));
  }, []);

  const padrao = agenda.padrao;
  const textoPadrao = padrao?.aberto
    ? `${padrao.abre} às ${padrao.fecha}, última reserva ${padrao.ultima_reserva}`
    : "fechado";
  // 🔑 Bloqueio de vários dias: sair dele aqui solta SÓ este dia — o resto do
  // período continua fechado. Dizer isso evita o medo de desfazer as férias.
  const periodo =
    agenda.bloqueio_de && agenda.bloqueio_de !== agenda.bloqueio_ate
      ? `${agenda.bloqueio_de.split("-").reverse().join("/")} a ${agenda
          .bloqueio_ate!.split("-")
          .reverse()
          .join("/")}`
      : null;

  function copiar(d: DiaDaSemana) {
    setAbre(d.abre);
    setFecha(d.fecha);
    setUltima(d.ultima_reserva);
    if (!motivo.trim()) setMotivo(`Horário de ${d.nome.toLowerCase()}`);
  }

  async function salvar() {
    if (modo === "FECHADO" && !motivo.trim()) {
      setErro("Diga o motivo — é ele que o cliente vê ao escolher o dia.");
      return;
    }
    setErro("");
    setOcupado(true);
    try {
      const r = await definirDia(agenda.data, {
        modo,
        motivo: modo === "PADRAO" ? null : motivo.trim() || null,
        ...(modo === "ESPECIAL" ? { abre, fecha, ultima_reserva: ultima } : {}),
      });
      if (r.reservas_fora) aviso.erro(r.message);
      else aviso.sucesso(r.message);
      await aoSalvar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível salvar a exceção");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal
      titulo="Exceção deste dia"
      descricao={`${nomeDoDia}. Padrão da semana: ${textoPadrao}.`}
      aoFechar={aoFechar}
      largura="560px"
      rodape={
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className="btn btn-secundario" onClick={aoFechar}>
            Cancelar
          </button>
          <button
            type="button"
            className="btn btn-primario"
            onClick={() => void salvar()}
            aria-busy={ocupado}
            disabled={ocupado}
          >
            {ocupado ? "…" : "Salvar"}
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="o que vale neste dia">
          {OPCOES.map((o) => (
            <button
              key={o.v}
              type="button"
              role="radio"
              aria-checked={modo === o.v}
              onClick={() => setModo(o.v)}
              className={[
                "rounded-[10px] border p-3 text-left transition-colors",
                modo === o.v
                  ? "border-[var(--color-erva)] bg-[var(--color-erva-claro)]"
                  : "border-[var(--color-linha)] hover:border-[var(--color-erva)]",
              ].join(" ")}
            >
              <b className="block text-[14px]">{o.r}</b>
              <span className="text-[12.5px] text-suave">{o.d}</span>
            </button>
          ))}
        </div>

        {periodo && (
          <Aviso tipo="info">
            Este dia está dentro de um bloqueio de <b>{periodo}</b>. Mudar aqui solta só este
            dia; o resto do período continua fechado.
          </Aviso>
        )}

        {modo === "ESPECIAL" && (
          <>
            {semana.some((d) => d.aberto) && (
              <div className="flex flex-wrap items-center gap-2 text-[13px]">
                <span className="text-suave">Copiar o horário de:</span>
                {semana
                  .filter((d) => d.aberto)
                  .map((d) => (
                    <button
                      key={d.dia_semana}
                      type="button"
                      className="btn btn-secundario px-2.5 py-1 text-[13px]"
                      onClick={() => copiar(d)}
                    >
                      {d.nome}
                    </button>
                  ))}
              </div>
            )}
            <div className="grid grid-cols-3 gap-3">
              <Campo rotulo="Abre">
                <input className="campo mono" type="time" value={abre}
                       onChange={(e) => setAbre(e.target.value)} />
              </Campo>
              <Campo rotulo="Fecha">
                <input className="campo mono" type="time" value={fecha}
                       onChange={(e) => setFecha(e.target.value)} />
              </Campo>
              <Campo rotulo="Última reserva">
                <input className="campo mono" type="time" value={ultima}
                       onChange={(e) => setUltima(e.target.value)} />
              </Campo>
            </div>
          </>
        )}

        {modo !== "PADRAO" && (
          <Campo
            rotulo="Motivo"
            opcional={modo === "ESPECIAL"}
            dica="Aparece para o cliente no site quando ele escolhe este dia."
          >
            <input
              className="campo"
              maxLength={120}
              placeholder={modo === "FECHADO" ? "Ex.: evento fechado" : "Ex.: feriado, abrimos em horário de sábado"}
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
            />
          </Campo>
        )}

        {erro && <Aviso tipo="erro">{erro}</Aviso>}
      </div>
    </Modal>
  );
}
