"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import {
  desvincularCodigo,
  previaDoDesvinculo,
  type PreviaDoDesvinculo,
} from "@/lib/produto-codigos";

/**
 * Os códigos de fora que caem neste produto — e quanto cada um vale.
 *
 * 🔑 **O caso do AÇÚCAR DE CONFEITEIRO** (pedido do dono, 04/09/2026). O
 * fornecedor manda o pacote de 1 kg e o de 500 g como produtos DIFERENTES, com
 * códigos diferentes — e aqui os dois são o mesmo produto. Feita a fusão, o
 * código do de 500 g vira apelido do sobrevivente, e a nota dele passava a
 * entrar como **1 kg por unidade**: o estoque dobrava sem nada denunciando, e a
 * diferença só apareceria na primeira contagem como "ajuste de inventário".
 *
 * 🔑 **A conversão por código já era o primeiro degrau da cascata** — ganha da
 * unidade da nota, do fornecedor e do fator de compra do produto. O que faltava
 * era alguém poder informá-la: a API aceitava o fator desde sempre e nenhuma
 * tela o oferecia.
 *
 * ⚠️ **Vale da próxima nota em diante.** Nota já lançada não se recalcula — o
 * razão é append-only, e a entrada antiga ficou com a quantidade que se
 * acreditava na época. Corrigir o passado é estorno, à mão.
 *
 * 🔑 **Cada linha se DESVINCULA** (06/10/2026, pedido do dono: *"na linha do
 * produto vinculado ter a opção de desvincular"*). Vínculo errado ficava para
 * sempre: toda nota com aquele código seguia entrando no produto errado.
 * ⚠️ **A prévia vem antes**, e diz o que o servidor achou: se o código veio de
 * uma fusão e o cadastro absorvido ainda existe, oferece devolver o código a
 * ele e reativá-lo — marcado por padrão, porque é o que "desvincular um produto"
 * quer dizer. Sem isso, a linha só sai, e a próxima nota pede conciliação.
 * ⚠️ **Não desfaz o que já aconteceu**: o que entrou no estoque por aquele
 * código fica onde está, e a janela diz isso antes do botão.
 */

export type CodigoExterno = {
  sistema: string;
  codigo: string;
  descricao_externa: string | null;
  fator: number | string;
  fator_confirmado: boolean;
  origem_vinculo: string | null;
  fornecedor: string | null;
  /** Parte da identidade da linha: o mesmo código pode existir por fornecedor. */
  id_fornecedor?: number | null;
};

const ORIGEM: Record<string, string> = {
  MANUAL: "vinculado à mão",
  FUSAO: "veio de uma fusão",
  AUTOMATICO: "reconhecido sozinho",
};

