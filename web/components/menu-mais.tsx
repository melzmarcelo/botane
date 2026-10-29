"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

/**
 * "Mais ▾": o que é de vez em quando sai da fila de botões do topo da tela.
 *
 * 🔑 Auditoria de 29/10/2026: Notas de entrada tinha sete botões no topo, quebrando em duas
 * linhas, e o do dia a dia pesava igual ao de uma vez por mês. Fica um principal, dois ou três
 * secundários e o resto aqui.
 * ⚠️ **Fechado é `invisible`, não desmontado.** Os itens são botões da casa que abrem janela
 * (Imprimir, confirmação) e guardam o estado dela; desmontar o menu ao clicar fecharia a
 * janela no mesmo instante. Por isso o `Modal` leva `visible`: ele é filho do menu no DOM e,
 * sem isso, herdaria o `invisible` do menu fechado.
 */
export default function MenuMais({ children, rotulo = "Mais" }: { children: ReactNode; rotulo?: string }) {
  const [aberto, setAberto] = useState(false);
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (!caixa.current?.contains(e.target as Node)) setAberto(false);
    };
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAberto(false);
    };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", tecla);
    };
  }, [aberto]);

  return (
    <div ref={caixa} className="relative">
      <button
        type="button"
        className="btn btn-secundario"
        aria-haspopup="menu"
        aria-expanded={aberto}
        onClick={() => setAberto((a) => !a)}
      >
        {rotulo} <span aria-hidden>▾</span>
      </button>
      <div
        role="menu"
        className={`menu-mais ${aberto ? "" : "invisible"}`}
        // Escolheu um item: o menu fecha (a janela que ele abriu continua — ver acima).
        onClick={(e) => {
          if ((e.target as HTMLElement).closest(".menu-mais > button, .menu-mais > a")) setAberto(false);
        }}
      >
        {children}
      </div>
    </div>
  );
}
