"use client";

/**
 * Uma tela de CONTEÚDO no feed (120): a abertura do cardápio, a abertura automática de uma
 * seção ou um cartão entre os pratos. Mesma moldura do prato — tela cheia, encaixe na
 * rolagem —, sem preço e sem botão de adicionar.
 *
 * 🔑 Sem mídia, o fundo é a CAPA do site (os dois brilhos sobre a cor da casa) e o texto
 * vai ao centro; com foto ou vídeo, o texto desce para o pé, sobre o véu, como no prato.
 * ⚠️ O vídeo segue a regra do prato: só toca VISÍVEL, e com economia de dados fica a capa.
 */

import { useEffect, useRef, useState } from "react";
import { urlArquivo } from "@/lib/api";
import { imagem, srcSet } from "@/lib/cardapio-vivo";
import type { Passo } from "./sequencia";
import type { Textos } from "./textos";

type Props = {
  passo: Extract<Passo, { tipo: "cartao" | "secao" | "anuncio" }>;
  posicao: number;
  ativo: boolean;
  perto: boolean;
  economia: boolean;
  t: Textos;
  /** O "Ver o prato" do cartão — só quando ele aponta um prato que está na tela. */
  aoVerPrato?: () => void;
};

const CAPA_DA_CASA = "radial-gradient(120% 60% at 30% 20%, #D8C9A8 0%, transparent 60%), radial-gradient(110% 60% at 80% 30%, #B7C3A6 0%, transparent 55%), linear-gradient(160deg, color-mix(in srgb, var(--cv-principal) 70%, #B7C3A6), var(--cv-principal))";