export default function CodigosDoProduto({
  idProduto,
  codigos,
  umEstoque,
  podeEditar,
  aoMudar,
}: {
  idProduto: number;
  codigos: CodigoExterno[];
  umEstoque: string | null;
  podeEditar: boolean;
  aoMudar: () => void;
}) {
  const aviso = useAviso();
  const [rascunho, setRascunho] = useState<Record<string, string>>({});
  const [salvando, setSalvando] = useState("");
  // O desvínculo em andamento: a linha, o que o servidor disse que faria e a
  // escolha de devolver o código ao cadastro absorvido.
  const [soltando, setSoltando] = useState<{ c: CodigoExterno; previa: PreviaDoDesvinculo } | null>(
    null,
  );
  const [devolver, setDevolver] = useState(true);
  const [ocupado, setOcupado] = useState("");

  async function pedirDesvinculo(c: CodigoExterno) {
    setOcupado(`${c.sistema}|${c.codigo}`);
    try {
      const previa = await previaDoDesvinculo(idProduto, c);
      setDevolver(true);
      setSoltando({ c, previa });
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível conferir o vínculo");
    } finally {
      setOcupado("");
    }
  }

  async function desvincular() {
    if (!soltando) return;
    const { c, previa } = soltando;
    setOcupado(`${c.sistema}|${c.codigo}`);
    try {
      const r = await desvincularCodigo(idProduto, c, devolver && !!previa.devolve_para);
      aviso.sucesso(r.message);
      setSoltando(null);
      aoMudar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível desvincular");
    } finally {
      setOcupado("");
    }
  }

  const chave = (c: CodigoExterno) => `${c.sistema}|${c.codigo}`;

  async function gravar(c: CodigoExterno) {
    const k = chave(c);
    const valor = Number((rascunho[k] ?? "").replace(",", "."));
    if (!(valor > 0)) {
      // ⚠️ Zero faria a nota inteira entrar como nada, e é erro de digitação
      // plausível — a vírgula no lugar errado.
      aviso.erro("A conversão precisa ser maior que zero.");
      return;
    }
    setSalvando(k);
    try {
      const r = await api.put<{ message: string }>(`/produtos/${idProduto}/codigos/conversao`, {
        sistema: c.sistema,
        codigo: c.codigo,
        fator: valor,
      });
      aviso.sucesso(r.message);
      // ⚠️ **APAGAR a chave, não pôr string vazia.** O campo lê
      // `rascunho[k] ?? String(atual)`, e `""` NÃO é `undefined`: o `??` não
      // caía no valor do servidor e o campo ficava em branco depois de gravar,
      // até alguém recarregar a página. O número estava salvo — só não aparecia.
      setRascunho((r0) => {
        const resto = { ...r0 };
        delete resto[k];
        return resto;
      });
      aoMudar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar a conversão");
    } finally {
      setSalvando("");
    }
  }

  if (!codigos.length) {
    return (
      <Vazio>
        Nenhum código de fora aponta para este produto ainda. Eles nascem quando uma nota é
        vinculada à mão ou quando dois cadastros são fundidos.
      </Vazio>
    );
  }

  return (
    <>
      <Aviso tipo="info">
        Um fornecedor pode mandar o mesmo produto em embalagens diferentes, cada uma com o seu
        código. Diga aqui <b>quanto vale uma unidade de cada código</b> — o pacote de 500 g de um
        insumo medido em KG vale <b>0,5</b>. <b>Por padrão é 1.</b> Vale da próxima nota em
        diante: o que já foi lançado não se recalcula.
      </Aviso>

      <div className="mt-3 grid-rolante">
        <table className="tabela">
          <thead>
            <tr>
              <th>Código</th>
              <th>O que é lá</th>
              <th>De onde veio</th>
              <th className="num">1 unidade = {umEstoque || "?"}</th>
              {podeEditar && <th />}
            </tr>
          </thead>
          <tbody>
            {codigos.map((c) => {
              const k = chave(c);
              const atual = Number(c.fator);
              return (
                <tr key={k}>
                  <td className="mono whitespace-nowrap">
                    {c.codigo}
                    <span className="block text-[12px] text-suave">{c.sistema}</span>
                  </td>
                  <td>
                    {c.descricao_externa ?? "—"}
                    {c.fornecedor && (
                      <span className="block text-[12.5px] text-suave">{c.fornecedor}</span>
                    )}
                  </td>
                  <td className="text-[13px] text-suave">
                    {ORIGEM[c.origem_vinculo ?? ""] ?? c.origem_vinculo ?? "—"}
                  </td>
                  <td className="num">
                    {podeEditar ? (
                      <input
                        className="campo mono max-w-[110px] text-right"
                        aria-label={`conversão de ${c.codigo}`}
                        value={rascunho[k] ?? String(atual)}
                        onChange={(e) => setRascunho({ ...rascunho, [k]: e.target.value })}
                      />
                    ) : (
                      <span className="mono">{atual}</span>
                    )}
                    {/* ⚠️ **A marca distingue o 1 DIGITADO do 1 automático.** A
                        coluna nasce com 1 e a cascata ignora esse 1 de
                        propósito — senão o vínculo criado pelo lançamento da
                        nota encobriria o fator de compra do produto. Sem a
                        etiqueta, quem olha não sabe se a conversão foi dita ou
                        se é só o padrão. */}
                    {!c.fator_confirmado && (
                      <span className="mt-1 block text-[11.5px] text-suave">não informada</span>
                    )}
                  </td>
                  {podeEditar && (
                    <td className="whitespace-nowrap">
                      <button
                        type="button"
                        className="btn btn-secundario"
                        // ⚠️ **Só desabilita enquanto grava.** Gravar sem mudar
                        // o número é ação legítima: confirmar o 1 que está ali
                        // é uma AFIRMAÇÃO, e é ela que faz a cascata passar a
                        // respeitar o valor. Desabilitar "sem mudança" tiraria
                        // justamente o caso do pacote de 1 kg.
                        aria-busy={salvando === k} disabled={salvando === k}
                        onClick={() => void gravar(c)}
                      >
                        {salvando === k ? "…" : "Gravar"}
                      </button>
                      <button
                        type="button"
                        className="link-acao link-acao-erro ml-3"
                        aria-label={`desvincular ${c.codigo}`}
                        disabled={ocupado === k}
                        onClick={() => void pedirDesvinculo(c)}
                      >
                        {ocupado === k ? "…" : "desvincular"}
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {soltando && (
        <Confirmacao
          titulo="Desvincular este código?"
          rotuloConfirmar="Desvincular"
          perigo
          ocupado={!!ocupado}
          aoCancelar={() => setSoltando(null)}
          aoConfirmar={() => void desvincular()}
        >
          <p>
            O código <b className="mono">{soltando.previa.codigo}</b>
            {soltando.previa.descricao && <> ({soltando.previa.descricao})</>} deixa de apontar
            para este produto.
          </p>
          {soltando.previa.devolve_para ? (
            <label className="mt-3 flex items-start gap-2 rounded-[10px] border border-linha p-3">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-erva"
                checked={devolver}
                onChange={(e) => setDevolver(e.target.checked)}
              />
              <span className="text-[13.5px] leading-snug">
                Reativar <b>{soltando.previa.devolve_para.nome}</b> e devolver este código a
                ele — os dois voltam a ser produtos separados.
                {!devolver && (
                  <span className="mt-1 block text-suave">
                    Desmarcado, o cadastro continua arquivado e a próxima nota com este código
                    vai pedir conciliação.
                  </span>
                )}
              </span>
            </label>
          ) : (
            <p className="mt-3 text-[13.5px] text-suave">
              A próxima nota que trouxer este código não vai achar produto e cairá na
              conciliação, para alguém dizer de quem é.
            </p>
          )}
          <p className="mt-3 text-[13.5px] text-suave">
            Vale daqui para a frente: o que já entrou no estoque por este código continua
            neste produto.
            {soltando.previa.itens_de_nota_abertos > 0 && (
              <>
                {" "}
                Há <b>{soltando.previa.itens_de_nota_abertos}</b> item(ns) de nota ainda não
                lançada ligados a este produto — confira se algum era deste código.
              </>
            )}
          </p>
        </Confirmacao>
      )}
    </>
  );
}
