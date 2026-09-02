"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Local, reais } from "@/lib/cadastros";
import { Aviso, Cartao, Carregando, Etiqueta, Vazio } from "@/components/ui";

/**
 * Onde este produto fica — e o que há em cada prateleira AGORA.
 *
 * 🔑 O cadastro só tinha o local PADRÃO, aquele por onde o produto ENTRA. Os
 * demais só passavam a existir na primeira transferência: o açúcar do canto do
 * Bar não existia até alguém levar o primeiro pacote para lá. Não havia como
 * preparar a casa antes de operar, nem como ver de relance em quantos cantos o
 * mesmo insumo mora.
 *
 * ⚠️ **Não há tabela nova**: a linha de `estoque_saldos` com quantidade zero já
 * quer dizer "mora aqui, vazio no momento". Uma segunda tabela para declarar a
 * mesma coisa daria duas versões da mesma verdade, e elas divergiriam no
 * primeiro movimento.
 *
 * ⚠️ Tirar um local só é possível com a prateleira VAZIA — quem recusa é o
 * servidor. Apagar a linha com saldo faria o estoque sumir da vista sem um
 * movimento no razão explicando, e o razão é a única memória do custo.
 */

type LocalDoProduto = {
  id_local: number;
  local: string;
  setor: string | null;
  principal: boolean;
  quantidade: number;
  custo_medio: number;
  valor: number;
  atualizado_em: string | null;
};

const qtd = (v: number) =>
  Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 4 });

export default function LocaisDoProduto({
  idProduto,
  podeEditar,
  podeVerCusto,
  umEstoque,
}: {
  idProduto: number;
  podeEditar: boolean;
  podeVerCusto: boolean;
  umEstoque: string | null;
}) {
  const aviso = useAviso();
  const [linhas, setLinhas] = useState<LocalDoProduto[] | null>(null);
  const [todos, setTodos] = useState<Local[]>([]);
  const [escolhido, setEscolhido] = useState("");
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [l, t] = await Promise.all([
        api.get<LocalDoProduto[]>(`/produtos/${idProduto}/locais`),
        api.get<Local[]>("/locais"),
      ]);
      setLinhas(l);
      setTodos(t);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar os locais");
    }
  }, [idProduto]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function acrescentar() {
    if (!escolhido) return;
    setSalvando(true);
    try {
      const r = await api.post<{ message: string }>(`/produtos/${idProduto}/locais`, {
        id_local: Number(escolhido),
      });
      aviso.sucesso(r.message);
      setEscolhido("");
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao acrescentar o local");
    } finally {
      setSalvando(false);
    }
  }

  async function tirar(l: LocalDoProduto) {
    setSalvando(true);
    try {
      const r = await api.delete<{ message: string }>(
        `/produtos/${idProduto}/locais/${l.id_local}`,
      );
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao tirar o local");
    } finally {
      setSalvando(false);
    }
  }

  if (erro)
    return (
      <Cartao titulo="Onde este produto fica">
        <Aviso tipo="erro">{erro}</Aviso>
      </Cartao>
    );
  if (!linhas)
    return (
      <Cartao titulo="Onde este produto fica">
        <Carregando />
      </Cartao>
    );

  // Só os que ainda não estão na lista — oferecer o que já está seria oferecer
  // uma ação que não faz nada.
  const disponiveis = todos.filter(
    (t) => t.ativo && !linhas.some((l) => l.id_local === t.id),
  );
  const totalQtd = linhas.reduce((s, l) => s + Number(l.quantidade), 0);
  const totalValor = linhas.reduce((s, l) => s + Number(l.valor), 0);

  return (
    <Cartao
      titulo="Onde este produto fica"
      descricao="As prateleiras deste produto nesta loja, com o saldo e o custo do momento."
    >
      {linhas.length === 0 ? (
        <Vazio>
          Este produto ainda não está em nenhuma prateleira desta loja. Acrescente os
          locais aqui para já poder transferir e contar por eles.
        </Vazio>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[14px]" id="locais-do-produto">
            <thead>
              <tr>
                <th className="rotulo text-left">Local</th>
                <th className="rotulo text-left">Setor</th>
                <th className="rotulo text-right">Saldo</th>
                {podeVerCusto && <th className="rotulo text-right">Custo médio</th>}
                {podeVerCusto && <th className="rotulo text-right">Valor</th>}
                <th />
              </tr>
            </thead>
            <tbody>
              {linhas.map((l) => (
                <tr key={l.id_local} className="border-t border-linha">
                  <td className="py-2">
                    {l.local} {l.principal && <Etiqueta cor="erva">principal</Etiqueta>}
                  </td>
                  <td className="py-2 text-suave">{l.setor ?? "—"}</td>
                  <td className="py-2 text-right tabular-nums">
                    {qtd(l.quantidade)}{" "}
                    <span className="text-suave">{umEstoque ?? ""}</span>
                  </td>
                  {podeVerCusto && (
                    <td className="py-2 text-right tabular-nums">
                      {reais(Number(l.custo_medio))}
                    </td>
                  )}
                  {podeVerCusto && (
                    <td className="py-2 text-right tabular-nums">
                      {reais(Number(l.valor))}
                    </td>
                  )}
                  <td className="py-2 text-right">
                    {podeEditar && (
                      <button
                        type="button"
                        className="link-acao link-acao-erro"
                        disabled={salvando}
                        aria-label={`tirar ${l.local}`}
                        onClick={() => void tirar(l)}
                      >
                        tirar
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
            {linhas.length > 1 && (
              <tfoot>
                <tr className="border-t border-linha font-semibold">
                  <td className="py-2" colSpan={2}>
                    Total nesta loja
                  </td>
                  <td className="py-2 text-right tabular-nums">
                    {qtd(totalQtd)} <span className="text-suave">{umEstoque ?? ""}</span>
                  </td>
                  {podeVerCusto && <td />}
                  {podeVerCusto && (
                    <td className="py-2 text-right tabular-nums">{reais(totalValor)}</td>
                  )}
                  <td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}

      {podeEditar && (
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="min-w-[220px] flex-1">
            <span className="rotulo">Acrescentar um local</span>
            <select
              id="local-a-acrescentar"
              className="campo"
              value={escolhido}
              onChange={(e) => setEscolhido(e.target.value)}
            >
              <option value="">— escolha a prateleira —</option>
              {disponiveis.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.nome}
                  {t.setor ? ` — ${t.setor}` : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn btn-secundario"
            disabled={!escolhido || salvando}
            onClick={() => void acrescentar()}
          >
            Acrescentar
          </button>
        </div>
      )}

      <p className="mt-3 text-[13px] text-suave">
        Acrescentar um local não movimenta nada: ele passa a existir vazio, pronto para
        receber a transferência e para entrar na contagem. Só sai da lista quem está com
        saldo zero — com mercadoria, o caminho é transferir ou lançar a saída.
      </p>
    </Cartao>
  );
}
