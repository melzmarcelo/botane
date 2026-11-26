"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro from "@/components/busca-cadastro";
import { Aviso, Campo, Modal } from "@/components/ui";
import { fonteProdutos } from "@/lib/busca-cadastro";
import { qtd, textoParaNumero } from "@/lib/numeros";
import {
  AbaOrdem,
  FILTRO_COMPRADOS,
  NovoItem,
  OpcoesDoProduto,
  opcoesDoProduto,
  pedirItem,
  rotuloUrgencia,
  unidadesDeMedida,
  Urgencia,
  URGENCIAS,
} from "@/lib/ordens-compra";

/**
 * O pedido em quatro perguntas numeradas (modelo "versão didática" do dono, 24/11/2026): qual
 * produto, quanto, para quando e uma observação. O resumo embaixo lê o pedido de volta antes
 * de enviar.
 *
 * 🔑 **Continua tudo pelo teclado**: produto, Tab, quantidade, observação, Enter. Na observação
 * o Enter envia e Shift+Enter quebra a linha. Ao gravar, o foco volta para o produto.
 * 🔑 **Aprovação** (migração 165): sem `compras.ordem_aprovar`, o pedido vai para "Aguardando
 * aprovação". Somar só se oferece na linha da MESMA situação de quem pede (a API repete a regra).
 */
