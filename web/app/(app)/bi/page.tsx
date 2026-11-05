"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso, Carregando } from "@/components/ui";
import {
  apagarBI, catalogoBI, type CatalogoBI, consultarBI, DEFINICAO_VAZIA, type DefinicaoBI, relatorioBI,
  relatoriosBI, type RelatorioBI, type ResultadoBI, salvarBI, type Visibilidade, type Visual,
} from "@/lib/bi";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { useSessao } from "@/lib/sessao";

import { Barras, Indicadores, JanelaSalvar, PassoCampos, PassoFontes, PassoLigacoes, PassoPeriodo, Tabela } from "./pecas";

/**
 * 🔑 **O Estúdio BI** (layout novo, fase 4 — 05/11/2026, pedido do dono: *"um menu estilo BI, onde o
 * usuário administrador pode criar relatórios personalizados com suas ligações configuráveis"*;
 * protótipo aprovado em `apresentacao/novo-layout/`).
 *
 * 1. fontes → 2. ligações (as sugeridas, com tipo, e as manuais pelas colunas de ligação) →
 * 3. dimensões e medidas → 4. período. A prévia roda sozinha a cada mudança, no servidor.
 * ⚠️ Quem monta o SQL é o servidor (`services/bi.py`), a partir dos NOMES daqui; o painel "Ver
 * consulta" só mostra o que ele montou. Erros de montagem (soma no grão errado, fonte solta) vêm
 * com a explicação dele e aparecem no lugar da prévia.
 */
