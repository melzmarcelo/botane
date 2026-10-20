"use client";

/**
 * A janela de UM cartão de conteúdo do Cardápio Vivo (120): título, texto, onde fica, o botão
 * "Ver o prato" e a mídia — foto OU vídeo.
 *
 * 🔑 Criar grava o texto e a posição e DEIXA A JANELA ABERTA no cartão novo: a foto e o vídeo
 * pedem o cartão já gravado, e fechar no meio obrigaria a achar o cartão e abrir de novo.
 * ⚠️ O vídeo segue a regra do prato (até 15 s, sem som); a foto enviada troca o vídeo e
 * vice-versa — o cartão mostra uma mídia só.
 */

import { useRef, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Confirmacao, Modal } from "@/components/ui";
import { urlArquivo } from "@/lib/api";
import type * as cat from "@/lib/catalogos";
import Traducoes from "@/components/traducoes";
import { CartoesService, type Cartao } from "@/lib/cartoes";

export type AbrindoCartao = {
  cartao: Cartao | null;
  /** A lista onde o cartão novo nasce. `id_categoria` nulo = abertura do cardápio. */
  id_categoria: number | null;
  id_subcategoria: number | null;
  onde: string;
};

type Props = {
  idCatalogo: number;
  abrindo: AbrindoCartao;
  /** Os pratos da lista do cartão — a posição é "antes de um deles". */
  pratosDaLista: cat.ItemDoCatalogo[];
  /** Todos os pratos do cardápio — o "Ver o prato" pode levar a qualquer um. */
  todosOsPratos: cat.ItemDoCatalogo[];
  podeEditar: boolean;
  /** De quando é a atenção mostrada ("últimos 30 dias"…), o que a aba escolheu. */
  periodo: string;
  aoFechar: () => void;
  aoMudar: () => Promise<void>;
};

const nomeDo = (i: cat.ItemDoCatalogo) => i.nome_catalogo || i.produto;

