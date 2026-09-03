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
  /**
   * Cupons cancelados no PDV neste dia.
   *
   * 🔑 **É o número que faz a conferência fechar.** O PDV conta os cupons
   * emitidos, incluindo os cancelados; aqui só as vendas contam. Sem este
   * número à vista, 164 lá e 154 aqui se lê como perda de dado — e foi
   * exatamente a desconfiança que gerou esta linha.
   */
  canceladas: number;
  /** Quanto o dia deixou de faturar por cancelamento. */
  valor_cancelado: number;
  itens: number;
  receita: number;
  ticket_medio: number | null;
  anterior: string | null;
  proximo: string | null;
};

const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
  "Jul", "Ago", "Set", "Out", "Nov", "Dez"];

const SEMANA = ["domingo", "segunda-feira", "terça-feira", "quarta-feira",
  "quinta-feira", "sexta-feira", "sábado"];

/** "2026-09-02" → "02 Set 2026", sem depender do ICU do navegador. */
function porExtenso(iso: string) {
  const [ano, mes, dia] = iso.split("-").map(Number);
  return `${String(dia).padStart(2, "0")} ${MESES[mes - 1]} ${ano}`;
}

/**
 * "2026-09-02" → "quarta-feira" (pedido do dono, 03/09/2026).
 *
 * 🔑 **O dia da semana é o que explica o número.** Um sábado e uma segunda não
 * se comparam, e a data sozinha obriga quem olha a fazer essa conta de cabeça —
 * ou a errar a leitura de um movimento que estava normal para aquele dia.
 *
 * ⚠️ **`new Date(iso)` está PROIBIDO aqui.** O construtor lê `aaaa-mm-dd` como
 * meia-noite UTC, e em Brasília isso é o dia ANTERIOR a partir das 21h: o
 * sábado apareceria como sexta, e justamente no fim de semana, que é quando a
 * casa mais olha. `new Date(ano, mes - 1, dia)` é meia-noite LOCAL, e aí o dia
 * da semana é o que a pessoa tem no calendário da parede. Mesma armadilha que
 * `lib/datas.ts` documenta, pela ponta da leitura.
 *
 * ⚠️ Os nomes são NOSSOS, e não `toLocaleDateString`, pela mesma razão dos
 * meses: sem o ICU completo o navegador devolve o nome em inglês, e o cartão
 * sairia com "Wednesday" no meio do português.
 */
function diaDaSemana(iso: string) {
  const [ano, mes, dia] = iso.split("-").map(Number);
  return SEMANA[new Date(ano, mes - 1, dia).getDay()];
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
          <div className="min-w-[150px] text-center">
            <p className="rotulo">Vendas do dia</p>
            <p className="mono mt-0.5 text-[19px] font-bold leading-none">
              {porExtenso(dia.data)}
            </p>
            {/* 🔑 Embaixo da data e menor: quem procura a data acha a data, e
                quem quer comparar com a semana passada já tem a resposta sem
                contar nos dedos. */}
            <p className="mt-1 text-[12.5px] leading-none text-suave">
              {diaDaSemana(dia.data)}
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
            {/* ⚠️ **A frase diz a CONTA, não só o número.** "10 cancelados"
                sozinho não responde por que o PDV mostra outro total; escrever
                a soma responde. */}
            {dia.canceladas > 0 && (
              <>
                {/* ⚠️ **O valor junto do número, e não só a contagem.** "10
                    cancelados" não diz se foram dez cafés ou dez bolos
                    inteiros — e é o valor que decide se aquilo merece uma
                    conversa com o caixa. */}
                <b>{inteiro(dia.canceladas)}</b> cupom(ns) cancelado(s) no PDV, somando{" "}
                <b>{reais(dia.valor_cancelado)}</b> — lá o dia tem{" "}
                <b>{inteiro(dia.vendas + dia.canceladas)}</b> cupons.{" "}
              </>
            )}
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