export default function EstudioBI() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const [cat, setCat] = useState<CatalogoBI | null>(null);
  const [erroCat, setErroCat] = useState("");
  const [salvos, setSalvos] = useState<RelatorioBI[]>([]);
  const [idUrl, setIdUrl] = useEstadoNaUrl<string>("id", "", { atraso: 0 });
  const [d, setD] = useState<DefinicaoBI>(DEFINICAO_VAZIA);
  const [nome, setNome] = useState("Novo relatório");
  const [visibilidade, setVisibilidade] = useState<Visibilidade>("EU");
  const [papeis, setPapeis] = useState<number[]>([]);
  const [noMenu, setNoMenu] = useState(true);
  const [res, setRes] = useState<ResultadoBI | null>(null);
  const [erro, setErro] = useState("");
  const [rodando, setRodando] = useState(false);
  const [verConsulta, setVerConsulta] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [janela, setJanela] = useState(false);
  const idAtual = idUrl ? Number(idUrl) : null;
  const carregado = useRef<string>("");

  const recarregarSalvos = useCallback(() => { relatoriosBI().then(setSalvos).catch(() => {}); }, []);
  useEffect(() => {
    catalogoBI().then(setCat).catch((e) => setErroCat(e instanceof Error ? e.message : "Falha ao carregar"));
    recarregarSalvos();
  }, [recarregarSalvos]);

  // Abrir um salvo pela URL (?id=), inclusive vindo de Relatórios ▸ "Editar no Estúdio".
  useEffect(() => {
    if (!idUrl || carregado.current === idUrl) return;
    carregado.current = idUrl;
    relatorioBI(Number(idUrl)).then((r) => {
      setD({ ...DEFINICAO_VAZIA, ...r.definicao });
      setNome(r.nome);
      setVisibilidade(r.visibilidade);
      setPapeis(r.papeis_vistos);
      setNoMenu(r.no_menu);
    }).catch((e) => aviso.erro(e instanceof Error ? e.message : "Relatório não encontrado"));
  }, [idUrl, aviso]);

  const mudar = useCallback((f: (x: DefinicaoBI) => DefinicaoBI) => setD((x) => f(x)), []);

  // As fontes sem ligação — o servidor recusa; aqui só se avisa antes, com o mesmo critério.
  const soltas = useMemo(() => {
    if (!cat || d.fontes.length < 2) return [];
    const arestas = cat.relacoes.filter((r) => d.fontes.includes(r.a) && d.fontes.includes(r.b) && d.tipos[r.id] !== "NENHUMA")
      .map((r) => [r.a, r.b]).concat(d.manuais.filter((m) => m.a !== m.b).map((m) => [m.a, m.b]));
    const exige = cat.fontes.filter((f) => d.fontes.includes(f.chave)).flatMap((f) => f.exige);
    const todas = [...new Set([...d.fontes, ...exige])];
    const ligadas = new Set([todas[0]]);
    let mudou = true;
    while (mudou) {
      mudou = false;
      for (const [a, b] of arestas) {
        if (ligadas.has(a) !== ligadas.has(b)) { ligadas.add(a); ligadas.add(b); mudou = true; }
      }
    }
    return todas.filter((k) => !ligadas.has(k)).map((k) => cat.fontes.find((f) => f.chave === k)?.rotulo ?? k);
  }, [cat, d]);

  // A prévia: roda sozinha, com um respiro, quando há fonte e medida. Indicadores = sem dimensão.
  useEffect(() => {
    if (!d.fontes.length || !d.medidas.length || soltas.length) { setRes(null); setErro(""); return; }
    const t = setTimeout(() => {
      setRodando(true);
      consultarBI(d.visual === "indicadores" ? { ...d, dimensoes: [] } : d)
        .then((r) => { setRes(r); setErro(""); })
        .catch((e) => { setRes(null); setErro(e instanceof Error ? e.message : "Falha na consulta"); })
        .finally(() => setRodando(false));
    }, 450);
    return () => clearTimeout(t);
  }, [d, soltas.length]);

  const salvar = async () => {
    setSalvando(true);
    try {
      const r = await salvarBI({ nome: nome.trim(), definicao: d, visibilidade, papeis_vistos: papeis, no_menu: noMenu }, idAtual);
      carregado.current = String(r.id);
      setIdUrl(String(r.id));
      setJanela(false);
      recarregarSalvos();
      aviso.sucesso(noMenu ? "Publicado em Relatórios ▸ Personalizados" : "Relatório salvo");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao salvar");
    } finally {
      setSalvando(false);
    }
  };
  const apagar = async () => {
    if (!idAtual) return;
    try {
      await apagarBI(idAtual);
      aviso.sucesso("Relatório apagado");
      novo();
      recarregarSalvos();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao apagar");
    }
  };
  const novo = () => {
    carregado.current = "";
    setIdUrl("");
    setD(DEFINICAO_VAZIA);
    setNome("Novo relatório");
    setVisibilidade("EU");
    setPapeis([]);
    setNoMenu(true);
  };

  if (!pode("bi.estudio")) {
    return <Aviso tipo="erro">O Estúdio BI é do administrador (permissão “Criar relatórios personalizados”).</Aviso>;
  }

  const VIZ: { v: Visual; r: string }[] = [{ v: "barras", r: "Barras" }, { v: "tabela", r: "Tabela" }, { v: "indicadores", r: "Indicadores" }];

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Análise"
        titulo={<>Estúdio BI</>}
        explica={<>Monte um relatório escolhendo as fontes, como elas se ligam e o que somar. A prévia
          aparece ao lado; salve para publicá-lo em Relatórios para quem você escolher.</>}
        acoes={
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn btn-secundario" aria-pressed={verConsulta}
                    onClick={() => setVerConsulta((v) => !v)}>{verConsulta ? "Esconder consulta" : "Ver consulta"}</button>
            <button type="button" id="bi-salvar" className="btn btn-primario" disabled={!res}
                    onClick={() => setJanela(true)}>Salvar e publicar</button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-2" id="bi-salvos">
        <span className="text-[13px] font-semibold text-suave">Meus relatórios:</span>
        {salvos.map((s) => (
          <button key={s.id} type="button" aria-pressed={idAtual === s.id}
                  onClick={() => { carregado.current = ""; setIdUrl(String(s.id)); }}
                  className={`rounded-full border px-3 py-1.5 text-[13px] font-semibold ${
                    idAtual === s.id ? "border-erva/40 bg-erva-claro text-erva" : "border-linha bg-superficie hover:border-linha2"}`}>
            {s.nome}
          </button>
        ))}
        <button type="button" onClick={novo} className="rounded-full border border-linha bg-superficie px-3 py-1.5 text-[13px] font-semibold text-erva">
          + Em branco
        </button>
        {idAtual && (
          <>
            <Link href={`/relatorios?r=bi-${idAtual}`} className="btn btn-terciario btn-pequeno ml-auto">Abrir em Relatórios</Link>
            <button type="button" className="btn btn-perigo btn-pequeno" onClick={() => void apagar()}>Apagar</button>
          </>
        )}
      </div>

      <label className="block max-w-[560px]">
        <span className="rotulo-campo">Nome do relatório</span>
        <input id="bi-nome" className="campo mt-1.5" maxLength={120} value={nome} onChange={(e) => setNome(e.target.value)} />
      </label>

      {erroCat ? <Aviso tipo="erro">{erroCat}</Aviso> : !cat ? <Carregando /> : (
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start">
          <div className="flex w-full shrink-0 flex-col gap-4 xl:w-[460px]">
            <PassoFontes cat={cat} d={d} mudar={mudar} />
            <PassoLigacoes cat={cat} d={d} mudar={mudar} soltas={soltas} />
            <PassoCampos cat={cat} d={d} mudar={mudar} />
            <PassoPeriodo d={d} mudar={mudar} />
          </div>

          <div className="flex min-w-0 flex-1 flex-col gap-4">
            <section className="cartao p-4 sm:p-5" id="bi-previa">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-[16px] font-bold">Prévia</h2>
                  <p className="text-[12.5px] text-suave">
                    {rodando ? "consultando…" : res ? `${res.linhas.length.toLocaleString("pt-BR")} linha(s)${res.cortado ? `, cortado em ${res.limite}` : ""}`
                      : "Escolha uma fonte e ao menos uma medida."}
                    {d.visual === "barras" && d.medidas.length > 1 ? " · as barras mostram a primeira medida; a tabela mostra todas" : ""}
                  </p>
                </div>
                <div className="seg-grade" role="group" aria-label="Forma de ver">
                  {VIZ.map((x) => (
                    <button key={x.v} type="button" aria-pressed={d.visual === x.v}
                            onClick={() => mudar((y) => ({ ...y, visual: x.v }))}>{x.r}</button>
                  ))}
                </div>
              </div>
              {erro && <Aviso tipo="erro">{erro}</Aviso>}
              {res && !erro && (d.visual === "barras" ? <Barras res={res} />
                : d.visual === "tabela" ? <Tabela res={res} /> : <Indicadores res={res} />)}
            </section>

            {verConsulta && (
              <section className="cartao p-4 sm:p-5" id="bi-consulta">
                <h2 className="text-[15px] font-bold">A consulta que o estúdio montou</h2>
                <p className="mb-3 text-[12.5px] text-suave">Só leitura, na loja do topo, com tempo máximo. Ninguém precisa escrever SQL.</p>
                <pre className="overflow-x-auto whitespace-pre-wrap rounded-xl bg-[#17221c] p-4 text-[12.5px] leading-relaxed text-[#d9e7de]"
                     style={{ fontFamily: "var(--font-mono)" }}>{res?.sql ?? "-- escolha fontes e campos"}</pre>
              </section>
            )}
          </div>
        </div>
      )}

      {janela && (
        <JanelaSalvar nome={nome} setNome={setNome} visibilidade={visibilidade} setVisibilidade={setVisibilidade}
                      papeis={papeis} setPapeis={setPapeis} noMenu={noMenu} setNoMenu={setNoMenu}
                      aoFechar={() => setJanela(false)} aoSalvar={() => void salvar()} salvando={salvando} />
      )}
    </div>
  );
}
