"use client";

import { useEffect, useState } from "react";

import { Aviso, Carregando } from "@/components/ui";
import { calendario, type Calendario } from "@/lib/reservas";

/**
 * O mês da agenda — a visão geral do que está reservado.
 *
 * 🔑 **Pedido do dono (24/09/2026):** *"na agenda de reservas, ter uma visão de
 * calendário, onde o usuário pode ter uma visão geral do que está reservado, e aí
 * clicar no dia."*
 *
 * ⚠️ **Cada célula diz o que importa para decidir se abre o dia**: quantas
 * reservas e pessoas, quantas ainda aguardam confirmação, e se a casa nem abre.
 * Mais que isso numa célula de 50px no celular vira borrão.
 */

const SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

const NOME_MES = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" });

/** Só a PRIMEIRA letra em maiúscula. ⚠️ O `capitalize` do CSS põe em todas as
 *  palavras e dá "Setembro De 2026" — preposição não leva maiúscula. */
export const maiuscula = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

/** AAAA-MM de um `Date` local — sem `toISOString`, que vira o mês em UTC. */
export const mesDe = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;

/** Soma meses a um AAAA-MM. */
export function outroMes(mes: string, delta: number) {
  const [a, m] = mes.split("-").map(Number);
  return mesDe(new Date(a, m - 1 + delta, 1));
}

export default function CalendarioDoMes({
  mes,
  hoje,
  aoMudarMes,
  aoEscolherDia,
}: {
  mes: string;
  hoje: string;
  aoMudarMes: (mes: string) => void;
  aoEscolherDia: (dia: string) => void;
}) {
  const [dados, setDados] = useState<Calendario | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let vivo = true;
    setDados(null);
    calendario(mes)
      .then((c) => vivo && (setDados(c), setErro("")))
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar o mês"));
    // ⚠️ Trocar de mês rápido dispara vários pedidos: vale o último.
    return () => {
      vivo = false;
    };
  }, [mes]);

  const [ano, numMes] = mes.split("-").map(Number);
  const titulo = maiuscula(NOME_MES.format(new Date(ano, numMes - 1, 1)));
  // ⚠️ A semana começa na SEGUNDA (ISO), como a configuração de horários —
  // `getDay()` do JavaScript começa no domingo, daí o `+ 6 % 7`.
  const vazios = (new Date(ano, numMes - 1, 1).getDay() + 6) % 7;

  const totais = dados?.dias.reduce(
    (t, d) => ({ r: t.r + d.reservas, p: t.p + d.pessoas, pend: t.pend + d.pendentes }),
    { r: 0, p: 0, pend: 0 },
  );

  return (
    <div className="cartao p-3 sm:p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="btn btn-secundario px-3"
            aria-label="mês anterior"
            onClick={() => aoMudarMes(outroMes(mes, -1))}
          >
            ‹
          </button>
          <h2 className="min-w-[170px] text-center text-[17px] font-semibold">
            {titulo}
          </h2>
          <button
            type="button"
            className="btn btn-secundario px-3"
            aria-label="próximo mês"
            onClick={() => aoMudarMes(outroMes(mes, 1))}
          >
            ›
          </button>
        </div>
        {totais && (
          <p className="text-[13px] text-suave">
            <b className="mono text-tinta">{totais.r}</b> reservas ·{" "}
            <b className="mono text-tinta">{totais.p}</b> pessoas
            {totais.pend > 0 && (
              <>
                {" "}· <b className="mono text-[var(--color-alerta)]">{totais.pend}</b> aguardando
              </>
            )}
          </p>
        )}
      </div>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!dados && !erro && <Carregando />}

      {dados && (
        <div className="grid grid-cols-7 gap-1 sm:gap-1.5">
          {SEMANA.map((s) => (
            <div key={s} className="pb-1 text-center text-[11.5px] uppercase tracking-wide text-suave">
              {s}
            </div>
          ))}
          {Array.from({ length: vazios }, (_, i) => (
            <div key={`v${i}`} />
          ))}
          {dados.dias.map((d) => {
            const numero = Number(d.data.slice(8));
            const fechado = !d.aberta || !!d.bloqueio;
            const eHoje = d.data === hoje;
            const passado = d.data < hoje;
            return (
              <button
                key={d.data}
                type="button"
                onClick={() => aoEscolherDia(d.data)}
                title={
                  d.bloqueio
                    ? `Bloqueado: ${d.bloqueio}`
                    : !d.aberta
                      ? "A casa não atende neste dia da semana"
                      : `${d.reservas} reserva(s), ${d.pessoas} pessoa(s)`
                }
                className={[
                  "flex min-h-[58px] flex-col items-stretch rounded-[10px] border p-1.5 text-left transition-colors sm:min-h-[84px] sm:p-2",
                  "hover:border-[var(--color-erva)]",
                  eHoje ? "border-[var(--color-erva)] ring-1 ring-[var(--color-erva)]" : "border-[var(--color-linha)]",
                  fechado ? "bg-[var(--color-superficie2)]" : "bg-[var(--color-superficie)]",
                  passado ? "opacity-60" : "",
                ].join(" ")}
              >
                <span
                  className={`mono text-[13px] font-semibold ${eHoje ? "text-[var(--color-erva)]" : ""}`}
                >
                  {numero}
                </span>
                {d.bloqueio ? (
                  <span className="mt-auto truncate text-[11px] text-[var(--color-erro)]">
                    {d.bloqueio}
                  </span>
                ) : d.reservas > 0 ? (
                  <span className="mt-auto flex flex-col gap-0.5">
                    <span className="rounded-md bg-[var(--color-erva-claro)] px-1 text-[11.5px] font-medium text-[var(--color-erva)]">
                      <span className="mono">{d.reservas}</span>
                      <span className="hidden sm:inline"> res.</span>
                      <span className="hidden sm:inline"> · <span className="mono">{d.pessoas}</span> p.</span>
                    </span>
                    {d.pendentes > 0 && (
                      <span className="rounded-md bg-[var(--color-alerta-claro)] px-1 text-[11px] text-[var(--color-alerta)]">
                        <span className="mono">{d.pendentes}</span>
                        <span className="hidden sm:inline"> aguardando</span>
                      </span>
                    )}
                  </span>
                ) : !d.aberta ? (
                  <span className="mt-auto hidden text-[11px] text-suave sm:block">fechado</span>
                ) : null}
              </button>
            );
          })}
        </div>
      )}

      {dados && (
        <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-suave">
          <span>
            <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[var(--color-erva-claro)] align-middle" />
            reservas e pessoas
          </span>
          <span>
            <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[var(--color-alerta-claro)] align-middle" />
            aguardando confirmação
          </span>
          <span>
            <span className="mr-1 inline-block h-2.5 w-2.5 rounded-sm bg-[var(--color-superficie2)] align-middle" />
            casa fechada ou bloqueada
          </span>
        </p>
      )}
    </div>
  );
}
