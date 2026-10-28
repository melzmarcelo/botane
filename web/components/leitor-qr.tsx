"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A câmera do aparelho lendo QR sem sair da tela — para a conferência do patrimônio ler
 * plaqueta atrás de plaqueta.
 *
 * ⚠️ **Usa o `BarcodeDetector` do navegador, que o Chrome do Android tem e o Safari do
 * iPhone não.** Sem ele, o componente não aparece (`leitorDisponivel()` = false) e o
 * caminho é a câmera COMUM do celular: ela abre a plaqueta no sistema, e o aparelho que
 * está conferindo conta a leitura lá (`/patrimonio/b/…`). Nenhuma biblioteca de leitura
 * entra no pacote por isso.
 * ⚠️ O mesmo código lido de novo em menos de 3 s é ignorado: a câmera vê a plaqueta
 * várias vezes por segundo enquanto ela está na frente.
 */
type Detector = { detect: (v: HTMLVideoElement) => Promise<{ rawValue: string }[]> };

export function leitorDisponivel(): boolean {
  return typeof window !== "undefined" && "BarcodeDetector" in window
    && !!navigator.mediaDevices?.getUserMedia;
}

export default function LeitorQr({ onLer, onFechar }: {
  onLer: (texto: string) => void;
  onFechar: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [erro, setErro] = useState("");
  const ultimo = useRef<{ texto: string; quando: number }>({ texto: "", quando: 0 });
  const lerRef = useRef(onLer);
  lerRef.current = onLer;

  useEffect(() => {
    let fluxo: MediaStream | null = null;
    let vivo = true;
    let espera: ReturnType<typeof setTimeout> | undefined;
    const Ctor = (window as unknown as { BarcodeDetector: new (o: object) => Detector })
      .BarcodeDetector;
    const detector = new Ctor({ formats: ["qr_code"] });

    const varrer = async () => {
      if (!vivo || !video.current) return;
      try {
        const achados = await detector.detect(video.current);
        const texto = achados[0]?.rawValue;
        const agora = Date.now();
        if (texto && !(texto === ultimo.current.texto && agora - ultimo.current.quando < 3000)) {
          ultimo.current = { texto, quando: agora };
          navigator.vibrate?.(80);
          lerRef.current(texto);
        }
      } catch { /* quadro ainda sem imagem */ }
      espera = setTimeout(varrer, 250);
    };

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((s) => {
        if (!vivo) { s.getTracks().forEach((t) => t.stop()); return; }
        fluxo = s;
        if (video.current) {
          video.current.srcObject = s;
          void video.current.play();
        }
        void varrer();
      })
      .catch(() => setErro("Sem acesso à câmera — permita no navegador, ou leia a plaqueta "
                           + "com a câmera do celular."));
    return () => {
      vivo = false;
      clearTimeout(espera);
      fluxo?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  return (
    <div className="flex flex-col gap-2" id="leitor-qr">
      {erro ? (
        <p className="text-[13.5px] text-erro">{erro}</p>
      ) : (
        <video ref={video} muted playsInline
               className="aspect-square w-full max-w-[360px] rounded-xl bg-black object-cover" />
      )}
      <button type="button" className="btn btn-secundario self-start" onClick={onFechar}>
        Fechar a câmera
      </button>
    </div>
  );
}
