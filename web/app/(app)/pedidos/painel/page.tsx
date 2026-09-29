"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso, Carregando, Vazio } from "@/components/ui";
import { confirmar, painel, quando, reais, type Painel, type PedidoResumo } from "@/lib/pedidos";
import { useSessao } from "@/lib/sessao";

import { JanelaDeCupom } from "../[id]/janelas";

/**
 * Pedidos ▸ Painel: a tela que o balcão deixa aberta.
 *
 * 🔑 Três colunas, e são as perguntas da operação (decisões do dono, 28/09/2026):
 * *confirmar* (novos) · *lançar no PDV* (confirmados que ainda não foram) · *o que é para
 * quando* (os confirmados, pela hora). Sem "em preparo/pronto": a cozinha trabalha pelo PDV.
 * ⚠️ Atualiza sozinho a cada 20 s, e toca um aviso quando chega pedido novo.
 */
const INTERVALO = 20_000;

function bip() {
  try {
    const ctx = new AudioContext();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.frequency.value = 880;
    g.gain.value = 0.15;
    o.connect(g).connect(ctx.destination);
    o.start();
    o.stop(ctx.currentTime + 0.35);
  } catch {
    /* sem áudio (aba sem interação ainda): o número na tela continua avisando */
  }
}

function Cartaozinho({ p, agora, children }: { p: PedidoResumo; agora: number; children?: React.ReactNode }) {
  const minutos = Math.round((agora - new Date(p.criado_em).getTime()) / 60000);
  return (
    <div className="cartao flex flex-col gap-1.5 px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <Link href={`/pedidos/${p.id}`} className="link-acao font-semibold">Nº {p.numero} · {p.nome}</Link>
        <span className="mono text-[13px]">{reais(p.total)}</span>
      </div>
      <span className="text-[12.5px] text-suave">
        {p.modo_rotulo} · {quando(p.para_quando)} · {p.itens} item(ns)
        {p.situacao === "NOVO" && <> · há <b className={minutos >= 15 ? "text-[var(--color-alerta)]" : ""}>{minutos} min</b></>}
      </span>
      {children}
    </div>
  );
}

export default function PainelDePedidos() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const [dados, setDados] = useState<Painel | null>(null);
  const [erro, setErro] = useState("");
  const [lancando, setLancando] = useState<PedidoResumo | null>(null);
  const [som, setSom] = useState(true);
  const novosAntes = useRef<number | null>(null);

  const carregar = useCallback(async () => {
    try {
      const d = await painel();
      if (novosAntes.current !== null && d.novos.length > novosAntes.current && som) bip();
      novosAntes.current = d.novos.length;
      setDados(d);
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o painel");
    }
  }, [som]);

  useEffect(() => {
    void carregar();
    const t = setInterval(() => void carregar(), INTERVALO);
    return () => clearInterval(t);
  }, [carregar]);

  async function confirmarRapido(p: PedidoResumo) {
    try {
      const r = await confirmar(p.id);
      aviso.sucesso(r.message);
      void carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível confirmar");
    }
  }

  const agora = dados ? new Date(dados.agora).getTime() : Date.now();
  const operar = pode("pedidos.operar");
  const colunas = dados ? [
    { t: "Novos — confirmar", l: dados.novos, vazio: "Nenhum pedido esperando.",
      acao: (p: PedidoResumo) => operar && (
        <div className="flex gap-3 text-[13px]">
          <button className="link-acao" onClick={() => void confirmarRapido(p)}>confirmar</button>
          <Link className="link-acao" href={`/pedidos/${p.id}`}>trocar / recusar</Link>
        </div>) },
    { t: "Confirmados — lançar no PDV", l: dados.sem_pdv, vazio: "Tudo lançado no PDV.",
      acao: (p: PedidoResumo) => operar && (
        <button className="link-acao self-start text-[13px]" onClick={() => setLancando(p)}>lançado no PDV</button>) },
    { t: "Para quando", l: dados.confirmados, vazio: "Nenhum pedido confirmado em aberto.",
      acao: (p: PedidoResumo) => !p.lancado_pdv_em && <span className="text-[12px] text-[var(--color-alerta)]">falta lançar no PDV</span> },
  ] : [];

  return (
    <div className="flex flex-col gap-5">
      <CabecalhoTela
        caminho="Portal de Clientes · Pedidos"
        titulo="Painel de pedidos"
        explica="Os pedidos do site em três perguntas: o que confirmar, o que falta lançar no PDV e o que é para quando. Atualiza sozinho."
        acoes={<>
          <label className="flex items-center gap-2 text-[13px]">
            <input type="checkbox" checked={som} onChange={(e) => setSom(e.target.checked)} /> som de pedido novo
          </label>
          <Link href="/pedidos" className="btn btn-secundario">Lista</Link>
        </>}
      />
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!dados ? <Carregando /> : (
        <div className="grid gap-4 lg:grid-cols-3">
          {colunas.map((c) => (
            <section key={c.t} className="flex flex-col gap-2">
              <h2 className="text-[15px] font-semibold">{c.t} <span className="mono text-suave">({c.l.length})</span></h2>
              {!c.l.length ? <Vazio>{c.vazio}</Vazio> : c.l.map((p) => (
                <Cartaozinho key={p.id} p={p} agora={agora}>{c.acao(p)}</Cartaozinho>
              ))}
            </section>
          ))}
        </div>
      )}
      {lancando && (
        <JanelaDeCupom pedido={lancando} aoFechar={() => setLancando(null)}
                       aoFeito={() => { setLancando(null); void carregar(); }} />
      )}
    </div>
  );
}
