"use client";

/**
 * Excluir um catálogo — o rascunho, ou o que já esteve no ar e hoje está INATIVO.
 *
 * 🔑 Pedido do dono (20/10/2026): *"um botão para poder excluir cardápios"* — o "Catering" de
 * teste só saía por SQL. A janela mostra o que vai junto (a prévia do servidor) e, no inativo,
 * pede o NOME digitado: é o que a casa publicou, e o clique distraído não pode levar.
 * ⚠️ O catálogo no ar não abre esta janela: primeiro sai do ar.
 */

import { useEffect, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Modal } from "@/components/ui";
import * as cat from "@/lib/catalogos";

export default function JanelaExcluirCatalogo({ capa, aoFechar, aoExcluir }: {
  capa: cat.Catalogo; aoFechar: () => void; aoExcluir: () => void;
}) {
  const aviso = useAviso();
  const [pv, setPv] = useState<cat.PreviaExclusao | null>(null);
  const [nome, setNome] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    cat.previaExclusao(capa.id).then(setPv).catch((e) => {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível conferir o que sai junto.");
      aoFechar();
    });
    // ⚠️ Só pelo catálogo: `aoFechar` nasce a cada desenho do pai e pediria a prévia de novo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capa.id]);

  async function excluir() {
    setOcupado(true);
    try {
      const r = await cat.excluir(capa.id, pv?.pede_nome ? nome : undefined);
      aviso.sucesso(r.message);
      aoExcluir();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível excluir.");
    } finally {
      setOcupado(false);
    }
  }

  const confere = !pv?.pede_nome || nome.trim().toLocaleLowerCase("pt-BR") === capa.nome.trim().toLocaleLowerCase("pt-BR");
  const linha = (n: number, um: string, varios: string) => (n ? <li>{n} {n === 1 ? um : varios}</li> : null);
  return (
    <Modal titulo={`Excluir “${capa.nome}”?`} aoFechar={aoFechar} largura="520px">
      {!pv ? <p className="text-[14px] text-suave">Conferindo o que vai junto…</p> : (
        <div className="flex flex-col gap-3 text-[14.5px] leading-snug" id="excluir-catalogo">
          {pv.situacao === "RASCUNHO"
            ? <p>Ele ainda é rascunho, então nunca esteve no ar.</p>
            : <p>Ele <b>já esteve no ar</b>. Excluir tira do sistema o que a casa publicou — inativo, ele continua guardado.</p>}
          <div>
            <p className="text-suave">Vai junto:</p>
            <ul className="ml-5 list-disc">
              {linha(pv.secoes, "seção", "seções")}
              {linha(pv.pratos, "prato vinculado (os produtos continuam cadastrados)", "pratos vinculados (os produtos continuam cadastrados)")}
              {linha(pv.cartoes, "cartão do Cardápio Vivo", "cartões do Cardápio Vivo")}
              {pv.cardapio_vivo && <li>o Cardápio Vivo dele (o link deixa de abrir)</li>}
              {linha(pv.testes, "teste A/B", "testes A/B")}
              {linha(pv.eventos, "evento de medição", "eventos de medição")}
              <li>as fotos e os vídeos das seções e dos cartões</li>
            </ul>
          </div>
          {(pv.pedidos > 0 || pv.anuncios > 0) && (
            <p className="text-[13.5px] text-suave">
              Ficam, sem o catálogo: {pv.pedidos ? `${pv.pedidos} pedido(s) que o citam` : ""}
              {pv.pedidos && pv.anuncios ? " e " : ""}{pv.anuncios ? `${pv.anuncios} anúncio(s) que o abrem (aparecem sem botão)` : ""}.
            </p>
          )}
          {pv.pede_nome && (
            <label className="flex flex-col gap-1">
              <span className="text-[13.5px]">Para confirmar, digite o nome do catálogo: <b>{capa.nome}</b></span>
              <input id="excluir-catalogo-nome" className="campo" value={nome} autoFocus
                     onChange={(e) => setNome(e.target.value)} />
            </label>
          )}
          <p className="text-[13.5px] font-semibold text-erro">Isto não se desfaz.</p>
        </div>
      )}
      <div className="mt-5 flex flex-wrap justify-end gap-2">
        <button type="button" className="btn btn-secundario" onClick={aoFechar}>Cancelar</button>
        <button type="button" id="excluir-catalogo-confirmar" className="btn btn-primario"
                style={{ background: "var(--color-erro)" }} aria-busy={ocupado}
                disabled={!pv || !pv.pode || !confere || ocupado} onClick={() => void excluir()}>
          Excluir
        </button>
      </div>
    </Modal>
  );
}
