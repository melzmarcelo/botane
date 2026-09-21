"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import { custo, qtd } from "@/lib/numeros";

/**
 * O razão DESTE produto, dentro do cadastro dele.
 *
 * 🔑 **Pedido do dono (16/09/2026):** *"criar uma nova aba de movimentação, onde
 * será listada a movimentação do produto"*. Hoje, para saber por que o saldo de
 * um item está negativo, é preciso sair do cadastro, abrir Saldos e movimentos e
 * achar o produto de novo pela lupa — e voltar depois. **A pergunta nasce aqui**,
 * olhando o produto; a resposta passa a estar aqui.
 *
 * ⚠️ **Só LEITURA.** Estornar e reprocessar continuam em Saldos e movimentos,
 * que é a tela com a permissão certa (`estoque.custo`) e com a prévia antes do
 * botão. Esta aba responde, não mexe — e o link ao pé leva para lá quem precisa
 * mexer.
 *
 * ⚠️ **Busca só quando a aba ABRE.** O razão é a tabela que mais cresce da casa;
 * carregá-lo junto com o cadastro faria toda visita ao produto pagar por uma
 * consulta que quase ninguém pediu.
 */
type Movimento = {
  id: number;
  data_movimento: string;
  tipo: string;
  rotulo: string;
  quantidade: number;
  custo_unitario: number;
  custo_total: number;
  saldo_apos: number;
  local: string | null;
  documento: string | null;
  motivo: string | null;
  estornado: boolean;
  id_estorno_de: number | null;
  custo_provisorio: boolean;
};

/** Os períodos que se pergunta de verdade, e o "tudo" para quem investiga. */
const PERIODOS = [
  { dias: 30, rotulo: "últimos 30 dias" },
  { dias: 90, rotulo: "últimos 90 dias" },
  { dias: 365, rotulo: "último ano" },
  { dias: 0, rotulo: "tudo" },
];

const desde = (dias: number) => {
  if (!dias) return "";
  const d = new Date(Date.now() - dias * 86400000);
  return d.toLocaleDateString("sv-SE");
};

export default function MovimentacaoDoProduto({
  idProduto,
  umEstoque,
  podeVerCusto,
}: {
  idProduto: number;
  umEstoque: string | null;
  /** `estoque.saldos`. Sem ela a coluna de dinheiro simplesmente não existe. */
  podeVerCusto: boolean;
}) {
  const [dias, setDias] = useState(90);
  const [linhas, setLinhas] = useState<Movimento[] | null>(null);
  const [total, setTotal] = useState(0);
  const [erro, setErro] = useState("");
  // ⚠️ Cresce em blocos em vez de paginar: quem investiga um saldo lê de cima
  // para baixo até achar a linha estranha, e trocar de página perde o fio.
  const [quantos, setQuantos] = useState(25);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      const inicio = desde(dias);
      const r = await api.listar<Movimento>(
        `/estoque/movimentos?id_produto=${idProduto}&por_pagina=${quantos}` +
          (inicio ? `&inicio=${inicio}` : ""),
      );
      setLinhas(r.itens);
      setTotal(r.total ?? r.itens.length);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [idProduto, dias, quantos]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  return (
    <Cartao
      titulo="Movimentação"
      descricao="O razão deste produto, do mais recente para trás."
      acao={
        /* ⚠️ A largura mora no INVÓLUCRO: `.campo` tem `width: 100%` sem camada e
           ganha de uma utilitária `w-auto` na cascata — o seletor esticava e
           empurrava o título do cartão para uma coluna estreita. */
        <span className="block w-[164px]">
          <select
            className="campo py-1.5 text-[13px]"
            aria-label="Período da movimentação"
            value={dias}
            onChange={(e) => {
              setDias(Number(e.target.value));
              setQuantos(25);
            }}
          >
            {PERIODOS.map((p) => (
              <option key={p.dias} value={p.dias}>
                {p.rotulo}
              </option>
            ))}
          </select>
        </span>
      }
    >
      {erro ? (
        <p className="text-[14px] text-erro">{erro}</p>
      ) : !linhas ? (
        <Carregando />
      ) : !linhas.length ? (
        <Vazio>
          Nenhum movimento no período. Este produto pode nunca ter entrado no estoque — ou o
          período escolhido é curto demais.
        </Vazio>
      ) : (
        <>
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Quando</th>
                  <th>O quê</th>
                  <th>Documento</th>
                  <th>Prateleira</th>
                  <th className="num">Quantidade</th>
                  <th className="num">Saldo depois</th>
                  {podeVerCusto && <th className="num">Custo un.</th>}
                  {podeVerCusto && <th className="num">Total</th>}
                </tr>
              </thead>
              <tbody>
                {linhas.map((m) => (
                  <tr key={m.id} className={m.estornado ? "opacity-55" : ""}>
                    <td className="mono whitespace-nowrap text-[13px]">
                      {new Date(m.data_movimento).toLocaleString("pt-BR", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td>
                      <span className="whitespace-nowrap">{m.rotulo}</span>
                      {m.motivo && (
                        <span className="block text-[12.5px] text-suave">{m.motivo}</span>
                      )}
                      {m.estornado && (
                        <span className="block">
                          <Etiqueta cor="alerta">estornado</Etiqueta>
                        </span>
                      )}
                      {m.custo_provisorio && (
                        <span className="block">
                          <Etiqueta cor="alerta">custo provisório</Etiqueta>
                        </span>
                      )}
                    </td>
                    <td className="mono text-[12.5px]">
                      {m.documento || <span className="text-suave">—</span>}
                    </td>
                    <td className="text-[13.5px]">{m.local ?? "—"}</td>
                    <td
                      className={`num whitespace-nowrap ${
                        Number(m.quantidade) < 0 ? "text-erro" : "text-erva"
                      }`}
                    >
                      {Number(m.quantidade) > 0 ? "+" : ""}
                      {qtd(m.quantidade)} {umEstoque}
                    </td>
                    <td className="num whitespace-nowrap text-suave">{qtd(m.saldo_apos)}</td>
                    {podeVerCusto && (
                      <td className="num whitespace-nowrap">{custo(Number(m.custo_unitario))}</td>
                    )}
                    {podeVerCusto && (
                      <td className="num whitespace-nowrap">{reais(Number(m.custo_total))}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Etiqueta>
              {linhas.length} de {total}
            </Etiqueta>
            {linhas.length < total && (
              <button
                type="button"
                className="link-acao"
                onClick={() => setQuantos((n) => n + 50)}
              >
                ver mais
              </button>
            )}
            {/* ⚠️ O caminho para QUEM PRECISA MEXER. Estornar e reprocessar têm
                permissão própria e prévia antes do botão; duplicá-los aqui seria
                duplicar a regra junto. */}
            <Link
              className="link-acao ml-auto"
              href={`/estoque?aba=movimentos&id_produto=${idProduto}`}
            >
              abrir em Saldos e movimentos →
            </Link>
          </div>
        </>
      )}
    </Cartao>
  );
}
