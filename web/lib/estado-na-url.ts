"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Estado de tela que vive na URL — o filtro que sobrevive ao voltar.
 *
 * 🔑 **O pedido do dono (09/09/2026):** "quando faço um filtro, acesso o
 * produto, volto, gostaria que o filtro continuasse". Enquanto o filtro morava
 * só em `useState`, abrir um registro e voltar remontava a tela do zero: a
 * lista reaparecia inteira, como se ninguém tivesse procurado nada.
 *
 * Na URL, o voltar do navegador restaura tudo sem nenhum código de restauração
 * — e a tela filtrada vira um link que se manda para alguém.
 */

/** A última escrita que este módulo pediu ao router, e de onde ela partiu.
 *
 * `partida` é a URL que havia quando a escrita foi montada; `destino`, a que ela
 * produziu. Enquanto o navegador não sair de uma para a outra, a escrita está
 * **em voo** — e é `destino` que descreve o estado, não a barra de endereço.
 */
let emVoo: { caminho: string; partida: string; destino: string; em: number } | null = null;

/** Quanto tempo um rascunho em voo continua valendo (ms).
 *
 * ⚠️ **Existe por causa do VOLTAR do navegador.** O par partida/destino
 * identifica o voo com precisão, menos num caso: voltar logo depois de uma
 * escrita devolve a URL exatamente à `partida`, que é indistinguível de "a
 * escrita ainda não aterrissou". Aí o rascunho reaplicaria a mudança que a
 * pessoa acabou de desfazer. Dois segundos cobrem com folga a ida ao servidor
 * de um `replace` (milissegundos em produção, mais no `next dev`) e são menos
 * do que qualquer pessoa leva para ler a tela e decidir voltar.
 */
const VALIDADE_DO_VOO = 2000;

/**
 * ⚠️ **A query se monta a partir da URL DE AGORA, não da que o render leu.**
 *
 * Uma tela tem vários pedaços de estado na URL (a busca, o tipo, a página), e
 * cada um escreve pelo seu próprio caminho. Montando a query a partir do
 * `useSearchParams` capturado no render, duas escritas no mesmo tick partem da
 * mesma foto antiga e a segunda apaga a primeira — trocar o tipo logo depois de
 * digitar limparia a busca, sem nada explicando.
 *
 * 🔑 **E `window.location.search` também mente, por um tempo** (12/09/2026,
 * achado ao investigar a checagem "filtrar volta para a primeira página"). O
 * `router.replace` do App Router é navegação suave: ele vai ao servidor buscar
 * a árvore e só então a barra de endereço muda. Entre pedir e aterrissar — dez
 * milissegundos em produção, bem mais no `next dev` — a URL ainda é a antiga, e
 * quem ler dali monta a query em cima de um estado que já foi trocado.
 *
 * **O caso medido**: na página 2, digitar no filtro. O reset de página escreve
 * `p: null` na hora; a busca escreve 300 ms depois e lê a URL — que ainda dizia
 * `p=2`, porque o reset não tinha aterrissado. Resultado: `?p=2&busca=...`,
 * página 2 de um resultado de uma página só, **lista vazia**. Digitando devagar
 * passava (o reset aterrissava entre as teclas); colando, nunca.
 *
 * 🔑 **Então a base é o DESTINO do que ainda está em voo**, e a barra de
 * endereço só quando não há voo — ou quando ele já não é de confiança (outra
 * tela, o voltar do navegador, tempo demais). Uma escrita só continua não
 * enxergando a outra pelo `window`, mas passa a enxergá-la aqui.
 */
