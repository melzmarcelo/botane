"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Aviso, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { dataBr } from "../vendas/tipos";

/**
 * Meu consumo — o que EU consumi e ainda não paguei.
 *
 * 🔑 **Pedido do dono (04/09/2026):** "estes valores em aberto podem ser
 * consultados pelo usuario, para saber o valor do seu consumo, isto pode estar
 * dentro do menu do usuario".
 *
 * ⚠️ **Sem permissão nenhuma, só autenticação** — como a Ajuda e o Perfil.
 * Exigir uma chave faria a pessoa precisar de permissão para ver a própria
 * dívida, e quem tem menos acesso é justamente quem mais precisa desta tela. O
 * escopo vem do vínculo usuário↔pessoa no servidor, nunca de um identificador
 * mandado pela tela.
 */

type Cupom = {
  id: number;
  data: string;
  hora: string | null;
  documento: string | null;
  itens: number;
  total_cheio: number;
  total: number;
};

type Fechado = {
  id: number;
  nome: string | null;
  inicio: string;
  fim: string;
  fechado_em: string | null;
  cupons: number;
  itens: number;
  total_cheio: number;
  desconto: number;
  total: number;
};

type MeuConsumo = {
  vinculado: boolean;
  pessoa: { id: number; nome: string; cupom_base: string | null;
            cupom_desconto_pct: number | null } | null;
  periodo: { id: number; nome: string | null; inicio: string; fim: string } | null;
  cupons: Cupom[];
  total: number;
  total_cheio: number;
  desconto: number;
  historico: Fechado[];
};

export default function PaginaMeuConsumo() {
  const [dados, setDados] = useState<MeuConsumo | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    api
      .get<MeuConsumo>("/consumo/meu")
      .then(setDados)
      .finally(() => setCarregando(false));
  }, []);

  if (carregando) {
    return <p className="text-suave">carregando…</p>;
  }

  // ⚠️ **"Não devo nada" e "não estou ligado a um cadastro" são coisas
  // diferentes**, e mostrar zero nos dois casos esconderia a segunda — que se
  // resolve no cadastro de usuários, não aqui.
  if (!dados?.vinculado) {
    return (
      <div className="flex flex-col gap-6">
        <header>
          <h1 className="text-[24px] font-bold tracking-tight sm:text-[30px]">Meu consumo</h1>
        </header>
        <Aviso tipo="info">
          Seu login ainda não está ligado a um cadastro de pessoa, então não há consumo
          para mostrar. Quem cuida dos usuários faz essa ligação no cadastro do usuário,
          no cartão <b>Quem é esta pessoa</b>.
        </Aviso>
      </div>
    );
  }

  const { pessoa, periodo, cupons, historico } = dados;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <h1 className="text-[24px] font-bold tracking-tight sm:text-[30px]">Meu consumo</h1>
        <p className="mt-1 text-suave">
          {pessoa?.nome}
          {pessoa?.cupom_base === "CUSTO" ? " · seus cupons saem pelo custo" : ""}
          {Number(pessoa?.cupom_desconto_pct) > 0
            ? ` · ${Number(pessoa?.cupom_desconto_pct)}% de desconto`
            : ""}
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Cartao titulo="Em aberto">
          <p className="text-[26px] font-bold tabular-nums">{reais(dados.total)}</p>
          <p className="mt-1 text-[13px] text-suave">
            {cupons.length} cupom(ns) ainda não fechados
          </p>
        </Cartao>
        <Cartao titulo="Valor cheio">
          <p className="text-[26px] font-bold tabular-nums">{reais(dados.total_cheio)}</p>
          <p className="mt-1 text-[13px] text-suave">se fosse pelo preço de venda</p>
        </Cartao>
        <Cartao titulo="Você economizou">
          <p className="text-[26px] font-bold tabular-nums">{reais(dados.desconto)}</p>
          <p className="mt-1 text-[13px] text-suave">
            {dados.total_cheio > 0
              ? ((dados.desconto / dados.total_cheio) * 100).toFixed(1) + "% do cheio"
              : "—"}
          </p>
        </Cartao>
      </div>

      {/* 🔑 O ciclo em curso, para a pessoa saber ATÉ QUANDO o que ela consumir
          entra nesta conta — que é a pergunta natural de quem vai pagar. */}
      {periodo && (
        <Aviso tipo="info">
          O período aberto vai de <b>{dataBr(periodo.inicio)}</b> a{" "}
          <b>{dataBr(periodo.fim)}</b>
          {periodo.nome ? ` (${periodo.nome})` : ""}. O que estiver em aberto entra no
          fechamento dele.
        </Aviso>
      )}

      <Cartao
        titulo="O que ainda não foi fechado"
        descricao="Cada cupom, com o que custaria e o que está sendo cobrado."
      >
        {!cupons.length ? (
          <Vazio>Nada em aberto. Você está em dia.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Documento</th>
                  <th className="num">Itens</th>
                  <th className="num">Cheio</th>
                  <th className="num">A pagar</th>
                </tr>
              </thead>
              <tbody>
                {cupons.map((c) => (
                  <tr key={c.id}>
                    <td className="whitespace-nowrap">
                      {dataBr(c.data)}
                      {c.hora ? (
                        <span className="text-suave"> às {String(c.hora).slice(0, 5)}</span>
                      ) : null}
                    </td>
                    <td className="text-suave">{c.documento ?? `#${c.id}`}</td>
                    <td className="num tabular-nums">{c.itens}</td>
                    <td className="num tabular-nums text-suave">{reais(c.total_cheio)}</td>
                    <td className="num font-semibold tabular-nums">{reais(c.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      {historico.length > 0 && (
        <Cartao
          titulo="Períodos já fechados"
          descricao="O recibo de cada ciclo, do jeito que foi cobrado."
        >
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Período</th>
                  <th className="num">Cupons</th>
                  <th className="num">Cheio</th>
                  <th className="num">Desconto</th>
                  <th className="num">Cobrado</th>
                </tr>
              </thead>
              <tbody>
                {historico.map((h) => (
                  <tr key={h.id}>
                    <td className="whitespace-nowrap">
                      {h.nome || `${dataBr(h.inicio)} a ${dataBr(h.fim)}`}
                      {h.nome && (
                        <span className="block text-[12.5px] text-suave">
                          {dataBr(h.inicio)} a {dataBr(h.fim)}
                        </span>
                      )}
                    </td>
                    <td className="num tabular-nums">{h.cupons}</td>
                    <td className="num tabular-nums text-suave">{reais(h.total_cheio)}</td>
                    <td className="num tabular-nums">{reais(h.desconto)}</td>
                    <td className="num font-semibold tabular-nums">{reais(h.total)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Cartao>
      )}

      <p className="text-[13px] text-suave">
        Dúvida sobre um cupom? Fale com quem cuida do fechamento — cada linha aqui é um
        cupom lançado no sistema. <Link href="/ajuda" className="underline">Ajuda</Link>
      </p>
    </div>
  );
}
