"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando } from "@/components/ui";
import { api } from "@/lib/api";
import { gravarPreferencia, lerPreferencia } from "@/lib/preferencias";
import { useSessao } from "@/lib/sessao";

import Atencao from "./_inicio/atencao";
import { ACasa, OndeOCustoPesa } from "./_inicio/custo-e-casa";
import FaixaHoje from "./_inicio/faixa";
import {
  type Bloco, CHAVE_LAYOUT, clonar, type IdBloco, type IdIndicador, larguras, type LayoutInicio, normalizar,
  PADRAO, SPAN,
} from "./_inicio/layout";
import { ListaDeMesas, ListaDePedidos, ListaDeProducao } from "./_inicio/listas";
import PeriodoAteAgora from "./_inicio/periodo";
import { BarraDePersonalizar, MolduraDoBloco } from "./_inicio/personalizar";
import { Atalhos, FaturamentoPorDia, MaisVendidos } from "./_inicio/vendas-dias";
import type { Painel } from "./_inicio/tipos";

/**
 * A tela inicial: a casa inteira num olhar.
 *
 * 🔑 **Protótipo aprovado pelo dono (29/09/2026)** e layout novo (05/11/2026,
 * `apresentacao/novo-layout/`): os indicadores do dia em cartões, o faturamento por dia ao lado do
 * que precisa de atenção, atalhos ao lado dos mais vendidos, o período, as listas do dia, o custo
 * por setor e a casa. É o PADRÃO (`_inicio/layout.ts`).
 * 🔑 **Cada um arruma a sua** (pedido do dono, 06/11/2026: *"permitir configuração no dashboard …
 * com os dados que preferir e a posição que preferir. Gravar isto por usuário"*): "Personalizar"
 * mostra, oculta, reordena e muda a largura dos quadros, e escolhe os indicadores da faixa. Grava
 * em `preferencias_usuario` (chave `painel:inicio`).
 *
 * Duas regras que continuam governando tudo:
 * 1. **Número verdadeiro ou nenhum.** Food cost sem venda importada não é 0%, é "—".
 * 2. **Cada número é uma porta** para a tela onde se age sobre ele.
 * ⚠️ Quem não vê valores recebe `dinheiro` e `dia` NULOS — o valor nem sai do servidor —, os
 * quadros de dinheiro somem e a linha se fecha sem buraco (`larguras`).
 */
function saudacao() {
  const h = new Date().getHours();
  return h < 12 ? "Bom dia" : h < 18 ? "Boa tarde" : "Boa noite";
}
const SEMANA = ["domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado"];
const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
  "setembro", "outubro", "novembro", "dezembro"];

