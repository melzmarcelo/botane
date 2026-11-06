"use client";

import { useLayoutEffect, useRef } from "react";

/**
 * Um número grande que ENCOLHE só quando não cabe na largura de quem o contém.
 *
 * 🔑 Pedido do dono (06/11/2026): *"dependendo do monitor, o valor faturado e ticket médio do
 * dashboard está estourando o quadrado"*. Com seis cartões numa linha, "R$ 12.345,67" a 26px passa
 * da borda; mas encolher TODOS pela largura do cartão deixava "77" minúsculo. Então cada valor
 * começa no tamanho cheio e, se passar, reduz na proporção exata do que sobrou (com piso).
 * ⚠️ Mede de novo quando o cartão muda de largura (`ResizeObserver`) e quando o texto muda.
 */
export default function ValorQueCabe({
  children, maximo, minimo = 12, className = "",
}: {
  children: React.ReactNode;
  maximo: number;
  minimo?: number;
  className?: string;
}) {
  const ref = useRef<HTMLParagraphElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    const pai = el?.parentElement;
    if (!el || !pai) return;
    const ajustar = () => {
      el.style.fontSize = `${maximo}px`;
      // O parágrafo é bloco: a largura dele é a que o cartão dá; o texto que passa vira rolagem.
      const cabe = el.clientWidth;
      if (el.scrollWidth > cabe && cabe > 0) {
        el.style.fontSize = `${Math.max(minimo, Math.floor(maximo * (cabe / el.scrollWidth) * 10) / 10)}px`;
      }
    };
    ajustar();
    const obs = new ResizeObserver(ajustar);
    obs.observe(pai);
    return () => obs.disconnect();
  }, [children, maximo, minimo]);
  return (
    <p ref={ref} className={`whitespace-nowrap ${className}`} style={{ fontSize: maximo }}>
      {children}
    </p>
  );
}
