"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import AlteracaoMultipla from "./alteracao-multipla";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import {
  Categoria,
  ProdutoResumo,
  TIPOS_PRODUTO,
  nomeTipo,
  reais,
  Setor,
} from "@/lib/cadastros";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";

type Contagem = { total: number; por_tipo: Record<string, number>; rascunhos: number; inativos: number };

export default function PaginaProdutos() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeEditar = pode("cadastros.produtos");

  const [lista, setLista] = useState<ProdutoResumo[] | null>(null);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  // Os setores existem so para a alteracao em lote: a lista nao os mostra.
  const [setores, setSetores] = useState<Setor[]>([]);
  const [contagem, setContagem] = useState<Contagem | null>(null);
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [tipo, setTipo] = useEstadoNaUrl<string>("tipo", "");
  const [idCategoria, setIdCategoria] = useEstadoNaUrl<string>("categoria", "");
  // 🔑 **Ativacao em TRES estados** (09/09/2026, pedido do dono). A caixinha
  // "mostrar inativos" so escolhia entre "os ativos" e "todos" -- nao havia como
  // perguntar "o que foi desativado?", que e a pergunta de quem esta limpando o
  // cadastro. Vazio = ativos, que e o padrao de sempre.
  const [ativacao, setAtivacao] = useEstadoNaUrl<string>("ativacao", "");
  // 🔑 **A situacao**: rascunho e o que ainda nao foi revisado, e "aprovado" e
  // o vocabulario da casa para o produto ja revisado (`status = ATIVO`).
  const [situacao, setSituacao] = useEstadoNaUrl<string>("situacao", "");
  const [erro, setErro] = useState("");
  // 🔑 **Selecao para alteracao multipla** (09/09/2026, pedido do dono).
  // ⚠️ Vive FORA da lista: virar a pagina nao pode perder o que ja foi
  // marcado -- quem esta arrumando a categoria de 2.229 produtos passa por
  // varias paginas, e recomecar a cada uma tornaria o recurso inutil.
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  const [alterando, setAlterando] = useState(false);
  const pag = usePaginacao("produtos", {
    filtros: [busca, tipo, idCategoria, ativacao, situacao],
  });

  const carregar = useCallback(async () => {
    // ⚠️ Espera a preferencia de "por pagina" ser resolvida: buscar antes
    // dispara a busca com o tamanho errado, e a resposta atrasada dela
    // sobrescreve a certa -- era o "seletor em 100, lista com 20".
    if (!pag.pronto) return;
    try {
      const q = new URLSearchParams(pag.parametros);
      if (busca.trim()) q.set("busca", busca.trim());
      if (tipo) q.set("tipo", tipo);
      if (idCategoria) q.set("id_categoria", idCategoria);
      // ⚠️ "todos" NAO manda `ativo`: manda `incluir_inativos`, que e o que
      // significa "nao recorte por ativacao". Mandar `ativo` vazio seria pedir
      // um filtro sem valor, e o servidor trataria como ausente por acidente.
      if (ativacao === "sim") q.set("ativo", "true");
      else if (ativacao === "nao") q.set("ativo", "false");
      else if (ativacao === "todos") q.set("incluir_inativos", "true");
      if (situacao) q.set("status", situacao);
      const r = await api.listar<ProdutoResumo>(`/produtos?${q}`);
      setLista(r.itens);
      pag.setTotal(r.total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, busca, tipo, idCategoria, ativacao, situacao,
      pag.offset, pag.porPagina]);

  useEffect(() => {
    api.get<Categoria[]>("/categorias").then(setCategorias).catch(() => {});
    api.get<Setor[]>("/setores").then(setSetores).catch(() => {});
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
          {/* ⚠️ Este botão despejava os 3.226 produtos, sempre — não havia
              recorte nenhum. Agora a janela pergunta tipo, categoria, setor e
              situação antes de gerar. */}
          <BotaoExportar relatorio="produtos" />
          {/* 🔑 **O caminho para a colheita de EAN vive AQUI** (08/09/2026), e
              não em Integrações: o código de barras é campo do cadastro, e quem
              vai preenchê-lo em lote está olhando a lista de produtos. Mesmo
              raciocínio do relatório de consumo, que mora em Vendas. */}
          {podeEditar && (
            <Link href="/produtos/ean-das-notas" className="btn btn-secundario">
              Código de barras das notas
            </Link>
          )}
          {podeEditar && (
            <Link href="/produtos/novo" className="btn btn-primario">
              Novo produto
            </Link>
          )}
        </div>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {/* 🔑 **A barra so existe quando ha marcado**, e diz o numero antes do
          verbo. ⚠️ Ela conta a selecao INTEIRA, nao a pagina: quem marcou 40
          numa pagina e 30 noutra precisa ver 70, senao aplica achando que sao 30. */}
      {podeEditar && marcados.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded border border-linha bg-superficie2 px-4 py-3">
          <span className="text-[14px]">
            <b>{marcados.size}</b> produto(s) marcado(s)
          </span>
          <button
            type="button"
            className="btn btn-primario"
            onClick={() => setAlterando(true)}
          >
            Alterar em lote
          </button>
          <button
            type="button"
            className="btn btn-secundario"
            onClick={() => setMarcados(new Set())}
          >
            Limpar seleção
          </button>
        </div>
      )}

      {alterando && (
        <AlteracaoMultipla
          ids={[...marcados]}
          categorias={categorias}
          setores={setores}
          aoFechar={() => setAlterando(false)}
          aoAplicar={() => {
            // ⚠️ Limpa a selecao depois de aplicar: manter marcado o que ja
            // mudou convida a aplicar duas vezes, e a segunda passada com outro
            // campo escolhido mexeria em quem ninguem quis mexer de novo.
            setMarcados(new Set());
            void carregar();
          }}
        />
      )}

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
          <label className="sm:w-[150px]">
            <span className="rotulo">Ativação</span>
            <select
              className="campo mt-1.5"
              value={ativacao}
              onChange={(e) => setAtivacao(e.target.value)}
            >
              {/* ⚠️ O vazio e "Ativo", e nao "Todos": a lista de produtos abre
                  mostrando o que esta em uso, e inverter esse padrao poria 1.655
                  cadastros desativados na frente de quem so quer trabalhar. */}
              <option value="">Ativo</option>
              <option value="nao">Inativo</option>
              <option value="todos">Todos</option>
            </select>
          </label>
          <label className="sm:w-[160px]">
            <span className="rotulo">Situação</span>
            <select
              className="campo mt-1.5"
              value={situacao}
              onChange={(e) => setSituacao(e.target.value)}
            >
              <option value="">Todas</option>
              <option value="ATIVO">Aprovado</option>
              <option value="RASCUNHO">Rascunho</option>
              {/* ⚠️ ARQUIVADO nao foi pedido, mas existe e e para onde vai o
                  cadastro absorvido numa fusao: sem ele, "Todas" mostraria uma
                  situacao que o filtro nao sabe nomear. */}
              <option value="ARQUIVADO">Arquivado</option>
            </select>
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
              <Link href="/produtos/novo" className="link-acao">
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
                      <span className="link-registro">{p.nome}</span>
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
                    {podeEditar && (
                      <th className="w-8">
                        {/* Marca ou desmarca a PAGINA, nao a lista inteira: o
                            servidor so mandou estes, e prometer os 3.183 com um
                            clique seria mentira. */}
                        <input
                          type="checkbox"
                          aria-label="Marcar todos desta página"
                          checked={!!lista.length && lista.every((x) => marcados.has(x.id))}
                          onChange={(e) => {
                            const proximo = new Set(marcados);
                            for (const x of lista) {
                              if (e.target.checked) proximo.add(x.id);
                              else proximo.delete(x.id);
                            }
                            setMarcados(proximo);
                          }}
                        />
                      </th>
                    )}
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
                      {podeEditar && (
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Marcar ${p.nome}`}
                            checked={marcados.has(p.id)}
                            onChange={() => {
                              const proximo = new Set(marcados);
                              if (proximo.has(p.id)) proximo.delete(p.id);
                              else proximo.add(p.id);
                              setMarcados(proximo);
                            }}
                          />
                        </td>
                      )}
                      <td className="mono text-[13px]">{p.codigo}</td>
                      <td>
                        <Link href={`/produtos/${p.id}`} className="link-registro">
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

            {/* Sem isto, lista cheia e lista cortada são indistinguíveis — e
                quem procura um produto conclui que ele não existe. */}
            <Paginacao p={pag} rotulo="produto(s)" />
          </>
        )}
      </Cartao>
    </div>
  );
}
