"use client";

/**
 * A tela de entrada do Cardápio Vivo (complemento do dono, 14/10/2026): a marca da loja e
 * até três botões — "Ver cardápio", "Avaliar no Google" e "Wi-Fi".
 *
 * 🔑 Só aparece quando a loja ligou E preencheu algum dos dois extras; senão o cliente cai
 * direto no feed (quem decide é o servidor, que manda `hub` nulo).
 * ⚠️ O link do Google abre em OUTRA aba, de um toque — `target=_blank` num `<a>` de verdade,
 * para não ser barrado como popup.
 */

import { useState } from "react";
import { imagem, type Feed } from "@/lib/cardapio-vivo";
import type { Textos } from "./textos";

type Props = {
  feed: Feed;
  t: Textos;
  aoVerCardapio: () => void;
  aoAvaliar: () => void;
  aoAbrirWifi: () => void;
};

export default function Hub({ feed, t, aoVerCardapio, aoAvaliar, aoAbrirWifi }: Props) {
  const [wifiAberto, setWifiAberto] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const hub = feed.hub!;

  async function copiar() {
    try {
      await navigator.clipboard.writeText(hub.wifi?.senha ?? "");
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    } catch {
      /* sem permissão de área de transferência: a senha continua à vista */
    }
  }

  const botao = "w-full rounded-full px-5 py-3.5 text-center text-[15px] font-semibold";
  return (
    <main className="flex min-h-[100dvh] flex-col items-center justify-center gap-8 bg-[var(--cv-fundo)] px-6 text-[var(--cv-tinta)]"
          aria-label={feed.loja.casa}>
      <div className="flex flex-col items-center gap-3 text-center">
        {feed.marca.logo && (
          <img src={imagem(feed.marca.logo, 320) ?? undefined} alt="" className="h-24 w-24 rounded-full bg-white object-contain shadow" />
        )}
        <h1 className="cv-serif text-[2rem] leading-tight">{feed.loja.casa}</h1>
        {feed.mesa && <p className="text-sm opacity-70">{t.mesa} {feed.mesa.nome} · {feed.mesa.salao}</p>}
      </div>

      <div className="flex w-full max-w-xs flex-col gap-3">
        <button type="button" onClick={aoVerCardapio} className={`${botao} bg-[var(--cv-principal)] text-white`}>
          {t.verCardapio}
        </button>
        {hub.avaliacao && (
          <a href={hub.avaliacao} target="_blank" rel="noopener noreferrer" onClick={aoAvaliar}
             className={`${botao} border border-current/25`}>
            ★ {t.avaliarGoogle}
          </a>
        )}
        {hub.wifi && (
          <button type="button" className={`${botao} border border-current/25`}
                  onClick={() => { setWifiAberto((v) => !v); if (!wifiAberto) aoAbrirWifi(); }}
                  aria-expanded={wifiAberto}>
            {t.wifi}
          </button>
        )}
        {hub.wifi && wifiAberto && (
          <div className="rounded-2xl border border-current/15 bg-white/60 p-4 text-sm" role="region" aria-label={t.wifi}>
            <p><span className="opacity-60">{t.rede}: </span><b>{hub.wifi.rede}</b></p>
            {hub.wifi.senha && (
              <div className="mt-2 flex items-center justify-between gap-3">
                <p className="min-w-0 break-all"><span className="opacity-60">{t.senha}: </span>
                  <b className="font-mono">{hub.wifi.senha}</b></p>
                <button type="button" onClick={() => void copiar()}
                        className="shrink-0 rounded-full bg-[var(--cv-principal)] px-3 py-1.5 text-xs font-semibold text-white">
                  {copiado ? t.copiado : t.copiar}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </main>
  );
}
