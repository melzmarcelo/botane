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
  passo: Extract<Passo, { tipo: "cartao" | "secao" }>;
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

  // As duas origens falam a mesma língua aqui: título, texto e mídia.
  const ehSecao = passo.tipo === "secao";
  const titulo = ehSecao ? passo.secao.nome : passo.cartao.titulo;
  const texto = ehSecao ? passo.secao.descricao : passo.cartao.texto;
  const m = ehSecao
    ? (passo.secao.video ? { tipo: "VIDEO" as const, video: passo.secao.video, capa: passo.secao.capa ?? passo.secao.foto }
       : { tipo: "FOTO" as const, foto: passo.secao.foto! })
    : passo.cartao.midia;
  const capa = m.tipo === "VIDEO" ? m.capa : m.tipo === "FOTO" ? m.foto : null;
  const temMidia = m.tipo !== "NENHUMA";
  const podeTocar = m.tipo === "VIDEO" && ativo && (!economia || tocarNoToque);

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
      data-cartao={ehSecao ? undefined : passo.cartao.id}
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
          <div className="absolute inset-x-0 bottom-0 h-[70%]"
               style={{ background: "linear-gradient(to top, color-mix(in srgb, var(--cv-principal) 30%, rgba(0,0,0,.9)) 0%, color-mix(in srgb, var(--cv-principal) 25%, rgba(0,0,0,.45)) 55%, transparent 100%)" }} />
        )}
      </div>

      {m.tipo === "VIDEO" && economia && !tocarNoToque && (
        <button type="button" onClick={() => setTocarNoToque(true)}
                className="absolute left-1/2 top-1/2 z-10 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/55 px-5 py-3 text-sm font-medium text-white backdrop-blur">
          ▶ {t.tocarParaVer}
        </button>
      )}

      <div className={`absolute inset-x-0 px-6 text-[#F4F0E5] ${temMidia
        ? "bottom-0 pb-[max(2rem,env(safe-area-inset-bottom))]"
        : "inset-y-0 flex flex-col justify-center text-center"}`}>
        {ehSecao && passo.dentroDe && (
          <p className="mb-1 text-[12px] font-semibold uppercase tracking-[0.18em] opacity-80">{passo.dentroDe}</p>
        )}
        {titulo && (
          <h2 className={`cv-serif leading-[1.08] drop-shadow ${ehSecao ? "text-[2.6rem]" : "text-[2.1rem]"}`}>{titulo}</h2>
        )}
        {texto && (
          <p className={`mt-3 whitespace-pre-line text-[16px] leading-relaxed text-[#F4F0E5]/90 ${temMidia ? "line-clamp-6" : "mx-auto max-w-[30ch]"}`}>
            {texto}
          </p>
        )}
        {aoVerPrato && (
          <button type="button" onClick={aoVerPrato}
                  className={`mt-5 rounded-full bg-[var(--cv-fundo)] px-5 py-2.5 text-sm font-semibold text-[var(--cv-tinta)] shadow-lg active:scale-95 ${temMidia ? "" : "self-center"}`}>
            {t.verOPrato}
          </button>
        )}
      </div>
    </section>
  );
}