export default function FormPedido({ aoPedir, podeAprovar }: {
  aoPedir: (status?: AbaOrdem) => void;
  podeAprovar: boolean;
}) {
  const aviso = useAviso();
  const fonte = useMemo(() => fonteProdutos(FILTRO_COMPRADOS), []);
  const [produto, setProduto] = useState<{ id: number; rotulo: string; nome: string } | null>(null);
  const [opcoes, setOpcoes] = useState<OpcoesDoProduto | null>(null);
  const [foraDoCadastro, setForaDoCadastro] = useState(false);
  const [descricao, setDescricao] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [um, setUm] = useState("");
  const [urgencia, setUrgencia] = useState<Urgencia>("SEMANA");
  const [observacao, setObservacao] = useState("");
  const [siglas, setSiglas] = useState<string[]>([]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [repetido, setRepetido] = useState<{ corpo: NovoItem; id: number; frase: string } | null>(null);
  // Remonta a busca ao limpar: é ela quem guarda o texto digitado.
  const [rodada, setRodada] = useState(0);
  const campoQtd = useRef<HTMLInputElement>(null);
  const formulario = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (!foraDoCadastro || siglas.length) return;
    unidadesDeMedida()
      .then((l) => setSiglas(l.map((u) => u.sigla)))
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar as unidades"));
  }, [foraDoCadastro, siglas.length]);

  async function escolher(id: number, rotulo: string, nome: string) {
    setProduto({ id, rotulo, nome });
    setErro("");
    try {
      const o = await opcoesDoProduto(id);
      setOpcoes(o);
      setUm(o.um_padrao ?? "");
      if (!o.um_padrao) setSiglas((await unidadesDeMedida()).map((u) => u.sigla));
      campoQtd.current?.focus();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar o produto");
    }
  }

  function limpar() {
    setProduto(null);
    setOpcoes(null);
    setDescricao("");
    setQuantidade("");
    setUm("");
    setUrgencia("SEMANA");
    setObservacao("");
    setErro("");
    setRepetido(null);
    setRodada((n) => n + 1);
  }

  async function gravar(corpo: NovoItem) {
    setOcupado(true);
    try {
      const r = await pedirItem(corpo);
      aviso.sucesso(r.message);
      limpar();
      aoPedir(r.status);
    } catch (e) {
      setRepetido(null);
      setErro(e instanceof Error ? e.message : "Não foi possível pedir o item");
    } finally {
      setOcupado(false);
    }
  }

  function enviar(e: FormEvent) {
    e.preventDefault();
    const n = textoParaNumero(quantidade);
    if (foraDoCadastro ? !descricao.trim() : !produto) {
      setErro(foraDoCadastro ? "Escreva o que precisa ser comprado." : "Escolha o produto.");
      return;
    }
    if (!n || n <= 0) return setErro("Informe a quantidade.");
    if (!um) return setErro("Escolha a unidade.");
    const corpo: NovoItem = {
      ...(foraDoCadastro ? { descricao_livre: descricao.trim() } : { id_produto: produto!.id }),
      quantidade: n,
      um,
      urgencia,
      observacao: observacao.trim() || null,
    };
    // ⚠️ Avisa e não bloqueia: pode ser para outro uso, e a observação diz qual.
    const minhaSituacao = podeAprovar ? "A_COMPRAR" : "AGUARDANDO";
    const igual = !foraDoCadastro &&
      opcoes?.abertos.find((a) => a.um === um && a.status === minhaSituacao);
    if (igual) {
      setRepetido({
        corpo,
        id: igual.id,
        frase: `Já tem ${qtd(igual.quantidade)} ${igual.um} pedidos por ${igual.pedido_por ?? "alguém"}.`,
      });
      return;
    }
    void gravar(corpo);
  }

  // Enter envia, como nos outros campos; Shift+Enter quebra a linha.
  function teclaNaObservacao(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      formulario.current?.requestSubmit();
    }
  }

  const unidades = opcoes?.unidades.length ? opcoes.unidades.map((u) => u.um) : siglas;
  const nomeDoItem = foraDoCadastro ? descricao.trim() : produto?.nome ?? "";
  const n = textoParaNumero(quantidade);
  const dicaUrgencia = URGENCIAS.find((u) => u.valor === urgencia)?.dica;

  return (
    <form ref={formulario} onSubmit={enviar} id="ordem-form" className="flex flex-col gap-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[17px] font-bold tracking-tight">Novo pedido</h2>
      </div>
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div>
        <Campo rotulo={foraDoCadastro ? "1. O que precisa ser comprado?" : "1. Qual produto?"}>
          {foraDoCadastro ? (
            <input className="campo" id="ordem-descricao" maxLength={160} autoFocus
                   placeholder="Ex.: guardanapo de papel, pano de prato…"
                   value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          ) : (
            // 🔑 Lista suspensa ao digitar (26/11/2026, pedido do dono): escolhe sem abrir a janela.
            <BuscaCadastro key={rodada} id="ordem-produto" fonte={fonte} selecionado={produto}
                           autoFocus={rodada > 0} sugerirAoDigitar
                           aoEscolher={(i) => {
                             if (i) void escolher(i.id, i.codigo ? `${i.codigo} · ${i.nome}` : i.nome, i.nome);
                             else { setProduto(null); setOpcoes(null); setUm(""); }
                           }} />
          )}
        </Campo>
        <p className="mt-1.5 text-[13px] text-suave">
          {foraDoCadastro ? <>Está no cadastro? </> : <>Não achou? </>}
          <button type="button" className="font-semibold text-erva underline underline-offset-2 hover:text-tinta"
                  id="ordem-alternar"
                  onClick={() => { limpar(); setForaDoCadastro((v) => !v); }}>
            {foraDoCadastro ? "Buscar no cadastro" : "Pedir um produto que não está no cadastro"}
          </button>
          {!foraDoCadastro && <> — escreva o nome e quem compra cadastra.</>}
        </p>
        {!!opcoes?.abertos.length && (
          <p className="mt-1 text-[13px] text-alerta" id="ordem-ja-na-lista">
            Já na lista: {opcoes.abertos.map((a) =>
              `${qtd(a.quantidade)} ${a.um} (${a.pedido_por ?? "alguém"}` +
              `${a.status === "AGUARDANDO" ? ", aguardando aprovação" : ""})`).join(", ")}
          </p>
        )}
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        <div>
          <span className="rotulo-campo">2. Quanto precisa?</span>
          <div className="mt-1 grid grid-cols-[minmax(0,7rem)_minmax(0,1fr)] gap-2">
            <input ref={campoQtd} className="campo" id="ordem-quantidade" inputMode="decimal"
                   aria-label="Quantidade" placeholder="Ex.: 6"
                   value={quantidade} onChange={(e) => setQuantidade(e.target.value)} />
            <select className="campo" id="ordem-um" aria-label="Unidade" value={um}
                    onChange={(e) => setUm(e.target.value)}>
              <option value="">Escolha a unidade</option>
              {unidades.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <p className="mt-1.5 text-[13px] text-suave">
            Peça o que falta até a próxima compra, não o estoque todo.
          </p>
        </div>

        <div>
          <span className="rotulo-campo" id="ordem-urgencia-rotulo">3. Para quando?</span>
          <div className="mt-1 flex flex-wrap gap-2" role="radiogroup" aria-labelledby="ordem-urgencia-rotulo">
            {URGENCIAS.map((u) => (
              <button key={u.valor} type="button" role="radio" aria-checked={urgencia === u.valor}
                      data-urgencia={u.valor}
                      className={`btn rounded-full ${urgencia === u.valor ? "btn-primario" : "btn-secundario"}`}
                      onClick={() => setUrgencia(u.valor)}>
                {u.rotulo}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-[13px] text-suave">{dicaUrgencia}</p>
        </div>
      </div>

      <Campo rotulo="4. Alguma observação?" opcional>
        <textarea className="campo min-h-[4.5rem] resize-y" id="ordem-observacao" maxLength={300}
                  rows={2} placeholder="Ex.: marca preferida, para a encomenda de sábado, acabou no freezer 2…"
                  value={observacao} onChange={(e) => setObservacao(e.target.value)}
                  onKeyDown={teclaNaObservacao} />
      </Campo>

      <div className="flex flex-col gap-3 rounded-lg bg-erva-claro/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
           id="ordem-resumo">
        <p className="text-[14px]">
          <span className="text-suave">Resumo: </span>
          {nomeDoItem && n && um ? (
            <><strong>{qtd(n)} {um} de {nomeDoItem}</strong> · <span className={
              urgencia === "HOJE" ? "font-semibold text-erro" : "text-alerta"}>{rotuloUrgencia(urgencia)}</span></>
          ) : (
            <span className="text-suave">escolha o produto e a quantidade</span>
          )}
        </p>
        <button type="submit" className="btn btn-primario" id="ordem-adicionar" disabled={ocupado}>
          {ocupado ? "Enviando…" : podeAprovar ? "Enviar pedido" : "Enviar para aprovação"}
        </button>
      </div>

      {repetido && (
        <Modal titulo="Este item já está na lista" aoFechar={() => setRepetido(null)} largura="480px"
               rodape={
                 <div className="flex flex-wrap justify-end gap-2">
                   <button type="button" className="btn" id="ordem-separado" disabled={ocupado}
                           onClick={() => void gravar(repetido.corpo)}>
                     Manter separado
                   </button>
                   <button type="button" className="btn btn-primario" id="ordem-somar" disabled={ocupado}
                           onClick={() => void gravar({ ...repetido.corpo, somar_em: repetido.id })}>
                     Somar ao pedido
                   </button>
                 </div>
               }>
          <p>{repetido.frase}</p>
        </Modal>
      )}
    </form>
  );
}
