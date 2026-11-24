"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { qtd } from "@/lib/numeros";
import {
  AbaOrdem,
  cancelarItem,
  listarOrdens,
  OrdemItem,
  resumoOrdens,
  voltarParaLista,
} from "@/lib/ordens-compra";
import { useSessao } from "@/lib/sessao";

import FormPedido from "./form-pedido";
import { JanelaComprar, JanelaCorrigir } from "./janelas";
import { SeloSituacao, SeloUrgencia } from "./selos";
import JanelaSugestoes from "./sugestoes";

/**
 * A ordem de compra: o que falta comprar e o que já foi.
 *
 * 🔑 **O layout é o do modelo "versão didática" do dono** (24/11/2026): título que diz o que se
 * faz aqui, os quatro passos, o pedido em perguntas numeradas e a lista em colunas, com os mais
 * urgentes primeiro.
 * 🔑 **Cada linha anda sozinha.** Comprou, sai de "A comprar" e entra em "Comprados".
 * 🔑 **Comprado não é recebido**: nada aqui mexe no estoque. Por isso desfazer é um clique.
 * ⚠️ As colunas só existem do `md` para cima: no celular (quem marca costuma estar no mercado)
 * cada linha volta a ser um cartão, com os mesmos elementos.
 */

const PASSOS = [
  { titulo: "Escolha o produto", texto: "Digite o nome ou o código e escolha da lista." },
  { titulo: "Diga quanto precisa", texto: "Quantidade e unidade (kg, L, un, cx…)." },
  { titulo: "Marque a urgência", texto: "Ajuda a priorizar o que comprar primeiro." },
  { titulo: "Acompanhe", texto: "Seu pedido vai de “A comprar” para “Comprados”." },
];

function quando(iso: string) {
  const d = new Date(iso);
  const hoje = new Date();
  const ontem = new Date(hoje);
  ontem.setDate(hoje.getDate() - 1);
  const hora = d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === hoje.toDateString()) return `hoje ${hora}`;
  if (d.toDateString() === ontem.toDateString()) return `ontem ${hora}`;
  return `${d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} ${hora}`;
}

// Produto · Quantidade · Urgência · Pedido por · Situação · ações (e a caixinha de quem compra).
// ⚠️ **Uma grade só, e cabeçalho e linhas em SUBGRADE.** Eram grades separadas com a mesma
// receita, e a coluna de ações é `auto`: vazia no cabeçalho (zero) e com os botões nas linhas
// (~250px). As frações saíam diferentes e "Quantidade" ficava 100px fora do número (24/11/2026).
const TRILHOS = "md:grid md:grid-cols-[1.75rem_minmax(0,2fr)_minmax(0,0.8fr)_minmax(8.5rem,1fr)_minmax(0,1.1fr)_minmax(9.5rem,1.1fr)_auto] md:gap-x-3";
const LINHA = "md:col-span-full md:grid md:grid-cols-subgrid md:items-center";

