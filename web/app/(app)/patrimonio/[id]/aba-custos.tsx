"use client";

import { useState } from "react";

import { Aviso, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { reais } from "@/lib/numeros";
import { dataBr, situacaoNoOmie, type BemDetalhe, type LinhaOmie, type SituacaoOmie } from "@/lib/patrimonio";

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

      <NoOmie bem={bem} />

      <Cartao titulo="Valor e depreciação" descricao="Linear pela vida útil — a mesma conta de Patrimônio ▸ Valor.">
        <ValorDoBem bem={bem} id="custos-valor" />
      </Cartao>
    </div>
  );
}

const COR_OMIE: Partial<Record<LinhaOmie["situacao"], "erva" | "alerta" | "neutro">> = {
  PAGO: "erva", ATRASADO: "alerta", ABERTO: "alerta",
};

/**
 * 157 — a situação no Omie da compra e de cada manutenção com nota: pago, em aberto, atrasado.
 * 🔑 **Por botão, nunca ao abrir a ficha**: cada consulta gasta cota da conta do Omie, e o
 * Omie bloqueia quem consome demais. 🔑 **Só leitura** — nada aqui é gravado; a situação é a
 * de agora, lá.
 */
function NoOmie({ bem }: { bem: BemDetalhe }) {
  const [r, setR] = useState<SituacaoOmie | null>(null);
  const [erro, setErro] = useState("");
  const [consultando, setConsultando] = useState(false);

  async function consultar() {
    setConsultando(true);
    setErro("");
    try {
      setR(await situacaoNoOmie(bem.id));
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Não foi possível consultar o Omie");
    } finally {
      setConsultando(false);
    }
  }

  return (
    <Cartao titulo="Situação no Omie"
            descricao="Se a compra e as manutenções com nota fiscal já foram pagas — consultado agora, no Omie."
            acao={
              <button type="button" className="btn btn-secundario" id="custos-omie-consultar"
                      disabled={consultando} aria-busy={consultando} onClick={() => void consultar()}>
                {consultando ? "Consultando…" : r ? "Consultar de novo" : "Consultar no Omie"}
              </button>
            }>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!r && !erro && (
        <p className="text-[14px] text-suave">
          O sistema acha o título pelo fornecedor e pelo número da nota. Manutenção sem nota não tem como ser achada.
        </p>
      )}
      {r && (r.linhas.length ? (
        <>
          {r.modo === "simulado" && (
            <p className="mb-3 text-[13px] text-alerta">Omie em modo simulado: são dados de demonstração.</p>
          )}
          <div className="grid-rolante">
            <table className="tabela" id="custos-omie-lista">
              <thead>
                <tr><th>Data</th><th>Lançamento</th><th>NF</th><th>Fornecedor</th>
                  <th className="num">Valor</th><th>No Omie</th><th>Detalhe</th></tr>
              </thead>
              <tbody>
                {r.linhas.map((l) => (
                  <tr key={l.chave} data-situacao={l.situacao}>
                    <td>{dataBr(l.data)}</td>
                    <td>{l.o_que}</td>
                    <td className="mono text-[13px]">{l.nota_fiscal ?? "—"}</td>
                    <td className="text-[13.5px]">{l.fornecedor ?? "—"}</td>
                    <td className="num">{l.valor !== null ? reais(l.valor) : "—"}</td>
                    <td><Etiqueta cor={COR_OMIE[l.situacao] ?? "neutro"}>{l.situacao_txt}</Etiqueta></td>
                    <td className="text-[13px] text-suave">
                      {[l.detalhe, l.proximo_vencimento ? `vence ${dataBr(l.proximo_vencimento)}` : null]
                        .filter(Boolean).join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : <Vazio>Sem compra nem manutenção com custo para procurar.</Vazio>)}
    </Cartao>
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
