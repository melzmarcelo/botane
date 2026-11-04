"use client";

import { useEffect, useMemo, useState } from "react";

import { montarMensagem } from "@/app/(app)/reservas/plano-de-acao/lista";
import { GraficoBarras, type Barra } from "@/app/(app)/vendas/painel/graficos";
import { fatiar, Paginacao, usePaginacao } from "@/components/paginacao";
import { Cartao, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { inteiro } from "@/lib/numeros";
import type { Aniversariante, PainelClientes } from "@/lib/reservas";

/**
 * Os aniversariantes, no Painel de clientes.
 *
 * 🔑 **Pedido do dono (04/11/2026):** *"algo relacionado a aniversariantes"*. Os recortes
 * prontos do LeadsFood (hoje, 7 dias, mês), mais o mês que vem para planejar, e cada um com
 * o botão que abre o WhatsApp com o parabéns escrito.
 * ⚠️ **O botão ABRE a conversa, não envia** — como no Plano de ação (`wa.me`, o WhatsApp de
 * quem está na tela). O parabéns automático do dia é outra coisa: o aviso ANIVERSARIO do
 * WhatsApp da loja (`services/whatsapp.varrer`), que só sai com o número conectado.
 * ⚠️ Quem respondeu "PARAR" ao WhatsApp da casa aparece, mas SEM o botão.
 */

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const SEMANA = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const MODELO =
  "Feliz aniversário, {nome}! 🎉 Toda a equipe do {loja} deseja um dia lindo para você. " +
  "Venha comemorar com a gente!";

type Aba = "hoje" | "semana" | "mes" | "proximo";

const fone = (t: string) => {
  const m = t.match(/^(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `(${m[1]}) ${m[2]}-${m[3]}` : t;
};

/** "2026-11-12" → "12/11 · qui". */
const quando = (iso: string) => {
  const [a, m, d] = iso.split("-").map(Number);
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")} · ${SEMANA[new Date(a, m - 1, d).getDay()]}`;
};

const distancia = (n: number) =>
  n === 0 ? "hoje" : n === 1 ? "amanhã" : n === -1 ? "ontem" : n > 0 ? `em ${n} dias` : `há ${-n} dias`;

export default function Aniversariantes({ p }: { p: PainelClientes }) {
  const a = p.aniversariantes;
  const mesAtual = Number(p.hoje.slice(5, 7)) - 1;
  const abas: { v: Aba; r: string; n: number; filtro: (x: Aniversariante) => boolean }[] = [
    { v: "hoje", r: "Hoje", n: a.hoje, filtro: (x) => x.faltam === 0 },
    { v: "semana", r: "Próximos 7 dias", n: a.semana, filtro: (x) => x.faltam >= 0 && x.faltam < 7 },
    { v: "mes", r: `Em ${MESES[mesAtual]}`, n: a.no_mes, filtro: (x) => x.dia.slice(0, 7) === p.hoje.slice(0, 7) },
    { v: "proximo", r: `Em ${MESES[(mesAtual + 1) % 12]}`, n: a.proximo_mes,
      filtro: (x) => x.dia.slice(0, 7) !== p.hoje.slice(0, 7) },
  ];
  // Abre na primeira aba que tem gente: um "Hoje" vazio esconderia a semana.
  const [aba, setAba] = useEstadoNaUrl<string>("aniversario", "");
  const atual = abas.find((x) => x.v === aba) ?? abas.find((x) => x.n > 0) ?? abas[0];
  const lista = useMemo(() => a.lista.filter(atual.filtro), [a.lista, atual]);
  const [modelo, setModelo] = useState(MODELO);
  const loja = p.loja ?? "nossa casa";

  const pag = usePaginacao("aniversariantes", { filtros: [atual.v] });
  const { setTotal } = pag;
  useEffect(() => { setTotal(lista.length); }, [lista.length, setTotal]);

  const total = a.por_mes.reduce((s, n) => s + n, 0);
  const barras: Barra[] = a.por_mes.map((n, i) => ({
    chave: String(i), rotulo: MESES[i], valor: n,
    titulo: `${MESES[i]}${i === mesAtual ? " (este mês)" : ""}`,
    dica: [{ rotulo: "Aniversariantes", valor: inteiro(n) }],
  }));

  return (
    <Cartao titulo="Aniversariantes"
            descricao={`Quem tem data de nascimento no cadastro: ${inteiro(total)} ${total === 1 ? "cliente" : "clientes"}.`}>
      <div className="grid grid-cols-1 gap-6 px-5 py-4 lg:grid-cols-[minmax(0,1fr)_380px]" id="clientes-aniversariantes">
        <div className="flex min-w-0 flex-col gap-4">
          <div className="flex flex-wrap gap-1" role="tablist" aria-label="Quando">
            {abas.map((x) => (
              <button key={x.v} type="button" role="tab" aria-selected={atual.v === x.v} data-aba={x.v}
                      className={`btn px-3 py-1.5 text-[13px] ${atual.v === x.v ? "btn-primario" : "btn-secundario"}`}
                      onClick={() => setAba(x.v)}>
                {x.r} <span className="mono">{inteiro(x.n)}</span>
              </button>
            ))}
          </div>

          <details>
            <summary className="cursor-pointer text-[14px]">
              <span className="rotulo-campo">Mensagem de parabéns</span>{" "}
              <span className="text-suave">· editar</span>
              <span className="mt-1 block truncate text-[13px] text-suave">{modelo}</span>
            </summary>
            <textarea aria-label="Mensagem de parabéns" className="campo mt-2 min-h-[80px]"
                      value={modelo} onChange={(e) => setModelo(e.target.value)} />
            <span className="mt-1 block text-[12px] text-suave">
              {"{nome}"} vira o primeiro nome do cliente e {"{loja}"}, o nome da casa. O texto abre no
              WhatsApp para você revisar antes de enviar.
            </span>
          </details>

          {!lista.length ? (
            <Vazio>Ninguém faz aniversário {atual.v === "hoje" ? "hoje" : "neste período"}.</Vazio>
          ) : (
            <div>
              <ul className="divide-y divide-linha border-y border-linha" aria-label="Aniversariantes">
                {fatiar(lista, pag).map((x) => (
                  <li key={x.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-2.5">
                    <div className="min-w-0 basis-full sm:basis-0 sm:flex-1">
                      <b className="block truncate">{x.nome || "Sem nome"}</b>
                      <span className="mono whitespace-nowrap text-[13px] text-suave">{fone(x.telefone)}</span>
                    </div>
                    <div className="min-w-0 flex-1 text-[13px] text-suave sm:flex-none sm:text-right">
                      <span className="mono text-tinta">{quando(x.dia)}</span>
                      <span className="block">
                        {x.faltam === 0 ? <b className="text-tinta">hoje</b> : distancia(x.faltam)} · faz{" "}
                        <span className="mono text-tinta">{x.faz}</span>
                      </span>
                    </div>
                    {x.nao_quer_whatsapp ? (
                      <span className="text-[12px] text-suave" title="Respondeu PARAR ao WhatsApp da casa">
                        não quer receber
                      </span>
                    ) : (
                      <a className="btn btn-secundario px-3 py-1.5 text-[13px]" target="_blank" rel="noreferrer"
                         href={`https://wa.me/55${x.telefone}?text=${encodeURIComponent(montarMensagem(modelo, x.nome, loja))}`}>
                        WhatsApp
                      </a>
                    )}
                  </li>
                ))}
              </ul>
              <Paginacao p={pag} rotulo="pessoas" />
            </div>
          )}
        </div>

        <div className="min-w-0" id="aniversarios-por-mes">
          <p className="rotulo-campo mb-2">Aniversários por mês do ano</p>
          <GraficoBarras barras={barras} altura={220} W={540} noEixo={inteiro}
                         rotulo="Aniversariantes por mês do ano" />
        </div>
      </div>
    </Cartao>
  );
}
