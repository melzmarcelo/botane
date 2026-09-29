"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Etiqueta } from "@/components/ui";
import Voltar from "@/components/voltar";
import {
  COR, ROTULO, confirmar, entregar, fone, imprimir, obter, quando, reais, type PedidoCompleto,
} from "@/lib/pedidos";
import { useSessao } from "@/lib/sessao";

import { JanelaDeCupom, JanelaDeMotivo, JanelaDePagamento } from "./janelas";
import TrocarProdutos from "./troca";

/**
 * O pedido inteiro, com as ações que cabem na situação dele.
 *
 * 🔑 **Decisões do dono (28/09/2026):** a casa SEMPRE confirma e pode trocar produtos antes;
 * o pedido não vira venda — a casa lança no PDV e marca aqui "lançado", com o cupom.
 */
export default function DetalheDoPedido() {
  const { id } = useParams<{ id: string }>();
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeOperar = pode("pedidos.operar");
  const [p, setP] = useState<PedidoCompleto | null>(null);
  const [erro, setErro] = useState("");
  const [janela, setJanela] = useState<"" | "troca" | "recusar" | "cancelar" | "cupom" | "pago">("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(() => {
    obter(Number(id)).then((x) => { setP(x); setErro(""); })
      .catch((e) => setErro(e instanceof Error ? e.message : "Pedido não encontrado"));
  }, [id]);
  useEffect(() => carregar(), [carregar]);

  async function agir(fazer: () => Promise<PedidoCompleto & { message: string }>) {
    setOcupado(true);
    try {
      const r = await fazer();
      setP(r);
      setJanela("");
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <div className="flex flex-col gap-4"><Voltar href="/pedidos">Pedidos</Voltar><Aviso tipo="erro">{erro}</Aviso></div>;
  if (!p) return <Carregando />;
  const aberto = p.situacao === "CONFIRMADO" || p.situacao === "ENTREGUE";

  return (
    <div className="flex flex-col gap-5">
      <Voltar href="/pedidos">Pedidos</Voltar>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="rotulo">Pedido pelo site{p.catalogo ? ` · ${p.catalogo}` : ""}</p>
          <h1 className="titulo mt-1">Pedido {p.numero}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Etiqueta cor={COR[p.situacao]}>{ROTULO[p.situacao]}</Etiqueta>
            {p.alterado && <Etiqueta cor="alerta">produtos trocados</Etiqueta>}
            {aberto && <Etiqueta cor={p.lancado_pdv_em ? "erva" : "alerta"}>
              {p.lancado_pdv_em ? "lançado no PDV" : "falta lançar no PDV"}</Etiqueta>}
            {p.pago_em && <Etiqueta cor="erva">pago · {p.pago_como?.toLowerCase()}</Etiqueta>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn btn-secundario" onClick={() => void imprimir(p.id).catch(
            (e) => aviso.erro(e instanceof Error ? e.message : "Falha ao imprimir"))}>PDF</button>
          {podeOperar && p.situacao === "NOVO" && (
            <>
              <button className="btn btn-secundario" onClick={() => setJanela("recusar")}>Recusar</button>
              <button className="btn btn-secundario" onClick={() => setJanela("troca")}>Trocar produtos</button>
              <button className="btn btn-primario" disabled={ocupado}
                      onClick={() => void agir(() => confirmar(p.id))}>Confirmar</button>
            </>
          )}
          {podeOperar && aberto && (
            <>
              {p.situacao === "CONFIRMADO" && (
                <button className="btn btn-secundario" onClick={() => setJanela("cancelar")}>Cancelar</button>
              )}
              <button className={`btn ${p.lancado_pdv_em ? "btn-secundario" : "btn-primario"}`}
                      onClick={() => setJanela("cupom")}>
                {p.lancado_pdv_em ? "Cupom do PDV" : "Lançado no PDV"}
              </button>
              {!p.pago_em && <button className="btn btn-secundario" onClick={() => setJanela("pago")}>Pago</button>}
              {p.situacao === "CONFIRMADO" && (
                <button className="btn btn-primario" disabled={ocupado}
                        onClick={() => void agir(() => entregar(p.id))}>Entregue</button>
              )}
            </>
          )}
        </div>
      </div>

      {p.motivo && <Aviso tipo="info">Motivo: {p.motivo}</Aviso>}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Cartao titulo="Itens">
          <div className="grid-rolante">
            <table className="tabela">
              <thead><tr><th>Produto</th><th className="text-right">Qtd</th><th className="text-right">Preço</th><th className="text-right">Total</th></tr></thead>
              <tbody>
                {p.itens.map((i) => (
                  <tr key={i.id}>
                    <td>{i.nome}{i.observacao && <span className="block text-[12.5px] text-suave">obs.: {i.observacao}</span>}</td>
                    <td className="num">{i.quantidade.toLocaleString("pt-BR")}</td>
                    <td className="num">{reais(i.preco_unitario)}</td>
                    <td className="num">{reais(i.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <dl className="mt-3 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[14px]">
            <dt className="text-suave">Subtotal</dt><dd className="num">{reais(p.subtotal)}</dd>
            {p.taxa_entrega > 0 && <><dt className="text-suave">Entrega</dt><dd className="num">{reais(p.taxa_entrega)}</dd></>}
            <dt className="font-semibold">Total</dt><dd className="num font-semibold">{reais(p.total)}</dd>
          </dl>
        </Cartao>

        <Cartao titulo="Cliente e entrega">
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-[14px]">
            <dt className="text-suave">Cliente</dt><dd>{p.nome}</dd>
            <dt className="text-suave">Telefone</dt>
            <dd className="mono"><a className="link-acao" href={`https://wa.me/55${p.telefone}`} target="_blank" rel="noreferrer">{fone(p.telefone)}</a></dd>
            <dt className="text-suave">Como</dt><dd>{p.modo_rotulo}</dd>
            <dt className="text-suave">Para</dt><dd className="mono">{quando(p.para_quando)}</dd>
            {p.endereco && <><dt className="text-suave">Endereço</dt><dd>{p.endereco}</dd></>}
            <dt className="text-suave">Pagamento</dt><dd>{p.pagamento_rotulo}</dd>
            {p.observacao && <><dt className="text-suave">Observação</dt><dd>{p.observacao}</dd></>}
            {p.cupom_pdv && <><dt className="text-suave">Cupom</dt>
              <dd className="mono">{p.cupom_pdv}{p.id_venda
                ? <> · <Link className="link-acao" href={`/vendas/${p.id_venda}`}>venda importada ✓</Link></>
                : <span className="text-suave"> · a venda ainda não chegou do PDV</span>}</dd></>}
          </dl>
        </Cartao>
      </div>

      <Cartao titulo="Histórico">
        <ul className="flex flex-col gap-1.5 text-[13.5px]">
          {p.historico.map((h, k) => (
            <li key={k}>
              <span className="mono text-suave">{quando(h.criado_em)}</span> · {h.acao.toLowerCase().replace("_", " ")}
              {" "}· {h.quem ?? "cliente (site)"}
              {h.detalhe && "pedido_pelo_cliente" in h.detalhe && (
                <span className="block pl-4 text-[12.5px] text-suave">
                  o cliente pediu: {(h.detalhe.pedido_pelo_cliente as { nome: string; quantidade: number }[])
                    .map((i) => `${i.quantidade}× ${i.nome}`).join(", ")}
                </span>
              )}
              {h.detalhe && typeof h.detalhe.motivo === "string" && <span className="text-suave"> — {h.detalhe.motivo}</span>}
              {h.detalhe && typeof h.detalhe.cupom === "string" && <span className="text-suave"> — cupom {h.detalhe.cupom}</span>}
            </li>
          ))}
        </ul>
      </Cartao>

      {janela === "troca" && (
        <TrocarProdutos pedido={p} aoFechar={() => setJanela("")}
                        aoConfirmar={(itens) => agir(() => confirmar(p.id, itens))} />
      )}
      {(janela === "recusar" || janela === "cancelar") && (
        <JanelaDeMotivo pedido={p} tipo={janela} aoFechar={() => setJanela("")}
                        aoFeito={(r) => { setP(r); setJanela(""); }} />
      )}
      {janela === "cupom" && <JanelaDeCupom pedido={p} aoFechar={() => setJanela("")} aoFeito={(r) => { setP(r); setJanela(""); }} />}
      {janela === "pago" && <JanelaDePagamento pedido={p} aoFechar={() => setJanela("")} aoFeito={(r) => { setP(r); setJanela(""); }} />}
    </div>
  );
}