export default function Inicio() {
  const { eu, pode } = useSessao();
  const aviso = useAviso();
  const [p, setP] = useState<Painel | null>(null);
  const [erro, setErro] = useState("");
  // O layout salvo, e o rascunho enquanto a pessoa personaliza (nada grava antes de "Salvar").
  const [layout, setLayout] = useState<LayoutInicio>(PADRAO);
  const [rascunho, setRascunho] = useState<LayoutInicio | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [arrastando, setArrastando] = useState<IdBloco | null>(null);

  useEffect(() => {
    api.get<Painel>("/inicio").then(setP)
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
    // ⚠️ Falhar ao ler o layout não pode deixar a tela vazia: fica o padrão.
    lerPreferencia<LayoutInicio>(CHAVE_LAYOUT).then((v) => v && setLayout(normalizar(v))).catch(() => {});
  }, []);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!p) return <Carregando />;

  const editando = rascunho !== null;
  const atual = rascunho ?? layout;
  const mexer = (f: (l: LayoutInicio) => void) => setRascunho((r) => {
    const n = clonar(r ?? layout);
    f(n);
    return n;
  });
  const achar = (l: LayoutInicio, id: IdBloco) => l.blocos.find((b) => b.id === id)!;
  // Põe `id` logo antes (ou logo depois) de `alvo`.
  const colocar = (l: LayoutInicio, id: IdBloco, alvo: IdBloco, depois: boolean) => {
    if (id === alvo) return;
    const [b] = l.blocos.splice(l.blocos.findIndex((x) => x.id === id), 1);
    const i = l.blocos.findIndex((x) => x.id === alvo);
    l.blocos.splice(depois ? i + 1 : i, 0, b);
  };

  async function salvar() {
    if (!rascunho) return;
    setSalvando(true);
    try {
      await gravarPreferencia(CHAVE_LAYOUT, rascunho);
      setLayout(rascunho);
      setRascunho(null);
      aviso.sucesso("Tela inicial salva.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao salvar a tela");
    } finally {
      setSalvando(false);
    }
  }

  const d = p.dinheiro;
  const o = p.operacao;
  const primeiroNome = (eu?.nome ?? "").split(" ")[0];
  const semMovimento = o.movimentos_mes === 0 && o.produtos === 0;
  const agora = new Date();
  const etiquetasHoje = p.etiquetas ? p.etiquetas.hoje : null;
  const diaDasVendas = d && p.dia ? p.dia.data : null;

  // Os indicadores que existem para ESTA pessoa, e os que ela tirou.
  const indicadoresDisponiveis: IdIndicador[] = [
    ...(diaDasVendas ? (["vendas", "faturado", "ticket"] as IdIndicador[]) : []),
    ...(p.pedidos ? (["pedidos"] as IdIndicador[]) : []),
    ...(p.reservas ? (["mesas"] as IdIndicador[]) : []),
    ...(p.producao ? (["producao"] as IdIndicador[]) : []),
    ...(p.etiquetas ? (["etiquetas"] as IdIndicador[]) : []),
  ];
  // Sem escolha salva vale a regra de sempre: etiquetas na faixa só de quem não vê dinheiro.
  const indicadoresOcultos: IdIndicador[] = atual.indicadores_ocultos ?? (diaDasVendas ? ["etiquetas"] : []);

  // Cada quadro, ou nada quando não há dado para ESTA pessoa (permissão, módulo, venda).
  const quadro = (id: IdBloco): React.ReactNode => {
    switch (id) {
      case "hoje":
        return indicadoresDisponiveis.length > 0
          ? <FaixaHoje p={p} ocultos={editando ? indicadoresOcultos : atual.indicadores_ocultos} /> : null;
      case "faturamento": return diaDasVendas ? <FaturamentoPorDia fim={diaDasVendas} /> : null;
      case "atencao": return <Atencao alertas={p.alertas} deste={p.periodo.termos.deste} />;
      case "atalhos": return <Atalhos pode={pode} />;
      case "mais_vendidos": return diaDasVendas ? <MaisVendidos fim={diaDasVendas} /> : null;
      case "periodo": return d ? <PeriodoAteAgora d={d} periodo={p.periodo} /> : null;
      case "pedidos": return p.pedidos ? <ListaDePedidos p={p.pedidos} /> : null;
      case "mesas": return p.reservas ? <ListaDeMesas r={p.reservas} /> : null;
      case "producao": return p.producao ? <ListaDeProducao p={p.producao} /> : null;
      case "custo": return d ? <OndeOCustoPesa pesos={p.pesos} periodo={p.periodo} compras={d.compras_mes} /> : null;
      case "casa": return <ACasa o={o} etiquetasHoje={etiquetasHoje} />;
    }
  };
  const conteudos = new Map<IdBloco, React.ReactNode>();
  for (const b of atual.blocos) {
    const c = quadro(b.id);
    if (c) conteudos.set(b.id, c);
  }
  const disponiveis = new Set(conteudos.keys());
  const desenhados: Bloco[] = atual.blocos.filter((b) => !b.oculto && conteudos.has(b.id));
  const spans = larguras(desenhados);

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold leading-tight tracking-[-0.02em] sm:text-[28px]">
            {saudacao()}{primeiroNome ? `, ${primeiroNome}` : ""}
          </h1>
          <p className="mt-1 text-[15px] text-suave">
            {SEMANA[agora.getDay()]}, {agora.getDate()} de {MESES[agora.getMonth()]} · período:{" "}
            <b className="text-tinta">{p.periodo.rotulo}</b>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!editando && (
            <button type="button" id="inicio-personalizar" className="btn btn-terciario"
                    onClick={() => setRascunho(clonar(layout))}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                   strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
                <rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" />
              </svg>
              Personalizar
            </button>
          )}
          {d && <Link href="/vendas/painel" className="btn btn-secundario">Painel de vendas</Link>}
          {pode("bi.estudio") && (
            <Link href="/bi" className="btn btn-primario">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
                   strokeLinecap="round" aria-hidden><path d="M12 5v14 M5 12h14" /></svg>
              Nova análise
            </Link>
          )}
        </div>
      </header>

      {editando && (
        <BarraDePersonalizar
          layout={atual} salvando={salvando} disponiveis={disponiveis}
          aoSalvar={() => void salvar()} aoCancelar={() => setRascunho(null)}
          aoRestaurar={() => setRascunho(clonar(PADRAO))}
          aoMostrar={(id) => mexer((l) => { achar(l, id).oculto = false; })}
        />
      )}

      {semMovimento && !editando && (
        <Aviso tipo="info">
          A casa ainda não tem movimento. Comece cadastrando os insumos em{" "}
          <Link href="/produtos" className="text-erva underline underline-offset-2">Produtos</Link>{" "}
          e dando entrada na primeira nota em{" "}
          <Link href="/compras" className="text-erva underline underline-offset-2">Notas de entrada</Link>.
        </Aviso>
      )}

      {/* 🔑 Uma grade só, de 12 colunas, na ordem e na largura escolhidas.
          ⚠️ `min-w-0` em cada item (auditoria de 29/10/2026): sem ele a linha `truncate` vira a
          largura mínima e a tela rola para o lado. ⚠️ items-start: cada cartão na altura do
          PRÓPRIO conteúdo. */}
      <div className="grid items-start gap-4 lg:grid-cols-12" data-grade-inicio>
        {desenhados.map((b, i) => (
          <div key={b.id} data-bloco={b.id} className={`min-w-0 ${SPAN[spans.get(b.id) ?? b.largura]}`}>
            {editando ? (
              <MolduraDoBloco
                bloco={b} primeiro={i === 0} ultimo={i === desenhados.length - 1} arrastando={arrastando}
                // Anda entre os quadros VISÍVEIS: pular por cima de um oculto pareceria clique perdido.
                aoMover={(passo) => mexer((l) => colocar(l, b.id, desenhados[i + passo].id, passo > 0))}
                aoLargura={(larg) => mexer((l) => { achar(l, b.id).largura = larg; })}
                aoOcultar={() => mexer((l) => { achar(l, b.id).oculto = true; })}
                aoArrastar={setArrastando}
                aoSoltar={(sobre) => {
                  // Solto num quadro que vinha DEPOIS, fica depois dele; num de antes, antes.
                  if (arrastando) {
                    const de = ids(desenhados).indexOf(arrastando);
                    mexer((l) => colocar(l, arrastando, sobre, de < i));
                  }
                  setArrastando(null);
                }}
                indicadores={b.id === "hoje" ? { disponiveis: indicadoresDisponiveis, ocultos: indicadoresOcultos } : undefined}
                aoIndicadores={(oc) => mexer((l) => { l.indicadores_ocultos = oc; })}
              >
                {conteudos.get(b.id)}
              </MolduraDoBloco>
            ) : conteudos.get(b.id)}
          </div>
        ))}
      </div>
      {!desenhados.length && (
        <Aviso tipo="info">Todos os quadros estão ocultos. Use “Personalizar” para mostrar algum.</Aviso>
      )}
    </div>
  );
}

const ids = (blocos: Bloco[]) => blocos.map((b) => b.id);
