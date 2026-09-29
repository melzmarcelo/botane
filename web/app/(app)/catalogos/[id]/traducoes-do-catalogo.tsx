"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import Traducoes from "@/components/traducoes";
import { Cartao, Etiqueta, Modal } from "@/components/ui";
import { useSessao } from "@/lib/sessao";
import { pendentesDoCatalogo, traduzirCatalogo, type TipoTraduzivel } from "@/lib/traducao";

/**
 * O cardápio em inglês e alemão, visto do catálogo.
 *
 * 🔑 Pedido do dono (decidido em 29/09/2026). O Claude traduz cada coisa ao salvar; este
 * cartão mostra quantas ainda estão sem tradução (ou com o português mudado) e traduz todas
 * de uma vez — é o caminho para o cardápio que já existia antes da tradução.
 */
export function TraducoesDoCatalogo({ idCatalogo, podeEditar }: { idCatalogo: number; podeEditar: boolean }) {
  const aviso = useAviso();
  const { pode } = useSessao();
  const [estado, setEstado] = useState<{ pendentes: number; ligada: boolean } | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [versao, setVersao] = useState(0);

  const carregar = useCallback(() => {
    pendentesDoCatalogo(idCatalogo).then(setEstado).catch(() => setEstado(null));
  }, [idCatalogo]);
  useEffect(() => carregar(), [carregar]);

  async function traduzir() {
    setOcupado(true);
    try {
      const r = await traduzirCatalogo(idCatalogo);
      aviso.sucesso(r.message);
      setVersao((v) => v + 1);
      carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível traduzir agora");
    } finally {
      setOcupado(false);
    }
  }

  if (!estado) return null;
  return (
    <Cartao
      titulo="Inglês e alemão"
      descricao="O site deixa o cliente escolher PT · EN · DE. O Claude traduz ao salvar; onde faltar tradução, o site mostra o português."
      acao={estado.pendentes
        ? <Etiqueta cor="alerta">{estado.pendentes} sem tradução</Etiqueta>
        : <Etiqueta cor="erva">tudo traduzido</Etiqueta>}
    >
      <div className="flex flex-col gap-3">
        {!estado.ligada && (
          <p className="text-[13px] text-suave">
            A tradução automática está <b>desligada</b>: falta cadastrar a chave da Anthropic em{" "}
            {pode("admin.integracoes")
              ? <Link className="link" href="/integracoes?aba=traducao">Integrações ▸ Tradução</Link>
              : <b>Integrações ▸ Tradução</b>}. Dá para traduzir à mão em cada produto e seção.
          </p>
        )}
        {podeEditar && estado.ligada && estado.pendentes > 0 && (
          <div>
            <button type="button" className="btn btn-primario" disabled={ocupado} aria-busy={ocupado}
                    onClick={() => void traduzir()}>
              {ocupado ? "Traduzindo…" : `Traduzir o que falta (${estado.pendentes})`}
            </button>
          </div>
        )}
        <Traducoes key={`catalogo-${versao}`} tipo="catalogo" id={idCatalogo} aoMudar={carregar} />
      </div>
    </Cartao>
  );
}

/** A janela das traduções de uma categoria ou subcategoria. */
export function JanelaDeTraducao({ tipo, id, nome, aoFechar }: {
  tipo: TipoTraduzivel; id: number; nome: string; aoFechar: () => void;
}) {
  return (
    <Modal titulo={`Traduções — ${nome}`} descricao="Como o cliente lê esta seção no site em inglês e em alemão."
           aoFechar={aoFechar} largura="720px">
      <Traducoes tipo={tipo} id={id} />
    </Modal>
  );
}
