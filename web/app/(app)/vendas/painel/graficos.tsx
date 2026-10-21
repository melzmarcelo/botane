"use client";

import { useRef, useState } from "react";

/**
 * Os gráficos do painel de vendas.
 *
 * 🔑 **Desenhados à mão**, como o de Preços e a cascata do CMV: uma dependência de
 * gráfico para três desenhos de barra pesaria mais que a tela inteira.
 * ⚠️ **Barra, não linha**, na evolução: venda é por dia (ou semana, ou mês) — ligar
 * os pontos inventaria uma venda contínua entre eles, e um dia fechado viraria uma
 * rampa em vez de um buraco.
 * ⚠️ **Buraco é buraco**: dia sem venda não ganha barra zero desenhada — o eixo
 * mostra só os pontos que existem.
 */
export const COR_BARRA = "var(--color-erva)";

export type Barra = {
  chave: string;
  /** O rótulo curto do eixo. */
  rotulo: string;
  valor: number;
  /** As linhas da dica, ao passar o cursor. */
  dica: { rotulo: string; valor: string }[];
  titulo: string;
};

const M = { esquerda: 64, direita: 12, topo: 12, base: 30 };

export function GraficoBarras({ barras, altura, rotulo, noEixo, aoClicar, W = 1080 }: {
  barras: Barra[];
  altura: number;
  /**
   * A largura do desenho em unidades do `viewBox`. ⚠️ Num quadro de MEIA tela, 1080
   * encolhe o texto pela metade e o eixo vira ilegível: ali vai 540.
   */
  W?: number;
  /** O que o desenho mostra, em palavras — é o que o leitor de tela lê. */
  rotulo: string;
  noEixo: (v: number) => string;
  aoClicar?: (b: Barra) => void;
}) {
  const caixa = useRef<SVGSVGElement>(null);
  const [sobre, setSobre] = useState<number | null>(null);
  if (!barras.length) return null;

  const teto = Math.max(...barras.map((b) => b.valor)) * 1.1 || 1;
  const largura = W - M.esquerda - M.direita;
  const passo = largura / barras.length;
  const grossura = Math.max(2, Math.min(56, passo * 0.72));
  const y = (v: number) => M.topo + (altura - M.topo - M.base) * (1 - v / teto);
  const grade = [0, 1, 2, 3, 4].map((k) => (teto * k) / 4);
  // ⚠️ Rótulos do eixo espaçados: com 60 dias, um rótulo por barra vira borrão.
  const cada = Math.max(1, Math.ceil(barras.length / 12));

  function mover(e: React.MouseEvent<SVGSVGElement>) {
    const r = caixa.current?.getBoundingClientRect();
    if (!r) return;
    const xv = ((e.clientX - r.left) / r.width) * W - M.esquerda;
    const i = Math.floor(xv / passo);
    setSobre(i >= 0 && i < barras.length ? i : null);
  }

  const atual = sobre !== null ? barras[sobre] : null;
  const xMira = sobre !== null ? M.esquerda + passo * (sobre + 0.5) : 0;

  return (
    <div className="relative">
      <svg ref={caixa} viewBox={`0 0 ${W} ${altura}`} width="100%" role="img" aria-label={rotulo}
           onMouseMove={mover} onMouseLeave={() => setSobre(null)}
           onClick={() => atual && aoClicar?.(atual)}
           style={{ cursor: aoClicar && atual ? "pointer" : undefined }}>
        {grade.map((g) => (
          <g key={g}>
            <line x1={M.esquerda} x2={W - M.direita} y1={y(g)} y2={y(g)}
                  stroke="var(--color-linha)" strokeWidth={1} />
            <text x={M.esquerda - 8} y={y(g) + 4} textAnchor="end" fontSize={12}
                  fill="var(--color-suave)">{noEixo(g)}</text>
          </g>
        ))}
        {barras.map((b, i) => {
          const cx = M.esquerda + passo * (i + 0.5);
          return (
            <g key={b.chave}>
              <rect x={cx - grossura / 2} y={y(b.valor)} width={grossura}
                    height={Math.max(0, y(0) - y(b.valor))} rx={Math.min(3, grossura / 4)}
                    fill={COR_BARRA} opacity={sobre === null || sobre === i ? 1 : 0.55}>
                <title>{b.titulo}</title>
              </rect>
              {i % cada === 0 && (
                <text x={cx} y={altura - 9} fontSize={12} textAnchor="middle"
                      fill="var(--color-suave)">{b.rotulo}</text>
              )}
            </g>
          );
        })}
      </svg>
      {atual && (
        <div
          className="pointer-events-none absolute top-2 z-10 whitespace-nowrap rounded-lg bg-tinta px-3 py-2 text-[13px] leading-snug text-white shadow-lg"
          style={{
            left: `${(xMira / W) * 100}%`,
            transform: xMira > W * 0.65 ? "translateX(calc(-100% - 10px))" : "translateX(10px)",
          }}
        >
          <b>{atual.titulo}</b>
          {atual.dica.map((l) => (
            <span key={l.rotulo} className="block">
              {l.rotulo} <b className="mono font-medium">{l.valor}</b>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Barras deitadas, em HTML: a lista de categorias ou setores com o tamanho de cada
 * um. ⚠️ HTML e não SVG porque o nome tem de quebrar linha e ser clicável — e é a
 * linha inteira que filtra o painel por aquele grupo.
 */
export function BarrasDeitadas({ linhas, valor, ativo, aoClicar }: {
  linhas: { chave: string; nome: string; valor: number; detalhe: string; id: number | null }[];
  valor: (v: number) => string;
  ativo?: number | null;
  aoClicar?: (id: number | null) => void;
}) {
  const teto = Math.max(...linhas.map((l) => l.valor), 0) || 1;
  return (
    <ul className="space-y-1.5">
      {linhas.map((l) => {
        const clicavel = !!aoClicar && l.id !== null;
        const corpo = (
          <>
            <span className="flex items-baseline justify-between gap-3 text-[13.5px]">
              <span className={`min-w-0 truncate ${ativo === l.id ? "font-bold" : ""}`}>{l.nome}</span>
              <span className="mono shrink-0">{valor(l.valor)}</span>
            </span>
            <span className="mt-0.5 block h-2 rounded-full bg-linha">
              <span className="block h-2 rounded-full"
                    style={{ width: `${(l.valor / teto) * 100}%`, background: COR_BARRA }} />
            </span>
            <span className="mt-0.5 block text-[12px] text-suave">{l.detalhe}</span>
          </>
        );
        return (
          <li key={l.chave}>
            {clicavel ? (
              <button type="button" className="block w-full rounded px-1 py-0.5 text-left hover:bg-linha/40"
                      title="filtrar o painel por este grupo" onClick={() => aoClicar?.(l.id)}>
                {corpo}
              </button>
            ) : (
              <div className="px-1 py-0.5">{corpo}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
