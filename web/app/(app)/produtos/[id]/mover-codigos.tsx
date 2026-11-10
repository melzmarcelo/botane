"use client";

import { useEffect, useMemo, useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Etiqueta, Modal } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";
import { concorda, qtd, textoParaNumero } from "@/lib/numeros";
import { dataCurta } from "@/lib/datas";
import {
  moverCodigos,
  previaDaMudanca,
  type CodigoMovivel,
  type PreviaDaMudanca,
} from "@/lib/produto-codigos";

/**
 * Mover os códigos de um produto para outro.
 *
 * 🔑 **Pedido do dono (10/11/2026), o caso CATCHUP × KETCHUP.** Os dois eram o
 * mesmo produto e a fusão recusou: os DOIS tinham movimento no razão. O saldo se
 * passa à mão (saída num, entrada no outro), mas os códigos ficavam presos no
 * cadastro velho, e a próxima nota caía em "produto inativo". Aqui eles mudam de
 * dono — é a parte da fusão que não depende de história.
 *
 * ⚠️ **A conversão é obrigatória no código do Omie e no do fornecedor.** São eles
 * que decidem a quantidade da nota. O CATCHUP compra em bag de 2 kg e o KETCHUP
 * em galão de 3,8 kg: movido sem fator, 1 bag entraria como 3,8 kg. A sugestão é
 * o que a última nota lançada fez, e só aparece com a mesma unidade de estoque.
 *
 * ⚠️ **A prévia vem antes do botão**, como na fusão e no desvincular.
 */

const SISTEMA: Record<string, string> = {
  OMIE: "código na nota do fornecedor",
  OMIE_PRODUTO: "código do produto no Omie",
  PDV_LEGAL: "código no cardápio do PDV",
  EAN: "código de barras",
};

const ONDE: Record<string, string> = {
  principal: "principal do cadastro",
  vinculado: "vinculado",
  fornecedor: "código no fornecedor",
};

const chave = (c: CodigoMovivel) => `${c.sistema}|${c.codigo}|${c.id_fornecedor ?? 0}`;

