"use client";

import { useState } from "react";

import type { Conjunto, Mesa, Salao } from "@/lib/salao";

import Passo from "./passo";

/**
 * Os conjuntos de mesas: de 2 a 4 que se juntam, com capacidade própria.
 *
 * 🔑 **Terceira entrega do estudo `docs/salao-estudo.md` (07/10/2026).** A junta
 * era só em PAR ("junta com", um campo da mesa): o maior grupo possível era o de
 * duas mesas, três de 4 em fila não viravam uma de 12, e a capacidade era sempre
 * a soma — juntar duas de 4 "dava 8" mesmo quando na prática dá 6.
 *
 * 🔑 **A capacidade é a que a casa INFORMA** (decisão do dono): a tela sugere a
 * soma dos máximos e mostra as duas, para ninguém baixar sem ver.
 *
 * 🔑 **Marcar na planta OU aqui.** Com "+ conjunto" ligado, clicar numa mesa da
 * planta a marca em vez de abrir; as mesmas mesas aparecem aqui como botões,
 * porque a lista e o celular não têm planta para clicar — e é aqui que entram as
 * mesas de OUTRO salão (a da porta da varanda encosta na do canto do principal).
 *
 * ⚠️ **A capacidade de um conjunto já criado tem o próprio "salvar"**: é número
 * que decide disponibilidade, e a regra da tela é que nada vale antes do botão.
 * ⚠️ **As mesas de um conjunto não se editam**: outro grupo de mesas é outro
 * conjunto — desfaça e crie.
 */
