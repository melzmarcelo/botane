"use client";

import { useRef, useState } from "react";

/**
 * Linhas em DEGRAU sobre o tempo — o gráfico da tela de Preços.
 *
 * 🔑 **Desenhado à mão, em SVG**, como a cascata do CMV: uma dependência de
 * gráfico para duas linhas pesaria mais que a tela inteira.
 * 🔑 **Degrau, não diagonal.** Preço e custo valem até a próxima mudança; ligar
 * os pontos em linha reta inventaria valores no meio do mês.
 * ⚠️ **Um eixo só.** Preço e custo dividem a escala de reais; a margem, que é
 * percentual, tem gráfico PRÓPRIO — dois eixos no mesmo desenho inventam uma
 * relação que não existe.
 * ⚠️ **As cores das séries foram VALIDADAS** para se distinguirem também para
 * quem não separa verde de laranja (por isso o custo é azul, e não o latão da
 * casa) — e a segunda linha é tracejada, para a identidade nunca depender só da
 * cor. Não trocar por gosto.
 * ⚠️ **Buraco é buraco**: ponto sem valor interrompe a linha. O sistema não
 * desenha o que não sabe.
 */
export const COR_PRECO = "#2a8a5c";
export const COR_CUSTO = "#3d6fc4";

export type Serie = {
  nome: string;
  cor: string;
  tracejada?: boolean;
  /** Um valor por ponto do eixo do tempo; nulo interrompe a linha. */
  valores: (number | null)[];
  /** Índices a marcar com um losango (as mudanças de preço). */
  marcas?: number[];
};

const W = 1080;
const MARGEM = { esquerda: 60, direita: 132, topo: 14, base: 30 };

