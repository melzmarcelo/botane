"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Confirmacao, Vazio } from "@/components/ui";
import {
  cancelarContas,
  Categoria,
  categoriasFinanceiro,
  Conta,
  dataBr,
  estornarContas,
  FORMAS,
  listarContas,
  Resumo,
  resumoContas,
  SituacaoConta,
} from "@/lib/contas-pagar";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { reais } from "@/lib/numeros";
import { useSessao } from "@/lib/sessao";

import { JanelaFixas } from "./fixas";
import {
  JanelaAgendar,
  JanelaAnexar,
  JanelaCategorias,
  JanelaComprovante,
  JanelaConta,
  JanelaEquipe,
  JanelaPagar,
} from "./janelas";

/**
 * Contas a pagar (migração 163, módulo Financeiro — pedido do dono de 24/11/2026).
 *
 * 🔑 Três abas pela situação: A pagar · Agendados · Pagos. O agendado com baixa automática vira
 * pago sozinho na data. A lista se agrupa por pessoa — "quanto cada freelancer tem a receber" —
 * e "pagar todas" de uma pessoa usa um comprovante só.
 * 🔑 Etapa 3 (167): as contas fixas (aluguel, internet, luz) geram a conta de cada mês sozinhas,
 * e a nova conta pode ser parcelada. A linha marca "parcela 2/3" e "conta fixa".
 * ⚠️ Não mexe em CMV nem estoque.
 */

type Aba = "A_PAGAR" | "AGENDADO" | "PAGO" | "CANCELADO";
const ABAS: { valor: Aba; rotulo: string }[] = [
  { valor: "A_PAGAR", rotulo: "A pagar" }, { valor: "AGENDADO", rotulo: "Agendados" },
  { valor: "PAGO", rotulo: "Pagos" }, { valor: "CANCELADO", rotulo: "Cancelados" },
];

function Numero({ rotulo, valor, sub, tom }: { rotulo: string; valor: string; sub?: string; tom?: "alerta" | "erro" }) {
  return (
    <div className="min-w-0" data-numero-pagar={rotulo}>
      <p className="rotulo">{rotulo}</p>
      <p className={`mono mt-1 text-[20px] font-bold leading-none ${tom === "erro" ? "text-erro" : tom === "alerta" ? "text-alerta" : ""}`}>{valor}</p>
      {sub && <p className="mt-1 text-[12.5px] text-suave">{sub}</p>}
    </div>
  );
}

