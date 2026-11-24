"use client";

import { Cartao } from "@/components/ui";
import { pct, plural, reais } from "@/lib/numeros";
import type { PorPagamento as Dados } from "@/lib/vendas-painel";

import { BarrasDeitadas } from "./graficos";

/**
 * Por forma de pagamento (migração 160, pedido do dono de 24/11/2026): as finalizadoras do
 * PDV. 🔑 Dinheiro já sem o troco, que é o que ficou na casa; o troco e o que não tem forma
 * aparecem ditos embaixo, para a soma fechar com o faturado.
 * ⚠️ Só sem recorte: o pagamento é do cupom inteiro (ver `painel_vendas.painel`).
 */
export function PorPagamento({ q }: { q: Dados }) {
  if (!q.linhas.length && !q.sem_pagamento.cupons) return null;
  return (
    <Cartao>
      <div id="painel-vendas-pagamento">
        <h2 className="mb-3 text-[15px] font-bold">Por forma de pagamento</h2>
        {q.linhas.length ? (
          <BarrasDeitadas
            linhas={q.linhas.map((l) => ({
              chave: l.grupo, id: null, nome: l.rotulo, valor: l.valor,
              detalhe: `${plural(l.cupons, "cupom", "cupons")}`
                + (l.participacao_pct !== null ? ` · ${pct(l.participacao_pct)}` : "")
                + (l.grupo === "DINHEIRO" && q.troco > 0
                  ? ` · ${reais(q.dinheiro_recebido)} recebidos, ${reais(q.troco)} de troco` : ""),
            }))}
            valor={reais} />
        ) : (
          <p className="text-[13.5px] text-suave">Nenhuma venda do recorte tem a forma de pagamento.</p>
        )}
        {q.sem_pagamento.cupons > 0 && (
          <p className="mt-3 border-t border-dashed border-linha pt-2.5 text-[12.5px] text-suave"
             id="painel-vendas-sem-pagamento">
            {plural(q.sem_pagamento.cupons, "venda", "vendas")} sem a forma de pagamento, somando{" "}
            {reais(q.sem_pagamento.valor)}: lançadas à mão, da planilha ou do PDV antes de o sistema
            guardar a forma. As do PDV se completam em Integrações ▸ PDV Legal.
          </p>
        )}
      </div>
    </Cartao>
  );
}
