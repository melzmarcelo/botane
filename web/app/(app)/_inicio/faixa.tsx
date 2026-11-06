"use client";

import Link from "next/link";
import { useState } from "react";

import ValorQueCabe from "@/components/valor-que-cabe";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { inteiro, plural } from "@/lib/numeros";

import type { IdIndicador } from "./layout";
import type { Dia, Painel } from "./tipos";

/**
 * A faixa "Hoje": o dia inteiro numa linha, cada número uma porta.
 *
 * 🔑 **Protótipo aprovado pelo dono (29/09/2026)** — `apresentacao/inicio-prototipo.html`.
 * Antes eram três cartões de largura inteira (vendas, pedidos, mesas) mais a produção lá
 * embaixo; agora são seis colunas.
 * 🔑 **As setas continuam** (pedido de 03/09/2026): a faixa abre no dia da ÚLTIMA venda, e
 * as setas andam entre os dias que TÊM venda — quem diz para onde dá para ir é o servidor.
 * ⚠️ Só as vendas navegam: pedidos, mesas e produção são sempre de hoje.
 * ⚠️ Quem não vê valores recebe `dia` nulo, e a faixa fica com pedidos, mesas, produção e
 * etiquetas — a checagem da manhã da cozinha.
 */
const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
const SEMANA = ["domingo", "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
  "sexta-feira", "sábado"];

// ⚠️ `new Date(iso)` é meia-noite UTC — em Brasília, o dia ANTERIOR a partir das 21h. As
// contas abaixo usam a data local, e os nomes são nossos (sem depender do ICU do navegador).
function porExtenso(iso: string) {
  const [ano, mes, dia] = iso.split("-").map(Number);
  return `${String(dia).padStart(2, "0")} ${MESES[mes - 1]} ${ano}`;
}
function diaDaSemana(iso: string) {
  const [ano, mes, dia] = iso.split("-").map(Number);
  return SEMANA[new Date(ano, mes - 1, dia).getDay()];
}

function Numero({ rotulo, valor, sub, tom, href }: {
  rotulo: string; valor: string; sub?: React.ReactNode; tom?: "alerta" | "erro" | "erva"; href: string;
}) {
  const cor = tom === "alerta" ? "text-alerta" : tom === "erro" ? "text-erro" : tom === "erva" ? "text-erva" : "";
  return (
    // 🔑 Layout novo (05/11/2026): cada número é um CARTÃO de indicador, como no protótipo.
    <Link href={href} className="faixa-numero group cartao block min-w-0 px-5 py-4 no-underline transition-colors hover:border-linha2">
      <p className="text-[13px] font-semibold text-suave">{rotulo}</p>
      {/* ⚠️ A fonte acompanha a LARGURA do cartão (pedido do dono, 06/11/2026: "dependendo do
          monitor, o valor faturado e ticket médio estão estourando o quadrado"): com seis cartões
          numa linha, "R$ 12.345,67" a 26px fixos passava da borda. */}
      <ValorQueCabe maximo={26} className={`faixa-valor mono mt-2 font-extrabold leading-none tracking-[-0.02em] group-hover:text-erva ${cor}`}>{valor}</ValorQueCabe>
      {sub && <p className="mt-2 text-[12.5px] leading-snug text-suave">{sub}</p>}
    </Link>
  );
}

// A chave de cada cartão e o indicador que ela é, para a escolha de cada um (06/11/2026).
const INDICADOR: Record<string, IdIndicador> = {
  v: "vendas", f: "faturado", t: "ticket", p: "pedidos", m: "mesas", pr: "producao", e: "etiquetas",
};

/**
 * `ocultos`: os indicadores que a pessoa tirou (tela personalizada). `null` = nunca escolheu, e
 * vale a regra de sempre (etiquetas só para quem não vê dinheiro).
 */
