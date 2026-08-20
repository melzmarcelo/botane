"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

/**
 * O aviso que aparece onde a pessoa está olhando.
 *
 * A mensagem de "salvo" ficava no TOPO da tela. Num formulário longo — produto,
 * ficha, nota — o botão de salvar está lá embaixo: a pessoa clicava, nada
 * parecia acontecer, e ela clicava de novo. O aviso agora flutua preso ao canto
 * inferior, à vista de qualquer rolagem.
 *
 * Sucesso some sozinho (a pessoa já viu o que queria ver); ERRO fica até
 * alguém fechar — sumir sozinho é o mesmo que não avisar, e erro que ninguém
 * leu vira retrabalho.
 *
 * O aviso pode carregar UMA ação: é ela que responde ao "cadastrei, e agora?"
 * — "criar outro" logo ali, sem voltar para a lista e clicar em novo.
 */

type Tipo = "ok" | "erro";

type Acao = { texto: string; ao: () => void };

type Recado = { id: number; tipo: Tipo; texto: string; acao?: Acao };

type API = {
  sucesso: (texto: string, acao?: Acao) => void;
  erro: (texto: string, acao?: Acao) => void;
  limpar: () => void;
};

const Contexto = createContext<API | null>(null);

const SEGUNDOS_ATE_SUMIR = 6000;

export function useAviso(): API {
  const ctx = useContext(Contexto);
  if (!ctx) throw new Error("useAviso precisa do ProvedorAvisos");
  return ctx;
}

export function ProvedorAvisos({ children }: { children: React.ReactNode }) {
  const [recados, setRecados] = useState<Recado[]>([]);
  const proximo = useRef(1);

  const remover = useCallback((id: number) => {
    setRecados((l) => l.filter((r) => r.id !== id));
  }, []);

  const empilhar = useCallback((tipo: Tipo, texto: string, acao?: Acao) => {
    const id = proximo.current++;
    // Três é o teto: uma pilha maior cobre a tela que a pessoa está usando.
    setRecados((l) => [...l.slice(-2), { id, tipo, texto, acao }]);
  }, []);

  const api: API = {
    sucesso: useCallback((t: string, a?: Acao) => empilhar("ok", t, a), [empilhar]),
    erro: useCallback((t: string, a?: Acao) => empilhar("erro", t, a), [empilhar]),
    limpar: useCallback(() => setRecados([]), []),
  };

  return (
    <Contexto.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-3 bottom-3 z-50 flex flex-col items-stretch gap-2 sm:inset-x-auto sm:right-6 sm:bottom-6 sm:w-[380px]"
        role="status"
        aria-live="polite"
      >
        {recados.map((r) => (
          <Balao key={r.id} recado={r} aoFechar={() => remover(r.id)} />
        ))}
      </div>
    </Contexto.Provider>
  );
}

function Balao({ recado, aoFechar }: { recado: Recado; aoFechar: () => void }) {
  const [entrou, setEntrou] = useState(false);

  useEffect(() => {
    const t = requestAnimationFrame(() => setEntrou(true));
    return () => cancelAnimationFrame(t);
  }, []);

  useEffect(() => {
    if (recado.tipo !== "ok") return;
    const t = setTimeout(aoFechar, SEGUNDOS_ATE_SUMIR);
    return () => clearTimeout(t);
  }, [recado.tipo, aoFechar]);

  const erro = recado.tipo === "erro";

  return (
    <div
      data-aviso={recado.tipo}
      className={`pointer-events-auto flex items-start gap-3 rounded border-l-4 bg-superficie px-4 py-3 shadow-[0_6px_24px_rgba(20,32,26,0.18)] transition-all duration-200 motion-reduce:transition-none ${
        entrou ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
      } ${erro ? "border-erro" : "border-erva"}`}
    >
      <span
        aria-hidden
        className={`mt-0.5 font-display text-[15px] leading-none font-bold ${
          erro ? "text-erro" : "text-erva"
        }`}
      >
        {erro ? "!" : "✓"}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-[14.5px] leading-snug break-words">{recado.texto}</p>
        {recado.acao && (
          <button
            type="button"
            className="mt-1.5 font-display text-[13px] font-semibold text-erva underline underline-offset-2 hover:text-tinta"
            onClick={() => {
              recado.acao?.ao();
              aoFechar();
            }}
          >
            {recado.acao.texto}
          </button>
        )}
      </div>
      <button
        type="button"
        aria-label="fechar aviso"
        className="-mt-1 -mr-1 px-1 text-[18px] leading-none text-suave hover:text-tinta"
        onClick={aoFechar}
      >
        ×
      </button>
    </div>
  );
}
