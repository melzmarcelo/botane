"use client";

import { ReactNode, useEffect, useRef } from "react";

import { mascaraMoeda } from "@/lib/numeros";

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
  // A forma mora no CSS (`.aviso`), não em oito utilitárias repetidas aqui: o
  // aviso aparece em quase toda tela, e um balão diferente por página seria a
  // primeira coisa a divergir.
  return (
    <p className={`aviso aviso-${tipo}`} role="status">
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
    <span className={`mono inline-block rounded-full border px-2.5 py-[3px] text-[11px] ${estilo}`}>
      {children}
    </span>
  );
}

/**
 * Janela sobre a tela. Fecha no Esc e no clique fora — as duas saídas que todo
 * mundo tenta antes de procurar o X.
 */
/**
 * 🔑 **A pilha de janelas abertas — só a de cima responde ao Escape.**
 *
 * ⚠️ Cada `Modal` registrava o ouvinte no `document`, e `stopPropagation` NÃO
 * impede outro ouvinte no MESMO nó (isso seria `stopImmediatePropagation`). Com
 * duas janelas abertas — a busca por cima da Vincular, por exemplo — um Escape
 * fechava as DUAS: a pessoa dispensava a busca e perdia junto a lista de
 * cadastros que tinha montado. Passou a doer de verdade quando a busca ganhou
 * seleção múltipla, porque aí há trabalho acumulado dentro dela para perder.
 *
 * A pilha é de módulo de propósito: é um fato do documento, não de uma árvore
 * de componentes — as janelas não são pai e filha uma da outra.
 */
const _janelasAbertas: symbol[] = [];

