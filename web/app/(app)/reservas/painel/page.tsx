"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import ExplicaTela from "@/components/explica-tela";
import { Aviso, Carregando, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { verPainelReservas, type PainelReservas } from "@/lib/reservas";

import {
  GruposGrandes, Numeros, PorDiaDaSemana, PorHorario, PorMes, PorObjetivo, type Metrica,
} from "./quadros";

/**
 * O painel das reservas — como a agenda andou.
 *
 * 🔑 **Pedido do dono (30/10/2026):** os gráficos do BI de reservas do LeadsFood ("Análise de
 * desempenho" e "Grupos grandes"), depois do Plano de ação. As contas estão em
 * `services/reservas_painel.py`: reserva válida, pessoas que vieram e no-show.
 * Período e medida na URL: voltar a esta tela traz o mesmo recorte.
 */

const PERIODOS = [
  { v: "3", r: "3 meses" },
  { v: "6", r: "6 meses" },
  { v: "12", r: "12 meses" },
  { v: "24", r: "24 meses" },
];

export default function PainelDasReservas() {
  const [meses, setMeses] = useEstadoNaUrl<string>("meses", "12", { atraso: 0 });
  const [medida, setMedida] = useEstadoNaUrl<string>("medida", "reservas", { atraso: 0 });
  const m: Metrica = medida === "pessoas" ? "pessoas" : "reservas";
  const [p, setP] = useState<PainelReservas | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let vivo = true;
    verPainelReservas(Number(meses) || 12)
      .then((r) => { if (vivo) { setP(r); setErro(""); } })
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar o painel"));
    return () => { vivo = false; };
  }, [meses]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="rotulo">Portal de Clientes · Reservas</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Painel</h1>
          <ExplicaTela>
            Como a agenda andou nesta loja: dias e horários mais procurados, a evolução mês a
            mês, por que as pessoas reservam e o peso dos grupos grandes. Conta só reservas que
            já passaram e que ocuparam a agenda (canceladas à parte). Pessoas que vieram não
            inclui quem faltou.
          </ExplicaTela>
        </div>
        <Link href="/reservas/plano-de-acao" className="btn btn-secundario">Plano de ação</Link>
      </header>

      {/* Os filtros numa linha, acima de tudo: valem para todos os quadros. */}
      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="rotulo-campo">Período</span>
          <select className="campo mt-1.5 min-w-[150px]" value={meses} onChange={(e) => setMeses(e.target.value)}>
            {PERIODOS.map((x) => <option key={x.v} value={x.v}>{x.r}</option>)}
          </select>
        </label>
        <div className="flex gap-1" role="tablist" aria-label="medida">
          {(["reservas", "pessoas"] as const).map((x) => (
            <button key={x} type="button" role="tab" aria-selected={m === x}
                    className={`btn px-3 py-1.5 text-[13px] ${m === x ? "btn-primario" : "btn-secundario"}`}
                    onClick={() => setMedida(x)}>
              {x === "reservas" ? "Reservas" : "Pessoas"}
            </button>
          ))}
        </div>
      </div>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {!p ? (
        !erro && <Carregando />
      ) : (
        <>
          <Numeros p={p} />
          {!p.resumo.reservas ? (
            <Vazio>
              Nenhuma reserva no período. O histórico de antes do Botané está no sistema
              anterior e entra quando for importado.
            </Vazio>
          ) : (
            <>
              <PorMes p={p} m={m} />
              <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2 [&>*]:min-w-0">
                <PorDiaDaSemana p={p} m={m} />
                <PorHorario p={p} m={m} />
                <PorObjetivo p={p} m={m} />
                <GruposGrandes p={p} m={m} />
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
