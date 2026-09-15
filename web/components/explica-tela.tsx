"use client";

import { useState } from "react";
import type { ReactNode } from "react";

/**
 * A frase que diz o que a tela é — recolhida atrás de um **"saber mais"**.
 *
 * 🔑 **Pedido do dono (15/09/2026):** *"podemos tirar o texto de explicação da
 * tela e colocar, como foi proposto, um saber mais"* — e depois, *"colocar este
 * saber mais em todas as telas que tenham o texto"*. O estudo de layout já o
 * propunha: **ela ensina na primeira semana e estorva na terceira.** Em trinta e
 * cinco telas, duas linhas de prosa antes do primeiro dado são duas linhas que
 * quem trabalha na casa pula todo dia.
 *
 * ⚠️ **A frase NÃO foi apagada, e essa é a diferença.** Ela é a voz da casa e é
 * o que separa este sistema de um ERP mudo: quem chega na primeira semana abre
 * o "saber mais" e aprende o que a tela faz. O que mudou foi quem paga por ela.
 *
 * ⚠️ **O mesmo controle fecha de volta.** Botão que só sabe abrir deixa a tela
 * no estado de que se estava saindo — e a pessoa que abriu por curiosidade fica
 * com a frase para sempre.
 *
 * ⚠️ **Um nó de DOM só, escondido pelo `hidden`** — e não montado e desmontado.
 * O `aria-controls` aponta para ele, e um alvo que some é um alvo que o leitor
 * de tela perde justamente quando importa.
 *
 * ⚠️ **Isto é para EXPLICAÇÃO, não para dado.** A linha que diz o e-mail do
 * usuário, o período da conta ou a origem da venda também é um `<p>` cinza
 * abaixo do título — e esconder um dado atrás de "saber mais" é esconder o
 * assunto da tela. Cinco telas ficaram de fora por isso, de propósito.
 */
export default function ExplicaTela({ children }: { children: ReactNode }) {
  const [aberta, setAberta] = useState(false);

  return (
    <>
      <button
        type="button"
        className="link-acao mt-2"
        aria-expanded={aberta}
        aria-controls="explica-tela"
        onClick={() => setAberta((e) => !e)}
      >
        {aberta ? "ocultar" : "saber mais"}
      </button>
      {/* ⚠️ O `id` é fixo porque só há UMA explicação por tela — é a mesma
          premissa do `<h1>`. Duas numa página só seriam duas telas numa página
          só, que é o defeito a corrigir, não um id a gerar. */}
      <p id="explica-tela" hidden={!aberta} className="prosa mt-2 max-w-[66ch] text-suave">
        {children}
      </p>
    </>
  );
}
