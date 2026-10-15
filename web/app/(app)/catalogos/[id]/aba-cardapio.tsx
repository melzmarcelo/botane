"use client";

/**
 * A aba Cardápio: as seções à esquerda, os pratos da seção escolhida à direita.
 *
 * 🔑 **Reforma de 15/10/2026** (pedido do dono: *"o cadastro de catálogos não está
 * muito intuitivo e fácil de realizar"*). Antes, cada categoria era um cartão
 * aberto com foto, horário, produtos soltos e subcategorias — tudo junto, e um
 * cardápio de sessenta pratos virava uma rolagem sem fim. Agora a estrutura fica
 * sempre à vista (a coluna das seções, com a contagem) e o trabalho é numa seção
 * por vez. No celular, as seções viram uma faixa que rola de lado.
 * ⚠️ A seção escolhida sobrevive ao recarregar (gravar um prato não devolve a
 * pessoa ao topo); se ela foi excluída, cai na primeira.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Vazio } from "@/components/ui";
import { useSessao } from "@/lib/sessao";
import { urlArquivo } from "@/lib/api";
import * as cat from "@/lib/catalogos";
import { resumoDaExibicao } from "./cardapio-vivo";
import GavetaDoPrato, { type Lugar } from "./gaveta-do-prato";
import JanelaPratos from "./janela-pratos";
import JanelaSecao, { type Editando } from "./janela-secao";
import LinhaDoPrato, { faltasDo } from "./linha-do-prato";
import { BotaoSecao, PainelFaltas } from "./painel-faltas";

type Selecao = { tipo: cat.TipoDeSecao; id: number };

export default function AbaCardapio({ idCatalogo, podeEditar }: { idCatalogo: number; podeEditar: boolean }) {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeProduto = pode("cadastros.produtos");
  const [conteudo, setConteudo] = useState<cat.Conteudo | null>(null);
  const [erro, setErro] = useState("");
  const [sel, setSel] = useState<Selecao | null>(null);
  const [editando, setEditando] = useState<Editando | null>(null);
  const [pondo, setPondo] = useState(false);
  const [gaveta, setGaveta] = useState<number | null>(null);
  /** 🔑 "Só o que falta": os pratos sem foto, descrição ou preço, de todas as
   *  seções, para arrumar em sequência — quem conserta um vê ele sair da lista. */
  const [soFaltas, setSoFaltas] = useState(false);

  const recarregar = useCallback(async () => {
    try {
      setConteudo(await cat.conteudo(idCatalogo));
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [idCatalogo]);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  const categorias = useMemo(() => conteudo?.categorias ?? [], [conteudo]);

  /** A seção escolhida, já resolvida no conteúdo de AGORA. */
  const atual = useMemo(() => {
    for (const c of categorias) {
      if (sel?.tipo === "categoria" && sel.id === c.id) return { tipo: "categoria" as const, categoria: c, sub: null };
      const s = c.subcategorias.find((x) => sel?.tipo === "subcategoria" && x.id === sel.id);
      if (s) return { tipo: "subcategoria" as const, categoria: c, sub: s };
    }
    // 🔑 Sem escolha, abre a primeira seção que TEM pratos: "Menu Principal" que
    // só se divide abriria em "nenhum prato aqui", e parece cardápio vazio.
    for (const c of categorias) {
      if (c.itens.length) return { tipo: "categoria" as const, categoria: c, sub: null };
      const s = c.subcategorias.find((x) => x.itens.length);
      if (s) return { tipo: "subcategoria" as const, categoria: c, sub: s };
    }
    return categorias[0] ? { tipo: "categoria" as const, categoria: categorias[0], sub: null } : null;
  }, [categorias, sel]);

  const totalDa = (c: cat.Categoria) => c.itens.length + c.subcategorias.reduce((t, s) => t + s.itens.length, 0);

  /** Todas as listas do cardápio, na ordem da tela: a categoria e as subdivisões dela. */
  const lugares = useMemo<(Lugar & { itens: cat.ItemDoCatalogo[] })[]>(() => categorias.flatMap((c) => [
    { rotulo: c.nome, id_categoria: c.id, id_subcategoria: null, itens: c.itens },
    ...c.subcategorias.map((s) => ({ rotulo: `${c.nome} ▸ ${s.nome}`, id_categoria: c.id, id_subcategoria: s.id, itens: s.itens })),
  ]), [categorias]);

  const comFaltas = useMemo(
    () => lugares.map((l) => ({ ...l, itens: l.itens.filter((i) => faltasDo(i).length) })).filter((l) => l.itens.length),
    [lugares]);
  const totalFaltas = new Set(comFaltas.flatMap((l) => l.itens.map((i) => i.id_produto))).size;

  /** Onde está o item da gaveta — procurado no conteúdo de agora. */
  const naGaveta = useMemo(() => {
    if (gaveta === null) return null;
    for (const c of categorias) {
      const solto = c.itens.find((i) => i.id === gaveta);
      if (solto) return { item: solto, onde: c.nome };
      for (const s of c.subcategorias) {
        const i = s.itens.find((x) => x.id === gaveta);
        if (i) return { item: i, onde: `${c.nome} ▸ ${s.nome}` };
      }
    }
    return null;
  }, [categorias, gaveta]);

  /**
   * Sobe ou desce um prato na lista dele.
   * 🔑 **A lista inteira é renumerada e enviada de uma vez** (10, 20, 30…).
   * 🔑 **A tela troca as linhas NA HORA**: recarregar a árvore a cada clique
   * custava 2,5 s num cardápio de 59 pratos — medido.
   */
  async function moverPrato(itens: cat.ItemDoCatalogo[], indice: number, passo: number) {
    const destino = indice + passo;
    if (destino < 0 || destino >= itens.length) return;
    const fila = [...itens];
    [fila[indice], fila[destino]] = [fila[destino], fila[indice]];
    const ordens = fila.map((i, n) => ({ id: i.id, ordem: (n + 1) * 10 }));
    const posicao = new Map(ordens.map((o) => [o.id, o.ordem]));
    const trocar = (lista: cat.ItemDoCatalogo[]) =>
      lista.some((i) => posicao.has(i.id))
        ? lista.map((i) => ({ ...i, ordem: posicao.get(i.id) ?? i.ordem })).sort((a, b) => a.ordem - b.ordem)
        : lista;
    setConteudo((c) => c && {
      ...c,
      categorias: c.categorias.map((k) => ({
        ...k, itens: trocar(k.itens),
        subcategorias: k.subcategorias.map((s) => ({ ...s, itens: trocar(s.itens) })),
      })),
    });
    try {
      await cat.reordenarItens(ordens);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reordenar");
      // ⚠️ Falhando, volta ao que o SERVIDOR tem — não a uma ordem que não existe.
      await recarregar();
    }
  }

  async function moverSecao(tipo: cat.TipoDeSecao, irmas: cat.Secao[], indice: number, passo: number) {
    const destino = indice + passo;
    if (destino < 0 || destino >= irmas.length) return;
    const fila = [...irmas];
    [fila[indice], fila[destino]] = [fila[destino], fila[indice]];
    try {
      await cat.reordenarSecoes(tipo, fila);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reordenar");
    }
    await recarregar();
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!conteudo) return <Carregando />;

  const novaCategoria = () => setEditando({
    tipo: "categoria", secao: null, idPai: idCatalogo, ordemNova: (categorias.length + 1) * 10, itens: 0,
  });

  if (!categorias.length) {
    return (
      <div className="flex flex-col gap-4">
        <Vazio>
          O cardápio está vazio. Comece por uma seção — “Menu Principal”, “Bebidas”. Dentro dela
          vêm os pratos e, se quiser, subdivisões como “Pra Dividir”.
        </Vazio>
        {podeEditar && (
          <div><button type="button" className="btn btn-primario" onClick={novaCategoria}>+ Nova seção</button></div>
        )}
        {editando && (
          <JanelaSecao editando={editando} podeEditar={podeEditar} aoFechar={() => setEditando(null)}
                       aoSalvar={async (id) => { await recarregar(); setSel({ tipo: "categoria", id }); }}
                       aoMudar={recarregar} aoExcluir={recarregar} />
        )}
      </div>
    );
  }

  // A seção do painel e a lista de pratos dela.
  const a = atual!;
  const secao: cat.Secao = a.sub ?? a.categoria;
  const itens = a.sub ? a.sub.itens : a.categoria.itens;
  const irmas: cat.Secao[] = a.sub ? a.categoria.subcategorias : categorias;
  const indiceNaLista = irmas.findIndex((x) => x.id === secao.id);
  const onde = a.sub ? `${a.categoria.nome} ▸ ${a.sub.nome}` : a.categoria.nome;
  const ehSel = (tipo: cat.TipoDeSecao, id: number) => a.tipo === tipo && secao.id === id;

  // A seção da janela, resolvida no conteúdo de agora (a foto muda enquanto ela está aberta).
  const editandoAgora = editando && editando.secao
    ? { ...editando, secao: (editando.tipo === "categoria"
        ? categorias.find((c) => c.id === editando.secao!.id)
        : categorias.flatMap((c) => c.subcategorias).find((s) => s.id === editando.secao!.id)) ?? editando.secao }
    : editando;

  const abrirSecao = (tipo: cat.TipoDeSecao, s: cat.Secao, idPai: number, itensDela: number) =>
    setEditando({ tipo, secao: s, idPai, ordemNova: s.ordem, itens: itensDela });

  return (
    <div className="flex flex-col gap-4 md:grid md:grid-cols-[250px_minmax(0,1fr)] md:items-start md:gap-6">
      {/* --------------------------------------------------- as seções --- */}
      <nav aria-label="seções do cardápio"
           className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 md:sticky md:top-4 md:mx-0 md:flex-col md:gap-0.5 md:overflow-visible md:px-0">
        <span className="rotulo hidden px-2 pb-1 md:block">Seções</span>
        {totalFaltas > 0 && (
          <button type="button" aria-pressed={soFaltas} onClick={() => setSoFaltas(!soFaltas)}
                  className={`flex shrink-0 items-center justify-between gap-3 rounded-md border px-3 py-1.5 text-left text-[13.5px] md:mb-2 md:w-full ${
                    soFaltas ? "border-alerta bg-alerta-claro text-alerta" : "border-alerta/40 text-alerta hover:bg-alerta-claro"}`}>
            <span>⚠ O que falta</span>
            <span className="mono text-[12px]">{totalFaltas}</span>
          </button>
        )}
        {categorias.map((c) => (
          <div key={c.id} className="contents md:block">
            <BotaoSecao nome={c.nome} total={totalDa(c)} ativo={!soFaltas && ehSel("categoria", c.id)}
                        aoClicar={() => { setSoFaltas(false); setSel({ tipo: "categoria", id: c.id }); }} />
            {c.subcategorias.map((s) => (
              <BotaoSecao key={s.id} nome={s.nome} total={s.itens.length} sub
                          ativo={!soFaltas && ehSel("subcategoria", s.id)}
                          aoClicar={() => { setSoFaltas(false); setSel({ tipo: "subcategoria", id: s.id }); }} />
            ))}
          </div>
        ))}
        {podeEditar && (
          <button type="button" className="link-acao shrink-0 md:mt-2 md:self-start" onClick={novaCategoria}>
            + seção
          </button>
        )}
      </nav>

      {/* ------------------------------------------- o que falta --- */}
      {soFaltas && totalFaltas > 0 ? (
        <PainelFaltas listas={comFaltas} aoAbrir={setGaveta} />
      ) : (
      /* ----------------------------------------- a seção escolhida --- */
      <section className="cartao min-w-0" aria-label={`seção ${secao.nome}`}>
        <header className="flex flex-wrap items-start gap-3 border-b border-linha px-5 py-4">
          {secao.foto_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={urlArquivo(secao.foto_url) ?? undefined} alt=""
                 className="h-12 w-12 shrink-0 rounded-lg border border-linha object-cover" />
          )}
          <div className="min-w-0 flex-1">
            {a.sub && <p className="rotulo">{a.categoria.nome}</p>}
            <h2 className="text-[18px] font-bold tracking-tight">{secao.nome}</h2>
            {secao.descricao && <p className="mt-0.5 text-[13.5px] text-suave">{secao.descricao}</p>}
            <p className="mt-1 text-[12.5px] text-suave">
              No Cardápio Vivo: <span className="text-tinta">{resumoDaExibicao(secao)}</span>
              {!secao.foto_url && " · sem foto"}
            </p>
          </div>
          <span className="flex flex-wrap items-center gap-1.5">
            {podeEditar && (
              <>
                <button type="button" className="link-acao" disabled={indiceNaLista <= 0}
                        aria-label={`subir a seção ${secao.nome}`}
                        onClick={() => void moverSecao(a.tipo, irmas, indiceNaLista, -1)}>↑</button>
                <button type="button" className="link-acao" disabled={indiceNaLista >= irmas.length - 1}
                        aria-label={`descer a seção ${secao.nome}`}
                        onClick={() => void moverSecao(a.tipo, irmas, indiceNaLista, 1)}>↓</button>
              </>
            )}
            <button type="button" className="link-acao"
                    onClick={() => abrirSecao(a.tipo, secao, a.sub ? a.categoria.id : idCatalogo,
                                              a.sub ? a.sub.itens.length : totalDa(a.categoria))}>
              {podeEditar ? "editar seção" : "ver seção"}
            </button>
            {podeEditar && !a.sub && (
              <button type="button" className="link-acao"
                      onClick={() => setEditando({ tipo: "subcategoria", secao: null, idPai: a.categoria.id,
                        ordemNova: (a.categoria.subcategorias.length + 1) * 10, itens: 0 })}>
                + subdivisão
              </button>
            )}
          </span>
        </header>

        <div className="p-5">
          {/* 🔑 Categoria que se divide: as subdivisões vêm primeiro, como atalho —
              os pratos "direto" nela são os que não caem em nenhuma. */}
          {!a.sub && a.categoria.subcategorias.length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-2 text-[13.5px]">
              <span className="text-suave">Se divide em</span>
              {a.categoria.subcategorias.map((s) => (
                <button key={s.id} type="button" className="link-acao"
                        onClick={() => setSel({ tipo: "subcategoria", id: s.id })}>
                  {s.nome} ({s.itens.length})
                </button>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between gap-3">
            <span className="rotulo">
              {!a.sub && a.categoria.subcategorias.length > 0 ? `Pratos direto em ${secao.nome}` : "Pratos"}
              {itens.length > 0 && ` · ${itens.length}`}
            </span>
            {podeEditar && (
              <button type="button" className="btn btn-primario" onClick={() => setPondo(true)}>+ pratos</button>
            )}
          </div>

          {itens.length === 0 ? (
            <p className="py-4 text-[13.5px] text-suave">Nenhum prato aqui ainda.</p>
          ) : (
            <ul className="mt-2 flex flex-col gap-px bg-linha">
              {itens.map((i, n) => (
                <LinhaDoPrato key={i.id} item={i} primeiro={n === 0} ultimo={n === itens.length - 1}
                              podeEditar={podeEditar} aoAbrir={() => setGaveta(i.id)}
                              aoMover={(passo) => void moverPrato(itens, n, passo)} />
              ))}
            </ul>
          )}
        </div>
      </section>
      )}

      {editandoAgora && (
        <JanelaSecao editando={editandoAgora} podeEditar={podeEditar} aoFechar={() => setEditando(null)}
                     aoSalvar={async (id) => { await recarregar(); setSel({ tipo: editandoAgora.tipo, id }); }}
                     aoMudar={recarregar}
                     aoExcluir={async () => { setSel(null); await recarregar(); }} />
      )}
      {pondo && (
        <JanelaPratos idCategoria={a.categoria.id} idSubcategoria={a.sub?.id ?? null} onde={onde}
                      jaEstao={new Set(itens.map((i) => i.id_produto))}
                      aoFechar={() => setPondo(false)} aoPor={recarregar} />
      )}
      {naGaveta && (
        <GavetaDoPrato key={naGaveta.item.id} item={naGaveta.item} onde={naGaveta.onde} lugares={lugares}
                       podeEditar={podeEditar} podeProduto={podeProduto}
                       aoMudar={recarregar} aoFechar={() => setGaveta(null)} />
      )}
    </div>
  );
}
