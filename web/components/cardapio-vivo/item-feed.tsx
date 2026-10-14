"use client";

/**
 * Um prato, uma tela: a mídia de fundo e, por cima, nome, descrição, preço, restrições e
 * o botão. Tocar no prato abre o detalhe.
 *
 * 🔑 **O vídeo só toca VISÍVEL** (≥ 50% da tela, quem decide é o feed) e pausa ao sair —
 * dez vídeos tocando fora da tela gastariam a bateria e o plano de dados de quem está
 * sentado à mesa. Com economia de dados (ou rede lenta), fica a capa e o vídeo só toca no
 * toque.
 */

import { useEffect, useRef, useState } from "react";
import { urlArquivo } from "@/lib/api";
import { imagem, srcSet, type ItemFeed } from "@/lib/cardapio-vivo";
import { moeda, nomeRestricao, type Textos } from "./textos";
import type { Idioma } from "@/lib/cardapio-vivo";

type Props = {
  item: ItemFeed;
  indice: number;
  ativo: boolean;
  perto: boolean;
  economia: boolean;
  selecionados: number;
  favorito: boolean;
  t: Textos;
  idioma: Idioma;
  aoAbrir: () => void;
  aoAdicionar: () => void;
  aoFavoritar: () => void;
};

export default function ItemFeed({ item, indice, ativo, perto, economia, selecionados, favorito, t, idioma,
                                   aoAbrir, aoAdicionar, aoFavoritar }: Props) {
  const video = useRef<HTMLVideoElement>(null);
  const [tocarNoToque, setTocarNoToque] = useState(false);
  const m = item.midia;
  const podeTocar = m.tipo === "VIDEO" && ativo && (!economia || tocarNoToque);

  useEffect(() => {
    const v = video.current;
    if (!v) return;
    if (podeTocar) v.play().catch(() => { /* autoplay barrado: a capa fica */ });
    else v.pause();
  }, [podeTocar]);

  const capa = m.tipo === "VIDEO" ? m.capa : m.tipo === "FOTO" ? m.foto : null;
  // 🔑 O primeiro prato é o maior desenho da tela (LCP): vai na frente de tudo.
  const prioridade = indice === 0;

  return (
    <section
      data-item={item.id}
      data-categoria={item.id_categoria}
      className="cv-item relative h-[100dvh] w-full snap-start snap-always overflow-hidden"
      aria-label={item.nome}
    >
      <button type="button" onClick={aoAbrir} className="absolute inset-0 block h-full w-full"
              aria-label={item.nome}>
        {capa ? (
          <img
            src={imagem(capa, 720) ?? undefined}
            srcSet={srcSet(capa)}
            sizes="100vw"
            alt=""
            className="absolute inset-0 h-full w-full object-cover"
            loading={prioridade || perto ? "eager" : "lazy"}
            fetchPriority={prioridade ? "high" : "auto"}
            decoding="async"
          />
        ) : (
          <div className="absolute inset-0 bg-[var(--cv-principal)] opacity-90" />
        )}
        {m.tipo === "VIDEO" && (perto || ativo) && (!economia || tocarNoToque) && (
          <video
            ref={video}
            className="absolute inset-0 h-full w-full object-cover"
            src={urlArquivo(m.video) ?? undefined}
            poster={imagem(capa, 720) ?? undefined}
            muted
            loop
            playsInline
            preload={ativo ? "auto" : "metadata"}
            aria-hidden
          />
        )}
        <div className="absolute inset-x-0 bottom-0 h-[62%] bg-gradient-to-t from-black/85 via-black/45 to-transparent" />
      </button>

      {m.tipo === "VIDEO" && economia && !tocarNoToque && (
        <button type="button" onClick={() => setTocarNoToque(true)}
                className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/55 px-5 py-3 text-sm font-medium text-white backdrop-blur">
          ▶ {t.tocarParaVer}
        </button>
      )}

      <div className="pointer-events-none absolute inset-x-0 bottom-0 px-5 pb-[max(1.5rem,env(safe-area-inset-bottom))] text-white">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {item.destaque && (
            <span className="rounded-full bg-[var(--cv-principal)] px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide">
              {t.destaque}
            </span>
          )}
          {item.fora_do_horario && (
            <span className="rounded-full bg-amber-500/90 px-2.5 py-0.5 text-[11px] font-semibold">{t.foraDoHorario}</span>
          )}
          {item.restricoes.map((r) => (
            <span key={r} className="rounded-full border border-white/60 px-2.5 py-0.5 text-[11px] font-medium backdrop-blur-sm">
              {nomeRestricao(idioma, r)}
            </span>
          ))}
        </div>
        <div className="flex items-start justify-between gap-3">
          <h2 className="cv-serif text-[2rem] leading-[1.08] drop-shadow">{item.nome}</h2>
          {/* 🔑 O favorito (114) é sinal de interesse, não pedido: nos dois modos, sempre. */}
          <button type="button" onClick={aoFavoritar} aria-pressed={favorito}
                  aria-label={favorito ? t.desfavoritar : t.favoritar}
                  className="pointer-events-auto -mr-1 shrink-0 rounded-full p-2 text-[26px] leading-none drop-shadow active:scale-90">
            {favorito ? "♥" : "♡"}
          </button>
        </div>
        {item.descricao && (
          <p className="mt-2 line-clamp-3 max-w-prose text-[15px] leading-snug text-white/90">{item.descricao}</p>
        )}
        <div className="pointer-events-auto mt-4 flex items-center justify-between gap-3">
          <span className="text-xl font-semibold tabular-nums">
            {item.preco !== null ? moeda(item.preco) : ""}
          </span>
          {item.esgotado ? (
            <span className="rounded-full bg-white/20 px-4 py-2.5 text-sm font-semibold backdrop-blur">{t.esgotado}</span>
          ) : (
            <button
              type="button"
              onClick={item.adicionais.length ? aoAbrir : aoAdicionar}
              className="rounded-full bg-[var(--cv-fundo)] px-4 py-2.5 text-sm font-semibold text-[var(--cv-tinta)] shadow-lg active:scale-95"
            >
              {selecionados > 0 ? `✓ ${t.adicionado} (${selecionados})` : `+ ${t.adicionarSelecao}`}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
