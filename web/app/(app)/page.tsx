"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao } from "@/components/ui";
import VendasDoDia, { Dia } from "./vendas-do-dia";

/**
 * A tela inicial: a casa inteira num olhar.
 *
 * Duas regras que governam tudo aqui:
 *
 * 1. **Número verdadeiro ou nenhum.** Food cost sem venda importada não é 0%,
 *    é desconhecido — e aparece como "—" com o motivo ao lado. Zero ali
 *    pareceria um resultado excelente.
 * 2. **Cada número traz o que fazer com ele.** Um valor sozinho não decide
 *    nada; por isso cada cartão tem uma linha em português dizendo o que
 *    aquilo significa, e leva para a tela onde se age.
 */

type Alerta = {
  chave: string;
  severidade: "critico" | "atencao" | "aviso";
  titulo: string;
  quantidade: number;
  detalhe: string;
  acao: string;
  href: string;
};

type Painel = {
  periodo: { inicio: string; fim: string; rotulo: string };
  operacao: {
    produtos: number;
    fichas: number;
    notas_abertas: number;
    itens_a_vincular: number;
    vencendo: number;
    abaixo_minimo: number;
    movimentos_mes: number;
  };
  alertas: Alerta[];
  dinheiro: {
    estoque_agora: number;
    compras_mes: number;
    cmv_mes: number;
    perdas_mes: number;
    receita_mes: number;
    vendas: number;
    food_cost_pct: number | null;
    variancia: number | null;
    cobertura_ficha_pct: number;
    cmv_teorico: number;
  } | null;
  /** O movimento do dia da última venda — nulo para quem não vê dinheiro. */
  dia: Dia | null;
  pesos: { grupo: string; cmv: number; participacao_pct: number }[];
  /**
   * O que a cozinha DESTA pessoa tem para fazer.
   *
   * ⚠️ Nulo para quem não tem `producao.agenda` — não uma lista vazia, que se
   * leria como "não há nada para produzir".
   */
  producao: {
    linhas: {
      id: number;
      id_produto: number;
      produto: string;
      um_estoque: string | null;
      data_prevista: string;
      quantidade: number;
      setor: string | null;
      atrasada: boolean;
    }[];
    total: number;
    atrasadas: number;
    hoje: number;
    todos_setores: boolean;
    setores: string[];
  } | null;
};

function Indicador({
  rotulo,
  valor,
  nota,
  href,
  tom = "normal",
}: {
  rotulo: string;
  valor: string;
  nota: string;
  href?: string;
  tom?: "normal" | "alerta" | "erva";
}) {
  const cor =
    tom === "alerta" ? "text-erro" : tom === "erva" ? "text-erva" : "text-tinta";
  const conteudo = (
    <>
      <p className="rotulo">{rotulo}</p>
      <p className={`mono mt-1.5 text-[26px] font-bold leading-none ${cor}`}>{valor}</p>
      <p className="mt-2 text-[13px] leading-snug text-suave">{nota}</p>
    </>
  );
  return href ? (
    <Link href={href} className="cartao block p-4 no-underline transition-colors hover:border-erva">
      {conteudo}
    </Link>
  ) : (
    <div className="cartao p-4">{conteudo}</div>
  );
}

const pct = (n: number) => `${n.toFixed(1).replace(".", ",")}%`;

/**
 * "04/09" — a data da linha da agenda, curta.
 *
 * ⚠️ **Sem `new Date(iso)`**: o construtor lê `aaaa-mm-dd` como MEIA-NOITE UTC,
 * e no fuso de Brasília isso é o dia anterior às 21h. A agenda de amanhã
 * apareceria como hoje. É a mesma armadilha que `lib/datas.ts` documenta, pela
 * ponta da leitura — aqui o texto já vem pronto do servidor e só é fatiado.
 */
const diaCurto = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

