"use client";

import { reais } from "@/lib/cadastros";

/**
 * A conta do CMV desenhada: cada barra parte de onde a anterior terminou.
 *
 * 🔑 **Protótipo aprovado pelo dono (16/09/2026).** Os cinco números já existiam
 * em ladrilhos separados, e quem lia montava a subtração de cabeça — é
 * justamente aí que se deixa de notar o que importa. Nesta base, desenhada, a
 * primeira coisa que salta é que **o estoque final cresceu 220 mil**: a casa
 * comprou muito mais do que consumiu no período, e o CMV pequeno não é mérito.
 *
 * ⚠️ **É a MESMA conta do relatório, não um gráfico à parte.** Os valores vêm da
 * apuração; nada é recalculado aqui. Um desenho que some por conta própria seria
 * a segunda versão da regra, e divergiria na primeira correção.
 *
 * ⚠️ **SVG à mão, sem biblioteca.** São cinco retângulos e dez rótulos; uma
 * dependência de gráfico para isso custaria mais peso no pacote do que a tela
 * inteira. O `viewBox` reserva as bordas para os rótulos de fora não serem
 * cortados.
 */
export default function Cascata({
  inicial,
  compras,
  final,
  cmv,
  receita,
}: {
  inicial: number;
  compras: number;
  final: number;
  cmv: number;
  receita: number;
}) {
  // A escala é o maior ponto que a cascata alcança — o topo das compras — ou a
  // receita, quando ela for maior. Sem incluir as duas, a barra da receita
  // estoura o quadro.
  const topo = Math.max(inicial + compras, receita, cmv, 1);
  const L = 70; // espaço à esquerda para os rótulos do eixo
  const BASE = 210; // a linha do zero
  const ALTO = 182; // altura útil do desenho
  const y = (v: number) => BASE - (v / topo) * ALTO;
  const alturaDe = (de: number, ate: number) => Math.max(2, Math.abs(y(de) - y(ate)));

  // Cada passo: [x, rótulo, valor exibido, de, até, cor]
  const largura = 110;
  const passo = 160;
  const barras = [
    { nome: "estoque inicial", valor: inicial, de: 0, ate: inicial, cor: "var(--color-linha2)" },
    { nome: "compras", valor: compras, de: inicial, ate: inicial + compras,
      cor: "var(--color-erva)" },
    { nome: "estoque final", valor: -final, de: inicial + compras, ate: cmv,
      cor: "var(--color-erro)" },
    { nome: "= CMV real", valor: cmv, de: 0, ate: cmv, cor: "var(--color-tinta)" },
    { nome: "receita", valor: receita, de: 0, ate: receita, cor: "var(--color-latao)" },
  ];

  const marcas = [1, 0.75, 0.5, 0.25, 0].map((f) => ({ f, v: topo * f }));
  const curto = (v: number) =>
    Math.abs(v) >= 1000 ? `${Math.round(v / 1000)} mil` : String(Math.round(v));

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox="0 0 900 270"
        className="h-[270px] w-full min-w-[640px]"
        role="img"
        aria-label={
          `Estoque inicial ${reais(inicial)}, mais compras ${reais(compras)}, ` +
          `menos estoque final ${reais(final)}, dão CMV de ${reais(cmv)}. ` +
          `Receita do período: ${reais(receita)}.`
        }
      >
        {marcas.map((m) => (
          <g key={m.f}>
            <line
              x1={L} y1={y(m.v)} x2={880} y2={y(m.v)}
              stroke="var(--color-linha)" strokeWidth="1"
            />
            <text
              x={L - 8} y={y(m.v) + 4} textAnchor="end"
              fontSize="10" fill="var(--color-suave)"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {curto(m.v)}
            </text>
          </g>
        ))}

        {barras.map((b, i) => {
          const x = 95 + i * passo;
          const alto = Math.min(y(b.de), y(b.ate));
          return (
            <g key={b.nome}>
              <rect
                x={x} y={alto} width={largura} height={alturaDe(b.de, b.ate)}
                fill={b.cor} rx="2"
              />
              <text
                x={x + largura / 2} y={BASE + 22} textAnchor="middle"
                fontSize="11.5" fill="var(--color-tinta)"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                {reais(b.valor)}
              </text>
              <text
                x={x + largura / 2} y={BASE + 40} textAnchor="middle"
                fontSize="11" fill="var(--color-suave)"
              >
                {b.nome}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
