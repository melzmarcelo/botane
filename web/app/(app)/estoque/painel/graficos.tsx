"use client";

import { useRef, useState } from "react";

/**
 * Os gráficos do painel de estoque — à mão, em SVG, como os do painel de vendas.
 *
 * 🔑 **O saldo é LINHA, e a venda era barra.** Venda acontece num dia e some; saldo é um
 * nível que continua de um dia para o outro — ligar os pontos é dizer a verdade aqui. Em
 * degrau: entre dois pontos o saldo não "desliza", ele fica até o próximo movimento.
 * 🔑 **Entradas para CIMA, saídas para BAIXO** do mesmo eixo: o que entrou e o que saiu no
 * mesmo dia ficam lado a lado, e o desequilíbrio se vê sem ler número nenhum.
 */

const M = { esquerda: 64, direita: 12, topo: 14, base: 30 };
const COR_SALDO = "var(--color-erva)";
const COR_ENTRADA = "var(--color-erva)";
const COR_SAIDA = "var(--color-alerta)";

export type Ponto = {
  chave: string;
  rotulo: string;
  titulo: string;
  dica: { rotulo: string; valor: string }[];
};

function useMira(W: number, n: number) {
  const caixa = useRef<SVGSVGElement>(null);
  const [sobre, setSobre] = useState<number | null>(null);
  const passo = (W - M.esquerda - M.direita) / Math.max(n, 1);
  function mover(e: React.MouseEvent<SVGSVGElement>) {
    const r = caixa.current?.getBoundingClientRect();
    if (!r) return;
    const i = Math.floor((((e.clientX - r.left) / r.width) * W - M.esquerda) / passo);
    setSobre(i >= 0 && i < n ? i : null);
  }
  return { caixa, sobre, setSobre, passo, mover };
}

function Dica({ ponto, x, W }: { ponto: Ponto; x: number; W: number }) {
  return (
    <div
      className="pointer-events-none absolute top-2 z-10 whitespace-nowrap rounded-lg bg-tinta px-3 py-2 text-[13px] leading-snug text-white shadow-lg"
      style={{ left: `${(x / W) * 100}%`,
               transform: x > W * 0.65 ? "translateX(calc(-100% - 10px))" : "translateX(10px)" }}
    >
      <b>{ponto.titulo}</b>
      {ponto.dica.map((l) => (
        <span key={l.rotulo} className="block">
          {l.rotulo} <b className="mono font-medium">{l.valor}</b>
        </span>
      ))}
    </div>
  );
}

/** O saldo ao fim de cada ponto, em degrau, com a linha do mínimo e a do zero. */
export function GraficoSaldo({ pontos, valores, minimo, altura = 240, W = 1080, rotulo, noEixo }: {
  pontos: Ponto[];
  valores: number[];
  minimo: number | null;
  altura?: number;
  W?: number;
  rotulo: string;
  noEixo: (v: number) => string;
}) {
  const { caixa, sobre, setSobre, passo, mover } = useMira(W, pontos.length);
  if (!pontos.length) return null;
  const todos = [...valores, minimo ?? 0, 0];
  const teto = Math.max(...todos) * 1.1 || 1;
  const piso = Math.min(...todos) < 0 ? Math.min(...todos) * 1.1 : 0;
  const y = (v: number) => M.topo + (altura - M.topo - M.base) * (1 - (v - piso) / (teto - piso));
  const x = (i: number) => M.esquerda + passo * (i + 0.5);
  const grade = [0, 1, 2, 3, 4].map((k) => piso + ((teto - piso) * k) / 4);
  const cada = Math.max(1, Math.ceil(pontos.length / 12));
  // Degrau: horizontal até o próximo ponto, e só então sobe ou desce.
  const caminho = valores
    .map((v, i) => (i === 0 ? `M ${x(0) - passo / 2} ${y(v)} H ${x(0)}`
                            : `H ${x(i)} V ${y(v)}`))
    .join(" ") + ` H ${x(valores.length - 1) + passo / 2}`;
  const area = `${caminho} V ${y(Math.max(piso, 0))} H ${x(0) - passo / 2} Z`;

  return (
    <div className="relative">
      <svg ref={caixa} viewBox={`0 0 ${W} ${altura}`} width="100%" role="img" aria-label={rotulo}
           onMouseMove={mover} onMouseLeave={() => setSobre(null)}>
        {grade.map((g) => (
          <g key={g}>
            <line x1={M.esquerda} x2={W - M.direita} y1={y(g)} y2={y(g)}
                  stroke="var(--color-linha)" strokeWidth={1} />
            <text x={M.esquerda - 8} y={y(g) + 4} textAnchor="end" fontSize={12}
                  fill="var(--color-suave)">{noEixo(g)}</text>
          </g>
        ))}
        {piso < 0 && (
          <line x1={M.esquerda} x2={W - M.direita} y1={y(0)} y2={y(0)}
                stroke="var(--color-alerta)" strokeWidth={1.2} />
        )}
        <path d={area} fill={COR_SALDO} opacity={0.12} />
        <path d={caminho} fill="none" stroke={COR_SALDO} strokeWidth={2.2} />
        {minimo !== null && minimo > 0 && (
          <g>
            <line x1={M.esquerda} x2={W - M.direita} y1={y(minimo)} y2={y(minimo)}
                  stroke="var(--color-alerta)" strokeWidth={1.4} strokeDasharray="6 4" />
            <text x={W - M.direita - 4} y={y(minimo) - 5} textAnchor="end" fontSize={12}
                  fill="var(--color-alerta)">mínimo {noEixo(minimo)}</text>
          </g>
        )}
        {sobre !== null && (
          <g>
            <line x1={x(sobre)} x2={x(sobre)} y1={M.topo} y2={altura - M.base}
                  stroke="var(--color-suave)" strokeWidth={1} strokeDasharray="3 3" />
            <circle cx={x(sobre)} cy={y(valores[sobre])} r={4} fill={COR_SALDO} />
          </g>
        )}
        {pontos.map((p, i) => i % cada === 0 && (
          <text key={p.chave} x={x(i)} y={altura - 9} fontSize={12} textAnchor="middle"
                fill="var(--color-suave)">{p.rotulo}</text>
        ))}
      </svg>
      {sobre !== null && <Dica ponto={pontos[sobre]} x={x(sobre)} W={W} />}
    </div>
  );
}

