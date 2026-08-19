"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { Local, reais } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

type Item = {
  id: number;
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  qtd_sistema: number;
  qtd_contada: number | null;
  custo_medio: number;
  diferenca: number;
  observacao: string | null;
};

type Inventario = {
  id: number;
  id_local: number;
  local: string;
  data: string;
  status: string;
  observacao: string | null;
  itens?: Item[];
  contados: number;
  total_itens: number;
  diferenca_valor?: number | null;
};

const qtd = (n: number | string | null) =>
  n === null ? "" : Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 3 });

export default function PaginaInventario() {
  const { pode } = useSessao();
  const podeFechar = pode("estoque.ajuste");

  const [lista, setLista] = useState<Inventario[] | null>(null);
  const [aberto, setAberto] = useState<Inventario | null>(null);
  const [locais, setLocais] = useState<Local[]>([]);
  const [idLocal, setIdLocal] = useState("");
  const [contagem, setContagem] = useState<Record<number, string>>({});
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const [l, ls] = await Promise.all([
        api.get<Inventario[]>("/inventarios"),
        api.get<Local[]>("/locais"),
      ]);
      setLista(l);
      setLocais(ls);
      setIdLocal((atual) => atual || (ls.find((x) => x.principal)?.id.toString() ?? ""));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function abrirInventario() {
    setOcupado(true);
    setErro("");
    setOk("");
    try {
      const inv = await api.post<Inventario>("/inventarios", { id_local: Number(idLocal) });
      setAberto(inv);
      setContagem({});
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível abrir");
    } finally {
      setOcupado(false);
    }
  }

  async function ver(id: number) {
    setErro("");
    setOk("");
    try {
      const inv = await api.get<Inventario>(`/inventarios/${id}`);
      setAberto(inv);
      setContagem(
        Object.fromEntries(
          (inv.itens ?? [])
            .filter((i) => i.qtd_contada !== null)
            .map((i) => [i.id_produto, String(i.qtd_contada)]),
        ),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao abrir");
    }
  }

  async function salvarContagem() {
    if (!aberto) return;
    setOcupado(true);
    setErro("");
    setOk("");
    try {
      const itens = Object.entries(contagem)
        .filter(([, v]) => v.trim() !== "")
        .map(([id, v]) => ({
          id_produto: Number(id),
          qtd_contada: Number(v.replace(",", ".")),
        }));
      const inv = await api.put<Inventario>(`/inventarios/${aberto.id}/contagem`, { itens });
      setAberto(inv);
      setOk("Contagem salva. Nada foi lançado no razão ainda.");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  async function fechar() {
    if (!aberto) return;
    setOcupado(true);
    setErro("");
    setOk("");
    try {
      const r = await api.post<{ ajustes: number; diferenca_valor: number }>(
        `/inventarios/${aberto.id}/fechar`,
      );
      setOk(
        `Inventário fechado: ${r.ajustes} ajuste(s), diferença de ${reais(
          Number(r.diferenca_valor),
        )}.`,
      );
      await ver(aberto.id);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível fechar");
    } finally {
      setOcupado(false);
    }
  }

  const itens = aberto?.itens ?? [];
  const diferencaPrevista = itens.reduce((soma, i) => {
    const contado = contagem[i.id_produto];
    if (contado === undefined || contado === "") return soma;
    return soma + (Number(contado.replace(",", ".")) - Number(i.qtd_sistema)) * Number(i.custo_medio);
  }, 0);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Estoque</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Inventário</h1>
        <p className="mt-1 max-w-[66ch] text-suave">
          Contar o que existe e acertar o razão pela diferença. A contagem não mexe em nada até
          você fechar — e o acerto entra como movimento, com nome e rastro.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {ok && <Aviso tipo="ok">{ok}</Aviso>}

      {pode("estoque.inventario") && (
        <Cartao titulo="Nova contagem">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Campo rotulo="Local" className="sm:w-[260px]">
              <select
                className="campo"
                value={idLocal}
                onChange={(e) => setIdLocal(e.target.value)}
              >
                {locais.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.nome}
                  </option>
                ))}
              </select>
            </Campo>
            <button className="btn btn-primario" onClick={abrirInventario} disabled={ocupado}>
              Abrir inventário
            </button>
          </div>
        </Cartao>
      )}

      {aberto && (
        <Cartao
          titulo={`Inventário #${aberto.id} · ${aberto.local}`}
          descricao={`${aberto.contados} de ${aberto.total_itens} item(ns) contado(s)`}
          acao={
            aberto.status === "ABERTO" ? (
              <div className="flex flex-wrap gap-2">
                <button
                  className="btn btn-secundario"
                  onClick={() => void api.baixar(`/exportar/inventario/${aberto.id}.csv`)}
                >
                  Folha de contagem
                </button>
                <button
                  className="btn btn-secundario"
                  onClick={salvarContagem}
                  disabled={ocupado}
                >
                  Salvar contagem
                </button>
                {podeFechar && (
                  <button className="btn btn-primario" onClick={fechar} disabled={ocupado}>
                    Fechar e ajustar
                  </button>
                )}
              </div>
            ) : (
              <Etiqueta cor="erva">{aberto.status.toLowerCase()}</Etiqueta>
            )
          }
        >
          {!itens.length ? (
            <Vazio>Nenhum item neste local ainda.</Vazio>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Produto</th>
                      <th className="num">Sistema</th>
                      <th className="num">Contado</th>
                      <th className="num">Diferença</th>
                      <th className="num">Impacto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {itens.map((i) => {
                      const valor = contagem[i.id_produto] ?? "";
                      const dif =
                        valor === ""
                          ? null
                          : Number(valor.replace(",", ".")) - Number(i.qtd_sistema);
                      return (
                        <tr key={i.id_produto}>
                          <td>
                            <span className="font-semibold">{i.produto}</span>
                            <span className="mono ml-2 text-[12px] text-suave">{i.codigo}</span>
                          </td>
                          <td className="num text-suave">
                            {qtd(i.qtd_sistema)} {i.um_estoque ?? ""}
                          </td>
                          <td className="num">
                            {aberto.status === "ABERTO" ? (
                              <input
                                className="campo mono w-[110px] py-1 text-right"
                                type="number"
                                step="0.001"
                                min="0"
                                value={valor}
                                onChange={(e) =>
                                  setContagem({ ...contagem, [i.id_produto]: e.target.value })
                                }
                              />
                            ) : (
                              qtd(i.qtd_contada)
                            )}
                          </td>
                          <td
                            className={`num ${
                              dif === null || dif === 0
                                ? "text-suave"
                                : dif > 0
                                  ? "text-erva"
                                  : "text-erro"
                            }`}
                          >
                            {dif === null ? "—" : `${dif > 0 ? "+" : ""}${qtd(dif)}`}
                          </td>
                          <td className="num text-suave">
                            {dif === null || dif === 0
                              ? "—"
                              : reais(dif * Number(i.custo_medio))}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {aberto.status === "ABERTO" && (
                <p className="mt-3 text-[14px]">
                  Impacto previsto no estoque:{" "}
                  <b className={`mono ${diferencaPrevista < 0 ? "text-erro" : "text-erva"}`}>
                    {reais(diferencaPrevista)}
                  </b>
                  <span className="text-suave">
                    {" "}
                    — vira ajuste no razão quando você fechar.
                  </span>
                </p>
              )}
            </>
          )}
        </Cartao>
      )}

      <Cartao titulo="Contagens">
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>Nenhum inventário ainda.</Vazio>
        ) : (
          <ul className="flex flex-col gap-px bg-linha">
            {lista.map((i) => (
              <li
                key={i.id}
                className="flex flex-wrap items-center justify-between gap-3 bg-superficie py-3"
              >
                <button className="text-left" onClick={() => void ver(i.id)}>
                  <span className="font-semibold hover:text-erva">
                    #{i.id} · {i.local}
                  </span>
                  <span className="block text-[13px] text-suave">
                    {new Date(i.data).toLocaleDateString("pt-BR")} · {i.contados} de{" "}
                    {i.total_itens} contado(s)
                  </span>
                </button>
                <Etiqueta cor={i.status === "ABERTO" ? "alerta" : "erva"}>
                  {i.status.toLowerCase()}
                </Etiqueta>
              </li>
            ))}
          </ul>
        )}
      </Cartao>
    </div>
  );
}
