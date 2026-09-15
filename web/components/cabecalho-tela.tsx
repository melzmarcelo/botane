"use client";

import type { ReactNode } from "react";

import ExplicaTela from "@/components/explica-tela";

/**
 * O cabeçalho de uma tela: onde estou, o que é isto, e o que dá para fazer.
 *
 * 🔑 **Nasceu porque não existia** (14/09/2026). Cada uma das 55 telas repetia a
 * marcação do cabeçalho na mão — e o resultado foi **oito classes diferentes
 * para o mesmo `<h1>`** (`text-[26px]`, `text-[24px]`, `text-[30px]`, com e sem
 * `leading-tight`, com e sem `break-words`). Não é desleixo de quem escreveu:
 * é o que sempre acontece quando a mesma peça é copiada em vez de compartilhada.
 *
 * 🔑 **E ele recupera os ~200px antes do primeiro dado.** O título, a frase e os
 * botões vinham empilhados: numa tela que se abre vinte vezes por dia, isso é
 * rolagem repetida para chegar à primeira linha da lista. Aqui o título e as
 * ações dividem a mesma linha.
 *
 * 🔑 **A frase explicativa fica RECOLHIDA, atrás de "saber mais"** (15/09/2026,
 * pedido do dono) — e quem faz isso é `ExplicaTela`, porque as outras trinta e
 * cinco telas ainda montam o cabeçalho na mão e precisam do mesmo controle.
 *
 * ⚠️ **A largura mínima do título não é enfeite: sem ela o cabeçalho QUEBRA.**
 * A coluna da esquerda era `min-w-0 flex-1`, e o bloco de ações do painel de
 * CMV tem cinco controles (dois campos de data, um seletor de período e dois
 * botões). O flex cedeu tudo para as ações: o título ficou com **2px de
 * largura e 1.613px de altura** — uma letra por linha — em vez de a linha
 * quebrar em duas. `min-w-0` deixa um filho encolher até o nada, e foi
 * exatamente o que aconteceu. Com um piso de 15rem, as ações descem para a
 * própria linha quando não cabem ao lado, que é o que se esperava desde sempre.
 */
export default function CabecalhoTela({
  caminho,
  titulo,
  explica,
  acoes,
  children,
}: {
  /** O grupo do menu a que esta tela pertence: "Cadastros", "Estoque"… */
  caminho?: string;
  titulo: ReactNode;
  /** A frase que diz o que a tela é. Escrita como prosa, não como rótulo. */
  explica?: ReactNode;
  /** Botões da tela — ficam na mesma linha do título. */
  acoes?: ReactNode;
  /** O que mais precisar vir logo abaixo do título (uma etiqueta de estado). */
  children?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      {/* ⚠️ `min-w-[15rem]`, e nunca `min-w-0` — ver a nota do componente. */}
      <div className="min-w-[15rem] flex-1">
        {caminho && <p className="rotulo">{caminho}</p>}
        <h1 className="titulo mt-1 break-words">{titulo}</h1>

        {explica && <ExplicaTela>{explica}</ExplicaTela>}

        {children}
      </div>

      {acoes && <div className="flex min-w-0 flex-wrap items-center gap-2">{acoes}</div>}
    </header>
  );
}
