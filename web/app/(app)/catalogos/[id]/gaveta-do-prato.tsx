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
import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Gaveta } from "@/components/ui";
import { urlArquivo } from "@/lib/api";
import { CardapioVivoService } from "@/lib/cardapio-vivo";
import * as cat from "@/lib/catalogos";
import { reais } from "@/lib/numeros";
import { MARGENS, OBJETIVOS } from "./cardapio-vivo";
import { SecaoDaEscolha } from "./escolha";
import VideoERestricoes from "./video-e-restricoes";

/** Uma lista do cardápio para onde o prato pode ir. */
export type Lugar = { rotulo: string; id_categoria: number; id_subcategoria: number | null };

type Props = {
  item: cat.ItemDoCatalogo;
  /** Todas as listas do catálogo, para o "mover para". */
  lugares: Lugar[];
  /** Onde ele está: "Menu Principal ▸ Pra Dividir". */
  onde: string;
  podeEditar: boolean;
  podeProduto: boolean;
  aoMudar: () => Promise<void>;
  aoFechar: () => void;
};

export default function GavetaDoPrato({ item: i, lugares, onde, podeEditar, podeProduto, aoMudar, aoFechar }: Props) {
  const aviso = useAviso();
  const falhou = (e: unknown, padrao: string) => aviso.erro(e instanceof Error ? e.message : padrao);
  const [nome, setNome] = useState(i.nome_catalogo ?? "");
  const [descricao, setDescricao] = useState(i.informacao_adicional ?? "");
  const [gravando, setGravando] = useState(false);
  const [enviando, setEnviando] = useState(false);

  const mudouTexto = nome.trim() !== (i.nome_catalogo ?? "") || descricao.trim() !== (i.informacao_adicional ?? "");

  const [volta, setVolta] = useState<"AMANHA" | "MANUAL">("AMANHA");
  // 🔑 142: o item de ESCOLHA não tem produto — a parte "O prato" vira a das opções.
  const escolha = i.tipo === "ESCOLHA";

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
    setEnviando(true);
    try {
      await cat.enviarFotoDoProduto(i.id_produto, arquivo);
      await aoMudar();
      aviso.sucesso("Foto atualizada.");
    } catch (e) {
      falhou(e, "Não foi possível enviar a foto.");
    } finally {
      setEnviando(false);
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

  async function mover(chave: string) {
    const l = lugares.find((x) => `${x.id_categoria}-${x.id_subcategoria ?? ""}` === chave);
    if (!l) return;
    try {
      const r = await cat.moverItem(i.id, { id_categoria: l.id_categoria, id_subcategoria: l.id_subcategoria });
      await aoMudar();
      aviso.sucesso(r.message);
    } catch (e) {
      falhou(e, "Não foi possível mover.");
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
      descricao={escolha ? <>Item de escolha · {i.escolhas?.length ?? 0} opções</> : (
        <>
          {i.codigo} · {i.produto} ·{" "}
          <Link href={`/produtos/${i.id_produto}`} className="link-registro">cadastro completo</Link>
        </>
      )}
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
          {/* 🔑 Mover não é tirar e pôr: leva as marcas e entra no fim da lista nova. */}
          {podeEditar && lugares.length > 1 && (
            <Campo rotulo="Mover para" dica="Leva junto destaque, esgotado, objetivo e margem.">
              <select className="campo" id="prato-mover" value=""
                      onChange={(e) => void mover(e.target.value)}>
                <option value="">— escolha a seção —</option>
                {lugares
                  .filter((l) => !(l.id_categoria === i.id_categoria && l.id_subcategoria === i.id_subcategoria))
                  .map((l) => (
                    <option key={`${l.id_categoria}-${l.id_subcategoria ?? ""}`}
                            value={`${l.id_categoria}-${l.id_subcategoria ?? ""}`}>{l.rotulo}</option>
                  ))}
              </select>
            </Campo>
          )}
          <label className="flex items-center gap-2 text-[14px]">
            <input type="checkbox" disabled={!podeEditar} checked={i.destaque}
                   onChange={(e) => void marcar({ destaque: e.target.checked })} />
            ★ Em destaque
          </label>
          {/* 🔑 123: o esgotado volta sozinho no próximo dia (o padrão), ou só quando alguém tirar. */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[14px]">
            <label className="flex items-center gap-2">
              <input type="checkbox" id="prato-esgotado" disabled={!podeEditar} checked={i.esgotado}
                     onChange={(e) => void marcar(e.target.checked
                       ? { esgotado: true, esgotado_volta: volta } : { esgotado: false })} />
              Esgotado <span className="text-[13px] text-suave">(fica no cardápio, sem poder pedir)</span>
            </label>
            {i.esgotado ? (
              <span className="text-[13px] text-suave" id="prato-esgotado-volta">
                {i.esgotado_ate
                  ? `volta sozinho ${new Date(i.esgotado_ate).toLocaleString("pt-BR", { weekday: "long", hour: "2-digit", minute: "2-digit" })}`
                  : "até alguém tirar"}
              </span>
            ) : podeEditar && (
              <select className="campo !w-auto !py-1 text-[13px]" aria-label="Quando o esgotado volta"
                      value={volta} onChange={(e) => setVolta(e.target.value as "AMANHA" | "MANUAL")}>
                <option value="AMANHA">volta sozinho amanhã (4h)</option>
                <option value="MANUAL">só quando alguém tirar</option>
              </select>
            )}
          </div>
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

        {escolha && <SecaoDaEscolha key={i.id} item={i} podeEditar={podeEditar} podeProduto={podeProduto} aoMudar={aoMudar} />}

        {/* ---------------------------------------------- o prato ------- */}
        {!escolha && (
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
                <label className={`btn btn-secundario relative cursor-pointer ${enviando ? "opacity-60" : ""}`}>
                  {enviando ? "Enviando…" : i.foto_url ? "Trocar foto" : "Pôr foto"}
                  <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" id="prato-foto"
                         disabled={enviando}
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

          {podeProduto && <VideoERestricoes idProduto={i.id_produto} aoMudar={aoMudar} />}
          <p className="text-[13px] text-suave">
            Adicionais e opções (ponto da carne, acompanhamentos) ficam no{" "}
            <Link href={`/produtos/${i.id_produto}`} className="link-registro">cadastro do produto</Link>, aba Catálogo.
          </p>
        </section>
        )}

        {podeEditar && (
          <section className="border-t border-linha pt-5">
            <button type="button" className="link-acao link-acao-erro" onClick={() => void tirarDoCardapio()}>
              Tirar deste cardápio
            </button>
            <p className="mt-1 text-[13px] text-suave">
              {escolha ? "O item e as opções dele saem; os produtos das opções continuam cadastrados."
                : "O produto continua cadastrado; sai só desta lista."}
            </p>
          </section>
        )}
      </div>
    </Gaveta>
  );
}
