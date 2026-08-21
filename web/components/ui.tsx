"use client";

import { ReactNode, useEffect } from "react";

export function Cartao({
  titulo,
  descricao,
  acao,
  children,
  className = "",
}: {
  titulo?: string;
  descricao?: string;
  acao?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`cartao ${className}`}>
      {(titulo || acao) && (
        <header className="flex items-start justify-between gap-4 border-b border-linha px-5 py-4">
          <div>
            {titulo && <h2 className="text-[17px] font-bold tracking-tight">{titulo}</h2>}
            {descricao && <p className="mt-1 text-[14px] text-suave">{descricao}</p>}
          </div>
          {acao}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function Campo({
  rotulo,
  dica,
  className = "",
  children,
}: {
  rotulo: string;
  dica?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="rotulo">{rotulo}</span>
      <div className="mt-1.5">{children}</div>
      {dica && <span className="mt-1 block text-[12.5px] text-suave">{dica}</span>}
    </label>
  );
}

export function Aviso({ tipo, children }: { tipo: "erro" | "ok" | "info"; children: ReactNode }) {
  const cor =
    tipo === "erro"
      ? "border-erro text-erro"
      : tipo === "ok"
        ? "border-erva text-erva"
        : "border-latao text-latao";
  return (
    <p className={`border-l-2 py-1 pl-3 text-[14px] ${cor}`} role="status">
      {children}
    </p>
  );
}

export function Vazio({ children }: { children: ReactNode }) {
  return <p className="px-1 py-8 text-center text-[15px] text-suave">{children}</p>;
}

export function Carregando({ children = "Carregando…" }: { children?: ReactNode }) {
  return <p className="px-1 py-8 text-center text-[14px] text-suave">{children}</p>;
}

export function Etiqueta({ cor = "neutro", children }: { cor?: "neutro" | "erva" | "alerta"; children: ReactNode }) {
  const estilo =
    cor === "erva"
      ? "border-erva/40 bg-erva-claro text-erva"
      : cor === "alerta"
        ? "border-alerta/40 text-alerta"
        : "border-linha2 text-suave";
  return (
    <span className={`mono inline-block rounded-full border px-2 py-0.5 text-[11px] ${estilo}`}>
      {children}
    </span>
  );
}

/**
 * Janela sobre a tela. Fecha no Esc e no clique fora — as duas saídas que todo
 * mundo tenta antes de procurar o X.
 */
export function Modal({
  titulo,
  descricao,
  aoFechar,
  children,
  largura = "760px",
}: {
  titulo: string;
  descricao?: string;
  aoFechar: () => void;
  children: ReactNode;
  largura?: string;
}) {
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        aoFechar();
      }
    };
    document.addEventListener("keydown", tecla);
    // Enquanto a janela está aberta a página atrás não rola: rolar o que está
    // por baixo dá a impressão de que o clique passou direto.
    const antes = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", tecla);
      document.body.style.overflow = antes;
    };
  }, [aoFechar]);

  return (
    <div
      className="fixed inset-0 z-40 flex items-start justify-center overflow-y-auto bg-tinta/45 p-4 sm:p-8"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) aoFechar();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className="cartao w-full shadow-[0_16px_48px_rgba(20,32,26,0.28)]"
        style={{ maxWidth: largura }}
      >
        <header className="flex items-start justify-between gap-4 border-b border-linha px-5 py-4">
          <div>
            <h2 className="text-[17px] font-bold tracking-tight">{titulo}</h2>
            {descricao && <p className="mt-1 text-[13.5px] text-suave">{descricao}</p>}
          </div>
          <button
            type="button"
            aria-label="fechar"
            className="-mt-1 px-1 text-[20px] leading-none text-suave hover:text-tinta"
            onClick={aoFechar}
          >
            ×
          </button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
