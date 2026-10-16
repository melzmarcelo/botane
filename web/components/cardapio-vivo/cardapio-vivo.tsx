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
import { buscarFeed, enderecoDoSite, imagem, previaFeed, type AnuncioFeed, type Feed, type Idioma, type ItemFeed as Item } from "@/lib/cardapio-vivo";
import Chamados from "./chamados";
import Detalhe from "./detalhe";
import { useFavoritos } from "./favoritos";
import Hub from "./hub";
import { Medidor, medicaoRecusada, recusarMedicao, sessaoParaTestes } from "./eventos";
import CartaoFeed from "./cartao-feed";
import ItemFeed from "./item-feed";
import SeletorDeIdioma, { idiomaDaAba, lembrarIdioma } from "./seletor-idioma";
import { montarSequencia } from "./sequencia";
import { useSelecao, type EscolhaAdicional } from "./selecao";
import TelaPedido from "./tela-pedido";
import TelaSelecao from "./tela-selecao";
import { idiomaDoNavegador, nomeRestricao, textos } from "./textos";

// 🔑 As MESMAS do site (15/10/2026: um layout só); FRAUNCES é a do protótipo e o padrão.
const FONTES: Record<string, { familia: string; url?: string }> = {
  FRAUNCES: { familia: "Fraunces, Georgia, serif",
              url: "https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,300;9..144,400;9..144,600&display=swap" },
  NEWSREADER: { familia: "'Newsreader', Georgia, serif" },
  PLAYFAIR: { familia: "'Playfair Display', Georgia, serif",
              url: "https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600&display=swap" },
  LORA: { familia: "'Lora', Georgia, serif",
          url: "https://fonts.googleapis.com/css2?family=Lora:wght@500;600&display=swap" },
  CORMORANT: { familia: "'Cormorant Garamond', Georgia, serif",
               url: "https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&display=swap" },
};
/* As letras do corpo e dos números do SITE (Karla e DM Mono), em todas as telas do feed. */
const LETRAS_DO_SITE = "https://fonts.googleapis.com/css2?family=Karla:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap";
const CHAVE_AVISO = "cardapio.aviso_cookies";

function economiaDeDados(): boolean {
  const c = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
  return !!c && (c.saveData === true || ["slow-2g", "2g"].includes(c.effectiveType ?? ""));
}

/** `cardapio`: o nome no link de um Cardápio Vivo que não é o principal (117). */
type Props = { loja: number; token: string | null; cardapio?: string | null; idCatalogoPrevia?: number };

