"use client";

import { useEffect, useState } from "react";

import { Aviso, Carregando } from "@/components/ui";
import { api } from "@/lib/api";

/**
 * Quantas pessoas → que horários existem.
 *
 * 🔑 **A ordem é a regra, não preferência de layout.** "Esgotado" depende do
 * tamanho do grupo: no mesmo sábado às 12h pode não haver mesa para 6 e haver
 * para 2. Perguntar o horário primeiro obrigaria a tela a mostrar uma lista que
 * ela ainda não pode calcular.
 *
 * 🔑 **Quem decide se cabe é o SERVIDOR.** A lista vem de
 * `/reservas/disponibilidade`, que roda a mesma regra que a gravação vai rodar —
 * uma segunda versão dela aqui divergiria no primeiro degrau novo, e a tela
 * passaria a oferecer horário que o servidor recusa.
 *
 * 🔑 **Um componente só para MARCAR e para REMARCAR.** Duas cópias deste bloco
 * divergiriam no primeiro ajuste, e a tela de remarcar passaria a oferecer
 * horários por uma regra diferente da de marcar — que é exatamente o tipo de
 * diferença que ninguém percebe até alguém sentar na mesa errada.
 *
 * ⚠️ **`ignorar` é o que faz o remarcar funcionar.** Sem ele, a reserva
 * disputaria mesa CONSIGO MESMA: passar das 12h para as 12h30 esbarraria na
 * própria permanência, e a tela diria "sem mesa" apontando para a mesa que a
 * própria reserva ocupa.
 */

export type Horario = {
  hora: string;
  livre: boolean;
  mesas_livres: number;
  sai_por_volta: string;
};

export type Disponibilidade = {
  data: string;
  pessoas: number;
  abre?: string;
  fecha?: string;
  ultima_reserva?: string;
  teto_online?: number;
  maior_grupo?: number;
  horarios: Horario[];
  motivo: string | null;
};

export default function EscolherHorario({
  dia,
  pessoas,
  aoMudarPessoas,
  hora,
  aoMudarHora,
  ignorar,
}: {
  dia: string;
  pessoas: number;
  aoMudarPessoas: (n: number) => void;
  hora: string;
  aoMudarHora: (h: string) => void;
  /** A reserva que está sendo remarcada — ela não disputa mesa consigo mesma. */
  ignorar?: number;
}) {
  const [disp, setDisp] = useState<Disponibilidade | null>(null);

  useEffect(() => {
    let vivo = true;
    setDisp(null);
    const alvo =
      `/reservas/disponibilidade?data=${dia}&pessoas=${pessoas}` +
      (ignorar ? `&ignorar=${ignorar}` : "");
    api
      .get<Disponibilidade>(alvo)
      .then((d) => vivo && setDisp(d))
      .catch(() => vivo && setDisp(null));
    return () => {
      vivo = false;
    };
  }, [dia, pessoas, ignorar]);

  const grupos = Array.from({ length: 12 }, (_v, i) => i + 1);

  return (
    <>
      <div>
        <span className="rot text-[13px] font-medium">Pessoas</span>
        <div className="mt-1.5 flex flex-wrap gap-2">
          {grupos.map((n) => (
            <button
              key={n}
              type="button"
              aria-label={`${n} pessoas`}
              aria-pressed={pessoas === n}
              className={`mono rounded-full border px-3.5 py-1.5 text-[13.5px] ${
                pessoas === n
                  ? "border-erva bg-erva-claro text-erva"
                  : "border-linha2 text-suave hover:border-erva"
              }`}
              onClick={() => aoMudarPessoas(n)}
            >
              {n}
            </button>
          ))}
        </div>
        {/* 🔑 O teto tem de caber no salão — se o maior grupo que a casa acomoda
            for menor que o pedido, a resposta vazia abaixo se explica sozinha em
            vez de parecer defeito. */}
        {disp?.maior_grupo !== undefined && pessoas > disp.maior_grupo && (
          <p className="mt-2 text-[13px] text-alerta">
            A maior mesa (ou junta) da casa acomoda {disp.maior_grupo}. Para um grupo maior,
            junte mesas na mão e marque duas reservas — ou acrescente a junta no cadastro do
            Salão.
          </p>
        )}
      </div>

      <div>
        <span className="rot text-[13px] font-medium">Horário</span>
        {!disp ? (
          <Carregando>Vendo o que cabe…</Carregando>
        ) : !disp.horarios.length ? (
          <Aviso tipo="info">{disp.motivo ?? "Sem horários neste dia."}</Aviso>
        ) : (
          <>
            <div className="mt-1.5 grid grid-cols-3 gap-2 sm:grid-cols-6">
              {disp.horarios.map((h) => (
                <button
                  key={h.hora}
                  type="button"
                  disabled={!h.livre}
                  aria-label={`horário ${h.hora}`}
                  aria-pressed={hora === h.hora}
                  title={h.livre ? `Sai por volta das ${h.sai_por_volta}` : "Sem mesa"}
                  className={`mono rounded-lg border px-2 py-2 text-[14px] ${
                    hora === h.hora
                      ? "border-erva bg-erva-claro text-erva"
                      : h.livre
                        ? "border-linha2 hover:border-erva"
                        : "border-linha2 text-suave line-through opacity-60"
                  }`}
                  onClick={() => aoMudarHora(h.hora)}
                >
                  {h.hora}
                </button>
              ))}
            </div>
            <p className="mt-2 text-[12.5px] text-suave">
              Atende das {disp.abre} às {disp.fecha}; a última reserva é {disp.ultima_reserva}{" "}
              — a diferença é o tempo de quem senta por último.
              {hora &&
                ` Escolhido ${hora}: a mesa vaga por volta das ${
                  disp.horarios.find((h) => h.hora === hora)?.sai_por_volta ?? "—"
                }.`}
            </p>
          </>
        )}
      </div>
    </>
  );
}
