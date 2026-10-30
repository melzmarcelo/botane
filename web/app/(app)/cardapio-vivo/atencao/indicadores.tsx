"use client";

/**
 * O topo do painel Atenção × Vendas: os números de cabeça, o funil, vídeo × foto, os
 * chamados e — sempre à vista — o que cada métrica quer dizer.
 *
 * 🔑 **As definições vêm do SERVIDOR** (`DEFINICOES` em `cardapio_atencao.py`): a tela não
 * mantém uma segunda versão delas.
 */

import { Cartao } from "@/components/ui";
import type { PainelAtencao } from "@/lib/cardapio-vivo";

import { plural } from "@/lib/numeros";
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(1).replace(".", ",")}%`);
export const segundos = (ms: number | null | undefined) => (ms === null || ms === undefined ? "—" : `${(ms / 1000).toFixed(1).replace(".", ",")} s`);

function Numero({ rotulo, valor, sub }: { rotulo: string; valor: string | number; sub?: string }) {
  return (
    <div className="cartao flex flex-col gap-0.5 px-4 py-3">
      <span className="text-[12.5px] text-suave">{rotulo}</span>
      <span className="mono text-[24px] font-semibold leading-tight">{valor}</span>
      {sub && <span className="text-[12px] text-suave">{sub}</span>}
    </div>
  );
}

export default function Indicadores({ p }: { p: PainelAtencao }) {
  const t = p.topo;
  const funil = [
    { nome: "Abriram o cardápio", n: p.funil.sessoes },
    { nome: "Viram pratos", n: p.funil.viram },
    { nome: "Adicionaram", n: p.funil.adicionaram },
    { nome: "Enviaram pedido", n: p.funil.enviaram },
  ];
  const maior = Math.max(1, ...funil.map((f) => f.n));
  const g = p.chamados.GARCOM, c = p.chamados.CONTA;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-5">
        <Numero rotulo="Sessões engajadas" valor={t.engajadas}
                sub={`de ${t.sessoes} abertas (${t.sessoes ? Math.round((t.engajadas / t.sessoes) * 100) : 0}%)`} />
        <Numero rotulo="Tela de entrada (Hub)" valor={t.hubs} sub="aberturas" />
        <Numero rotulo="Avaliar no Google" valor={t.cliques_avaliacao} sub="cliques" />
        <Numero rotulo="Wi-Fi" valor={t.cliques_wifi} sub="cliques" />
        <Numero rotulo="Chamar o garçom" valor={g?.total ?? 0}
                sub={g?.tempo_medio_min !== null && g?.tempo_medio_min !== undefined
                  ? `atendido em ${String(g.tempo_medio_min).replace(".", ",")} min, em média` : "sem atendimento medido"} />
      </div>

      {/* ⚠️ `min-w-0` nos filhos (auditoria de 29/10/2026): a tabela "Vídeo × foto" rola dentro
          do cartão, mas sem ele a largura dela virava o mínimo da coluna e a tela passava de
          390 para 441 px no celular. */}
      <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
        <Cartao titulo="Funil da sessão" descricao="Todas as sessões abertas no recorte.">
          <ol className="flex flex-col gap-2.5" aria-label="Funil da sessão">
            {funil.map((f) => (
              <li key={f.nome} className="grid grid-cols-[9.5rem_1fr_3.5rem] items-center gap-3 text-[13.5px]"
                  title={`${f.nome}: ${plural(f.n, "sessão", "sessões")}`}>
                <span>{f.nome}</span>
                <span className="h-4 rounded-r-[4px] bg-[var(--color-erva)]"
                      style={{ width: `${Math.max(1, (f.n / maior) * 100)}%` }} aria-hidden />
                <span className="mono text-right">{f.n}</span>
              </li>
            ))}
          </ol>
        </Cartao>

        <Cartao titulo="Vídeo × foto" descricao="Nas sessões engajadas: a mídia que estava na tela.">
          <div className="overflow-x-auto">
          <table className="tabela">
            <thead><tr><th>Mídia</th><th className="text-right">Visualizações</th><th className="text-right">Atenção média</th><th className="text-right">Adição</th></tr></thead>
            <tbody>
              {(["VIDEO", "FOTO"] as const).map((m) => {
                const x = p.midia[m];
                return (
                  <tr key={m}>
                    <td>{m === "VIDEO" ? "Vídeo" : "Foto"}</td>
                    <td className="mono text-right">{x?.visualizacoes ?? 0}</td>
                    <td className="mono text-right">{segundos(x?.atencao_media_ms)}</td>
                    <td className="mono text-right">{pct(x?.taxa_adicao)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
          {c && <p className="mt-3 text-[13px] text-suave">Pedidos de conta: {c.total}{c.tempo_medio_min !== null ? `, atendidos em ${String(c.tempo_medio_min).replace(".", ",")} min em média` : ""}.</p>}
        </Cartao>
      </div>

      <details className="cartao px-4 py-3 text-[13.5px]">
        <summary className="cursor-pointer font-semibold">O que cada número quer dizer</summary>
        <dl className="mt-2 grid gap-x-4 gap-y-1.5 sm:grid-cols-[12rem_1fr]">
          {Object.entries({
            "Sessão engajada": p.definicoes.sessao_engajada,
            "Atenção estimada": p.definicoes.atencao_estimada,
            "Deslize para trás": p.definicoes.deslize_tras,
            "Quase pediu": p.definicoes.quase_pediu,
            "Desistência": p.definicoes.desistencia,
            "Quadrante": p.definicoes.quadrante,
          }).map(([k, v]) => (
            <div key={k} className="contents"><dt className="font-medium">{k}</dt><dd className="text-suave">{v}</dd></div>
          ))}
        </dl>
      </details>
    </>
  );
}

export { pct };