export default function MoverCodigos({
  idOrigem,
  destino: destinoFixo = null,
  aoFechar,
  aoMover,
}: {
  idOrigem: number;
  /** Já escolhido por quem abriu (a fusão travada); sem ele, a janela pergunta. */
  destino?: { id: number; rotulo: string } | null;
  aoFechar: () => void;
  aoMover: () => void;
}) {
  const aviso = useAviso();
  // A busca não lista a própria origem: mover para si mesmo não existe.
  const PRODUTOS = useMemo(() => fonteProdutos(`excluir_id=${idOrigem}`), [idOrigem]);
  const [destino, setDestino] = useState(destinoFixo);
  const [previa, setPrevia] = useState<PreviaDaMudanca | null>(null);
  const [marcados, setMarcados] = useState<Record<string, boolean>>({});
  const [fatores, setFatores] = useState<Record<string, string>>({});
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    if (!destino) {
      setPrevia(null);
      return;
    }
    let vivo = true;
    setErro("");
    previaDaMudanca(idOrigem, destino.id)
      .then((p) => {
        if (!vivo) return;
        setPrevia(p);
        // Tudo que pode ir nasce marcado: o caso comum é "os dois são o mesmo".
        setMarcados(Object.fromEntries(p.codigos.map((c) => [chave(c), !c.bloqueio])));
        setFatores(
          Object.fromEntries(
            p.codigos.map((c) => [
              chave(c),
              c.fator_sugerido != null ? String(c.fator_sugerido).replace(".", ",") : "",
            ]),
          ),
        );
      })
      .catch((e) => {
        if (!vivo) return;
        setPrevia(null);
        setErro(e instanceof Error ? e.message : "Não foi possível conferir");
      });
    return () => {
      vivo = false;
    };
  }, [idOrigem, destino]);

  const escolhidos = (previa?.codigos ?? []).filter((c) => marcados[chave(c)] && !c.bloqueio);
  const semFator = escolhidos.filter(
    (c) => c.pede_fator && !((textoParaNumero(fatores[chave(c)] ?? "") ?? 0) > 0),
  );
  const pode = !!previa?.pode && !!escolhidos.length && !semFator.length;
  const umDestino = previa?.destino.um_estoque || "?";

  async function mover() {
    if (!previa || !destino) return;
    setOcupado(true);
    try {
      const r = await moverCodigos(
        idOrigem,
        destino.id,
        escolhidos.map((c) => ({
          sistema: c.sistema,
          codigo: c.codigo,
          id_fornecedor: c.id_fornecedor,
          fator: c.pede_fator ? textoParaNumero(fatores[chave(c)] ?? "") : null,
        })),
      );
      aviso.sucesso(r.message);
      aoMover();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível mover os códigos");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Modal
      titulo="Mover códigos para outro produto"
      descricao={
        "Os códigos marcados passam a cair no produto de destino: a próxima nota (ou venda) "
        + "com eles entra lá. O que já entrou no estoque continua onde está."
      }
      aoFechar={aoFechar}
      rodape={
        <div className="flex flex-wrap items-center gap-2">
          <button
            className="btn btn-primario"
            type="button"
            aria-busy={ocupado}
            disabled={ocupado || !pode}
            onClick={() => void mover()}
          >
            {ocupado
              ? "Movendo…"
              : `Mover ${escolhidos.length} ${concorda(escolhidos.length, "código", "códigos")}`}
          </button>
          <button className="btn btn-secundario" type="button" onClick={aoFechar}>
            Cancelar
          </button>
        </div>
      }
    >
      <>
        {destinoFixo ? (
          <p className="text-[14px]">
            Para <b>{destinoFixo.rotulo}</b>
          </p>
        ) : (
          <Campo rotulo="Produto de destino" dica="código ou nome — só produtos ativos">
            <BuscaCadastro
              fonte={PRODUTOS}
              selecionado={destino}
              aoEscolher={(i: ItemBusca | null) =>
                setDestino(i ? { id: i.id, rotulo: rotuloDe(i) } : null)
              }
            />
          </Campo>
        )}

        {erro && (
          <div className="mt-4">
            <Aviso tipo="erro">{erro}</Aviso>
          </div>
        )}

        {previa && (
          <div className="mt-4 flex flex-col gap-3">
            {previa.impedimentos.length > 0 && (
              <Aviso tipo="erro">Não dá para mover: {previa.impedimentos.join("; ")}.</Aviso>
            )}

            <p className="text-[13.5px]">
              De <b>{previa.origem.nome}</b> ({previa.origem.um_estoque || "sem unidade"}) para{" "}
              <b>{previa.destino.nome}</b> ({previa.destino.um_estoque || "sem unidade"})
              {!previa.origem.ativo && <> · a origem está inativa</>}
            </p>

            {!previa.mesma_unidade && previa.codigos.some((c) => c.pede_fator) && (
              <Aviso tipo="info">
                Os dois produtos têm <b>unidades de estoque diferentes</b>. Não há sugestão de
                conversão: diga quantos {umDestino} do destino vêm em 1 unidade de cada código.
              </Aviso>
            )}

            {!previa.codigos.length ? (
              <Aviso tipo="info">Este produto não tem código nenhum para mover.</Aviso>
            ) : (
              <div className="grid-rolante">
                <table className="tabela" id="codigos-a-mover">
                  <thead>
                    <tr>
                      <th />
                      <th>Código</th>
                      <th>De onde</th>
                      <th className="num">1 unidade = {umDestino}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previa.codigos.map((c) => {
                      const k = chave(c);
                      return (
                        <tr key={k}>
                          <td>
                            <input
                              type="checkbox"
                              className="h-4 w-4 accent-erva"
                              aria-label={`mover ${c.codigo}`}
                              disabled={!!c.bloqueio}
                              checked={!!marcados[k] && !c.bloqueio}
                              onChange={(e) => setMarcados({ ...marcados, [k]: e.target.checked })}
                            />
                          </td>
                          <td className="whitespace-nowrap">
                            <span className="mono">{c.codigo}</span>
                            <span className="block text-[12px] text-suave">
                              {SISTEMA[c.sistema] ?? c.sistema}
                            </span>
                          </td>
                          <td className="text-[13px]">
                            <Etiqueta cor={c.onde === "principal" ? "erva" : "neutro"}>
                              {ONDE[c.onde] ?? c.onde}
                            </Etiqueta>
                            {c.fornecedor && (
                              <span className="block text-[12px] text-suave">{c.fornecedor}</span>
                            )}
                            {c.descricao && c.descricao !== previa.origem.nome && (
                              <span className="block text-[12px] text-suave">{c.descricao}</span>
                            )}
                            {c.bloqueio && (
                              <span className="block text-[12px] text-alerta">{c.bloqueio}</span>
                            )}
                          </td>
                          <td className="num">
                            {c.pede_fator ? (
                              <>
                                <input
                                  className="campo mono max-w-[110px] text-right"
                                  aria-label={`conversão de ${c.codigo}`}
                                  inputMode="decimal"
                                  disabled={!marcados[k] || !!c.bloqueio}
                                  value={fatores[k] ?? ""}
                                  onChange={(e) => setFatores({ ...fatores, [k]: e.target.value })}
                                />
                                {c.ultima_nota && (
                                  <span className="mt-1 block text-[11.5px] text-suave">
                                    última nota
                                    {c.ultima_nota.data ? ` (${dataCurta(c.ultima_nota.data)})` : ""}
                                    : 1 {c.ultima_nota.um_nota || "un"} ={" "}
                                    {qtd(c.ultima_nota.fator)} {previa.origem.um_estoque || ""}
                                  </span>
                                )}
                              </>
                            ) : (
                              <span className="text-[12px] text-suave">não muda quantidade</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {semFator.length > 0 && (
              <p className="text-[13px] text-alerta">
                Falta a conversão de {semFator.map((c) => c.codigo).join(", ")}: sem ela a nota
                entraria com a quantidade errada.
              </p>
            )}

            <p className="text-[12.5px] leading-snug text-suave">
              O saldo não muda de produto: isso é uma saída num e uma entrada no outro. O cadastro
              de origem continua existindo; desative-o se ele não for mais usado.
              {previa.itens_de_nota_abertos > 0 && (
                <>
                  {" "}
                  Itens de nota ainda não lançada com estes códigos mudam junto, e a nota é
                  recalculada.
                </>
              )}
            </p>
          </div>
        )}
      </>
    </Modal>
  );
}
