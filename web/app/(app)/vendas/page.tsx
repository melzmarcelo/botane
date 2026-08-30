"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { CANAIS, dataBr, horaBr, ORIGENS, Venda } from "./tipos";

/**
 * A lista das vendas — só a lista.
 *
 * Lançar e conferir saíram daqui para páginas próprias (`/vendas/lancar` e
 * `/vendas/[id]`). Os dois eram cartões abertos no meio desta tela: o
 * formulário de planilha e o de lançamento à mão ocupavam a primeira dobra
 * inteira, e as vendas — que são o assunto da página — começavam abaixo do
 * campo de colar texto. Com 1.375 vendas num mês isso é a tela errada.
 *
 * ⚠️ **A linha inteira leva ao detalhe.** Uma venda não tem nada que se
 * resolva na lista: o que alguém quer saber (quais itens, quanto custou, se
 * baixou estoque) só cabe na página dela.
 */
export default function PaginaVendas() {
  const aviso = useAviso();
  const router = useRouter();
  const { pode } = useSessao();
  const podeLancar = pode("cmv.painel") || pode("cmv.fechamento");

  const [lista, setLista] = useState<Venda[] | null>(null);
  const [pendencias, setPendencias] = useState<number>(0);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");
  const [origem, setOrigem] = useState("");
  const [ocupado, setOcupado] = useState(false);

  // ⚠️ `filtros:` faz a busca voltar para a primeira página. Sem isso, quem
  // está na página 7 e digita um documento cai numa tela vazia sem explicação.
  const pag = usePaginacao("vendas", { padrao: 50, filtros: [busca, origem] });

  const carregar = useCallback(async () => {
    try {
      const q = new URLSearchParams(pag.parametros);
      if (busca.trim()) q.set("busca", busca.trim());
      if (origem) q.set("origem", origem);
      const [v, p] = await Promise.all([
        api.listar<Venda>(`/vendas?${q}`),
        api.get<unknown[]>("/vendas/sem-vinculo"),
      ]);
      setLista(v.itens);
      pag.setTotal(v.total);
      setPendencias(p.length);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.offset, pag.porPagina, busca, origem]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 350 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  /**
   * Traz os cupons do PDV — o mesmo lugar onde Compras busca no Omie.
   *
   * ⚠️ **A busca vive na tela do ASSUNTO, não só em Integrações.** Quem opera
   * abre Vendas para ver as vendas; ter de lembrar que a busca mora noutra tela
   * é o tipo de passo que ninguém dá — e venda que não é buscada é receita que
   * falta no CMV do período, sem nada denunciando.
   *
   * ⚠️ Sem período: a janela vai desde a última venda importada, com folga. A
   * resposta diz qual janela foi usada.
   */
  async function buscarNoPdv() {
    setOcupado(true);
    try {
      const r = await api.post<{
        importadas: number;
        itens_sem_vinculo: number;
        modo: string;
        message: string;
      }>("/pdv/sincronizar");
      aviso.sucesso(
        r.message +
          (r.modo === "simulado" ? " (modo simulado — dados de demonstração)" : ""),
        (r.itens_sem_vinculo ?? 0) > 0
          ? { texto: "ver itens sem vínculo", ao: () => router.push("/vendas/sem-vinculo") }
          : undefined,
      );
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível buscar as vendas");
    } finally {
      setOcupado(false);
    }
  }

  /**
   * Passa o de-para de novo nos itens que ficaram sem produto.
   *
   * ⚠️ Existe pela mesma razão do botão gêmeo em Compras: a ordem real é a venda
   * chegar ANTES de o cardápio estar ligado. Sem ele, item que não achou produto
   * no dia da importação só sairia da fila na mão.
   */
  async function reconciliar() {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>("/pdv/reconciliar");
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reconciliar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">CMV</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Vendas</h1>
          <p className="mt-1 max-w-[66ch] text-suave">
            As vendas alimentam o CMV teórico: quantidade vendida × custo da ficha na data. O
            custo é <b>congelado</b> na importação — corrigir uma receita amanhã não reescreve o
            mês passado.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {podeLancar && (
            <Link href="/vendas/lancar" className="btn btn-primario">
              Lançar
            </Link>
          )}
          {/* ⚠️ O gêmeo do "Buscar no Omie" de Compras. A busca precisa estar na
              tela do assunto: quem abre Vendas para ver as vendas não vai
              lembrar que ela mora em Integrações — e venda não buscada é receita
              faltando no CMV, sem nada denunciando. */}
          {pode("integracao.pdv") && (
            <button className="btn btn-secundario" onClick={buscarNoPdv} disabled={ocupado}>
              {ocupado ? "Buscando…" : "Buscar no PDV"}
            </button>
          )}
          {pendencias > 0 && pode("integracao.pdv") && (
            <button
              className="btn btn-secundario"
              onClick={reconciliar}
              disabled={ocupado}
              title="Procura de novo o produto dos itens pendentes"
            >
              Reconciliar {pendencias} pendente(s)
            </button>
          )}
        </div>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {/* ⚠️ A fila de de-para vira um AVISO com caminho, não uma tabela no topo.
          Ela ocupava meia tela mostrando o que já está resolvido; o que importa
          é saber que existe e conseguir chegar nela. */}
      {pendencias > 0 && (
        <Aviso tipo="info">
          {pendencias} item(ns) vendido(s) não acharam produto no cadastro — enquanto
          estiverem assim, essa receita não entra no CMV teórico.{" "}
          <Link href="/vendas/sem-vinculo" className="underline">
            resolver
          </Link>
        </Aviso>
      )}

      <Cartao titulo={lista ? `${pag.total ?? lista.length} venda(s)` : "Vendas"}>
        <div className="mb-4 flex flex-wrap gap-3">
          <input
            className="campo max-w-[280px]"
            placeholder="documento ou cupom"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
          <select
            className="campo max-w-[200px]"
            value={origem}
            onChange={(e) => setOrigem(e.target.value)}
          >
            <option value="">todas as origens</option>
            {Object.entries(ORIGENS).map(([v, r]) => (
              <option key={v} value={v}>
                {r}
              </option>
            ))}
          </select>
        </div>

        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>
            {busca || origem
              ? "Nenhuma venda com esse filtro."
              : "Nenhuma venda ainda. Lance uma, cole a planilha do PDV ou ligue a integração."}
          </Vazio>
        ) : (
          <ul className="flex flex-col gap-px bg-linha">
            {lista.map((v) => (
              <li
                key={v.id}
                className={`flex flex-wrap items-center justify-between gap-3 bg-superficie py-3 ${
                  v.cancelada ? "opacity-55" : ""
                }`}
              >
                <Link href={`/vendas/${v.id}`} className="min-w-0 text-left">
                  <span className="link-registro">
                    {dataBr(v.data)}
                    {horaBr(v.hora) && ` às ${horaBr(v.hora)}`} ·{" "}
                    {v.documento ?? `venda #${v.id}`}
                  </span>
                  <span className="block text-[13px] text-suave">
                    {ORIGENS[v.origem] ?? v.origem.toLowerCase()}
                    {v.canal ? ` · ${CANAIS[v.canal] ?? v.canal.toLowerCase()}` : ""} ·{" "}
                    {v.itens} item(ns) · {reais(Number(v.valor_total))}
                  </span>
                </Link>
                <span className="flex items-center gap-2">
                  {v.sem_custo > 0 && (
                    <Etiqueta cor="alerta">{v.sem_custo} sem custo</Etiqueta>
                  )}
                  {v.cancelada && <Etiqueta cor="alerta">cancelada</Etiqueta>}
                </span>
              </li>
            ))}
          </ul>
        )}
        <Paginacao p={pag} rotulo="venda(s)" />
      </Cartao>
    </div>
  );
}
