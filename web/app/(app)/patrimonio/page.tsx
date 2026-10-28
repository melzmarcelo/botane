"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BotaoExportar from "@/components/exportar";
import ExplicaTela from "@/components/explica-tela";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { api } from "@/lib/api";
import type { Setor } from "@/lib/cadastros";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import {
  COR_PREVENTIVA, CRITICIDADES, PREVENTIVA, SITUACOES, aCadastrar, dataBr, imprimirPlaquetas, listar,
  resumo, type ACadastrar, type Bem, type Resumo,
} from "@/lib/patrimonio";
import { useSessao } from "@/lib/sessao";

/**
 * Patrimônio: os equipamentos e móveis da loja, um registro por item físico.
 *
 * 🔑 **Pedido do dono (27/10/2026)**, com a planilha `Inventario_Equipamentos_Botane.xlsx`
 * (uma aba por setor). O quadro de cima é a aba "Resumo" dela; a lista, as abas dos
 * setores. Etapas 1 e 2 da proposta: cadastro com plaqueta e importação, manutenção com
 * plano e alertas.
 * ⚠️ **Os filtros moram na URL** — é por ela que o alerta do Início traz a lista já
 * filtrada ("preventiva vencida", "crítico parado"). `PARADOS` junta "em manutenção" e
 * "parado", que é o que o alerta crítico procura.
 */

const SITUACAO_OPCOES: [string, string][] = [
  ["", "Todos, menos os baixados"],
  ["PARADOS", "Em manutenção ou parados"],
  ...Object.entries(SITUACOES),
];

