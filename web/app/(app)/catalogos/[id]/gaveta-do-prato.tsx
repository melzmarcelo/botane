"use client";

/**
 * A gaveta do PRATO: tudo de um item do cardápio, sem sair do cardápio.
 *
 * 🔑 **Reforma de 15/10/2026.** Foto, descrição, nome de vitrine, vídeo e
 * restrições ficavam na aba Catálogo do PRODUTO — arrumar quarenta pratos eram
 * quarenta idas e voltas. Aqui eles se editam no lugar.
 * 🔑 **Decisão do dono: o que é do produto continua sendo do produto.** A gaveta
 * diz isso com todas as letras ("vale em todo cardápio em que ele estiver"): um
 * prato com duas fotos em dois cardápios seria cadastro duplicado. E a permissão
 * é a do produto (`cadastros.produtos`) — quem só edita catálogo vê, sem mexer.
 * ⚠️ As marcas DESTE cardápio (destaque, esgotado, objetivo, margem) são do ITEM,
 * e ficam numa parte separada, com a permissão do catálogo.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Gaveta } from "@/components/ui";
import { urlArquivo } from "@/lib/api";
import { CardapioVivoService, ProdutoCardapioService, type CardapioDoProduto } from "@/lib/cardapio-vivo";
import * as cat from "@/lib/catalogos";
import { reais } from "@/lib/numeros";
import { MARGENS, OBJETIVOS } from "./cardapio-vivo";

type Props = {
  item: cat.ItemDoCatalogo;
  /** Onde ele está: "Menu Principal ▸ Pra Dividir". */
  onde: string;
  podeEditar: boolean;
  podeProduto: boolean;
  aoMudar: () => Promise<void>;
  aoFechar: () => void;
};

