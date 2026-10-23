"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Aviso, Cartao, Etiqueta, Vazio } from "@/components/ui";
import type { Formas, Lote } from "@/lib/receber";
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

type MeuConsumo = {
  vinculado: boolean;
  pessoa: { id: number; nome: string; cupom_base: string | null;
            cupom_desconto_pct: number | null } | null;
  cupons: Cupom[];
  total: number;
  total_cheio: number;
  desconto: number;
  /** 🔑 Os lotes já mandados e ainda não pagos (22/10/2026). */
  em_cobranca: Lote[];
  /** Os lotes pagos — o recibo de cada um, do jeito que foi cobrado. */
  historico: Lote[];
  formas: Formas;
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

  const { pessoa, cupons, historico, em_cobranca: emCobranca, formas } = dados;

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
            {cupons.length} cupom(ns) ainda não cobrados
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

      {/* 🔑 **O que já foi mandado e espera o pagamento** (22/10/2026): o lote é a
          cobrança que a pessoa recebeu, e é por ele que ela confere o valor. */}
      {emCobranca.length > 0 && (
        <Cartao
          titulo="Em cobrança"
          descricao="Lotes que já foram enviados a você e aguardam o pagamento."
        >
          <TabelaDeLotes lotes={emCobranca} formas={formas} />
        </Cartao>
      )}

      <Cartao
        titulo="O que ainda não foi cobrado"
        descricao="Cada cupom, com o que custaria e o que está sendo cobrado."
      >
        {!cupons.length ? (
          <Vazio>Nada em aberto. Você está em dia.</Vazio>
        ) : (
          <div className="grid-rolante">
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
          titulo="Já pago"
          descricao="O recibo de cada lote, do jeito que foi cobrado."
        >
          <TabelaDeLotes lotes={historico} formas={formas} pago />
        </Cartao>
      )}

      <p className="text-[13px] text-suave">
        Dúvida sobre um cupom? Fale com quem cuida das cobranças — cada linha aqui é um
        cupom lançado no sistema. <Link href="/ajuda" className="underline">Ajuda</Link>
      </p>
    </div>
  );
}

function TabelaDeLotes({ lotes, formas, pago = false }: {
  lotes: Lote[];
  formas: Formas;
  pago?: boolean;
}) {
  return (
    <div className="grid-rolante">
      <table className="tabela">
        <thead>
          <tr>
            <th>Lote</th>
            <th>{pago ? "Pago em" : "Enviado em"}</th>
            <th className="num">Cupons</th>
            <th className="num">Cheio</th>
            <th className="num">Desconto</th>
            <th className="num">{pago ? "Pago" : "A pagar"}</th>
          </tr>
        </thead>
        <tbody>
          {lotes.map((l) => (
            <tr key={l.id}>
              <td className="whitespace-nowrap">
                Nº {l.id}
                <span className="block text-[12.5px] text-suave">
                  {l.desde ? `${dataBr(l.desde)} a ` : "até "}{dataBr(l.ate)}
                </span>
              </td>
              <td className="whitespace-nowrap">
                {pago && l.recebido_em ? dataBr(l.recebido_em) : dataBr(l.criado_em.slice(0, 10))}
                {pago && l.forma_pagamento && (
                  <span className="block text-[12.5px] text-suave">
                    {formas[l.forma_pagamento] ?? l.forma_pagamento}
                  </span>
                )}
              </td>
              <td className="num tabular-nums">{l.cupons}</td>
              <td className="num tabular-nums text-suave">{reais(l.total_cheio)}</td>
              <td className="num tabular-nums">{reais(l.desconto)}</td>
              <td className="num font-semibold tabular-nums">{reais(l.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
