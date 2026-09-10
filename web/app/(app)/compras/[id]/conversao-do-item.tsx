"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Modal } from "@/components/ui";
import { qtd, textoParaNumero } from "@/lib/numeros";

/**
 * A conversão do item, resolvida DENTRO da nota.
 *
 * 🔑 **Pedido do dono (10/09/2026).** A unidade de estoque é UN, o cadastro tem
 * CX/12, e chega uma nota em FD/6. Até aqui era preciso sair da conferência,
 * abrir o produto, acrescentar a unidade e voltar — e quem estava conferindo
 * trinta linhas simplesmente não ia.
 *
 * 🔑 **E o caso pior: CX/24 contra o CX/12 do cadastro.** Aí não há o que
 * acrescentar, há o que DECIDIR, e o sistema não pode decidir sozinho:
 *
 * - **o fornecedor mudou de embalagem** → corrigir o 12 para 24, e vale para
 *   todas as compras seguintes;
 * - **ele manda as duas caixas** → CX é ambíguo para este produto, e a resposta
 *   não é mexer no fator: é o de-para pelo CÓDIGO do fornecedor, que ganha do
 *   fator de embalagem na cascata de `_fator_do_item`.
 *
 * ⚠️ **Por isso esta janela PERGUNTA em vez de sobrescrever.** Sobrescrever
 * seria o sistema apostar em qual dos dois casos é — e errar em silêncio, que é
 * exatamente o defeito que ela existe para fechar.
 *
 * ⚠️ **Mexer no fator mexe em quanto ENTRA no estoque.** Corrigir o cadastro
 * não reescreve nota já lançada: o razão é append-only, e as compras antigas
 * seguem com o número antigo. A janela diz isso antes do botão.
 */

type Unidade = { um: string; fator: number; padrao: boolean; observacao: string | null };

