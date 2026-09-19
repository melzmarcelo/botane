"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hoje } from "@/lib/datas";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { nomeTipo, reais } from "@/lib/cadastros";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import CabecalhoTela from "@/components/cabecalho-tela";
import RelatoriosDono from "./relatorios-dono";
import Movimentacao from "./movimentacao";
import Cascata from "./cascata";
import Quebra, { EIXOS, type Eixo } from "./quebra";
import MemoriaDeCalculo from "./memoria";

import { pct, qtd } from "@/lib/numeros";
type Apuracao = {
  inicio: string;
  fim: string;
  estoque_inicial: number;
  compras: number;
  estoque_final: number;
  cmv_real: number;
  cmv_teorico: number;
  variancia: number;
  variancia_pct: number | null;
  perdas: number;
  consumo_interno: number;
  ajustes: number;
  receita: number;
  vendas: number;
  itens_sem_custo: number;
  itens_com_custo?: number;
  /** A receita que TEM ficha, em reais — o numerador da cobertura. */
  receita_com_custo?: number;
  cobertura_ficha_pct: number;
  food_cost_pct: number | null;
  fechado: boolean;
  ciclo: string;
  rotulo: string | null;
  /** 🔑 As palavras com que a tela se refere ao período desta loja — mês,
   *  semana ou dia, já com a preposição contraída. Vêm do servidor pelo mesmo
   *  motivo do `rotulo`: ele é o único que sabe qual é o ciclo, e remontar a
   *  frase aqui daria duas versões da mesma verdade. */
  termos?: { o: string; do: string; deste: string; neste: string };
  grupos?: {
    nome: string;
    cmv: number;
    compras: number;
    produtos: number;
    tipos: string[];
    considerar_no_cmv: boolean;
  }[];
  tipos_fora_do_cmv?: string[];
};

type LinhaAbc = {
  id_produto: number;
  codigo: string;
  produto: string;
  quantidade: number;
  valor: number;
  participacao_pct: number;
  acumulada_pct: number;
  classe: string;
};

type LinhaMargem = {
  id_produto: number | null;
  produto: string;
  quantidade: number;
  receita: number;
  custo: number;
  margem: number;
  margem_pct: number | null;
  food_cost_pct: number | null;
  sem_custo: boolean;
};

type Periodo = {
  inicio: string;
  fim: string;
  rotulo: string;
  corrente: boolean;
  status: string | null;
  fechavel: boolean;
};

type Ciclo = { ciclo: string; descricao: string; periodos: Periodo[] };

type Fechamento = {
  id: number;
  competencia: string;
  inicio: string;
  fim: string;
  rotulo: string | null;
  ciclo: string;
  cmv_real: number;
  cmv_teorico: number;
  variancia: number;
  receita: number;
  food_cost_pct: number | null;
  status: string;
  fechado_por: string | null;
};


