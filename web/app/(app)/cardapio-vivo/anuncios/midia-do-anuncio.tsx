"use client";

/**
 * A foto OU o vídeo do anúncio (121) e as traduções dele — a parte que pede o anúncio já gravado.
 * ⚠️ O vídeo segue a regra do prato (até 15 s, sem som); a foto troca o vídeo e vice-versa.
 */

import { useRef, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import Traducoes from "@/components/traducoes";
import { urlArquivo } from "@/lib/api";
import { AnunciosService, type Anuncio } from "@/lib/anuncios";

export default function MidiaDoAnuncio({ anuncio, podeEditar, aoMudar }: {
  anuncio: Anuncio; podeEditar: boolean; aoMudar: (a: Anuncio) => void;
}) {
  const aviso = useAviso();
  const [enviando, setEnviando] = useState<"" | "foto" | "video">("");
  const [traduzindo, setTraduzindo] = useState(false);
  const foto = useRef<HTMLInputElement>(null);
  const video = useRef<HTMLInputElement>(null);
  const falhou = (e: unknown, padrao: string) => aviso.erro(e instanceof Error ? e.message : padrao);

  async function enviar(tipo: "foto" | "video", arquivo: File | undefined) {
    if (!arquivo) return;
    setEnviando(tipo);
    try {
      const r = tipo === "foto"
        ? await AnunciosService.enviarFoto(anuncio.id, arquivo)
        : await AnunciosService.enviarVideo(anuncio.id, arquivo);
      aoMudar(r);
      aviso.sucesso(tipo === "video" ? ((r as { message?: string }).message ?? "Vídeo gravado.") : "Foto gravada.");
    } catch (e) {
      falhou(e, `Não foi possível enviar ${tipo === "foto" ? "a foto" : "o vídeo"}.`);
    } finally {
      setEnviando("");
      if (foto.current) foto.current.value = "";
      if (video.current) video.current.value = "";
    }
  }

  async function tirar() {
    try {
      aoMudar(await AnunciosService.removerMidia(anuncio.id));
    } catch (e) {
      falhou(e, "Não foi possível tirar a mídia.");
    }
  }

  const capa = anuncio.video_capa_url ?? anuncio.foto_url;
  return (
    <div className="flex flex-col gap-3">
      <div>
        <span className="rotulo-campo">Foto ou vídeo</span>
        <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[13.5px]">
          <span className="flex h-16 w-12 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-linha bg-superficie2">
            {capa
              // eslint-disable-next-line @next/next/no-img-element
              ? <img src={urlArquivo(capa) ?? undefined} alt="" className="h-full w-full object-cover" />
              : <span className="text-[11px] text-suave">nada</span>}
          </span>
          <span className="text-suave">
            {anuncio.video_url ? `Vídeo de ${Number(anuncio.video_segundos ?? 0).toFixed(0)} s.`
              : anuncio.foto_url ? "Foto." : "Sem mídia: o fundo é a capa da casa e o texto vai ao centro."}
          </span>
          {podeEditar && (
            <span className="flex flex-wrap gap-2">
              <input ref={foto} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                     onChange={(e) => void enviar("foto", e.target.files?.[0])} />
              <input ref={video} type="file" accept="video/mp4,video/quicktime,video/webm" className="hidden"
                     onChange={(e) => void enviar("video", e.target.files?.[0])} />
              <button type="button" className="btn btn-secundario" disabled={!!enviando} onClick={() => foto.current?.click()}>
                {enviando === "foto" ? "Enviando…" : "Pôr foto"}
              </button>
              <button type="button" className="btn btn-secundario" disabled={!!enviando} onClick={() => video.current?.click()}>
                {enviando === "video" ? "Convertendo…" : "Pôr vídeo"}
              </button>
              {(anuncio.foto_url || anuncio.video_url) && (
                <button type="button" className="link-acao link-acao-erro" onClick={() => void tirar()}>tirar</button>
              )}
            </span>
          )}
        </div>
        <p className="mt-1 text-[12.5px] text-suave">Vídeo de até 15 s, sem som. A foto troca o vídeo, e o vídeo a foto.</p>
      </div>
      {podeEditar && (traduzindo ? (
        <Traducoes key={`${anuncio.titulo}|${anuncio.texto}`} tipo="anuncio" id={anuncio.id}
                   rotulos={{ nome: "Título", descricao: "Texto" }} maxNome={120} maxDescricao={500} />
      ) : (
        <p className="text-[13.5px]">
          <button type="button" className="link-acao" id="anuncio-traducoes" onClick={() => setTraduzindo(true)}>traduções</button>
          <span className="ml-2 text-suave">o título e o texto em inglês e alemão</span>
        </p>
      ))}
    </div>
  );
}
