"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro from "@/components/busca-cadastro";
import { Aviso, Campo, CampoMoeda, Carregando, Cartao, Confirmacao, Etiqueta } from "@/components/ui";
import Voltar from "@/components/voltar";
import { api } from "@/lib/api";
import type { Local, Setor } from "@/lib/cadastros";
import { fonteProdutos } from "@/lib/busca-cadastro";
import { hoje } from "@/lib/datas";
import { moedaParaNumero, numeroParaMoeda, reais } from "@/lib/numeros";
import {
  COR_PREVENTIVA, CRITICIDADES, SITUACOES, TENSOES, apagar, apagarManutencao, criar, dataBr,
  doProduto, imprimirPlaquetas, obter, registrarManutencao, salvar, type BemDetalhe, type BemForm,
  type DoProduto,
} from "@/lib/patrimonio";
import { useSessao } from "@/lib/sessao";

/**
 * A ficha de um bem: o cadastro, o plano de preventiva, o histórico de manutenção e a
 * plaqueta. A mesma tela cria (`/patrimonio/novo`).
 *
 * 🔑 **A próxima preventiva é do servidor** (última + intervalo): a tela mostra, não
 * calcula — calculada aqui, divergiria da lista e do alerta no primeiro mês de 31 dias.
 * 🔑 **O equipamento que é local de estoque** (a câmara fria): parado ou em manutenção,
 * a ficha avisa quanto está guardado dentro dele.
 * 🔑 **O bem nasce do produto Patrimônio** (pedido do dono, 27/10/2026: "o equipamento
 * poderia ser um produto patrimônio, onde teria a opção de busca por produtos deste tipo").
 * Escolhido o produto, o que estiver VAZIO se preenche com a última entrada dele (data,
 * nota, fornecedor, valor) — o que a pessoa já digitou não é trocado. `?produto=` (o botão
 * "Cadastrar bem" da lista do que falta) chega já escolhido.
 */
const FONTE_PATRIMONIO = fonteProdutos("tipo=PATRIMONIO");

type Form = Record<string, string>;
const TEXTOS = ["descricao", "apelido", "marca", "modelo", "numero_serie", "fornecedor",
  "nota_fiscal", "assistencia", "assistencia_contato", "observacao", "motivo_baixa"] as const;
const DATAS = ["data_compra", "garantia_ate", "ultima_preventiva", "data_baixa"] as const;
const ESCOLHAS = ["tensao", "criticidade", "situacao", "id_setor", "id_local"] as const;

const VAZIO: Form = { situacao: "EM_USO" };

function paraForm(b: BemDetalhe): Form {
  const f: Form = {};
  for (const k of [...TEXTOS, ...DATAS, ...ESCOLHAS]) {
    const v = (b as unknown as Record<string, unknown>)[k];
    f[k] = v === null || v === undefined ? "" : String(v);
  }
  f.preventiva_meses = b.preventiva_meses ? String(b.preventiva_meses) : "";
  f.vida_util_anos = b.vida_util_anos ? String(b.vida_util_anos) : "";
  f.id_produto = b.id_produto ? String(b.id_produto) : "";
  f.valor_compra = b.valor_compra !== null ? numeroParaMoeda(b.valor_compra) : "";
  return f;
}

function paraCorpo(f: Form): BemForm {
  const c: BemForm = {};
  for (const k of [...TEXTOS, ...DATAS]) c[k] = f[k]?.trim() || null;
  c.tensao = f.tensao || null;
  c.criticidade = f.criticidade || null;
  c.situacao = f.situacao || "EM_USO";
  c.id_setor = f.id_setor ? Number(f.id_setor) : null;
  c.id_local = f.id_local ? Number(f.id_local) : null;
  c.id_produto = f.id_produto ? Number(f.id_produto) : null;
  c.preventiva_meses = f.preventiva_meses ? Number(f.preventiva_meses) : null;
  c.vida_util_anos = f.vida_util_anos ? Number(f.vida_util_anos) : null;
  // Fora do baixado a data não vale (o banco limpa); vazia na baixa, o banco põe hoje.
  if (c.situacao !== "BAIXADO") c.data_baixa = null;
  c.valor_compra = f.valor_compra ? moedaParaNumero(f.valor_compra) : null;
  return c;
}