export default function GraficoDegrau({
  datas,
  series,
  altura,
  rotulo,
  partirDoZero,
  noEixo,
  noValor,
  naDica,
}: {
  /** As datas (AAAA-MM-DD) de cada ponto, em ordem. */
  datas: string[];
  series: Serie[];
  altura: number;
  /** O que o desenho mostra, em palavras — é o que o leitor de tela lê. */
  rotulo: string;
  partirDoZero: boolean;
  noEixo: (v: number) => string;
  noValor: (v: number) => string;
  naDica: (indice: number) => { rotulo: string; valor: string }[];
}) {
  const caixa = useRef<SVGSVGElement>(null);
  const [sobre, setSobre] = useState<number | null>(null);

  const todos = series.flatMap((s) => s.valores.filter((v): v is number => v !== null));
  if (todos.length === 0 || datas.length < 2) return null;

  const tempo = datas.map((d) => new Date(d + "T12:00:00").getTime());
  const t0 = tempo[0];
  const t1 = tempo[tempo.length - 1];
  const teto = Math.max(...todos) * 1.12 || 1;
  const piso = partirDoZero ? 0 : Math.min(...todos) * 0.9;
  const largura = W - MARGEM.esquerda - MARGEM.direita;
  const x = (t: number) => MARGEM.esquerda + ((t - t0) / (t1 - t0 || 1)) * largura;
  const y = (v: number) =>
    MARGEM.topo + (altura - MARGEM.topo - MARGEM.base) * (1 - (v - piso) / (teto - piso || 1));

  const grade = [0, 1, 2, 3, 4].map((k) => piso + ((teto - piso) * k) / 4);
  // Cinco rótulos no eixo do tempo, espalhados por igual.
  const noTempo = [0, 0.25, 0.5, 0.75, 1].map((f) => t0 + (t1 - t0) * f);
  const dataCurta = (t: number) =>
    new Date(t).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" });

  /** A linha em degrau de uma série, respeitando os buracos. */
  const caminho = (valores: (number | null)[]) => {
    let d = "";
    let pena = false;
    valores.forEach((v, i) => {
      if (v === null) {
        pena = false;
        return;
      }
      d += pena ? `H${x(tempo[i])}V${y(v)}` : `M${x(tempo[i])},${y(v)}`;
      pena = true;
    });
    return d;
  };

  function mover(e: React.MouseEvent<SVGSVGElement>) {
    const r = caixa.current?.getBoundingClientRect();
    if (!r) return;
    const t = t0 + (((e.clientX - r.left) / r.width) * W - MARGEM.esquerda) / largura * (t1 - t0);
    // O degrau vale da data dele em diante: o ponto sob o cursor é o último
    // que começou ANTES dele, não o mais próximo.
    let i = 0;
    tempo.forEach((quando, k) => {
      if (quando <= t) i = k;
    });
    setSobre(i);
  }

  const dica = sobre !== null ? naDica(sobre) : [];
  const xMira = sobre !== null ? x(tempo[sobre]) : 0;

  return (
    <div className="relative">
      <svg
        ref={caixa}
        viewBox={`0 0 ${W} ${altura}`}
        width="100%"
        role="img"
        aria-label={rotulo}
        onMouseMove={mover}
        onMouseLeave={() => setSobre(null)}
      >
        {grade.map((g) => (
          <g key={g}>
            <line x1={MARGEM.esquerda} x2={W - MARGEM.direita} y1={y(g)} y2={y(g)}
                  stroke="var(--color-linha)" strokeWidth={1} />
            <text x={MARGEM.esquerda - 8} y={y(g) + 4} textAnchor="end" fontSize={12}
                  fill="var(--color-suave)">
              {noEixo(g)}
            </text>
          </g>
        ))}
        {noTempo.map((t, i) => (
          <text key={i} x={x(t)} y={altura - 8} fontSize={12} fill="var(--color-suave)"
                textAnchor={i === 0 ? "start" : i === noTempo.length - 1 ? "end" : "middle"}>
            {dataCurta(t)}
          </text>
        ))}
        {series.map((s) => {
          const ultimo = [...s.valores].reverse().find((v): v is number => v !== null);
          return (
            <g key={s.nome}>
              <path d={caminho(s.valores)} fill="none" stroke={s.cor} strokeWidth={2.5}
                    strokeLinejoin="round" strokeDasharray={s.tracejada ? "6 4" : undefined} />
              {(s.marcas ?? []).map((i) => {
                const v = s.valores[i];
                if (v === null) return null;
                const cx = x(tempo[i]);
                return (
                  <rect key={i} x={cx - 5} y={y(v) - 5} width={10} height={10}
                        transform={`rotate(45 ${cx} ${y(v)})`} fill={s.cor}
                        stroke="var(--color-superficie)" strokeWidth={2} />
                );
              })}
              {/* ⚠️ O rótulo veste a tinta do TEXTO, não a cor da série: quem
                  carrega a identidade é a linha ao lado dele. */}
              {ultimo !== undefined && (
                <text x={W - MARGEM.direita + 8} y={y(ultimo) + 4} fontSize={12.5}
                      fill="var(--color-tinta)">
                  <tspan fontWeight={600}>{s.nome}</tspan> {noValor(ultimo)}
                </text>
              )}
            </g>
          );
        })}
        {sobre !== null && (
          <line x1={xMira} x2={xMira} y1={MARGEM.topo} y2={altura - MARGEM.base}
                stroke="var(--color-tinta)" strokeWidth={1} strokeDasharray="3 3" />
        )}
      </svg>
      {sobre !== null && (
        <div
          className="pointer-events-none absolute top-3 z-10 whitespace-nowrap rounded-lg bg-tinta px-3 py-2 text-[13px] leading-snug text-white shadow-lg"
          style={{
            left: `${(xMira / W) * 100}%`,
            // Perto da borda direita a dica abre para a esquerda, senão sai da tela.
            transform: xMira > W * 0.7 ? "translateX(calc(-100% - 10px))" : "translateX(10px)",
          }}
        >
          <b>{new Date(tempo[sobre]).toLocaleDateString("pt-BR")}</b>
          {dica.map((l) => (
            <span key={l.rotulo} className="block">
              {l.rotulo} <b className="mono font-medium">{l.valor}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
