"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro from "@/components/busca-cadastro";
import { Aviso, Campo, Carregando, Modal, SeletorDeArquivo } from "@/components/ui";
import { fontePessoas } from "@/lib/busca-cadastro";
import {
  agendarContas,
  alterarCategoria,
  anexarComprovante,
  Categoria,
  comprovanteDaConta,
  Conta,
  corrigirConta,
  criarCategoria,
  Forma,
  FORMAS,
  hojeIso,
  lancarConta,
  lancarEquipe,
  pagarContas,
  ultimoDaPessoa,
} from "@/lib/contas-pagar";
import { reduzirFoto } from "@/lib/imagem";
import { textoParaNumero, reais } from "@/lib/numeros";

/**
 * As janelas das contas a pagar (migração 163). Cada uma faz UMA coisa: lançar (ou corrigir),
 * lançar a equipe do dia, agendar, pagar (com comprovante), ver o comprovante e as categorias.
 */

const paraCampo = (v: number | string | null | undefined) =>
  v === null || v === undefined || v === "" ? "" : Number(v).toFixed(2).replace(".", ",");

function SeletorCategoria({ categorias, valor, aoMudar, id }: {
  categorias: Categoria[]; valor: number | null; aoMudar: (v: number | null) => void; id?: string;
}) {
  return (
    <select className="campo" id={id} value={valor ?? ""}
            onChange={(e) => aoMudar(e.target.value ? Number(e.target.value) : null)}>
      <option value="">Sem categoria</option>
      {categorias.filter((c) => c.ativo || c.id === valor).map((c) => (
        <option key={c.id} value={c.id}>{c.nome}</option>
      ))}
    </select>
  );
}

function SeletorForma({ valor, aoMudar, id }: { valor: Forma; aoMudar: (f: Forma) => void; id?: string }) {
  return (
    <select className="campo" id={id} value={valor} onChange={(e) => aoMudar(e.target.value as Forma)}>
      {(Object.keys(FORMAS) as Forma[]).map((f) => <option key={f} value={f}>{FORMAS[f]}</option>)}
    </select>
  );
}

