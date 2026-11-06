"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import {
  CamposDoRelatorio, comoQuery, pedirCatalogo, type RelatorioDoServidor, type ValoresIniciais,
} from "@/components/exportar";
import { Aviso, Carregando, Cartao } from "@/components/ui";
import { api } from "@/lib/api";
import { executarBI, relatoriosBI, type RelatorioBI, type ResultadoBI } from "@/lib/bi";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { useSessao } from "@/lib/sessao";

import Folha, { type DadosDoRelatorio as Dados, FolhaDosDados, folhaDoBI } from "@/components/folha-relatorio";

/**
 * 🔑 **A tela única de Relatórios** (layout novo, fase 3 — 05/11/2026, pedido do dono: *"relatórios
 * padrões"*; protótipo em `apresentacao/novo-layout/`).
 *
 * À esquerda, o catálogo por área — os relatórios PADRÃO (o mesmo catálogo dos botões Imprimir das
 * telas, já filtrado pela permissão de quem vê) e os PERSONALIZADOS do Estúdio BI. À direita, os
 * filtros, a prévia em folha e os botões Imprimir (PDF numa aba) e Gerar planilha.
 * ⚠️ A prévia só roda no clique: o razão inteiro de um ano custa segundos, e abrir a tela não pode
 * disparar isso. O relatório escolhido vai na URL (`?r=`), para o link abrir o mesmo.
 */