export default function Inicio() {
  const { eu } = useSessao();
  const [p, setP] = useState<Painel | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api
      .get<Painel>("/inicio")
      .then(setP)
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, []);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!p) return <Carregando />;

  const d = p.dinheiro;
  const o = p.operacao;
  const primeiroNome = (eu?.nome ?? "").split(" ")[0];
  const semMovimento = o.movimentos_mes === 0 && o.produtos === 0;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">{p.periodo.rotulo}</p>
        <h1 className="mt-1 text-[26px] font-bold leading-tight tracking-tight sm:text-[32px]">
          {primeiroNome ? `Olá, ${primeiroNome}` : "Bom dia"}
        </h1>
        <p className="mt-1 max-w-[62ch] text-suave">
          O mês corrente, do jeito que está agora.
        </p>
      </header>

      {semMovimento && (
        <Aviso tipo="info">
          A casa ainda não tem movimento. Comece cadastrando os insumos em{" "}
          <Link href="/produtos" className="text-erva underline underline-offset-2">
            Produtos
          </Link>{" "}
          e dando entrada na primeira nota em{" "}
          <Link href="/compras" className="text-erva underline underline-offset-2">
            Notas de entrada
          </Link>
          .
        </Aviso>
      )}

      {/* 🔑 **O dia vem ANTES do período** (pedido do dono, 03/09/2026): o
          painel respondia pelo mês inteiro e não dizia como foi o último dia —
          que é a primeira coisa que se olha de manhã. As setas andam entre dias
          que TÊM venda; quem diz para onde dá para ir é o servidor. */}
      {p.dia && <VendasDoDia inicial={p.dia} />}

      {/* 🔑 **O que a cozinha DESTA pessoa tem para fazer** (pedido do dono,
          03/09/2026). A agenda existia só na tela dela: quem entrava de manhã
          via o painel do mês e tinha de navegar até Produção para descobrir o
          que assar hoje. E fica AQUI, acima dos números do período, porque para
          quem não vê dinheiro este é o painel inteiro — o cartão do dia e os
          indicadores vêm nulos. */}
      {p.producao && (
        <Cartao
          titulo="Para produzir"
          descricao={
            p.producao.todos_setores
              ? "O plano da casa para os próximos sete dias."
              : `O plano de ${p.producao.setores.join(", ") || "quem você cuida"} para os próximos sete dias.`
          }
          acao={
            <Link href="/producao" className="btn btn-secundario">
              Abrir a agenda
            </Link>
          }
        >
          {!p.producao.total ? (
            // ⚠️ A frase diz se o vazio é da CASA ou só do recorte da pessoa —
            // senão "nada para produzir" se lê como "a casa não produz nada".
            <p className="text-[14.5px] text-suave">
              Nada planejado para os próximos sete dias
              {p.producao.todos_setores ? "" : " nos seus setores"}.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap gap-x-6 gap-y-1 text-[13.5px]">
                <span>
                  <b className="mono">{p.producao.hoje}</b> para hoje
                </span>
                {p.producao.atrasadas > 0 && (
                  <span className="text-erro">
                    <b className="mono">{p.producao.atrasadas}</b> atrasada(s)
                  </span>
                )}
                <span className="text-suave">
                  <b className="mono">{p.producao.total}</b> no total
                </span>
              </div>
              <ul className="mt-3 flex flex-col gap-px bg-linha text-[14.5px]">
                {p.producao.linhas.map((l) => (
                  <li
                    key={l.id}
                    className="flex flex-wrap items-baseline gap-x-3 bg-superficie py-2.5"
                  >
                    <span
                      className={`mono text-[13px] ${l.atrasada ? "text-erro" : "text-suave"}`}
                    >
                      {diaCurto(l.data_prevista)}
                    </span>
                    <Link href={`/produtos/${l.id_produto}`} className="link-registro">
                      {l.produto}
                    </Link>
                    {l.setor && <span className="text-[12.5px] text-suave">{l.setor}</span>}
                    <span className="mono ml-auto font-semibold">
                      {l.quantidade.toLocaleString("pt-BR")}{" "}
                      <span className="font-normal text-suave">{l.um_estoque ?? ""}</span>
                    </span>
                  </li>
                ))}
              </ul>
              {p.producao.total > p.producao.linhas.length && (
                <p className="mt-3 text-[13px] text-suave">
                  Mostrando as {p.producao.linhas.length} primeiras — as outras estão na agenda.
                </p>
              )}
            </>
          )}
        </Cartao>
      )}

      {d && (
        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Indicador
            rotulo="Custo do que saiu"
            valor={reais(d.cmv_mes)}
            nota="O CMV do mês: estoque inicial + compras − o que sobrou."
            href="/cmv"
          />
          <Indicador
            rotulo="Food cost"
            valor={d.food_cost_pct === null ? "—" : pct(d.food_cost_pct)}
            nota={
              d.food_cost_pct === null
                ? "Sem vendas importadas no mês — sem receita não há percentual."
                : `Sobre ${reais(d.receita_mes)} de receita em ${d.vendas} venda(s).`
            }
            tom={d.food_cost_pct !== null && d.food_cost_pct > 40 ? "alerta" : "normal"}
            href="/cmv"
          />
          <Indicador
            rotulo="Parado na prateleira"
            valor={reais(d.estoque_agora)}
            nota="Quanto dinheiro está em estoque neste momento."
            href="/estoque"
          />
          <Indicador
            rotulo="Perdas do mês"
            valor={reais(d.perdas_mes)}
            nota={
              d.cmv_mes > 0
                ? `${pct((d.perdas_mes / d.cmv_mes) * 100)} do custo do mês.`
                : "Quebra, validade e cortesia apontadas."
            }
            tom={d.perdas_mes > 0 ? "alerta" : "normal"}
            href="/estoque"
          />
        </section>
      )}

      {!!p.alertas.length && (
        <Cartao
          titulo="Precisa da sua atenção"
          descricao="O que muda o número deste mês se ficar sem resposta."
        >
          <ul className="flex flex-col gap-px bg-linha">
            {p.alertas.slice(0, 5).map((a) => (
              <li key={a.chave} className="bg-superficie py-3">
                <Link href={a.href} className="flex flex-wrap items-baseline gap-x-2 no-underline">
                  <span
                    className={`mono text-[13px] font-bold ${
                      a.severidade === "critico" ? "text-erro" : "text-alerta"
                    }`}
                  >
                    {a.quantidade}
                  </span>
                  <span className="link-registro">{a.titulo}</span>
                  <span className="text-[13.5px] text-suave">— {a.acao}</span>
                </Link>
              </li>
            ))}
          </ul>
        </Cartao>
      )}

      {d && d.cobertura_ficha_pct < 80 && d.vendas > 0 && (
        <Aviso tipo="info">
          <b>{pct(d.cobertura_ficha_pct)} das vendas têm ficha técnica.</b> Enquanto essa
          cobertura não subir, a comparação entre o custo real e o previsto pelas receitas
          fica incompleta — e a diferença parece maior do que é.
        </Aviso>
      )}

      <section className="grid gap-6 lg:grid-cols-2">
        <Cartao titulo="A casa hoje" descricao="O que está cadastrado e o que está esperando.">
          <ul className="flex flex-col gap-px bg-linha text-[14.5px]">
            {[
              { rotulo: "Insumos e produtos", valor: o.produtos, href: "/produtos" },
              { rotulo: "Fichas técnicas prontas", valor: o.fichas, href: "/fichas" },
              { rotulo: "Notas esperando conferência", valor: o.notas_abertas, href: "/compras" },
              { rotulo: "Itens de nota a vincular", valor: o.itens_a_vincular, href: "/compras" },
              { rotulo: "Lotes vencendo em 7 dias", valor: o.vencendo, href: "/alertas" },
              { rotulo: "Abaixo do estoque mínimo", valor: o.abaixo_minimo, href: "/alertas" },
            ].map((l) => (
              <li key={l.rotulo} className="flex items-center justify-between bg-superficie py-2.5">
                <Link href={l.href} className="link-registro font-normal">
                  {l.rotulo}
                </Link>
                <span className={`mono font-semibold ${l.valor > 0 ? "" : "text-suave"}`}>
                  {l.valor}
                </span>
              </li>
            ))}
          </ul>
        </Cartao>

        {d && (
          <Cartao
            titulo="Onde o custo pesa"
            descricao={
              p.pesos.length
                ? "A participação de cada setor no custo do mês."
                : "Ainda não há custo apurado neste mês."
            }
          >
            {!p.pesos.length ? (
              <p className="text-[14.5px] text-suave">
                Assim que houver compra e consumo, o peso de cada setor aparece aqui.
              </p>
            ) : (
              <ul className="flex flex-col gap-3">
                {p.pesos.map((g) => (
                  <li key={g.grupo}>
                    <div className="flex items-baseline justify-between gap-3 text-[14.5px]">
                      <span className="font-semibold">{g.grupo}</span>
                      <span className="mono text-suave">{reais(g.cmv)}</span>
                    </div>
                    <div className="mt-1 h-2 w-full rounded bg-superficie2">
                      <div
                        className="h-2 rounded bg-erva"
                        style={{ width: `${Math.min(100, Math.abs(g.participacao_pct))}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-4 text-[13px] text-suave">
              Compras do mês: <b className="mono">{reais(d.compras_mes)}</b>
            </p>
          </Cartao>
        )}
      </section>
    </div>
  );
}
