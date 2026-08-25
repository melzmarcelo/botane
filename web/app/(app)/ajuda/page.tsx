"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Aviso } from "@/components/ui";

/**
 * O manual de referência, dentro do sistema.
 *
 * ⚠️ **Uma fonte só.** O manual é o arquivo `public/ajuda.html` — autocontido,
 * com a mesma paleta e as mesmas fontes das telas. Esta página o exibe; não o
 * reescreve em JSX. Duas cópias do mesmo texto divergem no primeiro parágrafo
 * novo, e aí o sistema passa a explicar duas coisas diferentes sobre si mesmo.
 * É também o arquivo que se publica para quem não tem acesso ao sistema.
 *
 * O quadro cresce até a altura do conteúdo, porque documento com barra de
 * rolagem própria dentro de uma página que já rola é briga de rolagem: a roda
 * do mouse para no meio e quem lê não sabe qual das duas está movendo.
 */
export default function PaginaAjuda() {
  const quadro = useRef<HTMLIFrameElement>(null);
  const [erro, setErro] = useState(false);

  const ajustarAltura = useCallback(() => {
    const el = quadro.current;
    // Mesma origem: dá para medir o conteúdo. Se um dia não der, o `try` deixa
    // o quadro na altura mínima em vez de derrubar a tela.
    try {
      const doc = el?.contentDocument;
      if (doc?.body) el!.style.height = `${doc.documentElement.scrollHeight + 24}px`;
    } catch {
      setErro(true);
    }
  }, []);

  useEffect(() => {
    window.addEventListener("resize", ajustarAltura);
    // As fontes chegam depois do `load` e mudam a altura do texto.
    const t = setInterval(ajustarAltura, 700);
    const parar = setTimeout(() => clearInterval(t), 5000);
    return () => {
      window.removeEventListener("resize", ajustarAltura);
      clearInterval(t);
      clearTimeout(parar);
    };
  }, [ajustarAltura]);

  return (
    <div className="flex flex-col gap-4">
      {/* O manual traz a própria capa — repetir o título aqui daria duas
          aberturas na mesma tela. Sobra a barra com o caminho para fora. */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <p className="rotulo">Ajuda · manual de referência</p>
        <a className="btn btn-secundario" href="/ajuda.html" target="_blank" rel="noreferrer">
          Abrir em outra aba
        </a>
      </header>

      {erro && (
        <Aviso tipo="erro">
          Não deu para exibir o manual aqui.{" "}
          <a href="/ajuda.html" target="_blank" rel="noreferrer" className="underline">
            Abra em outra aba
          </a>
          .
        </Aviso>
      )}

      <iframe
        ref={quadro}
        src="/ajuda.html"
        title="Manual do Botané"
        onLoad={ajustarAltura}
        className="w-full rounded-xl border border-linha bg-superficie"
        style={{ height: 640 }}
      />
    </div>
  );
}
