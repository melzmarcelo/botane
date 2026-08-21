"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Local, ProdutoResumo, reais } from "@/lib/cadastros";
import { FiltroCadastro } from "@/components/busca-cadastro";
import { fonteProdutos } from "@/lib/busca-cadastro";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import LotesEmEstoque from "./lotes";

type Saldo = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  id_local: number;
  local: string;
  quantidade: number;
  custo_medio: number;
  valor: number;
  abaixo_do_minimo: boolean;
};

type Movimento = {
  id: number;
  data_movimento: string;
  tipo: string;
  rotulo: string;
  produto: string;
  codigo: string;
  local: string;
  quantidade: number;
  custo_unitario: number;
  custo_total: number;
  saldo_apos: number;
  custo_medio_apos: number;
  custo_provisorio: boolean;
  documento: string | null;
  motivo: string | null;
  observacao: string | null;
  usuario: string | null;
  estornado: boolean;
  id_estorno_de: number | null;
};


const qtd = (n: number | string) =>
  Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 3 });

type TipoMovimento = { tipo: string; rotulo: string };

const PRODUTOS = fonteProdutos();

export default function PaginaEstoque() {
  const aviso = useAviso();
  const { pode } = useSessao();
  // Quem pode lançar qualquer um dos quatro ajustes vê o atalho para a tela.
  const podeAjustar = ["estoque.entradas", "estoque.saidas", "estoque.perdas",
                       "estoque.transferencias"].some(pode);
  const [aba, setAba] = useState<"saldos" | "movimentos">("saldos");
  const [saldos, setSaldos] = useState<Saldo[] | null>(null);
  const [movimentos, setMovimentos] = useState<Movimento[] | null>(null);
  const [locais, setLocais] = useState<Local[]>([]);
  const [busca, setBusca] = useState("");
  // Texto filtra solto ("café" traz os cinco); a lupa FIXA um produto, para
  // quem quer o saldo — ou o razão — de um só.
  const [produtoSaldo, setProdutoSaldo] = useState<{ id: number; rotulo: string } | null>(null);
  const [idLocal, setIdLocal] = useState("");
  const [comSaldo, setComSaldo] = useState(true);
  const [erro, setErro] = useState("");

  // Filtros do razão. Separados dos saldos de propósito: são perguntas
  // diferentes — "quanto tenho hoje" e "o que aconteceu com o café em agosto".
  const [movBusca, setMovBusca] = useState("");
  const [produtoMov, setProdutoMov] = useState<{ id: number; rotulo: string } | null>(null);
  const [movTipo, setMovTipo] = useState("");
  const [movLocal, setMovLocal] = useState("");
  const [movInicio, setMovInicio] = useState("");
  const [movFim, setMovFim] = useState("");
  const [movTotal, setMovTotal] = useState(0);
  const [movPagina, setMovPagina] = useState(1);
  const [tipos, setTipos] = useState<TipoMovimento[]>([]);

  const [baixando, setBaixando] = useState(false);

  async function baixar(caminho: string) {
    setBaixando(true);
    setErro("");
    try {
      await api.baixar(caminho);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível baixar");
    } finally {
      setBaixando(false);
    }
  }

  const carregar = useCallback(async () => {
    try {
      const q = new URLSearchParams();
      if (produtoSaldo) q.set("id_produto", String(produtoSaldo.id));
      else if (busca.trim()) q.set("busca", busca.trim());
      if (idLocal) q.set("id_local", idLocal);
      if (comSaldo) q.set("apenas_com_saldo", "true");
      setSaldos(await api.get<Saldo[]>(`/estoque/saldos?${q}`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [busca, produtoSaldo, idLocal, comSaldo]);

  const POR_PAGINA = 100;
  const temFiltroMov = !!(movBusca || produtoMov || movTipo || movLocal || movInicio || movFim);

  const carregarMovimentos = useCallback(async () => {
    try {
      const q = new URLSearchParams({ limite: String(POR_PAGINA * movPagina) });
      if (produtoMov) q.set("id_produto", String(produtoMov.id));
      else if (movBusca.trim()) q.set("busca", movBusca.trim());
      if (movTipo) q.set("tipo", movTipo);
      if (movLocal) q.set("id_local", movLocal);
      if (movInicio) q.set("inicio", movInicio);
      if (movFim) q.set("fim", movFim);
      const { itens, total } = await api.listar<Movimento>(`/estoque/movimentos?${q}`);
      setMovimentos(itens);
      setMovTotal(total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [movBusca, produtoMov, movTipo, movLocal, movInicio, movFim, movPagina]);

  // Trocar o filtro volta para a primeira página: manter a 3ª página de um
  // filtro no outro mostraria uma lista vazia sem explicação.
  useEffect(() => {
    setMovPagina(1);
  }, [movBusca, produtoMov, movTipo, movLocal, movInicio, movFim]);

  useEffect(() => {
    const t = setTimeout(() => void carregarMovimentos(), movBusca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregarMovimentos, movBusca]);

  useEffect(() => {
    api.get<Local[]>("/locais").then(setLocais).catch(() => {});
    api.get<TipoMovimento[]>("/estoque/tipos-movimento").then(setTipos).catch(() => {});
  }, []);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  async function estornar(m: Movimento) {
    setErro("");
    try {
      await api.post(`/estoque/movimentos/${m.id}/estornar`, { motivo: "estorno pela tela" });
      aviso.sucesso("Movimento estornado — o original continua no razão, com a contrapartida.");
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível estornar");
    }
  }

  const valorTotal = saldos?.reduce((s, x) => s + Number(x.valor), 0) ?? 0;

  /** A planilha do razão sai com os MESMOS filtros da tela — filtrar aqui e
      baixar outra coisa faria quem conferisse achar que um dos dois mente. */
  function csvDoRazao() {
    const q = new URLSearchParams();
    if (produtoMov) q.set("id_produto", String(produtoMov.id));
    else if (movBusca.trim()) q.set("busca", movBusca.trim());
    if (movTipo) q.set("tipo", movTipo);
    if (movLocal) q.set("id_local", movLocal);
    if (movInicio) q.set("inicio", movInicio);
    if (movFim) q.set("fim", movFim);
    const s = q.toString();
    return `/exportar/movimentos.csv${s ? `?${s}` : ""}`;
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Estoque</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Saldos e movimentos
          </h1>
          <p className="mt-1 max-w-[64ch] text-suave">
            Cada entrada recalcula o custo médio do insumo; cada saída baixa por esse custo.
            Nada aqui é apagado — correção entra como estorno.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* Lançar tem tela própria: aqui se CONSULTA. Os quatro botões de
              entrada, saída, perda e transferência viraram Estoque ▸ Ajustes. */}
          {podeAjustar && (
            <Link href="/ajustes" className="btn btn-primario">
              Lançar ajuste
            </Link>
          )}
          <button
            className="btn btn-secundario"
            onClick={() => void baixar(aba === "saldos" ? "/exportar/saldos.csv" : csvDoRazao())}
            disabled={baixando}
          >
            {baixando ? "Baixando…" : "Baixar planilha"}
          </button>
        </div>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <nav className="flex gap-1 border-b border-linha">
        {(["saldos", "movimentos"] as const).map((a) => (
          <button
            key={a}
            onClick={() => setAba(a)}
            className={`-mb-px border-b-2 px-3 py-2 text-[14.5px] ${
              aba === a
                ? "border-erva font-semibold text-erva"
                : "border-transparent text-suave hover:text-tinta"
            }`}
          >
            {a === "saldos" ? "Saldos" : "Movimentos"}
          </button>
        ))}
      </nav>

      {aba === "saldos" && (
        <>
          <Cartao>
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
              <div className="min-w-0 flex-1 sm:min-w-[240px]">
                <span className="rotulo">Produto</span>
                <div className="mt-1.5">
                  <FiltroCadastro
                    fonte={PRODUTOS}
                    texto={busca}
                    aoMudarTexto={setBusca}
                    fixado={produtoSaldo}
                    aoFixar={setProdutoSaldo}
                    placeholder="produto ou código"
                  />
                </div>
              </div>
              <label className="sm:w-[200px]">
                <span className="rotulo">Local</span>
                <select
                  className="campo mt-1.5"
                  value={idLocal}
                  onChange={(e) => setIdLocal(e.target.value)}
                >
                  <option value="">Todos</option>
                  {locais.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.nome}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex items-center gap-2 pb-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-erva"
                  checked={comSaldo}
                  onChange={(e) => setComSaldo(e.target.checked)}
                />
                <span className="text-[14px]">só com saldo</span>
              </label>
            </div>
          </Cartao>

          <Cartao
            titulo={saldos ? `${saldos.length} linha(s)` : "Saldos"}
            descricao={`Valor em estoque: ${reais(valorTotal)}`}
          >
            {!saldos ? (
              <Carregando />
            ) : !saldos.length ? (
              <Vazio>Nada em estoque ainda. Comece por uma entrada.</Vazio>
            ) : (
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Produto</th>
                      <th>Local</th>
                      <th className="num">Saldo</th>
                      <th className="num">Custo médio</th>
                      <th className="num">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {saldos.map((s) => (
                      <tr key={`${s.id_produto}-${s.id_local}`}>
                        <td>
                          <span className="font-semibold">{s.produto}</span>
                          <span className="mono ml-2 text-[12px] text-suave">{s.codigo}</span>
                          {s.abaixo_do_minimo && (
                            <span className="ml-2">
                              <Etiqueta cor="alerta">abaixo do mínimo</Etiqueta>
                            </span>
                          )}
                        </td>
                        <td className="text-suave">{s.local}</td>
                        <td className={`num ${Number(s.quantidade) < 0 ? "text-erro" : ""}`}>
                          {qtd(s.quantidade)} {s.um_estoque ?? ""}
                        </td>
                        <td className="num">{reais(Number(s.custo_medio))}</td>
                        <td className="num font-semibold">{reais(Number(s.valor))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Cartao>
        </>
      )}

      {aba === "movimentos" && (
        <>
        <LotesEmEstoque />

        <Cartao>
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
            <div className="min-w-0 flex-1 sm:min-w-[230px]">
              <span className="rotulo">Produto</span>
              <div className="mt-1.5">
                <FiltroCadastro
                  fonte={PRODUTOS}
                  texto={movBusca}
                  aoMudarTexto={setMovBusca}
                  fixado={produtoMov}
                  aoFixar={setProdutoMov}
                  placeholder="nome ou código"
                />
              </div>
            </div>
            <label className="sm:w-[168px]">
              <span className="rotulo">De</span>
              <input
                className="campo mt-1.5"
                type="date"
                value={movInicio}
                onChange={(e) => setMovInicio(e.target.value)}
              />
            </label>
            <label className="sm:w-[168px]">
              <span className="rotulo">Até</span>
              <input
                className="campo mt-1.5"
                type="date"
                value={movFim}
                onChange={(e) => setMovFim(e.target.value)}
              />
            </label>
            <label className="sm:w-[200px]">
              <span className="rotulo">Movimento</span>
              <select
                className="campo mt-1.5"
                value={movTipo}
                onChange={(e) => setMovTipo(e.target.value)}
              >
                <option value="">todos</option>
                {tipos.map((t) => (
                  <option key={t.tipo} value={t.tipo}>
                    {t.rotulo}
                  </option>
                ))}
              </select>
            </label>
            <label className="sm:w-[170px]">
              <span className="rotulo">Local</span>
              <select
                className="campo mt-1.5"
                value={movLocal}
                onChange={(e) => setMovLocal(e.target.value)}
              >
                <option value="">todos</option>
                {locais.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.nome}
                  </option>
                ))}
              </select>
            </label>
            {temFiltroMov && (
              <button
                type="button"
                className="btn btn-secundario"
                onClick={() => {
                  setMovBusca("");
                  setProdutoMov(null);
                  setMovTipo("");
                  setMovLocal("");
                  setMovInicio("");
                  setMovFim("");
                }}
              >
                Limpar
              </button>
            )}
          </div>
        </Cartao>

        <Cartao
          titulo="Razão de estoque"
          descricao={
            movimentos
              ? `${movimentos.length} de ${movTotal} lançamento(s)${
                  temFiltroMov ? " no filtro" : ""
                }.`
              : undefined
          }
        >
          {!movimentos ? (
            <Carregando />
          ) : !movimentos.length ? (
            <Vazio>
              {temFiltroMov
                ? "Nenhum movimento com esses filtros."
                : "Nenhum movimento ainda."}
            </Vazio>
          ) : (
            <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Quando</th>
                    <th>O quê</th>
                    <th>Produto</th>
                    <th className="num">Qtd</th>
                    <th className="num">Custo un.</th>
                    <th className="num">Total</th>
                    <th className="num">Saldo</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {movimentos.map((m) => (
                    <tr key={m.id} className={m.estornado ? "opacity-55" : ""}>
                      <td className="mono whitespace-nowrap text-[13px]">
                        {new Date(m.data_movimento).toLocaleString("pt-BR", {
                          day: "2-digit",
                          month: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td>
                        <span className="whitespace-nowrap">{m.rotulo}</span>
                        {m.motivo && (
                          <span className="block text-[12.5px] text-suave">{m.motivo}</span>
                        )}
                        {m.estornado && (
                          <span className="block">
                            <Etiqueta cor="alerta">estornado</Etiqueta>
                          </span>
                        )}
                        {m.custo_provisorio && (
                          <span className="block">
                            <Etiqueta cor="alerta">custo provisório</Etiqueta>
                          </span>
                        )}
                      </td>
                      <td>
                        {m.produto}
                        <span className="block text-[12.5px] text-suave">{m.local}</span>
                      </td>
                      <td
                        className={`num ${Number(m.quantidade) < 0 ? "text-erro" : "text-erva"}`}
                      >
                        {Number(m.quantidade) > 0 ? "+" : ""}
                        {qtd(m.quantidade)}
                      </td>
                      <td className="num">{reais(Number(m.custo_unitario))}</td>
                      <td className="num">{reais(Number(m.custo_total))}</td>
                      <td className="num text-suave">{qtd(m.saldo_apos)}</td>
                      <td className="text-right">
                        {pode("estoque.ajuste") && !m.estornado && !m.id_estorno_de && (
                          <button
                            className="rotulo whitespace-nowrap hover:text-erro"
                            onClick={() => void estornar(m)}
                          >
                            estornar
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Página de 100. O razão cresce todo dia e trazer tudo de uma vez
              trava a tela justamente na casa que mais movimenta. */}
          {!!movimentos && movimentos.length < movTotal && (
            <div className="mt-4 flex items-center justify-center gap-3">
              <button
                type="button"
                className="btn btn-secundario"
                onClick={() => setMovPagina((n) => n + 1)}
              >
                Mostrar mais 100
              </button>
              <span className="text-[13px] text-suave">
                faltam {movTotal - movimentos.length}
              </span>
            </div>
          )}
        </Cartao>
        </>
      )}
    </div>
  );
}
