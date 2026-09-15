"use client";

import { useState } from "react";

import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Modal } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import { custo as moedaCusto, qtd } from "@/lib/numeros";

/**
 * Reprocessar o estoque de UM produto — o razão relido em ordem de data.
 *
 * 🔑 **Pedido do dono (15/09/2026):** *"em saldos e movimentos, criar uma opção
 * de reprocessar, caso tenha alterações, disponibilizar a opção de reprocessar
 * o estoque, filtrando por produto"*.
 *
 * 🔑 **O caso que ele conserta é o lançamento RETROATIVO.** A nota do dia 9
 * entra hoje, depois de a venda do dia 12 já ter saído: a venda saiu com custo
 * estimado (não havia saldo) e o saldo ficou negativo. O custo médio é
 * calculado no instante do lançamento, com o que a prateleira sabia ali — e
 * nada disso se acerta sozinho.
 *
 * ⚠️ **A prévia vem antes do botão, sempre.** Isto reescreve número que alguém
 * já leu: o custo de uma saída, o saldo de uma data. É a mesma disciplina da
 * fusão de cadastros.
 *
 * ⚠️ **Só aparece com um PRODUTO escolhido.** Reprocessar a loja inteira seria
 * uma operação de minutos sobre milhares de movimentos, e sem ninguém poder
 * conferir o que mudou — o filtro não é limitação, é o recorte que torna a
 * conferência possível.
 */
export default function ReprocessarEstoque({
  produto,
  aoTerminar,
}: {
  /** O que o filtro da tela fixou: id e rótulo. O NOME vem da resposta do
      servidor — é ele quem sabe como o produto se chama agora. */
  produto: { id: number; rotulo: string };
  aoTerminar: () => void;
}) {
  const aviso = useAviso();
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [ocupado, setOcupado] = useState(false);

  async function conferir() {
    setOcupado(true);
    try {
      setPrevia(await api.post<Previa>("/estoque/reprocessar", { id_produto: produto.id }));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível conferir");
    } finally {
      setOcupado(false);
    }
  }

  async function aplicar() {
    setOcupado(true);
    try {
      const r = await api.post<Previa>("/estoque/reprocessar", {
        id_produto: produto.id,
        aplicar: true,
      });
      setPrevia(null);
      aviso.sucesso(r.message);
      aoTerminar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reprocessar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <button
        type="button"
        id="reprocessar-estoque"
        className="btn btn-secundario"
        aria-busy={ocupado}
        disabled={ocupado}
        onClick={conferir}
      >
        Reprocessar
      </button>

      {previa && (
        <Modal
          titulo={`Reprocessar o estoque de ${previa.produto}`}
          aoFechar={() => setPrevia(null)}
          largura="820px"
          rodape={
            <div className="flex flex-wrap items-center gap-2">
              {previa.mudam > 0 && (
                <button
                  className="btn btn-primario"
                  type="button"
                  aria-busy={ocupado}
                  disabled={ocupado}
                  onClick={aplicar}
                >
                  Reprocessar {previa.mudam} movimento(s)
                </button>
              )}
              <button className="btn btn-secundario" type="button" onClick={() => setPrevia(null)}>
                {previa.mudam > 0 ? "Cancelar" : "Fechar"}
              </button>
            </div>
          }
        >
          <p className="prosa text-suave">
            O razão é lido em ordem de <b>data</b> e o que é calculado se refaz: o saldo de cada
            movimento, o custo médio e o custo das <b>saídas</b> — que nunca foi um fato, é a
            média do momento. Nada é criado nem apagado, e o custo das <b>entradas</b> não se
            toca: ele é o que a casa pagou.
          </p>

          {previa.mudam === 0 ? (
            <Aviso tipo="ok">
              {previa.produto} já está em ordem — os {previa.movimentos} movimento(s) batem com
              o que a prateleira diz. Nada a reprocessar.
            </Aviso>
          ) : (
            <>
              <div className="mt-4">
                <p className="rotulo">Como fica a prateleira</p>
                <div className="mt-1.5 overflow-x-auto">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th className="num">Saldo agora</th>
                        <th className="num">Saldo reprocessado</th>
                        <th className="num">Custo médio agora</th>
                        <th className="num">Custo médio reprocessado</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previa.saldos.map((s) => (
                        <tr key={s.id_local}>
                          <td className="num mono">{qtd(Number(s.quantidade_de ?? 0))}</td>
                          <td className="num mono font-semibold">
                            {qtd(Number(s.quantidade_para))}
                          </td>
                          <td className="num mono">{moedaCusto(Number(s.custo_medio_de ?? 0))}</td>
                          <td className="num mono font-semibold">
                            {moedaCusto(Number(s.custo_medio_para))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-5">
                <p className="rotulo">O que muda em cada movimento</p>
                <div className="mt-1.5 overflow-x-auto">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Quando</th>
                        <th>O quê</th>
                        <th className="num">Custo un.</th>
                        <th className="num">Saldo depois</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previa.linhas.map((l) => (
                        <tr key={l.id}>
                          <td className="mono text-[13px]">{l.data.slice(0, 10)}</td>
                          <td className="text-[13.5px]">{l.tipo.toLowerCase().replace(/_/g, " ")}</td>
                          <td className="num mono">
                            {Number(l.custo_de) !== Number(l.custo_para) ? (
                              <>
                                <span className="text-suave line-through">
                                  {reais(Number(l.custo_de))}
                                </span>{" "}
                                <b>{reais(Number(l.custo_para))}</b>
                              </>
                            ) : (
                              <span className="text-suave">{reais(Number(l.custo_para))}</span>
                            )}
                          </td>
                          <td className="num mono">
                            {Number(l.saldo_de) !== Number(l.saldo_para) ? (
                              <>
                                <span className="text-suave line-through">
                                  {qtd(Number(l.saldo_de))}
                                </span>{" "}
                                <b>{qtd(Number(l.saldo_para))}</b>
                              </>
                            ) : (
                              <span className="text-suave">{qtd(Number(l.saldo_para))}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {previa.mudam > previa.linhas.length && (
                  <p className="mt-2 text-[12.5px] text-suave">
                    …e mais {previa.mudam - previa.linhas.length} movimento(s). A lista mostra os
                    primeiros para conferência.
                  </p>
                )}
              </div>
            </>
          )}
        </Modal>
      )}
    </>
  );
}

type LinhaPrevia = {
  id: number;
  data: string;
  tipo: string;
  id_local: number;
  saldo_de: string | number;
  saldo_para: string | number;
  medio_de: string | number;
  medio_para: string | number;
  custo_de: string | number;
  custo_para: string | number;
};

type Previa = {
  produto: string;
  movimentos: number;
  mudam: number;
  linhas: LinhaPrevia[];
  saldos: {
    id_local: number;
    quantidade_de: string | number | null;
    quantidade_para: string | number;
    custo_medio_de: string | number | null;
    custo_medio_para: string | number;
  }[];
  aplicado: boolean;
  message: string;
};