export default function PaginaOrdemDeCompra() {
  const { pode, eu, unidade } = useSessao();
  const aviso = useAviso();
  const podeComprar = pode("compras.ordem_comprar");
  const podePedir = pode("compras.ordem_solicitar");
  const [aba, setAba] = useEstadoNaUrl<string>("aba", "A_COMPRAR", { atraso: 0 });
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [de, setDe] = useEstadoNaUrl<string>("de", "", { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", "", { atraso: 0 });
  // 🔑 Na URL para o painel de estoque e os alertas abrirem direto nas sugestões (etapa 2).
  const [sugestoes, setSugestoes] = useEstadoNaUrl<boolean>("sugestoes", false);
  const abaAtual: AbaOrdem = aba === "COMPRADO" ? "COMPRADO" : "A_COMPRAR";
  const [lista, setLista] = useState<OrdemItem[] | null>(null);
  const [aComprar, setAComprar] = useState<number | null>(null);
  const [erro, setErro] = useState("");
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  const [comprando, setComprando] = useState<OrdemItem[] | null>(null);
  const [corrigindo, setCorrigindo] = useState<OrdemItem | null>(null);
  const [cancelando, setCancelando] = useState<OrdemItem | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const pag = usePaginacao("ordens-compra", { filtros: [abaAtual, busca, de, ate, unidade] });

  // ⚠️ A lista de uma aba não pode aparecer sob os botões da outra: "Voltar à lista" num item
  // que ainda está em A comprar. Limpa ao trocar, e resposta atrasada não sobrescreve a nova.
  const ultimoPedido = useRef(0);
  useEffect(() => { setLista(null); }, [abaAtual, unidade]);

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    const pedido = ++ultimoPedido.current;
    setErro("");
    try {
      const q: Record<string, string> = { ...pag.parametros };
      if (busca.trim()) q.busca = busca.trim();
      if (abaAtual === "COMPRADO" && de) q.de = de;
      if (abaAtual === "COMPRADO" && ate) q.ate = ate;
      const [l, r] = await Promise.all([listarOrdens(abaAtual, q), resumoOrdens()]);
      if (pedido !== ultimoPedido.current) return;
      setLista(l.itens);
      if (l.total !== null) pag.setTotal(l.total);
      setAComprar(r.a_comprar);
      setMarcados(new Set());
    } catch (e) {
      if (pedido !== ultimoPedido.current) return;
      setLista([]);
      setErro(e instanceof Error ? e.message : "Falha ao carregar a lista");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, abaAtual, busca, de, ate, unidade, pag.offset, pag.porPagina]);

  useEffect(() => { void carregar(); }, [carregar]);

  async function voltar(ids: number[]) {
    setOcupado(true);
    try {
      const r = await voltarParaLista(ids);
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível voltar à lista");
    } finally {
      setOcupado(false);
    }
  }

  async function cancelar() {
    if (!cancelando) return;
    setOcupado(true);
    try {
      const r = await cancelarItem(cancelando.id);
      aviso.sucesso(r.message);
      setCancelando(null);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível cancelar");
    } finally {
      setOcupado(false);
    }
  }

  const alternar = (id: number) => setMarcados((m) => {
    const novo = new Set(m);
    if (novo.has(id)) novo.delete(id); else novo.add(id);
    return novo;
  });
  const podeMexer = (i: OrdemItem) => podeComprar || i.criado_por === eu?.id;
  const selecionados = (lista ?? []).filter((i) => marcados.has(i.id));
  const comCaixinha = abaAtual === "A_COMPRAR" && podeComprar;

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Compras › Ordem de compra"
        titulo="Pedir insumo para compra"
        acoes={
          <div className="flex flex-wrap gap-2">
            {podePedir && (
              <button type="button" className="btn btn-secundario" id="ordem-abrir-sugestoes"
                      onClick={() => setSugestoes(true)}>
                Abaixo do mínimo
              </button>
            )}
            <BotaoExportar relatorio="ordens-compra" rotulo="Imprimir lista"
                           iniciais={{ situacao_ordem: [abaAtual] }} />
          </div>
        }
      >
        {/* 🔑 Aberta, e não atrás de "saber mais" (o padrão de 15/09): é a tela que a equipe
            inteira usa, e o modelo do dono a mostra à vista. */}
        <p className="prosa mt-2 max-w-[38rem] text-[15px] text-suave" id="ordem-explica">
          Acabou ou está acabando alguma coisa? Peça aqui. Quem compra recebe seu pedido, compra e
          marca como <strong className="text-tinta">comprado</strong>: você acompanha tudo nesta
          tela. Marcar não mexe no estoque; a mercadoria entra quando a nota é lançada.
        </p>
      </CabecalhoTela>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {podePedir && (
        // ⚠️ No celular, duas colunas e só o título: com o texto, os passos tomavam meia tela
        // antes do formulário.
        <ol className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4" id="ordem-passos">
          {PASSOS.map((p, n) => (
            <li key={p.titulo} className="cartao flex items-start gap-2 p-3 sm:gap-3 sm:p-4">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-erva text-[13px] font-bold text-white">
                {n + 1}
              </span>
              <div>
                <p className="text-[13px] font-semibold leading-snug sm:text-[14px]">{p.titulo}</p>
                <p className="hidden text-[12.5px] leading-snug text-suave sm:block">{p.texto}</p>
              </div>
            </li>
          ))}
        </ol>
      )}

      {abaAtual === "A_COMPRAR" && podePedir && (
        <section className="cartao p-5"><FormPedido aoPedir={() => void carregar()} /></section>
      )}

      <section className="cartao p-5">
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" id="ordem-aba-comprar" onClick={() => setAba("A_COMPRAR")}
                  className={abaAtual === "A_COMPRAR" ? "btn btn-primario" : "btn btn-secundario"}>
            A comprar{aComprar !== null ? ` (${aComprar})` : ""}
          </button>
          <button type="button" id="ordem-aba-comprados" onClick={() => setAba("COMPRADO")}
                  className={abaAtual === "COMPRADO" ? "btn btn-primario" : "btn btn-secundario"}>
            Comprados
          </button>
          {/* ⚠️ A largura vai no invólucro: `.campo` tem `width: 100%` fora das camadas e
              ganha de qualquer utilitário posto no próprio campo. */}
          <div className="w-full sm:ml-auto sm:w-64">
            <input className="campo py-1.5" id="ordem-busca"
                   placeholder="Buscar na lista…" aria-label="buscar na lista" value={busca}
                   onChange={(e) => setBusca(e.target.value)} />
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2 text-[13.5px]">
          <p className="text-suave">
            {abaAtual === "A_COMPRAR"
              ? "Pedidos esperando compra, os mais urgentes primeiro."
              : "O que já foi comprado, o mais recente primeiro."}
          </p>
          {abaAtual === "COMPRADO" && (
            <span className="flex flex-wrap items-center gap-1.5 sm:ml-auto">
              <span className="text-suave">de</span>
              <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="comprado de"
                     value={de} max={ate || undefined} onChange={(e) => setDe(e.target.value)} />
              <span className="text-suave">até</span>
              <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="comprado até"
                     value={ate} min={de || undefined} onChange={(e) => setAte(e.target.value)} />
            </span>
          )}
          {comCaixinha && selecionados.length > 0 && (
            <button type="button" className="btn btn-primario sm:ml-auto" id="ordem-comprar-selecionados"
                    onClick={() => setComprando(selecionados)}>
              Marcar {selecionados.length} como comprado
            </button>
          )}
        </div>

        {!lista ? (
          <div className="mt-4"><Carregando /></div>
        ) : !lista.length ? (
          <div className="mt-4">
            <Vazio>
              {busca || de || ate
                ? "Nada encontrado com esse filtro."
                : abaAtual === "A_COMPRAR" ? "Nada para comprar agora." : "Nenhum item comprado ainda."}
            </Vazio>
          </div>
        ) : (
          <div className={`mt-3 ${TRILHOS}`}>
            <div className={`hidden border-b border-linha pb-2 text-[12.5px] font-semibold text-suave ${LINHA}`}
                 aria-hidden>
              <span />
              <span>Produto</span>
              <span>Quantidade</span>
              <span>Urgência</span>
              <span>Pedido por</span>
              <span>Situação</span>
              <span />
            </div>
            <ul className={`flex flex-col divide-y divide-[var(--borda)] ${LINHA}`} id="ordem-lista">
              {lista.map((i) => (
                <li key={i.id} data-ordem-item={i.id}
                    className={`flex flex-wrap items-center gap-x-3 gap-y-2 py-3 ${LINHA}`}>
                  <span className="flex md:justify-center">
                    {comCaixinha && (
                      <input type="checkbox" className="h-5 w-5" aria-label={`selecionar ${i.item}`}
                             checked={marcados.has(i.id)} onChange={() => alternar(i.id)} />
                    )}
                  </span>
                  <div className="min-w-[10rem] flex-1">
                    <p className="font-semibold">
                      {i.item}
                      {i.fora_do_cadastro && <span className="ml-2"><Etiqueta>fora do cadastro</Etiqueta></span>}
                    </p>
                    <p className="text-[13px] text-suave">{i.observacao || "—"}</p>
                  </div>
                  <span className="mono w-full md:w-auto">
                    {qtd(i.quantidade)} {i.um}
                    {i.quantidade_pedida && (
                      <span className="block text-[12px] text-suave">pedido: {qtd(i.quantidade_pedida)} {i.um}</span>
                    )}
                  </span>
                  <span><SeloUrgencia urgencia={i.urgencia} /></span>
                  <span className="text-[13.5px]" title={i.pedido_por ?? undefined}>
                    {i.setor_pedido ?? i.pedido_por ?? "—"}
                    <span className="text-suave md:block"><span className="md:hidden"> · </span>{quando(i.criado_em)}</span>
                  </span>
                  <span className="text-[13px]">
                    <SeloSituacao status={i.status} />
                    {i.comprado_em && (
                      <span className="mt-1 block text-[12.5px] text-suave">
                        comprado por {i.comprado_por_nome ?? "—"} · {quando(i.comprado_em)}
                        {i.fornecedor && <> · {i.fornecedor}</>}
                      </span>
                    )}
                  </span>
                  {/* Comprei em destaque; corrigir e cancelar, que são raros, sem peso. */}
                  <div className="flex w-full flex-wrap items-center gap-1 md:w-auto md:justify-end">
                    {abaAtual === "A_COMPRAR" ? (
                      <>
                        {podeComprar && (
                          <button type="button" className="btn btn-secundario btn-pequeno" data-acao="comprei"
                                  onClick={() => setComprando([i])}>Comprei</button>
                        )}
                        {podeMexer(i) && (
                          <>
                            <button type="button" className="btn btn-terciario btn-pequeno" data-acao="corrigir"
                                    onClick={() => setCorrigindo(i)}>Corrigir</button>
                            <button type="button" className="btn btn-terciario btn-pequeno" data-acao="cancelar"
                                    onClick={() => setCancelando(i)}>Cancelar</button>
                          </>
                        )}
                      </>
                    ) : podeComprar && (
                      <button type="button" className="btn btn-secundario btn-pequeno" data-acao="voltar"
                              disabled={ocupado} onClick={() => void voltar([i.id])}>Voltar à lista</button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        <Paginacao p={pag} rotulo="itens" />
      </section>

      {sugestoes && podePedir && (
        <JanelaSugestoes aoFechar={() => setSugestoes(false)}
                         aoPor={(m) => {
                           setSugestoes(false);
                           aviso.sucesso(m);
                           if (abaAtual !== "A_COMPRAR") setAba("A_COMPRAR");
                           else void carregar();
                         }} />
      )}
      {comprando && (
        <JanelaComprar itens={comprando} aoFechar={() => setComprando(null)}
                       aoComprar={(ids, mensagem) => {
                         setComprando(null);
                         aviso.sucesso(mensagem, { texto: "desfazer", ao: () => void voltar(ids) });
                         void carregar();
                       }} />
      )}
      {corrigindo && (
        <JanelaCorrigir item={corrigindo} aoFechar={() => setCorrigindo(null)}
                        aoSalvar={(m) => { setCorrigindo(null); aviso.sucesso(m); void carregar(); }} />
      )}
      {cancelando && (
        <Confirmacao titulo="Cancelar este pedido?" rotuloConfirmar="Cancelar pedido"
                     rotuloCancelar="Manter" perigo ocupado={ocupado}
                     aoConfirmar={() => void cancelar()} aoCancelar={() => setCancelando(null)}>
          {cancelando.item}, {qtd(cancelando.quantidade)} {cancelando.um}, sai da lista.
        </Confirmacao>
      )}
    </div>
  );
}
