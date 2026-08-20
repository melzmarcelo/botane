"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Local, ProdutoResumo, reais } from "@/lib/cadastros";
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

type Motivo = { id: number; nome: string };
type Lancamento = "entrada" | "saida" | "perda" | "transferencia" | null;

const qtd = (n: number | string) =>
  Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 3 });

type TipoMovimento = { tipo: string; rotulo: string };

export default function PaginaEstoque() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const [aba, setAba] = useState<"saldos" | "movimentos">("saldos");
  const [saldos, setSaldos] = useState<Saldo[] | null>(null);
  const [movimentos, setMovimentos] = useState<Movimento[] | null>(null);
  const [produtos, setProdutos] = useState<ProdutoResumo[]>([]);
  const [locais, setLocais] = useState<Local[]>([]);
  const [motivos, setMotivos] = useState<Motivo[]>([]);
  const [busca, setBusca] = useState("");
  const [idLocal, setIdLocal] = useState("");
  const [comSaldo, setComSaldo] = useState(true);
  const [erro, setErro] = useState("");

  // Filtros do razão. Separados dos saldos de propósito: são perguntas
  // diferentes — "quanto tenho hoje" e "o que aconteceu com o café em agosto".
  const [movBusca, setMovBusca] = useState("");
  const [movTipo, setMovTipo] = useState("");
  const [movLocal, setMovLocal] = useState("");
  const [movInicio, setMovInicio] = useState("");
  const [movFim, setMovFim] = useState("");
  const [movTotal, setMovTotal] = useState(0);
  const [movPagina, setMovPagina] = useState(1);
  const [tipos, setTipos] = useState<TipoMovimento[]>([]);

  const [lancamento, setLancamento] = useState<Lancamento>(null);
  const [f, setF] = useState({
    id_produto: "", quantidade: "", custo_unitario: "", id_local: "",
    id_local_destino: "", id_motivo_perda: "", documento: "", observacao: "",
    lote: "", validade: "",
  });
  const [salvando, setSalvando] = useState(false);
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
      if (busca.trim()) q.set("busca", busca.trim());
      if (idLocal) q.set("id_local", idLocal);
      if (comSaldo) q.set("apenas_com_saldo", "true");
      setSaldos(await api.get<Saldo[]>(`/estoque/saldos?${q}`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [busca, idLocal, comSaldo]);

  const POR_PAGINA = 100;
  const temFiltroMov = !!(movBusca || movTipo || movLocal || movInicio || movFim);

  const carregarMovimentos = useCallback(async () => {
    try {
      const q = new URLSearchParams({ limite: String(POR_PAGINA * movPagina) });
      if (movBusca.trim()) q.set("busca", movBusca.trim());
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
  }, [movBusca, movTipo, movLocal, movInicio, movFim, movPagina]);

  // Trocar o filtro volta para a primeira página: manter a 3ª página de um
  // filtro no outro mostraria uma lista vazia sem explicação.
  useEffect(() => {
    setMovPagina(1);
  }, [movBusca, movTipo, movLocal, movInicio, movFim]);

  useEffect(() => {
    const t = setTimeout(() => void carregarMovimentos(), movBusca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregarMovimentos, movBusca]);

  useEffect(() => {
    api.get<ProdutoResumo[]>("/produtos").then((p) =>
      setProdutos(p.filter((x) => x.controla_estoque)),
    ).catch(() => {});
    api.get<Local[]>("/locais").then(setLocais).catch(() => {});
    api.get<Motivo[]>("/estoque/motivos-perda").then(setMotivos).catch(() => {});
    api.get<TipoMovimento[]>("/estoque/tipos-movimento").then(setTipos).catch(() => {});
  }, []);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  function abrir(tipo: Lancamento) {
    setLancamento(tipo);
    setErro("");
    setF({
      id_produto: "", quantidade: "", custo_unitario: "",
      id_local: String(locais.find((l) => l.principal)?.id ?? locais[0]?.id ?? ""),
      id_local_destino: "", id_motivo_perda: "", documento: "", observacao: "",
      lote: "", validade: "",
    });
  }

  async function lancar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    const base = {
      id_produto: Number(f.id_produto),
      quantidade: Number(f.quantidade.replace(",", ".")),
      id_local: f.id_local ? Number(f.id_local) : null,
      observacao: f.observacao || null,
    };
    try {
      if (lancamento === "entrada") {
        const r = await api.post<{ custo_medio: number }>("/estoque/entradas", {
          ...base,
          custo_unitario: Number(f.custo_unitario.replace(",", ".")),
          documento: f.documento || null,
          lote: f.lote || null,
          validade: f.validade || null,
        });
        aviso.sucesso(`Entrada lançada. Novo custo médio: ${reais(Number(r.custo_medio))}`);
      } else if (lancamento === "transferencia") {
        await api.post("/estoque/transferencias", {
          id_produto: base.id_produto,
          quantidade: base.quantidade,
          id_local_origem: Number(f.id_local),
          id_local_destino: Number(f.id_local_destino),
          observacao: base.observacao,
        });
        aviso.sucesso("Transferência lançada.");
      } else {
        const r = await api.post<{
          custo_unitario: number;
          custo_provisorio: boolean;
          message: string;
        }>("/estoque/saidas", {
          ...base,
          tipo: lancamento === "perda" ? "SAIDA_PERDA" : "SAIDA_CONSUMO_INTERNO",
          id_motivo_perda: f.id_motivo_perda ? Number(f.id_motivo_perda) : null,
        });
        // A frase de qual lote saiu vem pronta do servidor: é a mesma que qualquer
        // outro consumidor da API recebe, e escrevê-la de novo aqui seria a
        // segunda versão da mesma regra.
        aviso.sucesso(
          `${r.message ?? "Saída lançada"} — ${reais(Number(r.custo_unitario))} por unidade.` +
            (r.custo_provisorio ? " Custo provisório: não havia saldo suficiente." : ""),
        );
      }
      setLancamento(null);
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível lançar");
    } finally {
      setSalvando(false);
    }
  }

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
    if (movBusca.trim()) q.set("busca", movBusca.trim());
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
          {pode("estoque.entradas") && (
            <button className="btn btn-primario" onClick={() => abrir("entrada")}>
              Entrada
            </button>
          )}
          {pode("estoque.saidas") && (
            <button className="btn btn-secundario" onClick={() => abrir("saida")}>
              Saída
            </button>
          )}
          {pode("estoque.perdas") && (
            <button className="btn btn-secundario" onClick={() => abrir("perda")}>
              Perda
            </button>
          )}
          {pode("estoque.transferencias") && locais.length > 1 && (
            <button className="btn btn-secundario" onClick={() => abrir("transferencia")}>
              Transferir
            </button>
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

      {lancamento && (
        <Cartao
          titulo={
            {
              entrada: "Entrada de estoque",
              saida: "Saída / consumo",
              perda: "Apontar perda",
              transferencia: "Transferir entre locais",
            }[lancamento]
          }
          descricao={
            lancamento === "entrada"
              ? "O custo informado é o de aquisição: já com frete e desconto rateados."
              : lancamento === "perda"
                ? "Perda com nome vira decisão; perda anônima vira desconfiança."
                : undefined
          }
          acao={
            <button className="rotulo hover:text-erro" onClick={() => setLancamento(null)}>
              cancelar
            </button>
          }
        >
          <form onSubmit={lancar} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Campo rotulo="Produto" className="sm:col-span-2">
              <select
                className="campo"
                required
                value={f.id_produto}
                onChange={(e) => setF({ ...f, id_produto: e.target.value })}
              >
                <option value="">— escolha —</option>
                {produtos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nome} {p.um_estoque ? `(${p.um_estoque})` : ""}
                  </option>
                ))}
              </select>
            </Campo>
            <Campo rotulo="Quantidade">
              <input
                className="campo mono"
                type="number"
                step="0.001"
                min="0.001"
                required
                value={f.quantidade}
                onChange={(e) => setF({ ...f, quantidade: e.target.value })}
              />
            </Campo>
            {lancamento === "entrada" && (
              <Campo rotulo="Custo unitário (R$)">
                <input
                  className="campo mono"
                  type="number"
                  step="0.000001"
                  min="0"
                  required
                  value={f.custo_unitario}
                  onChange={(e) => setF({ ...f, custo_unitario: e.target.value })}
                />
              </Campo>
            )}
            <Campo rotulo={lancamento === "transferencia" ? "De qual local" : "Local"}>
              <select
                className="campo"
                value={f.id_local}
                onChange={(e) => setF({ ...f, id_local: e.target.value })}
              >
                {locais.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.nome}
                  </option>
                ))}
              </select>
            </Campo>
            {lancamento === "transferencia" && (
              <Campo rotulo="Para qual local">
                <select
                  className="campo"
                  required
                  value={f.id_local_destino}
                  onChange={(e) => setF({ ...f, id_local_destino: e.target.value })}
                >
                  <option value="">— escolha —</option>
                  {locais
                    .filter((l) => l.id.toString() !== f.id_local)
                    .map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.nome}
                      </option>
                    ))}
                </select>
              </Campo>
            )}
            {lancamento === "perda" && (
              <Campo rotulo="Motivo">
                <select
                  className="campo"
                  required
                  value={f.id_motivo_perda}
                  onChange={(e) => setF({ ...f, id_motivo_perda: e.target.value })}
                >
                  <option value="">— escolha —</option>
                  {motivos.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.nome}
                    </option>
                  ))}
                </select>
              </Campo>
            )}
            {lancamento === "entrada" && (
              <>
                <Campo rotulo="Documento" dica="nº da nota, se houver">
                  <input
                    className="campo"
                    value={f.documento}
                    onChange={(e) => setF({ ...f, documento: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="Lote" dica="opcional">
                  <input
                    className="campo mono"
                    value={f.lote}
                    onChange={(e) => setF({ ...f, lote: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="Validade" dica="opcional">
                  <input
                    className="campo"
                    type="date"
                    value={f.validade}
                    onChange={(e) => setF({ ...f, validade: e.target.value })}
                  />
                </Campo>
              </>
            )}
            <Campo rotulo="Observação" className="sm:col-span-2">
              <input
                className="campo"
                value={f.observacao}
                onChange={(e) => setF({ ...f, observacao: e.target.value })}
              />
            </Campo>
            <div className="flex items-end">
              <button className="btn btn-primario" type="submit" disabled={salvando}>
                {salvando ? "Lançando…" : "Lançar"}
              </button>
            </div>
          </form>
        </Cartao>
      )}

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
              <label className="min-w-0 flex-1 sm:min-w-[200px]">
                <span className="rotulo">Buscar</span>
                <input
                  className="campo mt-1.5"
                  placeholder="produto ou código"
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                />
              </label>
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
            <label className="min-w-0 flex-1 sm:min-w-[190px]">
              <span className="rotulo">Produto</span>
              <input
                className="campo mt-1.5"
                placeholder="nome ou código"
                value={movBusca}
                onChange={(e) => setMovBusca(e.target.value)}
              />
            </label>
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
