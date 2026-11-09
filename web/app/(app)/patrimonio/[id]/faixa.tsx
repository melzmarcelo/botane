"use client";

import type { ReactNode } from "react";

import ValorQueCabe from "@/components/valor-que-cabe";
import { plural, reais } from "@/lib/numeros";
import { dataBr, periodicidade, type BemDetalhe } from "@/lib/patrimonio";

import { emDias } from "./form";
import type { Aba } from "./abas-da-ficha";

/**
 * Os quatro números da ficha, nos mesmos cartões de indicador do Início (`.faixa-hoje`).
 * Cada cartão leva à aba que explica o número.
 * ⚠️ **Nada é calculado aqui**: a situação da garantia, a próxima preventiva, os dias e o
 * custo acumulado vêm prontos do servidor — calculados aqui, divergiriam da lista e do alerta.
 */
export default function FaixaDoBem({ bem, irPara }: { bem: BemDetalhe; irPara: (a: Aba) => void }) {
  const ultima = bem.manutencoes[0];
  const n = bem.manutencoes.length;
  return (
    <section aria-label="resumo do bem" className="faixa-hoje" id="bem-faixa">
      <Numero rotulo="Garantia" aba="garantia" irPara={irPara} {...garantia(bem)} />
      <Numero rotulo="Próxima preventiva" aba="preventiva" irPara={irPara} {...preventiva(bem)} />
      <Numero rotulo="Última manutenção" aba="manutencoes" irPara={irPara}
              valor={ultima ? dataBr(ultima.data) : "—"}
              sub={ultima
                ? <>{ultima.tipo_txt}{ultima.custo !== null ? ` · ${reais(ultima.custo)}` : ""}
                    {ultima.coberta_garantia ? " · garantia" : ""}
                    {` · ${bem.manutencoes_recentes} nos últimos ${bem.recente_dias} dias`}</>
                : "nenhuma registrada"} />
      <Numero rotulo="Custo acumulado" aba="custos" irPara={irPara} valor={reais(bem.custos.total)}
              sub={bem.custos.compra !== null
                ? `compra + ${plural(n, "manutenção", "manutenções")}`
                : `${plural(n, "manutenção", "manutenções")} · sem valor de compra`} />
    </section>
  );
}

type Linha = { valor: string; sub: ReactNode; tom?: "alerta" | "erro" };

function garantia(bem: BemDetalhe): Linha {
  const ate = dataBr(bem.garantia_ate);
  switch (bem.status_garantia) {
    case "VENCE_30":
      return { valor: bem.garantia_dias === 0 ? "Vence hoje" : `Vence ${emDias(bem.garantia_dias)}`,
               sub: `até ${ate}`, tom: "alerta" };
    case "ATIVA":
      return { valor: `Até ${ate}`, sub: `em garantia · vence ${emDias(bem.garantia_dias)}` };
    case "FORA":
      return { valor: "Vencida", sub: `desde ${ate}` };
    default:
      return { valor: "—", sub: "sem garantia informada" };
  }
}

function preventiva(bem: BemDetalhe): Linha {
  const per = periodicidade(bem.preventiva_meses);
  switch (bem.status_preventiva) {
    case "VENCIDA":
      return { valor: dataBr(bem.proxima_preventiva), sub: `${per} · atrasada ${emDias(bem.preventiva_dias)}`,
               tom: "erro" };
    case "VENCE_30":
      return { valor: dataBr(bem.proxima_preventiva), sub: `${per} · ${emDias(bem.preventiva_dias)}`,
               tom: "alerta" };
    case "EM_DIA":
      return { valor: dataBr(bem.proxima_preventiva), sub: `${per} · ${emDias(bem.preventiva_dias)}` };
    case "SEM_REGISTRO":
      return { valor: "—", sub: `${per} · falta a data da última` };
    case "FORA":
      return { valor: "—", sub: `não cobra preventiva (${bem.situacao_txt.toLowerCase()})` };
    default:
      return { valor: "—", sub: "sem plano de preventiva" };
  }
}

function Numero({ rotulo, valor, sub, tom, aba, irPara }: Linha & {
  rotulo: string; aba: Aba; irPara: (a: Aba) => void;
}) {
  const cor = tom === "alerta" ? "text-alerta" : tom === "erro" ? "text-erro" : "";
  return (
    <button type="button" onClick={() => irPara(aba)}
            className="faixa-numero group cartao block min-w-0 px-5 py-4 text-left transition-colors hover:border-linha2">
      <p className="text-[13px] font-semibold text-suave">{rotulo}</p>
      <ValorQueCabe maximo={24} className={`faixa-valor mono mt-2 font-extrabold leading-none tracking-[-0.02em] group-hover:text-erva ${cor}`}>
        {valor}
      </ValorQueCabe>
      <p className="mt-2 text-[12.5px] leading-snug text-suave">{sub}</p>
    </button>
  );
}
