"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Campo, Cartao, Etiqueta, Vazio } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import BotaoExportar from "@/components/exportar";
import { fontePessoas, ItemBusca } from "@/lib/busca-cadastro";
import { dataBr } from "../tipos";
import Voltar from "@/components/voltar";

/**
 * O que cada pessoa consumiu, e quanto deixou de pagar.
 *
 * 🔑 **O caso do dono** (04/09/2026): "o funcionário vai comprar, lançamos e
 * depois cobramos o valor dele" — esta tela é o documento dessa cobrança. Por
 * isso mostra as DUAS colunas: o que custaria e o que está sendo cobrado. Só o
 * valor a cobrar não seria aceito por quem paga, que quer ver o benefício.
 *
 * ⚠️ **Cupom cancelado fica de fora**, e o corte é no servidor. Ele existe na
 * base para a conferência com o PDV fechar, mas cobrar alguém por um cupom
 * cancelado seria cobrar o que não foi consumido.
 */

const PESSOAS = fontePessoas();

type LinhaSintetica = {
  id_pessoa: number;
  pessoa: string;
  cupom_base: "VENDA" | "CUSTO" | null;
  cupom_desconto_pct: number | null;
  cupons: number;
  itens: number;
  total_cheio: number;
  total: number;
  desconto: number;
};

type LinhaAnalitica = {
  id_venda: number;
  data: string;
  hora: string | null;
  documento: string | null;
  id_pessoa: number;
  pessoa: string;
  produto: string | null;
  produto_codigo: string | null;
  quantidade: number;
  unitario_cheio: number;
  unitario: number;
  total_cheio: number;
  total: number;
};

type Ciclo = {
  id: number;
  nome: string | null;
  inicio: string;
  fim: string;
  status: "ABERTO" | "FECHADO";
};

type Totais = {
  periodo: Ciclo | null;
  periodos: Ciclo[];
  total_cheio: number;
  total: number;
  desconto: number;
};

/**
 * 🔑 **O ciclo se escolhe, as datas não.** O consumo se cobra por ciclo fechado,
 * e o fechamento leva tudo que estava em aberto até a data final — inclusive
 * consumo anterior ao início dele. Um par de datas aqui mostraria um conjunto
 * diferente do que foi cobrado, e esta tela É o documento da cobrança.
 */
const EM_ABERTO = "aberto";

function rotuloDoCiclo(c: Ciclo) {
  const base = c.nome || `${dataBr(c.inicio)} a ${dataBr(c.fim)}`;
  return c.status === "ABERTO" ? `${base} (ciclo aberto)` : base;
}

/**
 * ⚠️ **União discriminada, nunca `LinhaSintetica & LinhaAnalitica`.** A
 * interseção afirmava que toda linha tem os campos das DUAS formas, o que
 * nenhuma resposta cumpre: a sintética não traz `quantidade`, a analítica não
 * traz `cupons`. Com ela o TypeScript avalizava ler qualquer campo de qualquer
 * linha, e o erro só aparecia no navegador, como `NaN` numa célula.
 */
type Resposta =
  | (Totais & { detalhe: "sintetico"; linhas: LinhaSintetica[] })
  | (Totais & { detalhe: "analitico"; linhas: LinhaAnalitica[] });

/**
 * 🔑 **Cada tabela recebe SÓ a forma que sabe desenhar.** Enquanto as duas
 * moravam no mesmo `map`, escolhidas pelo filtro da tela, existia um instante em
 * que o filtro já dizia "analítico" e as linhas na mão ainda eram as sintéticas
 * — e a célula de quantidade saía `NaN`. Separadas, a forma errada nem
 * compila.
 */