export function trocarNaUrl(
  router: { replace: (url: string, o?: { scroll?: boolean }) => void },
  caminho: string,
  mudancas: Record<string, string | null>,
) {
  const agora = typeof window === "undefined" ? "" : window.location.search;
  // O rascunho vale enquanto a URL for uma das duas pontas do voo anterior: a
  // partida (não aterrissou) ou o destino (aterrissou, e aí dá no mesmo).
  // Qualquer outra coisa foi mudança de fora, e manda mais que o rascunho.
  const valido =
    emVoo !== null &&
    emVoo.caminho === caminho &&
    Date.now() - emVoo.em < VALIDADE_DO_VOO &&
    (agora === emVoo.partida || agora === emVoo.destino);
  const base = valido ? (emVoo as NonNullable<typeof emVoo>).destino : agora;

  const q = new URLSearchParams(base);
  for (const [k, v] of Object.entries(mudancas)) {
    if (v === null || v === "") q.delete(k);
    else q.set(k, v);
  }
  const texto = q.toString();
  const destino = texto ? `?${texto}` : "";
  emVoo = { caminho, partida: agora, destino, em: Date.now() };
  // ⚠️ `replace`, não `push`: cada tecla digitada virando uma entrada no
  // histórico faria o voltar do navegador desfazer a busca letra por letra
  // antes de sair da tela.
  router.replace(texto ? `${caminho}?${texto}` : caminho, { scroll: false });
}

/**
 * Um pedaço de estado da tela guardado na URL. Usa-se como `useState`.
 *
 *     const [busca, setBusca] = useEstadoNaUrl("busca", "");
 *     const [inativos, setInativos] = useEstadoNaUrl("inativos", false);
 *
 * ⚠️ **O valor volta na hora; a URL, com atraso.** Escrever a URL a cada tecla
 * re-renderiza a árvore inteira por caractere e a digitação engasga. O estado
 * local responde imediatamente e a URL alcança depois — quem sai da tela já
 * levou o valor, porque o atraso é menor que qualquer navegação.
 *
 * ⚠️ **O valor igual ao padrão SAI da URL.** Sem isso, `/produtos` viraria
 * `/produtos?busca=&tipo=&inativos=false` no primeiro clique, e a URL deixaria
 * de ser legível justamente onde ela passou a servir de link.
 */
export function useEstadoNaUrl<T extends string | boolean>(
  chave: string,
  padrao: T,
  opcoes: { atraso?: number } = {},
): [T, (valor: T) => void] {
  const router = useRouter();
  const caminho = usePathname();
  const naUrl = useSearchParams();
  const atraso = opcoes.atraso ?? (typeof padrao === "string" ? 300 : 0);

  const daUrl = ((): T => {
    const bruto = naUrl.get(chave);
    if (bruto === null) return padrao;
    return (typeof padrao === "boolean" ? bruto === "1" : bruto) as T;
  })();

  const [valor, setValor] = useState<T>(daUrl);

  // ⚠️ **O voltar do navegador muda a URL sem passar pelo setter.** Sem este
  // efeito, a tela restauraria a URL certa e continuaria mostrando o estado
  // antigo — que é exatamente o defeito que este hook existe para tirar.
  // O `pendente` protege a digitação: enquanto há escrita em voo, a URL está
  // atrasada de propósito e não deve puxar o campo de volta.
  const pendente = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!pendente.current) setValor(daUrl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [daUrl]);

  const trocar = useCallback(
    (novo: T) => {
      setValor(novo);
      if (pendente.current) clearTimeout(pendente.current);
      const escrever = () => {
        pendente.current = null;
        trocarNaUrl(router, caminho, {
          [chave]: novo === padrao ? null : typeof novo === "boolean"
            ? (novo ? "1" : null)
            : String(novo),
        });
      };
      if (atraso) pendente.current = setTimeout(escrever, atraso);
      else escrever();
    },
    [router, caminho, chave, padrao, atraso],
  );

  // Uma escrita pendente ao sair da tela não pode virar navegação para uma URL
  // que já não é a de ninguém.
  useEffect(() => () => {
    if (pendente.current) clearTimeout(pendente.current);
  }, []);

  return [valor, trocar];
}
