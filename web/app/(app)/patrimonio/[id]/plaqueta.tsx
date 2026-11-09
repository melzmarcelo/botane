"use client";

import type { BemDetalhe } from "@/lib/patrimonio";

/**
 * A prévia da plaqueta, no tamanho (proporção) do rolo configurado em Etiquetas.
 * 🔑 **O QR vem do servidor como matriz**, do mesmo codificador do PDF: a prévia é o QR que
 * vai ser impresso, e o pacote do navegador não ganha uma biblioteca de QR.
 * ⚠️ A disposição imita `_desenhar` (`services/patrimonio.py`): QR à esquerda, código grande,
 * equipamento, setor · local e série. Mudou lá, muda aqui.
 */
export default function PreviaPlaqueta({ bem }: { bem: BemDetalhe }) {
  const { qr, largura_mm, altura_mm } = bem.plaqueta;
  const n = qr.length;
  const onde = [bem.setor, bem.local].filter(Boolean).join(" · ");
  return (
    <figure className="m-0" id="bem-plaqueta-previa">
      <div className="flex items-center gap-3 overflow-hidden rounded-md border border-linha2 bg-white p-2.5 text-black"
           style={{ aspectRatio: `${largura_mm} / ${altura_mm}` }}>
        <svg viewBox={`-2 -2 ${n + 4} ${n + 4}`} className="h-full max-h-full shrink-0" role="img"
             aria-label={`QR que abre ${bem.plaqueta.link}`} shapeRendering="crispEdges">
          <rect x={-2} y={-2} width={n + 4} height={n + 4} fill="#fff" />
          {qr.map((linha, y) => [...linha].map((m, x) =>
            m === "1" ? <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} fill="#000" /> : null))}
        </svg>
        <div className="min-w-0 leading-tight">
          <p className="text-[9px] font-semibold uppercase tracking-[0.08em]">Patrimônio</p>
          <p className="mono whitespace-nowrap text-[17px] font-extrabold">{bem.codigo}</p>
          <p className="line-clamp-2 text-[11px] font-bold uppercase">{bem.descricao}</p>
          {onde && <p className="truncate text-[9.5px]">{onde}</p>}
          {bem.numero_serie && <p className="truncate text-[9.5px]">Série: {bem.numero_serie}</p>}
        </div>
      </div>
      <figcaption className="mt-2 text-[12.5px] text-suave">
        {largura_mm.toLocaleString("pt-BR")} × {altura_mm.toLocaleString("pt-BR")} mm, o rolo de Etiquetas ▸
        Configuração. O QR abre esta ficha.
      </figcaption>
    </figure>
  );
}
