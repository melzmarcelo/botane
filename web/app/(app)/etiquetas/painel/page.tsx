"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Cartao } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import {
  EVENTOS, imprimir, listar, painel, usar, type Etiqueta, type PainelEtiquetas,
} from "@/lib/etiquetas";
import { useSessao } from "@/lib/sessao";

import Descarte from "../descarte";
import UsoParcial from "../uso-parcial";
import TabelaDeEtiquetas from "./tabela";

/**
 * Etiquetas → Painel de validades: a checagem da manhã.
 *
 * 🔑 O que venceu, o que vence hoje e amanhã — por local, sem abrir a câmara fria.
 * Cada linha tem as mesmas ações do QR: usei tudo, descartar (perda), reimprimir.
 */
const SITUACOES = [
  { v: "vencidas", r: "Vencidas" },
  { v: "hoje", r: "Vencem hoje" },
  { v: "amanha", r: "Vencem amanhã" },
  { v: "ativas", r: "Todas as ativas" },
  { v: "baixadas", r: "Baixadas" },
];

export default function PainelDeValidades() {
  const aviso = useAviso();
  const router = useRouter();
  const { pode } = useSessao();
  const [situacao, setSituacao] = useEstadoNaUrl<string>("situacao", "ativas");
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [evento, setEvento] = useEstadoNaUrl<string>("evento", "");
  const [codigo, setCodigo] = useState("");
  const [lista, setLista] = useState<Etiqueta[] | null>(null);
  const [numeros, setNumeros] = useState<PainelEtiquetas | null>(null);
  const [erro, setErro] = useState("");
  const [descartando, setDescartando] = useState<Etiqueta | null>(null);
  const [usandoParte, setUsandoParte] = useState<Etiqueta | null>(null);
  const pag = usePaginacao("etiquetas-painel", { filtros: [situacao, busca, evento] });

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    try {
      const [r, n] = await Promise.all([listar(pag.parametros, { situacao, busca, evento }), painel()]);
      setLista(r.itens);
      pag.setTotal(r.total);
      setNumeros(n);
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar as etiquetas");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, situacao, busca, evento, pag.offset, pag.porPagina]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  async function usarTudo(e: Etiqueta) {
    try {
      const r = await usar(e.id);
      aviso.sucesso(r.message);
      void carregar();
    } catch (x) {
      aviso.erro(x instanceof Error ? x.message : "Não foi possível dar baixa");
    }
  }

  const cartoes = numeros ? [
    { v: "vencidas", n: numeros.vencidas, r: "vencidas", alerta: true },
    { v: "hoje", n: numeros.hoje, r: "vencem hoje", alerta: true },
    { v: "amanha", n: numeros.amanha, r: "vencem amanhã" },
    { v: "ativas", n: numeros.ativas, r: "ativas" },
  ] : [];

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Etiquetas"
        titulo="Painel de validades"
        explica="O que venceu, o que vence hoje e amanhã. Dê baixa no que foi usado e descarte o que passou — o descarte lança a perda no estoque, com o valor."
        acoes={<Link href="/etiquetas" className="btn btn-primario">Imprimir etiquetas</Link>}
      />
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {numeros && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {cartoes.map((x) => (
            <button key={x.v} type="button" onClick={() => setSituacao(x.v)}
                    className={`cartao px-3 py-3 text-left hover:border-[var(--color-erva)] ${
                      situacao === x.v ? "ring-1 ring-[var(--color-erva)]" : ""}`}>
              <b className={`mono block text-[24px] leading-none ${
                x.alerta && x.n > 0 ? "text-[var(--color-alerta)]" : ""}`}>{x.n}</b>
              <span className="text-[12px] text-suave">{x.r}</span>
            </button>
          ))}
          <div className="cartao px-3 py-3">
            <b className="mono block text-[24px] leading-none">
              {numeros.valor_descartado_30d.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
            </b>
            <span className="text-[12px] text-suave">descartado em 30 dias ({numeros.descartadas_30d})</span>
          </div>
        </div>
      )}

      <Cartao>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <form className="flex items-end gap-2" onSubmit={(e) => {
            e.preventDefault();
            if (codigo.trim()) router.push(`/etiquetas/e/${codigo.trim().toUpperCase()}`);
          }}>
            <label>
              <span className="rotulo-campo">Código da etiqueta</span>
              <input className="campo mono mt-1.5 w-[130px] uppercase" maxLength={10} value={codigo}
                     placeholder="ex.: Q9682B" onChange={(e) => setCodigo(e.target.value)} />
            </label>
            <button className="btn btn-secundario">Abrir</button>
          </form>
          <label className="min-w-0 flex-1">
            <span className="rotulo-campo">Buscar</span>
            <input className="campo mt-1.5" placeholder="produto, código ou lote" value={busca}
                   onChange={(e) => setBusca(e.target.value)} />
          </label>
          <label>
            <span className="rotulo-campo">Evento</span>
            <select className="campo mt-1.5" value={evento} onChange={(e) => setEvento(e.target.value)}>
              <option value="">todos</option>
              {EVENTOS.map((x) => <option key={x.v} value={x.v}>{x.r}</option>)}
            </select>
          </label>
        </div>
        <div className="mt-3 flex flex-wrap gap-1" role="tablist" aria-label="situação">
          {SITUACOES.map((x) => (
            <button key={x.v} type="button" role="tab" aria-selected={situacao === x.v}
                    className={`btn px-3 py-1.5 text-[13px] ${situacao === x.v ? "btn-primario" : "btn-secundario"}`}
                    onClick={() => setSituacao(x.v)}>
              {x.r}
            </button>
          ))}
        </div>
      </Cartao>

      <Cartao>
        <TabelaDeEtiquetas
          lista={lista}
          podeDescartar={pode("etiquetas.descartar")}
          aoUsar={(e) => void usarTudo(e)}
          aoUsarParte={setUsandoParte}
          aoDescartar={setDescartando}
          aoReimprimir={(e) => void imprimir([e.id], true).catch(
            (x) => aviso.erro(x instanceof Error ? x.message : "Falha ao imprimir"))}
        />
        <Paginacao p={pag} rotulo="etiqueta(s)" />
      </Cartao>

      {usandoParte && (
        <UsoParcial etiqueta={usandoParte} aoFechar={() => setUsandoParte(null)}
                    aoConcluir={() => { setUsandoParte(null); void carregar(); }} />
      )}
      {descartando && (
        <Descarte etiqueta={descartando} aoFechar={() => setDescartando(null)}
                  aoConcluir={() => { setDescartando(null); void carregar(); }} />
      )}
    </div>
  );
}