export default function GavetaDoPrato({ item: i, onde, podeEditar, podeProduto, aoMudar, aoFechar }: Props) {
  const aviso = useAviso();
  const falhou = (e: unknown, padrao: string) => aviso.erro(e instanceof Error ? e.message : padrao);
  const [nome, setNome] = useState(i.nome_catalogo ?? "");
  const [descricao, setDescricao] = useState(i.informacao_adicional ?? "");
  const [gravando, setGravando] = useState(false);
  const [enviando, setEnviando] = useState<"" | "foto" | "video">("");
  const [extra, setExtra] = useState<CardapioDoProduto | null>(null);

  // O vídeo e as restrições vêm da rota do produto, que pede a permissão dele.
  useEffect(() => {
    if (!podeProduto) return;
    ProdutoCardapioService.obter(i.id_produto).then(setExtra).catch(() => setExtra(null));
  }, [i.id_produto, podeProduto]);

  const mudouTexto = nome.trim() !== (i.nome_catalogo ?? "") || descricao.trim() !== (i.informacao_adicional ?? "");

  async function marcar(marcas: Parameters<typeof CardapioVivoService.marcarItem>[1]) {
    try {
      const r = await CardapioVivoService.marcarItem(i.id, marcas);
      await aoMudar();
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível marcar.");
    }
  }

  async function gravarTexto() {
    setGravando(true);
    try {
      await cat.gravarVitrine(i.id_produto, {
        nome_catalogo: nome.trim() || null,
        informacao_adicional: descricao.trim() || null,
      });
      await aoMudar();
      aviso.sucesso("Prato salvo.");
    } catch (e) {
      falhou(e, "Não foi possível salvar.");
    } finally {
      setGravando(false);
    }
  }

  async function foto(arquivo: File | undefined) {
    if (!arquivo) return;
    setEnviando("foto");
    try {
      await cat.enviarFotoDoProduto(i.id_produto, arquivo);
      await aoMudar();
      aviso.sucesso("Foto atualizada.");
    } catch (e) {
      falhou(e, "Não foi possível enviar a foto.");
    } finally {
      setEnviando("");
    }
  }

  async function tirarFoto() {
    try {
      await cat.removerFotoDoProduto(i.id_produto);
      await aoMudar();
      aviso.sucesso("Foto removida.");
    } catch (e) {
      falhou(e, "Não foi possível tirar a foto.");
    }
  }

  async function video(arquivo: File | undefined) {
    if (!arquivo) return;
    setEnviando("video");
    try {
      const r = await ProdutoCardapioService.enviarVideo(i.id_produto, arquivo);
      setExtra((x) => x && { ...x, video: r.video });
      await aoMudar();
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível enviar o vídeo.");
    } finally {
      setEnviando("");
    }
  }

  async function tirarVideo() {
    try {
      const r = await ProdutoCardapioService.removerVideo(i.id_produto);
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
      const r = await ProdutoCardapioService.restricoes(i.id_produto, novas);
      setExtra({ ...extra, restricoes: r.restricoes });
    } catch (e) {
      falhou(e, "Não foi possível gravar a restrição.");
    }
  }

  async function tirarDoCardapio() {
    try {
      const r = await cat.desvincularProduto(i.id);
      aoFechar();
      await aoMudar();
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível tirar.");
    }
  }

  return (
    <Gaveta
      titulo={i.nome_catalogo || i.produto}
      descricao={
        <>
          {i.codigo} · {i.produto} ·{" "}
          <Link href={`/produtos/${i.id_produto}`} className="link-registro">cadastro completo</Link>
        </>
      }
      aoFechar={aoFechar}
    >
      <div className="flex flex-col gap-6">
        {!i.ativo && (
          <p className="rounded border border-alerta/40 bg-alerta-claro px-3 py-2 text-[13.5px] text-alerta">
            O produto está <b>inativo</b>: o cliente não o vê, embora continue aqui.
          </p>
        )}

        {/* ------------------------------------------- deste cardápio --- */}
        <section className="flex flex-col gap-3">
          <h3 className="rotulo">Neste cardápio</h3>
          <p className="text-[13.5px] text-suave">Em <b className="text-tinta">{onde}</b>
            {" · "}{i.preco !== null ? <>preço {reais(i.preco)}</> : "sem preço na loja"}</p>
          <label className="flex items-center gap-2 text-[14px]">
            <input type="checkbox" disabled={!podeEditar} checked={i.destaque}
                   onChange={(e) => void marcar({ destaque: e.target.checked })} />
            ★ Em destaque
          </label>
          <label className="flex items-center gap-2 text-[14px]">
            <input type="checkbox" disabled={!podeEditar} checked={i.esgotado}
                   onChange={(e) => void marcar({ esgotado: e.target.checked })} />
            Esgotado <span className="text-[13px] text-suave">(fica no cardápio, sem poder pedir)</span>
          </label>
          {/* 🔑 Fase 2 (115): o painel Atenção × Vendas usa os dois para priorizar. */}
          <div className="grid gap-3 sm:grid-cols-2">
            <Campo rotulo="Objetivo">
              <select className="campo" aria-label="Objetivo de negócio" disabled={!podeEditar}
                      value={i.objetivo ?? ""} onChange={(e) => void marcar({ objetivo: e.target.value })}>
                {OBJETIVOS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Margem" dica="Da ficha: pela margem-alvo da Precificação.">
              <select className="campo" aria-label="Nível de margem" disabled={!podeEditar}
                      value={i.margem_nivel ?? ""} onChange={(e) => void marcar({ margem_nivel: e.target.value })}>
                {MARGENS.map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </Campo>
          </div>
        </section>

        {/* ---------------------------------------------- o prato ------- */}
        <section className="flex flex-col gap-3 border-t border-linha pt-5">
          <h3 className="rotulo">O prato</h3>
          <p className="text-[13px] text-suave">
            ⚠️ É o cadastro do produto: vale em <b>todo</b> cardápio em que ele estiver.
            {!podeProduto && " Para mudar, é preciso a permissão de produtos."}
          </p>

          <div className="flex items-center gap-3">
            <span className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-linha bg-superficie2">
              {i.foto_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={urlArquivo(i.foto_url) ?? undefined} alt="" className="h-full w-full object-cover" />
              ) : (
                <span className="text-[12px] text-suave">sem foto</span>
              )}
            </span>
            {podeProduto && (
              <span className="flex flex-col items-start gap-2">
                {/* ⚠️ `relative` no rótulo: o input `sr-only` é absoluto, e sem
                    ancestral posicionado escapa e faz a página rolar de lado. */}
                <label className={`btn btn-secundario relative cursor-pointer ${enviando === "foto" ? "opacity-60" : ""}`}>
                  {enviando === "foto" ? "Enviando…" : i.foto_url ? "Trocar foto" : "Pôr foto"}
                  <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" id="prato-foto"
                         disabled={!!enviando}
                         onChange={(e) => { void foto(e.target.files?.[0]); e.target.value = ""; }} />
                </label>
                {i.foto_url && (
                  <button type="button" className="link-acao link-acao-erro" onClick={() => void tirarFoto()}>
                    tirar foto
                  </button>
                )}
              </span>
            )}
          </div>

          <Campo rotulo="Nome no cardápio" dica={`Em branco, sai o do cadastro: ${i.produto}.`}>
            <input className="campo" id="prato-nome" maxLength={120} disabled={!podeProduto}
                   placeholder={i.produto} value={nome} onChange={(e) => setNome(e.target.value)} />
          </Campo>
          <Campo rotulo="Descrição" dica="O que o cliente lê embaixo do nome.">
            <textarea className="campo" id="prato-descricao" rows={4} maxLength={1000} disabled={!podeProduto}
                      value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </Campo>
          {podeProduto && (
            <div className="flex justify-end">
              <button type="button" className="btn btn-primario" aria-busy={gravando}
                      disabled={gravando || !mudouTexto} onClick={() => void gravarTexto()}>
                {gravando ? "Salvando…" : "Salvar nome e descrição"}
              </button>
            </div>
          )}

          {extra && (
            <>
              <div>
                <span className="rotulo-campo">Vídeo</span>
                <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[13.5px]">
                  <span className="text-suave">
                    {extra.video
                      ? `${extra.video.nome ?? "vídeo"} · ${extra.video.segundos?.toFixed(0) ?? "?"} s — aparece no lugar da foto`
                      : "Sem vídeo. Até 15 s, sem som."}
                  </span>
                  <label className={`btn btn-secundario relative cursor-pointer ${enviando === "video" ? "opacity-60" : ""}`}>
                    {enviando === "video" ? "Convertendo…" : extra.video ? "Trocar vídeo" : "Enviar vídeo"}
                    <input type="file" accept="video/mp4,video/quicktime,video/webm" className="sr-only"
                           disabled={!!enviando}
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
              <p className="text-[13px] text-suave">
                Adicionais e opções (ponto da carne, acompanhamentos) ficam no{" "}
                <Link href={`/produtos/${i.id_produto}`} className="link-registro">cadastro do produto</Link>, aba Catálogo.
              </p>
            </>
          )}
        </section>

        {podeEditar && (
          <section className="border-t border-linha pt-5">
            <button type="button" className="link-acao link-acao-erro" onClick={() => void tirarDoCardapio()}>
              Tirar deste cardápio
            </button>
            <p className="mt-1 text-[13px] text-suave">O produto continua cadastrado; sai só desta lista.</p>
          </section>
        )}
      </div>
    </Gaveta>
  );
}
