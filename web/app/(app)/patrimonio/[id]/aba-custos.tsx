"use client";

import { Cartao, Vazio } from "@/components/ui";
import { reais } from "@/lib/numeros";
import { dataBr, type BemDetalhe } from "@/lib/patrimonio";

import ValorDoBem from "./valor";

/**
 * Aba Custos: compra, preventivas e reparos em separado, o total, a porcentagem da
 * manutenção sobre a compra e o extrato com o saldo acumulado.
 * 🔑 **Os números vêm prontos do servidor** (`custos` em `services/patrimonio.py`, somados em
 * Decimal): aqui só se mostra.
 * 🔑 O número que esta aba responde é "já vale trocar em vez de consertar?" — por isso a
 * porcentagem sobre a compra fica em destaque.
 */
export default function AbaCustos({ bem }: { bem: BemDetalhe }) {
  const c = bem.custos;
  return (
    <div className="flex flex-col gap-6">
      <section aria-label="custos do bem" className="faixa-hoje" id="custos-resumo">
        <Bloco rotulo="Compra" valor={c.compra !== null ? reais(c.compra) : "—"}
               sub={c.compra !== null ? dataBr(bem.data_compra) : "sem valor de compra"} />
        <Bloco rotulo="Preventivas" valor={reais(c.preventivas)} sub="manutenção planejada" />
        <Bloco rotulo="Reparos" valor={reais(c.corretivas)} sub="corretivas" />
        <Bloco rotulo="Custo total" valor={reais(c.total)}
               sub={c.manutencao_pct !== null
                 ? <>manutenção = <b>{c.manutencao_pct.toLocaleString("pt-BR")}%</b> da compra</>
                 : "sem compra para comparar"} />
      </section>

      <Cartao titulo="Extrato" descricao="Da compra até hoje, com o saldo acumulado de cada lançamento.">
        {c.extrato.length ? (
          <div className="grid-rolante">
            <table className="tabela" id="custos-extrato">
              <thead>
                <tr><th>Data</th><th>Lançamento</th><th>Detalhe</th><th className="num">Valor</th>
                  <th className="num">Saldo acumulado</th></tr>
              </thead>
              <tbody>
                {c.extrato.map((l, i) => (
                  <tr key={i}>
                    <td>{dataBr(l.data)}</td>
                    <td>{l.o_que}{l.garantia ? " · garantia" : ""}</td>
                    <td className="text-[13.5px] text-suave">{l.detalhe ?? "—"}</td>
                    <td className="num">{l.valor !== null ? reais(l.valor) : "—"}</td>
                    <td className="num font-semibold">{reais(l.saldo)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Vazio>Sem valor de compra e sem manutenção registrada.</Vazio>}
      </Cartao>

      <Cartao titulo="Valor e depreciação" descricao="Linear pela vida útil — a mesma conta de Patrimônio ▸ Valor.">
        <ValorDoBem bem={bem} id="custos-valor" />
      </Cartao>
    </div>
  );
}

function Bloco({ rotulo, valor, sub }: { rotulo: string; valor: string; sub: React.ReactNode }) {
  return (
    <div className="cartao min-w-0 px-5 py-4">
      <p className="text-[13px] font-semibold text-suave">{rotulo}</p>
      <p className="mono mt-2 text-[22px] font-extrabold leading-none tracking-[-0.02em]">{valor}</p>
      <p className="mt-2 text-[12.5px] leading-snug text-suave">{sub}</p>
    </div>
  );
}
