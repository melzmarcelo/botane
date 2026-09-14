"use client";

import { useState } from "react";
import type { ReactNode } from "react";

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
 * ⚠️ **A frase explicativa fica escondida no CELULAR, e só nele.** Ela é a voz
 * da casa e ensina na primeira semana — mas no telefone ela custa meia tela, e
 * quem está com o celular na mão no salão já sabe o que a tela faz. No
 * computador ela continua à vista, porque lá sobra espaço.
 * ⚠️ **Um nó de DOM só, não dois.** A tentação é renderizar duas versões e
 * esconder uma por breakpoint — e aí o leitor de tela lê a frase duas vezes.
 * O que muda é a classe, não o conteúdo.
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
  const [aberta, setAberta] = useState(false);

  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
      <div className="min-w-0 flex-1">
        {caminho && <p className="rotulo">{caminho}</p>}
        <h1 className="titulo mt-1 break-words">{titulo}</h1>

        {explica && (
          <>
            <p
              className={`prosa mt-1 max-w-[66ch] text-suave ${
                aberta ? "" : "hidden sm:block"
              }`}
            >
              {explica}
            </p>
            {/* ⚠️ Só aparece no celular, e some depois de aberta: um controle
                que continua oferecendo o que já está feito vira ruído. */}
            {!aberta && (
              <button
                type="button"
                className="link-acao mt-1.5 sm:hidden"
                onClick={() => setAberta(true)}
              >
                o que é esta tela?
              </button>
            )}
          </>
        )}
        {children}
      </div>

      {acoes && <div className="flex flex-wrap items-center gap-2">{acoes}</div>}
    </header>
  );
}
