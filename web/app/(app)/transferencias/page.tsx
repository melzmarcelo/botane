"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Paginacao, usePaginacao } from "@/components/paginacao";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";

/**
 * O que está no caminho entre as lojas.
 *
 * 🔑 **A remessa em trânsito continua contando no estoque de quem mandou** — é
 * isso que impede o valor de ficar sem dono enquanto a mercadoria viaja. Esta
 * tela existe porque, sem ela, esse "continua contando" seria uma armadilha:
 * quem olhasse o saldo da matriz veria mercadoria que já está no carro e
 * despacharia de novo.
 */

/** Data e hora curtas — o que interessa numa lista é o dia e a hora do envio. */
const quando = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit",
  });

type Remessa = {
  id: number;
  status: string;
  enviada_em: string;
  recebida_em: string | null;
  observacao: string | null;
  id_unidade_origem: number;
  id_unidade_destino: number;
  loja_origem: string;
  loja_destino: string;
  local_origem: string;
  local_destino: string;
  enviada_por: string | null;
  itens: number;
  quantidade: number;
};

const ABAS = [
  { id: "EM_TRANSITO", nome: "Em trânsito" },
  { id: "RECEBIDA", nome: "Recebidas" },
  { id: "CANCELADA", nome: "Canceladas" },
];

export default function PaginaTransferencias() {
  // ⚠️ A loja vem da SESSÃO, não do localStorage cru: ele fica vazio até alguém
  // mexer no seletor, e aí a comparação seria contra zero.
  const { unidade: minhaLoja } = useSessao();
  const [aba, setAba] = useState("EM_TRANSITO");
  const [lista, setLista] = useState<Remessa[] | null>(null);
  const [erro, setErro] = useState("");
  // ⚠️ `filtros` volta para a primeira página ao trocar de aba: quem está na
  // página 3 das recebidas e clica em "em trânsito" cairia numa tela vazia sem
  // nada explicando.
  const pag = usePaginacao("transferencias", { filtros: [aba] });

  const carregar = useCallback(async () => {
    setLista(null);
    try {
      const l = await api.listar<Remessa>(
        `/transferencias?status=${aba}&${new URLSearchParams(pag.parametros)}`);
      setLista(l.itens);
      pag.setTotal(l.total);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aba, pag.offset, pag.porPagina]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Estoque</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
          Remessas entre lojas
        </h1>
        <p className="mt-1 max-w-[74ch] text-suave">
          O que saiu de uma loja e ainda não foi conferido na outra. Enquanto está em trânsito, a
          quantidade <strong>continua no estoque de quem mandou</strong> — é o que mantém o valor
          com dono no caminho. O razão só se mexe no recebimento, nas duas lojas ao mesmo tempo.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <div className="flex flex-wrap gap-2">
        {ABAS.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => setAba(a.id)}
            className={aba === a.id ? "btn btn-primario" : "btn"}
          >
            {a.nome}
          </button>
        ))}
      </div>

      <Cartao>
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>
            {aba === "EM_TRANSITO"
              ? "Nada em trânsito. Remessas são criadas em Estoque ▸ Ajustes, escolhendo um local de outra loja como destino."
              : "Nenhuma remessa aqui."}
          </Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Remessa</th>
                  <th>De</th>
                  <th>Para</th>
                  <th className="text-right">Itens</th>
                  <th>Enviada</th>
                  <th>Situação</th>
                </tr>
              </thead>
              <tbody>
                {lista.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link href={`/transferencias/${r.id}`} className="link-registro font-semibold">
                        #{r.id}
                      </Link>
                      {/* Quem espera a mercadoria precisa distinguir a remessa
                          que ELA recebe da que ela mandou — a lista mostra as
                          duas de propósito. */}
                      {r.status === "EM_TRANSITO" && minhaLoja === r.id_unidade_destino && (
                        <span className="ml-2">
                          <Etiqueta cor="alerta">a receber</Etiqueta>
                        </span>
                      )}
                    </td>
                    <td>
                      {r.loja_origem}
                      <span className="text-suave"> · {r.local_origem}</span>
                    </td>
                    <td>
                      {r.loja_destino}
                      <span className="text-suave"> · {r.local_destino}</span>
                    </td>
                    <td className="mono text-right">{r.itens}</td>
                    <td>
                      {quando(r.enviada_em)}
                      {r.enviada_por && <span className="text-suave"> · {r.enviada_por}</span>}
                    </td>
                    <td>
                      {r.status === "EM_TRANSITO"
                        ? "em trânsito"
                        : r.status === "RECEBIDA"
                          ? `recebida ${r.recebida_em ? quando(r.recebida_em) : ""}`
                          : "cancelada"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <Paginacao p={pag} rotulo="remessas" />
      </Cartao>
    </div>
  );
}
