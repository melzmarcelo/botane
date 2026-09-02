"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Local, ProdutoResumo, reais } from "@/lib/cadastros";
import { FiltroCadastro } from "@/components/busca-cadastro";
import { fonteProdutos } from "@/lib/busca-cadastro";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import BotaoExportar from "@/components/exportar";
import LotesEmEstoque from "./lotes";

/** Uma linha por PRODUTO somando os locais desta loja. */
type SaldoAgrupado = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  quantidade: number;
  valor: number;
  custo_medio: number | null;
  abaixo_do_minimo: boolean;
  por_local: { id_local: number; local: string; setor: string | null;
               quantidade: number; valor: number }[];
};

/** Uma linha da visão de EMPRESA: o produto somando as lojas. */
type SaldoRede = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  quantidade: number;
  valor: number;
  /** ⚠️ Nulo quando a rede tem zero daquele item: é uma divisão pela
      quantidade, e "não custa nada" não é a mesma coisa que "não há nada
      para custar". */
  custo_medio: number | null;
  abaixo_do_minimo: boolean;
  por_loja: { id_unidade: number; loja: string; quantidade: number; valor: number }[];
};

type Saldo = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  id_local: number;
  local: string;
  quantidade: number;
  /** Já despachado para outra loja e ainda não recebido lá. */
  em_transito?: number;
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
  const { pode, eu } = useSessao();
  const variasLojas = (eu?.unidades?.length ?? 0) > 1;
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
  // 🔑 **A visão de EMPRESA.** Toda tela do sistema responde por uma loja, e
  // está certo — quem opera opera numa de cada vez. Mas quem responde pelas
  // duas precisava trocar de loja no seletor e somar de cabeça para saber
  // quanto a rede tem de um item. Aqui a linha vira o PRODUTO, e a prateleira
  // sai: agrupar por local devolveria a mesma lista, só que mais longa.
  // 🔑 **Três granularidades, não duas caixinhas.** O processo da casa põe o
  // mesmo produto em vários locais — o açúcar entra no Estoque Central e cada
  // setor leva um pacote para o seu canto. "Onde está" e "quanto a loja tem"
  // são perguntas diferentes, e a de empresa é uma terceira. Duas caixinhas
  // que interagem fariam quatro combinações, duas delas sem sentido.
  const [visao, setVisao] = useState<"prateleira" | "produto" | "empresa">("prateleira");
  const rede = visao === "empresa";
  const [saldosRede, setSaldosRede] = useState<SaldoRede[] | null>(null);
  const [saldosAgrupados, setAgrupados] = useState<SaldoAgrupado[] | null>(null);
  // 🔑 **O painel da rede conta o produto INATIVO que ainda tem saldo; esta
  // lista não.** As duas regras estão certas — o painel responde ao CMV, a
  // lista mostra o que se opera —, mas os números não fechavam e nada dizia por
  // quê. Agora a tela diz quanto ficou de fora, e a caixinha inclui.
  const [inativos, setInativos] = useState(false);
  const [fora, setFora] = useState<{ produtos: number; valor: number } | null>(null);
  const [erro, setErro] = useState("");
  // O que mexe no razão pergunta antes: estorno não se desfaz, ele contrapõe.
  const [confirmando, setConfirmando] = useState<Movimento | null>(null);

  // Filtros do razão. Separados dos saldos de propósito: são perguntas
  // diferentes — "quanto tenho hoje" e "o que aconteceu com o café em agosto".
  const [movBusca, setMovBusca] = useState("");
  const [produtoMov, setProdutoMov] = useState<{ id: number; rotulo: string } | null>(null);
  const [movTipo, setMovTipo] = useState("");
  const [movLocal, setMovLocal] = useState("");
  const [movInicio, setMovInicio] = useState("");
  const [movFim, setMovFim] = useState("");
  // 🔑 **A saída que não achou saldo sai por um custo PROVISÓRIO**, e cada uma
  // é uma entrada que ninguém lançou. A etiqueta na linha sempre existiu, mas
  // com centenas de movimentos ela só ajuda quem já está olhando para a linha
  // certa — não havia como perguntar "quais são?".
  const [movProvisorio, setMovProvisorio] = useState(false);
  const [tipos, setTipos] = useState<TipoMovimento[]>([]);
  const pagSaldos = usePaginacao("saldos", {
    // ⚠️ `rede` entra como filtro: trocar de modo muda o número de linhas, e
    // quem estava na página 7 cairia numa tela vazia sem nada explicando.
    filtros: [busca, produtoSaldo?.id, idLocal, comSaldo, visao, inativos],
  });
  const pagMov = usePaginacao("razao", {
    padrao: 100,
    filtros: [movBusca, produtoMov?.id, movTipo, movLocal, movInicio, movFim, movProvisorio],
  });

  const carregar = useCallback(async () => {
    try {
      const q = new URLSearchParams(pagSaldos.parametros);
      if (produtoSaldo) q.set("id_produto", String(produtoSaldo.id));
      else if (busca.trim()) q.set("busca", busca.trim());
      if (comSaldo) q.set("apenas_com_saldo", "true");
      if (rede) {
        // ⚠️ O local sai do pedido de propósito: na visão de empresa a linha é
        // o produto, e mandar um filtro que o servidor não usa faria a tela
        // prometer um corte que não acontece.
        if (inativos) q.set("incluir_inativos", "true");
        const r = await api.listar<SaldoRede>(`/estoque/saldos-rede?${q}`);
        setSaldosRede(r.itens);
        pagSaldos.setTotal(r.total);
        // ⚠️ **Os MESMOS filtros da lista**, e quem responde é o servidor: um
        // aviso que fala de outro recorte diria "e mais R$ 24 mil" com um
        // produto só na tela. Com os inativos já dentro não há o que avisar.
        if (inativos) setFora(null);
        else {
          const f = new URLSearchParams();
          if (produtoSaldo) f.set("id_produto", String(produtoSaldo.id));
          else if (busca.trim()) f.set("busca", busca.trim());
          if (comSaldo) f.set("apenas_com_saldo", "true");
          setFora(await api.get(`/estoque/saldos-rede/inativos?${f}`));
        }
        return;
      }
      if (visao === "produto") {
        // ⚠️ O local sai do pedido: aqui a linha é o produto, e mandar um
        // filtro que o servidor não usa faria a tela prometer um corte que
        // não acontece. Onde ele está vem em `por_local`.
        const r = await api.listar<SaldoAgrupado>(`/estoque/saldos-agrupados?${q}`);
        setAgrupados(r.itens);
        pagSaldos.setTotal(r.total);
        return;
      }
      if (idLocal) q.set("id_local", idLocal);
      const r = await api.listar<Saldo>(`/estoque/saldos?${q}`);
      setSaldos(r.itens);
      pagSaldos.setTotal(r.total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca, produtoSaldo, idLocal, comSaldo, visao, inativos,
      pagSaldos.offset, pagSaldos.porPagina]);

  const temFiltroMov = !!(movBusca || produtoMov || movTipo || movLocal || movInicio
    || movFim || movProvisorio);

  const carregarMovimentos = useCallback(async () => {
    try {
      const q = new URLSearchParams(pagMov.parametros);
      if (produtoMov) q.set("id_produto", String(produtoMov.id));
      else if (movBusca.trim()) q.set("busca", movBusca.trim());
      if (movTipo) q.set("tipo", movTipo);
      if (movLocal) q.set("id_local", movLocal);
      if (movInicio) q.set("inicio", movInicio);
      if (movFim) q.set("fim", movFim);
      if (movProvisorio) q.set("apenas_provisorios", "true");
      const { itens, total } = await api.listar<Movimento>(`/estoque/movimentos?${q}`);
      setMovimentos(itens);
      pagMov.setTotal(total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [movBusca, produtoMov, movTipo, movLocal, movInicio, movFim, movProvisorio,
      pagMov.offset, pagMov.porPagina]);

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

  // ⚠️ **Isto soma a PÁGINA, não a base** — e por isso o rótulo diz qual das
  // duas coisas é. Chamar de "valor em estoque" o total de vinte linhas de
  // duzentas é a mentira que a casa já pagou noutra tela: quem lê acha que
  // confere o estoque inteiro e confere um pedaço.
  const listaNaTela =
    visao === "empresa" ? saldosRede : visao === "produto" ? saldosAgrupados : saldos;
  const valorTotal = listaNaTela?.reduce((s, x) => s + Number(x.valor), 0) ?? 0;
  const temMaisPaginas = (listaNaTela?.length ?? 0) < pagSaldos.total;

  /** O que a janela de exportação recebe já preenchido.

      ⚠️ São os MESMOS filtros da tela: filtrar aqui e baixar outra coisa faria
      quem conferisse os dois achar que um deles mente. O `id_produto` era
      mandado e o servidor o IGNORAVA — a planilha vinha inteira com um produto
      fixado na tela, calada. */
  const semeaduraDoRazao = {
    inicio: movInicio || undefined,
    fim: movFim || undefined,
    tipos_movimento: movTipo ? [movTipo] : [],
    locais: movLocal ? [Number(movLocal)] : [],
    produtos: produtoMov ? [{ id: produtoMov.id, rotulo: produtoMov.rotulo }] : [],
    busca: produtoMov ? "" : movBusca.trim(),
    provisorio: movProvisorio,
  };

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
          {/* Baixar deixou de ser um clique cego: a janela pergunta o recorte
              e o formato antes de gerar. */}
          {/* ⚠️ **A posição de HOJE e o inventário NUMA DATA são perguntas
              diferentes.** A primeira é operacional ("o que tem na prateleira
              agora"); a segunda é o documento do balanço ("quanto valia o
              estoque em 31/12"), declara o método de custeio e conta inclusive
              o que fica fora do CMV — detergente em estoque é patrimônio igual.
              Oferecer só uma faria a outra ser respondida errado. */}
          {aba === "saldos" ? (
            <>
              <BotaoExportar relatorio="saldos" />
              <BotaoExportar
                relatorio="inventario-valorizado"
                rotulo="Inventário valorizado"
              />
            </>
          ) : (
            <BotaoExportar relatorio="movimentos" iniciais={semeaduraDoRazao} />
          )}
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
              {/* ⚠️ O filtro de local SOME na visão de empresa: ali a linha é o
                  produto, e um seletor que não corta nada é promessa falsa. */}
              {visao === "prateleira" && (
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
              )}
              <label className="flex items-center gap-2 pb-2">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-erva"
                  checked={comSaldo}
                  onChange={(e) => setComSaldo(e.target.checked)}
                />
                <span className="text-[14px]">só com saldo</span>
              </label>
              {/* 🔑 **Três granularidades da mesma pergunta.** Por prateleira
                  responde "onde está" — é o que quem conta precisa. Por produto
                  responde "quanto a loja tem", que é a pergunta de quem compra:
                  com o açúcar espalhado em quatro setores, a lista por
                  prateleira mostra quatro linhas e nenhum total.
                  ⚠️ A de EMPRESA só aparece com mais de uma loja: numa casa só
                  ela é a do meio com uma coluna a mais. */}
              <label className="sm:w-[210px]">
                <span className="rotulo">Ver por</span>
                <select
                  id="visao-saldos"
                  className="campo mt-1.5"
                  value={visao}
                  onChange={(e) => setVisao(e.target.value as typeof visao)}
                >
                  <option value="prateleira">prateleira (onde está)</option>
                  <option value="produto">produto (soma os locais)</option>
                  {variasLojas && <option value="empresa">produto, todas as lojas</option>}
                </select>
              </label>
              {/* Só faz sentido na visão de empresa: é ela que promete explicar
                  o total do painel da rede. */}
              {rede && (
                <label className="flex items-center gap-2 pb-2">
                  <input
                    type="checkbox"
                    id="incluir-inativos"
                    className="h-4 w-4 accent-erva"
                    checked={inativos}
                    onChange={(e) => setInativos(e.target.checked)}
                  />
                  <span className="text-[14px]">incluir inativos</span>
                </label>
              )}
            </div>
            {visao === "produto" && (
              <p className="mt-3 text-[12.5px] text-suave">
                Uma linha por produto, somando os locais desta loja. O detalhe de cada
                prateleira — e o setor dela — vem abaixo do nome.
              </p>
            )}
            {rede && (
              <p className="mt-3 text-[12.5px] text-suave">
                Uma linha por produto, somando as lojas que você enxerga. O custo médio da rede
                é <strong>ponderado</strong> — valor total dividido pela quantidade total —, não
                a média dos custos de cada loja.
              </p>
            )}
          </Cartao>

          <Cartao
            titulo={
              listaNaTela
                ? `${pagSaldos.total} ${visao === "prateleira" ? "linha(s)" : "produto(s)"}`
                : "Saldos"
            }
            descricao={
              temMaisPaginas
                ? `Valor nesta página: ${reais(valorTotal)}`
                : `Valor em estoque: ${reais(valorTotal)}`
            }
          >
            {visao === "produto" ? (
              !saldosAgrupados ? (
                <Carregando />
              ) : !saldosAgrupados.length ? (
                <Vazio>Nada em estoque nesta loja. Comece por uma entrada.</Vazio>
              ) : (
                <div className="overflow-x-auto">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Produto</th>
                        <th>Onde está</th>
                        <th className="num">Total</th>
                        <th className="num">Custo médio</th>
                        <th className="num">Valor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {saldosAgrupados.map((s) => (
                        <tr key={s.id_produto}>
                          <td>
                            <span className="font-semibold">{s.produto}</span>
                            <span className="mono ml-2 text-[12px] text-suave">{s.codigo}</span>
                            {s.abaixo_do_minimo && (
                              <span className="ml-2">
                                <Etiqueta cor="alerta">abaixo do mínimo</Etiqueta>
                              </span>
                            )}
                          </td>
                          <td className="text-[12.5px] text-suave">
                            {/* A prateleira com o SETOR dela: "Confeitaria — 3 KG"
                                é o que o processo da casa precisa ler. */}
                            {s.por_local.map((l) => (
                              <span key={l.id_local} className="block">
                                {l.local}
                                {l.setor ? ` · ${l.setor}` : ""} — {qtd(l.quantidade)}{" "}
                                {s.um_estoque ?? ""}
                              </span>
                            ))}
                          </td>
                          <td className={`num ${Number(s.quantidade) < 0 ? "text-erro" : ""}`}>
                            <span className="font-semibold">{qtd(s.quantidade)}</span>{" "}
                            {s.um_estoque ?? ""}
                          </td>
                          <td className="num">
                            {s.custo_medio === null ? "—" : reais(Number(s.custo_medio))}
                          </td>
                          <td className="num font-semibold">{reais(Number(s.valor))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            ) : rede ? (
              !saldosRede ? (
                <Carregando />
              ) : !saldosRede.length ? (
                <Vazio>Nada em estoque em loja nenhuma. Comece por uma entrada.</Vazio>
              ) : (
                <div className="overflow-x-auto">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Produto</th>
                        {/* Uma coluna por loja, na ordem de sempre — coluna que
                            troca de lugar entre uma página e outra ninguém lê. */}
                        {(eu?.unidades ?? []).map((u) => (
                          <th key={u.id} className="num">
                            {u.apelido ?? u.nome}
                          </th>
                        ))}
                        <th className="num">Total</th>
                        <th className="num">Custo médio</th>
                        <th className="num">Valor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {saldosRede.map((s) => (
                        <tr key={s.id_produto}>
                          <td>
                            <span className="font-semibold">{s.produto}</span>
                            <span className="mono ml-2 text-[12px] text-suave">{s.codigo}</span>
                            {s.abaixo_do_minimo && (
                              <span className="ml-2">
                                <Etiqueta cor="alerta">abaixo do mínimo</Etiqueta>
                              </span>
                            )}
                          </td>
                          {(eu?.unidades ?? []).map((u) => {
                            const daLoja = s.por_loja.find((x) => x.id_unidade === u.id);
                            return (
                              <td key={u.id} className="num text-suave">
                                {/* ⚠️ Traço, não zero: "não tem saldo aqui" e
                                    "tem zero" se leem igual, mas só o segundo é
                                    uma linha de estoque. */}
                                {daLoja ? qtd(daLoja.quantidade) : "—"}
                              </td>
                            );
                          })}
                          <td className={`num ${Number(s.quantidade) < 0 ? "text-erro" : ""}`}>
                            <span className="font-semibold">{qtd(s.quantidade)}</span>{" "}
                            {s.um_estoque ?? ""}
                          </td>
                          <td className="num">
                            {/* Traço quando a rede tem zero: com saldos que se
                                anulam entre lojas, custo médio não existe. */}
                            {s.custo_medio === null ? "—" : reais(Number(s.custo_medio))}
                          </td>
                          <td className="num font-semibold">{reais(Number(s.valor))}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {/* 🔑 **A linha que faz os dois números da empresa fecharem.**
                      O painel da rede conta o produto inativo que ainda tem
                      saldo — é o que o CMV precisa contar —, e esta lista não.
                      Sem dizer quanto ficou de fora, quem confere um contra o
                      outro conclui que um dos dois mente. */}
                  {!!fora?.produtos && (
                    <p id="fora-da-lista" className="mt-3 text-[12.5px] text-suave">
                      E mais <strong>{reais(fora.valor)}</strong> em {fora.produtos} produto(s)
                      <strong> inativos</strong> que ainda têm saldo — o painel da rede os conta.
                      Marque <em>incluir inativos</em> para somá-los aqui.
                    </p>
                  )}
                </div>
              )
            ) : !saldos ? (
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
                          {/* 🔑 **Parte deste saldo já está no carro.** O
                              número continua contando aqui de propósito — é o
                              que mantém o valor com dono enquanto a mercadoria
                              viaja —, mas sem esta linha quem despacha de novo
                              mandaria o que já saiu. */}
                          {Number(s.em_transito) > 0 && (
                            <div className="text-[12px] text-alerta">
                              {qtd(Number(s.em_transito))} em trânsito
                            </div>
                          )}
                        </td>
                        <td className="num">{reais(Number(s.custo_medio))}</td>
                        <td className="num font-semibold">{reais(Number(s.valor))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Paginacao p={pagSaldos} rotulo="linha(s)" />
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
            {/* ⚠️ Caixinha, e não mais um valor no seletor de Movimento: não é
                um TIPO de movimento — é uma marca que qualquer saída pode ter.
                Dentro daquela lista ela pareceria excludente das outras. */}
            <label className="flex items-center gap-2 pb-2">
              <input
                type="checkbox"
                id="so-provisorios"
                className="h-4 w-4 accent-erva"
                checked={movProvisorio}
                onChange={(e) => setMovProvisorio(e.target.checked)}
              />
              <span className="text-[14px]">só custo provisório</span>
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
                  setMovProvisorio(false);
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
              ? `${pagMov.total} lançamento(s)${temFiltroMov ? " no filtro" : ""}.`
              : undefined
          }
        >
          {/* Quem liga o filtro precisa saber o que fazer com o resultado: a
              lista é de saídas esperando uma entrada, não de erros a corrigir
              no razão — que é append-only. */}
          {movProvisorio && !!movimentos?.length && (
            <p className="mb-3 text-[12.5px] text-suave">
              Cada linha saiu por um custo <strong>estimado</strong> porque não havia saldo do
              produto na hora. Lançar a entrada que falta resolve: ela revaloriza o que já saiu
              e o custo passa a ser o de verdade.
            </p>
          )}
          {!movimentos ? (
            <Carregando />
          ) : !movimentos.length ? (
            <Vazio>
              {/* ⚠️ Lista vazia aqui é a BOA notícia, e "nenhum movimento com
                  esses filtros" faria parecer que o filtro não funcionou. */}
              {movProvisorio
                ? "Nenhuma saída por custo provisório no recorte — não há entrada faltando."
                : temFiltroMov
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
                            className="link-acao link-acao-erro"
                            onClick={() => setConfirmando(m)}
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

          {/* O razão cresce todo dia: trazer tudo de uma vez trava a tela
              justamente na casa que mais movimenta. */}
          <Paginacao p={pagMov} rotulo="lançamento(s)" />
        </Cartao>
        </>
      )}

      {confirmando && (
        <Confirmacao
          titulo="Confirmar o estorno"
          rotuloConfirmar="Estornar"
          perigo
          aoCancelar={() => setConfirmando(null)}
          aoConfirmar={() => {
            const m = confirmando;
            setConfirmando(null);
            void estornar(m);
          }}
        >
          <p>
            Estornar <b>{confirmando.rotulo}</b> de <b>{confirmando.produto}</b>?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            O movimento original CONTINUA no razão — o estorno entra como a contrapartida,
            apontando para ele. É assim que o histórico segue fiel ao que aconteceu.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
