/**
 * Os favoritos do cliente — um coração por prato, guardado NO APARELHO.
 *
 * 🔑 **Sinal de interesse, não pedido** (complemento do dono, 14/10/2026): não substitui a
 * "minha seleção" nem o carrinho. Vale nos dois modos.
 * ⚠️ Por LOJA, e não por mesa: quem favoritou a torta na mesa 3 quer reencontrá-la na
 * próxima visita, sentado em outra mesa. Sem prazo de validade, ao contrário da seleção.
 */

import { useCallback, useEffect, useState } from "react";

const chave = (loja: number) => `cardapio.favoritos.${loja}`;

export function useFavoritos(loja: number) {
  const [ids, setIds] = useState<number[]>([]);

  useEffect(() => {
    try {
      const g = JSON.parse(localStorage.getItem(chave(loja)) ?? "[]");
      if (Array.isArray(g)) setIds(g.filter((x) => Number.isInteger(x)));
    } catch {
      /* sem armazenamento: começa vazio */
    }
  }, [loja]);

  /** Liga ou desliga; devolve se ficou favoritado. */
  const alternar = useCallback((id: number): boolean => {
    const fica = !ids.includes(id);
    const novos = fica ? [...ids, id] : ids.filter((x) => x !== id);
    setIds(novos);
    try {
      localStorage.setItem(chave(loja), JSON.stringify(novos));
    } catch {
      /* só não lembra depois */
    }
    return fica;
  }, [ids, loja]);

  return { ids, alternar, eh: (id: number) => ids.includes(id) };
}
