"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import BuscaCadastro from "@/components/busca-cadastro";
import { Aviso, Campo, Modal } from "@/components/ui";
import { fonteFornecedores } from "@/lib/busca-cadastro";
import { qtd, textoParaNumero } from "@/lib/numeros";
import {
  corrigirItem,
  marcarComprado,
  opcoesDoProduto,
  OrdemItem,
  qtdParaCampo,
  unidadesDeMedida,
  Urgencia,
  URGENCIAS,
} from "@/lib/ordens-compra";

/**
 * Marcar como comprado. A quantidade já vem com o pedido: quem comprou tudo só confirma, e
 * quem achou menos troca o número — o que faltou continua na lista.
 */
export function JanelaComprar({
  itens,
  aoFechar,
  aoComprar,
}: {
  itens: OrdemItem[];
  aoFechar: () => void;
  aoComprar: (ids: number[], mensagem: string) => void;
}) {
  const fonte = useMemo(() => fonteFornecedores(), []);
  const [quantidades, setQuantidades] = useState<Record<number, string>>(() =>
    Object.fromEntries(itens.map((i) => [i.id, qtdParaCampo(i.quantidade)])));
  const [fornecedor, setFornecedor] = useState<{ id: number; rotulo: string } | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function confirmar(e?: FormEvent) {
    e?.preventDefault();
    const linhas = itens.map((i) => ({ id: i.id, quantidade: textoParaNumero(quantidades[i.id]) ?? 0 }));
    const ruim = linhas.findIndex((l) => l.quantidade <= 0);
    if (ruim >= 0) return setErro(`Informe quanto foi comprado de ${itens[ruim].item}.`);
    setOcupado(true);
    try {
      const r = await marcarComprado(linhas, fornecedor?.id ?? null);
      aoComprar(r.ids, r.message);
    } catch (x) {
      setErro(x instanceof Error ? x.message : "Não foi possível marcar como comprado");
      setOcupado(false);
    }
  }

  return (
    <Modal titulo="Marcar como comprado" aoFechar={aoFechar} largura="560px"
           rodape={
             <div className="flex justify-end gap-2">
               <button type="button" className="btn" onClick={aoFechar}>Cancelar</button>
               <button type="button" className="btn btn-primario" id="ordem-confirmar-compra"
                       disabled={ocupado} onClick={() => void confirmar()}>
                 {ocupado ? "Marcando…" : "Confirmar"}
               </button>
             </div>
           }>
      <form onSubmit={confirmar} className="flex flex-col gap-3">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        {itens.map((i) => {
          const n = textoParaNumero(quantidades[i.id]) ?? 0;
          const falta = Number(i.quantidade) - n;
          return (
            <div key={i.id} className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1 font-medium">{i.item}</span>
              <input className="campo w-24 text-right" inputMode="decimal"
                     aria-label={`quantidade comprada de ${i.item}`} data-ordem-qtd={i.id}
                     value={quantidades[i.id]}
                     // ⚠️ Quem entra aqui veio trocar o número: sem isto, digitar 7 sobre 12 dava 712.
                     onFocus={(e) => e.target.select()}
                     onChange={(e) => setQuantidades((q) => ({ ...q, [i.id]: e.target.value }))} />
              <span className="w-10 text-suave">{i.um}</span>
              {n > 0 && falta > 0 && (
                <p className="w-full text-right text-[13px] text-suave">
                  {qtd(falta)} {i.um} continuam na lista
                </p>
              )}
            </div>
          );
        })}
        <Campo rotulo="Fornecedor" opcional>
          <BuscaCadastro id="ordem-fornecedor" fonte={fonte} selecionado={fornecedor}
                         aoEscolher={(f) => setFornecedor(f ? { id: f.id, rotulo: f.nome } : null)} />
        </Campo>
        <p className="text-[13px] text-suave">
          Isto não mexe no estoque. A mercadoria entra quando a nota for lançada.
        </p>
      </form>
    </Modal>
  );
}

export function JanelaCorrigir({
  item,
  aoFechar,
  aoSalvar,
}: {
  item: OrdemItem;
  aoFechar: () => void;
  aoSalvar: (mensagem: string) => void;
}) {
  const [quantidade, setQuantidade] = useState(qtdParaCampo(item.quantidade));
  const [um, setUm] = useState(item.um);
  const [observacao, setObservacao] = useState(item.observacao ?? "");
  const [urgencia, setUrgencia] = useState<Urgencia>(item.urgencia);
  const [unidades, setUnidades] = useState<string[]>([item.um]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    const pedir = item.id_produto
      ? opcoesDoProduto(item.id_produto).then((o) => o.unidades.map((u) => u.um))
      : unidadesDeMedida().then((l) => l.map((u) => u.sigla));
    pedir
      .then((l) => { if (l.length) setUnidades(l.includes(item.um) ? l : [item.um, ...l]); })
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar as unidades"));
  }, [item.id_produto, item.um]);

  async function salvar(e?: FormEvent) {
    e?.preventDefault();
    const n = textoParaNumero(quantidade);
    if (!n || n <= 0) return setErro("Informe a quantidade.");
    setOcupado(true);
    try {
      const r = await corrigirItem(item.id, { quantidade: n, um, observacao: observacao.trim() || null, urgencia });
      aoSalvar(r.message);
    } catch (x) {
      setErro(x instanceof Error ? x.message : "Não foi possível corrigir");
      setOcupado(false);
    }
  }

  return (
    <Modal titulo={`Corrigir: ${item.item}`} aoFechar={aoFechar} largura="480px"
           rodape={
             <div className="flex justify-end gap-2">
               <button type="button" className="btn" onClick={aoFechar}>Cancelar</button>
               <button type="button" className="btn btn-primario" id="ordem-salvar-correcao"
                       disabled={ocupado} onClick={() => void salvar()}>Salvar</button>
             </div>
           }>
      <form onSubmit={salvar} className="flex flex-col gap-3">
        {erro && <Aviso tipo="erro">{erro}</Aviso>}
        <div className="grid grid-cols-2 gap-3">
          <Campo rotulo="Quantidade">
            <input className="campo" id="ordem-corrigir-qtd" inputMode="decimal" value={quantidade}
                   onChange={(e) => setQuantidade(e.target.value)} />
          </Campo>
          <Campo rotulo="Unidade">
            <select className="campo" value={um} onChange={(e) => setUm(e.target.value)}>
              {unidades.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Campo>
        </div>
        <Campo rotulo="Para quando?">
          <select className="campo" id="ordem-corrigir-urgencia" value={urgencia}
                  onChange={(e) => setUrgencia(e.target.value as Urgencia)}>
            {URGENCIAS.map((u) => <option key={u.valor} value={u.valor}>{u.rotulo}</option>)}
          </select>
        </Campo>
        <Campo rotulo="Observação" opcional>
          <input className="campo" maxLength={300} value={observacao}
                 onChange={(e) => setObservacao(e.target.value)} />
        </Campo>
      </form>
    </Modal>
  );
}
