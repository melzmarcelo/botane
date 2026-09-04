"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Etiqueta, Vazio } from "@/components/ui";

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
 */

export type CodigoExterno = {
  sistema: string;
  codigo: string;
  descricao_externa: string | null;
  fator: number | string;
  fator_confirmado: boolean;
  origem_vinculo: string | null;
  fornecedor: string | null;
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
      setRascunho({ ...rascunho, [k]: "" });
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

      <div className="mt-3 overflow-x-auto">
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
                    <td>
                      <button
                        type="button"
                        className="btn btn-secundario"
                        disabled={salvando === k || (rascunho[k] ?? String(atual)) === String(atual)
                          ? salvando === k
                          : false}
                        onClick={() => void gravar(c)}
                      >
                        {salvando === k ? "…" : "Gravar"}
                      </button>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
