"use client";

/**
 * Avisos entre telas que não têm relação de pai e filho.
 * Hoje só um: a empresa mudou (nome ou logo) e o topo precisa se atualizar.
 */
export const EVENTO_EMPRESA = "botane:empresa-mudou";

export const avisarEmpresaMudou = () => {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(EVENTO_EMPRESA));
};
