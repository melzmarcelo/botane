"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { trocarNaUrl as trocar } from "@/lib/estado-na-url";
import { useCallback, useEffect, useMemo, useState } from "react";

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
  opcoes: {
    padrao?: number;
    filtros?: unknown[];
    /**
     * ⚠️ **Obrigatorio quando a TELA tem duas listas.** As duas escreveriam
     * `p` e `pp` na mesma URL e uma apagaria a outra -- virar a pagina dos
     * saldos levaria o razao junto, e ninguem ligaria uma coisa a outra. Com o
     * prefixo, a segunda lista usa `movp`/`movpp`. A primeira fica sem, para a
     * URL do caso comum continuar legivel.
     */
    prefixoUrl?: string;
  } = {},
) {
  const padrao = opcoes.padrao ?? POR_PAGINA_PADRAO;
  const pre = opcoes.prefixoUrl ?? "";
  const router = useRouter();
  const caminho = usePathname();
  const naUrl = useSearchParams();

  // 🔑 **A URL e a fonte da verdade da pagina e do tamanho** (09/09/2026,
  // pedido do dono). Antes viviam so em estado de componente: abrir um registro
  // e voltar remontava a tela do zero, e a lista reaparecia na primeira pagina,
  // com 20 linhas, como se ninguem tivesse escolhido nada. Na URL, o voltar do
  // navegador restaura tudo de graca -- e a tela filtrada vira um link que se
  // manda para alguem.
  const daUrl = (chave: string) => {
    const n = Number(naUrl.get(chave));
    return Number.isFinite(n) && n > 0 ? n : null;
  };
  const ppDaUrl = daUrl(`${pre}pp`);
  const porPagina = (TAMANHOS as readonly number[]).includes(ppDaUrl ?? 0)
    ? (ppDaUrl as number)
    : padrao;
  const pagina = Math.max(0, (daUrl(`${pre}p`) ?? 1) - 1);
  const [total, guardarTotal] = useState(0);

  // ⚠️ **`pronto` existe por causa de uma CORRIDA de verdade, nao por zelo.**
  // A preferencia guardada so pode ser lida num efeito (o servidor renderiza a
  // tela antes de existir `localStorage`, e valores diferentes dos dois lados
  // quebram a hidratacao). Sem esperar por ela, a tela dispara DUAS buscas --
  // `limite=20` e depois `limite=100` -- e nenhuma cancela a outra: quando a de
  // 20 chegava por ultimo, o seletor mostrava 100 e a lista trazia 20. Era esse
  // o defeito relatado. Quem lista espera `pronto` antes de buscar.
  const [pronto, setPronto] = useState(false);

  // ⚠️ **A escrita e COMPARTILHADA com os filtros** (`lib/estado-na-url`), e
  // monta a query a partir da URL de AGORA -- nao da que este render leu. Duas
  // escritas no mesmo tick partindo da mesma foto antiga fariam a segunda
  // apagar a primeira: trocar de pagina logo depois de digitar limparia a
  // busca, sem nada explicando.
  const trocarNaUrl = useCallback(
    (mudancas: Record<string, string | null>) => trocar(router, caminho, mudancas),
    [router, caminho],
  );

  // ⚠️ Nulo quer dizer "o servidor não disse", não "zero". Ele não diz ao virar
  // a página, porque o total do mesmo filtro não mudou — e recontar custaria a
  // tabela inteira. Aceitar o nulo como zero apagaria o rodapé na página 2.
  const setTotal = useCallback((n: number | null) => {
    if (n !== null && n !== undefined) guardarTotal(n);
  }, []);

  // 🔑 **"Guardar o que já tinha" pressupõe TER TIDO** (09/09/2026, relatado
  // pelo dono: *"quando vou para a segunda ou terceira página adiante, ao
  // entrar no produto e voltar para o grid, a parte de paginação some"*).
  // Ao voltar, a tela é montada do ZERO. A página vem da URL — `?p=3` —, mas o
  // total não vem de lugar nenhum: a primeira busca já sai com `offset = 40`, e
  // o servidor só conta no `offset = 0`. O total ficava em 0, o rodapé sumia
  // inteiro, e com ele o caminho de volta para a página 2: a lista ficava presa
  // naquela fatia, sem nada dizendo que existiam outras.
  // ⚠️ **Quem sabe que precisa é o CLIENTE.** O servidor não tem como saber se
  // aquela tela já viu o número antes — por isso o pedido é explícito.
  // ⚠️ E ele sai de `parametros`, que TODA lista espalha na query. Uma linha
  // aqui conserta as catorze, e a lista nova nasce consertada. Repetir a
  // condição em cada tela seria repeti-la errado numa delas.
  const precisaDoTotal = total === 0 && pagina > 0;

  // ⚠️ A preferencia e lida num efeito, nao no estado inicial: o servidor
  // renderiza esta tela antes de existir `localStorage`, e devolver valores
  // diferentes dos dois lados quebra a hidratacao. Ela so vale quando a URL NAO
  // diz nada -- URL escrita a mao, ou um link que alguem mandou, manda mais que
  // a preferencia guardada.
  useEffect(() => {
    if (ppDaUrl === null) {
      const guardado = Number(localStorage.getItem(chaveGuardada(nome)));
      if ((TAMANHOS as readonly number[]).includes(guardado) && guardado !== padrao) {
        trocarNaUrl({ [`${pre}pp`]: String(guardado), [`${pre}p`]: null });
        return;   // o `pronto` vem no render seguinte, ja com o valor certo
      }
    }
    setPronto(true);
  }, [nome, pre, ppDaUrl, padrao, trocarNaUrl]);

  const setPagina = useCallback(
    (n: number) => trocarNaUrl({ [`${pre}p`]: n <= 0 ? null : String(n + 1) }),
    [pre, trocarNaUrl],
  );

  // Comparado por VALOR: a lista de filtros e recriada a cada render, e
  // compara-la por identidade zeraria a pagina em todo render -- inclusive no
  // que acontece logo depois de trocar de pagina.
  const marcaDosFiltros = JSON.stringify(opcoes.filtros ?? []);
  useEffect(() => {
    // ⚠️ So volta ao comeco quando o filtro muda DEPOIS de a tela estar de pe.
    // Zerar na montagem apagaria a pagina que veio na URL -- que e justamente o
    // que se esta restaurando ao voltar de um registro.
    if (!pronto) return;
    trocarNaUrl({ [`${pre}p`]: null });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marcaDosFiltros]);

  const setPorPagina = useCallback(
    (n: number) => {
      // Trocar o tamanho volta para a primeira pagina: manter a pagina 7 de uma
      // lista que agora tem 3 mostraria uma tela vazia sem explicacao.
      trocarNaUrl({ [`${pre}pp`]: n === padrao ? null : String(n), [`${pre}p`]: null });
      localStorage.setItem(chaveGuardada(nome), String(n));
    },
    [nome, pre, padrao, trocarNaUrl],
  );

  const paginas = Math.max(1, Math.ceil(total / porPagina));
  return {
    /**
     * ⚠️ Falso ate a preferencia guardada ser resolvida. Quem lista precisa
     * esperar: buscar antes dispara a busca com o tamanho errado, e a resposta
     * atrasada dela sobrescreve a certa.
     */
    pronto,
    pagina,
    setPagina,
    porPagina,
    setPorPagina,
    total,
    setTotal,
    paginas,
    offset: pagina * porPagina,
    /** Os parâmetros que o servidor espera, prontos para a query. */
    parametros: {
      limite: String(porPagina),
      offset: String(pagina * porPagina),
      // Só quando falta: a contagem custa a tabela do filtro inteira, e virar a
      // página não pode pagá-la de novo a cada clique.
      ...(precisaDoTotal ? { com_total: "1" } : {}),
    },
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
