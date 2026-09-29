"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Aviso, Carregando } from "@/components/ui";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";

import Atencao from "./_inicio/atencao";
import { ACasa, OndeOCustoPesa } from "./_inicio/custo-e-casa";
import FaixaHoje from "./_inicio/faixa";
import { ListaDeMesas, ListaDePedidos, ListaDeProducao } from "./_inicio/listas";
import PeriodoAteAgora from "./_inicio/periodo";
import type { Painel } from "./_inicio/tipos";

/**
 * A tela inicial: a casa inteira num olhar.
 *
 * 🔑 **Protótipo aprovado pelo dono (29/09/2026):** *"um protótipo de tela inicial mais limpa
 * e que tenha todas as informações necessárias; talvez alguns dados podem ter colunas e não a
 * linha toda"* → *"pode implementar conforme o protótipo"* (`apresentacao/inicio-prototipo.html`).
 * De cima para baixo: o DIA numa faixa; o PERÍODO ao lado do que precisa de ATENÇÃO; as três
 * listas do dia lado a lado; o custo por setor e "a casa".
 *
 * Duas regras que continuam governando tudo:
 * 1. **Número verdadeiro ou nenhum.** Food cost sem venda importada não é 0%, é "—".
 * 2. **Cada número é uma porta** para a tela onde se age sobre ele.
 * ⚠️ Quem não vê valores recebe `dinheiro` e `dia` NULOS — o valor nem sai do servidor —, e
 * a tela se rearranja sem buraco: atenção ao lado da casa.
 */
function saudacao() {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}
const SEMANA = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
  "setembro", "outubro", "novembro", "dezembro"];

export default function Inicio() {
  const { eu } = useSessao();
  const [p, setP] = useState<Painel | null>(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    api.get<Painel>("/inicio").then(setP)
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
  }, []);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!p) return <Carregando />;

  const d = p.dinheiro;
  const o = p.operacao;
  const primeiroNome = (eu?.nome ?? "").split(" ")[0];
  const semMovimento = o.movimentos_mes === 0 && o.produtos === 0;
  const agora = new Date();
  const listas = [
    p.pedidos && <ListaDePedidos key="p" p={p.pedidos} />,
    p.reservas && <ListaDeMesas key="m" r={p.reservas} />,
    p.producao && <ListaDeProducao key="pr" p={p.producao} />,
  ].filter(Boolean);
  const etiquetasHoje = p.etiquetas ? p.etiquetas.hoje : null;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h1 className="text-[24px] font-bold leading-tight tracking-tight sm:text-[28px]">
          {saudacao()}{primeiroNome ? `, ${primeiroNome}` : ""}
        </h1>
        <p className="text-[13.5px] text-suave">
          {SEMANA[agora.getDay()]}, {agora.getDate()} de {MESES[agora.getMonth()]} · período:{" "}
          <b className="text-tinta">{p.periodo.rotulo}</b>
        </p>
      </header>

      {semMovimento && (
        <Aviso tipo="info">
          A casa ainda não tem movimento. Comece cadastrando os insumos em{" "}
          <Link href="/produtos" className="text-erva underline underline-offset-2">Produtos</Link>{" "}
          e dando entrada na primeira nota em{" "}
          <Link href="/compras" className="text-erva underline underline-offset-2">Notas de entrada</Link>.
        </Aviso>
      )}

      <FaixaHoje p={p} />

      {/* O período ao lado do que precisa de atenção. ⚠️ No celular (uma coluna) a atenção
          vem PRIMEIRO: é o que pede ação. Sem dinheiro, a atenção divide a linha com a casa. */}
      <div className="grid gap-4 lg:grid-cols-12">
        {d && (
          <div className="order-2 lg:order-none lg:col-span-8">
            <PeriodoAteAgora d={d} periodo={p.periodo} />
          </div>
        )}
        <div className={`order-1 lg:order-none ${d ? "lg:col-span-4" : "lg:col-span-6"}`}>
          <Atencao alertas={p.alertas} deste={p.periodo.termos.deste} />
        </div>
        {!d && (
          <div className="order-3 lg:col-span-6">
            <ACasa o={o} etiquetasHoje={etiquetasHoje} />
          </div>
        )}
      </div>

      {listas.length > 0 && (
        <div className={`grid gap-4 ${listas.length === 3 ? "lg:grid-cols-3" : listas.length === 2 ? "lg:grid-cols-2" : ""}`}>
          {listas}
        </div>
      )}

      {d && (
        <div className="grid gap-4 lg:grid-cols-12">
          <div className="lg:col-span-8">
            <OndeOCustoPesa pesos={p.pesos} periodo={p.periodo} compras={d.compras_mes} />
          </div>
          <div className="lg:col-span-4">
            <ACasa o={o} etiquetasHoje={etiquetasHoje} />
          </div>
        </div>
      )}
    </div>
  );
}
