"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { ProdutoResumo, reais } from "@/lib/cadastros";
import { Aviso, Cartao, Etiqueta, Vazio } from "@/components/ui";

/**
 * A composição do combo.
 *
 * Aparece só quando o produto é do tipo KIT, e mostra o custo saindo enquanto
 * se monta: combo existe para ter preço, e montar sem ver o custo é trabalhar
 * às cegas.
 *
 * Cada componente resolve o próprio custo pela regra dele — o prato pela ficha
 * vigente, o refrigerante pelo médio do estoque —, e a coluna "origem" diz qual
 * foi. Quando falta o custo de algum, o total continua aparecendo com o aviso
 * de que está incompleto: zerar esconderia o buraco.
 */

type Item = {
  id_componente: number;
  componente: string;
  quantidade: number;
  tipo: string;
  um_estoque: string | null;
};

type Detalhe = {
  id_componente: number;
  componente: string;
  quantidade: number;
  custo_unitario: number | null;
  custo: number | null;
  origem: string;
};

type Composicao = {
  itens: Item[];
  custo: number | null;
  origem: string | null;
  detalhe: Detalhe[];
};

const ORIGEM: Record<string, string> = {
  ficha: "ficha técnica",
  ficha_parcial: "ficha incompleta",
  ficha_sem_custo: "ficha sem custo",
  kit: "kit",
  kit_parcial: "kit incompleto",
  kit_vazio: "sem composição",
  estoque: "custo médio",
  fornecedor: "preço do fornecedor",
  sem_custo: "sem custo",
};

export default function ComposicaoKit({
  idProduto,
  podeEditar,
  podeVerCusto,
}: {
  idProduto: number;
  podeEditar: boolean;
  podeVerCusto: boolean;
}) {
  const aviso = useAviso();
  const [dados, setDados] = useState<Composicao | null>(null);
  const [produtos, setProdutos] = useState<ProdutoResumo[]>([]);
  const [linhas, setLinhas] = useState<{ id: string; qtd: string }[]>([]);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [c, p] = await Promise.all([
        api.get<Composicao>(`/produtos/${idProduto}/kit`),
        api.get<ProdutoResumo[]>("/produtos"),
      ]);
      setDados(c);
      setProdutos(p.filter((x) => x.id !== idProduto));
      setLinhas(
        c.itens.length
          ? c.itens.map((i) => ({ id: String(i.id_componente), qtd: String(i.quantidade) }))
          : [{ id: "", qtd: "1" }],
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar a composição");
    }
  }, [idProduto]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function salvar() {
    setSalvando(true);
    setErro("");
    try {
      const itens = linhas
        .filter((l) => l.id && Number(l.qtd.replace(",", ".")) > 0)
        .map((l) => ({
          id_componente: Number(l.id),
          quantidade: Number(l.qtd.replace(",", ".")),
        }));
      const r = await api.put<{ message: string }>(`/produtos/${idProduto}/kit`, { itens });
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar");
    } finally {
      setSalvando(false);
    }
  }

  if (!dados) return null;

  const incompleto = dados.origem === "kit_parcial";
  const porComponente = new Map(dados.detalhe.map((d) => [d.id_componente, d]));

  return (
    <Cartao
      titulo="O que vai no combo"
      descricao="Cada componente custa pela regra dele: o prato pela ficha vigente, a bebida pelo custo médio."
      acao={
        podeEditar && (
          <button
            type="button"
            className="btn btn-primario"
            onClick={salvar}
            disabled={salvando}
          >
            {salvando ? "Gravando…" : "Gravar composição"}
          </button>
        )
      }
    >
      {erro && (
        <div className="mb-4">
          <Aviso tipo="erro">{erro}</Aviso>
        </div>
      )}
      {incompleto && (
        <div className="mb-4">
          <Aviso tipo="info">
            Um componente ainda não tem custo conhecido. O total abaixo é o que já dá para
            somar — vai entrar assim no CMV teórico até a ficha dele ficar pronta.
          </Aviso>
        </div>
      )}

      {!podeEditar && !dados.itens.length ? (
        <Vazio>Nenhum componente definido.</Vazio>
      ) : (
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead>
              <tr>
                <th className="w-[46%]">Componente</th>
                <th className="num">Quantidade</th>
                {podeVerCusto && <th className="num">Custo un.</th>}
                {podeVerCusto && <th className="num">Custo</th>}
                <th>De onde vem</th>
              </tr>
            </thead>
            <tbody>
              {(podeEditar ? linhas : dados.itens.map((i) => ({
                id: String(i.id_componente),
                qtd: String(i.quantidade),
              }))).map((linha, i) => {
                const d = porComponente.get(Number(linha.id));
                return (
                  <tr key={i}>
                    <td>
                      {podeEditar ? (
                        <select
                          className="campo"
                          value={linha.id}
                          onChange={(e) =>
                            setLinhas(
                              linhas.map((l, j) =>
                                j === i ? { ...l, id: e.target.value } : l,
                              ),
                            )
                          }
                        >
                          <option value="">— escolher —</option>
                          {produtos.map((p) => (
                            <option key={p.id} value={p.id}>
                              {p.nome}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="font-semibold">{d?.componente ?? "—"}</span>
                      )}
                    </td>
                    <td>
                      {podeEditar ? (
                        <input
                          className="campo mono w-[110px] text-right"
                          inputMode="decimal"
                          value={linha.qtd}
                          onChange={(e) =>
                            setLinhas(
                              linhas.map((l, j) =>
                                j === i ? { ...l, qtd: e.target.value } : l,
                              ),
                            )
                          }
                        />
                      ) : (
                        <span className="num mono">{linha.qtd}</span>
                      )}
                    </td>
                    {podeVerCusto && (
                      <td className="num mono text-suave">
                        {d?.custo_unitario != null ? reais(d.custo_unitario) : "—"}
                      </td>
                    )}
                    {podeVerCusto && (
                      <td className="num mono">{d?.custo != null ? reais(d.custo) : "—"}</td>
                    )}
                    <td>
                      {d ? (
                        <Etiqueta cor={d.custo == null ? "alerta" : "neutro"}>
                          {ORIGEM[d.origem] ?? d.origem}
                        </Etiqueta>
                      ) : (
                        <span className="text-suave">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {podeEditar && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="btn btn-secundario"
            onClick={() => setLinhas([...linhas, { id: "", qtd: "1" }])}
          >
            + componente
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

      {podeVerCusto && (
        <p className="mt-4 text-[14.5px]">
          Custo do combo:{" "}
          <b className="mono">{dados.custo != null ? reais(dados.custo) : "—"}</b>
          <span className="text-suave">
            {dados.origem === "kit_vazio"
              ? " — monte a composição para o combo entrar no CMV teórico com custo."
              : incompleto
                ? " — incompleto, falta o custo de um componente."
                : " — é o que ele deveria custar a cada venda."}
          </span>
        </p>
      )}
    </Cartao>
  );
}
