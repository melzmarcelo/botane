"use client";

import { reais } from "@/lib/numeros";
import { dataBr, type BemDetalhe } from "@/lib/patrimonio";

/** 141 — o valor de hoje (ou o da baixa), calculado pelo servidor com a conta do relatório. */
export default function ValorDoBem({ bem, id }: { bem: BemDetalhe; id?: string }) {
  const v = bem.valor;
  if (v.sem_valor) {
    return <p className="text-[13.5px] text-suave" id={id}>
      Sem valor de compra — o bem não entra no valor do patrimônio.</p>;
  }
  if (v.sem_data) {
    return <p className="text-[13.5px] text-suave" id={id}>
      Sem data de compra, não deprecia: conta pelo valor de compra ({reais(v.valor_atual ?? 0)}).</p>;
  }
  return (
    <p className="text-[13.5px]" id={id}>
      <b>{bem.situacao === "BAIXADO" ? "Valor na baixa" : "Valor atual"}: {reais(v.valor_atual ?? 0)}</b>
      <span className="text-suave">
        {" "}· depreciação {reais(v.depreciacao ?? 0)} ({v.depreciado_pct?.toLocaleString("pt-BR")}%)
        em {v.meses} {v.meses === 1 ? "mês" : "meses"} · {reais(v.quota_mensal ?? 0)} por mês
        · vida útil {v.vida_util} anos{v.vida_padrao ? " (padrão)" : ""}
        {v.depreciado_total ? " · totalmente depreciado" : v.fim_vida ? ` · até ${dataBr(v.fim_vida)}` : ""}
      </span>
    </p>
  );
}
