"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { rotuloMes } from "@/app/(app)/reservas/painel/quadros";
import {
  BarrasDeitadas, CORES_PAREADAS, GraficoBarras, type Barra,
} from "@/app/(app)/vendas/painel/graficos";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Cartao, Carregando } from "@/components/ui";
import { dataCurta } from "@/lib/datas";
import { inteiro, pct, plural } from "@/lib/numeros";
import { verPainelClientes, type PainelClientes } from "@/lib/reservas";

/**
 * O painel dos clientes — quem é a base.
 *
 * 🔑 **Pedido do dono (04/11/2026):** *"uma tela com todos os indicadores que são apresentados
 * lá"* — o painel "Leads" do LeadsFood: novos contatos, contatos no ano e base; novos por mês e
 * por dia; idade por gênero; top 10 cidades; origem. A base é da REDE, como o grid de Clientes
 * (`services/clientes_painel.py`).
 * ⚠️ Enquanto a casa usar o LeadsFood, os números daqui são os da última importação mais o que
 * se cadastrou no Botané: o que entra lá não chega aqui sozinho.
 */
export default function PainelDeClientes() {
  const [p, setP] = useState<PainelClientes | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    let vivo = true;
    verPainelClientes()
      .then((r) => vivo && setP(r))
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar o painel"));
    return () => { vivo = false; };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="rotulo">Portal de Clientes · Clientes</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Painel de clientes</h1>
          <ExplicaTela>
            Quem é a base de clientes da rede: quantos são, quando se cadastraram, idade, gênero,
            cidade e de onde vieram. Quem veio do LeadsFood conta pela data em que se cadastrou lá.
          </ExplicaTela>
        </div>
        <Link href="/reservas/clientes" className="btn btn-secundario">Lista de clientes</Link>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!p ? !erro && <Carregando /> : <Quadros p={p} />}
    </div>
  );
}