export function Modal({
  titulo,
  descricao,
  aoFechar,
  children,
  rodape,
  largura = "760px",
}: {
  titulo: string;
  descricao?: string;
  aoFechar: () => void;
  children: ReactNode;
  /**
   * O que fica GRUDADO embaixo, fora da rolagem: os botões da ação e o número
   * que se olha antes de clicar. Dentro do corpo eles rolam para fora da vista
   * numa janela longa, e quem não vê o botão acha que a janela não tem saída.
   */
  rodape?: ReactNode;
  largura?: string;
}) {
  useEffect(() => {
    const eu = Symbol("janela");
    _janelasAbertas.push(eu);
    const tecla = (e: KeyboardEvent) => {
      // Só a janela do TOPO fecha. As de baixo ignoram e continuam abertas.
      if (e.key === "Escape" && _janelasAbertas[_janelasAbertas.length - 1] === eu) {
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
      const onde = _janelasAbertas.indexOf(eu);
      if (onde >= 0) _janelasAbertas.splice(onde, 1);
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
      {/* ⚠️ A janela CABE na tela e rola por dentro.
          Ela era do tamanho do conteúdo, e a de exportação — com cinco filtros
          — passava de mil pixels: numa tela de notebook os últimos campos e o
          botão de baixar ficavam fora, sem barra de rolagem em lugar nenhum
          (o corpo da página está travado enquanto a janela está aberta). Agora
          o cartão é limitado pela altura da JANELA, o cabeçalho e o rodapé
          ficam parados, e só o miolo rola.
          ⚠️ `dvh`, não `vh`: no celular a barra de endereço entra na conta do
          `vh`, e o pedaço de baixo do cartão fica atrás dela. */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className="cartao flex max-h-[calc(100dvh-2rem)] w-full flex-col shadow-[0_16px_48px_rgba(20,32,26,0.28)] sm:max-h-[calc(100dvh-4rem)]"
        style={{ maxWidth: largura }}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-linha px-5 py-4">
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
        {/* `min-h-0` é o que deixa um filho de flex encolher abaixo do próprio
            conteúdo — sem ele o `overflow-y-auto` não tem o que rolar. */}
        <div className="min-h-0 flex-1 overflow-y-auto p-5">{children}</div>
        {rodape && (
          <div className="shrink-0 border-t border-linha px-5 py-4">{rodape}</div>
        )}
      </div>
    </div>
  );
}

/**
 * A pergunta antes do que não se desfaz.
 *
 * `window.confirm` e `window.prompt` funcionam, mas são a caixa do NAVEGADOR:
 * fonte de sistema, botão em inglês, e nenhuma chance de explicar o que a ação
 * faz. Numa tela que existe para dar confiança sobre estoque e dinheiro, a
 * confirmação é parte do produto.
 */
export function Confirmacao({
  titulo,
  children,
  rotuloConfirmar = "Confirmar",
  perigo = false,
  ocupado = false,
  aoConfirmar,
  aoCancelar,
}: {
  titulo: string;
  children: ReactNode;
  rotuloConfirmar?: string;
  perigo?: boolean;
  ocupado?: boolean;
  aoConfirmar: () => void;
  aoCancelar: () => void;
}) {
  return (
    <Modal titulo={titulo} aoFechar={aoCancelar} largura="480px">
      <div className="text-[15px] leading-snug">{children}</div>
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <button type="button" className="btn btn-secundario" onClick={aoCancelar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn-primario"
          style={perigo ? { background: "var(--color-erro)" } : undefined}
          onClick={aoConfirmar}
          disabled={ocupado}
          autoFocus
        >
          {ocupado ? "…" : rotuloConfirmar}
        </button>
      </div>
    </Modal>
  );
}


/** Campo de DINHEIRO, com máscara de verdade.
 *
 * 🔑 **`type="number"` não serve para preço.** Era o que estava no cadastro de
 * produtos, e traz três defeitos que só aparecem com gente usando: no teclado
 * pt-BR a vírgula não entra em parte dos navegadores (quem digitava "12,50"
 * gravava 12), o campo aceita "1e5" e "1.2.3", e a setinha de incremento
 * aparece em cima de um preço, onde ela não quer dizer nada.
 *
 * 🔑 **Os centavos entram primeiro, como em caixa de banco**: digitar "1250"
 * mostra 12,50, e o valor cresce pela direita. É a única forma em que apagar um
 * caractere faz o que se espera — com a vírgula solta no meio do texto, o
 * cursor cai do lado errado dela e o número muda de ordem de grandeza sem
 * ninguém entender por quê.
 *
 * ⚠️ **O "R$" fica FORA do campo, como prefixo.** Dentro do valor ele seria
 * apagável, e apagá-lo não muda o valor — controle que aceita clique e não faz
 * nada é pior que controle nenhum.
 *
 * ⚠️ `inputMode="decimal"` chama o teclado numérico do celular sem trazer as
 * armadilhas do `type="number"`; a contagem e o cadastro acontecem com o
 * telefone na mão.
 */
export function CampoMoeda({
  valor,
  aoMudar,
  desabilitado = false,
  placeholder,
  className = "",
}: {
  valor: string;
  aoMudar: (v: string) => void;
  desabilitado?: boolean;
  placeholder?: string;
  className?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);

  // ⚠️ **O cursor mora no FIM — sempre, e não só depois de digitar.** O valor
  // cresce pela direita, então é o único lugar onde ele faz sentido. Sem isso
  // os dígitos se espalham pelo meio do número: medido, com "18,99" no campo e
  // o cursor na posição 1, digitar "5" e depois "7" dava **1.578,99** — o 5 e o
  // 7 separados pelos dígitos velhos, que não é o que ninguém quis escrever.
  // Com o fim garantido dá 1.899,57, que é o número na ordem em que foi
  // digitado.
  // ⚠️ Vale no FOCO também, não só na mudança: quem clica no meio do texto
  // espera continuar escrevendo o número, não emendar um algarismo lá dentro.
  const paraOFim = (el: HTMLInputElement | null) => {
    if (el) el.setSelectionRange(el.value.length, el.value.length);
  };
  useEffect(() => {
    const el = ref.current;
    if (el && document.activeElement === el) paraOFim(el);
  }, [valor]);

  return (
    <div className="relative">
      <span
        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[14px] text-suave"
        aria-hidden="true"
      >
        R$
      </span>
      <input
        ref={ref}
        className={`campo mono pl-9 text-right ${className}`}
        type="text"
        inputMode="decimal"
        disabled={desabilitado}
        placeholder={placeholder}
        value={valor}
        onChange={(e) => aoMudar(mascaraMoeda(e.target.value))}
        onFocus={(e) => paraOFim(e.currentTarget)}
        onClick={(e) => paraOFim(e.currentTarget)}
      />
    </div>
  );
}
