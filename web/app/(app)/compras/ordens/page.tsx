"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
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

/**
 * A ordem de compra: o que falta comprar e o que já foi.
 *
 * 🔑 **Cada linha anda sozinha.** Comprou, sai de "A comprar" e entra em "Comprados".
 * 🔑 **Comprado não é recebido**: nada aqui mexe no estoque. Por isso desfazer é um clique.
 * ⚠️ Em cartões e não em tabela: quem marca costuma estar no mercado, com o celular.
 */

const quando = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });

export default function PaginaOrdemDeCompra() {
  const { pode, eu, unidade } = useSessao();
  const aviso = useAviso();
  const podeComprar = pode("compras.ordem_comprar");
  const podePedir = pode("compras.ordem_solicitar");
  const [aba, setAba] = useEstadoNaUrl<string>("aba", "A_COMPRAR", { atraso: 0 });
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [de, setDe] = useEstadoNaUrl<string>("de", "", { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", "", { atraso: 0 });
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

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Compras"
        titulo="Ordem de compra"
        explica={<>O que precisa ser comprado e o que já foi. Marcar como comprado
          <strong> não mexe no estoque</strong>: a mercadoria entra quando a nota é lançada.</>}
        acoes={<BotaoExportar relatorio="ordens-compra" iniciais={{ situacao_ordem: [abaAtual] }} />}
      />

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className="flex flex-wrap gap-2">
        <button type="button" id="ordem-aba-comprar" onClick={() => setAba("A_COMPRAR")}
                className={abaAtual === "A_COMPRAR" ? "btn btn-primario" : "btn"}>
          A comprar{aComprar !== null ? ` (${aComprar})` : ""}
        </button>
        <button type="button" id="ordem-aba-comprados" onClick={() => setAba("COMPRADO")}
                className={abaAtual === "COMPRADO" ? "btn btn-primario" : "btn"}>
          Comprados
        </button>
      </div>

      {abaAtual === "A_COMPRAR" && podePedir && (
        <Cartao><FormPedido aoPedir={() => void carregar()} /></Cartao>
      )}

      <Cartao>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-[13.5px]">
          <input className="campo py-1" style={{ width: "auto" }} id="ordem-busca"
                 placeholder="buscar item" aria-label="buscar item" value={busca}
                 onChange={(e) => setBusca(e.target.value)} />
          {abaAtual === "COMPRADO" && (
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="text-suave">de</span>
              <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="comprado de"
                     value={de} max={ate || undefined} onChange={(e) => setDe(e.target.value)} />
              <span className="text-suave">até</span>
              <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="comprado até"
                     value={ate} min={de || undefined} onChange={(e) => setAte(e.target.value)} />
            </span>
          )}
          {abaAtual === "A_COMPRAR" && podeComprar && selecionados.length > 0 && (
            <button type="button" className="btn btn-primario ml-auto" id="ordem-comprar-selecionados"
                    onClick={() => setComprando(selecionados)}>
              Marcar {selecionados.length} como comprado
            </button>
          )}
        </div>

        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>
            {busca || de || ate
              ? "Nada encontrado com esse filtro."
              : abaAtual === "A_COMPRAR" ? "Nada para comprar agora." : "Nenhum item comprado ainda."}
          </Vazio>
        ) : (
          <ul className="flex flex-col divide-y divide-[var(--borda)]" id="ordem-lista">
            {lista.map((i) => (
              <li key={i.id} data-ordem-item={i.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3">
                {abaAtual === "A_COMPRAR" && podeComprar && (
                  <input type="checkbox" className="h-5 w-5" aria-label={`selecionar ${i.item}`}
                         checked={marcados.has(i.id)} onChange={() => alternar(i.id)} />
                )}
                <div className="min-w-[12rem] flex-1">
                  <p className="font-semibold">
                    {i.item}{" "}
                    <span className="mono font-normal">{qtd(i.quantidade)} {i.um}</span>
                    {i.fora_do_cadastro && <span className="ml-2"><Etiqueta>fora do cadastro</Etiqueta></span>}
                  </p>
                  {i.observacao && <p className="text-[13.5px]">{i.observacao}</p>}
                  <p className="text-[12.5px] text-suave">
                    {i.pedido_por ?? "—"} · {quando(i.criado_em)}
                    {i.comprado_em && <> · comprado por {i.comprado_por_nome ?? "—"} em {quando(i.comprado_em)}</>}
                    {i.fornecedor && <> · {i.fornecedor}</>}
                    {i.quantidade_pedida && <> · pedido: {qtd(i.quantidade_pedida)} {i.um}</>}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  {abaAtual === "A_COMPRAR" ? (
                    <>
                      {podeComprar && (
                        <button type="button" className="btn btn-secundario" data-acao="comprei"
                                onClick={() => setComprando([i])}>Comprei</button>
                      )}
                      {podeMexer(i) && (
                        <>
                          <button type="button" className="btn" data-acao="corrigir"
                                  onClick={() => setCorrigindo(i)}>Corrigir</button>
                          <button type="button" className="btn" data-acao="cancelar"
                                  onClick={() => setCancelando(i)}>Cancelar</button>
                        </>
                      )}
                    </>
                  ) : podeComprar && (
                    <button type="button" className="btn" data-acao="voltar" disabled={ocupado}
                            onClick={() => void voltar([i.id])}>Voltar à lista</button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
        <Paginacao p={pag} rotulo="itens" />
      </Cartao>

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
