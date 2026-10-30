"use client";

import { BarrasDeitadas, GraficoBarras, type Barra } from "@/app/(app)/vendas/painel/graficos";
import { Cartao, Vazio } from "@/components/ui";
import { inteiro, pct, plural } from "@/lib/numeros";
import type { ContaDoPainel, PainelReservas } from "@/lib/reservas";

/**
 * Os quadros do painel das reservas. Os desenhos são os do painel de vendas (`GraficoBarras`,
 * `BarrasDeitadas`): uma cor só, a da casa — cada gráfico mostra UMA medida.
 */

export type Metrica = "reservas" | "pessoas";

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
/** "2026-10" → "out/26". */
export const rotuloMes = (m: string) => `${MESES[Number(m.slice(5, 7)) - 1]}/${m.slice(2, 4)}`;

const numero = (v: number) => inteiro(v);

/** As linhas da dica: as três contas, sempre — quem passa o cursor quer o quadro todo. */
const dica = (x: ContaDoPainel) => [
  { rotulo: "Reservas", valor: inteiro(x.reservas) },
  { rotulo: "Pessoas que vieram", valor: inteiro(x.pessoas) },
  { rotulo: "No-shows", valor: inteiro(x.faltas) },
];

export function Numeros({ p }: { p: PainelReservas }) {
  const r = p.resumo;
  const itens = [
    { n: inteiro(r.reservas), r: "reservas válidas" },
    { n: inteiro(r.clientes), r: "clientes diferentes" },
    { n: inteiro(r.pessoas), r: "pessoas que vieram" },
    { n: `${inteiro(r.faltas)} · ${pct(r.reservas ? (r.faltas / r.reservas) * 100 : 0, 1)}`, r: "no-shows",
      alerta: r.reservas > 0 && r.faltas / r.reservas >= 0.15 },
    { n: inteiro(r.canceladas), r: "canceladas" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5 [&>*]:min-w-0">
      {itens.map((x) => (
        <div key={x.r} className="cartao px-3 py-3">
          <b className={`mono block text-[22px] leading-none ${x.alerta ? "text-[var(--color-alerta)]" : ""}`}>{x.n}</b>
          <span className="mt-1 block text-[12px] text-suave">{x.r}</span>
        </div>
      ))}
    </div>
  );
}

export function PorDiaDaSemana({ p, m }: { p: PainelReservas; m: Metrica }) {
  const barras: Barra[] = p.por_dia_semana.map((x) => ({
    chave: String(x.dia), rotulo: x.nome, valor: x[m], titulo: x.nome, dica: dica(x),
  }));
  return (
    <Cartao titulo="Por dia da semana">
      <div className="px-3 py-3">
        <GraficoBarras barras={barras} altura={240} W={540} noEixo={numero}
                       rotulo={`${m === "reservas" ? "Reservas" : "Pessoas"} por dia da semana`} />
      </div>
    </Cartao>
  );
}

export function PorHorario({ p, m }: { p: PainelReservas; m: Metrica }) {
  const barras: Barra[] = p.por_hora.map((x) => ({
    chave: String(x.hora), rotulo: `${x.hora}h`, valor: x[m],
    titulo: `Das ${x.hora}h às ${x.hora}h59`, dica: dica(x),
  }));
  return (
    <Cartao titulo="Por horário de chegada">
      {barras.length ? (
        <div className="px-3 py-3">
          <GraficoBarras barras={barras} altura={240} W={540} noEixo={numero}
                         rotulo={`${m === "reservas" ? "Reservas" : "Pessoas"} por hora`} />
        </div>
      ) : (
        <Vazio>Sem reservas no período.</Vazio>
      )}
    </Cartao>
  );
}

export function PorMes({ p, m }: { p: PainelReservas; m: Metrica }) {
  const barras: Barra[] = p.por_mes.map((x) => ({
    chave: x.mes, rotulo: rotuloMes(x.mes), valor: x[m],
    titulo: `${rotuloMes(x.mes)}${x.parcial ? " (mês em andamento)" : ""}`, dica: dica(x),
  }));
  return (
    <Cartao titulo="Evolução por mês"
            descricao="O último mês ainda está em andamento: conta só até hoje.">
      <div className="px-3 py-3">
        <GraficoBarras barras={barras} altura={260} noEixo={numero}
                       rotulo={`${m === "reservas" ? "Reservas" : "Pessoas"} por mês`} />
      </div>
      {/* Os números, para quem não lê o desenho (leitor de tela, impressão, conferência). */}
      <details className="border-t border-linha px-5 py-3">
        <summary className="cursor-pointer text-[13px] text-suave">Ver os números</summary>
        <div className="grid-rolante mt-2">
          <table className="tabela">
            <thead>
              <tr><th>Mês</th><th className="num">Reservas</th><th className="num">Pessoas</th>
                <th className="num">No-shows</th><th className="num">Grupos</th></tr>
            </thead>
            <tbody>
              {p.por_mes.map((x) => (
                <tr key={x.mes}>
                  <td>{rotuloMes(x.mes)}{x.parcial && <span className="text-suave"> · parcial</span>}</td>
                  <td className="num mono">{x.reservas}</td>
                  <td className="num mono">{x.pessoas}</td>
                  <td className="num mono">{x.faltas}</td>
                  <td className="num mono">{x.grupos}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Cartao>
  );
}

export function PorObjetivo({ p, m }: { p: PainelReservas; m: Metrica }) {
  const total = p.por_objetivo.reduce((s, x) => s + x[m], 0) || 1;
  return (
    <Cartao titulo="Objetivo da visita">
      <div className="px-5 py-4">
        {p.por_objetivo.length ? (
          <BarrasDeitadas
            linhas={p.por_objetivo.map((x) => ({
              chave: x.objetivo, nome: x.objetivo, valor: x[m], id: null,
              detalhe: `${pct((x[m] / total) * 100, 0)} · ${plural(x.reservas, "reserva", "reservas")}`,
            }))}
            valor={numero}
          />
        ) : (
          <Vazio>Sem reservas no período.</Vazio>
        )}
      </div>
    </Cartao>
  );
}

export function GruposGrandes({ p, m }: { p: PainelReservas; m: Metrica }) {
  const g = p.grupos;
  const parte = p.resumo.reservas ? (g.reservas / p.resumo.reservas) * 100 : 0;
  const vieram = g.reservas - g.faltas;
  const itens = [
    { n: inteiro(g.reservas), r: `grupos de ${p.grupo_pessoas}+` },
    { n: pct(parte, 1), r: "das reservas válidas" },
    { n: inteiro(g.pessoas), r: "pessoas trazidas" },
    { n: vieram ? (g.pessoas / vieram).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) : "—",
      r: "pessoas por grupo" },
  ];
  const barras: Barra[] = p.por_mes.map((x) => ({
    chave: x.mes, rotulo: rotuloMes(x.mes), valor: m === "reservas" ? x.grupos : x.grupos_pessoas,
    titulo: `${rotuloMes(x.mes)}${x.parcial ? " (mês em andamento)" : ""}`,
    dica: [{ rotulo: "Grupos", valor: inteiro(x.grupos) },
           { rotulo: "Pessoas que vieram", valor: inteiro(x.grupos_pessoas) }],
  }));
  return (
    <Cartao titulo="Grupos grandes"
            descricao={`Reservas de ${p.grupo_pessoas} pessoas ou mais. Maior grupo do período: ${
              g.maior} pessoas · ${plural(g.faltas, "no-show", "no-shows")} entre eles.`}>
      <div className="grid grid-cols-2 gap-3 px-5 pt-4 sm:grid-cols-4 [&>*]:min-w-0">
        {itens.map((x) => (
          <div key={x.r}>
            <b className="mono block text-[20px] leading-none">{x.n}</b>
            <span className="mt-1 block text-[12px] text-suave">{x.r}</span>
          </div>
        ))}
      </div>
      <div className="px-3 py-3">
        <GraficoBarras barras={barras} altura={220} W={540} noEixo={numero} maxRotulos={6}
                       rotulo={`Grupos grandes por mês (${m === "reservas" ? "reservas" : "pessoas"})`} />
      </div>
    </Cartao>
  );
}
