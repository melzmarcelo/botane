"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BuscaCadastro from "@/components/busca-cadastro";
import { Aviso, Campo, Modal } from "@/components/ui";
import { fonteProdutos } from "@/lib/busca-cadastro";
import { qtd, textoParaNumero } from "@/lib/numeros";
import {
  FILTRO_COMPRADOS,
  NovoItem,
  OpcoesDoProduto,
  opcoesDoProduto,
  pedirItem,
  unidadesDeMedida,
} from "@/lib/ordens-compra";

/**
 * Pedir um item em três campos, com Enter. Quem lembrou de cinco coisas lança as cinco sem
 * abrir janela: ao gravar, o foco volta para o produto.
 */
export default function FormPedido({ aoPedir }: { aoPedir: () => void }) {
  const aviso = useAviso();
  const fonte = useMemo(() => fonteProdutos(FILTRO_COMPRADOS), []);
  const [produto, setProduto] = useState<{ id: number; rotulo: string } | null>(null);
  const [opcoes, setOpcoes] = useState<OpcoesDoProduto | null>(null);
  const [foraDoCadastro, setForaDoCadastro] = useState(false);
  const [descricao, setDescricao] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [um, setUm] = useState("");
  const [observacao, setObservacao] = useState("");
  const [siglas, setSiglas] = useState<string[]>([]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [repetido, setRepetido] = useState<{ corpo: NovoItem; id: number; frase: string } | null>(null);
  // Remonta a busca ao limpar: é ela quem guarda o texto digitado.
  const [rodada, setRodada] = useState(0);
  const campoQtd = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!foraDoCadastro || siglas.length) return;
    unidadesDeMedida()
      .then((l) => setSiglas(l.map((u) => u.sigla)))
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar as unidades"));
  }, [foraDoCadastro, siglas.length]);

  async function escolher(id: number, rotulo: string) {
    setProduto({ id, rotulo });
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
      aoPedir();
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
      observacao: observacao.trim() || null,
    };
    // ⚠️ Avisa e não bloqueia: pode ser para outro uso, e a observação diz qual.
    const igual = !foraDoCadastro && opcoes?.abertos.find((a) => a.um === um);
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

  const unidades = opcoes?.unidades.length ? opcoes.unidades.map((u) => u.um) : siglas;

  return (
    <form onSubmit={enviar} id="ordem-form" className="flex flex-col gap-3">
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_110px_110px]">
        <Campo rotulo={foraDoCadastro ? "Item" : "Produto"}>
          {foraDoCadastro ? (
            <input className="campo" id="ordem-descricao" maxLength={160} autoFocus
                   value={descricao} onChange={(e) => setDescricao(e.target.value)} />
          ) : (
            <BuscaCadastro key={rodada} id="ordem-produto" fonte={fonte} selecionado={produto}
                           autoFocus={rodada > 0}
                           aoEscolher={(i) => {
                             if (i) void escolher(i.id, i.codigo ? `${i.codigo} · ${i.nome}` : i.nome);
                             else { setProduto(null); setOpcoes(null); setUm(""); }
                           }} />
          )}
        </Campo>
        <Campo rotulo="Quantidade">
          <input ref={campoQtd} className="campo" id="ordem-quantidade" inputMode="decimal"
                 value={quantidade} onChange={(e) => setQuantidade(e.target.value)} />
        </Campo>
        <Campo rotulo="Unidade">
          <select className="campo" id="ordem-um" value={um} onChange={(e) => setUm(e.target.value)}>
            <option value="">—</option>
            {unidades.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </Campo>
      </div>

      {!!opcoes?.abertos.length && (
        <p className="text-[13px] text-suave" id="ordem-ja-na-lista">
          Já na lista: {opcoes.abertos.map((a) =>
            `${qtd(a.quantidade)} ${a.um} (${a.pedido_por ?? "alguém"})`).join(", ")}
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <Campo rotulo="Observação" opcional className="min-w-0 flex-1">
          <input className="campo" id="ordem-observacao" maxLength={300}
                 value={observacao} onChange={(e) => setObservacao(e.target.value)} />
        </Campo>
        <button type="submit" className="btn btn-primario" id="ordem-adicionar" disabled={ocupado}>
          {ocupado ? "Adicionando…" : "Adicionar"}
        </button>
      </div>

      <button type="button" className="link-acao self-start text-[13px]" id="ordem-alternar"
              onClick={() => { limpar(); setForaDoCadastro((v) => !v); }}>
        {foraDoCadastro ? "buscar no cadastro" : "não está no cadastro"}
      </button>

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
