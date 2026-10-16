"use client";

/**
 * A janela de uma seção — categoria ou subcategoria, que têm os mesmos campos.
 *
 * 🔑 **Reforma de 15/10/2026**: a foto e o "quando aparece no Cardápio Vivo"
 * ficavam ABERTOS em cima de cada seção, e a tela ficava longa antes do primeiro
 * prato. Agora moram aqui, junto do nome — e as traduções e o excluir também.
 * ⚠️ O campo numérico de ORDEM saiu: a seção sobe e desce pelas setas do painel,
 * como os pratos. Um número que só a casa entende ("10? 15?") não é ordem.
 * ⚠️ Criando, só nome e descrição: foto e horário pedem a seção já gravada.
 */

import { useRef, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Confirmacao, Modal } from "@/components/ui";
import { urlArquivo } from "@/lib/api";
import * as cat from "@/lib/catalogos";
import { CartoesService } from "@/lib/cartoes";
import { ExibicaoDaSecao } from "./cardapio-vivo";
import { JanelaDeTraducao } from "./traducoes-do-catalogo";

export type Editando = {
  tipo: cat.TipoDeSecao;
  /** A seção gravada; nula = criando. */
  secao: cat.Secao | null;
  /** O catálogo (categoria) ou a categoria (subcategoria). */
  idPai: number;
  /** A ordem da seção nova: fim da lista. */
  ordemNova: number;
  /** Quantos pratos saem junto se ela for excluída. */
  itens: number;
};

type Props = {
  editando: Editando;
  podeEditar: boolean;
  aoFechar: () => void;
  /** Depois de gravar; recebe o id, para a seção nova já abrir selecionada. */
  aoSalvar: (id: number) => Promise<void>;
  aoMudar: () => Promise<void>;
  aoExcluir: () => Promise<void>;
};

