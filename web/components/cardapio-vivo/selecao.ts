/**
 * A "minha seleção" do modo VITRINE — fica NO APARELHO e não gera pedido.
 *
 * 🔑 É uma lista para mostrar ao garçom, não um carrinho: nada vai ao servidor além dos
 * eventos `adicionou`/`removeu`, que são o que mede o "quase pediu".
 * ⚠️ Guardada por loja + mesa: quem abriu o cardápio da mesa 3 ontem não encontra a
 * seleção de ontem na mesa 7 hoje. E vence em 6 h.
 */

import { useCallback, useEffect, useState } from "react";

/** `quantidade` (142): a mesma opção mais de uma vez, nos grupos que deixam ("2× Geleia"). */
export type EscolhaAdicional = { id: number; nome: string; preco: number | null; quantidade?: number };

export type LinhaSelecao = {
  chave: string;
  id_item: number;
  /** 142: o PRODUTO escolhido no item de escolha (Chocolate Quente → Branco). */
  escolha?: number | null;
  nome: string;
  preco: number | null;
  quantidade: number;
  adicionais: EscolhaAdicional[];
};

const vezes = (a: EscolhaAdicional) => a.quantidade ?? 1;

/** "2× Geleia · Pão" — como a linha mostra os adicionais. */
export const nomeDosAdicionais = (adicionais: EscolhaAdicional[]) =>
  adicionais.map((a) => (vezes(a) > 1 ? `${vezes(a)}× ${a.nome}` : a.nome)).join(" · ");

/** Os ids como o servidor os quer: a opção repetida aparece uma vez por unidade. */
export const idsDosAdicionais = (adicionais: EscolhaAdicional[]) =>
  adicionais.flatMap((a) => Array<number>(vezes(a)).fill(a.id));

const VALIDADE_MS = 6 * 60 * 60 * 1000;

const chaveDoArmazem = (loja: number, mesa: string | null) => `cardapio.selecao.${loja}.${mesa ?? "loja"}`;

/** Mesmo item com as mesmas escolhas soma na linha; escolhas diferentes são outra linha. */
export const chaveDaLinha = (idItem: number, adicionais: EscolhaAdicional[], escolha?: number | null) =>
  `${idItem}:${escolha ?? ""}:${idsDosAdicionais(adicionais).sort((a, b) => a - b).join(",")}`;

export function precoDaLinha(l: LinhaSelecao): number | null {
  if (l.preco === null) return null;
  const extras = l.adicionais.reduce((s, a) => s + (a.preco ?? 0) * vezes(a), 0);
  return (l.preco + extras) * l.quantidade;
}

export function useSelecao(loja: number, mesa: string | null) {
  const [linhas, setLinhas] = useState<LinhaSelecao[]>([]);
  const chave = chaveDoArmazem(loja, mesa);

  // ⚠️ Lido num efeito, não no inicializador: a página é pré-renderizada no servidor.
  useEffect(() => {
    try {
      const g = JSON.parse(localStorage.getItem(chave) ?? "null");
      if (g && Date.now() - g.em < VALIDADE_MS && Array.isArray(g.linhas)) setLinhas(g.linhas);
    } catch {
      /* sem armazenamento: começa vazia */
    }
  }, [chave]);

  const gravar = useCallback((novas: LinhaSelecao[]) => {
    setLinhas(novas);
    try {
      localStorage.setItem(chave, JSON.stringify({ em: Date.now(), linhas: novas }));
    } catch {
      /* só não lembra depois */
    }
  }, [chave]);

  const adicionar = useCallback((l: Omit<LinhaSelecao, "chave">) => {
    const k = chaveDaLinha(l.id_item, l.adicionais, l.escolha);
    const existente = linhas.find((x) => x.chave === k);
    gravar(existente
      ? linhas.map((x) => (x.chave === k ? { ...x, quantidade: x.quantidade + l.quantidade } : x))
      : [...linhas, { ...l, chave: k }]);
  }, [linhas, gravar]);

  const remover = useCallback((k: string) => gravar(linhas.filter((x) => x.chave !== k)), [linhas, gravar]);
  const limpar = useCallback(() => gravar([]), [gravar]);

  const quantidade = linhas.reduce((s, l) => s + l.quantidade, 0);
  const total = linhas.reduce((s, l) => s + (precoDaLinha(l) ?? 0), 0);
  const algumSemPreco = linhas.some((l) => l.preco === null);
  return { linhas, adicionar, remover, limpar, quantidade, total, algumSemPreco };
}
