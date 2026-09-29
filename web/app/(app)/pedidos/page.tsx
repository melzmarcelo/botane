"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import CabecalhoTela from "@/components/cabecalho-tela";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { COR, ROTULO, fone, listar, quando, reais, type PedidoResumo } from "@/lib/pedidos";

/**
 * Portal de Clientes ▸ Pedidos: a lista, para achar e conferir.
 *
 * 🔑 **Pedido do dono (28/09/2026):** *"teremos uma tela com pedidos"*. O dia a dia é o
 * painel; esta é a lista paginada com filtros, e o caminho para o detalhe de cada pedido.
 */
const SITUACOES = [
  { v: "abertos", r: "Em aberto" },
  { v: "novos", r: "Novos" },
  { v: "sem_pdv", r: "Falta lançar no PDV" },
  { v: "confirmados", r: "Confirmados" },
  { v: "entregues", r: "Entregues" },
  { v: "recusados", r: "Recusados e cancelados" },
  { v: "todos", r: "Todos" },
];

export default function ListaDePedidos() {
  const [situacao, setSituacao] = useEstadoNaUrl<string>("situacao", "abertos");
  const [dia, setDia] = useEstadoNaUrl<string>("dia", "");
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [lista, setLista] = useState<PedidoResumo[] | null>(null);
  const [erro, setErro] = useState("");
  const pag = usePaginacao("pedidos", { filtros: [situacao, dia, busca] });

  const carregar = useCallback(async () => {
    if (!pag.pronto) return;
    try {
      const r = await listar(pag.parametros, { situacao, dia, busca });
      setLista(r.itens);
      pag.setTotal(r.total);
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar os pedidos");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, situacao, dia, busca, pag.offset, pag.porPagina]);

  useEffect(() => {
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Portal de Clientes · Pedidos"
        titulo="Pedidos"
        explica="Os pedidos feitos pelo cardápio do site. A casa confirma (podendo trocar produtos), lança no PDV — que é onde a venda acontece — e marca a entrega."
        acoes={<Link href="/pedidos/painel" className="btn btn-primario">Painel</Link>}
      />
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="min-w-0 flex-1">
            <span className="rotulo-campo">Buscar</span>
            <input className="campo mt-1.5" placeholder="número, nome ou telefone" value={busca}
                   onChange={(e) => setBusca(e.target.value)} />
          </label>
          <label>
            <span className="rotulo-campo">Para o dia</span>
            <input className="campo mono mt-1.5" type="date" value={dia} onChange={(e) => setDia(e.target.value)} />
          </label>
        </div>
        <div className="mt-3 flex flex-wrap gap-1" role="tablist" aria-label="situação">
          {SITUACOES.map((x) => (
            <button key={x.v} type="button" role="tab" aria-selected={situacao === x.v}
                    className={`btn px-3 py-1.5 text-[13px] ${situacao === x.v ? "btn-primario" : "btn-secundario"}`}
                    onClick={() => setSituacao(x.v)}>
              {x.r}
            </button>
          ))}
        </div>
      </Cartao>

      <Cartao>
        {!lista ? <Carregando /> : !lista.length ? <Vazio>Nenhum pedido aqui.</Vazio> : (
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th className="w-[70px]">Nº</th>
                  <th>Cliente</th>
                  <th>Para quando</th>
                  <th>Como</th>
                  <th className="text-right">Total</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((p) => (
                  <tr key={p.id}>
                    <td className="mono"><Link className="link-acao" href={`/pedidos/${p.id}`}>{p.numero}</Link></td>
                    <td>
                      <Link className="link-acao" href={`/pedidos/${p.id}`}>{p.nome}</Link>
                      <span className="mono block text-[12px] text-suave">{fone(p.telefone)}</span>
                    </td>
                    <td className="mono text-[13px]">{quando(p.para_quando)}</td>
                    <td className="text-[13px]">
                      {p.modo_rotulo}
                      <span className="block text-[12px] text-suave">{p.pagamento_rotulo}</span>
                    </td>
                    <td className="num">{reais(p.total)}</td>
                    <td>
                      <Etiqueta cor={COR[p.situacao]}>{ROTULO[p.situacao]}</Etiqueta>
                      {(p.situacao === "CONFIRMADO" || p.situacao === "ENTREGUE") && (
                        <span className="block text-[12px] text-suave">
                          {p.lancado_pdv_em ? `no PDV${p.cupom_pdv ? ` · cupom ${p.cupom_pdv}` : ""}` : "falta lançar no PDV"}
                          {p.pago_em ? " · pago" : ""}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Paginacao p={pag} rotulo="pedido(s)" />
      </Cartao>
    </div>
  );
}
