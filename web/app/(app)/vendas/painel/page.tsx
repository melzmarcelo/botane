"use client";

import { useEffect, useState } from "react";

import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import {
  pedirCategorias, pedirPainel, pedirSetores,
  type Agrupar, type Opcao, type Ordem, type PainelVendas,
} from "@/lib/vendas-painel";

import { andar, janela, MODOS, nomeDoRecorte, type Modo } from "./periodo";
import { DiaDaSemana, Evolucao, Grupos, PorHora, Produtos, Resumo } from "./quadros";

/**
 * O painel de vendas — o estudo do período (pedido do dono, 21/10/2026).
 *
 * 🔑 **Chega-se aqui pela faixa da tela inicial**: clicar em Vendas, Faturado ou
 * Ticket abre o painel NAQUELE dia. Daqui se troca para semana, mês ou um período
 * livre, e as setas andam um passo do tamanho do recorte.
 * 🔑 **Tudo na URL** (`useEstadoNaUrl`): voltar de um produto devolve o mesmo recorte,
 * e o painel filtrado vira um link que se manda para alguém.
 * 🔑 **O botão Baixar leva o MESMO recorte** — a conta do arquivo é a mesma da tela.
 * ⚠️ Sem data na URL, o servidor escolhe o dia da ÚLTIMA venda, como a tela inicial.
 */
