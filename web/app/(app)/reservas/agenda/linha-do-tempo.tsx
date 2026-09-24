"use client";

import { Etiqueta } from "@/components/ui";
import { VIVOS, type Agenda, type Reserva } from "@/lib/reservas";

import { COR, ROTULO } from "./status";

/**
 * O dia inteiro de uma vez — a visão "macro" depois de clicar no calendário.
 *
 * 🔑 **Pedido do dono (24/09/2026):** *"clicar no dia dá uma visão mais macro
 * daquele dia, e aí pode visualizar a reserva."*
 *
 * 🔑 **A barra é quem está SENTADO, não quem chega.** Uma reserva das 12:00 que
 * fica até as 13:30 ocupa as linhas de 12:00, 12:30 e 13:00. Somar só as
 * chegadas mostraria o salão vazio às 12:30 com ele cheio — e é justamente a
 * pergunta "dá para encaixar mais um grupo às 12:30?" que esta tela responde.
 */

const min = (h: string) => Number(h.slice(0, 2)) * 60 + Number(h.slice(3, 5));
const hm = (m: number) =>
  `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;

export default function LinhaDoTempo({
  agenda,
  aoAbrir,
}: {
  agenda: Agenda;
  aoAbrir: (r: Reserva) => void;
}) {
  const vivas = agenda.reservas.filter((r) => VIVOS.includes(r.status));
  const passo = agenda.passo || 30;

  // Os horários da linha: a janela do dia de passo em passo, mais qualquer hora
  // de reserva fora dela (marcada pelo balcão num horário quebrado, ou antes de a
  // janela mudar) — reserva que não aparece na linha do tempo é reserva perdida.
  const horas = new Set<number>();
  if (agenda.abre && agenda.fecha) {
    for (let m = min(agenda.abre); m < min(agenda.fecha); m += passo) horas.add(m);
  }
  agenda.reservas.forEach((r) => horas.add(min(r.hora)));
  const linhas = [...horas].sort((a, b) => a - b);

  if (!linhas.length) {
    return (
      <p className="px-1 py-8 text-center text-[15px] text-suave">
        A casa não atende neste dia e não há reservas.
      </p>
    );
  }

  const sentados = (m: number) =>
    vivas
      .filter((r) => {
        const ini = min(r.hora);
        const fim = r.sai_por_volta ? min(r.sai_por_volta) : ini + passo;
        return ini <= m && m < fim;
      })
      .reduce((s, r) => s + r.pessoas, 0);
  const pico = Math.max(0, ...linhas.map(sentados));

  return (
    <div className="flex flex-col">
      <p className="mb-2 text-[12.5px] text-suave">
        A barra é a ocupação do salão em cada horário — quem já está sentado, contando a
        permanência. Pico do dia: <b className="mono text-tinta">{pico}</b> de{" "}
        <b className="mono text-tinta">{agenda.lugares}</b> lugares.
      </p>
      {linhas.map((m) => {
        const hora = hm(m);
        const chegam = agenda.reservas.filter((r) => r.hora === hora);
        const n = sentados(m);
        const pct = agenda.lugares ? Math.min(100, Math.round((n / agenda.lugares) * 100)) : 0;
        const cheio = pct >= 90;
        return (
          <div
            key={m}
            className="grid grid-cols-[52px_1fr] items-start gap-x-3 border-t border-[var(--color-linha)] py-2 first:border-t-0 sm:grid-cols-[52px_minmax(120px,220px)_1fr]"
          >
            <span className="mono pt-0.5 text-[13.5px] font-semibold">{hora}</span>
            <div className="pt-1.5" title={`${n} de ${agenda.lugares} lugares ocupados`}>
              <div className="h-2 overflow-hidden rounded-full bg-[var(--color-superficie2)]">
                <div
                  className={`h-full rounded-full ${cheio ? "bg-[var(--color-alerta)]" : "bg-[var(--color-erva)]"}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="mono mt-0.5 block text-[11px] text-suave">
                {n}/{agenda.lugares}
              </span>
            </div>
            <div className="col-span-2 mt-1.5 flex flex-wrap gap-1.5 sm:col-span-1 sm:mt-0">
              {chegam.map((r) => {
                const solta = !VIVOS.includes(r.status);
                return (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => aoAbrir(r)}
                    className={`flex items-center gap-2 rounded-[10px] border border-[var(--color-linha)] bg-[var(--color-superficie)] px-2.5 py-1.5 text-left text-[13.5px] hover:border-[var(--color-erva)] ${solta ? "opacity-55" : ""}`}
                  >
                    <span className={`font-medium ${solta ? "line-through" : ""}`}>{r.nome}</span>
                    <span className="mono text-suave">{r.pessoas}p</span>
                    {r.mesas && <span className="mono text-[12px] text-suave">{r.mesas}</span>}
                    <Etiqueta cor={COR[r.status]}>{ROTULO[r.status] ?? r.status}</Etiqueta>
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
