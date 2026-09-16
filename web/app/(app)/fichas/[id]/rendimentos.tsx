"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Local } from "@/lib/cadastros";

/**
 * Os MODOS de rendimento desta receita — como ela é produzida, e quanto rende.
 *
 * 🔑 **Pedido do dono (16/09/2026):** *"no cadastro de ficha posso cadastrar o
 * padrão — o Cookies Flat rende 8,535 KG em 65 porções, a receita toda. E podemos
 * criar mais modos de rendimento para diferentes setores, com um nome, e este
 * será o modo selecionado ao agendar ou produzir. Modo padrão é produzir a
 * receita toda para estoque; podemos ter um Modo Consumo, com o setor Bar e 30
 * porções; ou outro onde as porções são menores."*
 *
 * 🔑 **O que o modo muda não é ESCALA, é a PORÇÃO.** Produzir 30 em vez de 65
 * sempre funcionou: a quantidade é livre e o consumo é proporcional. O que não
 * existia era a mesma massa render *outra coisa* — os mesmos 8,535 KG em 130
 * unidades menores, que é outro custo unitário e outra contagem de estoque.
 *
 * 🔑 **A primeira linha É a ficha, e ela é o Modo padrão.** `rendimento_qtd`,
 * `porcoes` e `porcao_qtd` são colunas da própria `fichas_tecnicas` e respondem
 * quando nenhum modo casa — é assim desde a migração 066. Ela não se remove e não
 * ganha nome: sem ela, produzir sem escolher modo ficaria sem resposta.
 *
 * ⚠️ **Prateleira e setor são só PRÉ-SELEÇÃO.** Eles fazem o modo vir escolhido
 * quando o destino é aquele; quem decide de verdade é quem produz, na tela. Por
 * isso os dois são opcionais e um modo pode não ter nenhum dos dois.
 *
 * ⚠️ **Modo novo nasce IGUAL ao padrão** — a pessoa ajusta só o que difere (o
 * forno muda o rendimento, não a receita). Nascer vazio obrigaria a redigitar
 * três números para mudar um.
 *
 * ⚠️ **Em ficha NOVA só existe a linha do padrão**: modo aponta para uma ficha
 * gravada, e não há onde pendurá-lo antes de ela existir.
 */
export type LinhaModo = {
  nome: string;
  id_local: number | null;
  id_setor: number | null;
  rendimento_qtd: string;
  porcoes: string;
  porcao_qtd: string;
  quantidade_sugerida: string;
  observacao: string;
};

type Setor = { id: number; nome: string; ativo?: boolean };

/**
 * ⚠️ **Prateleira e setor num seletor só.** São a mesma pergunta — "onde este
 * modo vale?" — e duas colunas para ela deixariam a tabela mais larga que a
 * tela, com a metade das células sempre vazia. O prefixo separa os dois mundos
 * porque os ids se repetem entre tabelas.
 */
const valorDoOnde = (l: LinhaModo) =>
  l.id_local ? `l:${l.id_local}` : l.id_setor ? `s:${l.id_setor}` : "";

const lerOnde = (v: string) => ({
  id_local: v.startsWith("l:") ? Number(v.slice(2)) : null,
  id_setor: v.startsWith("s:") ? Number(v.slice(2)) : null,
});