export default function ConjuntosDoSalao({
  idSalao,
  saloes,
  mesas,
  conjuntos,
  podeEditar,
  ocupado,
  marcando,
  marcadas,
  aoComecar,
  aoCancelar,
  aoMarcar,
  aoCriar,
  aoMudar,
  aoExcluir,
}: {
  idSalao: number;
  saloes: Salao[];
  /** Todas as mesas da LOJA: um conjunto pode atravessar salões. */
  mesas: Mesa[];
  conjuntos: Conjunto[];
  podeEditar: boolean;
  ocupado: boolean;
  marcando: boolean;
  marcadas: number[];
  aoComecar: () => void;
  aoCancelar: () => void;
  aoMarcar: (id: number) => void;
  aoCriar: (mesas: number[], capacidade: number) => void;
  aoMudar: (id: number, capacidade: number) => void;
  aoExcluir: (c: Conjunto) => void;
}) {
  // A capacidade que a pessoa escolheu para o conjunto novo; nula = a soma.
  const [escolhida, setEscolhida] = useState<number | null>(null);
  // Capacidades mexidas e ainda não salvas, por conjunto.
  const [mexidas, setMexidas] = useState<Record<number, number>>({});

  const nomeDoSalao = (id: number) => saloes.find((s) => s.id === id)?.nome ?? "";
  const rotuloDaMesa = (m: { nome: string; id_salao: number }) =>
    m.id_salao === idSalao ? m.nome : `${m.nome} · ${nomeDoSalao(m.id_salao)}`;

  // Só os conjuntos que tocam ESTE salão — os outros aparecem na aba deles.
  const daqui = conjuntos.filter((c) => c.mesas.some((m) => m.id_salao === idSalao));
  const soma = mesas
    .filter((m) => marcadas.includes(m.id))
    .reduce((t, m) => t + m.capacidade_max, 0);
  const capacidade = Math.min(escolhida ?? soma, 99);
  const podeCriar = marcadas.length >= 2 && marcadas.length <= 4 && capacidade >= 1;
  // As deste salão primeiro; as dos outros depois, com o nome do salão.
  const candidatas = [
    ...mesas.filter((m) => m.id_salao === idSalao),
    ...mesas.filter((m) => m.id_salao !== idSalao),
  ];

  return (
    <section className="mt-5 border-t border-linha2 pt-4" aria-label="conjuntos de mesas">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-[15px] font-medium">Conjuntos de mesas</h3>
          <p className="text-[12.5px] text-suave">
            Mesas que se juntam para um grupo maior. Só são usados quando nenhuma mesa sozinha
            serve.
          </p>
        </div>
        {podeEditar && !marcando && mesas.length >= 2 && (
          <button type="button" className="btn btn-secundario" disabled={ocupado}
                  onClick={() => { setEscolhida(null); aoComecar(); }}>
            + conjunto
          </button>
        )}
      </div>

      {marcando && (
        <div className="mt-3 rounded-xl border border-linha2 bg-superficie2 p-4"
             role="group" aria-label="novo conjunto">
          <p className="text-[13.5px]">
            Marque de <b>2 a 4 mesas</b> — aqui ou clicando na planta.
          </p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {candidatas.map((m) => {
              const marcada = marcadas.includes(m.id);
              return (
                <button key={m.id} type="button" aria-pressed={marcada}
                        aria-label={`marcar mesa ${m.nome}`}
                        disabled={ocupado || (!marcada && marcadas.length >= 4)}
                        className={`mono rounded-lg border px-2.5 py-1 text-[12.5px] disabled:opacity-40 ${
                          marcada
                            ? "border-erva bg-erva-claro font-medium text-erva"
                            : "border-linha2 bg-superficie text-suave hover:border-erva"
                        }`}
                        onClick={() => aoMarcar(m.id)}>
                  {rotuloDaMesa(m)}
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="text-[13.5px]">Acomoda</span>
            <div className="w-[130px]">
              <Passo rotulo="capacidade do conjunto novo" valor={capacidade} minimo={1} maximo={99}
                     desabilitado={ocupado || marcadas.length < 2}
                     aoMudar={(n) => setEscolhida(n)} />
            </div>
            {marcadas.length >= 2 && (
              <span className="text-[12.5px] text-suave">
                as mesas somam {soma}
                {escolhida !== null && escolhida !== soma && (
                  <>
                    {" · "}
                    <button type="button" className="link-acao" onClick={() => setEscolhida(null)}>
                      usar a soma
                    </button>
                  </>
                )}
              </span>
            )}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button type="button" className="btn btn-primario" aria-busy={ocupado}
                    disabled={ocupado || !podeCriar}
                    onClick={() => aoCriar(marcadas, capacidade)}>
              Criar conjunto
            </button>
            <button type="button" className="link-acao" onClick={aoCancelar}>
              cancelar
            </button>
            {marcadas.length === 1 && (
              <span className="text-[12.5px] text-suave">falta pelo menos mais uma mesa</span>
            )}
          </div>
        </div>
      )}

      {!daqui.length ? (
        !marcando && (
          <p className="mt-3 text-[13.5px] text-suave">
            Nenhum conjunto neste salão. Sem conjunto, o maior grupo é o da maior mesa.
          </p>
        )
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {daqui.map((c) => {
            const valor = mexidas[c.id] ?? c.capacidade;
            const mudou = valor !== c.capacidade;
            const nomes = c.mesas.map(rotuloDaMesa).join(" + ");
            return (
              <li key={c.id} aria-label={`conjunto ${c.mesas.map((m) => m.nome).join(" + ")}`}
                  className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-linha2 px-3 py-2">
                <b className="mono min-w-[120px] flex-1 text-[14px]">{nomes}</b>
                <span className="flex items-center gap-2 text-[13.5px]">
                  acomoda
                  {podeEditar ? (
                    <span className="w-[120px]">
                      <Passo rotulo={`capacidade do conjunto ${nomes}`} valor={valor} minimo={1}
                             maximo={99} desabilitado={ocupado}
                             aoMudar={(n) => setMexidas((antes) => ({ ...antes, [c.id]: n }))} />
                    </span>
                  ) : (
                    <b className="mono">{c.capacidade}</b>
                  )}
                </span>
                <span className="text-[12.5px] text-suave">as mesas somam {c.soma_maximos}</span>
                {podeEditar && (
                  <span className="flex items-center gap-3">
                    {mudou && (
                      <>
                        <button type="button" className="btn btn-primario" disabled={ocupado}
                                aria-busy={ocupado}
                                onClick={() => {
                                  aoMudar(c.id, valor);
                                  setMexidas((antes) => {
                                    const resto = { ...antes };
                                    delete resto[c.id];
                                    return resto;
                                  });
                                }}>
                          Salvar
                        </button>
                        <span className="text-[12.5px] text-alerta">não salvo</span>
                      </>
                    )}
                    <button type="button" className="link-acao link-acao-erro" disabled={ocupado}
                            onClick={() => aoExcluir(c)}>
                      desfazer conjunto
                    </button>
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
