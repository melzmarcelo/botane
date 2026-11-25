"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro from "@/components/busca-cadastro";
import BotaoExportar from "@/components/exportar";
import { Aviso, Campo, Carregando, Confirmacao, Modal, Vazio } from "@/components/ui";
import { fontePessoas } from "@/lib/busca-cadastro";
import {
  alterarFixa,
  Categoria,
  ContaFixa,
  criarFixa,
  dataBr,
  encerrarFixa,
  Forma,
  FORMAS,
  hojeIso,
  listarFixas,
  NovaContaFixa,
  reativarFixa,
} from "@/lib/contas-pagar";
import { reais, textoParaNumero } from "@/lib/numeros";

/**
 * Contas fixas (etapa 3 do Financeiro, migração 167): o aluguel, a internet, a luz. Cada uma é
 * um molde, e a conta de cada mês nasce sozinha em Contas a pagar alguns dias antes do vencimento.
 *
 * ⚠️ Mudar a conta fixa vale para os meses que ainda não nasceram; a já gerada se corrige nela.
 */

const mesBr = (iso: string | null) => (iso ? `${iso.slice(5, 7)}/${iso.slice(0, 4)}` : "");

export function JanelaFixas({ categorias, podeLancar, aoFechar }: {
  categorias: Categoria[]; podeLancar: boolean; aoFechar: (mudou: boolean) => void;
}) {
  const aviso = useAviso();
  const [lista, setLista] = useState<ContaFixa[] | null>(null);
  const [encerradas, setEncerradas] = useState(false);
  const [erro, setErro] = useState("");
  const [editando, setEditando] = useState<ContaFixa | "nova" | null>(null);
  const [encerrando, setEncerrando] = useState<ContaFixa | null>(null);
  const [cancelarAbertas, setCancelarAbertas] = useState(false);
  const [mudou, setMudou] = useState(false);

  const carregar = useCallback(() => {
    setErro("");
    listarFixas(encerradas).then(setLista)
      .catch((e) => { setLista([]); setErro(e instanceof Error ? e.message : "Falha ao carregar"); });
  }, [encerradas]);
  useEffect(() => { carregar(); }, [carregar]);

  const depois = (m: string) => { aviso.sucesso(m); setMudou(true); setEditando(null); carregar(); };
  const total = (lista ?? []).filter((f) => f.ativo).reduce((s, f) => s + Number(f.valor), 0);

  async function encerrar() {
    if (!encerrando) return;
    try {
      depois((await encerrarFixa(encerrando.id, cancelarAbertas)).message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível encerrar");
    }
    setEncerrando(null);
    setCancelarAbertas(false);
  }

  async function reativar(f: ContaFixa) {
    try {
      depois((await reativarFixa(f.id)).message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reativar");
    }
  }

  if (editando) {
    return <FormFixa fixa={editando === "nova" ? null : editando} categorias={categorias}
                     aoVoltar={() => setEditando(null)} aoSalvar={depois} />;
  }

  return (
    <Modal titulo="Contas fixas" aoFechar={() => aoFechar(mudou)} largura="820px"
           rodape={<div className="flex flex-wrap items-center justify-end gap-2">
             <span className="mr-auto text-[13.5px]">Ativas somam <b>{reais(total)}</b> por mês</span>
             <BotaoExportar relatorio="contas-fixas" />
             {podeLancar && (
               <button type="button" className="btn btn-primario" id="fixa-nova" onClick={() => setEditando("nova")}>
                 Nova conta fixa
               </button>
             )}
           </div>}>
      <div className="flex flex-col gap-3" id="fixas-janela">
        <p className="text-[13.5px] text-suave">
          Aluguel, internet, luz: a conta de cada mês nasce sozinha em Contas a pagar, alguns dias
          antes do vencimento. Depois é uma conta como outra qualquer: corrige, agenda, paga.
        </p>
        <label className="flex items-center gap-2 text-[13.5px]">
          <input type="checkbox" className="h-4 w-4" id="fixas-encerradas" checked={encerradas}
                 onChange={(e) => setEncerradas(e.target.checked)} />
          mostrar as encerradas
        </label>
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {!lista ? <Carregando /> : !lista.length ? (
          <Vazio>Nenhuma conta fixa ainda. Cadastre o aluguel, a internet, a luz…</Vazio>
        ) : (
          <ul className="divide-y divide-[var(--borda)]" id="fixas-lista">
            {lista.map((f) => (
              <li key={f.id} data-fixa={f.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3">
                <div className="min-w-[14rem] flex-1">
                  <p className={`font-semibold ${f.ativo ? "" : "text-suave line-through"}`}>
                    {f.descricao} <span className="font-normal text-suave">· {f.pessoa}</span>
                  </p>
                  <p className="text-[12.5px] text-suave">
                    todo dia {f.dia_vencimento}
                    {f.categoria ? ` · ${f.categoria}` : ""}
                    {f.agendar ? ` · débito automático (${FORMAS[f.forma as Forma] ?? ""})` : ""}
                    {f.fim ? ` · até ${mesBr(f.fim)}` : ""}
                    {f.em_aberto > 0 ? ` · ${f.em_aberto} em aberto` : ""}
                  </p>
                  <p className="text-[12.5px]" data-fixa-proxima>
                    {!f.ativo ? <span className="text-suave">encerrada</span>
                      : f.proxima ? <>próxima: vence {dataBr(f.proxima.vencimento)}
                          <span className="text-suave"> · nasce em {dataBr(f.proxima.gera_em)}</span></>
                        : <span className="text-suave">sem próximos meses (chegou ao fim)</span>}
                  </p>
                </div>
                <span className="mono font-semibold">
                  {reais(Number(f.valor))}
                  {f.valor_variavel && <span className="block text-right text-[11.5px] font-normal text-suave">previsto</span>}
                </span>
                {podeLancar && (
                  <span className="flex gap-1">
                    {f.ativo ? (
                      <>
                        <button type="button" className="btn btn-terciario btn-pequeno" data-acao="editar-fixa"
                                onClick={() => setEditando(f)}>Editar</button>
                        <button type="button" className="btn btn-terciario btn-pequeno" data-acao="encerrar-fixa"
                                onClick={() => setEncerrando(f)}>Encerrar</button>
                      </>
                    ) : (
                      <button type="button" className="btn btn-secundario btn-pequeno" data-acao="reativar-fixa"
                              onClick={() => void reativar(f)}>Reativar</button>
                    )}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
      {encerrando && (
        <Confirmacao titulo="Encerrar esta conta fixa?" rotuloConfirmar="Encerrar" rotuloCancelar="Voltar" perigo
                     aoConfirmar={() => void encerrar()}
                     aoCancelar={() => { setEncerrando(null); setCancelarAbertas(false); }}>
          <p>{encerrando.descricao} deixa de gerar contas. As já geradas continuam em Contas a pagar.</p>
          {encerrando.em_aberto > 0 && (
            <label className="mt-3 flex items-start gap-2 text-[14px]">
              <input type="checkbox" className="mt-1 h-4 w-4" id="fixa-cancelar-abertas" checked={cancelarAbertas}
                     onChange={(e) => setCancelarAbertas(e.target.checked)} />
              <span>Cancelar também as que estão em aberto e ainda não venceram
                <span className="block text-[12.5px] text-suave">As atrasadas ficam: são dívida de verdade.</span>
              </span>
            </label>
          )}
        </Confirmacao>
      )}
    </Modal>
  );
}

function FormFixa({ fixa, categorias, aoVoltar, aoSalvar }: {
  fixa: ContaFixa | null; categorias: Categoria[]; aoVoltar: () => void; aoSalvar: (m: string) => void;
}) {
  const fonte = useMemo(() => fontePessoas(), []);
  const [pessoa, setPessoa] = useState<{ id: number; rotulo: string } | null>(
    fixa ? { id: fixa.id_pessoa, rotulo: fixa.pessoa } : null);
  const [categoria, setCategoria] = useState<number | null>(fixa?.id_categoria ?? null);
  const [descricao, setDescricao] = useState(fixa?.descricao ?? "");
  const [valor, setValor] = useState(fixa ? Number(fixa.valor).toFixed(2).replace(".", ",") : "");
  const [variavel, setVariavel] = useState(fixa?.valor_variavel ?? false);
  const [dia, setDia] = useState(String(fixa?.dia_vencimento ?? 10));
  const [inicio, setInicio] = useState((fixa?.inicio ?? hojeIso()).slice(0, 7));
  const [fim, setFim] = useState(fixa?.fim ? fixa.fim.slice(0, 7) : "");
  const [antecedencia, setAntecedencia] = useState(String(fixa?.antecedencia_dias ?? 10));
  const [agendar, setAgendar] = useState(fixa?.agendar ?? false);
  const [forma, setForma] = useState<Forma>(fixa?.forma ?? "BOLETO");
  const [obs, setObs] = useState(fixa?.observacao ?? "");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function salvar() {
    const n = textoParaNumero(valor);
    const d = Number(dia);
    const a = Number(antecedencia);
    if (!pessoa) return setErro("Escolha a pessoa (a quem se paga).");
    if (!descricao.trim()) return setErro("Diga o que é: aluguel, internet, luz…");
    if (!n || n <= 0) return setErro("Informe o valor.");
    if (!Number.isInteger(d) || d < 1 || d > 31) return setErro("O dia do vencimento vai de 1 a 31.");
    if (!Number.isInteger(a) || a < 0 || a > 60) return setErro("A antecedência vai de 0 a 60 dias.");
    if (!inicio) return setErro("Escolha o primeiro mês.");
    if (fim && fim < inicio) return setErro("O último mês vem antes do primeiro.");
    setOcupado(true);
    const corpo: NovaContaFixa = {
      id_pessoa: pessoa.id, id_categoria: categoria, descricao: descricao.trim(), valor: n,
      valor_variavel: variavel, dia_vencimento: d, inicio: `${inicio}-01`, fim: fim ? `${fim}-01` : null,
      antecedencia_dias: a, agendar, forma: agendar ? forma : null, observacao: obs.trim() || null,
    };
    try {
      aoSalvar((fixa ? await alterarFixa(fixa.id, corpo) : await criarFixa(corpo)).message);
    } catch (x) {
      setErro(x instanceof Error ? x.message : "Não foi possível salvar");
      setOcupado(false);
    }
  }

  return (
    <Modal titulo={fixa ? `Editar ${fixa.descricao}` : "Nova conta fixa"} aoFechar={aoVoltar} largura="640px"
           rodape={<div className="flex justify-end gap-2">
             <button type="button" className="btn" onClick={aoVoltar}>Voltar</button>
             <button type="button" className="btn btn-primario" id="fixa-salvar" disabled={ocupado}
                     onClick={() => void salvar()}>{fixa ? "Salvar" : "Criar"}</button>
           </div>}>
      <div className="grid gap-4 sm:grid-cols-2" id="fixa-form">
        {erro && <div className="sm:col-span-2"><Aviso tipo="erro">{erro}</Aviso></div>}
        {fixa && (
          <p className="text-[13px] text-suave sm:col-span-2">
            Vale para os meses que ainda não nasceram. A conta já gerada se corrige nela, em Contas a pagar.
          </p>
        )}
        <Campo rotulo="Pessoa" className="sm:col-span-2">
          <BuscaCadastro id="fixa-pessoa" fonte={fonte} selecionado={pessoa}
                         aoEscolher={(p) => setPessoa(p ? { id: p.id, rotulo: p.nome } : null)} />
        </Campo>
        <Campo rotulo="O que é">
          <input className="campo" id="fixa-descricao" maxLength={180} placeholder="Ex.: aluguel da loja, internet"
                 value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        </Campo>
        <Campo rotulo="Categoria">
          <select className="campo" id="fixa-categoria" value={categoria ?? ""}
                  onChange={(e) => setCategoria(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Sem categoria</option>
            {categorias.filter((c) => c.ativo || c.id === categoria).map((c) => (
              <option key={c.id} value={c.id}>{c.nome}</option>
            ))}
          </select>
        </Campo>
        <Campo rotulo="Valor por mês">
          <input className="campo text-right" id="fixa-valor" inputMode="decimal" placeholder="0,00"
                 value={valor} onFocus={(e) => e.target.select()} onChange={(e) => setValor(e.target.value)} />
        </Campo>
        <Campo rotulo="Vence todo dia" dica="31 em mês curto vence no último dia">
          <input className="campo text-right" id="fixa-dia" inputMode="numeric" value={dia}
                 onFocus={(e) => e.target.select()} onChange={(e) => setDia(e.target.value.replace(/\D/g, "").slice(0, 2))} />
        </Campo>
        <label className="flex items-start gap-2 text-[14px] sm:col-span-2">
          <input type="checkbox" className="mt-1 h-4 w-4" id="fixa-variavel" checked={variavel}
                 onChange={(e) => setVariavel(e.target.checked)} />
          <span>O valor muda todo mês (luz, água, gás)
            <span className="block text-[12.5px] text-suave">A conta nasce com este valor como previsão e avisa para corrigir quando a fatura chegar.</span>
          </span>
        </label>
        <Campo rotulo="Primeiro mês">
          <input type="month" className="campo" id="fixa-inicio" value={inicio} onChange={(e) => setInicio(e.target.value)} />
        </Campo>
        <Campo rotulo="Último mês" opcional dica="vazio = sem fim">
          <input type="month" className="campo" id="fixa-fim" value={fim} min={inicio} onChange={(e) => setFim(e.target.value)} />
        </Campo>
        <Campo rotulo="Nasce quantos dias antes" dica="do vencimento">
          <input className="campo text-right" id="fixa-antecedencia" inputMode="numeric" value={antecedencia}
                 onFocus={(e) => e.target.select()}
                 onChange={(e) => setAntecedencia(e.target.value.replace(/\D/g, "").slice(0, 2))} />
        </Campo>
        <Campo rotulo="Observação" opcional>
          <input className="campo" maxLength={300} value={obs} onChange={(e) => setObs(e.target.value)} />
        </Campo>
        <label className="flex items-start gap-2 text-[14px] sm:col-span-2">
          <input type="checkbox" className="mt-1 h-4 w-4" id="fixa-agendar" checked={agendar}
                 onChange={(e) => setAgendar(e.target.checked)} />
          <span>Débito automático: já nasce agendada para o vencimento, com baixa sozinha na data
            <span className="block text-[12.5px] text-suave">Como no agendamento à mão, o sistema não confere o banco: se não sair, estorne a baixa.</span>
          </span>
        </label>
        {agendar && (
          <Campo rotulo="Forma do débito">
            <select className="campo" id="fixa-forma" value={forma} onChange={(e) => setForma(e.target.value as Forma)}>
              {(Object.keys(FORMAS) as Forma[]).map((f) => <option key={f} value={f}>{FORMAS[f]}</option>)}
            </select>
          </Campo>
        )}
      </div>
    </Modal>
  );
}