export default function CartaoFeed({ passo, posicao, ativo, perto, economia, t, aoVerPrato }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const [tocarNoToque, setTocarNoToque] = useState(false);

  // As três origens falam a mesma língua aqui: título, texto e mídia.
  const ehSecao = passo.tipo === "secao";
  const anuncio = passo.tipo === "anuncio" ? passo.anuncio : null;
  const conteudo = passo.tipo === "secao"
    ? { titulo: passo.secao.nome, texto: passo.secao.descricao,
        midia: passo.secao.video
          ? { tipo: "VIDEO" as const, video: passo.secao.video, capa: passo.secao.capa ?? passo.secao.foto }
          : { tipo: "FOTO" as const, foto: passo.secao.foto! } }
    : passo.tipo === "anuncio"
      ? { titulo: passo.anuncio.titulo, texto: passo.anuncio.texto, midia: passo.anuncio.midia }
      : { titulo: passo.cartao.titulo, texto: passo.cartao.texto, midia: passo.cartao.midia };
  const { titulo, texto } = conteudo;
  const m = conteudo.midia;
  // 🔑 O rótulo do botão do anúncio: o que a casa escreveu, ou o padrão do tipo de ação.
  const rotuloAnuncio = anuncio && (anuncio.acao.rotulo
    || (anuncio.acao.tipo === "CATALOGO" ? t.verCardapioAnuncio : anuncio.acao.tipo === "PRATO" ? t.verOPrato : t.saibaMais));
  const capa = m.tipo === "VIDEO" ? m.capa : m.tipo === "FOTO" ? m.foto : null;
  const temMidia = m.tipo !== "NENHUMA";
  const podeTocar = m.tipo === "VIDEO" && ativo && (!economia || tocarNoToque);
  // ⚠️ **Texto longo não se corta** (16/10/2026: a abertura do Catering, 465 letras com quebra a
  // cada ~30, saía cortada em 6 linhas). Ele ganha letra um pouco menor, véu mais alto e, no
  // limite, rola dentro do cartão — o que a casa escreveu aparece inteiro.
  const longo = (texto?.length ?? 0) > 220 || (texto?.split("\n").length ?? 0) > 6;

  useEffect(() => {
    const v = video.current;
    if (!v) return;
    if (podeTocar) v.play().catch(() => { /* autoplay barrado: a capa fica */ });
    else v.pause();
  }, [podeTocar]);

  return (
    <section
      data-pos={posicao}
      {...(ehSecao ? { "data-categoria": passo.id_categoria } : {})}
      data-cartao={passo.tipo === "cartao" ? passo.cartao.id : undefined}
      data-anuncio={anuncio?.id}
      className="cv-conteudo relative h-full w-full snap-start snap-always overflow-hidden"
      aria-label={titulo ?? t.verCardapio}
    >
      <div className="absolute inset-0" style={temMidia ? undefined : { background: CAPA_DA_CASA }}>
        {capa && (
          <img src={imagem(capa, 720) ?? undefined} srcSet={srcSet(capa)}
               sizes="(min-width: 768px) 440px, 100vw" alt=""
               className="absolute inset-0 h-full w-full object-cover"
               loading={perto || posicao === 0 ? "eager" : "lazy"} decoding="async" />
        )}
        {m.tipo === "VIDEO" && (perto || ativo) && (!economia || tocarNoToque) && (
          <video ref={video} className="absolute inset-0 h-full w-full object-cover"
                 src={urlArquivo(m.video) ?? undefined} poster={imagem(capa, 720) ?? undefined}
                 muted loop playsInline preload={ativo ? "auto" : "metadata"} aria-hidden />
        )}
        {temMidia && (
          <div className={`absolute inset-x-0 bottom-0 ${longo ? "h-full" : "h-[70%]"}`}
               style={{ background: "linear-gradient(to top, color-mix(in srgb, var(--cv-principal) 30%, rgba(0,0,0,.9)) 0%, color-mix(in srgb, var(--cv-principal) 25%, rgba(0,0,0,.45)) 55%, transparent 100%)" }} />
        )}
      </div>

      {m.tipo === "VIDEO" && economia && !tocarNoToque && (
        <button type="button" onClick={() => setTocarNoToque(true)}
                className="absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/55 px-5 py-3 text-sm font-medium text-white backdrop-blur">
          ▶ {t.tocarParaVer}
        </button>
      )}

      {/* ⚠️ O topo do feed (marca, filtros, categorias) ocupa uns 7rem: o texto nunca sobe
          por baixo dele — o que não cabe rola aqui dentro. Sem mídia, o miolo vai ao CENTRO pela
          margem automática (`my-auto`), que não corta o começo quando o texto é maior que a tela.
          ⚠️ Era `justify-[safe_center]`, que o Tailwind não gerou: o texto ficava no alto. */}
      <div className={`absolute inset-x-0 overflow-y-auto px-6 text-[#F4F0E5] [scrollbar-width:none] ${temMidia
        ? "bottom-0 max-h-[calc(100%-7rem)] pb-[max(2rem,env(safe-area-inset-bottom))]"
        : "bottom-0 top-[7rem] flex flex-col pb-[max(1.5rem,env(safe-area-inset-bottom))] text-center"}`}>
        <div className={temMidia ? "" : "my-auto flex flex-col"}>
        {/* 🔑 Propaganda tem de ser reconhecível (121): "Patrocinado · marca" ou "Da casa". */}
        {anuncio && (
          <p className={`mb-2 inline-flex rounded-full bg-[rgba(20,26,22,.72)] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] ${temMidia ? "" : "self-center"}`}>
            {anuncio.origem === "EXTERNO" ? `${t.patrocinado}${anuncio.anunciante ? ` · ${anuncio.anunciante}` : ""}` : t.daCasa}
          </p>
        )}
        {ehSecao && passo.dentroDe && (
          <p className="mb-1 text-[12px] font-semibold uppercase tracking-[0.18em] opacity-80">{passo.dentroDe}</p>
        )}
        {titulo && (
          <h2 className={`cv-serif leading-[1.08] drop-shadow ${ehSecao ? "text-[2.6rem]" : "text-[2.1rem]"}`}>{titulo}</h2>
        )}
        {texto && (
          <p className={`mt-3 whitespace-pre-line text-[#F4F0E5]/90 ${longo ? "text-[15px] leading-normal" : "text-[16px] leading-relaxed"} ${temMidia ? "" : "mx-auto max-w-[34ch]"}`}>
            {texto}
          </p>
        )}
        {aoVerPrato && (
          <button type="button" onClick={aoVerPrato}
                  className={`mt-5 rounded-full bg-[var(--cv-fundo)] px-5 py-2.5 text-sm font-semibold text-[var(--cv-tinta)] shadow-lg active:scale-95 ${temMidia ? "" : "self-center"}`}>
            {rotuloAnuncio ?? t.verOPrato}
          </button>
        )}
        </div>
      </div>
    </section>
  );
}
