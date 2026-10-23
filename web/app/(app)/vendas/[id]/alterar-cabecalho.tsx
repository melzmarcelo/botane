"use client";

/**
 * Trocar a data e o número de um documento lançado à mão.
 *
 * 🔑 Pedido do dono (23/10/2026): *"Para documentos lançados a mão, que ainda não estão
 * em algum lote baixado, permitir alterar a data e numero do documento"*. Quem decide
 * se pode é o servidor (`pode_alterar`).
 * ⚠️ Trocar a DATA refaz a baixa de estoque: a saída é estornada na data antiga e
 * lançada de novo na nova — a confirmação diz isso antes.
 */

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Cartao, Confirmacao } from "@/components/ui";
import { hoje } from "@/lib/datas";
import { alterarVenda } from "@/lib/vendas";
import { dataBr } from "../tipos";

export default function AlterarCabecalho({ idVenda, data, documento, temBaixa, aoAlterar }: {
  idVenda: number;
  data: string;
  documento: string | null;
  temBaixa: boolean;
  aoAlterar: () => void;
}) {
  const aviso = useAviso();
  const [aberto, setAberto] = useState(false);
  const [novaData, setNovaData] = useState(data);
  const [novoDoc, setNovoDoc] = useState(documento ?? "");
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  const mudaData = novaData !== data;
  const mudaDoc = novoDoc.trim() !== (documento ?? "") && novoDoc.trim() !== "";
  const pronto = !!novaData && (mudaData || mudaDoc);

  async function salvar() {
    setOcupado(true);
    try {
      const r = await alterarVenda(idVenda, {
        data: mudaData ? novaData : null,
        documento: mudaDoc ? novoDoc.trim() : null,
      });
      aviso.sucesso(r.message);
      setConfirmando(false);
      setAberto(false);
      aoAlterar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível alterar a venda");
    } finally {
      setOcupado(false);
    }
  }

  if (!aberto) {
    return (
      <div>
        <button id="venda-alterar" className="btn btn-secundario" onClick={() => setAberto(true)}>
          Alterar data ou número
        </button>
      </div>
    );
  }

  return (
    <Cartao
      titulo="Alterar data ou número do documento"
      descricao="Só o cabeçalho: os itens e os valores continuam os mesmos."
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <Campo rotulo="Data">
          <input id="venda-alterar-data" className="campo" type="date" max={hoje()}
            value={novaData} onChange={(e) => setNovaData(e.target.value)} />
        </Campo>
        <Campo rotulo="Número do documento">
          <input id="venda-alterar-documento" className="campo" maxLength={40}
            value={novoDoc} onChange={(e) => setNovoDoc(e.target.value)} />
        </Campo>
        <div className="flex items-end gap-2">
          <button id="venda-alterar-salvar" className="btn btn-primario" disabled={!pronto || ocupado}
            onClick={() => setConfirmando(true)}>
            Salvar
          </button>
          <button className="btn btn-secundario" onClick={() => {
            setAberto(false);
            setNovaData(data);
            setNovoDoc(documento ?? "");
          }}>
            Cancelar
          </button>
        </div>
      </div>

      {confirmando && (
        <Confirmacao
          titulo="Alterar a venda?"
          rotuloConfirmar="Alterar"
          ocupado={ocupado}
          aoConfirmar={salvar}
          aoCancelar={() => setConfirmando(false)}
        >
          <p id="venda-alterar-confirma">
            {mudaDoc && <>Documento <b>{documento ?? "—"}</b> passa a <b>{novoDoc.trim()}</b>. </>}
            {mudaData && <>Data <b>{dataBr(data)}</b> passa a <b>{dataBr(novaData)}</b>.</>}
          </p>
          {mudaData && temBaixa && (
            <p className="mt-3 text-[13.5px] text-suave">
              A baixa de estoque desta venda é <b>estornada</b> no dia {dataBr(data)} e{" "}
              <b>lançada de novo</b> no dia {dataBr(novaData)} — o estoque não se apaga, se
              corrige.
            </p>
          )}
        </Confirmacao>
      )}
    </Cartao>
  );
}