export default function CardapioVivo({ loja, token, cardapio = null, idCatalogoPrevia }: Props) {
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
  // ⚠️ A seleção guardada é de CADA cardápio: a do catering não pode aparecer na da mesa.
  const selecao = useSelecao(loja, token ?? (cardapio ? `cardapio-${cardapio}` : null));
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
    // 🔑 16/10/2026: o `?idioma=` do link, senão o que a pessoa já escolheu NESTA aba (no site
    // ou aqui, a mesma chave), senão o do navegador. O do link é gravado na aba, para o "voltar
    // ao site" manter a escolha.
    const pedido = new URLSearchParams(window.location.search).get("idioma");
    const doLink = pedido === "en" || pedido === "de" || pedido === "pt" ? pedido : null;
    if (doLink) lembrarIdioma(doLink);
    setIdioma(doLink ?? idiomaDaAba() ?? idiomaDoNavegador());
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
    const r = await buscarFeed(loja, token, idioma, sessaoParaTestes(), cardapio);
    if ("feed" in r) setFeed(r.feed);
    else setErro(r.erro);
  }, [loja, token, cardapio, idioma, previa, idCatalogoPrevia]);

  useEffect(() => { void carregar(); }, [carregar]);

  // O medidor nasce com o feed (o modo vem dele) e morre com a página.
  useEffect(() => {
    if (!feed || previa) return;
    const m = new Medidor(feed.loja.id, token, feed.modo, idioma, false, feed.vivo?.id_catalogo ?? null);
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
  // 🔑 Os pratos com os cartões de conteúdo entre eles (120) e os anúncios pelas regras da casa
  // (121). Com filtro, só pratos. A semente do sorteio é a sessão anônima: mesma visita, mesma ordem.
  const [semente] = useState(() => (typeof window === "undefined" ? "" : sessaoParaTestes() ?? String(Math.random())));
  const seq = useMemo(() => montarSequencia(itens, feed?.categorias ?? [], feed?.cartoes ?? [],
                                            filtro.length === 0, {
                                              aberturas: feed?.aberturas, anuncios: feed?.anuncios,
                                              regras: feed?.regras_anuncio, semente,
                                            }), [itens, feed, filtro, semente]);

  // 🔑 Quem decide o "visível" é o observador: ≥ 50% da tela é ver o prato (ou o cartão).
  useEffect(() => {
    const raiz = rolagem.current;
    if (!raiz || !seq.length) return;
    const obs = new IntersectionObserver((entradas) => {
      for (const e of entradas) {
        const pos = Number((e.target as HTMLElement).dataset.pos);
        const passo = seq[pos];
        if (!passo) continue;
        const visto = e.intersectionRatio >= 0.5;
        if (visto) setAtivo(pos);
        if (passo.tipo === "prato") {
          if (visto) medidor.current?.comecouAVer(passo.item.id, passo.item.midia.tipo);
          else medidor.current?.parouDeVer(passo.item.id);
        } else if (visto) {
          medidor.current?.comecouAVerConteudo(passo.chave,
            passo.tipo === "cartao" ? { tipo: "viu_cartao", cartao: passo.cartao.id, midia: passo.cartao.midia.tipo }
            : passo.tipo === "anuncio" ? { tipo: "viu_anuncio", anuncio: passo.anuncio.id, midia: passo.anuncio.midia.tipo }
            : { tipo: "viu_secao", categoria: passo.id_categoria, subcategoria: passo.id_subcategoria ?? undefined,
                midia: passo.secao.video ? "VIDEO" : "FOTO" });
        } else {
          medidor.current?.parouDeVerConteudo(passo.chave);
        }
      }
    }, { root: raiz, threshold: [0, 0.5] });
    raiz.querySelectorAll("[data-pos]").forEach((el) => obs.observe(el));
    anterior.current = null;
    return () => obs.disconnect();
  }, [seq, noHub]);

  // 🔑 **O deslize** (114): para a frente, ou de volta a um prato já visto — o segundo é
  // sinal de interesse. ⚠️ Ignora a rolagem que a própria tela fez ao tocar numa categoria.
  useEffect(() => {
    const antes = anterior.current;
    anterior.current = ativo;
    if (antes === null || antes === ativo || rolagemDaTela.current) return;
    // O deslize é do PRATO: chegar a um cartão não conta (120).
    const passo = seq[ativo];
    if (passo?.tipo === "prato") medidor.current?.registrar(ativo > antes ? "deslizou_frente" : "deslizou_tras",
                                                             { item: passo.item.id, midia: passo.item.midia.tipo });
  }, [ativo, seq]);

  // A abertura do cardápio não é de seção nenhuma: acende a primeira.
  const categoriaAtiva = seq[ativo]?.id_categoria ?? itens[0]?.id_categoria;
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

  /**
   * 🔑 O botão do anúncio (121): abrir um catálogo da casa (o feed dele, se for Cardápio Vivo;
   * senão o site), ir a um prato DESTE cardápio, ou um link — em outra aba, para o cardápio ficar.
   * ⚠️ O toque é medido e o lote sai ANTES de trocar de página, senão o clique se perde.
   */
  function acaoDoAnuncio(a: AnuncioFeed): (() => void) | undefined {
    const medir = () => {
      medidor.current?.registrar("clicou_anuncio", { anuncio: a.id });
      medidor.current?.enviar();
    };
    const { tipo, slug, catalogo, item, url } = a.acao;
    if (tipo === "CATALOGO" && catalogo && feed) {
      return () => {
        medir();
        const q = new URLSearchParams(idioma !== "pt" ? { idioma } : {});
        window.location.assign(slug
          ? `/c/${feed.loja.id}?${new URLSearchParams({ cardapio: slug, ...(idioma !== "pt" ? { idioma } : {}) })}`
          : `${enderecoDoSite()}?loja=${feed.loja.id}&catalogo=${catalogo}${q.toString() ? `&${q}` : ""}`);
      };
    }
    if (tipo === "PRATO" && item && itens.some((x) => x.id === item)) return () => { medir(); irParaItem(item); };
    if (tipo === "LINK" && url) return () => { medir(); window.open(url, "_blank", "noopener"); };
    return undefined;
  }

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

  /**
   * 🔑 **A encomenda do catering** (15/10/2026): a seleção vira o carrinho do SITE, que já sabe
   * retirada/entrega, quando, pagamento e identificação — o site e o feed estão no mesmo
   * endereço, então a aba é a mesma. ⚠️ O pedido do site não tem adicionais: as escolhas vão
   * na observação do item, e a casa confere o preço delas ao confirmar.
   */
  function encomendar() {
    if (!feed) return;
    type ItemCarrinho = { id: number; nome: string; preco: number | null; quantidade: number; observacao: string };
    const itens: Record<string, ItemCarrinho> = {};
    for (const l of selecao.linhas) {
      const atual = itens[l.id_item] ?? { id: l.id_item, nome: l.nome, preco: l.preco, quantidade: 0, observacao: "" };
      atual.quantidade += l.quantidade;
      if (l.adicionais.length) {
        atual.observacao = [atual.observacao, `${l.quantidade}× ${l.adicionais.map((a) => a.nome).join(", ")}`]
          .filter(Boolean).join("; ").slice(0, 200);
      }
      itens[l.id_item] = atual;
    }
    try {
      sessionStorage.setItem("botane.carrinho", JSON.stringify({
        id_catalogo: feed.vivo.id_catalogo,
        chave: (crypto.randomUUID?.() ?? `${Date.now()}${Math.random()}`).slice(0, 60),
        itens,
      }));
      sessionStorage.setItem("botane.idioma", idioma);
    } catch {
      /* sem armazenamento: o site abre o cardápio, e o pedido se monta lá */
    }
    medidor.current?.registrar("enviou_pedido");
    medidor.current?.enviar();
    window.location.assign(`${enderecoDoSite()}?loja=${feed.loja.id}&encomenda=${feed.vivo.id_catalogo}#carrinho`);
  }

  const fonte = FONTES[feed?.marca.fonte ?? "FRAUNCES"] ?? FONTES.FRAUNCES;
  const estilo = {
    "--cv-principal": feed?.marca.cor_principal ?? "#3C4A3E",
    "--cv-fundo": feed?.marca.cor_fundo ?? "#F3EFE4",
    "--cv-tinta": "#1B211C",
    "--cv-serif": fonte.familia,
  } as React.CSSProperties;

  const letras = (
    <>
      <link rel="stylesheet" href={LETRAS_DO_SITE} />
      {fonte.url && <link rel="stylesheet" href={fonte.url} />}
    </>
  );

  if (erro) {
    return (
      <main style={estilo} className="cv-corpo flex min-h-[100dvh] flex-col items-center justify-center gap-4 bg-[var(--cv-fundo)] px-8 text-center text-[var(--cv-tinta)]">
        {letras}
        <p className="cv-serif text-2xl">{t.erro}</p>
        <p className="opacity-70">{erro}</p>
        <button type="button" onClick={() => void carregar()} className="rounded-full bg-[var(--cv-principal)] px-5 py-2.5 text-white">
          {t.tentar}
        </button>
      </main>
    );
  }
  if (!feed) {
    // ⚠️ O carregando é da cor do SITE, não um cinza-escuro: quem vem da página inicial não
    // pode ver a tela apagar antes do cardápio aparecer.
    return <main style={estilo} className="min-h-[100dvh] animate-pulse bg-[var(--cv-fundo)]" aria-busy />;
  }

  if (noHub && feed.hub) {
    return (
      <div style={estilo} className="cv-corpo">
        {letras}
        <Hub feed={feed} t={t} idioma={idioma} aoEscolherIdioma={setIdioma}
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
    // 🔑 **E a coluna é a FOLHA do site** (16/10/2026, "parecem dois sistemas"): o fundo areia
    // da casa em volta, 440 px, cantos de 18 px e a mesma sombra — no computador, o site e o
    // cardápio são o mesmo cartão no centro. Era uma coluna preta sobre fundo quase preto.
    <div style={estilo} className="cv-corpo min-h-[100dvh] bg-[var(--cv-fundo)] md:flex md:justify-center md:py-6">
    <main style={estilo}
          className="relative h-[100dvh] w-full overflow-hidden bg-[var(--cv-principal)] text-[#F4F0E5] md:h-[calc(100dvh-3rem)] md:max-w-[440px] md:rounded-[18px] md:border md:border-[#E0D8C6] md:shadow-[0_1px_2px_rgba(27,33,28,.05),0_10px_30px_rgba(27,33,28,.08)] md:[transform:translateZ(0)]">
      {letras}

      {/* 🔑 O topo é da COR DA CASA (a capa do site), e não um véu preto: ele desce sobre a
          foto até sumir, e a marca entra no medalhão de borda clara, como no site. */}
      <header className="absolute inset-x-0 top-0 z-30 pb-6 pt-[max(0.75rem,env(safe-area-inset-top))]"
              style={{ background: "linear-gradient(to bottom, color-mix(in srgb, var(--cv-principal) 92%, transparent) 0%, color-mix(in srgb, var(--cv-principal) 60%, transparent) 55%, transparent 100%)" }}>
        <div className="flex items-center gap-2 px-4">
          {/* 🔑 **A volta ao site da casa** (15/10/2026: "parecia dois sistemas"): a marca no
              topo leva à página inicial — reservar, fidelidade, contato —, no mesmo endereço.
              ⚠️ Na prévia do cadastro não há para onde voltar. */}
          <a href={previa ? undefined : enderecoDoSite()} aria-label={t.siteDaCasa}
             className="flex min-w-0 flex-1 items-center gap-2 leading-tight">
            {!previa && <span aria-hidden className="text-lg opacity-80">‹</span>}
            {feed.marca.logo && (
              <img src={imagem(feed.marca.logo, 320) ?? undefined} alt=""
                   className="h-9 w-9 shrink-0 rounded-full border-2 border-[#FBF9F3] bg-white object-cover" />
            )}
            {/* ⚠️ Com logo, o medalhão JÁ diz de quem é a casa: o nome dela ao lado saía
                cortado ("Botan…", e depois "Cardá…") entre a marca e os botões, a 400 px. Fica
                só a logo — e, na mesa, qual é a mesa, que é curto e é o que importa ali. */}
            {(!feed.marca.logo || feed.mesa) && (
              <span className="min-w-0">
                {!feed.marca.logo && <span className="cv-serif block truncate text-[15px]">{feed.loja.casa}</span>}
                <span className={feed.marca.logo ? "cv-serif block truncate text-[15px]" : "block truncate text-xs opacity-80"}>
                  {feed.mesa ? `${t.mesa} ${feed.mesa.nome}` : feed.cardapio}
                </span>
                {feed.marca.logo && feed.mesa && <span className="block truncate text-xs opacity-80">{feed.mesa.salao}</span>}
              </span>
            )}
          </a>
          {/* ⚠️ **As opções têm cor PRÓPRIA** (16/10/2026, pedido do dono: "na web o seletor de
              idiomas fica todo branco"): elas herdavam a letra clara do feed, e a lista que o
              navegador do computador abre é branca — branco sobre branco. No celular a lista é
              do sistema e não herda, por isso só aparecia na web. */}
          <SeletorDeIdioma idioma={idioma} aoEscolher={setIdioma} />
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
          {/* 🔑 Só consulta (119): sem a estrela, sem botão de adicionar e sem o "adicionar"
              da janela do prato — o cliente vê o cardápio e fala com o garçom. */}
          {feed.selecao && <button type="button" onClick={() => setVerSelecao(true)}
                  className="rounded-full bg-[var(--cv-fundo)] px-3 py-1 text-xs font-semibold text-[var(--cv-tinta)]">
            {modoPedido ? "🛒" : "★"} {selecao.quantidade}
          </button>}
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
                      c.id === categoriaAtiva ? "bg-[#FBF9F3] font-semibold text-[var(--cv-principal)]" : "bg-[#FBF9F3]/15 backdrop-blur"}`}>
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

      <div ref={rolagem} className="h-full snap-y snap-mandatory overflow-y-scroll overscroll-y-contain [scrollbar-width:none]">
        {itens.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
            <p>{t.nenhumComFiltro}</p>
            <button type="button" onClick={() => setFiltro([])} className="rounded-full bg-white px-4 py-2 text-black">
              {t.limparFiltro}
            </button>
          </div>
        )}
        {seq.map((passo, i) => passo.tipo === "anuncio" ? (
          <CartaoFeed key={passo.chave} passo={passo} posicao={i} ativo={i === ativo}
                      perto={Math.abs(i - ativo) <= 1} economia={economia} t={t}
                      aoVerPrato={acaoDoAnuncio(passo.anuncio)} />
        ) : passo.tipo !== "prato" ? (
          <CartaoFeed key={passo.chave} passo={passo} posicao={i} ativo={i === ativo}
                      perto={Math.abs(i - ativo) <= 1} economia={economia} t={t}
                      aoVerPrato={passo.tipo === "cartao" && passo.cartao.id_item_link
                        && itens.some((x) => x.id === passo.cartao.id_item_link)
                        ? () => {
                            medidor.current?.registrar("clicou_cartao", { cartao: passo.cartao.id, item: passo.cartao.id_item_link! });
                            irParaItem(passo.cartao.id_item_link!);
                          }
                        : undefined} />
        ) : (
          <ItemFeed
            key={passo.chave}
            item={passo.item}
            indice={i}
            posicao={i}
            ativo={i === ativo}
            perto={Math.abs(i - ativo) <= 1}
            economia={economia}
            selecionados={selecao.linhas.filter((l) => l.id_item === passo.item.id).reduce((s, l) => s + l.quantidade, 0)}
            favorito={favoritos.eh(passo.item.id)}
            aoFavoritar={() => favoritar(passo.item)}
            t={t}
            idioma={idioma}
            aoAbrir={() => abrirDetalhe(passo.item)}
            aoAdicionar={feed.selecao ? () => adicionar(passo.item, 1, []) : undefined}
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
                 aoAdicionar={feed.selecao ? (q, ad) => adicionar(aberto, q, ad) : undefined} />
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
          aoEncomendar={feed.encomenda && !token ? encomendar : undefined}
        />
      )}
    </main>
    </div>
  );
}
