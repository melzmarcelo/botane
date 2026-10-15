"use client";

/**
 * O Cardápio Vivo da mesa — um prato por tela, com rolagem que encaixa.
 *
 * 🔑 **Pedido do dono (14/10/2026)**, estudo em `docs/cardapio-vivo-estudo.md`.
 * 🔑 O topo leva as categorias, e a ativa ACOMPANHA a rolagem: quem rola até as bebidas
 * vê "Bebidas" acender sem tocar em nada. Tocar leva até a categoria.
 * ⚠️ Sem service worker e sem a casca do sistema: esta tela é do cliente, no celular dele.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { buscarFeed, imagem, previaFeed, type Feed, type Idioma, type ItemFeed as Item } from "@/lib/cardapio-vivo";
import Chamados from "./chamados";
import Detalhe from "./detalhe";
import { useFavoritos } from "./favoritos";
import Hub from "./hub";
import { Medidor, medicaoRecusada, recusarMedicao } from "./eventos";
import ItemFeed from "./item-feed";
import { useSelecao, type EscolhaAdicional } from "./selecao";
import TelaPedido from "./tela-pedido";
import TelaSelecao from "./tela-selecao";
import { idiomaDoNavegador, nomeRestricao, textos } from "./textos";

const FONTES: Record<string, { familia: string; url?: string }> = {
  NEWSREADER: { familia: "'Newsreader', Georgia, serif" },
  PLAYFAIR: { familia: "'Playfair Display', Georgia, serif",
              url: "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600&display=swap" },
  LORA: { familia: "'Lora', Georgia, serif",
          url: "https://fonts.googleapis.com/css2?family=Lora:wght@500;600&display=swap" },
  CORMORANT: { familia: "'Cormorant Garamond', Georgia, serif",
               url: "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&display=swap" },
};
const CHAVE_AVISO = "cardapio.aviso_cookies";

function economiaDeDados(): boolean {
  const c = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  return !!c && (c.saveData === true || ["slow-2g", "2g"].includes(c.effectiveType ?? ""));
}

type Props = { loja: number; token: string | null; idCatalogoPrevia?: number };

export default function CardapioVivo({ loja, token, idCatalogoPrevia }: Props) {
  const [idioma, setIdioma] = useState<Idioma>("pt");
  const [feed, setFeed] = useState<Feed | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [ativo, setAtivo] = useState(0);
  const [filtro, setFiltro] = useState<string[]>([]);
  const [filtroAberto, setFiltroAberto] = useState(false);
  const [aberto, setAberto] = useState<Item | null>(null);
  const [verSelecao, setVerSelecao] = useState(false);
  const [aviso, setAviso] = useState(false);
  const [economia, setEconomia] = useState(false);
  // O Hub (114) aparece UMA vez, na chegada — trocar o idioma não o traz de volta.
  const [noHub, setNoHub] = useState(false);
  const hubDecidido = useRef(false);
  const [verFavoritos, setVerFavoritos] = useState(false);
  const favoritos = useFavoritos(loja || -1);
  // Rolagem que a TELA fez (tocar numa categoria) não é deslize do cliente.
  const rolagemDaTela = useRef(false);
  const anterior = useRef<number | null>(null);
  const rolagem = useRef<HTMLDivElement>(null);
  const barra = useRef<HTMLDivElement>(null);
  const medidor = useRef<Medidor | null>(null);
  const selecao = useSelecao(loja, token);
  const previa = idCatalogoPrevia !== undefined;
  // 🔑 **No modo PEDIDO** (fase 2, 115), a "minha seleção" vira o carrinho que vai ao painel —
  // a mesma lista no aparelho, com os rótulos de pedido. Sem mesa, nunca há pedido.
  const modoPedido = feed?.modo === "PEDIDO" && !!token;
  const base = textos(idioma);
  const t = modoPedido
    ? { ...base, adicionarSelecao: base.adicionarPedido, adicionado: base.noPedido, minhaSelecao: base.meuPedido }
    : base;
  const sessao = useCallback(() => medidor.current?.idSessao ?? "", []);

  useEffect(() => {
    // O site de reservas manda o idioma que a pessoa escolheu lá (`?idioma=en`); sem
    // ele, vale o do navegador.
    const pedido = new URLSearchParams(window.location.search).get("idioma");
    setIdioma(pedido === "en" || pedido === "de" || pedido === "pt" ? pedido : idiomaDoNavegador());
    setEconomia(economiaDeDados());
    try {
      setAviso(!previa && !localStorage.getItem(CHAVE_AVISO));
    } catch {
      setAviso(!previa);
    }
  }, [previa]);

  const carregar = useCallback(async () => {
    setErro(null);
    if (previa) {
      try {
        setFeed(await previaFeed(idCatalogoPrevia!));
      } catch (e) {
        setErro((e as Error).message);
      }
      return;
    }
    const r = await buscarFeed(loja, token, idioma);
    if ("feed" in r) setFeed(r.feed);
    else setErro(r.erro);
  }, [loja, token, idioma, previa, idCatalogoPrevia]);

  useEffect(() => { void carregar(); }, [carregar]);

  // O medidor nasce com o feed (o modo vem dele) e morre com a página.
  useEffect(() => {
    if (!feed || previa) return;
    const m = new Medidor(feed.loja.id, token, feed.modo, idioma);
    medidor.current = m;
    m.iniciar();
    if (!hubDecidido.current) {
      hubDecidido.current = true;
      if (feed.hub) {
        setNoHub(true);
        m.registrar("abriu_hub");
      } else {
        m.registrar("abriu_cardapio");
      }
    }
    return () => m.parar();
  }, [feed, token, idioma, previa]);

  const itens = useMemo(() => (feed?.itens ?? []).filter(
    (i) => filtro.every((r) => i.restricoes.includes(r))), [feed, filtro]);

  // 🔑 Quem decide o "visível" é o observador: ≥ 50% da tela é ver o prato.
  useEffect(() => {
    const raiz = rolagem.current;
    if (!raiz || !itens.length) return;
    const obs = new IntersectionObserver((entradas) => {
      for (const e of entradas) {
        const id = Number((e.target as HTMLElement).dataset.item);
        const item = itens.find((i) => i.id === id);
        if (!item) continue;
        if (e.intersectionRatio >= 0.5) {
          setAtivo(itens.indexOf(item));
          medidor.current?.comecouAVer(id, item.midia.tipo);
        } else {
          medidor.current?.parouDeVer(id);
        }
      }
    }, { root: raiz, threshold: [0, 0.5] });
    raiz.querySelectorAll(".cv-item").forEach((el) => obs.observe(el));
    anterior.current = null;
    return () => obs.disconnect();
  }, [itens, noHub]);

  // 🔑 **O deslize** (114): para a frente, ou de volta a um prato já visto — o segundo é
  // sinal de interesse. ⚠️ Ignora a rolagem que a própria tela fez ao tocar numa categoria.
  useEffect(() => {
    const antes = anterior.current;
    anterior.current = ativo;
    if (antes === null || antes === ativo || rolagemDaTela.current) return;
    const item = itens[ativo];
    if (item) medidor.current?.registrar(ativo > antes ? "deslizou_frente" : "deslizou_tras",
                                         { item: item.id, midia: item.midia.tipo });
  }, [ativo, itens]);

  const categoriaAtiva = itens[ativo]?.id_categoria;
  const categorias = useMemo(() => (feed?.categorias ?? []).filter(
    (c) => itens.some((i) => i.id_categoria === c.id)), [feed, itens]);

  // A pílula da categoria ativa entra na tela sozinha (a barra rola de lado).
  useEffect(() => {
    const el = barra.current?.querySelector<HTMLElement>(`[data-cat="${categoriaAtiva}"]`);
    el?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
  }, [categoriaAtiva]);

  const irPara = (idCategoria: number) => {
    medidor.current?.registrar("tocou_categoria", { categoria: idCategoria });
    const el = rolagem.current?.querySelector<HTMLElement>(`[data-categoria="${idCategoria}"]`);
    rolagemDaTela.current = true;
    el?.scrollIntoView({ behavior: "smooth" });
    setTimeout(() => { rolagemDaTela.current = false; }, 1200);
  };

  const irParaItem = (idItem: number) => {
    setVerFavoritos(false);
    const el = rolagem.current?.querySelector<HTMLElement>(`[data-item="${idItem}"]`);
    rolagemDaTela.current = true;
    el?.scrollIntoView();
    setTimeout(() => { rolagemDaTela.current = false; }, 600);
  };

  const favoritar = (item: Item) => {
    const ficou = favoritos.alternar(item.id);
    medidor.current?.registrar(ficou ? "favoritou" : "desfavoritou", { item: item.id, midia: item.midia.tipo });
  };

  const adicionar = (item: Item, quantidade: number, adicionais: EscolhaAdicional[]) => {
    selecao.adicionar({ id_item: item.id, nome: item.nome, preco: item.preco, quantidade, adicionais });
    medidor.current?.registrar("adicionou", { item: item.id, midia: item.midia.tipo });
    setAberto(null);
  };

  const abrirDetalhe = (item: Item) => {
    medidor.current?.registrar("abriu_detalhe", { item: item.id, midia: item.midia.tipo });
    // A personalização (114) é abrir as escolhas de um prato que TEM adicionais.
    if (item.adicionais.length) medidor.current?.registrar("abriu_personalizacao", { item: item.id, midia: item.midia.tipo });
    setAberto(item);
  };

  const fonte = FONTES[feed?.marca.fonte ?? "NEWSREADER"] ?? FONTES.NEWSREADER;
  const estilo = {
    "--cv-principal": feed?.marca.cor_principal ?? "#3C4A3E",
    "--cv-fundo": feed?.marca.cor_fundo ?? "#F3EFE4",
    "--cv-tinta": "#1B211C",
    "--cv-serif": fonte.familia,
  } as React.CSSProperties;

  if (erro) {
    return (
      <main style={estilo} className="flex min-h-[100dvh] flex-col items-center justify-center gap-4 bg-[var(--cv-fundo)] px-8 text-center text-[var(--cv-tinta)]">
        <p className="cv-serif text-2xl">{t.erro}</p>
        <p className="opacity-70">{erro}</p>
        <button type="button" onClick={() => void carregar()} className="rounded-full bg-[var(--cv-principal)] px-5 py-2.5 text-white">
          {t.tentar}
        </button>
      </main>
    );
  }
  if (!feed) {
    return <main style={estilo} className="min-h-[100dvh] animate-pulse bg-[#2a2f28]" aria-busy />;
  }

  if (noHub && feed.hub) {
    return (
      <div style={estilo}>
        {fonte.url && <link rel="stylesheet" href={fonte.url} />}
        <Hub feed={feed} t={t}
             aoVerCardapio={() => { setNoHub(false); medidor.current?.registrar("abriu_cardapio"); }}
             aoAvaliar={() => medidor.current?.registrar("clicou_avaliacao")}
             aoAbrirWifi={() => medidor.current?.registrar("clicou_wifi")} />
      </div>
    );
  }

  return (
    // 🔑 **No computador, o feed é uma COLUNA de celular no centro** (pedido do dono,
    // 14/10/2026: "não ficou bem visualmente na web, no mobile sim"). Esticado na
    // largura do monitor, a foto vertical virava um recorte ampliado e os controles
    // iam para cantos opostos. ⚠️ O `transform` não é enfeite: ele faz as camadas
    // `fixed inset-0` (detalhe, favoritos, seleção) ficarem presas DENTRO da coluna.
    <div className="min-h-[100dvh] bg-[#0f0f0f] md:flex md:justify-center">
    <main style={estilo}
          className="relative h-[100dvh] w-full overflow-hidden bg-black text-white md:max-w-[480px] md:shadow-[0_0_80px_rgba(0,0,0,0.7)] md:[transform:translateZ(0)]">
      {fonte.url && <link rel="stylesheet" href={fonte.url} />}

      <header className="absolute inset-x-0 top-0 z-30 bg-gradient-to-b from-black/70 to-transparent pb-6 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <div className="flex items-center gap-3 px-4">
          {feed.marca.logo && (
            <img src={imagem(feed.marca.logo, 320) ?? undefined} alt={feed.loja.casa}
                 className="h-8 w-8 rounded-full bg-white object-contain" />
          )}
          <div className="min-w-0 flex-1 leading-tight">
            <p className="truncate text-sm font-semibold">{feed.loja.casa}</p>
            <p className="truncate text-xs opacity-80">
              {feed.mesa ? `${t.mesa} ${feed.mesa.nome} · ${feed.mesa.salao}` : feed.cardapio}
            </p>
          </div>
          <select value={idioma} onChange={(e) => setIdioma(e.target.value as Idioma)} aria-label="Idioma"
                  className="rounded-full bg-white/15 px-2 py-1 text-xs backdrop-blur">
            <option value="pt">PT</option><option value="en">EN</option><option value="de">DE</option>
          </select>
          <button type="button" onClick={() => setFiltroAberto((v) => !v)} aria-expanded={filtroAberto}
                  className={`rounded-full px-3 py-1 text-xs backdrop-blur ${filtro.length ? "bg-white text-black" : "bg-white/15"}`}>
            {t.filtrar}{filtro.length ? ` (${filtro.length})` : ""}
          </button>
          {feed.chamar_garcom && token && (
            <Chamados token={token} sessao={sessao} t={t}
                      aoChamar={(tipo) => medidor.current?.registrar(tipo === "CONTA" ? "pediu_conta" : "chamou_garcom")} />
          )}
          <button type="button" onClick={() => setVerFavoritos(true)} aria-label={t.meusFavoritos}
                  className="rounded-full bg-white/15 px-3 py-1 text-xs backdrop-blur">
            ♥ {favoritos.ids.filter((id) => feed.itens.some((i) => i.id === id)).length}
          </button>
          <button type="button" onClick={() => setVerSelecao(true)}
                  className="rounded-full bg-[var(--cv-fundo)] px-3 py-1 text-xs font-semibold text-[var(--cv-tinta)]">
            {modoPedido ? "🛒" : "★"} {selecao.quantidade}
          </button>
        </div>
        {filtroAberto && (
          <div className="mt-2 flex flex-wrap gap-2 px-4" role="group" aria-label={t.filtros}>
            {feed.restricoes.map((r) => {
              const on = filtro.includes(r.chave);
              return (
                <button key={r.chave} type="button" aria-pressed={on}
                        onClick={() => setFiltro((f) => (on ? f.filter((x) => x !== r.chave) : [...f, r.chave]))}
                        className={`rounded-full border px-3 py-1 text-xs ${on ? "border-white bg-white text-black" : "border-white/60"}`}>
                  {nomeRestricao(idioma, r.chave)}
                </button>
              );
            })}
          </div>
        )}
        <nav ref={barra} className="mt-2 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none]" aria-label="Categorias">
          {categorias.map((c) => (
            <button key={c.id} type="button" data-cat={c.id} onClick={() => irPara(c.id)}
                    aria-current={c.id === categoriaAtiva}
                    className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm transition ${
                      c.id === categoriaAtiva ? "bg-white font-semibold text-black" : "bg-white/15 backdrop-blur"}`}>
              {c.nome}
            </button>
          ))}
        </nav>
        {(feed.aviso || feed.previa) && (
          <p className="mx-4 mt-2 rounded-xl bg-amber-400/90 px-3 py-1.5 text-xs font-medium text-black">
            {feed.previa ? t.previa : feed.aviso}
          </p>
        )}
      </header>

      <div ref={rolagem} className="h-[100dvh] snap-y snap-mandatory overflow-y-scroll overscroll-y-contain [scrollbar-width:none]">
        {itens.length === 0 && (
          <div className="flex h-[100dvh] flex-col items-center justify-center gap-3 px-8 text-center">
            <p>{t.nenhumComFiltro}</p>
            <button type="button" onClick={() => setFiltro([])} className="rounded-full bg-white px-4 py-2 text-black">
              {t.limparFiltro}
            </button>
          </div>
        )}
        {itens.map((item, i) => (
          <ItemFeed
            key={item.id}
            item={item}
            indice={i}
            ativo={i === ativo}
            perto={Math.abs(i - ativo) <= 1}
            economia={economia}
            selecionados={selecao.linhas.filter((l) => l.id_item === item.id).reduce((s, l) => s + l.quantidade, 0)}
            favorito={favoritos.eh(item.id)}
            aoFavoritar={() => favoritar(item)}
            t={t}
            idioma={idioma}
            aoAbrir={() => abrirDetalhe(item)}
            aoAdicionar={() => adicionar(item, 1, [])}
          />
        ))}
      </div>

      {aviso && (
        // ⚠️ Embaixo da barra, NÃO no rodapé: no rodapé ele tapava o nome e o preço do primeiro prato.
        <div className="absolute inset-x-3 top-[calc(env(safe-area-inset-top)+6.5rem)] z-50 rounded-2xl bg-[var(--cv-fundo)]/95 p-3.5 text-[13px] text-[var(--cv-tinta)] shadow-2xl backdrop-blur">
          <p>{t.cookies}</p>
          <div className="mt-3 flex justify-end gap-2">
            <button type="button" className="rounded-full px-3 py-1.5 opacity-70" onClick={() => {
              recusarMedicao(true); medidor.current?.desligar(true);
              try { localStorage.setItem(CHAVE_AVISO, "1"); } catch { /* só não lembra */ }
              setAviso(false);
            }}>{t.naoQuero}</button>
            <button type="button" className="rounded-full bg-[var(--cv-principal)] px-4 py-1.5 font-semibold text-white" onClick={() => {
              if (medicaoRecusada()) { recusarMedicao(false); medidor.current?.desligar(false); }
              try { localStorage.setItem(CHAVE_AVISO, "1"); } catch { /* só não lembra */ }
              setAviso(false);
            }}>{t.entendi}</button>
          </div>
        </div>
      )}

      {aberto && (
        <Detalhe item={aberto} t={t} idioma={idioma} aoFechar={() => setAberto(null)}
                 aoEscolher={() => medidor.current?.registrar("escolheu_opcao", { item: aberto.id, midia: aberto.midia.tipo })}
                 aoAdicionar={(q, ad) => adicionar(aberto, q, ad)} />
      )}
      {verFavoritos && (
        <div className="fixed inset-0 z-40 flex flex-col bg-[var(--cv-fundo)] text-[var(--cv-tinta)]" role="dialog"
             aria-modal aria-label={t.meusFavoritos}>
          <header className="flex items-center justify-between border-b border-current/10 px-5 pb-3 pt-[max(1rem,env(safe-area-inset-top))]">
            <h2 className="cv-serif text-2xl">{t.meusFavoritos}</h2>
            <button type="button" onClick={() => setVerFavoritos(false)} aria-label={t.fechar}
                    className="rounded-full px-3 py-1 text-3xl leading-none opacity-60">×</button>
          </header>
          <ul className="flex-1 divide-y divide-current/10 overflow-y-auto px-5">
            {feed.itens.filter((i) => favoritos.eh(i.id)).map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-3 py-3">
                <button type="button" className="text-left text-lg" onClick={() => irParaItem(i.id)}>{i.nome}</button>
                <button type="button" onClick={() => favoritar(i)} aria-label={t.desfavoritar} className="text-2xl">♥</button>
              </li>
            ))}
            {!feed.itens.some((i) => favoritos.eh(i.id)) && <li className="py-10 text-center opacity-70">{t.semFavoritos}</li>}
          </ul>
        </div>
      )}
      {verSelecao && modoPedido && (
        <TelaPedido
          linhas={selecao.linhas}
          total={selecao.total}
          algumSemPreco={selecao.algumSemPreco}
          mesa={feed.mesa ? `${t.mesa} ${feed.mesa.nome}` : null}
          token={token!}
          loja={feed.loja.id}
          sessao={sessao}
          t={t}
          aoRemover={(l) => {
            selecao.remover(l.chave);
            const item = feed.itens.find((i) => i.id === l.id_item);
            medidor.current?.registrar("removeu", { item: l.id_item, midia: item?.midia.tipo });
          }}
          aoEnviado={() => {
            // O carrinho que foi vira pedido: esvazia SEM "removeu" (não é desistência).
            medidor.current?.registrar("enviou_pedido");
            medidor.current?.enviar();
            selecao.limpar();
          }}
          aoFechar={() => setVerSelecao(false)}
        />
      )}
      {verSelecao && !modoPedido && (
        <TelaSelecao
          linhas={selecao.linhas}
          total={selecao.total}
          algumSemPreco={selecao.algumSemPreco}
          mesa={feed.mesa ? `${t.mesa} ${feed.mesa.nome}` : null}
          t={t}
          aoRemover={(l) => {
            selecao.remover(l.chave);
            const item = feed.itens.find((i) => i.id === l.id_item);
            medidor.current?.registrar("removeu", { item: l.id_item, midia: item?.midia.tipo });
          }}
          aoLimpar={() => {
            for (const l of selecao.linhas) medidor.current?.registrar("removeu", { item: l.id_item });
            selecao.limpar();
          }}
          aoFechar={() => setVerSelecao(false)}
        />
      )}
    </main>
    </div>
  );
}
