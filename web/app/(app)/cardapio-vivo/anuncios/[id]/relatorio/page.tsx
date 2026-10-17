"use client";

/**
 * O relatório de UM anúncio do Cardápio Vivo (121) — para a casa apresentar ao parceiro.
 *
 * 🔑 Pedido do dono (16/10/2026): "a casa cadastra o anúncio e depois, a partir das métricas,
 * gera um relatório para apresentar os números". Período escolhido na tela; "Imprimir / PDF"
 * usa a impressão do navegador (o menu e os botões somem no papel — `globals.css`).
 * 🔑 Pessoas = visitas anônimas ao cardápio que viram o anúncio; ninguém é identificado.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Aviso, Cartao, Carregando } from "@/components/ui";
import { AnunciosService, porcento, type Relatorio } from "@/lib/anuncios";

const data = (iso: string) => iso.split("-").reverse().join("/");

function Numero({ rotulo, valor, nota }: { rotulo: string; valor: string; nota?: string }) {
  return (
    <div className="rounded-lg border border-linha px-4 py-3">
      <p className="text-[12.5px] text-suave">{rotulo}</p>
      <p className="mono mt-1 text-[24px] font-semibold">{valor}</p>
      {nota && <p className="text-[12px] text-suave">{nota}</p>}
    </div>
  );
}

export default function RelatorioDoAnuncio() {
  const { id } = useParams<{ id: string }>();
  const [rel, setRel] = useState<Relatorio | null>(null);
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [erro, setErro] = useState("");

  const carregar = useCallback(async (d?: string, a?: string) => {
    try {
      const r = await AnunciosService.relatorio(Number(id), d, a);
      setRel(r);
      setDe(r.de);
      setAte(r.ate);
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o relatório");
    }
  }, [id]);

  useEffect(() => { void carregar(); }, [carregar]);

  if (erro && !rel) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!rel) return <Carregando />;
  const a = rel.anuncio;
  const t = rel.total;
  const maiorHora = Math.max(1, ...rel.por_hora.map((h) => h.aparicoes));

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo nao-imprimir">
          <Link href="/cardapio-vivo/anuncios" className="link-acao">‹ Anúncios</Link>
        </p>
        <p className="rotulo mt-2">{rel.casa ?? ""} · Cardápio Vivo</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight">Relatório do anúncio — {a.nome}</h1>
        <p className="mt-1 text-[14px] text-suave">
          {a.origem === "EXTERNO" ? `Patrocinado · ${a.anunciante ?? ""}` : "Da casa"} · de {data(rel.de)} a {data(rel.ate)}
        </p>
      </header>

      <div className="nao-imprimir flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-[13px]"><span className="text-suave">De</span>
          <input type="date" className="campo mono" value={de} onChange={(e) => setDe(e.target.value)} /></label>
        <label className="flex flex-col gap-1 text-[13px]"><span className="text-suave">Até</span>
          <input type="date" className="campo mono" value={ate} onChange={(e) => setAte(e.target.value)} /></label>
        <button type="button" className="btn btn-secundario" onClick={() => void carregar(de, ate)}>Atualizar</button>
        <button type="button" className="btn btn-primario" onClick={() => window.print()}>Imprimir / salvar em PDF</button>
        {erro && <span className="text-[13px] text-erro">{erro}</span>}
      </div>

      <section aria-label="resumo" className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Numero rotulo="Pessoas que viram" valor={String(t.sessoes)} nota="visitas ao cardápio, sem identificação" />
        <Numero rotulo="Vezes que apareceu" valor={String(t.aparicoes)} />
        <Numero rotulo="Tempo médio na tela" valor={t.segundos !== null ? `${String(t.segundos).replace(".", ",")} s` : "—"} />
        <Numero rotulo="Tocaram no botão" valor={String(t.sessoes_tocaram)} nota={`${t.toques} toques`} />
        <Numero rotulo="Taxa de toque" valor={porcento(t.taxa_toque)} nota="pessoas que tocaram ÷ que viram" />
        <Numero rotulo="Passaram direto" valor={porcento(t.taxa_pulou)} nota={`menos de ${rel.pulou_ms / 1000} s na tela`} />
      </section>

      <Cartao titulo="Dia a dia">
        {rel.por_dia.length === 0 ? <p className="text-[13.5px] text-suave">Nenhuma aparição no período.</p> : (
          <table className="tabela w-full">
            <thead><tr><th>Dia</th><th className="text-right">Pessoas</th><th className="text-right">Aparições</th>
              <th className="text-right">Tocaram</th><th className="text-right">Segundos</th></tr></thead>
            <tbody>
              {rel.por_dia.map((d) => (
                <tr key={d.dia}><td className="mono">{data(d.dia)}</td><td className="mono text-right">{d.sessoes}</td>
                  <td className="mono text-right">{d.aparicoes}</td><td className="mono text-right">{d.sessoes_tocaram}</td>
                  <td className="mono text-right">{d.segundos !== null ? String(d.segundos).replace(".", ",") : "—"}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </Cartao>

      <div className="grid gap-6 md:grid-cols-2">
        <Cartao titulo="Onde viram">
          {rel.por_canal.length === 0 ? <p className="text-[13.5px] text-suave">—</p> : (
            <table className="tabela w-full">
              <thead><tr><th /><th className="text-right">Pessoas</th><th className="text-right">Tocaram</th></tr></thead>
              <tbody>
                {rel.por_canal.map((c) => (
                  <tr key={c.canal}><td>{c.canal === "MESA" ? "Na mesa (QR)" : "Pelo link (site, catering)"}</td>
                    <td className="mono text-right">{c.sessoes}</td><td className="mono text-right">{c.sessoes_tocaram}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {rel.por_cardapio.length > 0 && (
            <table className="tabela mt-4 w-full" id="relatorio-por-cardapio">
              <thead><tr><th>Em qual cardápio</th><th className="text-right">Pessoas</th><th className="text-right">Tocaram</th></tr></thead>
              <tbody>
                {rel.por_cardapio.map((c) => (
                  <tr key={c.id_catalogo ?? 0}>
                    <td>{c.cardapio ?? (c.id_catalogo ? "(catálogo apagado)" : "(sem registro)")}</td>
                    <td className="mono text-right">{c.sessoes}</td><td className="mono text-right">{c.sessoes_tocaram}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </Cartao>
        <Cartao titulo="A que horas">
          {rel.por_hora.length === 0 ? <p className="text-[13.5px] text-suave">—</p> : (
            <div className="flex flex-col gap-1">
              {rel.por_hora.map((h) => (
                <div key={h.hora} className="grid grid-cols-[3rem_1fr_3rem] items-center gap-2 text-[13px]">
                  <span className="mono">{String(h.hora).padStart(2, "0")}h</span>
                  <span className="h-3 rounded-r-[3px] bg-[var(--color-erva)]" style={{ width: `${(h.aparicoes / maiorHora) * 100}%` }} />
                  <span className="mono text-right">{h.aparicoes}</span>
                </div>
              ))}
            </div>
          )}
        </Cartao>
      </div>
      <p className="text-[12px] text-suave">
        Medição anônima do Cardápio Vivo: cada visita ao cardápio é uma sessão sem nome, telefone ou endereço.
        Período limitado ao que a casa guarda (13 meses, por padrão).
      </p>
    </div>
  );
}