export default function PaginaCmv() {
  const aviso = useAviso();
  const { pode } = useSessao();
  // ⚠️ **Quem diz qual é o período é o servidor.** A casa pode fechar por dia,
  // por semana ou por mês, e a semana que fecha na quarta não se calcula com
  // `primeiroDiaDoMes()`. Enquanto o ciclo não chega, as datas ficam vazias e a
  // apuração não é pedida — um flash com o mês do calendário numa casa que
  // fecha por semana já seria um número errado na tela.
  const [inicio, setInicio] = useState("");
  const [fim, setFim] = useState("");
  const [ciclo, setCiclo] = useState<Ciclo | null>(null);
  const [a, setA] = useState<Apuracao | null>(null);
  const [abc, setAbc] = useState<LinhaAbc[] | null>(null);
  const [margem, setMargem] = useState<LinhaMargem[] | null>(null);
  const [fechamentos, setFechamentos] = useState<Fechamento[]>([]);
  // Fechar e reabrir mês são as duas ações que mudam o que já foi contado ao
  // dono — as duas perguntam antes.
  const [confirmando, setConfirmando] = useState<
    { tipo: "fechar" } | { tipo: "reabrir"; id: number; competencia: string } | null
  >(null);
  /**
   * 🔑 **As abas do painel** (16/09/2026, protótipo aprovado pelo dono). Eram
   * quatro listas empilhadas sob os ladrilhos; passam a ser sete perguntas, e a
   * primeira é **a conta** — que antes só existia como tabela no meio da tela e
   * pedia que a subtração se montasse na cabeça de quem lê.
   */
  const [aba, setAba] = useState<
    "conta" | "quebra" | "abc" | "margem" | "movimentacao" | "precos" | "memoria"
  >("conta");
  /**
   * 🔑 **O RECORTE** — *"podendo ter a opção de ser pela empresa, por loja, por
   * local de estoque, setor, categoria, produto"*. `escopo` diz QUAIS lojas
   * entram na conta; `eixo` diz como a aba Quebra a fatia. São perguntas
   * diferentes: dá para ver a empresa inteira quebrada por setor.
   */
  const [escopo, setEscopo] = useState<"loja" | "empresa">("loja");
  const [eixo, setEixo] = useState<Eixo>("setor");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  // O ciclo é pedido uma vez: ele muda na tela de Lojas, não aqui.
  useEffect(() => {
    api
      .get<Ciclo>("/cmv/periodos?quantos=12")
      .then((c) => {
        setCiclo(c);
        const atual = c.periodos.find((p) => p.corrente) ?? c.periodos[0];
        if (atual) {
          setInicio(atual.inicio);
          // O período corrente ainda não acabou: mostrar até hoje, não até o
          // fim que ainda vai acontecer.
          setFim(atual.fim > hoje() ? hoje() : atual.fim);
        }
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, []);

  const carregar = useCallback(async () => {
    if (!inicio || !fim) return;
    const q = `inicio=${inicio}&fim=${fim}`;
    try {
      const [ap, cur, mar, fec] = await Promise.all([
        api.get<Apuracao>(`/cmv/apuracao?${q}&escopo=${escopo}`),
        api.get<LinhaAbc[]>(`/cmv/abc?${q}&limite=30`),
        api.get<LinhaMargem[]>(`/cmv/margem?${q}&limite=30`),
        api.get<Fechamento[]>("/cmv/fechamentos"),
      ]);
      setA(ap);
      setAbc(cur);
      setMargem(mar);
      setFechamentos(fec);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [inicio, fim, escopo]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function fechar() {
    setOcupado(true);
    setErro("");
    try {
      const r = await api.post<{ rotulo: string; variancia: number }>("/cmv/fechamentos", {
        competencia: inicio,
      });
      aviso.sucesso(
        `Período de ${r.rotulo} fechado. A partir de agora, lançamento com data dentro dele exige permissão de retroativo.`,
      );
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível fechar");
    } finally {
      setOcupado(false);
    }
  }

  async function reabrir(id: number) {
    setErro("");
    try {
      await api.post(`/cmv/fechamentos/${id}/reabrir`);
      aviso.sucesso("Período reaberto — e isso ficou registrado na auditoria.");
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reabrir");
    }
  }

  const variânciaAlta = a && a.cmv_teorico > 0 && Math.abs(a.variancia_pct ?? 0) > 5;
  /** Abaixo disto o CMV teórico — e a variância com ele — medem o cadastro. */
  const pobreDeFicha = !!a && a.receita > 0 && a.cobertura_ficha_pct < 95;

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="CMV"
        titulo={<>Painel de CMV</>}
        explica={
          <>
            O real vem do estoque; o teórico, das fichas técnicas com as vendas do período. A
            diferença entre os dois é o número que vale olhar todo dia.
          </>
        }
        acoes={
          /* 🔑 **No cabeçalho só o RECORTE** (pedido do dono, 16/09/2026:
             primeiro *"os filtros e botão do cabeçalho estão misturados,
             podendo haver confusão"*, depois *"retirar o baixar e o imprimir
             tela do cabeçalho"*). A primeira volta separou os dois grupos com
             um traço; a segunda tirou os botões daqui de vez. Baixar virou
             **um** botão, na barra das abas, porque o que ele baixa depende da
             aba — e um botão longe do que ele baixa se clica sem saber o que
             vem.
             ⚠️ **"Imprimir a tela" saiu, o recurso não**: `Ctrl+P` continua
             imprimindo o painel com os cartões e os gráficos, e as regras de
             `@media print` continuam em `globals.css`. O que sumiu foi o botão
             que duplicava o atalho do navegador ao lado de um "Baixar" que faz
             outra coisa. */
          <div className="nao-imprimir flex flex-wrap items-end gap-2">
            {/* 🔑 **Só os períodos do CMV, sem data solta** (pedido do dono,
                16/09/2026: *"colocar como filtro de período somente os
                períodos do CMV, não os de data inicial e final"*).
                ⚠️ **Data digitada à mão é onde o engano entra**: "17/08 a
                23/08" com um dia a mais e a apuração deixa de bater com o
                fechamento — e ninguém percebe, porque o número continua
                saindo. O ciclo da loja (mensal, semanal ou diário) é o único
                recorte em que a conta fecha com o que foi fechado.
                ⚠️ **O período em curso é truncado em HOJE**, então o `fim` do
                estado não é o `fim` do período: o seletor casa pelo INÍCIO,
                que é a chave de verdade. Casando pelos dois, o período
                corrente nunca aparecia escolhido. */}
            {ciclo && ciclo.periodos.length > 0 && (
              <label>
                <span className="rotulo-campo">Período</span>
                <span className="mt-1.5 block w-[232px]">
                  <select
                    className="campo"
                    value={ciclo.periodos.find((p) => p.inicio === inicio)?.inicio ?? ""}
                    onChange={(e) => {
                      const p = ciclo.periodos.find((x) => x.inicio === e.target.value);
                      if (!p) return;
                      setInicio(p.inicio);
                      setFim(p.fim > hoje() ? hoje() : p.fim);
                    }}
                  >
                    {ciclo.periodos.map((p) => (
                      <option key={p.inicio} value={p.inicio}>
                        {p.rotulo}
                        {p.corrente
                          ? " (em curso)"
                          : p.status === "FECHADO"
                            ? " · fechado"
                            : ""}
                      </option>
                    ))}
                  </select>
                </span>
              </label>
            )}
            {/* 🔑 **O ESCOPO** (16/09/2026, protótipo aprovado): a apuração é por
                LOJA e está certo — quem opera opera numa de cada vez. Mas quem
                responde pelas duas precisava trocar de loja no seletor e somar de
                cabeça. ⚠️ Empresa é o que o USUÁRIO enxerga: quem tem uma loja só
                continua vendo uma loja, e o escopo amplia até o limite da
                permissão, nunca além dele. */}
            <label>
              <span className="rotulo-campo">Escopo</span>
              <span className="mt-1.5 block w-[152px]">
                <select
                  className="campo"
                  value={escopo}
                  onChange={(e) => setEscopo(e.target.value as "loja" | "empresa")}
                >
                  <option value="loja">Esta loja</option>
                  <option value="empresa">Empresa inteira</option>
                </select>
              </span>
            </label>
            {/* 🔑 **Ver por**: o eixo da aba Quebra. Fica aqui em cima, e não
                dentro dela, porque é decisão de RECORTE — a mesma família do
                período e do escopo. */}
            <label>
              <span className="rotulo-campo">Ver por</span>
              <span className="mt-1.5 block w-[160px]">
                <select
                  className="campo"
                  value={eixo}
                  onChange={(e) => {
                    setEixo(e.target.value as Eixo);
                    setAba("quebra");
                  }}
                >
                  {(Object.keys(EIXOS) as Eixo[]).map((x) => (
                    <option key={x} value={x}>
                      {EIXOS[x]}
                    </option>
                  ))}
                </select>
              </span>
            </label>
          </div>
        }
      />

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {!a ? (
        <Carregando />
      ) : (
        <>
          {/* 🔑 **A CONFIANÇA do número vem ANTES do número** (16/09/2026,
              protótipo aprovado). Com 28% de cobertura de ficha, a variância de
              235% desta base não é notícia sobre a cozinha — é sobre o cadastro:
              o teórico compara a fatia que tem ficha contra o CMV inteiro. O
              painel mostrava o número grande e calava sobre isso.
              ⚠️ Fica ACIMA dos ladrilhos, não abaixo: quem lê o número já leu. */}
          {/* ⚠️ `info` É o amarelo da casa: `.aviso-info` usa `--color-alerta`.
              Ver `globals.css` — o nome ficou do começo e a cor é a certa. */}
          {pobreDeFicha && (
            <Aviso tipo="info">
              <b>O CMV teórico deste período não é confiável.</b> Só{" "}
              {pct(a.cobertura_ficha_pct)} da receita tem ficha técnica —{" "}
              <b className="mono">{a.itens_sem_custo}</b> itens vendidos não sabem o próprio
              custo e entram na conta valendo zero
              {a.receita_com_custo != null && (
                <>
                  {" "}
                  ({reais(a.receita_com_custo)} dos {reais(a.receita)} vendidos)
                </>
              )}
              . Por isso a variância aparece em {pct(a.variancia_pct)}: ela está medindo o
              cadastro, não a cozinha.{" "}
              <Link href="/vendas" className="underline">
                ver os itens sem custo
              </Link>
            </Aviso>
          )}

          <div className="grid gap-px overflow-hidden rounded border border-linha bg-linha sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                r: "CMV real", selo: "do razão", v: reais(a.cmv_real),
                d: "o que saiu do estoque: comprado, contado e baixado",
                cor: "text-erva",
              },
              {
                r: "Receita", v: reais(a.receita),
                d: `${a.vendas} venda(s) no período`,
              },
              {
                r: "Food cost", v: pct(a.food_cost_pct),
                d: `CMV real ÷ receita${escopo === "empresa" ? " · empresa inteira" : ""}`,
              },
              // ⚠️ O teórico leva o SELO da cobertura: sem ele, ele compete de
              // igual para igual com o real, e não é a mesma coisa.
              // ⚠️ **A variância perdeu o ladrilho e virou a LEGENDA do teórico**
              // (16/09/2026, protótipo aprovado). Sozinha ela competia de igual
              // com o CMV real, e ela não é um número: é a RELAÇÃO entre dois —
              // fora do lugar onde essa relação nasce, ninguém sabe do que ela
              // é diferença. O ladrilho vago virou Receita, que faltava.
              {
                r: "CMV teórico",
                selo: pobreDeFicha ? `${pct(a.cobertura_ficha_pct)} de ficha` : undefined,
                v: reais(a.cmv_teorico),
                d: "o que as fichas dizem que deveria ter saído",
                extra: `Variância: ${reais(a.variancia)} (${pct(a.variancia_pct)})`,
                cor: pobreDeFicha ? "text-alerta" : undefined,
              },
            ].map((c) => (
              <div key={c.r} className="bg-superficie p-4">
                <p className="rotulo flex items-center justify-between gap-2">
                  {c.r}
                  {c.selo && <Etiqueta cor="alerta">{c.selo}</Etiqueta>}
                </p>
                <p className={`mono mt-1 text-[24px] ${c.cor ?? ""}`}>{c.v}</p>
                <p className="mt-0.5 text-[12.5px] leading-snug text-suave">{c.d}</p>
                {c.extra && (
                  <p className="mono mt-1 text-[12.5px] leading-snug text-suave">{c.extra}</p>
                )}
              </div>
            ))}
          </div>

          {/* ⚠️ A variância só vira aviso quando o teórico MERECE confiança:
              com meia cozinha sem ficha, dizer "saiu 15 mil a mais" é acusar o
              estoque de um buraco que está no cadastro. */}
          {variânciaAlta && !pobreDeFicha && (
            <Aviso tipo={a.variancia > 0 ? "erro" : "info"}>
              {a.variancia > 0
                ? `Saiu ${reais(a.variancia)} a mais do estoque do que as receitas justificam. Olhe perdas (${reais(a.perdas)}), porção fora do padrão e desvio.`
                : `O estoque consumiu ${reais(Math.abs(a.variancia))} a menos que o teórico — costuma ser prato vendido sem ficha ou ficha exagerada.`}
            </Aviso>
          )}

          {/* ⚠️ O aviso vem ANTES da conta, não depois: quem compara o CMV
              deste mês com o do mês passado precisa saber que a régua mudou. */}
          {(a.tipos_fora_do_cmv?.length ?? 0) > 0 && (
            <Aviso tipo="info">
              {(a.grupos ?? [])
                .filter((g) => !g.considerar_no_cmv)
                .map((g) => g.nome)
                .join(", ") || "Um grupo"}{" "}
              está <b>fora do CMV real</b>: o custo de{" "}
              {(a.tipos_fora_do_cmv ?? []).map(nomeTipo).join(", ").toLowerCase()} não entra na
              conta abaixo nem no food cost. Ele continua à vista, em linha própria — quem
              quiser somá-lo, soma.{" "}
              <Link href="/cadastros?aba=grupos-cmv" className="underline">
                mudar isso
              </Link>
            </Aviso>
          )}


          {/* 🔑 **Sete perguntas, não quatro listas** (16/09/2026, protótipo
              aprovado). A primeira é A CONTA — ela existia como tabela no meio
              da tela e pedia que a subtração se montasse na cabeça de quem lê.
              ⚠️ A ordem é a da leitura: primeiro o total, depois onde ele pesa,
              depois o detalhe, e por último a prova. */}
          <nav className="flex flex-wrap gap-1 border-b border-linha" role="tablist">
            {([
              ["conta", "A conta"],
              ["quebra", `Quebra por ${EIXOS[eixo]}`],
              ["abc", "Curva ABC"],
              ["margem", "Margem por prato"],
              ["movimentacao", "Movimentação"],
              ["precos", "O que subiu de preço"],
              ["memoria", "Memória de cálculo"],
            ] as const).map(([x, texto]) => (
              <button
                key={x}
                role="tab"
                aria-selected={aba === x}
                onClick={() => setAba(x)}
                className={`-mb-px min-h-[44px] border-b-2 px-3 py-2 text-[14.5px] ${
                  aba === x
                    ? "border-erva font-semibold text-erva"
                    : "border-transparent text-suave hover:text-tinta"
                }`}
              >
                {texto}
              </button>
            ))}
            {/* 🔑 **UM botão de baixar, e ele leva a conta MAIS a aba**
                (pedido do dono, 16/09/2026: *"alterar o baixar esta tabela para
                um botão de baixar... este deve baixar os números do CMV, abaixo
                do cabeçalho, e os dados da aba posicionada"*).
                Eram cinco: um no cabeçalho, um por aba como link discreto, e
                mais um dentro da memória — cada um dando um arquivo diferente,
                nenhum com a conta do CMV junto. Quem baixava a curva ABC
                recebia a curva ABC solta, sem o número que ela explica.
                ⚠️ **O relatório é sempre `cmv`; o que muda é o filtro `aba`.**
                Um relatório por aba seria a mesma conta escrita sete vezes, e
                bastaria corrigir uma para as outras mentirem.
                ⚠️ **A aba vai com o EIXO junto** quando é a quebra: "quebra" sem
                dizer por quê não identifica quadro nenhum, e o arquivo sairia
                num eixo que a pessoa não escolheu.
                ⚠️ Botão de verdade, não `link-acao`: ele TIRA a tela de dentro
                do sistema, e isso não é um link de navegação. */}
            <span className="nao-imprimir ml-auto self-center">
              <BotaoExportar
                relatorio="cmv"
                rotulo="Baixar"
                iniciais={{ inicio, fim, aba: aba === "quebra" ? `quebra-${eixo}` : aba }}
              />
            </span>
          </nav>

          {aba === "conta" && (
            <Cartao
              titulo="Como se chega ao CMV"
              descricao="Estoque inicial + compras − estoque final. Cada barra parte de onde a anterior terminou."
            >
              <Cascata
                inicial={a.estoque_inicial}
                compras={a.compras}
                final={a.estoque_final}
                cmv={a.cmv_real}
                receita={a.receita}
              />
            </Cartao>
          )}

          {aba === "conta" && (
          <Cartao
            titulo="O que explica o CMV"
            descricao="A conta aberta, para conferir de onde cada real veio."
            acao={
              a.fechado ? (
                <Etiqueta cor="erva">período fechado</Etiqueta>
              ) : pode("cmv.fechamento") ? (
                <button
                  className="btn btn-secundario"
                  onClick={() => setConfirmando({ tipo: "fechar" })}
                  aria-busy={ocupado} disabled={ocupado}
                >
                  Fechar {a.rotulo ? `— ${a.rotulo}` : "o período"}
                </button>
              ) : undefined
            }
          >
            <div className="overflow-x-auto">
              <table className="tabela">
                <tbody>
                  {[
                    ["Estoque inicial", a.estoque_inicial, "o que havia no começo"],
                    ["+ Compras", a.compras, "entradas por nota e manuais"],
                    ["− Estoque final", -a.estoque_final, "o que sobrou no fim"],
                    ["= CMV real", a.cmv_real, "o que de fato saiu", true],
                    ["Perdas", a.perdas, "quebra, validade, cortesia — dentro do CMV real"],
                    ["Consumo interno", a.consumo_interno, "equipe e degustação"],
                    ["Ajustes de inventário", a.ajustes, "diferença apurada na contagem"],
                    // ⚠️ **Duas naturezas de linha de grupo.** A que está
                    // DENTRO explica o CMV real, como Perdas: o custo já está
                    // no total, e a linha diz quanto do total é aquilo. A que
                    // está FORA mostra um valor que NÃO está no total — foi
                    // tirado do estoque inicial, das compras e do final. Sem a
                    // frase dizendo qual é qual, a conta parece não fechar.
                    ...(a.grupos ?? []).map((g) => [
                      g.nome,
                      g.cmv,
                      `${g.tipos.map(nomeTipo).join(" e ")} — ${
                        g.considerar_no_cmv ? "dentro do CMV real" : "FORA do CMV real"
                      }`,
                    ] as [string, number, string]),
                  ].map(([rotulo, valor, ajuda, forte]) => (
                    <tr key={String(rotulo)}>
                      <td className={forte ? "font-bold" : ""}>{rotulo}</td>
                      <td className="text-[13px] text-suave">{ajuda}</td>
                      <td className={`num ${forte ? "font-bold" : ""}`}>
                        {reais(Number(valor))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[13px] text-suave">
              {a.vendas} venda(s) no período
              {a.itens_sem_custo > 0 && ` · ${a.itens_sem_custo} item(ns) vendido(s) sem custo conhecido`}
            </p>
          </Cartao>
          )}

          {aba === "quebra" && (
            <Quebra
              inicio={inicio}
              fim={fim}
              eixo={eixo}
              escopo={escopo}
              cmvDoPeriodo={a.cmv_real}
            />
          )}

          {aba === "movimentacao" && <Movimentacao inicio={inicio} fim={fim} />}

          {aba === "precos" && <RelatoriosDono inicio={inicio} fim={fim} />}

          {aba === "memoria" && <MemoriaDeCalculo inicio={inicio} fim={fim} />}

          {aba === "abc" && (
            <Cartao
              titulo="Onde o dinheiro foi parar"
              descricao={`Classe A = os 80% do valor consumido. É neles que negociar preço muda ${a?.termos?.o ?? "o período"}.`}
            >
              {!abc ? (
                <Carregando />
              ) : !abc.length ? (
                <Vazio>Nenhum consumo no período.</Vazio>
              ) : (
                <div className="overflow-x-auto">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Insumo</th>
                        <th className="num">Consumo</th>
                        <th className="num">Valor</th>
                        <th className="num">Participação</th>
                        <th className="num">Acumulado</th>
                        <th>Classe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {abc.map((l) => (
                        <tr key={l.id_produto}>
                          <td>
                            <span className="font-semibold">{l.produto}</span>
                            <span className="mono ml-2 text-[12px] text-suave">{l.codigo}</span>
                          </td>
                          <td className="num text-suave">
                            {qtd(l.quantidade)}
                          </td>
                          <td className="num font-semibold">{reais(l.valor)}</td>
                          <td className="num">{pct(l.participacao_pct)}</td>
                          <td className="num text-suave">{pct(l.acumulada_pct)}</td>
                          <td>
                            <Etiqueta cor={l.classe === "A" ? "erva" : l.classe === "B" ? "alerta" : "neutro"}>
                              {l.classe}
                            </Etiqueta>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Cartao>
          )}

          {aba === "margem" && (
            <Cartao
              titulo="O que cada prato deixa"
              descricao="Receita menos o custo da ficha. É a base da engenharia de cardápio."
            >
              {!margem ? (
                <Carregando />
              ) : !margem.length ? (
                <Vazio>Nenhuma venda no período.</Vazio>
              ) : (
                <div className="overflow-x-auto">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Prato</th>
                        <th className="num">Vendidos</th>
                        <th className="num">Receita</th>
                        <th className="num">Custo</th>
                        <th className="num">Margem</th>
                        <th className="num">Food cost</th>
                      </tr>
                    </thead>
                    <tbody>
                      {margem.map((l, i) => (
                        <tr key={l.id_produto ?? `sem-${i}`}>
                          <td>
                            <span className="font-semibold">{l.produto}</span>
                            {l.sem_custo && (
                              <span className="ml-2">
                                <Etiqueta cor="alerta">sem custo</Etiqueta>
                              </span>
                            )}
                          </td>
                          <td className="num text-suave">
                            {qtd(l.quantidade)}
                          </td>
                          <td className="num">{reais(l.receita)}</td>
                          <td className="num">{reais(l.custo)}</td>
                          <td className="num font-semibold">{reais(l.margem)}</td>
                          <td
                            className={`num ${
                              (l.food_cost_pct ?? 0) > 40 ? "text-erro" : "text-suave"
                            }`}
                          >
                            {pct(l.food_cost_pct)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Cartao>
          )}

          <Cartao
            titulo="Períodos fechados"
            descricao="Fechar congela o período: depois disso, lançar com data de trás exige permissão."
          >
            {!fechamentos.length ? (
              <Vazio>Nenhum período fechado ainda.</Vazio>
            ) : (
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Período</th>
                      <th className="num">CMV real</th>
                      <th className="num">Teórico</th>
                      <th className="num">Variância</th>
                      <th className="num">Food cost</th>
                      <th>Situação</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {fechamentos.map((f) => (
                      <tr key={f.id}>
                        {/* ⚠️ O nome do período vem do servidor. Ele é o único
                            que sabe se "01/08" é o mês de agosto ou a semana que
                            começou nele — a coluna `ciclo` é quem responde, e
                            remontar a frase aqui daria duas versões da mesma
                            verdade. */}
                        <td>{f.rotulo ?? `${f.inicio} a ${f.fim}`}</td>
                        <td className="num">{reais(f.cmv_real)}</td>
                        <td className="num">{reais(f.cmv_teorico)}</td>
                        <td className={`num ${f.variancia > 0 ? "text-erro" : "text-erva"}`}>
                          {reais(f.variancia)}
                        </td>
                        <td className="num">{pct(f.food_cost_pct)}</td>
                        <td>
                          <Etiqueta cor={f.status === "FECHADO" ? "erva" : "alerta"}>
                            {f.status.toLowerCase()}
                          </Etiqueta>
                        </td>
                        <td className="text-right">
                          {f.status === "FECHADO" && pode("cmv.reabrir") && (
                            <button
                              className="link-acao link-acao-erro"
                              onClick={() =>
                                setConfirmando({ tipo: "reabrir", id: f.id,
                                                 competencia: f.rotulo ?? f.competencia })
                              }
                            >
                              reabrir
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Cartao>
        </>
      )}

      {confirmando?.tipo === "fechar" && (
        <Confirmacao
          titulo="Fechar o período"
          rotuloConfirmar="Fechar"
          ocupado={ocupado}
          aoCancelar={() => setConfirmando(null)}
          aoConfirmar={() => {
            setConfirmando(null);
            void fechar();
          }}
        >
          <p>
            Fechar a apuração de <b>{a?.rotulo ?? `${inicio} a ${fim}`}</b> e congelar os
            números?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            A movimentação por produto é congelada junto, e movimento com data dentro do
            período passa a ser recusado — só quem tem a permissão de lançamento retroativo
            passa.
          </p>
        </Confirmacao>
      )}

      {confirmando?.tipo === "reabrir" && (
        <Confirmacao
          titulo="Reabrir o período"
          rotuloConfirmar="Reabrir"
          perigo
          ocupado={ocupado}
          aoCancelar={() => setConfirmando(null)}
          aoConfirmar={() => {
            const alvo = confirmando;
            setConfirmando(null);
            void reabrir(alvo.id);
          }}
        >
          <p>
            Reabrir o período de <b>{confirmando.competencia}</b>?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            O período volta a aceitar lançamento retroativo — e o número que já foi levado ao
            dono pode mudar. Fechar de novo recalcula tudo.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