export default function FichaDoBem() {
  const { id } = useParams<{ id: string }>();
  const novo = id === "novo";
  const router = useRouter();
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeCadastrar = pode("patrimonio.cadastrar");
  const podeManutencao = pode("patrimonio.manutencao") || podeCadastrar;
  const [bem, setBem] = useState<BemDetalhe | null>(null);
  const [f, setF] = useState<Form>(VAZIO);
  const [setores, setSetores] = useState<Setor[]>([]);
  const [locais, setLocais] = useState<Local[]>([]);
  const [erro, setErro] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [apagando, setApagando] = useState(false);
  const [produto, setProduto] = useState<{ id: number; rotulo: string } | null>(null);
  const doQr = useSearchParams().get("produto");

  const carregar = useCallback(() => {
    if (novo) return;
    obter(Number(id))
      .then((b) => {
        setBem(b);
        setF(paraForm(b));
        setProduto(b.id_produto ? { id: b.id_produto, rotulo: b.produto ?? "" } : null);
        setErro("");
      })
      .catch((e) => setErro(e instanceof Error ? e.message : "Bem não encontrado"));
  }, [id, novo]);

  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => {
    api.get<Setor[]>("/setores").then(setSetores).catch(() => {});
    api.get<Local[]>("/locais").then(setLocais).catch(() => {});
  }, []);

  /** Preenche só o que está VAZIO com a sugestão do produto (a última entrada dele). */
  const completar = useCallback((d: DoProduto) => {
    setProduto({ id: d.produto.id, rotulo: d.produto.nome });
    setF((atual) => {
      const novoF: Form = { ...atual, id_produto: String(d.produto.id) };
      const s = d.sugestao;
      const vazio = (k: string) => !atual[k];
      if (vazio("descricao")) novoF.descricao = s.descricao;
      if (s.id_setor && vazio("id_setor")) novoF.id_setor = String(s.id_setor);
      if (s.id_local && vazio("id_local")) novoF.id_local = String(s.id_local);
      if (s.data_compra && vazio("data_compra")) novoF.data_compra = s.data_compra;
      if (s.fornecedor && vazio("fornecedor")) novoF.fornecedor = s.fornecedor;
      if (s.nota_fiscal && vazio("nota_fiscal")) novoF.nota_fiscal = s.nota_fiscal;
      if (s.valor_compra && vazio("valor_compra")) novoF.valor_compra = numeroParaMoeda(s.valor_compra);
      return novoF;
    });
  }, []);

  useEffect(() => {
    if (novo && doQr) doProduto(Number(doQr)).then(completar).catch(() => {});
  }, [novo, doQr, completar]);

  function escolherProduto(item: { id: number; nome: string } | null) {
    if (!item) {
      setProduto(null);
      setF({ ...f, id_produto: "" });
      return;
    }
    if (novo) {
      doProduto(item.id).then(completar).catch(() => {
        setProduto({ id: item.id, rotulo: item.nome });
        setF({ ...f, id_produto: String(item.id) });
      });
    } else {
      setProduto({ id: item.id, rotulo: item.nome });
      setF({ ...f, id_produto: String(item.id), descricao: f.descricao || item.nome });
    }
  }

  const muda = (k: string) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  async function gravar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    try {
      if (novo) {
        const r = await criar(paraCorpo(f));
        aviso.sucesso(r.message);
        router.replace(`/patrimonio/${r.id}`);
      } else {
        const r = await salvar(Number(id), paraCorpo(f));
        aviso.sucesso(r.message);
        carregar();
      }
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function confirmarApagar() {
    try {
      const r = await apagar(Number(id));
      aviso.sucesso(r.message);
      router.replace("/patrimonio");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível apagar");
      setApagando(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!novo && !bem) return <Carregando />;

  const parado = bem && ["EM_MANUTENCAO", "PARADO"].includes(bem.situacao);
  const travado = !podeCadastrar;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Voltar href="/patrimonio">patrimônio</Voltar>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          {novo ? "Novo bem" : (
            <>
              <span className="mono">{bem!.codigo}</span> · {bem!.descricao}
            </>
          )}
        </h1>
        {bem && (
          <div className="mt-2 flex flex-wrap items-center gap-2 text-[13.5px]">
            <Etiqueta cor={bem.situacao === "EM_USO" ? "erva" : "alerta"}>{bem.situacao_txt}</Etiqueta>
            {bem.status_preventiva !== "FORA" && (
              <Etiqueta cor={COR_PREVENTIVA[bem.status_preventiva] ?? "neutro"}>
                Preventiva: {bem.preventiva_txt}
                {bem.proxima_preventiva ? ` · próxima ${dataBr(bem.proxima_preventiva)}` : ""}
              </Etiqueta>
            )}
            {bem.em_garantia && <Etiqueta cor="erva">em garantia até {dataBr(bem.garantia_ate)}</Etiqueta>}
            <span className="text-suave" id="bem-conferido">
              {bem.conferido_em ? `conferido em ${dataBr(bem.conferido_em)}` : "nunca conferido"}
            </span>
            {podeCadastrar && (
              <button type="button" className="btn btn-secundario" id="bem-plaqueta"
                      onClick={() => imprimirPlaquetas([bem.id]).catch((x) =>
                        aviso.erro(x instanceof Error ? x.message : "Não foi possível imprimir"))}>
                Imprimir plaqueta
              </button>
            )}
          </div>
        )}
      </header>

      {parado && bem?.estoque_no_local && bem.estoque_no_local.produtos > 0 && (
        <Aviso tipo="erro">
          <b>{bem.local}</b> guarda {bem.estoque_no_local.produtos} produto(s) com saldo
          {bem.estoque_no_local.valor !== null ? ` (${reais(bem.estoque_no_local.valor)})` : ""}.
          Com o equipamento {bem.situacao_txt.toLowerCase()}, confira se precisam ir para outro local.
        </Aviso>
      )}

      <form onSubmit={gravar} className="flex flex-col gap-6" id="bem-form">
        <Cartao titulo="Identificação">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Campo rotulo="Produto (Patrimônio)" opcional className="sm:col-span-2 lg:col-span-3"
                   dica="o produto do cadastro, do tipo Patrimônio — num bem novo, a última entrada dele preenche a compra">
              <BuscaCadastro fonte={FONTE_PATRIMONIO} selecionado={produto} id="bem-produto"
                             disabled={travado} aoEscolher={escolherProduto} />
            </Campo>
            <Campo rotulo="Equipamento" className="sm:col-span-2">
              <input className="campo" id="bem-descricao" required maxLength={120} disabled={travado}
                     value={f.descricao ?? ""} onChange={muda("descricao")} />
            </Campo>
            <Campo rotulo="Código da casa" opcional dica="o da planilha (ex.: BAR-02)">
              <input className="campo mono" id="bem-apelido" maxLength={20} disabled={travado}
                     value={f.apelido ?? ""} onChange={muda("apelido")} />
            </Campo>
            <Campo rotulo="Setor" opcional>
              <select className="campo" id="bem-setor" disabled={travado}
                      value={f.id_setor ?? ""} onChange={muda("id_setor")}>
                <option value="">—</option>
                {setores.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Local" opcional dica="a câmara fria É o local: o estoque dela aparece aqui">
              <select className="campo" id="bem-local" disabled={travado}
                      value={f.id_local ?? ""} onChange={muda("id_local")}>
                <option value="">—</option>
                {locais.map((l) => <option key={l.id} value={l.id}>{l.nome}</option>)}
              </select>
            </Campo>
            <Campo rotulo="Situação">
              <select className="campo" id="bem-situacao" disabled={travado}
                      value={f.situacao ?? "EM_USO"} onChange={muda("situacao")}>
                {Object.entries(SITUACOES).map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </Campo>
            {f.situacao === "BAIXADO" && (
              <Campo rotulo="Motivo da baixa" className="sm:col-span-2"
                     dica="venda, descarte, perda, doação — o bem sai da lista, o histórico fica">
                <input className="campo" id="bem-motivo-baixa" required maxLength={200} disabled={travado}
                       value={f.motivo_baixa ?? ""} onChange={muda("motivo_baixa")} />
              </Campo>
            )}
            {f.situacao === "BAIXADO" && (
              <Campo rotulo="Data da baixa" opcional dica="vazia, fica hoje — a depreciação para nela">
                <input type="date" className="campo" id="bem-data-baixa" max={hoje()} disabled={travado}
                       value={f.data_baixa ?? ""} onChange={muda("data_baixa")} />
              </Campo>
            )}
            <Campo rotulo="Criticidade" opcional
                   dica="Alta: parar o equipamento para a venda ou estraga insumo. Média: atrapalha. Baixa: tem alternativa.">
              <select className="campo" id="bem-criticidade" disabled={travado}
                      value={f.criticidade ?? ""} onChange={muda("criticidade")}>
                <option value="">—</option>
                {Object.entries(CRITICIDADES).map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </Campo>
          </div>
        </Cartao>

        <Cartao titulo="Dados técnicos">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Campo rotulo="Marca" opcional>
              <input className="campo" maxLength={60} disabled={travado} value={f.marca ?? ""} onChange={muda("marca")} />
            </Campo>
            <Campo rotulo="Modelo" opcional>
              <input className="campo" maxLength={60} disabled={travado} value={f.modelo ?? ""} onChange={muda("modelo")} />
            </Campo>
            <Campo rotulo="Nº de série" opcional>
              <input className="campo mono" maxLength={60} disabled={travado}
                     value={f.numero_serie ?? ""} onChange={muda("numero_serie")} />
            </Campo>
            <Campo rotulo="Tensão" opcional>
              <select className="campo" disabled={travado} value={f.tensao ?? ""} onChange={muda("tensao")}>
                <option value="">—</option>
                {Object.entries(TENSOES).map(([v, n]) => <option key={v} value={v}>{n}</option>)}
              </select>
            </Campo>
          </div>
        </Cartao>

        <Cartao titulo="Compra, garantia e assistência">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Campo rotulo="Data de compra" opcional>
              <input type="date" className="campo" disabled={travado}
                     value={f.data_compra ?? ""} onChange={muda("data_compra")} />
            </Campo>
            <Campo rotulo="Valor de compra" opcional>
              <CampoMoeda valor={f.valor_compra ?? ""} desabilitado={travado}
                          aoMudar={(v) => setF({ ...f, valor_compra: v })} />
            </Campo>
            <Campo rotulo="Fornecedor da compra" opcional>
              <input className="campo" maxLength={120} disabled={travado}
                     value={f.fornecedor ?? ""} onChange={muda("fornecedor")} />
            </Campo>
            <Campo rotulo="Nota fiscal" opcional>
              <input className="campo mono" maxLength={40} disabled={travado}
                     value={f.nota_fiscal ?? ""} onChange={muda("nota_fiscal")} />
            </Campo>
            <Campo rotulo="Garantia até" opcional>
              <input type="date" className="campo" disabled={travado}
                     value={f.garantia_ate ?? ""} onChange={muda("garantia_ate")} />
            </Campo>
            <Campo rotulo="Assistência técnica" opcional className="sm:col-span-2">
              <input className="campo" id="bem-assistencia" maxLength={120} disabled={travado}
                     value={f.assistencia ?? ""} onChange={muda("assistencia")} />
            </Campo>
            <Campo rotulo="Contato" opcional>
              <input className="campo" maxLength={80} disabled={travado}
                     value={f.assistencia_contato ?? ""} onChange={muda("assistencia_contato")} />
            </Campo>
            <Campo rotulo="Vida útil (anos)" opcional
                   dica="vazia, 10 — o padrão da Receita para máquinas e móveis; computador é 5">
              <input type="number" min={1} max={50} className="campo" id="bem-vida-util" disabled={travado}
                     placeholder="10" value={f.vida_util_anos ?? ""} onChange={muda("vida_util_anos")} />
            </Campo>
          </div>
          {bem && <ValorDoBem bem={bem} />}
        </Cartao>

        <Cartao titulo="Manutenção preventiva"
                descricao="Com o intervalo e a data da última, o sistema calcula a próxima e avisa quando vencer.">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Campo rotulo="Preventiva a cada (meses)" opcional dica="o que o fabricante ou o técnico indica">
              <input type="number" min={1} max={120} className="campo" id="bem-preventiva-meses" disabled={travado}
                     value={f.preventiva_meses ?? ""} onChange={muda("preventiva_meses")} />
            </Campo>
            <Campo rotulo="Última preventiva" opcional dica="registrar uma preventiva abaixo atualiza sozinho">
              <input type="date" className="campo" id="bem-ultima-preventiva" disabled={travado}
                     value={f.ultima_preventiva ?? ""} onChange={muda("ultima_preventiva")} />
            </Campo>
            <Campo rotulo="Observações" opcional className="sm:col-span-2">
              <input className="campo" maxLength={500} disabled={travado}
                     value={f.observacao ?? ""} onChange={muda("observacao")} />
            </Campo>
          </div>
        </Cartao>

        {podeCadastrar && (
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="btn btn-primario" id="bem-salvar"
                    disabled={salvando} aria-busy={salvando}>
              {novo ? "Cadastrar" : "Salvar"}
            </button>
            {bem && !bem.manutencoes.length && (
              <button type="button" className="btn btn-secundario" onClick={() => setApagando(true)}>
                Apagar
              </button>
            )}
          </div>
        )}
      </form>

      {bem && (
        <Historico bem={bem} podeRegistrar={podeManutencao} aoMudar={carregar} />
      )}

      {apagando && (
        <Confirmacao titulo="Apagar este bem?" perigo rotuloConfirmar="Apagar"
                     aoConfirmar={() => void confirmarApagar()} aoCancelar={() => setApagando(false)}>
          Apagar é para cadastro feito por engano. Um bem que existiu e saiu da casa se
          <b> baixa</b> (Situação ▸ Baixado), para o histórico continuar existindo.
        </Confirmacao>
      )}
    </div>
  );
}

/** 141 — o valor de hoje (ou o da baixa), calculado pelo servidor com a conta do relatório. */
function ValorDoBem({ bem }: { bem: BemDetalhe }) {
  const v = bem.valor;
  if (v.sem_valor) {
    return <p className="mt-4 text-[13.5px] text-suave" id="bem-valor-atual">
      Sem valor de compra — o bem não entra no valor do patrimônio.</p>;
  }
  if (v.sem_data) {
    return <p className="mt-4 text-[13.5px] text-suave" id="bem-valor-atual">
      Sem data de compra, não deprecia: conta pelo valor de compra ({reais(v.valor_atual ?? 0)}).</p>;
  }
  return (
    <p className="mt-4 text-[13.5px]" id="bem-valor-atual">
      <b>{bem.situacao === "BAIXADO" ? "Valor na baixa" : "Valor atual"}: {reais(v.valor_atual ?? 0)}</b>
      <span className="text-suave">
        {" "}· depreciação {reais(v.depreciacao ?? 0)} ({v.depreciado_pct?.toLocaleString("pt-BR")}%)
        em {v.meses} {v.meses === 1 ? "mês" : "meses"} · {reais(v.quota_mensal ?? 0)} por mês
        · vida útil {v.vida_util} anos{v.vida_padrao ? " (padrão)" : ""}
        {v.depreciado_total ? " · totalmente depreciado" : v.fim_vida ? ` · até ${dataBr(v.fim_vida)}` : ""}
      </span>
    </p>
  );
}

function Historico({ bem, podeRegistrar, aoMudar }: {
  bem: BemDetalhe; podeRegistrar: boolean; aoMudar: () => void;
}) {
  const aviso = useAviso();
  const [m, setM] = useState({ tipo: "PREVENTIVA", data: hoje(), executado_por: "", custo: "",
                               descricao: "", situacao_depois: "" });
  const [gravando, setGravando] = useState(false);

  async function registrar(e: FormEvent) {
    e.preventDefault();
    setGravando(true);
    try {
      const r = await registrarManutencao(bem.id, {
        tipo: m.tipo, data: m.data, executado_por: m.executado_por.trim() || null,
        custo: m.custo ? moedaParaNumero(m.custo) : null, descricao: m.descricao.trim() || null,
        situacao_depois: m.situacao_depois || null,
      });
      aviso.sucesso(r.message);
      setM({ ...m, executado_por: "", custo: "", descricao: "", situacao_depois: "" });
      aoMudar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível registrar");
    } finally {
      setGravando(false);
    }
  }

  async function tirar(id: number) {
    try {
      const r = await apagarManutencao(id);
      aviso.sucesso(r.message);
      aoMudar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível apagar");
    }
  }

  return (
    <Cartao titulo="Histórico de manutenção"
            descricao={bem.manutencoes.length
              ? `${bem.manutencoes.length} registro(s) · ${reais(bem.custo_manutencao)} no total`
              : "Nenhuma manutenção registrada ainda."}>
      {podeRegistrar && (
        <form onSubmit={registrar} className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-6" id="manutencao-form">
          <Campo rotulo="Tipo">
            <select className="campo" id="manutencao-tipo" value={m.tipo}
                    onChange={(e) => setM({ ...m, tipo: e.target.value })}>
              <option value="PREVENTIVA">Preventiva</option>
              <option value="CORRETIVA">Corretiva</option>
            </select>
          </Campo>
          <Campo rotulo="Data">
            <input type="date" className="campo" id="manutencao-data" required max={hoje()} value={m.data}
                   onChange={(e) => setM({ ...m, data: e.target.value })} />
          </Campo>
          <Campo rotulo="Feito por" opcional>
            <input className="campo" maxLength={120} value={m.executado_por}
                   onChange={(e) => setM({ ...m, executado_por: e.target.value })} />
          </Campo>
          <Campo rotulo="Custo" opcional>
            <CampoMoeda valor={m.custo} aoMudar={(v) => setM({ ...m, custo: v })} />
          </Campo>
          <Campo rotulo="Depois da visita" opcional>
            <select className="campo" id="manutencao-situacao" value={m.situacao_depois}
                    onChange={(e) => setM({ ...m, situacao_depois: e.target.value })}>
              <option value="">não muda</option>
              {["EM_USO", "EM_MANUTENCAO", "PARADO", "DESATIVADO"].map((v) => (
                <option key={v} value={v}>{SITUACOES[v]}</option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="O que foi feito" opcional className="sm:col-span-2 lg:col-span-5">
            <input className="campo" id="manutencao-descricao" maxLength={500} value={m.descricao}
                   onChange={(e) => setM({ ...m, descricao: e.target.value })} />
          </Campo>
          <div className="flex items-end">
            <button type="submit" className="btn btn-primario w-full" id="manutencao-registrar"
                    disabled={gravando} aria-busy={gravando}>
              Registrar
            </button>
          </div>
        </form>
      )}
      {bem.manutencoes.length > 0 && (
        <div className="grid-rolante">
          <table className="tabela" id="manutencao-lista">
            <thead>
              <tr>
                <th>Data</th><th>Tipo</th><th>Feito por</th><th className="num">Custo</th>
                <th>O que foi feito</th><th>Registrado por</th>{podeRegistrar && <th />}
              </tr>
            </thead>
            <tbody>
              {bem.manutencoes.map((x) => (
                <tr key={x.id}>
                  <td>{dataBr(x.data)}</td>
                  <td>{x.tipo_txt}</td>
                  <td>{x.executado_por ?? "—"}</td>
                  <td className="num">{x.custo !== null ? reais(x.custo) : "—"}</td>
                  <td className="text-[13.5px]">{x.descricao ?? "—"}</td>
                  <td className="text-[13px] text-suave">{x.registrado_por ?? "—"}</td>
                  {podeRegistrar && (
                    <td>
                      <button type="button" className="link-acao text-[13px]"
                              onClick={() => void tirar(x.id)}>apagar</button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Cartao>
  );
}
