"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import ExplicaTela from "@/components/explica-tela";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import {
  listarParticipantes,
  resumoFidelidade,
  type Participante,
  type ResumoFidelidade,
} from "@/lib/fidelidade";
import { useSessao } from "@/lib/sessao";

import FichaDoParticipante from "./ficha";

/**
 * Fidelidade → Painel: o programa inteiro numa tela.
 *
 * 🔑 **Pedido do dono (27/09/2026):** *"uma tela para verificar os selos, os resgates, a
 * validade, ajustar o vencimento, dar selos, visualizar tudo que diz respeito ao plano de
 * fidelidade em uma só tela."* Os números do programa em cima, os participantes em grid
 * paginado, e a ficha de cada um (cartão, prêmios, selos lançados, pedidos de código) numa
 * janela — com as ações ali mesmo.
 * ⚠️ **Da rede**: o cadastro e o cartão são únicos por telefone.
 */
const FILTROS = [
  { v: "", r: "Todos" },
  { v: "com_premio", r: "Com prêmio disponível" },
  { v: "vencendo", r: "Prêmio vencendo (7 dias)" },
  { v: "vencidos", r: "Com prêmio vencido" },
];

function telefone(t: string) {
  const m = t.match(/^(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : t;
}
const dataBr = (iso: string | null) => (iso ? iso.slice(0, 10).split("-").reverse().join("/") : "—");

export default function PainelDaFidelidade() {
  const { pode } = useSessao();
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [filtro, setFiltro] = useEstadoNaUrl<string>("filtro", "");
  const [aberto, setAberto] = useEstadoNaUrl<string>("cliente", "");
  const [lista, setLista] = useState<Participante[] | null>(null);
  const [resumo, setResumo] = useState<ResumoFidelidade | null>(null);
  const [erro, setErro] = useState("");
  const pag = usePaginacao("fidelidade-painel", { filtros: [busca, filtro] });

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    try {
      const [r, s] = await Promise.all([
        listarParticipantes(pag.parametros, { busca, filtro }),
        resumoFidelidade(),
      ]);
      setLista(r.itens);
      pag.setTotal(r.total);
      setResumo(s);
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar a fidelidade");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, busca, filtro, pag.offset, pag.porPagina]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  const numeros = resumo
    ? [
        { n: resumo.participantes, r: "participantes" },
        { n: resumo.selos_abertos, r: "selos em cartões abertos" },
        { n: resumo.premios_disponiveis, r: "prêmios disponíveis", f: "com_premio" },
        { n: resumo.vencendo_7_dias, r: "vencendo em 7 dias", f: "vencendo", alerta: true },
        { n: resumo.premios_vencidos, r: "prêmios vencidos", f: "vencidos" },
        { n: resumo.entregues_no_mes, r: "entregues no mês" },
        { n: resumo.visitas_hoje, r: "visitas hoje" },
      ]
    : [];

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Portal de Clientes · Fidelidade</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Painel</h1>
        <ExplicaTela>
          O programa inteiro: quem participa, quantos selos cada um tem, os prêmios e as
          validades. Clique num cliente para ver tudo dele — e, com permissão, dar selos,
          retirar um lançamento errado ou ajustar o vencimento de um prêmio.
        </ExplicaTela>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {resumo && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {numeros.map((x) => (
            <button key={x.r} type="button" disabled={!x.f}
                    onClick={() => x.f && setFiltro(filtro === x.f ? "" : x.f)}
                    className={`cartao px-3 py-3 text-left ${x.f ? "hover:border-[var(--color-erva)]" : "cursor-default"} ${
                      filtro && filtro === x.f ? "ring-1 ring-[var(--color-erva)]" : ""}`}>
              <b className={`mono block text-[24px] leading-none ${
                x.alerta && x.n > 0 ? "text-[var(--color-alerta)]" : ""}`}>{x.n}</b>
              <span className="text-[12px] text-suave">{x.r}</span>
            </button>
          ))}
        </div>
      )}
      {resumo && (
        <p className="-mt-3 text-[13px] text-suave">
          A cada {resumo.visitas_por_premio} selos: {resumo.premio} · método{" "}
          {resumo.metodo === "CODIGO_CAIXA" ? "código do caixa" : "QR na mesa"} ·{" "}
          <Link href="/fidelidade/configuracao" className="link-acao">configuração</Link>
        </p>
      )}

      <Cartao>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="min-w-0 flex-1">
            <span className="rotulo-campo">Buscar</span>
            <input className="campo mt-1.5" placeholder="nome ou telefone" value={busca}
                   onChange={(e) => setBusca(e.target.value)} />
          </label>
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="filtro">
            {FILTROS.map((x) => (
              <button key={x.v} type="button" role="tab" aria-selected={filtro === x.v}
                      className={`btn px-3 py-1.5 text-[13px] ${filtro === x.v ? "btn-primario" : "btn-secundario"}`}
                      onClick={() => setFiltro(x.v)}>
                {x.r}
              </button>
            ))}
          </div>
        </div>
      </Cartao>

      <Cartao titulo={lista ? `${pag.total ?? lista.length} participante(s)` : "Participantes"}>
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>{busca || filtro ? "Ninguém com esse filtro." : "Ninguém participa do programa ainda."}</Vazio>
        ) : (
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th className="min-w-[200px]">Cliente</th>
                  <th className="num">No cartão</th>
                  <th className="num">Visitas</th>
                  <th className="num">Última visita</th>
                  <th>Prêmios</th>
                  <th className="num">Próx. vencimento</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((x) => (
                  <tr key={x.id} className="cursor-pointer hover:bg-[var(--color-superficie2)]"
                      onClick={() => setAberto(String(x.id))}>
                    <td>
                      <span className="link-registro font-medium">{x.nome}</span>
                      <span className="mono block text-[12px] text-suave">{telefone(x.telefone)}</span>
                    </td>
                    <td className="num mono">
                      {x.no_cartao}
                      {resumo && <span className="text-suave">/{resumo.visitas_por_premio}</span>}
                    </td>
                    <td className="num mono">{x.visitas}</td>
                    <td className="num mono">{dataBr(x.ultima_visita)}</td>
                    <td>
                      <span className="flex flex-wrap gap-1">
                        {x.disponiveis > 0 && <Etiqueta cor="erva">{x.disponiveis} disponível(is)</Etiqueta>}
                        {x.vencidos > 0 && <Etiqueta cor="alerta">{x.vencidos} vencido(s)</Etiqueta>}
                        {x.usados > 0 && <Etiqueta>{x.usados} entregue(s)</Etiqueta>}
                        {!x.disponiveis && !x.vencidos && !x.usados && <span className="text-suave">—</span>}
                      </span>
                    </td>
                    <td className="num mono">{dataBr(x.proximo_vencimento)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Paginacao p={pag} rotulo="participante(s)" />
      </Cartao>

      {aberto && (
        <FichaDoParticipante
          idCliente={Number(aberto)}
          podeMexer={pode("fidelidade.configurar")}
          podeEntregar={pode("fidelidade.operar")}
          aoFechar={() => setAberto("")}
          aoMudar={() => void carregar()}
        />
      )}
    </div>
  );
}