export default function JanelaCartao({ idCatalogo, abrindo, pratosDaLista, todosOsPratos, podeEditar, periodo, aoFechar, aoMudar }: Props) {
  const aviso = useAviso();
  const [atual, setAtual] = useState<Cartao | null>(abrindo.cartao);
  const [titulo, setTitulo] = useState(atual?.titulo ?? "");
  const [texto, setTexto] = useState(atual?.texto ?? "");
  const [antes, setAntes] = useState<number | null>(atual?.antes_do_item ?? null);
  const [link, setLink] = useState<number | null>(atual?.id_item_link ?? null);
  const [ativo, setAtivo] = useState(atual?.ativo ?? true);
  const [salvando, setSalvando] = useState(false);
  const [enviando, setEnviando] = useState<"" | "foto" | "video">("");
  const [apagando, setApagando] = useState(false);
  const [traduzindo, setTraduzindo] = useState(false);
  const foto = useRef<HTMLInputElement>(null);
  const video = useRef<HTMLInputElement>(null);
  const abertura = abrindo.id_categoria === null;
  const falhou = (e: unknown, padrao: string) => aviso.erro(e instanceof Error ? e.message : padrao);

  async function salvar() {
    const corpo = {
      id_categoria: abrindo.id_categoria, id_subcategoria: abrindo.id_subcategoria,
      antes_do_item: abertura ? null : antes, titulo: titulo.trim() || null, texto: texto.trim() || null,
      id_item_link: link, ativo,
    };
    setSalvando(true);
    try {
      if (atual) {
        setAtual(await CartoesService.atualizar(atual.id, corpo));
        await aoMudar();
        aviso.sucesso("Cartão gravado.");
        aoFechar();
      } else {
        setAtual(await CartoesService.criar(idCatalogo, corpo));
        await aoMudar();
        aviso.sucesso("Cartão criado. Se quiser, ponha agora a foto ou o vídeo.");
      }
    } catch (e) {
      falhou(e, "Não foi possível gravar o cartão.");
    } finally {
      setSalvando(false);
    }
  }

  async function midia(tipo: "foto" | "video", arquivo: File | undefined) {
    if (!arquivo || !atual) return;
    setEnviando(tipo);
    try {
      const r = tipo === "foto"
        ? await CartoesService.enviarFoto(atual.id, arquivo)
        : await CartoesService.enviarVideo(atual.id, arquivo);
      setAtual(r);
      await aoMudar();
      aviso.sucesso(tipo === "video" ? ((r as { message?: string }).message ?? "Vídeo gravado.") : "Foto gravada.");
    } catch (e) {
      falhou(e, `Não foi possível enviar ${tipo === "foto" ? "a foto" : "o vídeo"}.`);
    } finally {
      setEnviando("");
      if (foto.current) foto.current.value = "";
      if (video.current) video.current.value = "";
    }
  }

  async function tirarMidia() {
    if (!atual) return;
    try {
      setAtual(await CartoesService.removerMidia(atual.id));
      await aoMudar();
    } catch (e) {
      falhou(e, "Não foi possível tirar a mídia.");
    }
  }

  async function excluir() {
    if (!atual) return;
    try {
      await CartoesService.remover(atual.id);
      setApagando(false);
      aoFechar();
      await aoMudar();
      aviso.sucesso("Cartão removido.");
    } catch (e) {
      falhou(e, "Não foi possível remover.");
    }
  }

  const capa = atual?.video_capa_url ?? atual?.foto_url ?? null;
  return (
    <Modal
      titulo={atual ? "Cartão do Cardápio Vivo" : abertura ? "Nova abertura do cardápio" : "Novo cartão"}
      descricao={`${abrindo.onde}. Só no Cardápio Vivo — sem preço e sem botão de adicionar.`}
      aoFechar={aoFechar}
      largura="620px"
      rodape={
        <div className="flex flex-wrap items-center justify-end gap-2">
          {atual && podeEditar && (
            <button type="button" className="link-acao link-acao-erro mr-auto" onClick={() => setApagando(true)}>
              excluir cartão
            </button>
          )}
          <button type="button" className="btn btn-secundario" onClick={aoFechar}>{atual ? "Fechar" : "Cancelar"}</button>
          {podeEditar && (
            <button type="button" className="btn btn-primario" id="cartao-gravar" aria-busy={salvando} disabled={salvando}
                    onClick={() => void salvar()}>
              {atual ? "Gravar" : "Criar cartão"}
            </button>
          )}
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        <Campo rotulo="Título" opcional dica="Grande, na fonte da casa. Ex.: “Massas frescas, feitas aqui”.">
          <input id="cartao-titulo" className="campo" maxLength={120} autoFocus disabled={!podeEditar}
                 value={titulo} onChange={(e) => setTitulo(e.target.value)} />
        </Campo>
        <Campo rotulo="Texto" opcional dica="Até 700 letras. Traduzido para inglês e alemão sozinho, como os pratos.">
          <textarea id="cartao-texto" className="campo" rows={4} maxLength={700} disabled={!podeEditar}
                    value={texto} onChange={(e) => setTexto(e.target.value)} />
        </Campo>
        {!abertura && (
          <Campo rotulo="Onde aparece" dica="O cartão fica colado no prato: se o prato subir ou descer, ele vai junto.">
            <select id="cartao-posicao" className="campo" disabled={!podeEditar} value={antes ?? ""}
                    onChange={(e) => setAntes(e.target.value ? Number(e.target.value) : null)}>
              {pratosDaLista.map((i) => <option key={i.id} value={i.id}>antes de {nomeDo(i)}</option>)}
              <option value="">no fim da lista</option>
            </select>
          </Campo>
        )}
        <Campo rotulo="Botão “Ver o prato”" opcional dica="Leva o cliente direto ao prato citado no cartão.">
          <select id="cartao-link" className="campo" disabled={!podeEditar} value={link ?? ""}
                  onChange={(e) => setLink(e.target.value ? Number(e.target.value) : null)}>
            <option value="">sem botão</option>
            {todosOsPratos.map((i) => <option key={i.id} value={i.id}>{nomeDo(i)}</option>)}
          </select>
        </Campo>
        <label className="flex items-center gap-2 text-[14px]">
          <input type="checkbox" checked={ativo} disabled={!podeEditar} onChange={(e) => setAtivo(e.target.checked)} />
          Ligado — aparece no Cardápio Vivo
        </label>

        {atual ? (
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
                {atual.video_url ? `Vídeo de ${Number(atual.video_segundos ?? 0).toFixed(0)} s.`
                  : atual.foto_url ? "Foto." : "Sem mídia: o fundo é a capa da casa e o texto vai ao centro."}
              </span>
              {podeEditar && (
                <span className="flex flex-wrap gap-2">
                  <input ref={foto} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                         onChange={(e) => void midia("foto", e.target.files?.[0])} />
                  <input ref={video} type="file" accept="video/mp4,video/quicktime,video/webm" className="hidden"
                         onChange={(e) => void midia("video", e.target.files?.[0])} />
                  <button type="button" className="btn btn-secundario" disabled={!!enviando} onClick={() => foto.current?.click()}>
                    {enviando === "foto" ? "Enviando…" : "Pôr foto"}
                  </button>
                  <button type="button" className="btn btn-secundario" disabled={!!enviando} onClick={() => video.current?.click()}>
                    {enviando === "video" ? "Convertendo…" : "Pôr vídeo"}
                  </button>
                  {(atual.foto_url || atual.video_url) && (
                    <button type="button" className="link-acao link-acao-erro" onClick={() => void tirarMidia()}>tirar</button>
                  )}
                </span>
              )}
            </div>
            <p className="mt-1 text-[12.5px] text-suave">Vídeo de até 15 s, sem som. A foto troca o vídeo, e o vídeo a foto.</p>
            {(atual.vistas ?? 0) > 0 && (
              <p className="mt-3 text-[13px]">
                Nos {periodo}: visto <b>{atual.vistas}×</b>, <b>{atual.segundos ?? 0} s</b> em média
                {atual.cliques ? <>, <b>{atual.cliques}</b> toques no “Ver o prato”</> : null}.
              </p>
            )}
          </div>
        ) : (
          <p className="text-[13px] text-suave">A foto ou o vídeo entram depois de criar o cartão.</p>
        )}

        {/* 🔑 A correção da tradução (16/10/2026, pedido do dono): o Claude traduz ao gravar, e
            aqui se confere e se corrige — o campo corrigido à mão a tradução automática não
            sobrescreve. ⚠️ Vale o que está GRAVADO: mudou o português, grave antes. */}
        {atual && podeEditar && (
          traduzindo ? (
            <Traducoes key={`${atual.titulo}|${atual.texto}`} tipo="cartao" id={atual.id}
                       rotulos={{ nome: "Título", descricao: "Texto" }} maxNome={120} />
          ) : (
            <p className="text-[13.5px]">
              <button type="button" className="link-acao" id="cartao-traducoes" onClick={() => setTraduzindo(true)}>
                traduções
              </button>
              <span className="ml-2 text-suave">o título e o texto em inglês e alemão</span>
            </p>
          )
        )}
      </div>

      {apagando && atual && (
        <Confirmacao titulo="Excluir este cartão?" rotuloConfirmar="Excluir" perigo
                     aoConfirmar={() => void excluir()} aoCancelar={() => setApagando(false)}>
          <p>Ele sai do Cardápio Vivo, com a foto ou o vídeo. Os pratos não mudam.</p>
        </Confirmacao>
      )}
    </Modal>
  );
}