export default function ConversaoDoItem({
  idProduto,
  produto,
  umEstoque,
  umNota,
  fatorCadastro,
  fatorDeclarado,
  podeEditar,
  aoFechar,
  aoSalvar,
}: {
  idProduto: number;
  produto: string;
  umEstoque: string | null;
  umNota: string | null;
  /** O fator que o lançamento usaria hoje — vem do servidor, da mesma cascata. */
  fatorCadastro: number | null;
  /** O que a NOTA declarou (`qTrib/qCom`). Nulo quando ela não disse. */
  fatorDeclarado: number | null;
  podeEditar: boolean;
  aoFechar: () => void;
  aoSalvar: () => void;
}) {
  const aviso = useAviso();
  const [unidades, setUnidades] = useState<Unidade[] | null>(null);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const sigla = (umNota ?? "").trim().toUpperCase();

  const carregar = useCallback(async () => {
    try {
      setUnidades(await api.get<Unidade[]>(`/produtos/${idProduto}/unidades`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [idProduto]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const jaExiste = (unidades ?? []).find((u) => u.um.toUpperCase() === sigla);
  const diverge =
    fatorDeclarado !== null &&
    fatorCadastro !== null &&
    Math.abs(fatorDeclarado - fatorCadastro) > fatorCadastro * 0.005;

  // O campo nasce com o que a NOTA declarou, quando ela declarou — é o número
  // que a pessoa veio conferir, e redigitá-lo seria pedir para errar.
  const [fator, setFator] = useState("");
  useEffect(() => {
    if (fatorDeclarado) setFator(String(fatorDeclarado).replace(".", ","));
    else if (jaExiste) setFator(String(jaExiste.fator).replace(".", ","));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fatorDeclarado, jaExiste?.fator]);

  async function gravar(substituir: boolean) {
    const valor = textoParaNumero(fator);
    if (!valor || valor <= 0) {
      aviso.erro("O fator tem de ser maior que zero.");
      return;
    }
    setSalvando(true);
    try {
      // ⚠️ O PUT substitui a tabela INTEIRA — então manda-se a lista completa,
      // com a linha nova ou corrigida no meio. Mandar só a que mudou apagaria
      // as outras, e o palete de 480 sumiria porque alguém mexeu no fardo.
      const outras = (unidades ?? []).filter((u) => u.um.toUpperCase() !== sigla);
      const itens = substituir || !jaExiste
        ? [...outras, { um: sigla, fator: valor, padrao: jaExiste?.padrao ?? false,
                        observacao: jaExiste?.observacao ?? null }]
        : (unidades ?? []);
      await api.put(`/produtos/${idProduto}/unidades`, { itens });
      aviso.sucesso(
        jaExiste
          ? `${sigla} passa a valer ${qtd(valor)} ${umEstoque ?? ""} neste produto.`
          : `${sigla} entrou na conversão: ${qtd(valor)} ${umEstoque ?? ""}.`,
      );
      aoSalvar();
      aoFechar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Modal
      titulo="Conversão deste item"
      descricao={`${produto} — a nota veio em ${sigla || "?"} e o estoque é ${umEstoque ?? "?"}`}
      aoFechar={aoFechar}
      largura="620px"
    >
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {/* A conferência primeiro: é por causa dela que a janela foi aberta. */}
      {diverge && (
        <Aviso tipo="erro">
          <b>A nota discorda do cadastro.</b> Ela declara que{" "}
          <b>1 {sigla} = {qtd(fatorDeclarado)} {umEstoque}</b>, e o cadastro diz{" "}
          <b>{qtd(fatorCadastro)}</b>. Do jeito que está, o lançamento vai usar o do
          cadastro — e a diferença entra no estoque e no custo sem aparecer.
        </Aviso>
      )}
      {!diverge && fatorDeclarado !== null && (
        <Aviso tipo="ok">
          A nota declara <b>1 {sigla} = {qtd(fatorDeclarado)} {umEstoque}</b>, e o cadastro
          concorda.
        </Aviso>
      )}
      {fatorDeclarado === null && (
        <Aviso tipo="info">
          Esta nota não declarou conversão — ou é digitada, ou o XML veio com a unidade
          tributável igual à comercial. O número abaixo é o do cadastro.
        </Aviso>
      )}

      <div className="mt-4">
        <p className="rotulo">Como está hoje</p>
        {unidades === null ? (
          <p className="mt-1 text-suave">carregando…</p>
        ) : unidades.length === 0 ? (
          <p className="mt-1 text-[14px] text-suave">
            Nenhuma unidade de conversão cadastrada — só a de estoque ({umEstoque ?? "?"}).
          </p>
        ) : (
          <ul className="mt-1 flex flex-wrap gap-2">
            {unidades.map((u) => (
              <li
                key={u.um}
                className={`rounded border px-2 py-1 text-[13.5px] ${
                  u.um.toUpperCase() === sigla
                    ? "border-alerta bg-alerta-claro"
                    : "border-linha2 text-suave"
                }`}
              >
                1 {u.um} = {qtd(u.fator)} {umEstoque}
                {u.padrao && " · padrão"}
              </li>
            ))}
          </ul>
        )}
      </div>

      {podeEditar && (
        <div className="mt-5 border-t border-linha pt-4">
          <Campo
            rotulo={`Quantos ${umEstoque ?? "?"} vêm em 1 ${sigla || "?"}`}
            className="w-[240px]"
          >
            <input
              className="campo mono text-right"
              inputMode="decimal"
              value={fator}
              onChange={(e) => setFator(e.target.value.replace(/[^\d.,]/g, ""))}
            />
          </Campo>

          {/* 🔑 **A pergunta, e é ela que faz esta janela existir.** Com a
              unidade JÁ cadastrada e um número diferente, os dois caminhos são
              legítimos e só quem conferiu a mercadoria sabe qual é. */}
          {jaExiste ? (
            <div className="mt-4 flex flex-col gap-3">
              <p className="text-[14px] leading-snug">
                O cadastro já tem <b>{sigla}</b> valendo <b>{qtd(jaExiste.fator)}</b>. O que
                aconteceu?
              </p>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn btn-primario"
                  disabled={salvando}
                  onClick={() => void gravar(true)}
                >
                  O fornecedor mudou de embalagem — corrigir para {fator || "…"}
                </button>
                <button
                  type="button"
                  className="btn btn-secundario"
                  disabled={salvando}
                  onClick={aoFechar}
                >
                  Ele manda as duas — não mexer
                </button>
              </div>
              <p className="text-[13px] leading-snug text-suave">
                <b>Corrigir</b> vale para todas as compras seguintes e{" "}
                <b>não reescreve nota já lançada</b> — o razão não se reescreve, e o que já
                entrou fica como entrou. <b>Não mexer</b> é a resposta certa quando o mesmo{" "}
                {sigla} chega em dois tamanhos: aí o caminho é vincular o item pelo{" "}
                <b>código do fornecedor</b>, que vale mais que o fator da embalagem.
              </p>
            </div>
          ) : (
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <button
                type="button"
                className="btn btn-primario"
                disabled={salvando || !fator}
                onClick={() => void gravar(false)}
              >
                {salvando ? "Gravando…" : `Acrescentar ${sigla} ao produto`}
              </button>
              <span className="text-[13px] text-suave">
                Vale da próxima nota em diante; esta você confere agora.
              </span>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}
