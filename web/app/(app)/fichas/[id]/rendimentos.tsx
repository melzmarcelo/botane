"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Local } from "@/lib/cadastros";

/**
 * Onde esta receita é produzida — e quanto ela rende em cada lugar.
 *
 * 🔑 **Pedido do dono (13/09/2026):** *"hoje o rendimento e destinos estão em um
 * grupo separado. Podemos colocar isto juntamente com o cabeçalho, onde o destino
 * é o local padrão do produto, e assim gerados os seus rendimentos. Caso eu
 * adicione um novo local que este produto pode ser estocado, adicionar uma nova
 * linha e assim ter um novo cadastro de rendimentos igual ao padrão"*.
 *
 * 🔑 **A primeira linha É a ficha.** `rendimento_qtd`, `porcoes` e `porcao_qtd`
 * são colunas da própria `fichas_tecnicas`, e valem para qualquer prateleira que
 * não tenha linha própria — é assim desde a migração 066. Mostrá-los como "a
 * linha do local padrão" não muda dado nenhum: muda o que a tela diz que eles
 * são, que é o que o pedido pede.
 *
 * ⚠️ **A linha do padrão não se remove e não troca de prateleira.** Ela é o
 * rendimento da receita; sem ela, produzir para um destino não cadastrado ficaria
 * sem resposta. As outras saem à vontade.
 *
 * ⚠️ **Destino novo nasce IGUAL ao padrão**, como o pedido diz — a pessoa ajusta
 * só o que difere (o forno muda o rendimento, não a receita). Nascer vazio
 * obrigaria a redigitar três números para mudar um.
 *
 * ⚠️ **Em ficha NOVA só existe a linha do padrão**: destino aponta para uma ficha
 * gravada, e não há onde pendurá-lo antes de ela existir.
 */
export type LinhaDestino = {
  id_local: number | null;
  rendimento_qtd: string;
  porcoes: string;
  porcao_qtd: string;
  observacao: string;
};

