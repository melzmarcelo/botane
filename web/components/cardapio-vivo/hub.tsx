"use client";

/**
 * A tela de entrada do Cardápio Vivo (complemento do dono, 14/10/2026): a marca da loja e
 * os botões — "Ver cardápio", "Avaliar no Google", "Wi-Fi" e, desde 15/10/2026, o site da
 * casa ("Reservas, fidelidade e contato"), com a mesma cara da página inicial dele.
 *
 * 🔑 Só aparece quando a loja ligou E preencheu algum dos dois extras; senão o cliente cai
 * direto no feed (quem decide é o servidor, que manda `hub` nulo).
 * ⚠️ O link do Google abre em OUTRA aba, de um toque — `target=_blank` num `<a>` de verdade,
 * para não ser barrado como popup.
 */

import { useState } from "react";
import { enderecoDoSite, imagem, type Feed } from "@/lib/cardapio-vivo";
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

  const botao = "flex min-h-[52px] w-full items-center justify-center rounded-[13px] border px-4 py-[15px] text-center text-[16px] font-medium leading-tight";
  const comum = `${botao} border-[#E0D8C6] bg-[#F7F3E9] text-[#1B211C] hover:border-[var(--cv-principal)]`;
  const primeiroNome = (feed.loja.casa || "").split(" ")[0];
  // 🔑 **A MESMA cara da página inicial do site** (pedido do dono, 15/10/2026: "o site de
  // reserva e cardápio ficou parecendo dois sistemas separados"): a folha clara no centro,
  // a capa com o medalhão descendo sobre ela e os botões centralizados — com as cores, a
  // fonte e a logo da casa. Antes era uma tela própria, de fundo chapado.
  return (
    <main className="min-h-[100dvh] bg-[var(--cv-fundo)] sm:px-4 sm:py-6" aria-label={feed.loja.casa}>
      <div className="mx-auto min-h-[100dvh] max-w-[440px] overflow-hidden bg-[#FBF9F3] text-[#1B211C] shadow-[0_1px_2px_rgba(27,33,28,.05),0_10px_30px_rgba(27,33,28,.08)] sm:min-h-0 sm:rounded-[18px] sm:border sm:border-[#E0D8C6]">
        <header className="relative h-32"
                style={{ background: "radial-gradient(120% 90% at 30% 20%, #D8C9A8 0%, transparent 60%), radial-gradient(110% 90% at 80% 30%, #B7C3A6 0%, transparent 55%), linear-gradient(160deg, color-mix(in srgb, var(--cv-principal) 70%, #B7C3A6), var(--cv-principal))" }}>
          <div className={`absolute -bottom-[34px] left-1/2 grid h-[92px] w-[92px] -translate-x-1/2 place-content-center overflow-hidden rounded-full border-[3px] border-[#FBF9F3] text-center ${feed.marca.logo ? "bg-white" : "bg-[var(--cv-principal)] text-[#F3EFE4]"}`}>
            {feed.marca.logo
              ? <img src={imagem(feed.marca.logo, 320) ?? undefined} alt="" className="h-full w-full object-cover" />
              : <b className="cv-serif text-[21px] font-light">{primeiroNome}</b>}
          </div>
        </header>
        <div className="flex flex-col gap-3.5 px-5 pb-7 pt-[46px]">
          <h1 className="cv-serif text-center text-[22px] leading-tight">{feed.loja.casa}</h1>
          <p className="text-center text-[14px] text-[#5E6659]">
            {feed.mesa ? `${t.mesa} ${feed.mesa.nome} · ${feed.mesa.salao}` : feed.cardapio}
          </p>
          <div className="flex flex-col gap-[9px]">
            <button type="button" onClick={aoVerCardapio}
                    className={`${botao} border-[var(--cv-principal)] bg-[var(--cv-principal)] text-[#F4F0E5]`}>
              {t.verCardapio}
            </button>
            {hub.avaliacao && (
              <a href={hub.avaliacao} target="_blank" rel="noopener noreferrer" onClick={aoAvaliar} className={comum}>
                ★ {t.avaliarGoogle}
              </a>
            )}
            {hub.wifi && (
              <button type="button" className={comum}
                      onClick={() => { setWifiAberto((v) => !v); if (!wifiAberto) aoAbrirWifi(); }}
                      aria-expanded={wifiAberto}>
                {t.wifi}
              </button>
            )}
            {hub.wifi && wifiAberto && (
          <div className="rounded-2xl border border-current/15 bg-white p-4 text-sm" role="region" aria-label={t.wifi}>
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
            {/* 🔑 O resto da casa — reservar, fidelidade, contato — está no site, que é
                o mesmo endereço e a mesma cara. */}
            <a href={enderecoDoSite()} className={comum}>{t.siteDaCasa}</a>
          </div>
        </div>
      </div>
    </main>
  );
}
