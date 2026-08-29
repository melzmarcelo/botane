"use client";

import { useEffect, useState } from "react";

/**
 * Registro do service worker e o convite para instalar.
 *
 * O `?dev=1` na URL do registro não é enfeite: é como o service worker sabe
 * que está no servidor de desenvolvimento e desliga o cache de estático.
 * Trocar o parâmetro também troca a URL do script, o que faz o navegador
 * reinstalar o worker em vez de manter o antigo.
 */
export function RegistroPWA() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    const dev = process.env.NODE_ENV !== "production";
    void navigator.serviceWorker.register(`/sw.js${dev ? "?dev=1" : ""}`).catch(() => {
      // Sem service worker o sistema funciona igual — só não instala. Não é
      // erro que valha assustar quem está usando.
    });
  }, []);
  return null;
}

type Prompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: string }> };

const CHAVE = "botane_instalar_dispensado";
const SILENCIO_DIAS = 60;

const jaInstalado = () =>
  window.matchMedia("(display-mode: standalone)").matches ||
  // O iPhone não implementa `display-mode`, mas marca a janela como standalone.
  (window.navigator as { standalone?: boolean }).standalone === true;

const ehIOS = () =>
  /iphone|ipad|ipod/i.test(navigator.userAgent) ||
  // iPad recente se apresenta como Mac; o toque no lugar do mouse denuncia.
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

/**
 * Convite para pôr o sistema na tela inicial.
 *
 * São dois caminhos que não se encontram: o Chrome guarda o evento
 * `beforeinstallprompt` e instala num toque; o iPhone não tem essa API e nunca
 * vai ter — lá só resta ensinar o caminho do menu Compartilhar.
 */
export function ConviteInstalar() {
  const [prompt, setPrompt] = useState<Prompt | null>(null);
  const [ios, setIos] = useState(false);

  useEffect(() => {
    if (jaInstalado()) return;
    const dispensadoEm = Number(localStorage.getItem(CHAVE) ?? 0);
    if (Date.now() - dispensadoEm < SILENCIO_DIAS * 86400_000) return;

    if (ehIOS()) {
      setIos(true);
      return;
    }
    const aoPoder = (e: Event) => {
      e.preventDefault();
      setPrompt(e as Prompt);
    };
    window.addEventListener("beforeinstallprompt", aoPoder);
    // Instalou por outro caminho (menu do navegador): o convite some e não volta.
    const aoInstalar = () => {
      setPrompt(null);
      localStorage.setItem(CHAVE, String(Date.now() + 3650 * 86400_000));
    };
    window.addEventListener("appinstalled", aoInstalar);
    return () => {
      window.removeEventListener("beforeinstallprompt", aoPoder);
      window.removeEventListener("appinstalled", aoInstalar);
    };
  }, []);

  if (!prompt && !ios) return null;

  const dispensar = () => {
    localStorage.setItem(CHAVE, String(Date.now()));
    setPrompt(null);
    setIos(false);
  };

  return (
    <div className="cartao nao-imprimir mb-5 flex flex-wrap items-center justify-between gap-3 border-erva/30 bg-erva-claro p-4">
      <p className="max-w-[60ch] text-[14.5px]">
        <b>Deixe o Botané na tela inicial do celular.</b>{" "}
        {ios ? (
          <span className="text-suave">
            No iPhone: toque em Compartilhar (o quadrado com a seta) e depois em “Adicionar à
            Tela de Início”.
          </span>
        ) : (
          <span className="text-suave">
            Abre em tela cheia, como um aplicativo — útil para contar o estoque com o telefone
            na mão.
          </span>
        )}
      </p>
      <div className="flex items-center gap-2">
        {prompt && (
          <button
            className="btn btn-primario"
            onClick={async () => {
              await prompt.prompt();
              const { outcome } = await prompt.userChoice;
              if (outcome === "accepted") localStorage.setItem(CHAVE, String(Date.now() + 3650 * 86400_000));
              setPrompt(null);
            }}
          >
            Instalar
          </button>
        )}
        <button className="link-acao link-acao-erro" onClick={dispensar}>
          agora não
        </button>
      </div>
    </div>
  );
}
