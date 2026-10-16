"use client";

/**
 * O seletor de idioma do Cardápio Vivo — a MESMA pílula PT · EN · DE do site
 * (`.idiomas` em `site/index.html`): fundo escuro translúcido, o idioma escolhido em claro.
 *
 * 🔑 Pedido do dono (16/10/2026): *"ao selecionar o idioma na primeira página, leva para as
 * demais; mas se selecionar dentro do catálogo, ao voltar, se perde a seleção. E manter o
 * mesmo estilo de seleção em todas as páginas."* Era um `<select>`, de outra cara.
 * 🔑 **A escolha fica na ABA, na mesma chave do site** (`sessionStorage["botane.idioma"]`):
 * site e feed estão no mesmo endereço, então o que se escolhe num vale no outro.
 */

import type { Idioma } from "@/lib/cardapio-vivo";

const IDIOMAS: Idioma[] = ["pt", "en", "de"];
export const CHAVE_IDIOMA = "botane.idioma";

/** Grava a escolha onde o site também lê. ⚠️ Sem armazenamento, vale só nesta tela. */
export function lembrarIdioma(i: Idioma) {
  try {
    sessionStorage.setItem(CHAVE_IDIOMA, i);
  } catch {
    /* navegador sem armazenamento */
  }
}

/** O idioma guardado na aba (o que a pessoa escolheu no site ou no feed), se houver. */
export function idiomaDaAba(): Idioma | null {
  try {
    const salvo = sessionStorage.getItem(CHAVE_IDIOMA);
    return salvo === "pt" || salvo === "en" || salvo === "de" ? salvo : null;
  } catch {
    return null;
  }
}

export default function SeletorDeIdioma({ idioma, aoEscolher, className = "" }: {
  idioma: Idioma; aoEscolher: (i: Idioma) => void; className?: string;
}) {
  return (
    <span role="group" aria-label="idioma · language · Sprache"
          className={`flex shrink-0 gap-0.5 rounded-full bg-[rgba(20,26,22,.72)] p-[3px] ${className}`}>
      {IDIOMAS.map((i) => (
        <button key={i} type="button" data-idioma={i} aria-pressed={i === idioma}
                onClick={() => { if (i !== idioma) { lembrarIdioma(i); aoEscolher(i); } }}
                className={`rounded-full px-2 py-[3px] text-[11px] font-medium leading-none ${
                  i === idioma ? "bg-[#F1EDE2] text-[#1B211C]" : "text-[#F1EDE2]"}`}>
          {i.toUpperCase()}
        </button>
      ))}
    </span>
  );
}