function Quadros({ p }: { p: PainelClientes }) {
  const r = p.resumo;
  const numeros = [
    { n: r.base, r: "clientes na base" },
    { n: r.no_ano, r: `novos em ${p.hoje.slice(0, 4)}` },
    { n: r.no_mes, r: "novos neste mês" },
    { n: r.hoje, r: "novos hoje" },
  ];
  const porMes: Barra[] = p.por_mes.map((x) => ({
    chave: x.mes, rotulo: rotuloMes(x.mes), valor: x.n,
    titulo: `${rotuloMes(x.mes)}${x.parcial ? " (mês em andamento)" : ""}`,
    dica: [{ rotulo: "Novos clientes", valor: inteiro(x.n) }],
  }));
  const porDia: Barra[] = p.por_dia.map((x, i) => {
    const faltam = p.por_dia.length - 1 - i;
    return {
      chave: x.dia, rotulo: faltam === 0 ? "hoje" : faltam === 1 ? "ontem" : dataCurta(x.dia),
      valor: x.n, titulo: dataCurta(x.dia), dica: [{ rotulo: "Novos clientes", valor: inteiro(x.n) }],
    };
  });
  const c = p.cidades;
  const comCidade = c.top.reduce((s, x) => s + x.n, 0) + c.outras;
  const totalOrigem = p.origens.reduce((s, x) => s + x.n, 0) || 1;

  return (
    <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 [&>*]:min-w-0" id="clientes-numeros">
        {numeros.map((x) => (
          <div key={x.r} className="cartao px-3 py-3">
            <b className="mono block text-[22px] leading-none">{inteiro(x.n)}</b>
            <span className="mt-1 block text-[12px] text-suave">{x.r}</span>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-2 [&>*]:min-w-0">
        <Cartao titulo={`Novos clientes por mês (últimos ${p.por_mes.length})`}
                descricao="O último mês ainda está em andamento.">
          <div className="px-3 py-3" id="clientes-por-mes">
            <GraficoBarras barras={porMes} altura={240} W={540} noEixo={inteiro}
                           rotulo="Novos clientes por mês" />
          </div>
        </Cartao>
        <Cartao titulo={`Novos clientes por dia (últimos ${p.por_dia.length} dias)`}>
          <div className="px-3 py-3" id="clientes-por-dia">
            <GraficoBarras barras={porDia} altura={240} W={540} noEixo={inteiro} maxRotulos={7}
                           rotulo="Novos clientes por dia" />
          </div>
        </Cartao>

        <Piramide p={p} />
        <Genero p={p} />

        <Cartao titulo="As 10 cidades com mais clientes"
                descricao={`${plural(c.outras_cidades, "outra cidade soma", "outras cidades somam")} ${
                  inteiro(c.outras)} · ${inteiro(c.sem_cidade)} sem cidade`}>
          <div className="px-5 py-4" id="clientes-cidades">
            <BarrasDeitadas
              linhas={c.top.map((x) => ({
                chave: x.cidade, nome: x.cidade, valor: x.n, id: null,
                detalhe: pct(comCidade ? (x.n / comCidade) * 100 : 0, 1),
              }))}
              valor={inteiro} />
          </div>
        </Cartao>
        <Cartao titulo="De onde vieram"
                descricao="A origem gravada no LeadsFood. Quem se cadastrou aqui (site, reserva, fidelidade) é “Cadastro no Botané”.">
          <div className="px-5 py-4" id="clientes-origem">
            <BarrasDeitadas
              linhas={p.origens.map((x) => ({
                chave: x.origem, nome: x.origem, valor: x.n, id: null,
                detalhe: pct((x.n / totalOrigem) * 100, 1),
              }))}
              valor={inteiro} />
          </div>
        </Cartao>
      </div>
    </>
  );
}

/**
 * 🔑 **A pirâmide**: mulheres à esquerda, homens à direita, cada faixa em % do total com idade
 * conhecida (como a do LeadsFood). Em HTML, para a faixa no meio quebrar bem no celular.
 * ⚠️ Quem não informou gênero entra no total da faixa, mas não em nenhum dos lados.
 */
function Piramide({ p }: { p: PainelClientes }) {
  const total = p.idade.reduce((s, x) => s + x.feminino + x.masculino + x.outros, 0) || 1;
  const teto = Math.max(...p.idade.flatMap((x) => [x.feminino, x.masculino]), 1);
  const lado = (n: number, k: 0 | 1) => (
    <span className={`flex items-center gap-1.5 ${k === 0 ? "flex-row-reverse" : ""}`}>
      <span className="block h-3.5 rounded-sm"
            style={{ width: `${(n / teto) * 100}%`, minWidth: n ? 2 : 0, background: CORES_PAREADAS[k] }} />
      <span className="mono shrink-0 text-[11.5px] text-suave">{pct((n / total) * 100, 1)}</span>
    </span>
  );
  return (
    <Cartao titulo="Idade e gênero"
            descricao={`Cada faixa em % de quem tem idade informada · ${inteiro(p.sem_idade)} sem data de nascimento`}>
      <div className="px-5 py-4" id="clientes-piramide">
        <div className="mb-2 flex justify-between text-[12.5px] text-suave">
          <span className="inline-flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: CORES_PAREADAS[0] }} />Mulheres
          </span>
          <span className="inline-flex items-center gap-1.5">
            Homens<span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: CORES_PAREADAS[1] }} />
          </span>
        </div>
        <ul className="space-y-1" aria-label="Clientes por faixa de idade e gênero">
          {p.idade.map((x) => (
            <li key={x.faixa} className="grid grid-cols-[1fr_52px_1fr] items-center gap-2"
                title={`${x.faixa}: ${inteiro(x.feminino)} mulheres, ${inteiro(x.masculino)} homens${
                  x.outros ? `, ${inteiro(x.outros)} sem gênero` : ""}`}>
              {lado(x.feminino, 0)}
              <span className="mono text-center text-[12px]">{x.faixa}</span>
              {lado(x.masculino, 1)}
            </li>
          ))}
        </ul>
      </div>
    </Cartao>
  );
}

function Genero({ p }: { p: PainelClientes }) {
  const g = p.genero;
  const total = g.feminino + g.masculino + g.nao_informado || 1;
  const itens = [
    { r: "Mulheres", n: g.feminino, cor: CORES_PAREADAS[0] },
    { r: "Homens", n: g.masculino, cor: CORES_PAREADAS[1] },
    { r: "Não informado", n: g.nao_informado, cor: "var(--color-sublinhado)" },
  ];
  return (
    <Cartao titulo="Gênero">
      <div className="px-5 py-4" id="clientes-genero">
        {/* Uma barra só, inteira = a base; os números ao lado, para não depender da cor. */}
        <div className="flex h-4 overflow-hidden rounded-full" role="img"
             aria-label={itens.map((x) => `${x.r} ${pct((x.n / total) * 100, 1)}`).join(", ")}>
          {itens.map((x) => x.n > 0 && (
            <span key={x.r} style={{ width: `${(x.n / total) * 100}%`, background: x.cor }}
                  className="border-r-2 border-[var(--color-superficie)] last:border-r-0" />
          ))}
        </div>
        <ul className="mt-4 grid grid-cols-3 gap-3">
          {itens.map((x) => (
            <li key={x.r}>
              <span className="flex items-center gap-1.5 text-[12.5px] text-suave">
                <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: x.cor }} />{x.r}
              </span>
              <b className="mono mt-1 block text-[20px] leading-none">{pct((x.n / total) * 100, 1)}</b>
              <span className="text-[12px] text-suave">{inteiro(x.n)}</span>
            </li>
          ))}
        </ul>
      </div>
    </Cartao>
  );
}
