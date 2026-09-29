"use client";

import Link from "next/link";

import { Cartao, Etiqueta } from "@/components/ui";
import { COR, ROTULO, quando, reais, type PedidoResumo } from "@/lib/pedidos";

/**
 * O cartão de pedidos do site no Início.
 *
 * 🔑 **Pedido do dono (28/09/2026):** *"aviso na tela inicial"*. O que pede ação vem ANTES da
 * lista, em destaque: pedido esperando confirmação é cliente esperando resposta, e confirmado
 * sem lançamento no PDV é venda que ainda não existe no caixa.
 * ⚠️ Nulo (sem cartão) quando a loja nunca recebeu pedido — ou sem o Portal, ou sem permissão.
 */
export type PedidosDoInicio = {
  novos: number;
  sem_pdv: number;
  hoje: number;
  todos: number;
  linhas: PedidoResumo[];
};

export default function PedidosDoDia({ p }: { p: PedidosDoInicio }) {
  return (
    <Cartao
      titulo="Pedidos do site"
      descricao={`${p.hoje} para hoje · ${p.linhas.length} em aberto`}
      acao={<Link href="/pedidos/painel" className="btn btn-secundario">Abrir o painel</Link>}
    >
      {(p.novos > 0 || p.sem_pdv > 0) && (
        <p className="mb-3 flex flex-wrap gap-x-4 text-[13.5px]">
          {p.novos > 0 && (
            <span><b className="mono text-alerta">{p.novos}</b> <span className="text-suave">esperando a casa confirmar</span></span>
          )}
          {p.sem_pdv > 0 && (
            <Link href="/pedidos?situacao=sem_pdv">
              <b className="mono text-alerta">{p.sem_pdv}</b> <span className="text-suave">confirmado(s) sem lançar no PDV</span>
            </Link>
          )}
        </p>
      )}
      {!p.linhas.length ? (
        <p className="text-[14.5px] text-suave">Nenhum pedido em aberto.</p>
      ) : (
        <ul className="lista-rolante flex flex-col gap-px bg-linha text-[14.5px]">
          {p.linhas.map((l) => (
            <li key={l.id} className="flex flex-wrap items-baseline gap-x-3 bg-superficie py-2.5">
              <span className="mono text-[13px] text-suave">{quando(l.para_quando)}</span>
              <Link href={`/pedidos/${l.id}`} className="link-registro">Nº {l.numero} · {l.nome}</Link>
              <span className="mono text-[13px]">{reais(l.total)}</span>
              <Etiqueta cor={COR[l.situacao]}>{ROTULO[l.situacao]}</Etiqueta>
            </li>
          ))}
        </ul>
      )}
    </Cartao>
  );
}
