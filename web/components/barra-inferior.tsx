"use client";

import { useEffect, useState } from "react";

import { BASE_API } from "@/lib/api";

/**
 * O rodapé fixo — e o que ele existe para dizer é a VERSÃO.
 *
 * 🔑 **O número vem de `GET /saude`, não de uma constante compilada aqui.**
 * Uma constante no front diz o que foi COMPILADO; esta diz o que está NO AR — e
 * é justamente quando os dois discordam que alguém precisa do número. É a mesma
 * razão que fez `/saude` devolver a impressão do código e a última migração:
 * sem isso não se separa *"a correção não funcionou"* de *"a correção não foi
 * publicada"*.
 *
 * ⚠️ **Falhar aqui não mostra nada** — nem "erro", nem "—". O rodapé é
 * decoração informativa; um aviso de falha nele assustaria por algo que não
 * impede nada, e a pessoa não tem o que fazer com a informação.
 */
export default function BarraInferior() {
  const [versao, setVersao] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    // Rota pública e minúscula: uma vez por sessão, sem token.
    fetch(`${BASE_API}/saude`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => vivo && d?.versao && setVersao(String(d.versao)))
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, []);

  return (
    <footer
      id="barra-inferior"
      className="fixed inset-x-0 bottom-0 z-30 flex h-8 items-center justify-end border-t border-linha bg-superficie/95 px-4 backdrop-blur-sm sm:px-6"
    >
      <span className="mono text-[11.5px] text-suave">{versao ? `v${versao}` : ""}</span>
    </footer>
  );
}
