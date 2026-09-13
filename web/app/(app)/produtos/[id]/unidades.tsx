"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { UnidadeMedida } from "@/lib/cadastros";
import { Aviso, Cartao } from "@/components/ui";

/**
 * Em que unidades este produto é comprado — e quanto pesa uma unidade dele.
 *
 * O saldo e o custo vivem numa unidade só — a de estoque. Aqui fica a tabela de
 * conversão: a mesma água vem em caixa de 12, fardo de 6 e palete de 480, e a
 * nota chega em qualquer uma delas. Sem isto, quem comprava no palete tinha de
 * corrigir a conta à mão a cada nota.
 *
 * 🔑 **E a PERGUNTA muda de lado quando a unidade é de peso** (12/09/2026, caso
 * da cliente: *"ela compra a dúzia de ovos, entra no estoque em unidade, e em
 * algumas receitas usa 50 G de ovo"*). A tabela sempre guardou "quantas
 * unidades de estoque cabem em uma desta" — 1 CX = 12 UN. Para o grama isso
 * vira 0,02, e ninguém sabe quantos ovos cabem num grama: a cozinha sabe que
 * **o ovo pesa 50 g**. Então a linha de peso pergunta ao contrário, "1 UN =
 * [50] G", e a tela grava o inverso.
 *
 * ⚠️ **O engano que isso fecha é de ordem de grandeza.** Quem lesse "Quantos
 * UN" e digitasse 50 passaria a consumir cinquenta ovos por grama de receita,
 * calado — o mesmo fator invertido que já custou o custo de um produto aqui
 * (09/09). Agora cada linha diz a relação inteira, com as duas siglas à vista.
 *
 * ⚠️ **Nada mudou no banco nem no motor de conversão**: `produto_unidades.fator`
 * continua com o mesmo significado, e é `custos.fator_de_embalagem` que o lê.
 * O que mudou é de que lado a pergunta é feita.
 */

type Unidade = {
  id?: number;
  um: string;
  fator: number | string;
  padrao: boolean;
  observacao: string | null;
};

type Linha = { um: string; fator: string; padrao: boolean; observacao: string };

const numero = (t: string) => Number((t || "0").replace(",", ".")) || 0;
const texto = (n: number) => String(n).replace(".", ",");

/** A pergunta vira do avesso quando a unidade cadastrada é de PESO ou VOLUME e
 *  o estoque é contado em unidades.
 *
 * ⚠️ **É a única combinação em que o número natural é o inverso do gravado.**
 * Estoque em UN com linha em G: o gravado é 0,02 e o natural é 50. Estoque em
 * KG com linha em UN já pergunta certo ("1 UN = 0,05 KG"), e embalagem contra
 * embalagem (CX, FD, DZ) também — 1 CX = 12 UN é como se fala. */
const invertida = (um: string, umEstoque: string | null, ums: UnidadeMedida[]) => {
  const a = ums.find((u) => u.sigla === um)?.grandeza;
  const b = ums.find((u) => u.sigla === (umEstoque ?? ""))?.grandeza;
  return !!a && !!b && a !== b && b === "UNIDADE";
};

/** O fator gravado, lido na direção natural: 0,02 volta como "50".
 *
 * ⚠️ **O laço para na primeira casa que reproduz o gravado**, que é a mesma
 * regra do relatório exportado. `fator` é `numeric(18,6)`, então 1/55 vira
 * 0,018182 — e 1/0,018182 dá 55,0005. Mostrar isso seria devolver à pessoa um
 * número que ela não digitou; arredondar cego quebraria o caso de 350 ML, que
 * só fecha com casa decimal. */
const naturalDoFator = (fator: number) => {
  if (!Number.isFinite(fator) || fator <= 0) return "";
  const bruto = 1 / fator;
  for (const casas of [0, 1, 2, 3, 4]) {
    const candidato = Number(bruto.toFixed(casas));
    if (candidato > 0
        && Math.abs(Number((1 / candidato).toFixed(6)) - fator) < 1e-9) {
      return texto(candidato);
    }
  }
  return texto(Number(bruto.toFixed(4)));
};