export default function PaginaRelatorios() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const [catalogo, setCatalogo] = useState<RelatorioDoServidor[] | null>(null);
  const [personalizados, setPersonalizados] = useState<RelatorioBI[]>([]);
  const [erro, setErro] = useState("");
  const [sel, setSel] = useEstadoNaUrl<string>("r", "", { atraso: 0 });
  const [busca, setBusca] = useState("");

  useEffect(() => {
    pedirCatalogo().then(setCatalogo).catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
    relatoriosBI().then(setPersonalizados).catch(() => {});
  }, []);

  const grupos = useMemo(() => {
    const t = busca.trim().toLowerCase();
    const casa = (s: string) => !t || s.toLowerCase().includes(t);
    const mapa = new Map<string, { chave: string; rotulo: string; descricao: string }[]>();
    for (const r of catalogo ?? []) {
      if (!casa(r.rotulo) && !casa(r.descricao)) continue;
      const g = r.grupo ?? "Outros";
      mapa.set(g, [...(mapa.get(g) ?? []), { chave: r.chave, rotulo: r.rotulo, descricao: r.descricao }]);
    }
    const lista = [...mapa.entries()].map(([g, itens]) => ({ grupo: g, itens }));
    const pers = personalizados.filter((p) => p.no_menu && casa(p.nome))
      .map((p) => ({ chave: `bi-${p.id}`, rotulo: p.nome, descricao: "Criado no Estúdio BI" }));
    if (pers.length) lista.push({ grupo: "Personalizados", itens: pers });
    return lista;
  }, [catalogo, personalizados, busca]);

  const escolhido = catalogo?.find((r) => r.chave === sel) ?? null;
  const idBI = sel.startsWith("bi-") ? Number(sel.slice(3)) : null;
  const bi = idBI ? personalizados.find((p) => p.id === idBI) ?? null : null;

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Análise"
        titulo={<>Relatórios</>}
        explica={<>Os relatórios padrão do sistema e os personalizados do Estúdio BI, num lugar só. Escolha
          um, ajuste os filtros, veja a prévia e imprima ou gere a planilha.</>}
        acoes={pode("bi.estudio") ? <Link href="/bi" className="btn btn-secundario">Criar no Estúdio BI</Link> : undefined}
      />
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
        <aside className="cartao w-full shrink-0 p-3 lg:w-[310px]" aria-label="Catálogo de relatórios">
          <label htmlFor="busca-relatorio" className="sr-only">Buscar relatório</label>
          <input id="busca-relatorio" className="campo mb-2" placeholder="Buscar relatório"
                 value={busca} onChange={(e) => setBusca(e.target.value)} />
          {!catalogo ? <Carregando /> : !grupos.length ? (
            <p className="px-2 py-4 text-[14px] text-suave">Nenhum relatório com esse nome.</p>
          ) : grupos.map((g) => (
            <div key={g.grupo} className="mt-2">
              <p className="rotulo px-2 pb-1 pt-2">{g.grupo}</p>
              <ul>
                {g.itens.map((r) => (
                  <li key={r.chave}>
                    <button type="button" data-relatorio={r.chave} aria-current={sel === r.chave ? "true" : undefined}
                            onClick={() => setSel(r.chave)}
                            className={`flex w-full flex-col items-start rounded-[10px] px-2.5 py-2 text-left transition-colors ${
                              sel === r.chave ? "bg-erva-claro" : "hover:bg-superficie2"}`}>
                      <span className={`text-[14px] font-semibold ${sel === r.chave ? "text-erva" : ""}`}>{r.rotulo}</span>
                      <span className="text-[12.5px] leading-snug text-suave">{r.descricao}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </aside>

        <div className="min-w-0 flex-1">
          {escolhido ? <RelatorioPadrao key={escolhido.chave} rel={escolhido} aviso={aviso} />
            : bi ? <RelatorioPersonalizado key={bi.id} rel={bi} aviso={aviso} />
            : (
              <Cartao>
                <p className="py-10 text-center text-[15px] text-suave">
                  Escolha um relatório no catálogo para ver os filtros e a prévia.
                </p>
              </Cartao>
            )}
        </div>
      </div>
    </div>
  );
}

type AvisoT = ReturnType<typeof useAviso>;

function Botoes({ aoImprimir, aoPlanilha, aoPrevia, carregando }: {
  aoImprimir: () => void; aoPlanilha: () => void; aoPrevia: () => void; carregando: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      <button type="button" id="relatorio-previa" className="btn btn-secundario" onClick={aoPrevia}
              disabled={carregando} aria-busy={carregando}>{carregando ? "Carregando…" : "Ver prévia"}</button>
      <button type="button" className="btn btn-secundario" onClick={aoPlanilha}>Gerar planilha</button>
      <button type="button" className="btn btn-primario" onClick={aoImprimir}>Imprimir</button>
    </div>
  );
}

function RelatorioPadrao({ rel, aviso }: { rel: RelatorioDoServidor; aviso: AvisoT }) {
  const [valores, setValores] = useState<ValoresIniciais>({});
  const [produtos, setProdutos] = useState<{ id: number; rotulo: string }[]>([]);
  const [dados, setDados] = useState<Dados | null>(null);
  const [carregando, setCarregando] = useState(false);
  const query = comoQuery({ ...valores, produtos: produtos.map((p) => p.id) });

  const previa = async () => {
    setCarregando(true);
    try {
      setDados(await api.get<Dados>(`/exportar/${rel.chave}/dados${query}`));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao montar a prévia");
    } finally {
      setCarregando(false);
    }
  };
  const arquivo = async (ext: "pdf" | "csv") => {
    try {
      if (ext === "pdf") await api.abrir(`/exportar/${rel.chave}.pdf${query}`);
      else await api.baixar(`/exportar/${rel.chave}.csv${query}`);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao gerar o arquivo");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <Cartao titulo={rel.rotulo} descricao={rel.descricao}>
        <div className="flex flex-col gap-5">
          {rel.filtros.length ? (
            <CamposDoRelatorio rel={rel} valores={valores} setValores={setValores}
                               produtos={produtos} setProdutos={setProdutos} />
          ) : <p className="text-[14px] text-suave">Este relatório sai inteiro, sem recorte.</p>}
          <Botoes aoPrevia={() => void previa()} aoImprimir={() => void arquivo("pdf")}
                  aoPlanilha={() => void arquivo("csv")} carregando={carregando} />
        </div>
      </Cartao>
      {dados && (
        <section className="cartao overflow-hidden p-0">
          <FolhaDosDados dados={dados} />
        </section>
      )}
    </div>
  );
}

function RelatorioPersonalizado({ rel, aviso }: { rel: RelatorioBI; aviso: AvisoT }) {
  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [res, setRes] = useState<ResultadoBI | null>(null);
  const [carregando, setCarregando] = useState(false);
  const periodo = new URLSearchParams({ ...(de ? { de } : {}), ...(ate ? { ate } : {}) }).toString();

  const previa = async () => {
    setCarregando(true);
    try {
      setRes(await executarBI(rel.id, { de: de || null, ate: ate || null }));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao rodar o relatório");
    } finally {
      setCarregando(false);
    }
  };
  const arquivo = async (formato: "pdf" | "csv") => {
    try {
      const url = `/bi/relatorios/${rel.id}/exportar?formato=${formato}${periodo ? `&${periodo}` : ""}`;
      if (formato === "pdf") await api.abrir(url);
      else await api.baixar(url);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao gerar o arquivo");
    }
  };
  const f = res ? folhaDoBI(res.colunas, res.linhas) : null;

  return (
    <div className="flex flex-col gap-4">
      <Cartao titulo={rel.nome}
              descricao={`Personalizado, criado no Estúdio BI${rel.criado_por ? ` por ${rel.criado_por}` : ""}.`}>
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-end gap-3">
            <label><span className="rotulo-campo">De</span>
              <input type="date" className="campo mt-1.5 w-auto" value={de} onChange={(e) => setDe(e.target.value)} /></label>
            <label><span className="rotulo-campo">Até</span>
              <input type="date" className="campo mt-1.5 w-auto" value={ate} onChange={(e) => setAte(e.target.value)} /></label>
            <p className="pb-3 text-[12.5px] text-suave">Vazio = o período salvo no relatório.</p>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Botoes aoPrevia={() => void previa()} aoImprimir={() => void arquivo("pdf")}
                    aoPlanilha={() => void arquivo("csv")} carregando={carregando} />
            {rel.pode_editar && <Link href={`/bi?id=${rel.id}`} className="btn btn-terciario">Editar no Estúdio</Link>}
          </div>
        </div>
      </Cartao>
      {res && f && (
        <section className="cartao overflow-hidden p-0">
          <Folha titulo={rel.nome} colunas={f.colunas} linhas={f.linhas}
                 rodape={res.cortado ? `Mostrando as primeiras ${res.limite} linhas.` : `${res.linhas.length} linha(s).`} />
        </section>
      )}
    </div>
  );
}