export default function PainelDeVendas() {
  const [modo, setModo] = useEstadoNaUrl<string>("modo", "dia");
  const [de, setDe] = useEstadoNaUrl<string>("de", "", { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", "", { atraso: 0 });
  const [agrupar, setAgrupar] = useEstadoNaUrl<string>("agrupar", "dia");
  const [ordem, setOrdem] = useEstadoNaUrl<string>("ordem", "receita");
  const [limite, setLimite] = useEstadoNaUrl<string>("limite", "20");
  const [cat, setCat] = useEstadoNaUrl<string>("categoria", "");
  const [setor, setSetor] = useEstadoNaUrl<string>("setor", "");

  const [p, setP] = useState<PainelVendas | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [categorias, setCategorias] = useState<Opcao[]>([]);
  const [setores, setSetores] = useState<Opcao[]>([]);

  useEffect(() => {
    pedirCategorias().then(setCategorias).catch(() => setCategorias([]));
    pedirSetores().then(setSetores).catch(() => setSetores([]));
  }, []);

  useEffect(() => {
    let vivo = true;
    setCarregando(true);
    setErro("");
    pedirPainel({
      inicio: de || undefined, fim: ate || undefined,
      agrupar: agrupar as Agrupar, ordem: ordem as Ordem, limite: Number(limite) || 20,
      categoria: cat ? Number(cat) : null, setor: setor ? Number(setor) : null,
    })
      .then((r) => vivo && setP(r))
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar o painel"))
      .finally(() => vivo && setCarregando(false));
    return () => {
      vivo = false;
    };
  }, [de, ate, agrupar, ordem, limite, cat, setor]);

  const m = (MODOS.some((x) => x.valor === modo) ? modo : "dia") as Modo;
  // O recorte EM VIGOR: o da URL, ou o que o servidor escolheu (o dia da última venda).
  const inicio = de || p?.inicio || "";
  const fim = ate || p?.fim || "";

  function ir([novoDe, novoAte]: [string, string]) {
    setDe(novoDe);
    setAte(novoAte);
  }
  function trocarModo(novo: Modo) {
    setModo(novo);
    if (!inicio) return;
    // Âncora: o FIM do recorte atual — de um mês, "dia" cai no último dia dele.
    ir(janela(novo, novo === "dia" ? fim : inicio, inicio, fim));
    // Um dia não tem evolução por semana; um mês por dia já são 30 barras.
    if (novo === "dia" || novo === "semana") setAgrupar("dia");
  }

  const nomeCat = categorias.find((c) => String(c.id) === cat)?.nome;
  const nomeSetor = setores.find((s) => String(s.id) === setor)?.nome;
  const umDia = inicio && inicio === fim;
  const semVenda = p && p.totais.cupons === 0;

  return (
    <div className="space-y-4">
      <CabecalhoTela
        caminho="Vendas"
        titulo={<>Painel {inicio && <span className="font-normal text-suave">· {nomeDoRecorte(m, inicio, fim)}</span>}</>}
        explica={
          <>
            O estudo das vendas de um recorte: faturado, cupons e ticket comparados com o período
            anterior, a evolução, o dia da semana, a hora e os mais vendidos. Cupom cancelado e
            consumo interno ficam fora das somas. <b>Baixar</b> leva o mesmo recorte, com todos os
            produtos.
          </>
        }
        acoes={inicio && (
          <BotaoExportar
            relatorio="vendas"
            iniciais={{
              inicio, fim, agrupar,
              ...(cat ? { categorias: [Number(cat)] } : {}),
              ...(setor ? { setores: [Number(setor)] } : {}),
            }}
          />
        )}
      />

      <Cartao>
        <div className="flex flex-wrap items-center gap-3" id="painel-vendas-filtros">
          <div className="flex overflow-hidden rounded-lg border border-linha" role="group" aria-label="recorte">
            {MODOS.map((x) => (
              <button key={x.valor} type="button" data-modo={x.valor}
                      className={`px-3 py-1.5 text-[13.5px] ${m === x.valor ? "bg-erva font-bold text-white" : "hover:bg-linha/40"}`}
                      onClick={() => trocarModo(x.valor)}>
                {x.nome}
              </button>
            ))}
          </div>

          {m === "periodo" ? (
            <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
              <input type="date" className="campo py-1" style={{ width: "auto" }} id="painel-vendas-de" aria-label="início"
                     value={inicio} onChange={(e) => e.target.value && setDe(e.target.value)} />
              <span className="text-suave">a</span>
              <input type="date" className="campo py-1" style={{ width: "auto" }} id="painel-vendas-ate" aria-label="fim"
                     value={fim} onChange={(e) => e.target.value && setAte(e.target.value)} />
            </div>
          ) : m === "dia" ? (
            <input type="date" className="campo py-1" style={{ width: "auto" }} id="painel-vendas-dia" aria-label="dia"
                   value={inicio} onChange={(e) => e.target.value && ir([e.target.value, e.target.value])} />
          ) : null}

          <div className="flex items-center gap-1">
            <button type="button" className="link-acao px-2 text-[18px]" aria-label="recorte anterior"
                    disabled={!inicio || carregando} onClick={() => ir(andar(m, inicio, fim, -1))}>‹</button>
            <button type="button" className="link-acao px-2 text-[18px]" aria-label="próximo recorte"
                    disabled={!inicio || carregando} onClick={() => ir(andar(m, inicio, fim, 1))}>›</button>
          </div>

          {!umDia && (
            <label className="flex items-center gap-2 text-[13.5px]">
              <span className="text-suave">evolução por</span>
              <select className="campo py-1" style={{ width: "auto" }} id="painel-vendas-agrupar" value={agrupar}
                      onChange={(e) => setAgrupar(e.target.value)}>
                <option value="dia">dia</option>
                <option value="semana">semana</option>
                <option value="mes">mês</option>
              </select>
            </label>
          )}

          <select className="campo py-1 text-[13.5px]" style={{ width: "auto", maxWidth: "16rem" }} id="painel-vendas-categoria" aria-label="categoria"
                  value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="">todas as categorias</option>
            {categorias.map((c) => <option key={c.id} value={c.id}>{c.caminho ?? c.nome}</option>)}
          </select>
          <select className="campo py-1 text-[13.5px]" style={{ width: "auto", maxWidth: "16rem" }} id="painel-vendas-setor" aria-label="setor"
                  value={setor} onChange={(e) => setSetor(e.target.value)}>
            <option value="">todos os setores</option>
            {setores.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
          </select>
          {(cat || setor) && (
            <button type="button" className="link-acao text-[13px]" onClick={() => { setCat(""); setSetor(""); }}>
              limpar recorte{nomeCat || nomeSetor ? ` (${[nomeCat, nomeSetor].filter(Boolean).join(" · ")})` : ""}
            </button>
          )}
        </div>
      </Cartao>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!p && carregando && <Carregando />}

      {p && (
        <div className={`space-y-4 ${carregando ? "opacity-60" : ""}`} aria-busy={carregando}>
          {semVenda ? (
            // ⚠️ Número verdadeiro ou nenhum: um recorte sem venda importada não é "a casa
            // vendeu zero" — pode ser só a busca no PDV que ainda não rodou.
            <Cartao><Vazio>Nenhuma venda importada neste recorte.</Vazio></Cartao>
          ) : (
            <>
              <Resumo p={p} />
              {p.serie.length > 1 && <Evolucao p={p} />}
              <div className={`grid gap-4 ${umDia ? "" : "lg:grid-cols-2"}`}>
                {!umDia && <DiaDaSemana p={p} />}
                <PorHora p={p} largo={!!umDia} />
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <Grupos titulo="Por categoria" linhas={p.por_categoria} ativo={cat ? Number(cat) : null}
                        aoClicar={(id) => setCat(id === null || String(id) === cat ? "" : String(id))} />
                <Grupos titulo="Por setor" linhas={p.por_setor} ativo={setor ? Number(setor) : null}
                        aoClicar={(id) => setSetor(id === null || String(id) === setor ? "" : String(id))} />
              </div>
              <Produtos p={p} ordem={ordem as Ordem} aoOrdenar={setOrdem}
                        limite={Number(limite) || 20} aoLimitar={(n) => setLimite(String(n))} />
            </>
          )}
        </div>
      )}
    </div>
  );
}
