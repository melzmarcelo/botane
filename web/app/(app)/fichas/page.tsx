"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { useSessao } from "@/lib/sessao";
import { ProdutoResumo, reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

type Ficha = {
  id: number;
  id_produto: number;
  produto: string;
  codigo: string;
  versao: number;
  status: string;
  rendimento_qtd: number;
  rendimento_um: string | null;
  porcoes: number;
  itens: number;
  custo_total: number | null;
  custo_por_porcao: number | null;
  custo_completo: boolean | null;
};

const CORES: Record<string, "erva" | "alerta" | "neutro"> = {
  HOMOLOGADA: "erva",
  RASCUNHO: "alerta",
  ARQUIVADA: "neutro",
};

export default function PaginaFichas() {
  const { pode } = useSessao();
  const podeEditar = pode("fichas.editar");
  const veCusto = pode("fichas.custos");

  const [lista, setLista] = useState<Ficha[] | null>(null);
  const [semFicha, setSemFicha] = useState<ProdutoResumo[]>([]);
  const [busca, setBusca] = useState("");
  const [status, setStatus] = useState("");
  const [erro, setErro] = useState("");
  const pag = usePaginacao("fichas", { filtros: [busca, status] });

  const carregar = useCallback(async () => {
    const q = new URLSearchParams(pag.parametros);
    if (busca.trim()) q.set("busca", busca.trim());
    if (status) q.set("status", status);
    try {
      const fichas = await api.listar<Ficha>(`/fichas?${q}`);
      setLista(fichas.itens);
      pag.setTotal(fichas.total);
      // Produzido sem ficha nenhuma: é a fila de trabalho da cozinha. ⚠️ Quem
      // responde é o SERVIDOR (`sem_ficha=true`): comparar com as fichas desta
      // PÁGINA acusaria como sem ficha todo produto cuja ficha está na próxima.
      setSemFicha(
        await api.get<ProdutoResumo[]>("/produtos?tipo=PRODUZIDO&sem_ficha=true&limite=100"),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca, status, pag.offset, pag.porPagina]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Cadastros</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Fichas técnicas
          </h1>
          <p className="mt-1 max-w-[64ch] text-suave">
            A receita de cada prato e o que ela custa por porção. Um preparo pode entrar em
            outro — o molho tem ficha própria e o custo dele desce sozinho para os pratos que
            o usam.
          </p>
        </div>
        {podeEditar && (
          <Link href="/fichas/nova" className="btn btn-primario">
            Nova ficha
          </Link>
        )}
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {!!semFicha.length && podeEditar && (
        <Aviso tipo="info">
          {semFicha.length} produto(s) de produção própria ainda sem ficha:{" "}
          {semFicha.slice(0, 4).map((p) => p.nome).join(", ")}
          {semFicha.length > 4 ? "…" : ""}
        </Aviso>
      )}

      <Cartao>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="min-w-0 flex-1">
            <span className="rotulo">Buscar</span>
            <input
              className="campo mt-1.5"
              placeholder="nome do produto"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
          </label>
          <label className="sm:w-[200px]">
            <span className="rotulo">Situação</span>
            <select
              className="campo mt-1.5"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="">Todas</option>
              <option value="HOMOLOGADA">Homologadas</option>
              <option value="RASCUNHO">Rascunhos</option>
              <option value="ARQUIVADA">Arquivadas</option>
            </select>
          </label>
        </div>
      </Cartao>

      <Cartao titulo={lista ? `${pag.total} ficha(s)` : "Fichas"}>
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>
            Nenhuma ficha ainda.{" "}
            {podeEditar && (
              <Link href="/fichas/nova" className="link-acao">
                criar a primeira
              </Link>
            )}
          </Vazio>
        ) : (
          <>
            <ul className="flex flex-col gap-px bg-linha md:hidden">
              {lista.map((f) => (
                <li key={f.id} className="bg-superficie py-3">
                  <Link href={`/fichas/${f.id}`} className="block">
                    <div className="flex items-start justify-between gap-3">
                      <span className="link-registro">{f.produto}</span>
                      <Etiqueta cor={CORES[f.status]}>{f.status.toLowerCase()}</Etiqueta>
                    </div>
                    <p className="mt-1 text-[13px] text-suave">
                      v{f.versao} · {f.itens} item(ns) · rende {Number(f.rendimento_qtd)}{" "}
                      {f.rendimento_um ?? ""} em {Number(f.porcoes)} porção(ões)
                    </p>
                    {veCusto && (
                      <p className="mono mt-1 text-[13.5px]">
                        {f.custo_por_porcao !== null ? reais(Number(f.custo_por_porcao)) : "—"}
                        <span className="text-suave"> / porção</span>
                        {f.custo_completo === false && (
                          <span className="ml-2 text-alerta">custo incompleto</span>
                        )}
                      </p>
                    )}
                  </Link>
                </li>
              ))}
            </ul>

            <div className="hidden overflow-x-auto md:block">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Produto</th>
                    <th>Versão</th>
                    <th>Situação</th>
                    <th className="num">Itens</th>
                    <th>Rendimento</th>
                    {veCusto && <th className="num">Custo total</th>}
                    {veCusto && <th className="num">Por porção</th>}
                  </tr>
                </thead>
                <tbody>
                  {lista.map((f) => (
                    <tr key={f.id} className={f.status === "ARQUIVADA" ? "opacity-55" : ""}>
                      <td>
                        <Link href={`/fichas/${f.id}`} className="link-registro">
                          {f.produto}
                        </Link>
                        <span className="mono ml-2 text-[12px] text-suave">{f.codigo}</span>
                      </td>
                      <td className="mono">v{f.versao}</td>
                      <td>
                        <Etiqueta cor={CORES[f.status]}>{f.status.toLowerCase()}</Etiqueta>
                      </td>
                      <td className="num">{f.itens}</td>
                      <td className="text-suave">
                        {Number(f.rendimento_qtd)} {f.rendimento_um ?? ""} ·{" "}
                        {Number(f.porcoes)} porção(ões)
                      </td>
                      {veCusto && (
                        <td className="num">
                          {f.custo_total !== null ? reais(Number(f.custo_total)) : "—"}
                          {f.custo_completo === false && (
                            <span className="ml-1 text-alerta" title="há item sem preço">
                              *
                            </span>
                          )}
                        </td>
                      )}
                      {veCusto && (
                        <td className="num font-semibold">
                          {f.custo_por_porcao !== null ? reais(Number(f.custo_por_porcao)) : "—"}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {veCusto && lista.some((f) => f.custo_completo === false) && (
              <p className="mt-3 text-[13px] text-suave">
                * há item sem preço conhecido — o custo mostrado é parcial. O preço vem da
                última compra do fornecedor; na etapa de estoque passa a vir do custo médio.
              </p>
            )}
          </>
        )}
        <Paginacao p={pag} rotulo="ficha(s)" />
      </Cartao>
    </div>
  );
}