/** Nova conta, ou corrigir uma que ainda não foi paga. */
export function JanelaConta({ conta, categorias, aoFechar, aoSalvar }: {
  conta: Conta | null; categorias: Categoria[]; aoFechar: () => void; aoSalvar: (m: string) => void;
}) {
  const fonte = useMemo(() => fontePessoas(), []);
  const freelancer = categorias.find((c) => c.nome.toLowerCase() === "freelancer")?.id ?? null;
  const [pessoa, setPessoa] = useState<{ id: number; rotulo: string } | null>(
    conta ? { id: conta.id_pessoa, rotulo: conta.pessoa } : null);
  const [categoria, setCategoria] = useState<number | null>(conta ? conta.id_categoria : freelancer);
  const [descricao, setDescricao] = useState(conta?.descricao ?? "");
  const [funcao, setFuncao] = useState(conta?.funcao ?? "");
  const [competencia, setCompetencia] = useState(conta?.competencia ?? hojeIso());
  const [vencimento, setVencimento] = useState(conta?.vencimento ?? hojeIso());
  const [valor, setValor] = useState(paraCampo(conta?.valor));
  const [obs, setObs] = useState(conta?.observacao ?? "");
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function escolherPessoa(id: number, rotulo: string) {
    setPessoa({ id, rotulo });
    if (conta) return;
    // O último lançamento da pessoa preenche valor, função e categoria — a diária de sempre.
    const u = await ultimoDaPessoa(id).catch(() => ({} as Awaited<ReturnType<typeof ultimoDaPessoa>>));
    if (u.valor && !valor) setValor(paraCampo(u.valor));
    if (u.funcao && !funcao) setFuncao(u.funcao);
    if (u.id_categoria) setCategoria(u.id_categoria);
  }

  async function salvar(e?: FormEvent) {
    e?.preventDefault();
    const n = textoParaNumero(valor);
    if (!pessoa) return setErro("Escolha a pessoa.");
    if (!descricao.trim()) return setErro("Diga o que é (a descrição).");
    if (!n || n <= 0) return setErro("Informe o valor.");
    setOcupado(true);
    try {
      const corpo = { id_pessoa: pessoa.id, id_categoria: categoria, descricao: descricao.trim(),
                      funcao: funcao.trim() || null, competencia, vencimento, valor: n,
                      observacao: obs.trim() || null };
      const r = conta ? await corrigirConta(conta.id, corpo) : await lancarConta(corpo);
      aoSalvar(r.message);
    } catch (x) {
      setErro(x instanceof Error ? x.message : "Não foi possível salvar");
      setOcupado(false);
    }
  }

  return (
    <Modal titulo={conta ? `Corrigir conta nº ${conta.id}` : "Nova conta a pagar"} aoFechar={aoFechar} largura="640px"
           rodape={<div className="flex justify-end gap-2">
             <button type="button" className="btn" onClick={aoFechar}>Cancelar</button>
             <button type="button" className="btn btn-primario" id="conta-salvar" disabled={ocupado}
                     onClick={() => void salvar()}>{conta ? "Salvar" : "Lançar"}</button>
           </div>}>
      <form onSubmit={salvar} className="grid gap-4 sm:grid-cols-2">
        {erro && <div className="sm:col-span-2"><Aviso tipo="erro">{erro}</Aviso></div>}
        <Campo rotulo="Pessoa" className="sm:col-span-2">
          <BuscaCadastro id="conta-pessoa" fonte={fonte} selecionado={pessoa}
                         aoEscolher={(p) => (p ? void escolherPessoa(p.id, p.nome) : setPessoa(null))} />
        </Campo>
        <Campo rotulo="Categoria">
          <SeletorCategoria id="conta-categoria" categorias={categorias} valor={categoria} aoMudar={setCategoria} />
        </Campo>
        <Campo rotulo="Função" opcional>
          <input className="campo" id="conta-funcao" maxLength={60} placeholder="Ex.: garçom, cozinha"
                 value={funcao} onChange={(e) => setFuncao(e.target.value)} />
        </Campo>
        <Campo rotulo="O que é" className="sm:col-span-2">
          <input className="campo" id="conta-descricao" maxLength={200} placeholder="Ex.: diária do sábado, conserto da coifa"
                 value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        </Campo>
        <Campo rotulo="Competência" dica="o dia do trabalho ou do serviço">
          <input type="date" className="campo" id="conta-competencia" value={competencia}
                 onChange={(e) => setCompetencia(e.target.value)} />
        </Campo>
        <Campo rotulo="Vencimento">
          <input type="date" className="campo" id="conta-vencimento" value={vencimento}
                 onChange={(e) => setVencimento(e.target.value)} />
        </Campo>
        <Campo rotulo="Valor">
          <input className="campo text-right" id="conta-valor" inputMode="decimal" placeholder="0,00"
                 value={valor} onFocus={(e) => e.target.select()} onChange={(e) => setValor(e.target.value)} />
        </Campo>
        <Campo rotulo="Observação" opcional>
          <input className="campo" maxLength={300} value={obs} onChange={(e) => setObs(e.target.value)} />
        </Campo>
      </form>
    </Modal>
  );
}

type LinhaEquipe = { id: number; rotulo: string; valor: string; funcao: string };

