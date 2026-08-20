"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { UnidadeMedida } from "@/lib/cadastros";
import { Aviso, Cartao } from "@/components/ui";

/**
 * Em que unidades este produto é comprado.
 *
 * O saldo e o custo vivem numa unidade só — a de estoque. Aqui fica a tabela de
 * conversão: a mesma água vem em caixa de 12, fardo de 6 e palete de 480, e a
 * nota chega em qualquer uma delas. Sem isto, quem comprava no palete tinha de
 * corrigir a conta à mão a cada nota.
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

export default function UnidadesDeCompra({
  idProduto,
  umEstoque,
  podeEditar,
}: {
  idProduto: number;
  umEstoque: string | null;
  podeEditar: boolean;
}) {
  const [ums, setUms] = useState<UnidadeMedida[]>([]);
  const [linhas, setLinhas] = useState<Linha[] | null>(null);
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");
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
              fator: String(Number(x.fator)),
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
    setOk("");
    try {
      const itens = (linhas ?? [])
        .filter((l) => l.um && numero(l.fator) > 0)
        .map((l) => ({
          um: l.um,
          fator: numero(l.fator),
          padrao: l.padrao,
          observacao: l.observacao || null,
        }));
      const r = await api.put<{ message: string }>(`/produtos/${idProduto}/unidades`, { itens });
      setOk(r.message);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível gravar");
    } finally {
      setSalvando(false);
    }
  }

  function mudar(i: number, campo: keyof Linha, valor: string | boolean) {
    setLinhas((atuais) =>
      (atuais ?? []).map((l, j) => {
        if (j !== i) return { ...l, padrao: campo === "padrao" && valor ? false : l.padrao };
        return { ...l, [campo]: valor };
      }),
    );
  }

  if (!linhas) return null;

  return (
    <Cartao
      titulo="Unidades de compra"
      descricao={
        umEstoque
          ? `Quantos ${umEstoque} vêm em cada unidade em que este produto é comprado.`
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
      {ok && (
        <div className="mb-4">
          <Aviso tipo="ok">{ok}</Aviso>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="tabela">
          <thead>
            <tr>
              <th className="w-[110px] min-w-[110px]">Unidade</th>
              <th className="num w-[140px] min-w-[140px]">Quantos {umEstoque ?? "?"}</th>
              <th className="w-[92px] min-w-[92px]">Padrão</th>
              <th className="min-w-[160px]">Observação</th>
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
                  <input
                    className="campo mono text-right"
                    inputMode="decimal"
                    disabled={!podeEditar}
                    value={l.fator}
                    onChange={(e) => mudar(i, "fator", e.target.value)}
                  />
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
          {linhas.length > 1 && (
            <button
              type="button"
              className="rotulo hover:text-erro"
              onClick={() => setLinhas(linhas.slice(0, -1))}
            >
              remover a última
            </button>
          )}
        </div>
      )}

      <p className="mt-4 text-[13px] leading-snug text-suave">
        A nota que chegar em qualquer uma destas unidades é convertida sozinha para{" "}
        {umEstoque ?? "a unidade de estoque"}. A <b>padrão</b> é a que a tela sugere e a que
        vale quando a nota vem numa unidade que não está aqui.
      </p>
    </Cartao>
  );
}
