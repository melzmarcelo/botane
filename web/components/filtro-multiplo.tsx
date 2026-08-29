"use client";

import { useMemo, useState } from "react";

/**
 * Um filtro de várias escolhas: caixas de seleção, com "todos" sendo NENHUMA
 * marcada.
 *
 * ⚠️ "Todos" não é uma opção na lista: é a ausência de escolha. Uma caixinha
 * "todos" que se desmarca sozinha ao marcar outra é um estado a mais para
 * manter em dia, e o primeiro a divergir.
 *
 * ⚠️ Nasceu dentro de `/inventario/novo` e saiu de lá quando a exportação
 * passou a precisar do mesmo controle. Uma segunda cópia divergiria na
 * primeira correção — e o sintoma seria uma tela filtrando de um jeito e a
 * outra de outro, sem nada explicando.
 */
export default function FiltroMultiplo<T extends string | number>({
  titulo,
  ajuda,
  opcoes,
  escolhidos,
  aoTrocar,
}: {
  titulo: string;
  ajuda: string;
  opcoes: { valor: T; nome: string }[];
  escolhidos: T[];
  aoTrocar: (v: T[]) => void;
}) {
  const [busca, setBusca] = useState("");

  const alternar = (v: T) =>
    aoTrocar(escolhidos.includes(v) ? escolhidos.filter((x) => x !== v) : [...escolhidos, v]);

  // ⚠️ A busca só aparece em lista longa. Numa base real são 99 locais e 70
  // categorias, e rolar uma lista dessas atrás de "Câmara fria" é pior que
  // digitar três letras. Em lista de quatro itens o campo seria só ruído.
  const comBusca = opcoes.length > 12;
  const visiveis = useMemo(() => {
    const t = busca.trim().toLowerCase();
    if (!t) return opcoes;
    return opcoes.filter((o) => o.nome.toLowerCase().includes(t));
  }, [opcoes, busca]);

  return (
    <div className="flex min-w-0 flex-col">
      <div className="flex items-baseline justify-between gap-2">
        <span className="rotulo">{titulo}</span>
        {escolhidos.length > 0 && (
          <button type="button" className="link-acao" onClick={() => aoTrocar([])}>
            limpar
          </button>
        )}
      </div>
      <p className="mt-0.5 text-[12.5px] leading-snug text-suave">
        {escolhidos.length ? `${escolhidos.length} escolhido(s)` : ajuda}
      </p>

      {!opcoes.length ? (
        <p className="mt-2 text-[13px] text-suave">nada cadastrado</p>
      ) : (
        <>
          {comBusca && (
            <input
              className="campo mt-2 text-[13.5px]"
              placeholder={`achar entre ${opcoes.length}…`}
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
          )}
          <ul className="mt-2 flex max-h-[180px] flex-col gap-px overflow-y-auto rounded border border-linha bg-linha">
            {!visiveis.length ? (
              <li className="bg-superficie px-3 py-2 text-[13px] text-suave">
                nada com “{busca}”
              </li>
            ) : (
              visiveis.map((o) => (
                <li key={String(o.valor)} className="bg-superficie">
                  <label className="flex cursor-pointer items-center gap-2.5 px-3 py-2 text-[14px]">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-erva"
                      checked={escolhidos.includes(o.valor)}
                      onChange={() => alternar(o.valor)}
                    />
                    {o.nome}
                  </label>
                </li>
              ))
            )}
          </ul>
        </>
      )}
    </div>
  );
}
