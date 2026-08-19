"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import {
  Categoria,
  ProdutoResumo,
  TIPOS_PRODUTO,
  nomeTipo,
  reais,
} from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

type Contagem = { total: number; por_tipo: Record<string, number>; rascunhos: number; inativos: number };

export default function PaginaProdutos() {
  const { pode } = useSessao();
  const podeEditar = pode("cadastros.produtos");

  const [lista, setLista] = useState<ProdutoResumo[] | null>(null);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [contagem, setContagem] = useState<Contagem | null>(null);
  const [busca, setBusca] = useState("");
  const [tipo, setTipo] = useState("");
  const [idCategoria, setIdCategoria] = useState("");
  const [inativos, setInativos] = useState(false);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    const q = new URLSearchParams();
    if (busca.trim()) q.set("busca", busca.trim());
    if (tipo) q.set("tipo", tipo);
    if (idCategoria) q.set("id_categoria", idCategoria);
    if (inativos) q.set("incluir_inativos", "true");
    try {
      setLista(await api.get<ProdutoResumo[]>(`/produtos?${q}`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [busca, tipo, idCategoria, inativos]);

  useEffect(() => {
    api.get<Categoria[]>("/categorias").then(setCategorias).catch(() => {});
    api.get<Contagem>("/produtos/contagem").then(setContagem).catch(() => {});
  }, []);

  // Espera a digitação parar: sem isso a lista pisca a cada tecla.
  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Cadastros</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Produtos</h1>
          <p className="mt-1 max-w-[62ch] text-suave">
            Tudo o que entra e sai da casa: insumo, revenda, o que a cozinha produz e a
            embalagem. É daqui que a ficha técnica e o estoque vão puxar.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn btn-secundario"
            onClick={async () => {
              try {
                await api.baixar("/exportar/produtos.csv");
              } catch (e) {
                setErro(e instanceof Error ? e.message : "Não foi possível baixar");
              }
            }}
          >
            Baixar planilha
          </button>
          {podeEditar && (
            <Link href="/produtos/novo" className="btn btn-primario">
              Novo produto
            </Link>
          )}
        </div>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {contagem && contagem.rascunhos > 0 && (
        <Aviso tipo="info">
          {contagem.rascunhos} produto(s) em rascunho — eles não entram no estoque enquanto não
          tiverem unidade de estoque e fator de conversão.
        </Aviso>
      )}

      <Cartao>
        <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="min-w-0 flex-1 sm:min-w-[220px]">
            <span className="rotulo">Buscar</span>
            <input
              className="campo mt-1.5"
              placeholder="nome, código ou código de barras"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
            />
          </label>
          <label className="sm:w-[170px]">
            <span className="rotulo">Tipo</span>
            <select className="campo mt-1.5" value={tipo} onChange={(e) => setTipo(e.target.value)}>
              <option value="">Todos</option>
              {TIPOS_PRODUTO.map((t) => (
                <option key={t.valor} value={t.valor}>
                  {t.nome}
                </option>
              ))}
            </select>
          </label>
          <label className="sm:w-[220px]">
            <span className="rotulo">Categoria</span>
            <select
              className="campo mt-1.5"
              value={idCategoria}
              onChange={(e) => setIdCategoria(e.target.value)}
            >
              <option value="">Todas</option>
              {categorias.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.caminho}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 pb-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-erva"
              checked={inativos}
              onChange={(e) => setInativos(e.target.checked)}
            />
            <span className="text-[14px]">mostrar inativos</span>
          </label>
        </div>
      </Cartao>

      <Cartao
        titulo={lista ? `${lista.length} produto(s)` : "Produtos"}
        descricao={contagem ? `${contagem.total} ativos no total` : undefined}
      >
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>
            Nenhum produto encontrado.{" "}
            {podeEditar && (
              <Link href="/produtos/novo" className="text-erva underline">
                cadastrar o primeiro
              </Link>
            )}
          </Vazio>
        ) : (
          <>
            {/* celular: cartões */}
            <ul className="flex flex-col gap-px bg-linha md:hidden">
              {lista.map((p) => (
                <li key={p.id} className="bg-superficie py-3">
                  <Link href={`/produtos/${p.id}`} className="block">
                    <div className="flex items-start justify-between gap-3">
                      <span className="font-semibold">{p.nome}</span>
                      <span className="mono shrink-0 text-[12px] text-suave">{p.codigo}</span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      <Etiqueta>{nomeTipo(p.tipo)}</Etiqueta>
                      {p.um_estoque && <Etiqueta>{p.um_estoque}</Etiqueta>}
                      {p.status === "RASCUNHO" && <Etiqueta cor="alerta">rascunho</Etiqueta>}
                      {!p.ativo && <Etiqueta cor="alerta">inativo</Etiqueta>}
                      {p.categoria && (
                        <span className="text-[13px] text-suave">{p.categoria}</span>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>

            <div className="hidden overflow-x-auto md:block">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Código</th>
                    <th>Produto</th>
                    <th>Tipo</th>
                    <th>Categoria</th>
                    <th>Setor</th>
                    <th>Un.</th>
                    <th className="num">Preço</th>
                  </tr>
                </thead>
                <tbody>
                  {lista.map((p) => (
                    <tr key={p.id} className={p.ativo ? "" : "opacity-55"}>
                      <td className="mono text-[13px]">{p.codigo}</td>
                      <td>
                        <Link href={`/produtos/${p.id}`} className="font-semibold hover:text-erva">
                          {p.nome}
                        </Link>
                        <span className="ml-2 inline-flex gap-1">
                          {p.status === "RASCUNHO" && <Etiqueta cor="alerta">rascunho</Etiqueta>}
                          {p.producao_propria && <Etiqueta cor="erva">ficha</Etiqueta>}
                          {!p.controla_estoque && <Etiqueta>sem estoque</Etiqueta>}
                        </span>
                      </td>
                      <td>{nomeTipo(p.tipo)}</td>
                      <td className="text-suave">{p.categoria ?? "—"}</td>
                      <td className="text-suave">{p.setor ?? "—"}</td>
                      <td className="mono">{p.um_estoque ?? "—"}</td>
                      <td className="num">{p.preco_venda ? reais(Number(p.preco_venda)) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Cartao>
    </div>
  );
}
