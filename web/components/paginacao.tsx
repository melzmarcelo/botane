"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * O rodapé de página das listas — o padrão da casa.
 *
 * Toda lista que pode crescer mostra um PEDAÇO e diz quantos existem. Sem isso
 * uma lista cheia e uma lista cortada são iguais na tela: a de compras mostrava
 * as 50 notas mais recentes de 3.670, e a nota do mês passado simplesmente não
 * existia para quem procurava.
 *
 * Duas decisões que valem para todos os grids:
 *
 * * **O corte é do SERVIDOR.** Trazer tudo e fatiar no navegador só troca a
 *   mentira de lugar — a lista continua cortada, agora pelo `LIMIT` que
 *   ninguém vê. Quem usa este rodapé manda `limite` e `offset` e lê o total no
 *   cabeçalho `X-Total`.
 * * **Quantos por página é escolha de quem olha**, e ela é lembrada. Conferir
 *   estoque pede 100 numa tela grande; o celular pede 20. Cada lista guarda a
 *   sua preferência, porque a resposta não é a mesma para todas.
 */

export const TAMANHOS = [20, 50, 100] as const;
export const POR_PAGINA_PADRAO = 20;

const chaveGuardada = (nome: string) => `botane:porPagina:${nome}`;

export type Paginacao = ReturnType<typeof usePaginacao>;

/**
 * O estado de paginação de uma lista.
 *
 * `nome` identifica a lista para guardar a preferência — use o nome da tela
 * ("produtos", "razao", "auditoria"), não um número.
 *
 * `filtros` são os valores que mudam o QUE a lista mostra (busca, tipo,
 * período). Quando um deles muda, a página volta ao começo — senão quem estava
 * na página 7 e digita uma busca cai numa tela vazia, sem nada explicando que
 * o resultado tem duas páginas e ele está pedindo a sétima.
 */
export function usePaginacao(
  nome: string,
  opcoes: { padrao?: number; filtros?: unknown[] } = {},
) {
  const padrao = opcoes.padrao ?? POR_PAGINA_PADRAO;
  const [porPagina, guardarPorPagina] = useState(padrao);
  const [pagina, setPagina] = useState(0);
  const [total, setTotal] = useState(0);

  // ⚠️ A preferência é lida num efeito, não no estado inicial: o servidor
  // renderiza esta tela antes de existir `localStorage`, e devolver valores
  // diferentes dos dois lados quebra a hidratação. O custo é uma busca a mais
  // no primeiro carregamento de quem escolheu um tamanho diferente do padrão.
  useEffect(() => {
    const guardado = Number(localStorage.getItem(chaveGuardada(nome)));
    if ((TAMANHOS as readonly number[]).includes(guardado)) guardarPorPagina(guardado);
  }, [nome]);

  // Comparado por VALOR: a lista de filtros é recriada a cada render, e
  // compará-la por identidade zeraria a página em todo render — inclusive no
  // que acontece logo depois de trocar de página.
  const marcaDosFiltros = JSON.stringify(opcoes.filtros ?? []);
  useEffect(() => {
    setPagina(0);
  }, [marcaDosFiltros]);

  const setPorPagina = useCallback(
    (n: number) => {
      guardarPorPagina(n);
      // Trocar o tamanho volta para a primeira página: manter a página 7 de uma
      // lista que agora tem 3 mostraria uma tela vazia sem explicação.
      setPagina(0);
      localStorage.setItem(chaveGuardada(nome), String(n));
    },
    [nome],
  );

  const paginas = Math.max(1, Math.ceil(total / porPagina));
  return {
    pagina,
    setPagina,
    porPagina,
    setPorPagina,
    total,
    setTotal,
    paginas,
    offset: pagina * porPagina,
    /** Os parâmetros que o servidor espera, prontos para a query. */
    parametros: { limite: String(porPagina), offset: String(pagina * porPagina) },
    /** Volta ao começo — para quando o FILTRO muda e a página 5 deixa de existir. */
    aoFiltrar: () => setPagina(0),
  };
}

/** Fatia uma lista já carregada. Só para grid que o servidor devolve inteiro. */
export function fatiar<T>(itens: T[], p: { offset: number; porPagina: number }): T[] {
  return itens.slice(p.offset, p.offset + p.porPagina);
}

export function Paginacao({
  p,
  rotulo = "registro(s)",
}: {
  p: Paginacao;
  /** O nome do que está sendo listado: "nota(s)", "produto(s)". */
  rotulo?: string;
}) {
  const { pagina, setPagina, porPagina, setPorPagina, total, paginas } = p;
  const primeiro = total === 0 ? 0 : pagina * porPagina + 1;
  const ultimo = Math.min((pagina + 1) * porPagina, total);

  // Uma página só e cabendo no menor tamanho: não há o que paginar, e um rodapé
  // de navegação numa lista de três linhas é ruído.
  if (total <= TAMANHOS[0] && paginas <= 1) return null;

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-linha pt-3">
      <span className="text-[13px] text-suave">
        {primeiro}–{ultimo} de{" "}
        <b className="mono text-texto">{total.toLocaleString("pt-BR")}</b> {rotulo}
      </span>

      <div className="flex items-center gap-3">
        <label className="flex items-center gap-2 whitespace-nowrap text-[13px] text-suave">
          por página
          <select
            className="campo w-[76px] py-1"
            aria-label="Registros por página"
            value={porPagina}
            onChange={(e) => setPorPagina(Number(e.target.value))}
          >
            {TAMANHOS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>

        <div className="flex items-center gap-1.5">
          <button
            className="btn btn-secundario px-2.5 py-1"
            onClick={() => setPagina(pagina - 1)}
            disabled={pagina === 0}
            aria-label="Página anterior"
          >
            ‹
          </button>
          <span className="mono min-w-[76px] text-center text-[13px] text-suave">
            {pagina + 1} de {paginas}
          </span>
          <button
            className="btn btn-secundario px-2.5 py-1"
            onClick={() => setPagina(pagina + 1)}
            disabled={pagina + 1 >= paginas}
            aria-label="Próxima página"
          >
            ›
          </button>
        </div>
      </div>
    </div>
  );
}
