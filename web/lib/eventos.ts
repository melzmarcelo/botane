"use client";

/**
 * Avisos entre telas que não têm relação de pai e filho.
 * A empresa mudou (nome ou logo) e o topo precisa se atualizar.
 */
export const EVENTO_EMPRESA = "botane:empresa-mudou";

export const avisarEmpresaMudou = () => {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(EVENTO_EMPRESA));
};

/**
 * Abrir a busca de telas (a paleta do Ctrl+K).
 *
 * 🔑 **Evento, e não contexto.** Quem pede é um botão dentro do menu lateral;
 * quem responde é uma janela montada na casca, e as duas não têm relação de pai
 * e filho. Um contexto só para isto obrigaria a casca inteira a re-renderizar a
 * cada abertura da busca.
 */
export const EVENTO_BUSCA = "botane:abrir-busca";

export const abrirBuscaDeTelas = () => {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(EVENTO_BUSCA));
};