export default function UnidadesDeCompra({
  idProduto,
  umEstoque,
  podeEditar,
}: {
  idProduto: number;
  umEstoque: string | null;
  podeEditar: boolean;
}) {
  const aviso = useAviso();
  const [ums, setUms] = useState<UnidadeMedida[]>([]);
  const [linhas, setLinhas] = useState<Linha[] | null>(null);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [u, m] = await Promise.all([
        api.get<Unidade[]>(`/produtos/${idProduto}/unidades`),
        api.get<UnidadeMedida[]>("/unidades-medida"),
      ]);
      setUms(m);
      setLinhas(
        u.length
          ? u.map((x) => ({
              um: x.um,
              // ⚠️ O estado guarda o que a pessoa VÊ, não o que o banco guarda:
              // na linha de peso os dois são inversos, e converter na hora de
              // gravar (uma vez) é mais simples que manter os dois em sincronia
              // a cada tecla.
              fator: invertida(x.um, umEstoque, m)
                ? naturalDoFator(Number(x.fator))
                : String(Number(x.fator)),
              padrao: x.padrao,
              observacao: x.observacao ?? "",
            }))
          : [{ um: umEstoque ?? "", fator: "1", padrao: true, observacao: "" }],
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [idProduto, umEstoque]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function salvar() {
    setSalvando(true);
    setErro("");
    try {
      const itens = (linhas ?? [])
        .filter((l) => l.um && numero(l.fator) > 0)
        .map((l) => {
          const digitado = numero(l.fator);
          // ⚠️ Arredonda aqui, na escala da coluna (`numeric(18,6)`), para o que
          // se manda ser o que fica gravado: sem isto a tela mostraria 50 e o
          // banco guardaria outro número, e a próxima leitura divergiria.
          const fator = invertida(l.um, umEstoque, ums)
            ? Number((1 / digitado).toFixed(6))
            : digitado;
          return {
            um: l.um,
            fator,
            padrao: l.padrao,
            observacao: l.observacao || null,
          };
        });
      // ⚠️ **Peso grande demais some na escala da coluna.** "1 UN = 10.000.000 G"
      // daria fator 0,0000001, que arredondado em seis casas é zero — e o
      // servidor recusaria com uma mensagem sobre `fator`, que não é o número
      // que a pessoa digitou. Melhor dizer aqui, na linguagem da tela.
      const pequena = itens.find((x) => x.fator <= 0);
      if (pequena) {
        setErro(`A equivalência de ${pequena.um} é fina demais para o sistema `
                + `guardar. Use uma unidade maior nesta linha.`);
        setSalvando(false);
        return;
      }
      const r = await api.put<{ message: string }>(`/produtos/${idProduto}/unidades`, { itens });
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar");
    } finally {
      setSalvando(false);
    }
  }

  function mudar(i: number, campo: keyof Linha, valor: string | boolean) {
    setLinhas((atuais) =>
      (atuais ?? []).map((l, j) => {
        if (j !== i) return { ...l, padrao: campo === "padrao" && valor ? false : l.padrao };
        const proxima = { ...l, [campo]: valor };
        // ⚠️ **Trocar a unidade pode virar o lado da pergunta** — de "1 CX = 12
        // UN" para "1 UN = ? G". O número que estava ali significava outra coisa
        // e não se converte: 12 UN por caixa não diz nada sobre o peso de um
        // ovo. Então o campo esvazia, e a frase da linha já mostra o que pedir.
        if (campo === "um"
            && invertida(String(valor), umEstoque, ums) !== invertida(l.um, umEstoque, ums)) {
          proxima.fator = "";
        }
        return proxima;
      }),
    );
  }

  if (!linhas) return null;

  return (
    <Cartao
      titulo="Unidades de compra"
      descricao={
        umEstoque
          ? `Quantos ${umEstoque} vêm em cada unidade em que este produto é `
            + `comprado — e, se ele for contado por unidade, quanto uma pesa.`
          : "Defina a unidade de estoque antes de montar a conversão."
      }
      acao={
        podeEditar && (
          <button type="button" className="btn btn-primario" onClick={salvar} disabled={salvando}>
            {salvando ? "Gravando…" : "Gravar unidades"}
          </button>
        )
      }
    >
      {erro && (
        <div className="mb-4">
          <Aviso tipo="erro">{erro}</Aviso>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="tabela">
          <thead>
            <tr>
              <th className="w-[110px] min-w-[110px]">Unidade</th>
              {/* 🔑 **A coluna deixou de ser um número solto.** "Quantos UN" com
                  0,02 embaixo não diz que 0,02 é o inverso de 50 — a frase
                  inteira diz, e é ela que impede o fator invertido. */}
              <th className="min-w-[210px]">Equivalência</th>
              <th className="w-[92px] min-w-[92px]">Padrão</th>
              <th className="min-w-[160px]">Observação</th>
              {podeEditar && <th className="w-[80px] min-w-[80px]"></th>}
            </tr>
          </thead>
          <tbody>
            {linhas.map((l, i) => (
              <tr key={i}>
                <td>
                  <select
                    className="campo"
                    disabled={!podeEditar}
                    value={l.um}
                    onChange={(e) => mudar(i, "um", e.target.value)}
                  >
                    <option value="">—</option>
                    {ums.map((u) => (
                      <option key={u.sigla} value={u.sigla}>
                        {u.sigla}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  {(() => {
                    const deLado = invertida(l.um, umEstoque, ums);
                    // De um lado a unidade da linha, do outro a de estoque — e
                    // na linha de peso os dois trocam de lugar.
                    const esquerda = deLado ? (umEstoque ?? "?") : (l.um || "?");
                    const direita = deLado ? (l.um || "?") : (umEstoque ?? "?");
                    return (
                      <span className="flex items-center gap-1.5 whitespace-nowrap">
                        <span className="mono text-suave">1 {esquerda} =</span>
                        <input
                          className="campo mono w-[92px] text-right"
                          inputMode="decimal"
                          disabled={!podeEditar}
                          value={l.fator}
                          aria-label={`quantos ${direita} em 1 ${esquerda}`}
                          placeholder={deLado ? "peso" : "quantos"}
                          onChange={(e) => mudar(i, "fator", e.target.value)}
                        />
                        <span className="mono text-suave">{direita}</span>
                      </span>
                    );
                  })()}
                </td>
                <td>
                  <input
                    type="radio"
                    name={`padrao-${idProduto}`}
                    disabled={!podeEditar}
                    checked={l.padrao}
                    onChange={() => mudar(i, "padrao", true)}
                    aria-label="unidade padrão de compra"
                  />
                </td>
                <td>
                  <input
                    className="campo"
                    disabled={!podeEditar}
                    value={l.observacao}
                    placeholder="palete, fardo do distribuidor…"
                    onChange={(e) => mudar(i, "observacao", e.target.value)}
                  />
                </td>
                {podeEditar && (
                  <td className="text-right">
                    {/* 🔑 **O remover é da LINHA, não "a última".** Antes só dava
                        para tirar a de baixo, então quem quisesse remover a
                        caixa de 12 tinha de apagar o fardo e o palete pelo
                        caminho — e recadastrá-los depois.
                        ⚠️ A última linha não se remove: `produto_unidades` sem
                        nenhuma é o produto sem conversão de compra, e aí a tela
                        não teria onde a pessoa voltar a cadastrar. */}
                    {linhas.length > 1 && (
                      <button
                        type="button"
                        className="link-acao link-acao-erro"
                        aria-label={`remover ${l.um || "esta unidade"}`}
                        onClick={() => setLinhas(linhas.filter((_x, j) => j !== i))}
                      >
                        remover
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {podeEditar && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn btn-secundario"
            onClick={() =>
              setLinhas([...linhas, { um: "", fator: "", padrao: false, observacao: "" }])
            }
          >
            + unidade
          </button>
          {/* 🔑 O remover saiu daqui e foi para a LINHA. "Remover a última"
              obrigava a apagar as de baixo para chegar na do meio — e a pessoa
              que quer tirar a caixa de 12 não quer tocar no fardo. */}
        </div>
      )}

      <p className="mt-4 text-[13px] leading-snug text-suave">
        A nota que chegar em qualquer uma destas unidades é convertida sozinha para{" "}
        {umEstoque ?? "a unidade de estoque"}. A <b>padrão</b> é a que a tela sugere e a que
        vale quando a nota vem numa unidade que não está aqui.
        {umEstoque && (
          <>
            {" "}
            Uma linha de <b>peso ou volume</b> serve à ficha técnica: com
            &ldquo;1 {umEstoque} = 50 G&rdquo; cadastrado, a receita pode pedir 50 G e o
            sistema baixa 1 {umEstoque} do estoque.
          </>
        )}
      </p>
    </Cartao>
  );
}
