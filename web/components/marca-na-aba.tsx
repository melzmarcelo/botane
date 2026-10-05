"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { useMarca } from "@/lib/marca";

/**
 * O título e o ícone da ABA do navegador: o nome e a logo da casa.
 *
 * 🔑 **Pedido do dono (05/10/2026):** *"como no reservas, colocar a logo no
 * título da página no navegador"*. O site do cliente já fazia isso
 * (`pintarOIcone` em `site/index.html`); aqui a aba dizia um nome fixo, com um
 * ícone que não era de ninguém.
 *
 * ⚠️ **Refaz a cada navegação** (`caminho` nas dependências): o `<title>` e o
 * `<link rel="icon">` são do `metadata` do Next, e ele pode reescrevê-los ao
 * trocar de rota.
 * ⚠️ **Sem logo cadastrada, o ícone padrão fica** — inventar uma imagem seria
 * mostrar a marca de outra pessoa.
 */
export default function MarcaNaAba() {
  const marca = useMarca();
  const caminho = usePathname();

  useEffect(() => {
    if (!marca) return;
    document.title = marca.nome;
    if (!marca.logo) return;
    document
      .querySelectorAll<HTMLLinkElement>('link[rel="icon"], link[rel="apple-touch-icon"]')
      .forEach((link) => {
        // O `type` e o `sizes` descrevem o PNG padrão; a logo pode ser outro formato.
        link.removeAttribute("type");
        link.removeAttribute("sizes");
        link.href = marca.logo!;
      });
  }, [marca, caminho]);

  return null;
}