/** A equipe do dia: uma conta por pessoa, de uma vez. */
export function JanelaEquipe({ categorias, aoFechar, aoSalvar }: {
  categorias: Categoria[]; aoFechar: () => void; aoSalvar: (m: string) => void;
}) {
  const fonte = useMemo(() => fontePessoas(), []);
  const freelancer = categorias.find((c) => c.nome.toLowerCase() === "freelancer")?.id ?? null;
  const [data, setData] = useState(hojeIso());
  const [vencimento, setVencimento] = useState(hojeIso());
  const [descricao, setDescricao] = useState("Diária");
  const [categoria, setCategoria] = useState<number | null>(freelancer);
  const [linhas, setLinhas] = useState<LinhaEquipe[]>([]);
  const [rodada, setRodada] = useState(0);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function acrescentar(id: number, rotulo: string) {
    setRodada((n) => n + 1);
    if (linhas.some((l) => l.id === id)) return setErro(`${rotulo} já está na equipe.`);
    setErro("");
    const u = await ultimoDaPessoa(id).catch(() => ({} as Awaited<ReturnType<typeof ultimoDaPessoa>>));
    setLinhas((ls) => [...ls, { id, rotulo, valor: paraCampo(u.valor), funcao: u.funcao ?? "" }]);
  }
  const mudar = (id: number, parte: Partial<LinhaEquipe>) =>
    setLinhas((ls) => ls.map((l) => (l.id === id ? { ...l, ...parte } : l)));
  const total = linhas.reduce((s, l) => s + (textoParaNumero(l.valor) ?? 0), 0);

  async function salvar() {
    if (!linhas.length) return setErro("Acrescente quem trabalhou.");
    const ruim = linhas.find((l) => !(textoParaNumero(l.valor) ?? 0));
    if (ruim) return setErro(`Informe o valor de ${ruim.rotulo}.`);
    setOcupado(true);
    try {
      const r = await lancarEquipe({
        data, vencimento, id_categoria: categoria, descricao: descricao.trim() || "Diária",
        itens: linhas.map((l) => ({ id_pessoa: l.id, valor: textoParaNumero(l.valor)!, funcao: l.funcao.trim() || null })),
      });
      aoSalvar(r.message);
    } catch (x) {
      setErro(x instanceof Error ? x.message : "Não foi possível lançar a equipe");
      setOcupado(false);
    }
  }

  return (
    <Modal titulo="Lançar a equipe do dia" aoFechar={aoFechar} largura="760px"
           rodape={<div className="flex flex-wrap items-center justify-end gap-3">
             <span className="mr-auto text-[14px]">{linhas.length} pessoa(s) · <b>{reais(total)}</b></span>
             <button type="button" className="btn" onClick={aoFechar}>Cancelar</button>
             <button type="button" className="btn btn-primario" id="equipe-lancar" disabled={ocupado}
                     onClick={() => void salvar()}>Lançar {linhas.length || ""}</button>
           </div>}>
      <div className="flex flex-col gap-4" id="equipe-janela">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="grid gap-3 sm:grid-cols-4">
          <Campo rotulo="Dia do trabalho">
            <input type="date" className="campo" id="equipe-data" value={data} onChange={(e) => setData(e.target.value)} />
          </Campo>
          <Campo rotulo="Vence em">
            <input type="date" className="campo" id="equipe-vencimento" value={vencimento}
                   onChange={(e) => setVencimento(e.target.value)} />
          </Campo>
          <Campo rotulo="Categoria">
            <SeletorCategoria categorias={categorias} valor={categoria} aoMudar={setCategoria} />
          </Campo>
          <Campo rotulo="O que é">
            <input className="campo" maxLength={200} value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          </Campo>
        </div>
        <Campo rotulo="Acrescentar pessoa">
          <BuscaCadastro key={rodada} id="equipe-pessoa" fonte={fonte} selecionado={null}
                         aoEscolher={(p) => { if (p) void acrescentar(p.id, p.nome); }} />
        </Campo>
        {!!linhas.length && (
          <ul className="divide-y divide-[var(--borda)]" id="equipe-linhas">
            {linhas.map((l) => (
              <li key={l.id} data-equipe-pessoa={l.id} className="flex flex-wrap items-center gap-2 py-2">
                <span className="min-w-[10rem] flex-1 font-semibold">{l.rotulo}</span>
                <input className="campo w-36" maxLength={60} placeholder="função" aria-label={`função de ${l.rotulo}`}
                       value={l.funcao} onChange={(e) => mudar(l.id, { funcao: e.target.value })} />
                <input className="campo w-28 text-right" inputMode="decimal" placeholder="valor"
                       aria-label={`valor de ${l.rotulo}`} data-equipe-valor value={l.valor}
                       onFocus={(e) => e.target.select()} onChange={(e) => mudar(l.id, { valor: e.target.value })} />
                <button type="button" className="btn btn-terciario btn-pequeno"
                        onClick={() => setLinhas((ls) => ls.filter((x) => x.id !== l.id))}>tirar</button>
              </li>
            ))}
          </ul>
        )}
        <p className="text-[13px] text-suave">
          O valor e a função vêm do último lançamento de cada pessoa. Cada uma vira uma conta a pagar.
        </p>
      </div>
    </Modal>
  );
}

