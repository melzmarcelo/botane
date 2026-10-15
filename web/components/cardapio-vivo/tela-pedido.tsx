"use client";

/**
 * O carrinho do modo PEDIDO (fase 2, 115): revisar, mandar e acompanhar.
 *
 * 🔑 **O preço que vale é o do servidor** — a tela mostra a estimativa, e o pedido volta com
 * o total que a casa vai cobrar. 🔑 **A chave do envio muda quando o carrinho muda**: o mesmo
 * carrinho mandado duas vezes (toque duplo, rede ruim) vira UM pedido; um carrinho novo, outro.
 * ⚠️ O pagamento continua no caixa — fora do escopo, e a tela diz isso.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { MesaService, type PedidoPublico } from "@/lib/cardapio-vivo";
import Identificacao, { telefoneGuardado } from "./identificacao";
import { precoDaLinha, type LinhaSelecao } from "./selecao";
import { moeda, type Textos } from "./textos";

type Props = {
  linhas: LinhaSelecao[];
  total: number;
  algumSemPreco: boolean;
  mesa: string | null;
  token: string;
  loja: number;
  sessao: () => string;
  t: Textos;
  aoRemover: (linha: LinhaSelecao) => void;
  aoEnviado: (pedido: PedidoPublico) => void;
  aoFechar: () => void;
};

const novaChave = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;

export default function TelaPedido({ linhas, total, algumSemPreco, mesa, token, loja, sessao, t,
                                     aoRemover, aoEnviado, aoFechar }: Props) {
  const [observacao, setObservacao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [pedidos, setPedidos] = useState<PedidoPublico[]>([]);
  const [telefone, setTelefone] = useState<string | null>(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const chave = useMemo(novaChave, [JSON.stringify(linhas), observacao]);

  useEffect(() => { setTelefone(telefoneGuardado()); }, []);

  const acompanhar = useCallback(async () => {
    const r = await MesaService.pedidos(token, sessao());
    if (r.ok) setPedidos(r.dados);
  }, [token, sessao]);

  // Enquanto a tela está aberta e há pedido em aberto, atualiza a cada 15 s.
  useEffect(() => {
    void acompanhar();
    const abertos = pedidos.some((p) => p.situacao === "NOVO" || p.situacao === "CONFIRMADO");
    if (!abertos) return;
    const id = setInterval(() => void acompanhar(), 15_000);
    return () => clearInterval(id);
  }, [acompanhar, pedidos.length]); // eslint-disable-line react-hooks/exhaustive-deps

  async function enviar() {
    setEnviando(true);
    setErro(null);
    const r = await MesaService.enviarPedido(token, {
      sessao: sessao(), chave, observacao: observacao.trim() || null, telefone,
      itens: linhas.map((l) => ({ item: l.id_item, quantidade: l.quantidade, adicionais: l.adicionais.map((a) => a.id) })),
    });
    setEnviando(false);
    if (!r.ok) {
      setErro(r.erro);
      return;
    }
    setObservacao("");
    aoEnviado(r.dados);
    void acompanhar();
  }

  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-[var(--cv-fundo)] text-[var(--cv-tinta)]" role="dialog" aria-modal
         aria-label={t.meuPedido}>
      <header className="flex items-center justify-between border-b border-current/10 px-5 pb-3 pt-[max(1rem,env(safe-area-inset-top))]">
        <div>
          <h2 className="cv-serif text-2xl">{t.meuPedido}</h2>
          {mesa && <p className="text-sm opacity-70">{mesa}</p>}
        </div>
        <button type="button" onClick={aoFechar} className="rounded-full px-3 py-1 text-3xl leading-none opacity-60"
                aria-label={t.fechar}>×</button>
      </header>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-5 py-3">
        {linhas.length === 0 ? (
          pedidos.length === 0 && <p className="mt-6 text-center opacity-70">{t.vazia}</p>
        ) : (
          <>
            <ul className="divide-y divide-current/10">
              {linhas.map((l) => {
                const preco = precoDaLinha(l);
                return (
                  <li key={l.chave} className="flex items-start justify-between gap-3 py-3">
                    <div>
                      <p className="font-semibold"><span className="mr-1 tabular-nums">{l.quantidade}×</span>{l.nome}</p>
                      {l.adicionais.length > 0 && <p className="text-sm opacity-75">{l.adicionais.map((a) => a.nome).join(" · ")}</p>}
                      <button type="button" onClick={() => aoRemover(l)} className="text-sm underline opacity-60">{t.remover}</button>
                    </div>
                    <span className="shrink-0 tabular-nums">{preco !== null ? moeda(preco) : t.semPreco}</span>
                  </li>
                );
              })}
            </ul>
            <textarea className="w-full rounded-xl border border-current/20 bg-white/70 px-3 py-2.5 text-[15px]"
                      rows={2} maxLength={500} placeholder={t.observacaoPedido} aria-label={t.observacaoPedido}
                      value={observacao} onChange={(e) => setObservacao(e.target.value)} />
            {!telefone && <Identificacao token={token} loja={loja} t={t} aoIdentificar={(f) => setTelefone(f)} />}
            {erro && <p className="rounded-xl bg-red-100 px-3 py-2 text-sm text-red-800" role="alert">{erro}</p>}
          </>
        )}

        {pedidos.length > 0 && (
          <section aria-label={t.acompanhar}>
            <h3 className="mt-2 text-sm font-semibold opacity-70">{t.acompanhar}</h3>
            <ul className="mt-1 flex flex-col gap-2">
              {pedidos.map((p) => (
                <li key={p.numero} className="rounded-2xl border border-current/15 px-4 py-3 text-sm">
                  <p className="flex justify-between font-semibold">
                    <span>Nº {p.numero}</span><span className="tabular-nums">{moeda(p.total)}</span>
                  </p>
                  <p className={p.situacao === "RECUSADO" || p.situacao === "CANCELADO" ? "text-red-700" : "opacity-80"}>
                    {t.situacoes[p.situacao] ?? p.situacao}{p.motivo ? ` — ${p.motivo}` : ""}
                  </p>
                  <p className="mt-1 text-xs opacity-60">{p.itens.map((i) => `${i.quantidade}× ${i.nome}`).join(", ")}</p>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {linhas.length > 0 && (
        <footer className="border-t border-current/10 px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3">
          <div className="flex items-baseline justify-between text-lg font-semibold">
            <span>{t.total}</span>
            <span className="tabular-nums">{moeda(total)}{algumSemPreco ? " +" : ""}</span>
          </div>
          <p className="mt-1 text-xs opacity-60">{t.pagamentoNoCaixa}</p>
          <button type="button" disabled={enviando} onClick={() => void enviar()}
                  className="mt-3 w-full rounded-full bg-[var(--cv-principal)] py-3.5 text-base font-semibold text-white disabled:opacity-50">
            {enviando ? t.enviando : t.enviarPedido}
          </button>
        </footer>
      )}
    </div>
  );
}