export default function ModosDeRendimento({
  idFicha,
  localPadrao,
  um,
  editavel,
  padrao,
  aoMudarPadrao,
  extras,
  aoMudarExtras,
}: {
  idFicha: number | null;
  localPadrao: string | null;
  um: string | null;
  editavel: boolean;
  /** A linha do Modo padrão — são os campos da própria ficha. */
  padrao: { rendimento_qtd: string; porcoes: string; porcao_qtd: string };
  aoMudarPadrao: (campo: "rendimento_qtd" | "porcoes" | "porcao_qtd", valor: string) => void;
  /** Os demais modos, de `ficha_modos`. */
  extras: LinhaModo[];
  aoMudarExtras: (linhas: LinhaModo[]) => void;
}) {
  const [locais, setLocais] = useState<Local[]>([]);
  const [setores, setSetores] = useState<Setor[]>([]);

  useEffect(() => {
    api.get<Local[]>("/locais").then(setLocais).catch(() => setLocais([]));
    api.get<Setor[]>("/setores").then(setSetores).catch(() => setSetores([]));
  }, []);

  const unidade = um || "un.";
  const mudar = (i: number, campo: keyof LinhaModo, valor: unknown) =>
    aoMudarExtras(extras.map((x, j) => (j === i ? { ...x, [campo]: valor } : x)));

  return (
    <div className="mt-4 overflow-x-auto">
      <table className="tabela">
        <thead>
          <tr>
            <th className="min-w-[160px]">Modo</th>
            <th className="min-w-[160px]">Onde vale</th>
            <th className="num w-[120px] min-w-[120px]">Rende ({unidade})</th>
            <th className="num w-[100px] min-w-[100px]">Porções</th>
            <th className="num w-[120px] min-w-[120px]">Cada porção</th>
            <th className="num w-[120px] min-w-[120px]">Costuma produzir</th>
            <th className="min-w-[140px]">Observação</th>
            {editavel && <th className="w-[80px]"></th>}
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              <span className="font-medium">Padrão</span>
              <span className="ml-2 text-[12px] text-suave">a receita toda</span>
            </td>
            <td className="text-[13px] text-suave">
              {localPadrao ? `${localPadrao} e qualquer outra` : "qualquer prateleira"}
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
            <td className="text-center text-[13px] text-suave">—</td>
            <td className="text-[13px] text-suave">vale quando nenhum modo casa</td>
            {editavel && <td></td>}
          </tr>

          {extras.map((l, i) => (
            <tr key={i}>
              <td>
                <input
                  className="campo"
                  disabled={!editavel}
                  placeholder="Consumo — Bar"
                  aria-label={`nome do modo ${i + 1}`}
                  value={l.nome}
                  onChange={(e) => mudar(i, "nome", e.target.value)}
                />
              </td>
              <td>
                <select
                  className="campo"
                  disabled={!editavel}
                  aria-label={`onde vale o modo ${i + 1}`}
                  value={valorDoOnde(l)}
                  onChange={(e) => {
                    const { id_local, id_setor } = lerOnde(e.target.value);
                    aoMudarExtras(
                      extras.map((x, j) => (j === i ? { ...x, id_local, id_setor } : x)),
                    );
                  }}
                >
                  <option value="">— escolher na hora —</option>
                  <optgroup label="Prateleira">
                    {locais
                      .filter((x) => x.ativo)
                      .map((x) => (
                        <option key={`l${x.id}`} value={`l:${x.id}`}>
                          {x.nome}
                        </option>
                      ))}
                  </optgroup>
                  <optgroup label="Setor">
                    {setores
                      .filter((x) => x.ativo !== false)
                      .map((x) => (
                        <option key={`s${x.id}`} value={`s:${x.id}`}>
                          {x.nome}
                        </option>
                      ))}
                  </optgroup>
                </select>
              </td>
              {(
                ["rendimento_qtd", "porcoes", "porcao_qtd", "quantidade_sugerida"] as const
              ).map((campo, n) => (
                <td key={campo}>
                  <input
                    className="campo mono text-right"
                    inputMode="decimal"
                    disabled={!editavel}
                    aria-label={
                      ["rendimento", "porções", "tamanho da porção", "quantidade sugerida"][n] +
                      ` do modo ${i + 1}`
                    }
                    value={l[campo]}
                    onChange={(e) => mudar(i, campo, e.target.value)}
                  />
                </td>
              ))}
              <td>
                <input
                  className="campo"
                  disabled={!editavel}
                  placeholder="assada, porcionada…"
                  value={l.observacao}
                  onChange={(e) => mudar(i, "observacao", e.target.value)}
                />
              </td>
              {editavel && (
                <td className="text-right">
                  <button
                    type="button"
                    className="link-acao link-acao-erro"
                    aria-label={`remover modo ${i + 1}`}
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
                  nome: "",
                  id_local: null,
                  id_setor: null,
                  // Nasce IGUAL ao padrão: ajusta-se o que difere.
                  rendimento_qtd: padrao.rendimento_qtd,
                  porcoes: padrao.porcoes,
                  porcao_qtd: padrao.porcao_qtd,
                  quantidade_sugerida: "",
                  observacao: "",
                },
              ])
            }
          >
            + modo
          </button>
          <span className="text-[12.5px] text-suave">
            {idFicha
              ? "o novo nasce igual ao padrão — ajuste só o que muda"
              : "depois de criar a ficha dá para acrescentar outros modos"}
          </span>
        </div>
      )}

      <p className="mt-3 text-[13px] leading-snug text-suave">
        ⚠️ O rendimento <b>divide o consumo</b>: produzir 10 num modo que rende 8 gasta uma
        receita e um quarto. Ao agendar ou produzir você escolhe o modo — ele vem escolhido
        quando a prateleira ou o setor de destino é o dele —, e a tela diz qual está valendo.
      </p>
    </div>
  );
}
