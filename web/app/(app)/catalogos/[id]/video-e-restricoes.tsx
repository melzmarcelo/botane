"use client";

/**
 * Vídeo e restrições alimentares do PRATO, na gaveta do editor do cardápio.
 *
 * 🔑 São do PRODUTO (decisão do dono, 14/10/2026): o mesmo prato em duas listas tem
 * o mesmo vídeo e as mesmas restrições. As rotas pedem `cadastros.produtos`, e
 * quem chama só monta isto com essa permissão.
 */

import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { ProdutoCardapioService, type CardapioDoProduto } from "@/lib/cardapio-vivo";

export default function VideoERestricoes({ idProduto, aoMudar }: { idProduto: number; aoMudar: () => Promise<void> }) {
  const aviso = useAviso();
  const falhou = (e: unknown, padrao: string) => aviso.erro(e instanceof Error ? e.message : padrao);
  const [extra, setExtra] = useState<CardapioDoProduto | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    ProdutoCardapioService.obter(idProduto).then(setExtra).catch(() => setExtra(null));
  }, [idProduto]);

  async function video(arquivo: File | undefined) {
    if (!arquivo) return;
    setEnviando(true);
    try {
      const r = await ProdutoCardapioService.enviarVideo(idProduto, arquivo);
      setExtra((x) => x && { ...x, video: r.video });
      await aoMudar();
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível enviar o vídeo.");
    } finally {
      setEnviando(false);
    }
  }

  async function tirarVideo() {
    try {
      const r = await ProdutoCardapioService.removerVideo(idProduto);
      setExtra((x) => x && { ...x, video: null });
      await aoMudar();
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível tirar o vídeo.");
    }
  }

  async function restricao(chave: string) {
    if (!extra) return;
    const novas = extra.restricoes.includes(chave)
      ? extra.restricoes.filter((r) => r !== chave) : [...extra.restricoes, chave];
    try {
      const r = await ProdutoCardapioService.restricoes(idProduto, novas);
      setExtra({ ...extra, restricoes: r.restricoes });
    } catch (e) {
      falhou(e, "Não foi possível gravar a restrição.");
    }
  }

  if (!extra) return null;
  return (
    <>
      <div>
        <span className="rotulo-campo">Vídeo</span>
        <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[13.5px]">
          <span className="text-suave">
            {extra.video
              ? `${extra.video.nome ?? "vídeo"} · ${extra.video.segundos?.toFixed(0) ?? "?"} s — aparece no lugar da foto`
              : "Sem vídeo. Até 15 s, sem som."}
          </span>
          <label className={`btn btn-secundario relative cursor-pointer ${enviando ? "opacity-60" : ""}`}>
            {enviando ? "Convertendo…" : extra.video ? "Trocar vídeo" : "Enviar vídeo"}
            <input type="file" accept="video/mp4,video/quicktime,video/webm" className="sr-only"
                   disabled={enviando}
                   onChange={(e) => { void video(e.target.files?.[0]); e.target.value = ""; }} />
          </label>
          {extra.video && (
            <button type="button" className="link-acao link-acao-erro" onClick={() => void tirarVideo()}>
              tirar
            </button>
          )}
        </div>
      </div>
      <div>
        <span className="rotulo-campo">Restrições alimentares</span>
        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-2 text-[14px]">
          {extra.opcoes_restricoes.map((r) => (
            <label key={r.chave} className="flex items-center gap-2">
              <input type="checkbox" checked={extra.restricoes.includes(r.chave)}
                     onChange={() => void restricao(r.chave)} />
              {r.nome}
            </label>
          ))}
        </div>
      </div>
    </>
  );
}
