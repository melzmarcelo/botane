"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Etiqueta, Modal } from "@/components/ui";

/**
 * Marcar de uma vez as categorias que JÁ EXISTEM no cardápio do PDV.
 *
 * 🔑 **Pedido do dono (09/09/2026).** O produto carrega o grupo pelo
 * `codGrupoExterno`, e o PDV só o resolve se a categoria daqui tiver sido
 * adotada lá. Sem nenhuma categoria marcada, **todo** produto marcado aparece
 * como "atualizar" e trava: na conta real eram 636 produtos parados por 30
 * categorias que ninguém tinha marcado.
 *
 * Marcar uma a uma são trinta idas ao cadastro para responder sempre a mesma
 * pergunta — e ela tem resposta certa, que só o PDV sabe dar: *esta categoria
 * existe no cardápio?*
 *
 * ⚠️ **Prévia antes, sempre.** Mesma regra da fusão, da colheita de EAN e da
 * alteração múltipla: quem vai marcar trinta cadastros de uma vez não confere
 * um a um depois.
 *
 * ⚠️ **Aparece TAMBÉM com o envio desligado.** É o passo de preparar — marcar
 * não manda nada para lugar nenhum —, e exigir o interruptor ligado obrigaria a
 * ligá-lo antes de a fila estar sã, que é o que se está tentando evitar.
 */

type Linha = { id: number; nome: string; motivo?: string };

type Resposta = {
  marcam: Linha[];
  ja_marcadas: Linha[];
  sem_par: Linha[];
  aplicado: boolean;
  message: string;
};

export default function MarcarCategorias({ aoAplicar }: { aoAplicar?: () => void }) {
  const aviso = useAviso();
  const [previa, setPrevia] = useState<Resposta | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  async function conferir() {
    setOcupado(true);
    setErro("");
    try {
      setPrevia(await api.post<Resposta>("/pdv/envio/marcar-categorias", {}));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível ler o cardápio");
    } finally {
      setOcupado(false);
    }
  }

  async function aplicar() {
    setOcupado(true);
    try {
      const r = await api.post<Resposta>("/pdv/envio/marcar-categorias", { simular: false });
      aviso.sucesso(r.message);
      setPrevia(null);
      aoAplicar?.();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível marcar");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <>
      <button
        type="button"
        className="btn btn-secundario"
        disabled={ocupado}
        onClick={() => void conferir()}
        title="Pergunta ao PDV quais categorias já existem no cardápio"
      >
        {ocupado && !previa ? "Lendo o cardápio…" : "Conferir categorias do cardápio"}
      </button>

      {previa && (
        <Modal
          titulo="Categorias que já existem no cardápio do PDV"
          descricao="Marcar não envia nada — é o passo que destrava os produtos na fila."
          aoFechar={() => setPrevia(null)}
          rodape={
            <div className="flex flex-wrap items-center justify-between gap-3">
              <span className="text-[13px] text-suave">{previa.message}</span>
              <div className="flex gap-2">
                <button type="button" className="btn btn-secundario"
                        onClick={() => setPrevia(null)}>
                  Cancelar
                </button>
                <button
                  type="button"
                  className="btn btn-primario"
                  disabled={ocupado || !previa.marcam.length}
                  onClick={() => void aplicar()}
                >
                  {ocupado ? "Marcando…" : `Marcar ${previa.marcam.length}`}
                </button>
              </div>
            </div>
          }
        >
          {erro && <Aviso tipo="erro">{erro}</Aviso>}

          {/* ⚠️ **O que vem DEPOIS precisa estar dito aqui.** Marcar não basta:
              o produto só resolve o grupo quando o vínculo estiver gravado LÁ, e
              isso acontece no envio. Sem esta frase, quem marcar volta para a
              fila, vê os mesmos números e conclui que não funcionou. */}
          <Aviso tipo="info">
            Depois de marcar, as categorias entram na fila como <b>adotar</b> (existem lá e
            ninguém as reivindicou), <b>atualizar</b> (já são suas) ou <b>criar</b>. Só o
            envio grava o vínculo no PDV — e é ele que destrava os produtos.
          </Aviso>

          {!!previa.marcam.length && (
            <div className="mt-4">
              <p className="mb-2 text-[13px] text-suave">
                {previa.marcam.length} categoria(s) serão marcadas:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {previa.marcam.map((c) => (
                  <Etiqueta key={c.id} cor="erva">{c.nome}</Etiqueta>
                ))}
              </div>
            </div>
          )}

          {!!previa.ja_marcadas.length && (
            <p className="mt-4 text-[13px] text-suave">
              <b>{previa.ja_marcadas.length}</b> já estava(m) marcada(s) e não contam como
              alteração.
            </p>
          )}

          {/* 🔑 **As de fora aparecem NOMEADAS, com o motivo.** São as categorias
              de COMPRA — vindas das famílias do Omie, como HORTIFRÚTI e LIMPEZA —
              e não têm o que fazer num cardápio. Sem dizer por que ficaram de
              fora, alguém as marcaria à mão desfazendo o cuidado. */}
          {!!previa.sem_par.length && (
            <div className="mt-4">
              <p className="mb-2 text-[13px] text-suave">
                {previa.sem_par.length} ficam de fora — não existem como grupo no cardápio:
              </p>
              <div className="flex flex-wrap gap-1.5">
                {previa.sem_par.map((c) => (
                  <Etiqueta key={c.id}>{c.nome}</Etiqueta>
                ))}
              </div>
            </div>
          )}
        </Modal>
      )}
    </>
  );
}
