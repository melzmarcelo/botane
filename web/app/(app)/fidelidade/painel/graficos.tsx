"use client";

import { useEffect, useState } from "react";

import { rotuloMes } from "@/app/(app)/reservas/painel/quadros";
import { GraficoBarras, GraficoBarrasPareadas, type Barra } from "@/app/(app)/vendas/painel/graficos";
import { Aviso, Cartao, Vazio } from "@/components/ui";
import { graficosFidelidade, type ClienteDoTop, type GraficosFidelidade } from "@/lib/fidelidade";
import { dataCurta } from "@/lib/datas";
import { inteiro } from "@/lib/numeros";

/**
 * Os check-ins no tempo e quem mais vem.
 *
 * 🔑 **Pedido do dono (04/11/2026):** o que faltava do painel de fidelidade do LeadsFood —
 * check-ins por mês com clientes únicos, por dia (14 dias) e os "Top clientes" de 30 dias e de
 * sempre. Check-in é a VISITA (o selo manual não conta); as contas estão em
 * `services/fidelidade.graficos`. O nome no ranking abre a ficha do participante.
 */
export default function GraficosDaFidelidade({ aoAbrir }: { aoAbrir: (id: number) => void }) {
  const [g, setG] = useState<GraficosFidelidade | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let vivo = true;
    graficosFidelidade()
      .then((r) => vivo && setG(r))
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar os gráficos"));
    return () => { vivo = false; };
  }, []);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!g) return null;

  const porDia: Barra[] = g.por_dia.map((x, i) => {
    const faltam = g.por_dia.length - 1 - i;
    const rotulo = faltam === 0 ? "hoje" : faltam === 1 ? "ontem" : dataCurta(x.dia);
    return { chave: x.dia, rotulo, valor: x.n, titulo: dataCurta(x.dia),
             dica: [{ rotulo: "Check-ins", valor: inteiro(x.n) }] };
  });

  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2 [&>*]:min-w-0" id="fidelidade-graficos">
      <Cartao titulo="Check-ins por mês"
              descricao="Visitas com selo e quantos clientes diferentes vieram. O último mês ainda está em andamento.">
        <div className="px-3 py-3">
          <GraficoBarrasPareadas
            pares={g.por_mes.map((x) => ({
              chave: x.mes, rotulo: rotuloMes(x.mes), parcial: x.parcial,
              titulo: `${rotuloMes(x.mes)}${x.parcial ? " (mês em andamento)" : ""}`,
              valores: [x.checkins, x.clientes],
            }))}
            series={["Check-ins", "Clientes únicos"]} altura={240} W={540} noEixo={inteiro}
            rotulo="Check-ins e clientes únicos por mês" />
        </div>
      </Cartao>
      <Cartao titulo={`Check-ins por dia (últimos ${g.por_dia.length} dias)`}>
        <div className="px-3 py-3">
          <GraficoBarras barras={porDia} altura={264} W={540} noEixo={inteiro} maxRotulos={7}
                         rotulo="Check-ins por dia" />
        </div>
      </Cartao>
      <Ranking titulo="Quem mais veio (últimos 30 dias)" lista={g.top_30_dias} aoAbrir={aoAbrir} id="top-30-dias" />
      <Ranking titulo="Quem mais veio (desde sempre)" lista={g.top_sempre} aoAbrir={aoAbrir} id="top-sempre"
               nota="Desde sempre = no Botané, mais os selos em aberto trazidos do LeadsFood." />
    </div>
  );
}

function Ranking({ titulo, lista, aoAbrir, id, nota }: {
  titulo: string; lista: ClienteDoTop[]; aoAbrir: (id: number) => void; id: string; nota?: string;
}) {
  return (
    <Cartao titulo={titulo} descricao={nota}>
      {lista.length ? (
        <ol className="divide-y divide-linha" id={id}>
          {lista.map((x, i) => (
            <li key={x.id}>
              <button type="button" onClick={() => aoAbrir(x.id)}
                      className="flex w-full items-center gap-3 px-5 py-2 text-left hover:bg-linha/40">
                <span className="mono w-5 shrink-0 text-right text-[12px] text-suave">{i + 1}</span>
                <span className="min-w-0 flex-1 truncate text-[14px]">{x.nome}</span>
                <span className="shrink-0 text-[12px] text-suave">última {dataCurta(x.ultima)}</span>
                <b className="mono w-12 shrink-0 text-right text-[14px]">{x.visitas}×</b>
              </button>
            </li>
          ))}
        </ol>
      ) : (
        <Vazio>Nenhum check-in no período.</Vazio>
      )}
    </Cartao>
  );
}
