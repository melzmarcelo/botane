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
 * **Os dois somem sozinhos**, o erro depois de mais que o dobro do tempo:
 * ninguém quer fechar aviso na mão, e uma pilha que não se limpa acaba tapando
 * a tela que a pessoa está usando. O erro ganha mais tempo porque costuma ter
 * frase longa — e **para de contar enquanto o ponteiro está em cima**, que era
 * o medo real: a mensagem sumir no meio da leitura. Parada a leitura, o tempo
 * volta a correr.
 *
 * A barrinha embaixo mostra quanto falta. Sem ela, o aviso sumindo parece a
 * tela piscando; com ela, é uma coisa que estava anunciada.
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

// ⚠️ Em milissegundos, apesar do nome antigo. Erro fica mais que o dobro: a
// frase é mais longa, e ler "não foi possível gravar porque tal produto não
// converte de CX para KG" leva mais tempo que ler "salvo".
const TEMPO_ATE_SUMIR: Record<Tipo, number> = { ok: 6000, erro: 14000 };

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

  const total = TEMPO_ATE_SUMIR[recado.tipo];
  const [pausado, setPausado] = useState(false);
  // Quanto ainda falta. Fica num `ref` porque o relógio não pode reiniciar a
  // cada render — só quando a pessoa tira o ponteiro de cima.
  const restante = useRef(total);
  const [progresso, setProgresso] = useState(1);

  useEffect(() => {
    if (pausado) return;
    const comecou = Date.now();
    const fim = comecou + restante.current;

    // ⚠️ O intervalo só pinta a barra; quem fecha é o `setTimeout`. Fechar
    // dentro do intervalo faria o aviso sumir num múltiplo de 80 ms depois da
    // hora — invisível, mas é o tipo de imprecisão que vira bug de teste.
    const pulso = setInterval(() => {
      setProgresso(Math.max(0, (fim - Date.now()) / total));
    }, 80);
    const relogio = setTimeout(aoFechar, restante.current);

    return () => {
      clearInterval(pulso);
      clearTimeout(relogio);
      restante.current = Math.max(0, fim - Date.now());
    };
  }, [pausado, total, aoFechar]);

  const erro = recado.tipo === "erro";

  return (
    <div
      data-aviso={recado.tipo}
      // ⚠️ Passar o ponteiro (ou dar foco, para quem anda de teclado) SEGURA o
      // aviso. É o que torna o fechar-sozinho seguro: quem está lendo não vê a
      // frase sumir no meio.
      onMouseEnter={() => setPausado(true)}
      onMouseLeave={() => setPausado(false)}
      onFocusCapture={() => setPausado(true)}
      onBlurCapture={() => setPausado(false)}
      className={`pointer-events-auto relative flex items-start gap-3 overflow-hidden rounded border-l-4 bg-superficie px-4 py-3 shadow-[0_6px_24px_rgba(20,32,26,0.18)] transition-all duration-200 motion-reduce:transition-none ${
        entrou ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
      } ${erro ? "border-erro" : "border-erva"}`}
    >
      {/* A barra diz quanto falta — e para de andar quando o aviso está pausado.
          `aria-hidden`: é informação de tempo, não de conteúdo, e um leitor de
          tela anunciando percentual a cada 80 ms seria ruído puro. */}
      <span
        aria-hidden
        className={`absolute inset-x-0 bottom-0 h-[3px] origin-left ${
          erro ? "bg-erro/50" : "bg-erva/50"
        }`}
        style={{ transform: `scaleX(${progresso})` }}
      />
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
