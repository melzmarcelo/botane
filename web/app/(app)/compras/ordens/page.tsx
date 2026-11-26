"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Campo, Carregando, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { qtd } from "@/lib/numeros";
import {
  AbaOrdem,
  ABAS_ORDEM,
  aprovarPedidos,
  cancelarItem,
  listarOrdens,
  OrdemItem,
  recusarPedidos,
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
 * 🔑 **Aprovação** (migração 165, pedido do dono de 25/11/2026): o pedido de quem não tem
 * `compras.ordem_aprovar` espera em "Aguardando aprovação"; aprovado, vai para "A comprar";
 * recusado, para "Recusados", com o motivo. O pedido de quem aprova já nasce aprovado.
 * ⚠️ As colunas só existem do `md` para cima: no celular (quem marca costuma estar no mercado)
 * cada linha volta a ser um cartão, com os mesmos elementos.
 * 🔑 **Fornecedor** (26/11/2026, pedido do dono): nas abas abertas, o fornecedor PRINCIPAL do
 * produto; em Comprados, o fornecedor DA COMPRA. "Agrupar por fornecedor" ordena no banco por
 * ele e põe um cabeçalho por grupo, com "selecionar" para marcar o grupo inteiro de uma vez —
 * e a janela de comprar já sugere o fornecedor quando todos têm o mesmo principal.
 */

const PASSOS = [
  { titulo: "Escolha o produto", texto: "Digite o nome ou o código e escolha da lista." },
  { titulo: "Diga quanto precisa", texto: "Quantidade e unidade (kg, L, un, cx…)." },
  { titulo: "Marque a urgência", texto: "Ajuda a priorizar o que comprar primeiro." },
  { titulo: "Acompanhe", texto: "Seu pedido é aprovado, vai para “A comprar” e depois para “Comprados”." },
];

const ROTULO_ABA: Record<AbaOrdem, string> = {
  AGUARDANDO: "Aguardando aprovação",
  A_COMPRAR: "A comprar",
  COMPRADO: "Comprados",
  RECUSADO: "Recusados",
};

const ID_ABA: Record<AbaOrdem, string> = {
  AGUARDANDO: "ordem-aba-aguardando",
  A_COMPRAR: "ordem-aba-comprar",
  COMPRADO: "ordem-aba-comprados",
  RECUSADO: "ordem-aba-recusados",
};

const FRASE_ABA: Record<AbaOrdem, string> = {
  AGUARDANDO: "Pedidos esperando aprovação, os mais urgentes primeiro. Aprovado, vai para quem compra.",
  A_COMPRAR: "Pedidos aprovados esperando compra, os mais urgentes primeiro.",
  COMPRADO: "O que já foi comprado, o mais recente primeiro.",
  RECUSADO: "Pedidos recusados, com o motivo, o mais recente primeiro.",
};

const VAZIO_ABA: Record<AbaOrdem, string> = {
  AGUARDANDO: "Nenhum pedido aguardando aprovação.",
  A_COMPRAR: "Nada para comprar agora.",
  COMPRADO: "Nenhum item comprado ainda.",
  RECUSADO: "Nenhum pedido recusado.",
};

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

// Produto · Quantidade · Urgência · Pedido por · Fornecedor · Situação · ações (e a caixinha).
// ⚠️ **Uma grade só, e cabeçalho e linhas em SUBGRADE.** Eram grades separadas com a mesma
// receita, e a coluna de ações é `auto`: vazia no cabeçalho (zero) e com os botões nas linhas
// (~250px). As frações saíam diferentes e "Quantidade" ficava 100px fora do número (24/11/2026).
const TRILHOS = "md:grid md:grid-cols-[1.75rem_minmax(0,1.7fr)_minmax(4.75rem,0.7fr)_minmax(7.75rem,0.9fr)_minmax(0,1fr)_minmax(0,1.35fr)_minmax(8.75rem,1fr)_auto] md:gap-x-3";
const LINHA = "md:col-span-full md:grid md:grid-cols-subgrid md:items-center";

export default function PaginaOrdemDeCompra() {
  const { pode, eu, unidade } = useSessao();
  const aviso = useAviso();
  const podeComprar = pode("compras.ordem_comprar");
  const podePedir = pode("compras.ordem_solicitar");
  const podeAprovar = pode("compras.ordem_aprovar");
  // 🔑 Sem ver todos (166), a lista, as contagens e o relatório trazem só os próprios pedidos.
  const veTodos = podeComprar || podeAprovar || pode("compras.ordem_ver_todos");
  const [aba, setAba] = useEstadoNaUrl<string>("aba", "A_COMPRAR", { atraso: 0 });
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [de, setDe] = useEstadoNaUrl<string>("de", "", { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", "", { atraso: 0 });
  // 🔑 Na URL para o painel de estoque e os alertas abrirem direto nas sugestões (etapa 2).
  const [sugestoes, setSugestoes] = useEstadoNaUrl<boolean>("sugestoes", false);
  const [agrupar, setAgrupar] = useEstadoNaUrl<boolean>("agrupar", false, { atraso: 0 });
  const abaAtual: AbaOrdem = (ABAS_ORDEM as string[]).includes(aba) ? (aba as AbaOrdem) : "A_COMPRAR";
  const comData = abaAtual === "COMPRADO" || abaAtual === "RECUSADO";
  const [lista, setLista] = useState<OrdemItem[] | null>(null);
  const [contagem, setContagem] = useState<{ a_comprar: number; aguardando: number } | null>(null);
  const [recusando, setRecusando] = useState<OrdemItem[] | null>(null);
  const [motivo, setMotivo] = useState("");
  const [erro, setErro] = useState("");
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  const [comprando, setComprando] = useState<OrdemItem[] | null>(null);
  const [corrigindo, setCorrigindo] = useState<OrdemItem | null>(null);
  const [cancelando, setCancelando] = useState<OrdemItem | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const pag = usePaginacao("ordens-compra", { filtros: [abaAtual, busca, de, ate, unidade, agrupar] });

  // ⚠️ A lista de uma aba não pode aparecer sob os botões da outra: "Voltar à lista" num item
  // que ainda está em A comprar. Limpa ao trocar, e resposta atrasada não sobrescreve a nova.
  const ultimoPedido = useRef(0);
  // ⚠️ Agrupar também: os cabeçalhos apareciam sobre a lista VELHA, e o "Selecionar o grupo"
  // clicado nesse meio-tempo sumia quando a lista agrupada chegava (ela zera as marcações).
  useEffect(() => { setLista(null); }, [abaAtual, unidade, agrupar]);

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    const pedido = ++ultimoPedido.current;
    setErro("");
    try {
      const q: Record<string, string> = { ...pag.parametros };
      if (busca.trim()) q.busca = busca.trim();
      if (comData && de) q.de = de;
      if (comData && ate) q.ate = ate;
      if (agrupar) q.agrupar_fornecedor = "true";
      const [l, r] = await Promise.all([listarOrdens(abaAtual, q), resumoOrdens()]);
      if (pedido !== ultimoPedido.current) return;
      setLista(l.itens);
      if (l.total !== null) pag.setTotal(l.total);
      setContagem(r);
      // ⚠️ Fica marcado o que continua na lista, e não "zera tudo": o agrupar recarrega mais de
      // uma vez (estado, URL, paginação), e o "Selecionar o grupo" clicado entre uma e outra
      // sumia. O que saiu (comprado, aprovado, cancelado) sai da seleção sozinho.
      setMarcados((m) => new Set(l.itens.filter((i) => m.has(i.id)).map((i) => i.id)));
    } catch (e) {
      if (pedido !== ultimoPedido.current) return;
      setLista([]);
      setErro(e instanceof Error ? e.message : "Falha ao carregar a lista");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, abaAtual, comData, busca, de, ate, agrupar, unidade, pag.offset, pag.porPagina]);

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

  async function aprovar(ids: number[]) {
    setOcupado(true);
    try {
      const r = await aprovarPedidos(ids);
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível aprovar");
    } finally {
      setOcupado(false);
    }
  }

  async function recusar() {
    if (!recusando) return;
    setOcupado(true);
    try {
      const r = await recusarPedidos(recusando.map((i) => i.id), motivo.trim() || null);
      aviso.sucesso(r.message);
      setRecusando(null);
      setMotivo("");
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível recusar");
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
  // ⚠️ Aprovado pelo gestor, quem só pediu não corrige nem cancela (166; a API recusa). Linha de
  // antes da aprovação existir (`aprovado_por` nulo) segue como era.
  const podeMexer = (i: OrdemItem) => podeComprar || podeAprovar ||
    (i.criado_por === eu?.id && (i.status === "AGUARDANDO" || !i.aprovado_por));
  const selecionados = (lista ?? []).filter((i) => marcados.has(i.id));
  const comCaixinha = (abaAtual === "A_COMPRAR" && podeComprar) ||
    (abaAtual === "AGUARDANDO" && podeAprovar);
  const aberta = abaAtual === "A_COMPRAR" || abaAtual === "AGUARDANDO";
  // Em Comprados, de quem se comprou; nas outras abas, o principal do produto.
  const fornecedorDe = (i: OrdemItem) =>
    abaAtual === "COMPRADO" ? i.fornecedor : i.fornecedor_principal;
  const grupos = new Map<string, number[]>();
  for (const i of lista ?? []) {
    const chave = fornecedorDe(i) ?? "";
    grupos.set(chave, [...(grupos.get(chave) ?? []), i.id]);
  }
  const marcarGrupo = (ids: number[]) => setMarcados((m) => {
    const todos = ids.every((id) => m.has(id));
    const novo = new Set(m);
    for (const id of ids) if (todos) novo.delete(id); else novo.add(id);
    return novo;
  });

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
          Acabou ou está acabando alguma coisa? Peça aqui. O pedido passa pela{" "}
          <strong className="text-tinta">aprovação</strong>; aprovado, quem compra recebe, compra e
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

      {aberta && podePedir && (
        <section className="cartao p-5">
          <FormPedido podeAprovar={podeAprovar}
                      aoPedir={(status) => {
                        // O pedido que foi para aprovação aparece onde ele está.
                        if (status && status !== abaAtual) setAba(status);
                        else void carregar();
                      }} />
        </section>
      )}

      <section className="cartao p-5">
        <div className="flex flex-wrap items-center gap-2">
          {ABAS_ORDEM.map((a) => {
            const n = a === "AGUARDANDO" ? contagem?.aguardando : a === "A_COMPRAR" ? contagem?.a_comprar : null;
            return (
              <button key={a} type="button" id={ID_ABA[a]} onClick={() => setAba(a)}
                      className={abaAtual === a ? "btn btn-primario" : "btn btn-secundario"}>
                {ROTULO_ABA[a]}{n != null ? ` (${n})` : ""}
              </button>
            );
          })}
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
            {FRASE_ABA[abaAtual]}
            {!veTodos && <span id="ordem-so-meus"> Você vê só os seus pedidos.</span>}
          </p>
          {comData && (
            <span className="flex flex-wrap items-center gap-1.5 sm:ml-auto">
              <span className="text-suave">de</span>
              <input type="date" className="campo py-1" style={{ width: "auto" }}
                     aria-label={abaAtual === "RECUSADO" ? "recusado de" : "comprado de"}
                     value={de} max={ate || undefined} onChange={(e) => setDe(e.target.value)} />
              <span className="text-suave">até</span>
              <input type="date" className="campo py-1" style={{ width: "auto" }}
                     aria-label={abaAtual === "RECUSADO" ? "recusado até" : "comprado até"}
                     value={ate} min={de || undefined} onChange={(e) => setAte(e.target.value)} />
            </span>
          )}
          <label className="flex items-center gap-1.5 sm:ml-auto" htmlFor="ordem-agrupar">
            <input type="checkbox" id="ordem-agrupar" className="h-4 w-4" checked={agrupar}
                   onChange={(e) => setAgrupar(e.target.checked)} />
            Agrupar por fornecedor
          </label>
          {comCaixinha && selecionados.length > 0 && abaAtual === "A_COMPRAR" && (
            <button type="button" className="btn btn-primario sm:ml-auto" id="ordem-comprar-selecionados"
                    onClick={() => setComprando(selecionados)}>
              Marcar {selecionados.length} como comprado
            </button>
          )}
          {comCaixinha && selecionados.length > 0 && abaAtual === "AGUARDANDO" && (
            <span className="flex flex-wrap gap-2 sm:ml-auto">
              <button type="button" className="btn btn-secundario" id="ordem-recusar-selecionados"
                      disabled={ocupado} onClick={() => setRecusando(selecionados)}>
                Recusar {selecionados.length}
              </button>
              <button type="button" className="btn btn-primario" id="ordem-aprovar-selecionados"
                      disabled={ocupado} onClick={() => void aprovar(selecionados.map((i) => i.id))}>
                Aprovar {selecionados.length}
              </button>
            </span>
          )}
        </div>

        {!lista ? (
          <div className="mt-4"><Carregando /></div>
        ) : !lista.length ? (
          <div className="mt-4">
            <Vazio>
              {busca || de || ate
                ? "Nada encontrado com esse filtro."
                : VAZIO_ABA[abaAtual]}
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
              <span title={abaAtual === "COMPRADO" ? undefined : "o fornecedor principal do produto"}>
                {abaAtual === "COMPRADO" ? "Comprado de" : "Fornecedor"}
              </span>
              <span>Situação</span>
              <span />
            </div>
            <ul className={`flex flex-col divide-y divide-[var(--borda)] ${LINHA}`} id="ordem-lista">
              {lista.map((i, n) => {
                const chave = fornecedorDe(i) ?? "";
                const novoGrupo = agrupar && (n === 0 || (fornecedorDe(lista[n - 1]) ?? "") !== chave);
                const doGrupo = grupos.get(chave) ?? [];
                return (
                <Fragment key={i.id}>
                {novoGrupo && (
                  <li data-ordem-grupo={chave || "sem"}
                      className={`flex flex-wrap items-center gap-2 bg-superficie2 px-2 py-2 text-[13.5px] ${LINHA}`}>
                    <span className="font-semibold md:col-span-6">
                      {chave || (abaAtual === "COMPRADO" ? "Sem fornecedor informado" : "Sem fornecedor principal")}
                      <span className="ml-1.5 font-normal text-suave">
                        · {doGrupo.length} {doGrupo.length === 1 ? "item" : "itens"}
                      </span>
                    </span>
                    {comCaixinha && (
                      <span className="md:col-span-2 md:justify-self-end">
                        <button type="button" className="btn btn-terciario btn-pequeno" data-acao="selecionar-grupo"
                                onClick={() => marcarGrupo(doGrupo)}>
                          {doGrupo.every((id) => marcados.has(id)) ? "Desmarcar o grupo" : "Selecionar o grupo"}
                        </button>
                      </span>
                    )}
                  </li>
                )}
                <li data-ordem-item={i.id}
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
                  <span className="min-w-0 text-[13.5px]" title={i.pedido_por ?? undefined}>
                    {/* Nome comprido corta com reticências (o inteiro fica no title), e não no meio. */}
                    <span className="md:block md:truncate">{i.setor_pedido ?? i.pedido_por ?? "—"}</span>
                    <span className="text-suave md:block"><span className="md:hidden"> · </span>{quando(i.criado_em)}</span>
                  </span>
                  {/* ⚠️ Duas linhas no máximo: nome de distribuidora é comprido e empurrava a linha. */}
                  <span className="text-[13.5px] md:line-clamp-2" data-fornecedor title={fornecedorDe(i) ?? undefined}>
                    <span className="text-suave md:hidden">{abaAtual === "COMPRADO" ? "Comprado de " : "Fornecedor: "}</span>
                    {fornecedorDe(i) ?? "—"}
                  </span>
                  <span className="text-[13px]">
                    <SeloSituacao status={i.status} />
                    {i.comprado_em ? (
                      <span className="mt-1 block text-[12.5px] text-suave">
                        comprado por {i.comprado_por_nome ?? "—"} · {quando(i.comprado_em)}
                      </span>
                    ) : i.status === "RECUSADO" ? (
                      <span className="mt-1 block text-[12.5px] text-suave" data-recusa>
                        por {i.recusado_por_nome ?? "—"}
                        {i.recusado_em && <> · {quando(i.recusado_em)}</>}
                        {i.motivo_recusa && <span className="block text-tinta">“{i.motivo_recusa}”</span>}
                      </span>
                    ) : i.status === "A_COMPRAR" && i.aprovado_por_nome && i.aprovado_por !== i.criado_por ? (
                      <span className="mt-1 block text-[12.5px] text-suave" data-aprovado>
                        aprovado por {i.aprovado_por_nome}
                      </span>
                    ) : null}
                  </span>
                  {/* Comprei em destaque; corrigir e cancelar, que são raros, sem peso. */}
                  <div className="flex w-full flex-wrap items-center gap-1 md:w-auto md:justify-end">
                    {aberta ? (
                      <>
                        {abaAtual === "A_COMPRAR" && podeComprar && (
                          <button type="button" className="btn btn-secundario btn-pequeno" data-acao="comprei"
                                  onClick={() => setComprando([i])}>Comprei</button>
                        )}
                        {abaAtual === "AGUARDANDO" && podeAprovar && (
                          <>
                            <button type="button" className="btn btn-secundario btn-pequeno" data-acao="aprovar"
                                    disabled={ocupado} onClick={() => void aprovar([i.id])}>Aprovar</button>
                            <button type="button" className="btn btn-terciario btn-pequeno" data-acao="recusar"
                                    disabled={ocupado} onClick={() => setRecusando([i])}>Recusar</button>
                          </>
                        )}
                        {podeMexer(i) && (
                          <button type="button" className="btn btn-terciario btn-pequeno" data-acao="corrigir"
                                  onClick={() => setCorrigindo(i)}>Corrigir</button>
                        )}
                        {podeMexer(i) && (
                          <button type="button" className="btn btn-terciario btn-pequeno" data-acao="cancelar"
                                  onClick={() => setCancelando(i)}>Cancelar</button>
                        )}
                      </>
                    ) : abaAtual === "COMPRADO" && podeComprar && (
                      <button type="button" className="btn btn-secundario btn-pequeno" data-acao="voltar"
                              disabled={ocupado} onClick={() => void voltar([i.id])}>Voltar à lista</button>
                    )}
                  </div>
                </li>
                </Fragment>
                );
              })}
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
                           const destino: AbaOrdem = podeAprovar ? "A_COMPRAR" : "AGUARDANDO";
                           if (abaAtual !== destino) setAba(destino);
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
      {recusando && (
        <Confirmacao titulo={recusando.length === 1 ? "Recusar este pedido?" : `Recusar ${recusando.length} pedidos?`}
                     rotuloConfirmar="Recusar" rotuloCancelar="Voltar" perigo ocupado={ocupado}
                     aoConfirmar={() => void recusar()}
                     aoCancelar={() => { setRecusando(null); setMotivo(""); }}>
          <p>
            {recusando.length === 1
              ? `${recusando[0].item}, ${qtd(recusando[0].quantidade)} ${recusando[0].um}, não vai para a compra.`
              : "Eles não vão para a compra."}{" "}
            Quem pediu vê a recusa na aba Recusados.
          </p>
          <div className="mt-3">
            <Campo rotulo="Motivo" opcional>
              <textarea className="campo min-h-[4rem]" id="ordem-motivo-recusa" maxLength={300} rows={2}
                        placeholder="Ex.: ainda tem no estoque do freezer 2"
                        value={motivo} onChange={(e) => setMotivo(e.target.value)} />
            </Campo>
          </div>
        </Confirmacao>
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