export function JanelaAgendar({ contas, aoFechar, aoSalvar }: {
  contas: Conta[]; aoFechar: () => void; aoSalvar: (m: string) => void;
}) {
  const [data, setData] = useState(contas[0]?.vencimento ?? hojeIso());
  const [forma, setForma] = useState<Forma>("PIX");
  const [automatica, setAutomatica] = useState(true);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const total = contas.reduce((s, c) => s + Number(c.valor), 0);

  async function salvar() {
    setOcupado(true);
    try {
      const r = await agendarContas(contas.map((c) => c.id), data, forma, automatica);
      aoSalvar(r.message);
    } catch (x) {
      setErro(x instanceof Error ? x.message : "Não foi possível agendar");
      setOcupado(false);
    }
  }

  return (
    <Modal titulo={`Agendar ${contas.length} conta(s) — ${reais(total)}`} aoFechar={aoFechar} largura="480px"
           rodape={<div className="flex justify-end gap-2">
             <button type="button" className="btn" onClick={aoFechar}>Cancelar</button>
             <button type="button" className="btn btn-primario" id="agendar-confirmar" disabled={ocupado}
                     onClick={() => void salvar()}>Agendar</button>
           </div>}>
      <div className="flex flex-col gap-3">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="grid grid-cols-2 gap-3">
          <Campo rotulo="Pagamento agendado para">
            <input type="date" className="campo" id="agendar-data" value={data} onChange={(e) => setData(e.target.value)} />
          </Campo>
          <Campo rotulo="Forma">
            <SeletorForma id="agendar-forma" valor={forma} aoMudar={setForma} />
          </Campo>
        </div>
        <label className="flex items-start gap-2 text-[14px]">
          <input type="checkbox" className="mt-1 h-4 w-4" id="agendar-automatica" checked={automatica}
                 onChange={(e) => setAutomatica(e.target.checked)} />
          <span>Dar baixa sozinho na data
            <span className="block text-[12.5px] text-suave">
              O sistema marca como pago no dia agendado. Ele não confere o banco: se o pagamento não
              sair, estorne a baixa.
            </span>
          </span>
        </label>
      </div>
    </Modal>
  );
}

export function JanelaPagar({ contas, aoFechar, aoSalvar }: {
  contas: Conta[]; aoFechar: () => void; aoSalvar: (m: string) => void;
}) {
  const aviso = useAviso();
  const uma = contas.length === 1;
  const [data, setData] = useState(hojeIso());
  const [forma, setForma] = useState<Forma>((contas[0]?.forma as Forma) ?? "PIX");
  const [valor, setValor] = useState(uma ? paraCampo(contas[0].valor) : "");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const total = contas.reduce((s, c) => s + Number(c.valor), 0);
  const pessoas = [...new Set(contas.map((c) => c.pessoa))];
  const pix = uma || pessoas.length === 1 ? contas[0].chave_pix : null;

  async function salvar() {
    const n = uma ? textoParaNumero(valor) : null;
    if (uma && (n === null || n < 0)) return setErro("Informe o valor pago.");
    setOcupado(true);
    try {
      const ids = contas.map((c) => c.id);
      const r = await pagarContas(ids, data, forma,
        uma && n !== null && Math.abs(n - Number(contas[0].valor)) >= 0.005 ? n : null);
      if (arquivo) {
        const enviar = arquivo.type === "application/pdf" ? arquivo : await reduzirFoto(arquivo);
        await anexarComprovante(ids, enviar).catch((x) =>
          aviso.erro(`Pago, mas o comprovante não foi: ${x instanceof Error ? x.message : x}`));
      }
      aoSalvar(r.message + (arquivo ? " · comprovante anexado" : ""));
    } catch (x) {
      setErro(x instanceof Error ? x.message : "Não foi possível pagar");
      setOcupado(false);
    }
  }

  return (
    <Modal titulo={`Pagar ${contas.length} conta(s) — ${reais(total)}`} aoFechar={aoFechar} largura="520px"
           rodape={<div className="flex justify-end gap-2">
             <button type="button" className="btn" onClick={aoFechar}>Cancelar</button>
             <button type="button" className="btn btn-primario" id="pagar-confirmar" disabled={ocupado}
                     onClick={() => void salvar()}>{ocupado ? "Pagando…" : "Confirmar pagamento"}</button>
           </div>}>
      <div className="flex flex-col gap-3">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <p className="text-[14px]">
          {pessoas.join(", ")}
          {pix && <span className="block text-[13px] text-suave">Pix: <span className="mono">{pix}</span></span>}
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Campo rotulo="Pago em">
            <input type="date" className="campo" id="pagar-data" value={data} max={hojeIso()}
                   onChange={(e) => setData(e.target.value)} />
          </Campo>
          <Campo rotulo="Forma">
            <SeletorForma id="pagar-forma" valor={forma} aoMudar={setForma} />
          </Campo>
          {uma && (
            <Campo rotulo="Valor pago" dica="se diferente: juros ou desconto">
              <input className="campo text-right" id="pagar-valor" inputMode="decimal" value={valor}
                     onFocus={(e) => e.target.select()} onChange={(e) => setValor(e.target.value)} />
            </Campo>
          )}
        </div>
        <Campo rotulo="Comprovante" opcional>
          <SeletorDeArquivo id="pagar-comprovante" accept="image/*,application/pdf" arquivo={arquivo}
                            onEscolher={setArquivo} rotulo="Anexar foto ou PDF" />
        </Campo>
        {contas.length > 1 && (
          <p className="text-[12.5px] text-suave">Cada conta é paga pelo valor dela; o comprovante vale para todas.</p>
        )}
      </div>
    </Modal>
  );
}