export default function JanelaSecao({ editando: e, podeEditar, aoFechar, aoSalvar, aoMudar, aoExcluir }: Props) {
  const aviso = useAviso();
  const nomeTipo = e.tipo === "categoria" ? "categoria" : "subcategoria";
  const [nome, setNome] = useState(e.secao?.nome ?? "");
  const [descricao, setDescricao] = useState(e.secao?.descricao ?? "");
  const [salvando, setSalvando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [apagando, setApagando] = useState(false);
  const [traduzindo, setTraduzindo] = useState(false);
  const seletor = useRef<HTMLInputElement>(null);
  const seletorVideo = useRef<HTMLInputElement>(null);
  const [convertendo, setConvertendo] = useState(false);
  const s = e.secao;

  async function salvar() {
    const corpo = { nome: nome.trim(), descricao: descricao.trim() || null, ordem: s?.ordem ?? e.ordemNova };
    setSalvando(true);
    try {
      let id: number;
      if (e.tipo === "categoria") {
        id = s ? (await cat.atualizarCategoria(s.id, corpo)).id : (await cat.criarCategoria(e.idPai, corpo)).id;
      } else {
        id = s ? (await cat.atualizarSubcategoria(s.id, corpo)).id : (await cat.criarSubcategoria(e.idPai, corpo)).id;
      }
      await aoSalvar(id);
      aviso.sucesso(s ? "Alterado." : `${nomeTipo[0].toUpperCase()}${nomeTipo.slice(1)} criada.`);
      aoFechar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function foto(arquivo: File | undefined) {
    if (!arquivo || !s) return;
    setEnviando(true);
    try {
      await cat.enviarFotoDaSecao(e.tipo, s.id, arquivo);
      await aoMudar();
      aviso.sucesso("Foto atualizada.");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível enviar");
    } finally {
      setEnviando(false);
      // ⚠️ Zera: escolher o MESMO arquivo depois de um erro não dispararia `change`.
      if (seletor.current) seletor.current.value = "";
    }
  }

  async function tirarFoto() {
    if (!s) return;
    try {
      await cat.removerFotoDaSecao(e.tipo, s.id);
      await aoMudar();
      aviso.sucesso("Foto removida.");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível remover");
    }
  }

  /** 120: o vídeo da abertura da seção no Cardápio Vivo — ganha da foto quando existe. */
  async function video(arquivo: File | undefined) {
    if (!arquivo || !s) return;
    setConvertendo(true);
    try {
      const r = await CartoesService.enviarVideoDaSecao(e.tipo, s.id, arquivo);
      await aoMudar();
      aviso.sucesso(r.message);
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível enviar o vídeo");
    } finally {
      setConvertendo(false);
      if (seletorVideo.current) seletorVideo.current.value = "";
    }
  }

  async function tirarVideo() {
    if (!s) return;
    try {
      await CartoesService.removerVideoDaSecao(e.tipo, s.id);
      await aoMudar();
      aviso.sucesso("Vídeo removido — a abertura volta a usar a foto.");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível remover");
    }
  }

  async function excluir() {
    if (!s) return;
    try {
      if (e.tipo === "categoria") await cat.excluirCategoria(s.id);
      else await cat.excluirSubcategoria(s.id);
      setApagando(false);
      aoFechar();
      await aoExcluir();
      aviso.sucesso("Removido.");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível remover");
    }
  }

  return (
    <Modal
      titulo={`${s ? "Seção" : "Nova"} ${s ? `— ${s.nome}` : nomeTipo}`}
      descricao={s ? undefined : e.tipo === "categoria"
        ? "Uma parte do cardápio: “Menu Principal”, “Bebidas”."
        : "Uma divisão dentro da categoria: “Pra Dividir”, “Pratos”."}
      aoFechar={aoFechar}
      largura="620px"
      rodape={
        <div className="flex flex-wrap items-center justify-end gap-2">
          {s && podeEditar && (
            <button type="button" className="link-acao link-acao-erro mr-auto" onClick={() => setApagando(true)}>
              excluir {nomeTipo}
            </button>
          )}
          <button type="button" className="btn btn-secundario" onClick={aoFechar}>
            {podeEditar ? "Cancelar" : "Fechar"}
          </button>
          {podeEditar && (
            <button type="button" className="btn btn-primario" aria-busy={salvando}
                    disabled={salvando || nome.trim().length < 2} onClick={() => void salvar()}>
              {s ? "Salvar" : `Criar ${nomeTipo}`}
            </button>
          )}
        </div>
      }
    >
      <div className="flex flex-col gap-5">
        <Campo rotulo="Nome" dica="É o que o cliente lê no cardápio.">
          <input id="secao-nome" className="campo" maxLength={120} autoFocus disabled={!podeEditar}
                 value={nome} onChange={(ev) => setNome(ev.target.value)} />
        </Campo>
        <Campo rotulo="Descrição" dica="Opcional. Aparece abaixo do nome.">
          <textarea id="secao-descricao" className="campo" rows={3} maxLength={500} disabled={!podeEditar}
                    value={descricao} onChange={(ev) => setDescricao(ev.target.value)} />
        </Campo>

        {s && (
          <>
            <div>
              <span className="rotulo-campo">Foto</span>
              <div className="mt-1.5 flex items-center gap-3">
                <span className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-linha bg-superficie2">
                  {s.foto_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={urlArquivo(s.foto_url) ?? undefined} alt={s.nome} className="h-full w-full object-cover" />
                  ) : (
                    <span className="text-[11px] text-suave">sem foto</span>
                  )}
                </span>
                {podeEditar && (
                  <span className="flex flex-col items-start gap-1">
                    <input ref={seletor} type="file" accept="image/png,image/jpeg,image/webp" className="hidden"
                           onChange={(ev) => void foto(ev.target.files?.[0])} />
                    <button type="button" className="link-acao" disabled={enviando}
                            onClick={() => seletor.current?.click()}>
                      {enviando ? "enviando…" : s.foto_url ? "trocar foto" : "pôr foto"}
                    </button>
                    {s.foto_url && (
                      <button type="button" className="link-acao link-acao-erro" onClick={() => void tirarFoto()}>
                        tirar foto
                      </button>
                    )}
                  </span>
                )}
              </div>
              <p className="mt-1 text-[12.5px] text-suave">
                É a capa da seção no site e a foto de reserva dos pratos sem foto no Cardápio Vivo.
                No Cardápio Vivo, com foto (ou vídeo) a seção ganha uma tela de abertura com o nome e a descrição.
              </p>
            </div>

            <div>
              <span className="rotulo-campo">Vídeo da abertura (Cardápio Vivo)</span>
              <div className="mt-1.5 flex flex-wrap items-center gap-3 text-[13.5px]">
                <span className="text-suave">
                  {s.video_url ? "A abertura da seção mostra este vídeo no lugar da foto." : "Sem vídeo. Até 15 s, sem som."}
                </span>
                {podeEditar && (
                  <>
                    <input ref={seletorVideo} type="file" accept="video/mp4,video/quicktime,video/webm" className="hidden"
                           onChange={(ev) => void video(ev.target.files?.[0])} />
                    <button type="button" className="link-acao" disabled={convertendo}
                            onClick={() => seletorVideo.current?.click()}>
                      {convertendo ? "convertendo…" : s.video_url ? "trocar vídeo" : "pôr vídeo"}
                    </button>
                    {s.video_url && (
                      <button type="button" className="link-acao link-acao-erro" onClick={() => void tirarVideo()}>
                        tirar vídeo
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>

            <ExibicaoDaSecao key={`${s.dias}${s.hora_de}${s.hora_ate}${s.horario_especial}`}
                             tipo={e.tipo} secao={s} podeEditar={podeEditar} aoMudar={aoMudar} />

            {podeEditar && (
              <p className="text-[13.5px]">
                <button type="button" className="link-acao" onClick={() => setTraduzindo(true)}>traduções</button>
                <span className="ml-2 text-suave">o nome e a descrição em inglês e alemão</span>
              </p>
            )}
          </>
        )}
      </div>

      {traduzindo && s && (
        <JanelaDeTraducao tipo={e.tipo} id={s.id} nome={s.nome} aoFechar={() => setTraduzindo(false)} />
      )}
      {apagando && s && (
        <Confirmacao titulo={`Excluir "${s.nome}"?`} rotuloConfirmar="Excluir" perigo
                     aoConfirmar={() => void excluir()} aoCancelar={() => setApagando(false)}>
          {/* 🔑 A frase diz QUANTOS pratos saem junto. */}
          <p>
            {e.itens > 0
              ? `${e.itens} prato(s) saem do cardápio junto. Os produtos continuam cadastrados — o que se desfaz é o vínculo.`
              : "Não há prato nenhum nela."}
            {e.tipo === "categoria" && " As subcategorias dela também são removidas."}
          </p>
        </Confirmacao>
      )}
    </Modal>
  );
}