export default function FaixaHoje({ p, ocultos = null }: { p: Painel; ocultos?: IdIndicador[] | null }) {
  const [dia, setDia] = useState<Dia | null>(p.dia);
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
  const numeros: React.ReactNode[] = [];
  // 🔑 **Os números das vendas abrem o PAINEL, naquele dia** (pedido do dono, 21/10/2026):
  // daqui se troca para semana, mês ou período. A lista de documentos continua no "ver
  // as vendas" do canto.
  const noPainel = dia ? `/vendas/painel?modo=dia&de=${dia.data}&ate=${dia.data}` : "/vendas/painel";
  if (dia) {
    const c = dia.comparacao;
    numeros.push(
      <Numero key="v" rotulo="Vendas" valor={inteiro(dia.vendas)} href={noPainel}
              sub={plural(dia.itens, "item", "itens")} />,
      <Numero key="f" rotulo="Faturado" valor={reais(dia.receita)} href={noPainel}
              sub={c && c.pct !== null
                ? <span className={c.pct >= 0 ? "text-erva" : "text-alerta"}>
                    {c.pct >= 0 ? "+" : ""}{c.pct.toLocaleString("pt-BR")}% sobre {diaDaSemana(dia.data).split("-")[0]} passada
                    {c.ate_hora ? ` (até ${c.ate_hora})` : ""}
                  </span>
                : "sem venda na semana passada para comparar"} />,
      // ⚠️ Sem venda no dia o ticket é NULO, não zero.
      <Numero key="t" rotulo="Ticket médio" valor={dia.ticket_medio === null ? "—" : reais(dia.ticket_medio)}
              href={noPainel} sub="por cupom" />,
    );
  }
  if (p.pedidos) {
    // ⚠️ O número é o que está EM ABERTO (novos + confirmados): "0 · 1 a confirmar" se lia
    // como contradição quando o número era só o "para hoje".
    numeros.push(<Numero key="p" rotulo="Pedidos em aberto" valor={inteiro(p.pedidos.abertos)} href="/pedidos/painel"
      sub={p.pedidos.novos ? <span className="text-alerta">{p.pedidos.novos} a confirmar</span>
        : p.pedidos.sem_pdv ? <span className="text-erro">{p.pedidos.sem_pdv} sem lançar no PDV</span>
        : `${p.pedidos.hoje} para hoje`} />);
  }
  if (p.reservas) {
    numeros.push(<Numero key="m" rotulo="Mesas" valor={inteiro(p.reservas.hoje)} href="/reservas/agenda?visao=dia"
      sub={<>{p.reservas.pessoas_hoje} pessoas{p.reservas.pendentes
        ? <span className="text-alerta"> · {p.reservas.pendentes} a confirmar</span> : ""}</>} />);
  }
  if (p.producao) {
    numeros.push(<Numero key="pr" rotulo="Produção" valor={inteiro(p.producao.hoje)} href="/producao"
      sub={p.producao.atrasadas ? <span className="text-erro">{plural(p.producao.atrasadas, "atrasada", "atrasadas")}</span> : "para hoje"} />);
  }
  // 🔑 As etiquetas entram na faixa de quem NÃO vê dinheiro (a cozinha): para quem vê, a
  // faixa já tem seis números, e as etiquetas estão nos alertas e em "A casa".
  // ⚠️ Quem ESCOLHEU (tela personalizada) vê as etiquetas mesmo vendo dinheiro.
  if (p.etiquetas && (ocultos ? !ocultos.includes("etiquetas") : !dia)) {
    numeros.push(<Numero key="e" rotulo="Etiquetas" valor={inteiro(p.etiquetas.vencidas)} href="/etiquetas/painel"
      tom={p.etiquetas.vencidas ? "erro" : undefined}
      sub={`vencidas · ${p.etiquetas.hoje} vencem hoje`} />);
  }
  const visiveis = numeros.filter((n) => {
    const k = (n as React.ReactElement).key;
    return !(k && ocultos?.includes(INDICADOR[String(k)]));
  });
  if (!visiveis.length) return null;

  return (
    <section aria-label="hoje">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        {dia ? (
          <div className="flex items-center gap-2">
            <button type="button" className="link-acao seta-data" aria-label="dia anterior com venda"
                    disabled={!dia.anterior || indo} onClick={() => void ir(dia.anterior)}>‹</button>
            <h2 className="text-[15px] font-bold">
              Vendas do dia{" "}
              <span className="font-normal text-suave">
                · {dia.data === hoje ? "hoje, " : ""}{diaDaSemana(dia.data)}, {porExtenso(dia.data)}
              </span>
            </h2>
            <button type="button" className="link-acao seta-data" aria-label="próximo dia com venda"
                    disabled={!dia.proximo || indo} onClick={() => void ir(dia.proximo)}>›</button>
          </div>
        ) : (
          <h2 className="text-[15px] font-bold">Hoje</h2>
        )}
        {dia && <Link href="/vendas" className="link-acao text-[13px]">ver as vendas ›</Link>}
      </div>

      <div className="faixa-hoje">{visiveis}</div>

      {dia && (dia.canceladas > 0 || (!dia.proximo && dia.data !== hoje) || erro) && (
        <p className="mt-3 text-[12.5px] text-suave">
          {/* ⚠️ A frase diz a CONTA: é o que faz a conferência com o PDV fechar. */}
          {dia.canceladas > 0 && (
            <>{plural(dia.canceladas, "cupom cancelado", "cupons cancelados")} no PDV, somando {reais(dia.valor_cancelado)} — lá
              o dia tem {inteiro(dia.vendas + dia.canceladas)} cupons. </>
          )}
          {!dia.proximo && dia.data !== hoje && "É o dia mais recente com venda importada."}
          {erro && <span className="text-erro"> {erro}</span>}
        </p>
      )}
    </section>
  );
}
