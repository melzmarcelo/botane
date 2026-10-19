"use client";

/**
 * Portal de Clientes → Catálogos → Testes A/B (Cardápio Vivo, fase 3, migração 116).
 *
 * 🔑 Decisões do dono (15/10/2026): **mídia** = vídeo × foto no mesmo prato; **ordem** = a do
 * catálogo × a sugerida pelo painel; o **vencedor** sai da taxa de adição. Metade das sessões
 * vê cada braço, sempre o mesmo para a mesma sessão.
 * ⚠️ Nada muda no cardápio até alguém APLICAR — e aplicar é um clique de quem edita.
 */

import { useCallback, useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso, Cartao, Carregando, Etiqueta, Vazio } from "@/components/ui";
import { CardapioVivoService, TestesService, type TesteAB } from "@/lib/cardapio-vivo";
import * as cat from "@/lib/catalogos";
import { useSessao } from "@/lib/sessao";
import EscolhaCardapio from "../escolha-cardapio";

const pct = (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(1).replace(".", ",")}%`);
const CONCLUSAO: Record<TesteAB["resultado"]["conclusao"], string> = {
  AMOSTRA_PEQUENA: "Amostra pequena — ainda não dá para dizer",
  SEM_DIFERENCA: "Sem diferença que se sustente",
  A_VENCE: "A vence",
  B_VENCE: "B vence",
};

function Resultado({ t }: { t: TesteAB }) {
  const r = t.resultado;
  const maior = Math.max(r.taxa_a ?? 0, r.taxa_b ?? 0, 0.0001);
  return (
    <div className="flex flex-col gap-2">
      {(["A", "B"] as const).map((v) => {
        const b = r[v];
        const taxa = v === "A" ? r.taxa_a : r.taxa_b;
        return (
          <div key={v} className="grid grid-cols-[8.5rem_1fr_5rem] items-center gap-3 text-[13.5px]"
               title={`${b.rotulo}: ${b.adicionaram} de ${b.sessoes} sessões adicionaram`}>
            <span><b>{v}</b> · {b.rotulo}</span>
            <span className="h-4 rounded-r-[4px] bg-[var(--color-erva)]" aria-hidden
                  style={{ width: `${taxa ? Math.max(1, (taxa / maior) * 100) : 1}%`, opacity: v === "A" ? 0.55 : 1 }} />
            <span className="mono text-right">{pct(taxa)}</span>
            <span className="col-start-2 -mt-1 text-[12px] text-suave">{b.adicionaram} de {b.sessoes} sessões expostas</span>
          </div>
        );
      })}
      <p className="text-[13px]">
        <b>{CONCLUSAO[r.conclusao]}</b>
        {r.p_valor !== null && <span className="text-suave"> · p = {String(r.p_valor).replace(".", ",")}</span>}
        {r.conclusao === "AMOSTRA_PEQUENA" && <span className="text-suave"> (mínimo de {r.minimo_por_braco} sessões por braço)</span>}
      </p>
    </div>
  );
}

export default function PaginaTestes() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const [lista, setLista] = useState<TesteAB[] | null>(null);
  const [pratos, setPratos] = useState<{ id: number; nome: string }[]>([]);
  const [prato, setPrato] = useState("");
  // 🔑 Em qual Cardápio Vivo o teste novo roda (1.1.109); começa no principal.
  const [vivos, setVivos] = useState<{ id_catalogo: number; nome: string; principal: boolean }[]>([]);
  const [idCatalogo, setIdCatalogo] = useState<number | null>(null);
  const [erro, setErro] = useState("");
  const editar = pode("catalogos.editar");

  const carregar = useCallback(() => TestesService.listar().then(setLista)
    .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar os testes")), []);

  useEffect(() => {
    void carregar();
    CardapioVivoService.config().then((r) => {
      setVivos(r.vivos.map((v) => ({ id_catalogo: v.id_catalogo, nome: v.nome, principal: v.principal })));
      setIdCatalogo(r.config.id_catalogo);
    }).catch(() => setVivos([]));
  }, [carregar]);

  useEffect(() => {
    // Os pratos que valem um teste de mídia: os do cardápio escolhido com vídeo E foto.
    setPrato("");
    if (!idCatalogo) { setPratos([]); return; }
    cat.conteudo(idCatalogo).then((k) => {
      const todos = k.categorias.flatMap((c) => [...c.itens, ...c.subcategorias.flatMap((s) => s.itens)]);
      setPratos(todos.filter((i) => i.tem_video && i.foto_url && i.ativo)
        .map((i) => ({ id: i.id, nome: i.nome_catalogo || i.produto })));
    }).catch(() => setPratos([]));
  }, [idCatalogo]);

  async function acao(p: Promise<{ message: string }>) {
    try {
      aviso.sucesso((await p).message);
      void carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível.");
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <CabecalhoTela
        caminho="Portal de Clientes · Catálogos"
        titulo="Testes A/B"
        explica="Metade das sessões do Cardápio Vivo vê uma versão, metade vê a outra — sempre a mesma para a mesma pessoa. Ganha quem faz mais gente adicionar o prato. Nada muda no cardápio até você aplicar."
      />
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {editar && <EscolhaCardapio opcoes={vivos} valor={idCatalogo} aoMudar={setIdCatalogo} />}
      {editar && (
        <div className="grid gap-4 md:grid-cols-2">
          <Cartao titulo="Vídeo × foto" descricao="Num prato que tem os dois: A mostra o vídeo, B a foto.">
            {pratos.length === 0 ? <Vazio>Nenhum prato deste cardápio tem vídeo e foto.</Vazio> : (
              <div className="flex flex-wrap gap-2">
                <select className="campo !w-auto flex-1" value={prato} onChange={(e) => setPrato(e.target.value)} aria-label="Prato">
                  <option value="">— escolha o prato —</option>
                  {pratos.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
                <button className="btn btn-primario" disabled={!prato}
                        onClick={() => void acao(TestesService.criar("MIDIA", Number(prato), idCatalogo))}>Começar</button>
              </div>
            )}
          </Cartao>
          <Cartao titulo="Ordem atual × sugerida"
                  descricao="B mostra, dentro de cada seção, a ordem que o painel Atenção × Vendas sugere (destaques e pratos a destacar sobem). A ordem B fica congelada no início.">
            <button className="btn btn-primario" onClick={() => void acao(TestesService.criar("ORDEM", undefined, idCatalogo))}>Começar</button>
          </Cartao>
        </div>
      )}

      {!lista ? <Carregando /> : lista.length === 0 ? <Vazio>Nenhum teste ainda.</Vazio> : lista.map((t) => (
        <Cartao key={t.id} titulo={t.nome}
                descricao={`${vivos.length > 1 && t.cardapio ? `${t.cardapio} · ` : ""}${t.aberto ? "Aberto desde" : "Encerrado em"} ${new Date(t.aberto ? t.inicio : t.encerrado_em!).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}`}
                acao={<div className="flex flex-wrap items-center gap-2">
                  {t.aplicado_em && <Etiqueta cor="erva">aplicado</Etiqueta>}
                  {!t.aberto && t.vencedor && <Etiqueta cor="erva">venceu {t.vencedor}</Etiqueta>}
                  {editar && t.aberto && <button className="btn btn-secundario" onClick={() => void acao(TestesService.encerrar(t.id))}>Encerrar</button>}
                  {editar && !t.aplicado_em && (["A", "B"] as const).map((v) => (
                    <button key={v} className={`btn ${t.vencedor === v || (t.aberto && t.resultado.conclusao === `${v}_VENCE`) ? "btn-primario" : "btn-secundario"}`}
                            onClick={() => void acao(TestesService.aplicar(t.id, v))}>Aplicar {v}</button>
                  ))}
                </div>}>
          <Resultado t={t} />
        </Cartao>
      ))}
    </div>
  );
}