/** Entradas para cima e saídas para baixo, no mesmo eixo. */
export function GraficoFluxo({ pontos, entradas, saidas, altura = 200, W = 1080, rotulo, noEixo }: {
  pontos: Ponto[];
  entradas: number[];
  saidas: number[];
  altura?: number;
  W?: number;
  rotulo: string;
  noEixo: (v: number) => string;
}) {
  const { caixa, sobre, setSobre, passo, mover } = useMira(W, pontos.length);
  if (!pontos.length) return null;
  // ⚠️ Estorno num ponto sem o original pode dar negativo: desenha-se o que sobra, nunca
  // uma barra para o lado errado.
  const ent = entradas.map((v) => Math.max(0, v));
  const sai = saidas.map((v) => Math.max(0, v));
  const teto = Math.max(...ent, ...sai) * 1.1 || 1;
  const meio = M.topo + (altura - M.topo - M.base) / 2;
  const meia = (altura - M.topo - M.base) / 2;
  const h = (v: number) => (v / teto) * meia;
  const x = (i: number) => M.esquerda + passo * (i + 0.5);
  const grossura = Math.max(2, Math.min(40, passo * 0.6));
  const cada = Math.max(1, Math.ceil(pontos.length / 12));

  return (
    <div className="relative">
      <svg ref={caixa} viewBox={`0 0 ${W} ${altura}`} width="100%" role="img" aria-label={rotulo}
           onMouseMove={mover} onMouseLeave={() => setSobre(null)}>
        {[teto, teto / 2].map((g) => (
          <g key={g}>
            <line x1={M.esquerda} x2={W - M.direita} y1={meio - h(g)} y2={meio - h(g)}
                  stroke="var(--color-linha)" strokeWidth={1} />
            <line x1={M.esquerda} x2={W - M.direita} y1={meio + h(g)} y2={meio + h(g)}
                  stroke="var(--color-linha)" strokeWidth={1} />
            <text x={M.esquerda - 8} y={meio - h(g) + 4} textAnchor="end" fontSize={12}
                  fill="var(--color-suave)">+{noEixo(g)}</text>
            <text x={M.esquerda - 8} y={meio + h(g) + 4} textAnchor="end" fontSize={12}
                  fill="var(--color-suave)">−{noEixo(g)}</text>
          </g>
        ))}
        <line x1={M.esquerda} x2={W - M.direita} y1={meio} y2={meio}
              stroke="var(--color-suave)" strokeWidth={1} />
        {pontos.map((p, i) => (
          <g key={p.chave} opacity={sobre === null || sobre === i ? 1 : 0.55}>
            {ent[i] > 0 && (
              <rect x={x(i) - grossura / 2} y={meio - h(ent[i])} width={grossura} height={h(ent[i])}
                    rx={Math.min(3, grossura / 4)} fill={COR_ENTRADA} />
            )}
            {sai[i] > 0 && (
              <rect x={x(i) - grossura / 2} y={meio} width={grossura} height={h(sai[i])}
                    rx={Math.min(3, grossura / 4)} fill={COR_SAIDA} />
            )}
            {i % cada === 0 && (
              <text x={x(i)} y={altura - 9} fontSize={12} textAnchor="middle"
                    fill="var(--color-suave)">{p.rotulo}</text>
            )}
          </g>
        ))}
      </svg>
      {sobre !== null && <Dica ponto={pontos[sobre]} x={x(sobre)} W={W} />}
    </div>
  );
}