function TabelaSintetica({ linhas }: { linhas: LinhaSintetica[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="tabela">
        <thead>
          <tr>
            <th>Pessoa</th>
            <th className="num">Cupons</th>
            <th className="num">Itens</th>
            <th className="num">Cheio</th>
            <th className="num">Desconto</th>
            <th className="num">A cobrar</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map((l) => (
            <tr key={l.id_pessoa}>
              <td>
                <Link href={"/fornecedores/" + l.id_pessoa} className="link-registro">
                  {l.pessoa}
                </Link>
                {l.cupom_base === "CUSTO" && (
                  <>
                    {" "}
                    <Etiqueta cor="neutro">pelo custo</Etiqueta>
                  </>
                )}
              </td>
              <td className="num tabular-nums">{l.cupons}</td>
              <td className="num tabular-nums">{l.itens}</td>
              <td className="num tabular-nums text-suave">{reais(l.total_cheio)}</td>
              <td className="num tabular-nums">{reais(l.desconto)}</td>
              <td className="num font-semibold tabular-nums">{reais(l.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TabelaAnalitica({ linhas }: { linhas: LinhaAnalitica[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="tabela">
        <thead>
          <tr>
            <th>Data</th>
            <th>Pessoa</th>
            <th>Produto</th>
            <th className="num">Qtd</th>
            <th className="num">Cheio un.</th>
            <th className="num">Cobrado un.</th>
            <th className="num">Total</th>
          </tr>
        </thead>
        <tbody>
          {linhas.map((l, n) => (
            <tr key={l.id_venda + "-" + n}>
              <td className="whitespace-nowrap">
                <Link href={"/vendas/" + l.id_venda} className="link-registro">
                  {dataBr(l.data)}
                </Link>
                {l.documento && (
                  <span className="block text-[12.5px] text-suave">{l.documento}</span>
                )}
              </td>
              <td>{l.pessoa}</td>
              <td>
                {l.produto ?? "—"}
                {l.produto_codigo && (
                  <span className="block text-[12.5px] text-suave">{l.produto_codigo}</span>
                )}
              </td>
              <td className="num tabular-nums">{Number(l.quantidade)}</td>
              <td className="num tabular-nums text-suave">{reais(l.unitario_cheio)}</td>
              <td className="num tabular-nums">{reais(l.unitario)}</td>
              <td className="num font-semibold tabular-nums">{reais(l.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PaginaConsumoPorPessoa() {
  // ⚠️ **"Em aberto" é o padrão, e é uma escolha de verdade** — é o que a casa
  // tem a receber e ainda não cobrou, a pergunta mais frequente desta tela, e o
  // único recorte possível numa loja que nunca fechou um ciclo.
  const [ciclo, setCiclo] = useState<string>(EM_ABERTO);
  const [pessoa, setPessoa] = useState<{ id: number; rotulo: string } | null>(null);
  const [detalhe, setDetalhe] = useState<"sintetico" | "analitico">("sintetico");
  const [dados, setDados] = useState<Resposta | null>(null);
  const [carregando, setCarregando] = useState(true);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      const q = new URLSearchParams({ detalhe });
      if (ciclo !== EM_ABERTO) q.set("id_periodo", ciclo);
      if (pessoa) q.set("id_pessoa", String(pessoa.id));
      setDados(await api.get<Resposta>("/vendas/por-pessoa?" + q.toString()));
    } finally {
      setCarregando(false);
    }
  }, [ciclo, detalhe, pessoa]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const linhas = dados?.linhas ?? [];
  // ⚠️ **O título também segue a RESPOSTA.** Ele contava "linha(s)" no
  // instante em que a tela ainda mostrava as pessoas do carregamento anterior.
  // O filtro só vale antes de a primeira resposta chegar, quando não há o que
  // contradizer.
  const visao = dados?.detalhe ?? detalhe;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Voltar href="/vendas">
          vendas
        </Voltar>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          Consumo por pessoa
        </h1>
        <p className="mt-1 text-suave">
          O que cada um consumiu no período, quanto custaria e quanto está sendo cobrado.
        </p>
      </header>

      {/* ⚠️ **O arquivo nasce dos MESMOS filtros da tela.** Semear o botão com o
          que está aqui é o que impede a planilha entregue ao funcionário de
          discordar do que ele viu — quem conferisse os dois acharia que um dos
          dois mente. */}
      <div className="flex flex-wrap gap-2">
        <BotaoExportar
          relatorio="consumo-pessoa"
          rotulo="Baixar"
          iniciais={{
            ciclo: [ciclo],
            pessoas: pessoa ? [pessoa.id] : [],
            detalhe: [detalhe],
          }}
        />
      </div>

      <Cartao
        titulo="Ciclo de consumo"
        descricao="Cupom cancelado não entra: não se cobra o que foi cancelado."
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <Campo rotulo="Ciclo" dica="o que ainda não foi cobrado, se não escolher">
            <select
              className="campo"
              value={ciclo}
              onChange={(e) => setCiclo(e.target.value)}
            >
              <option value={EM_ABERTO}>Em aberto — ainda não cobrado</option>
              {(dados?.periodos ?? []).map((c) => (
                <option key={c.id} value={String(c.id)}>
                  {rotuloDoCiclo(c)}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Pessoa" dica="em branco traz todas">
            <BuscaCadastro
              fonte={PESSOAS}
              selecionado={pessoa}
              aoEscolher={(item: ItemBusca | null) =>
                setPessoa(item ? { id: item.id, rotulo: rotuloDe(item) } : null)
              }
            />
          </Campo>
          <Campo rotulo="Detalhe">
            <select
              className="campo"
              value={detalhe}
              onChange={(e) => setDetalhe(e.target.value as "sintetico" | "analitico")}
            >
              <option value="sintetico">sintético — um total por pessoa</option>
              <option value="analitico">analítico — item a item</option>
            </select>
          </Campo>
        </div>
      </Cartao>

      {dados && linhas.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-3">
          <Cartao titulo="Valor cheio">
            <p className="text-[26px] font-bold tabular-nums">{reais(dados.total_cheio)}</p>
            <p className="mt-1 text-[13px] text-suave">pelo preço de venda</p>
          </Cartao>
          <Cartao titulo="Desconto">
            <p className="text-[26px] font-bold tabular-nums">{reais(dados.desconto)}</p>
            <p className="mt-1 text-[13px] text-suave">o que a política concedeu</p>
          </Cartao>
          <Cartao titulo="A cobrar">
            <p className="text-[26px] font-bold tabular-nums">{reais(dados.total)}</p>
            <p className="mt-1 text-[13px] text-suave">
              {dados.total_cheio > 0
                ? ((dados.total / dados.total_cheio) * 100).toFixed(1) + "% do cheio"
                : "—"}
            </p>
          </Cartao>
        </div>
      )}

      <Cartao
        titulo={
          visao === "sintetico" ? linhas.length + " pessoa(s)" : linhas.length + " linha(s)"
        }
      >
        {carregando ? (
          <p className="text-suave">carregando…</p>
        ) : !dados || !dados.linhas.length ? (
          <Vazio>Nenhum consumo com pessoa informada neste período.</Vazio>
        ) : dados.detalhe === "sintetico" ? (
          <TabelaSintetica linhas={dados.linhas} />
        ) : (
          <TabelaAnalitica linhas={dados.linhas} />
        )}
      </Cartao>
    </div>
  );
}
