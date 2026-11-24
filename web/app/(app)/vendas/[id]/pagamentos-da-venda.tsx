import { reais } from "@/lib/numeros";

import type { PagamentoDaVenda } from "../tipos";

/**
 * Como a venda foi paga (migração 160): as finalizadoras do cupom do PDV, com o troco dito.
 * ⚠️ Venda da planilha ou lançada à mão não tem forma, e a tela diz isso em vez de calar.
 */
export default function PagamentosDaVenda({ pagamentos, troco, origem }: {
  pagamentos: PagamentoDaVenda[];
  troco: number | string;
  origem: string;
}) {
  if (!pagamentos.length) {
    return (
      <p className="mt-2 text-[13px] text-suave" id="venda-pagamentos">
        forma de pagamento não informada
        {origem === "PDV_LEGAL" && " (completa-se em Integrações ▸ PDV Legal)"}
      </p>
    );
  }
  return (
    <div className="mt-2 border-t border-dashed border-linha pt-2 text-[13px]" id="venda-pagamentos">
      <p className="text-suave">pago em</p>
      <ul>
        {pagamentos.map((p, n) => (
          <li key={n} className="flex justify-between gap-3">
            <span>
              {p.rotulo}
              {p.nome_pdv && p.nome_pdv.toUpperCase() !== p.rotulo.toUpperCase() && (
                <span className="text-suave"> ({p.nome_pdv})</span>
              )}
            </span>
            <span className="tabular-nums">{reais(Number(p.valor))}</span>
          </li>
        ))}
      </ul>
      {Number(troco) > 0 && (
        <p className="text-suave">troco de {reais(Number(troco))} devolvido</p>
      )}
    </div>
  );
}