export default function PaginaContasPagar() {
  const { pode, unidade } = useSessao();
  const aviso = useAviso();
  const podeLancar = pode("financeiro.pagar_lancar");
  const podeBaixar = pode("financeiro.pagar_baixar");
  const [aba, setAba] = useEstadoNaUrl<string>("aba", "A_PAGAR", { atraso: 0 });
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [de, setDe] = useEstadoNaUrl<string>("de", "", { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", "", { atraso: 0 });
  const [categoria, setCategoria] = useEstadoNaUrl<string>("categoria", "", { atraso: 0 });
  const [porPessoa, setPorPessoa] = useEstadoNaUrl<boolean>("pessoa", false);
  const abaAtual = (ABAS.some((a) => a.valor === aba) ? aba : "A_PAGAR") as Aba;
  const [lista, setLista] = useState<Conta[] | null>(null);
  const [totais, setTotais] = useState<{ contas: number; valor: number; atrasadas: number } | null>(null);
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [erro, setErro] = useState("");
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set());
  const [janela, setJanela] = useState<
    | { tipo: "nova" } | { tipo: "corrigir"; conta: Conta } | { tipo: "equipe" } | { tipo: "categorias" }
    | { tipo: "fixas" }
    | { tipo: "agendar"; contas: Conta[] } | { tipo: "pagar"; contas: Conta[] }
    | { tipo: "anexar"; contas: Conta[] } | { tipo: "comprovante"; conta: Conta } | null>(null);
  const [confirmar, setConfirmar] = useState<{ acao: "estornar" | "cancelar"; contas: Conta[] } | null>(null);
  const ultimo = useRef(0);

  const carregarCategorias = useCallback(() => {
    categoriasFinanceiro().then(setCategorias).catch(() => setCategorias([]));
  }, []);
  useEffect(() => { carregarCategorias(); }, [carregarCategorias]);
  useEffect(() => { setLista(null); setMarcadas(new Set()); }, [abaAtual, unidade]);

  const carregar = useCallback(async () => {
    const pedido = ++ultimo.current;
    setErro("");
    try {
      const q = new URLSearchParams({ status: abaAtual, limite: "500" });
      if (de) q.set("de", de);
      if (ate) q.set("ate", ate);
      if (categoria) q.set("id_categoria", categoria);
      if (busca.trim()) q.set("busca", busca.trim());
      const [l, r] = await Promise.all([listarContas(q), resumoContas()]);
      if (pedido !== ultimo.current) return;
      setLista(l.itens);
      setTotais(l.totais);
      setResumo(r);
      setMarcadas(new Set());
    } catch (e) {
      if (pedido !== ultimo.current) return;
      setLista([]);
      setErro(e instanceof Error ? e.message : "Falha ao carregar as contas");
    }
  }, [abaAtual, de, ate, categoria, busca, unidade]);
  useEffect(() => { void carregar(); }, [carregar]);

  const grupos = useMemo(() => {
    const m = new Map<number, { pessoa: string; pix: string | null; contas: Conta[]; total: number }>();
    for (const c of lista ?? []) {
      const g = m.get(c.id_pessoa) ?? { pessoa: c.pessoa, pix: c.chave_pix, contas: [], total: 0 };
      g.contas.push(c);
      g.total += Number(c.valor_pago ?? c.valor);
      m.set(c.id_pessoa, g);
    }
    return [...m.values()].sort((a, b) => b.total - a.total);
  }, [lista]);

  const alternar = (id: number) => setMarcadas((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const selecionadas = (lista ?? []).filter((c) => marcadas.has(c.id));
  const aberta = abaAtual === "A_PAGAR" || abaAtual === "AGENDADO";
  const fechar = (m?: string) => { setJanela(null); if (m) { aviso.sucesso(m); void carregar(); } };

  async function executar() {
    if (!confirmar) return;
    try {
      const ids = confirmar.contas.map((c) => c.id);
      const r = confirmar.acao === "estornar" ? await estornarContas(ids) : await cancelarContas(ids);
      aviso.sucesso(r.message);
      setConfirmar(null);
      void carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível");
      setConfirmar(null);
    }
  }

  function Linha({ c }: { c: Conta }) {
    return (
      <li data-conta={c.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3">
        {abaAtual !== "CANCELADO" && (podeBaixar || podeLancar) && (
          <input type="checkbox" className="h-5 w-5" aria-label={`selecionar conta ${c.id}`}
                 checked={marcadas.has(c.id)} onChange={() => alternar(c.id)} />
        )}
        <div className="min-w-[12rem] flex-1">
          <p className="font-semibold">
            {!porPessoa && <>{c.pessoa} <span className="font-normal text-suave">· </span></>}
            <span className={porPessoa ? "" : "font-normal"}>{c.descricao}</span>
            {c.funcao && <span className="font-normal text-suave"> · {c.funcao}</span>}
            {c.parcelas && (
              <span className="ml-2 rounded-full bg-superficie2 px-2 py-0.5 text-[12px] font-semibold" data-parcela>
                parcela {c.parcela}/{c.parcelas}
              </span>
            )}
            {c.id_conta_fixa && (
              <span className="ml-2 rounded-full bg-superficie2 px-2 py-0.5 text-[12px] font-semibold" data-conta-fixa>
                conta fixa
              </span>
            )}
          </p>
          <p className="text-[12.5px] text-suave">
            {c.categoria ?? "sem categoria"} · competência {dataBr(c.competencia)}
            {c.status === "PAGO"
              ? <> · pago em {dataBr(c.pago_em)}{c.forma ? ` (${FORMAS[c.forma]})` : ""}
                  {c.baixado_automaticamente ? " · baixa automática" : c.pago_por_nome ? ` por ${c.pago_por_nome}` : ""}</>
              : <> · vence {dataBr(c.vencimento)}</>}
            {c.status === "AGENDADO" && <> · agendado {dataBr(c.agendado_para)}{c.forma ? ` (${FORMAS[c.forma]})` : ""}
              {c.baixa_automatica ? ", baixa automática" : ""}</>}
          </p>
        </div>
        {c.atrasada && <span className="rounded-full bg-erro-claro px-2.5 py-0.5 text-[12.5px] font-semibold text-erro">atrasada</span>}
        <span className="mono font-semibold">
          {reais(Number(c.valor_pago ?? c.valor))}
          {c.valor_pago !== null && Number(c.valor_pago) !== Number(c.valor) && (
            <span className="block text-right text-[11.5px] font-normal text-suave">de {reais(Number(c.valor))}</span>
          )}
        </span>
        <span className="flex flex-wrap gap-1">
          {aberta && podeBaixar && (
            <button type="button" className="btn btn-secundario btn-pequeno" data-acao="pagar"
                    onClick={() => setJanela({ tipo: "pagar", contas: [c] })}>Pagar</button>
          )}
          {aberta && podeLancar && (
            <>
              <button type="button" className="btn btn-terciario btn-pequeno" data-acao="agendar"
                      onClick={() => setJanela({ tipo: "agendar", contas: [c] })}>Agendar</button>
              <button type="button" className="btn btn-terciario btn-pequeno" data-acao="corrigir"
                      onClick={() => setJanela({ tipo: "corrigir", conta: c })}>Corrigir</button>
            </>
          )}
          {c.tem_comprovante && (
            <button type="button" className="btn btn-terciario btn-pequeno" data-acao="comprovante"
                    onClick={() => setJanela({ tipo: "comprovante", conta: c })}>Comprovante</button>
          )}
          {c.status === "PAGO" && podeBaixar && !c.tem_comprovante && (
            <button type="button" className="btn btn-terciario btn-pequeno" data-acao="anexar"
                    onClick={() => setJanela({ tipo: "anexar", contas: [c] })}>Anexar</button>
          )}
        </span>
      </li>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela caminho="Financeiro" titulo="Contas a pagar"
                     explica={<>O que a casa tem a pagar: freelancers, fornecedores, contas. Agende o
                       pagamento e, na data, o sistema dá baixa sozinho; ou pague à mão e anexe o
                       comprovante. As contas fixas (aluguel, internet) nascem sozinhas todo mês, e
                       uma compra pode ser parcelada. Não mexe no estoque nem no CMV.</>}
                     acoes={<div className="flex flex-wrap gap-2">
                       {podeLancar && <>
                         <button type="button" className="btn btn-primario" id="pagar-nova" onClick={() => setJanela({ tipo: "nova" })}>Nova conta</button>
                         <button type="button" className="btn btn-secundario" id="pagar-equipe" onClick={() => setJanela({ tipo: "equipe" })}>Lançar equipe do dia</button>
                       </>}
                       <button type="button" className="btn btn-secundario" id="pagar-fixas" onClick={() => setJanela({ tipo: "fixas" })}>Contas fixas</button>
                       <BotaoExportar relatorio="contas-pagar" iniciais={{ situacao_pagar: [abaAtual] }} />
                     </div>} />

      {resumo && (
        <Cartao>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5" id="pagar-resumo">
            <Numero rotulo="Atrasado" valor={reais(resumo.atrasado)} sub={`${resumo.n_atrasado} conta(s)`}
                    tom={resumo.n_atrasado ? "erro" : undefined} />
            <Numero rotulo="Vence hoje" valor={reais(resumo.hoje)} sub={`${resumo.n_hoje} conta(s)`}
                    tom={resumo.n_hoje ? "alerta" : undefined} />
            <Numero rotulo="Próximos 7 dias" valor={reais(resumo.semana)} />
            <Numero rotulo="A pagar" valor={reais(resumo.a_pagar)} sub={`${resumo.n_a_pagar} conta(s)`} />
            <Numero rotulo="Agendado" valor={reais(resumo.agendado)}
                    sub={`${resumo.n_agendado} conta(s)${resumo.pagos_sozinhos_hoje ? ` · ${resumo.pagos_sozinhos_hoje} baixada(s) sozinha(s) hoje` : ""}`} />
          </div>
        </Cartao>
      )}

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao>
        <div className="flex flex-wrap items-center gap-2">
          {ABAS.map((a) => (
            <button key={a.valor} type="button" data-aba-pagar={a.valor}
                    className={`btn ${abaAtual === a.valor ? "btn-primario" : "btn-secundario"}`}
                    onClick={() => setAba(a.valor)}>{a.rotulo}</button>
          ))}
          <label className="ml-2 flex items-center gap-2 text-[13.5px]">
            <input type="checkbox" className="h-4 w-4" id="pagar-por-pessoa" checked={porPessoa}
                   onChange={(e) => setPorPessoa(e.target.checked)} />
            agrupar por pessoa
          </label>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[13.5px]">
          <div className="w-full sm:w-56">
            <input className="campo py-1.5" id="pagar-busca" placeholder="pessoa, descrição ou função"
                   aria-label="buscar" value={busca} onChange={(e) => setBusca(e.target.value)} />
          </div>
          <select className="campo py-1.5" style={{ width: "auto" }} aria-label="categoria" value={categoria}
                  onChange={(e) => setCategoria(e.target.value)}>
            <option value="">todas as categorias</option>
            {categorias.map((c) => <option key={c.id} value={c.id}>{c.nome}</option>)}
          </select>
          <span className="text-suave">{abaAtual === "PAGO" ? "pagas de" : "vencendo de"}</span>
          <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="de" value={de}
                 onChange={(e) => setDe(e.target.value)} />
          <span className="text-suave">até</span>
          <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="até" value={ate}
                 onChange={(e) => setAte(e.target.value)} />
          {podeLancar && (
            <button type="button" className="link-acao ml-auto text-[13px]" onClick={() => setJanela({ tipo: "categorias" })}>
              categorias
            </button>
          )}
        </div>

        {totais && (
          <p className="mt-3 text-[13.5px]" id="pagar-totais">
            {totais.contas} conta(s) · <b>{reais(totais.valor)}</b>
            {totais.atrasadas > 0 && <span className="text-erro"> · {totais.atrasadas} atrasada(s)</span>}
          </p>
        )}

        {selecionadas.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-lg bg-erva-claro/60 px-3 py-2" id="pagar-selecao">
            <span className="text-[13.5px]">{selecionadas.length} selecionada(s) ·{" "}
              <b>{reais(selecionadas.reduce((s, c) => s + Number(c.valor_pago ?? c.valor), 0))}</b></span>
            {aberta && podeBaixar && <button type="button" className="btn btn-primario btn-pequeno" id="pagar-selecionadas"
                                             onClick={() => setJanela({ tipo: "pagar", contas: selecionadas })}>Pagar</button>}
            {aberta && podeLancar && <button type="button" className="btn btn-secundario btn-pequeno" id="agendar-selecionadas"
                                             onClick={() => setJanela({ tipo: "agendar", contas: selecionadas })}>Agendar</button>}
            {aberta && podeLancar && <button type="button" className="btn btn-terciario btn-pequeno" id="cancelar-selecionadas"
                                             onClick={() => setConfirmar({ acao: "cancelar", contas: selecionadas })}>Cancelar</button>}
            {abaAtual === "PAGO" && podeBaixar && <>
              <button type="button" className="btn btn-secundario btn-pequeno" id="anexar-selecionadas"
                      onClick={() => setJanela({ tipo: "anexar", contas: selecionadas })}>Anexar comprovante</button>
              <button type="button" className="btn btn-terciario btn-pequeno" id="estornar-selecionadas"
                      onClick={() => setConfirmar({ acao: "estornar", contas: selecionadas })}>Estornar baixa</button>
            </>}
          </div>
        )}

        <div className="mt-2">
          {!lista ? <Carregando /> : !lista.length ? (
            <Vazio>{busca || de || ate || categoria ? "Nada com esse filtro." : abaAtual === "A_PAGAR" ? "Nada a pagar." : "Nenhuma conta aqui."}</Vazio>
          ) : porPessoa ? (
            <div className="flex flex-col gap-4" id="pagar-grupos">
              {grupos.map((g) => (
                <section key={g.pessoa} className="rounded-lg border border-linha p-3" data-grupo-pessoa={g.pessoa}>
                  <header className="flex flex-wrap items-center gap-2">
                    <h3 className="font-bold">{g.pessoa}</h3>
                    {g.pix && <span className="mono text-[12.5px] text-suave">Pix {g.pix}</span>}
                    <span className="mono ml-auto font-semibold">{reais(g.total)}</span>
                    {aberta && podeBaixar && (
                      <button type="button" className="btn btn-secundario btn-pequeno" data-acao="pagar-todas"
                              onClick={() => setJanela({ tipo: "pagar", contas: g.contas })}>Pagar todas ({g.contas.length})</button>
                    )}
                  </header>
                  <ul className="divide-y divide-[var(--borda)]">{g.contas.map((c) => <Linha key={c.id} c={c} />)}</ul>
                </section>
              ))}
            </div>
          ) : (
            <ul className="divide-y divide-[var(--borda)]" id="pagar-lista">{lista.map((c) => <Linha key={c.id} c={c} />)}</ul>
          )}
        </div>
      </Cartao>

      {janela?.tipo === "nova" && <JanelaConta conta={null} categorias={categorias} aoFechar={() => fechar()} aoSalvar={fechar} />}
      {janela?.tipo === "corrigir" && <JanelaConta conta={janela.conta} categorias={categorias} aoFechar={() => fechar()} aoSalvar={fechar} />}
      {janela?.tipo === "equipe" && <JanelaEquipe categorias={categorias} aoFechar={() => fechar()} aoSalvar={fechar} />}
      {janela?.tipo === "agendar" && <JanelaAgendar contas={janela.contas} aoFechar={() => fechar()} aoSalvar={fechar} />}
      {janela?.tipo === "pagar" && <JanelaPagar contas={janela.contas} aoFechar={() => fechar()} aoSalvar={fechar} />}
      {janela?.tipo === "anexar" && <JanelaAnexar contas={janela.contas} aoFechar={() => fechar()} aoSalvar={fechar} />}
      {janela?.tipo === "comprovante" && <JanelaComprovante conta={janela.conta} aoFechar={() => fechar()} />}
      {janela?.tipo === "fixas" && (
        <JanelaFixas categorias={categorias} podeLancar={podeLancar}
                     aoFechar={(mudou) => { setJanela(null); if (mudou) void carregar(); }} />
      )}
      {janela?.tipo === "categorias" && (
        <JanelaCategorias categorias={categorias} aoFechar={() => fechar()} aoMudar={carregarCategorias} />
      )}
      {confirmar && (
        <Confirmacao titulo={confirmar.acao === "estornar" ? "Estornar a baixa?" : "Cancelar as contas?"}
                     rotuloConfirmar={confirmar.acao === "estornar" ? "Estornar" : "Cancelar contas"}
                     rotuloCancelar="Voltar" perigo aoConfirmar={() => void executar()} aoCancelar={() => setConfirmar(null)}>
          {confirmar.acao === "estornar"
            ? `${confirmar.contas.length} conta(s) voltam a ficar em aberto (agendadas, se tinham agendamento). Use quando o pagamento não saiu.`
            : `${confirmar.contas.length} conta(s) saem das contas a pagar. Fica registrado quem cancelou.`}
        </Confirmacao>
      )}
    </div>
  );
}