export default function PaginaPatrimonio() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const podeCadastrar = pode("patrimonio.cadastrar");
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [setor, setSetor] = useEstadoNaUrl<string>("setor", "");
  const [situacao, setSituacao] = useEstadoNaUrl<string>("situacao", "");
  const [preventiva, setPreventiva] = useEstadoNaUrl<string>("preventiva", "");
  const [criticidade, setCriticidade] = useEstadoNaUrl<string>("criticidade", "");
  const [lista, setLista] = useState<Bem[] | null>(null);
  const [quadro, setQuadro] = useState<Resumo | null>(null);
  const [pendentes, setPendentes] = useState<ACadastrar[]>([]);
  const [setores, setSetores] = useState<Setor[]>([]);
  const [erro, setErro] = useState("");
  const [marcados, setMarcados] = useState<number[]>([]);
  const [imprimindo, setImprimindo] = useState(false);
  const pag = usePaginacao("patrimonio", { filtros: [busca, setor, situacao, preventiva, criticidade] });

  const filtros = useMemo(() => ({
    busca,
    situacao: situacao === "PARADOS" ? ["EM_MANUTENCAO", "PARADO"] : situacao ? [situacao] : [],
    preventiva: preventiva ? [preventiva] : [],
    criticidade: criticidade ? [criticidade] : [],
    setores: setor ? [Number(setor)] : [],
  }), [busca, setor, situacao, preventiva, criticidade]);

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    setLista(null);
    try {
      const l = await listar(pag.parametros, filtros);
      setLista(l.itens);
      pag.setTotal(l.total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, pag.offset, pag.porPagina, filtros]);

  useEffect(() => { void carregar(); }, [carregar]);
  useEffect(() => {
    resumo().then(setQuadro).catch(() => {});
    aCadastrar().then(setPendentes).catch(() => {});
    api.get<Setor[]>("/setores").then(setSetores).catch(() => {});
  }, []);

  const alternar = (id: number) =>
    setMarcados((m) => (m.includes(id) ? m.filter((x) => x !== id) : [...m, id]));

  async function plaquetas() {
    setImprimindo(true);
    try {
      await imprimirPlaquetas(marcados);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível imprimir");
    } finally {
      setImprimindo(false);
    }
  }

  const filtrado = !!(busca || setor || situacao || preventiva || criticidade);
  const iniciais = {
    busca_bem: busca || undefined,
    situacao_bem: filtros.situacao.length ? filtros.situacao : undefined,
    preventiva_bem: filtros.preventiva.length ? filtros.preventiva : undefined,
    criticidade_bem: filtros.criticidade.length ? filtros.criticidade : undefined,
    setores: filtros.setores.length ? filtros.setores : undefined,
  };

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Estoque</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Patrimônio</h1>
        <ExplicaTela>
          Os equipamentos e móveis da loja, <strong>um registro por item</strong>: série, compra,
          garantia, assistência, criticidade e a manutenção preventiva. Cada bem ganha uma
          plaqueta com QR — lida no celular, ela abre a ficha dele. Não mexe no estoque.
        </ExplicaTela>
      </header>

      <div className="flex flex-wrap gap-2">
        {podeCadastrar && (
          <>
            <Link href="/patrimonio/novo" className="btn btn-primario" id="patrimonio-novo">
              Novo bem
            </Link>
            <Link href="/patrimonio/importar" className="btn btn-secundario" id="patrimonio-importar">
              Importar planilha
            </Link>
          </>
        )}
        {/* Etapa 3 (140): a conferência pelas plaquetas. Quem só vê também entra — para
            acompanhar a volta e baixar a folha. */}
        <Link href="/patrimonio/conferencias" className="btn btn-secundario" id="patrimonio-conferencias">
          Conferência
        </Link>
        {/* Etapa 4 (141): o valor e a depreciação. */}
        <Link href="/patrimonio/valor" className="btn btn-secundario" id="patrimonio-valor">
          Valor
        </Link>
        <BotaoExportar relatorio="patrimonio" iniciais={iniciais} />
        <BotaoExportar relatorio="patrimonio-manutencoes" rotulo="Manutenções"
                       iniciais={{ setores: iniciais.setores, busca_bem: iniciais.busca_bem }} />
      </div>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {/* 🔑 **O que entrou como Patrimônio e não virou bem** (pedido do dono, 27/10/2026:
          "caso entre um produto novo como patrimônio, o usuário deverá cadastrar ele como um
          novo bem"). A régua é o saldo: 3 no estoque e 1 bem ligado = faltam 2. */}
      {pendentes.length > 0 && (
        <section id="a-cadastrar">
          <Cartao titulo="Entrou como Patrimônio e falta cadastrar"
                  descricao="Cada item que entra no estoque com o tipo Patrimônio precisa do cadastro dele, para ter plaqueta e manutenção.">
            <div className="grid-rolante">
              <table className="tabela" id="patrimonio-a-cadastrar">
                <thead>
                  <tr><th>Produto</th><th>Onde está</th><th className="num">No estoque</th>
                      <th className="num">Bens</th><th className="num">Faltam</th><th /></tr>
                </thead>
                <tbody>
                  {pendentes.map((x) => (
                    <tr key={x.id_produto}>
                      <td>
                        <Link href={`/produtos/${x.id_produto}`} className="link-registro">{x.produto}</Link>
                        <span className="block text-[12px] text-suave mono">{x.codigo}</span>
                      </td>
                      <td className="text-[13.5px]">{x.onde ?? "—"}</td>
                      <td className="num">{x.saldo}</td>
                      <td className="num">{x.bens}</td>
                      <td className="num font-semibold">{x.faltam}</td>
                      <td>
                        {podeCadastrar && (
                          <Link href={`/patrimonio/novo?produto=${x.id_produto}`} className="btn btn-secundario">
                            Cadastrar bem
                          </Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Cartao>
        </section>
      )}

      {quadro && quadro.setores.length > 0 && (
        <Cartao titulo="Por setor" descricao="Clique no setor para ver só os bens dele.">
          <div className="grid-rolante">
            <table className="tabela" id="patrimonio-resumo">
              <thead>
                <tr>
                  <th>Setor</th>
                  <th className="num">Bens</th>
                  <th className="num">Criticidade alta</th>
                  <th className="num">Em manutenção ou parados</th>
                  <th className="num">Preventiva vencida</th>
                  <th className="num">Vence em 30 dias</th>
                  <th className="num">Sem plano</th>
                  <th className="num">A confirmar</th>
                </tr>
              </thead>
              <tbody>
                {quadro.setores.map((s) => (
                  <tr key={s.setor}>
                    <td>
                      {s.id_setor ? (
                        <button type="button" className="link-registro font-semibold"
                                onClick={() => setSetor(String(s.id_setor))}>
                          {s.setor}
                        </button>
                      ) : s.setor}
                    </td>
                    <td className="num">{s.bens}</td>
                    <td className="num">{s.criticidade_alta || "—"}</td>
                    <td className="num">{s.parados || "—"}</td>
                    <td className="num">{s.vencidas ? <b className="text-[var(--color-erro)]">{s.vencidas}</b> : "—"}</td>
                    <td className="num">{s.vencendo || "—"}</td>
                    <td className="num">{s.sem_plano || "—"}</td>
                    <td className="num">{s.a_confirmar || "—"}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td className="font-semibold">Total</td>
                  <td className="num font-semibold">{quadro.total.bens}</td>
                  <td className="num">{quadro.total.criticidade_alta}</td>
                  <td className="num">{quadro.total.parados}</td>
                  <td className="num">{quadro.total.vencidas}</td>
                  <td className="num">{quadro.total.vencendo}</td>
                  <td className="num">{quadro.total.sem_plano}</td>
                  <td className="num">{quadro.total.a_confirmar}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </Cartao>
      )}

      <Cartao>
        <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <input className="campo" id="patrimonio-busca" placeholder="Equipamento, código, marca, série…"
                 value={busca} onChange={(e) => setBusca(e.target.value)} aria-label="Buscar" />
          <select className="campo" id="patrimonio-setor" value={setor} aria-label="Setor"
                  onChange={(e) => setSetor(e.target.value)}>
            <option value="">Todos os setores</option>
            {setores.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
          </select>
          <select className="campo" id="patrimonio-situacao" value={situacao} aria-label="Situação"
                  onChange={(e) => setSituacao(e.target.value)}>
            {SITUACAO_OPCOES.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
          </select>
          <select className="campo" id="patrimonio-preventiva" value={preventiva} aria-label="Preventiva"
                  onChange={(e) => setPreventiva(e.target.value)}>
            <option value="">Qualquer preventiva</option>
            {Object.entries(PREVENTIVA).map(([v, n]) => <option key={v} value={v}>{n}</option>)}
          </select>
          <select className="campo" id="patrimonio-criticidade" value={criticidade} aria-label="Criticidade"
                  onChange={(e) => setCriticidade(e.target.value)}>
            <option value="">Qualquer criticidade</option>
            {Object.entries(CRITICIDADES).map(([v, n]) => <option key={v} value={v}>{n}</option>)}
          </select>
        </div>

        {podeCadastrar && marcados.length > 0 && (
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <button type="button" className="btn btn-secundario" id="patrimonio-plaquetas"
                    disabled={imprimindo} aria-busy={imprimindo} onClick={() => void plaquetas()}>
              Imprimir {marcados.length} plaqueta(s)
            </button>
            <button type="button" className="link-acao text-[13px]" onClick={() => setMarcados([])}>
              desmarcar
            </button>
          </div>
        )}

        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>
            {filtrado
              ? "Nenhum bem com estes filtros."
              : "Nenhum bem cadastrado ainda. Comece importando a planilha de equipamentos."}
          </Vazio>
        ) : (
          <div className="grid-rolante">
            <table className="tabela" id="patrimonio-lista">
              <thead>
                <tr>
                  {podeCadastrar && (
                    <th className="w-8">
                      <input type="checkbox" aria-label="Marcar todos desta página"
                             checked={lista.every((b) => marcados.includes(b.id))}
                             onChange={(e) => setMarcados(e.target.checked
                               ? Array.from(new Set([...marcados, ...lista.map((b) => b.id)]))
                               : marcados.filter((id) => !lista.some((b) => b.id === id)))} />
                    </th>
                  )}
                  <th>Código</th>
                  <th>Equipamento</th>
                  <th>Setor · local</th>
                  <th>Criticidade</th>
                  <th>Situação</th>
                  <th>Preventiva</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((b) => (
                  <tr key={b.id}>
                    {podeCadastrar && (
                      <td>
                        <input type="checkbox" aria-label={`Marcar ${b.codigo}`}
                               checked={marcados.includes(b.id)} onChange={() => alternar(b.id)} />
                      </td>
                    )}
                    <td className="mono">
                      <Link href={`/patrimonio/${b.id}`} className="link-registro font-semibold">{b.codigo}</Link>
                      {b.apelido && <span className="block text-[12px] text-suave">{b.apelido}</span>}
                    </td>
                    <td>
                      {b.descricao}
                      {(b.marca || b.modelo) && (
                        <span className="block text-[12.5px] text-suave">
                          {[b.marca, b.modelo].filter(Boolean).join(" · ")}
                        </span>
                      )}
                    </td>
                    <td>
                      {b.setor ?? "—"}
                      {b.local && <span className="text-suave"> · {b.local}</span>}
                    </td>
                    <td>{b.criticidade_txt ?? "—"}</td>
                    <td>
                      {b.situacao === "EM_USO" ? b.situacao_txt : (
                        <Etiqueta cor={b.situacao === "A_CONFIRMAR" ? "neutro" : "alerta"}>
                          {b.situacao_txt}
                        </Etiqueta>
                      )}
                    </td>
                    <td>
                      {b.status_preventiva === "FORA" ? "—" : (
                        <>
                          <Etiqueta cor={COR_PREVENTIVA[b.status_preventiva] ?? "neutro"}>
                            {b.preventiva_txt}
                          </Etiqueta>
                          {b.proxima_preventiva && (
                            <span className="block text-[12.5px] text-suave">
                              próxima {dataBr(b.proxima_preventiva)}
                            </span>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Paginacao p={pag} rotulo="bens" />
      </Cartao>
    </div>
  );
}
