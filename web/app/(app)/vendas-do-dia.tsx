"use client";

import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";

/**
 * O movimento de um dia, com setas para andar entre os dias que TÊM venda.
 *
 * 🔑 **Abre no dia da última venda, não em hoje** (pedido do dono, 03/09/2026).
 * De manhã, ou num dia em que a busca no PDV ainda não rodou, "hoje" é um dia
 * sem venda nenhuma — e um cartão zerado se lê como *"a casa não vendeu"*, que
 * é diferente de *"ainda não importou"*.
 *
 * 🔑 **As setas andam entre dias com venda, não entre dias do calendário.**
 * Quem diz para onde dá para ir é o servidor (`anterior` e `proximo`), e é isso
 * que desliga a seta: avançar para um domingo fechado mostraria um zero, que é
 * o mesmo engano pela outra porta.
 *
 * ⚠️ **Só o dia navega.** Trocar de dia não recarrega a apuração do período,
 * os alertas nem o peso por setor — seria refazer a tela toda para mudar três
 * números.
 */

export type Dia = {
  data: string;
  vendas: number;
  itens: number;
  receita: number;
  ticket_medio: number | null;
  anterior: string | null;
  proximo: string | null;
};

const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez"];

/** "2026-09-02" → "02 Set 2026", sem depender do ICU do navegador. */
function porExtenso(iso: string) {
  const [ano, mes, dia] = iso.split("-").map(Number);
  return `${String(dia).padStart(2, "0")} ${MESES[mes - 1]} ${ano}`;
}

const inteiro = (n: number) =>
  Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 0 });

export default function VendasDoDia({ inicial }: { inicial: Dia }) {
  const [dia, setDia] = useState<Dia>(inicial);
  const [indo, setIndo] = useState(false);
  const [erro, setErro] = useState("");

  async function ir(data: string | null) {
    if (!data) return;
    setIndo(true);
    setErro("");
    try {
      const r = await api.get<{ dia: Dia | null }>(`/inicio/dia?data=${data}`);
      if (r.dia) setDia(r.dia);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o dia");
    } finally {
      setIndo(false);
    }
  }

  const hoje = new Date().toLocaleDateString("sv-SE");
  // ⚠️ "É o dia mais recente com venda" só vale a pena dizer quando ele NÃO é
  // hoje: é a resposta para "por que não estou vendo o movimento de hoje?".
  const oMaisRecente = !dia.proximo && dia.data !== hoje;

  return (
    <section className="cartao p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="link-acao"
            aria-label="dia anterior com venda"
            disabled={!dia.anterior || indo}
            onClick={() => void ir(dia.anterior)}
          >
            ‹
          </button>
          <div className="min-w-[130px] text-center">
            <p className="rotulo">Vendas do dia</p>
            <p className="mono mt-0.5 text-[19px] font-bold leading-none">
              {porExtenso(dia.data)}
            </p>
          </div>
          <button
            type="button"
            className="link-acao"
            aria-label="próximo dia com venda"
            disabled={!dia.proximo || indo}
            onClick={() => void ir(dia.proximo)}
          >
            ›
          </button>
        </div>

        <div className="flex flex-wrap gap-6">
          <div>
            <p className="rotulo">Vendas</p>
            <p className="mono mt-1 text-[22px] font-bold leading-none">
              {inteiro(dia.vendas)}
            </p>
          </div>
          <div>
            <p className="rotulo">Valor total</p>
            <p className="mono mt-1 text-[22px] font-bold leading-none">
              {reais(dia.receita)}
            </p>
          </div>
          <div>
            <p className="rotulo">Ticket médio</p>
            {/* ⚠️ Sem venda no dia o ticket vem NULO, não zero: um ticket de
                zero real é uma afirmação, e não a ausência de uma. */}
            <p className="mono mt-1 text-[22px] font-bold leading-none">
              {dia.ticket_medio === null ? "—" : reais(dia.ticket_medio)}
            </p>
          </div>
        </div>
      </div>

      <p className="mt-3 text-[13px] leading-snug text-suave">
        {dia.vendas === 0 ? (
          "Nenhuma venda neste dia."
        ) : (
          <>
            {inteiro(dia.itens)} item(ns) vendido(s).{" "}
            <Link href="/vendas" className="text-erva underline underline-offset-2">
              ver as vendas
            </Link>
            {oMaisRecente && " · é o dia mais recente com venda importada"}
          </>
        )}
        {erro && <span className="text-erro"> {erro}</span>}
      </p>
    </section>
  );
}