/** Anexar (ou trocar) o comprovante de contas já pagas. */
export function JanelaAnexar({ contas, aoFechar, aoSalvar }: {
  contas: Conta[]; aoFechar: () => void; aoSalvar: (m: string) => void;
}) {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  async function salvar() {
    if (!arquivo) return setErro("Escolha a foto ou o PDF do comprovante.");
    setOcupado(true);
    try {
      const enviar = arquivo.type === "application/pdf" ? arquivo : await reduzirFoto(arquivo);
      const r = await anexarComprovante(contas.map((c) => c.id), enviar);
      aoSalvar(r.message);
    } catch (x) {
      setErro(x instanceof Error ? x.message : "Não foi possível anexar");
      setOcupado(false);
    }
  }
  return (
    <Modal titulo="Anexar comprovante" aoFechar={aoFechar} largura="460px"
           rodape={<div className="flex justify-end gap-2">
             <button type="button" className="btn" onClick={aoFechar}>Cancelar</button>
             <button type="button" className="btn btn-primario" id="anexar-confirmar" disabled={ocupado}
                     onClick={() => void salvar()}>Anexar</button>
           </div>}>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      <SeletorDeArquivo id="anexar-comprovante" accept="image/*,application/pdf" arquivo={arquivo}
                        onEscolher={setArquivo} rotulo="Escolher foto ou PDF" />
      <p className="mt-2 text-[12.5px] text-suave">Vale para {contas.length} conta(s). Troca o anexo anterior.</p>
    </Modal>
  );
}

export function JanelaComprovante({ conta, aoFechar }: { conta: Conta; aoFechar: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [erro, setErro] = useState("");
  useEffect(() => {
    let aberta: string | null = null;
    comprovanteDaConta(conta.id)
      .then((u) => { aberta = u; setUrl(u); })
      .catch((e) => setErro(e instanceof Error ? e.message : "Não foi possível abrir o comprovante"));
    return () => { if (aberta) URL.revokeObjectURL(aberta); };
  }, [conta.id]);
  return (
    <Modal titulo={`Comprovante — ${conta.pessoa}`} aoFechar={aoFechar} largura="820px">
      {erro ? <Aviso tipo="erro">{erro}</Aviso>
        // ⚠️ iframe serve para foto e para PDF: o tipo só se sabe depois de baixar.
        : url ? <iframe src={url} title="comprovante" id="comprovante-quadro" className="h-[70vh] w-full rounded border border-linha" />
          : <Carregando />}
    </Modal>
  );
}

export function JanelaCategorias({ categorias, aoFechar, aoMudar }: {
  categorias: Categoria[]; aoFechar: () => void; aoMudar: () => void;
}) {
  const aviso = useAviso();
  const [nova, setNova] = useState("");
  async function criar() {
    if (!nova.trim()) return;
    try {
      aviso.sucesso((await criarCategoria(nova.trim())).message);
      setNova("");
      aoMudar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível criar");
    }
  }
  async function alternar(c: Categoria) {
    try {
      await alterarCategoria(c.id, c.nome, !c.ativo);
      aoMudar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível alterar");
    }
  }
  return (
    <Modal titulo="Categorias das contas a pagar" aoFechar={aoFechar} largura="480px">
      <ul className="divide-y divide-[var(--borda)]" id="categorias-lista">
        {categorias.map((c) => (
          <li key={c.id} className="flex items-center justify-between py-2">
            <span className={c.ativo ? "" : "text-suave line-through"}>{c.nome}</span>
            <button type="button" className="btn btn-terciario btn-pequeno" onClick={() => void alternar(c)}>
              {c.ativo ? "desativar" : "reativar"}
            </button>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <input className="campo" id="categoria-nova" maxLength={60} placeholder="nova categoria"
               value={nova} onChange={(e) => setNova(e.target.value)}
               onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); void criar(); } }} />
        <button type="button" className="btn btn-secundario" onClick={() => void criar()}>Criar</button>
      </div>
    </Modal>
  );
}