export default function RendimentosPorDestino({
  idFicha,
  idLocalPadrao,
  localPadrao,
  um,
  editavel,
  padrao,
  aoMudarPadrao,
  extras,
  aoMudarExtras,
}: {
  idFicha: number | null;
  idLocalPadrao: number | null;
  localPadrao: string | null;
  um: string | null;
  editavel: boolean;
  /** A linha do local padrão — são os campos da própria ficha. */
  padrao: { rendimento_qtd: string; porcoes: string; porcao_qtd: string };
  aoMudarPadrao: (campo: "rendimento_qtd" | "porcoes" | "porcao_qtd", valor: string) => void;
  /** As demais prateleiras, de `ficha_locais`. */
  extras: LinhaDestino[];
  aoMudarExtras: (linhas: LinhaDestino[]) => void;
}) {
  const [locais, setLocais] = useState<Local[]>([]);

  useEffect(() => {
    api.get<Local[]>("/locais").then(setLocais).catch(() => setLocais([]));
  }, []);

  const usados = new Set(extras.map((l) => Number(l.id_local)).filter(Boolean));
  const unidade = um || "un.";

  return (
    <div className="mt-4 overflow-x-auto">
      <table className="tabela">
        <thead>
          <tr>
            <th className="min-w-[190px]">Onde é produzido</th>
            <th className="num w-[130px] min-w-[130px]">Rende ({unidade})</th>
            <th className="num w-[110px] min-w-[110px]">Porções</th>
            <th className="num w-[130px] min-w-[130px]">Cada porção</th>
            <th className="min-w-[150px]">Observação</th>
            {editavel && <th className="w-[80px]"></th>}
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              <span className="font-medium">{localPadrao ?? "Qualquer prateleira"}</span>
              <span className="ml-2 text-[12px] text-suave">padrão</span>
            </td>
            <td>
              <input
                className="campo mono text-right"
                type="number"
                step="0.001"
                min="0.001"
                disabled={!editavel}
                aria-label="Rendimento da receita"
                value={padrao.rendimento_qtd}
                onChange={(e) => aoMudarPadrao("rendimento_qtd", e.target.value)}
              />
            </td>
            <td>
              <input
                className="campo mono text-right"
                type="number"
                step="0.01"
                min="0.01"
                disabled={!editavel}
                aria-label="Porções da receita"
                value={padrao.porcoes}
                onChange={(e) => aoMudarPadrao("porcoes", e.target.value)}
              />
            </td>
            <td>
              <input
                className="campo mono text-right"
                type="number"
                step="0.0001"
                min="0.0001"
                disabled={!editavel}
                aria-label="Tamanho da porção"
                value={padrao.porcao_qtd}
                onChange={(e) => aoMudarPadrao("porcao_qtd", e.target.value)}
              />
            </td>
            <td className="text-[13px] text-suave">
              vale em toda prateleira sem linha própria
            </td>
            {editavel && <td></td>}
          </tr>

          {extras.map((l, i) => (
            <tr key={i}>
              <td>
                <select
                  className="campo"
                  disabled={!editavel}
                  aria-label={`prateleira do destino ${i + 1}`}
                  value={l.id_local ?? ""}
                  onChange={(e) =>
                    aoMudarExtras(
                      extras.map((x, j) =>
                        j === i ? { ...x, id_local: Number(e.target.value) || null } : x,
                      ),
                    )
                  }
                >
                  <option value="">—</option>
                  {locais
                    .filter(
                      (x) =>
                        x.ativo &&
                        x.id !== idLocalPadrao &&
                        (!usados.has(x.id) || x.id === Number(l.id_local)),
                    )
                    .map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.nome}
                      </option>
                    ))}
                </select>
              </td>
              {(["rendimento_qtd", "porcoes", "porcao_qtd"] as const).map((campo, n) => (
                <td key={campo}>
                  <input
                    className="campo mono text-right"
                    inputMode="decimal"
                    disabled={!editavel}
                    aria-label={
                      ["rendimento", "porções", "tamanho da porção"][n] +
                      ` do destino ${i + 1}`
                    }
                    value={l[campo]}
                    onChange={(e) =>
                      aoMudarExtras(
                        extras.map((x, j) =>
                          j === i ? { ...x, [campo]: e.target.value } : x,
                        ),
                      )
                    }
                  />
                </td>
              ))}
              <td>
                <input
                  className="campo"
                  disabled={!editavel}
                  placeholder="assada, porcionada…"
                  value={l.observacao}
                  onChange={(e) =>
                    aoMudarExtras(
                      extras.map((x, j) =>
                        j === i ? { ...x, observacao: e.target.value } : x,
                      ),
                    )
                  }
                />
              </td>
              {editavel && (
                <td className="text-right">
                  <button
                    type="button"
                    className="link-acao link-acao-erro"
                    aria-label={`remover destino ${i + 1}`}
                    onClick={() => aoMudarExtras(extras.filter((_x, j) => j !== i))}
                  >
                    remover
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {editavel && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn btn-secundario"
            disabled={!idFicha}
            onClick={() =>
              aoMudarExtras([
                ...extras,
                {
                  id_local: null,
                  // Nasce IGUAL ao padrão: ajusta-se o que difere.
                  rendimento_qtd: padrao.rendimento_qtd,
                  porcoes: padrao.porcoes,
                  porcao_qtd: padrao.porcao_qtd,
                  observacao: "",
                },
              ])
            }
          >
            + prateleira
          </button>
          <span className="text-[12.5px] text-suave">
            {idFicha
              ? "a nova nasce igual ao padrão — ajuste só o que muda"
              : "depois de criar a ficha dá para acrescentar outras prateleiras"}
          </span>
        </div>
      )}

      <p className="mt-3 text-[13px] leading-snug text-suave">
        ⚠️ O rendimento <b>divide o consumo</b>: produzir 10 para uma prateleira que rende 8
        gasta uma receita e um quarto. Ao programar a produção você escolhe a prateleira, e a
        tela diz qual rendimento está valendo.
      </p>
    </div>
  );
}
