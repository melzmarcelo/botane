"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { CANAIS, dataBr, ORIGEM_CUSTO, ORIGENS, VendaDetalhe } from "../tipos";

/**
 * Uma venda, inteira, numa página só.
 *
 * A lista mostrava data, origem e total — e mais nada. Quem precisava saber o
 * que foi vendido, quanto aquilo custou pela ficha ou se o estoque baixou não
 * tinha para onde ir; a única resposta era abrir o banco.
 *
 * A página responde três perguntas em ordem: **o que entrou de dinheiro**,
 * **o que saiu de custo** e **o que saiu da prateleira**. As três juntas são o
 * que faz a variância daquele dia ter explicação.
 */
export default function PaginaVenda() {
  const { id } = useParams<{ id: string }>();
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeCancelar = pode("cmv.painel") || pode("cmv.fechamento");

  const [venda, setVenda] = useState<VendaDetalhe | null>(null);
  const [erro, setErro] = useState("");
  const [confirmando, setConfirmando] = useState(false);

  const carregar = useCallback(async () => {
    try {
      setVenda(await api.get<VendaDetalhe>(`/vendas/${id}`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function cancelar() {
    try {
      const r = await api.delete<{ message: string }>(`/vendas/${id}`);
      aviso.sucesso(r.message);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível cancelar");
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!venda) return <Carregando />;

  const margem = venda.receita - venda.custo_teorico;
  const parcial = venda.itens_sem_custo > 0;

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link href="/vendas" className="link-voltar">
            vendas
          </Link>
          <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
            {venda.documento ?? `Venda #${venda.id}`}
          </h1>
          <p className="mt-1 text-suave">
            {dataBr(venda.data)}
            {venda.hora ? ` às ${String(venda.hora).slice(0, 5)}` : ""} ·{" "}
            {ORIGENS[venda.origem] ?? venda.origem.toLowerCase()}
            {venda.canal ? ` · ${CANAIS[venda.canal] ?? venda.canal.toLowerCase()}` : ""}
            {venda.mesa ? ` · mesa ${venda.mesa}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {venda.cancelada ? (
            <Etiqueta cor="alerta">cancelada</Etiqueta>
          ) : (
            podeCancelar && (
              <button className="btn btn-secundario" onClick={() => setConfirmando(true)}>
                Cancelar venda
              </button>
            )
          )}
        </div>
      </header>

      {/* ⚠️ O aviso vem ANTES dos números, não depois. Com item sem ficha o
          custo sai menor do que foi de verdade e a margem sai alta demais — quem
          lê o número primeiro já formou a impressão errada. */}
      {parcial && (
        <Aviso tipo="info">
          {venda.itens_sem_custo} de {venda.itens.length} item(ns) sem custo: o produto não tem
          ficha técnica. O custo e a margem abaixo são <b>parciais</b> — não são o resultado
          desta venda.
        </Aviso>
      )}
      {/* 🔑 **Custo vindo de ficha em RASCUNHO é um número de verdade — e ainda
          pode mudar.** Antes o item entrava com custo ZERO e a margem saía alta
          demais, sem nada denunciando; agora ele custeia, e o aviso diz que a
          receita não passou por homologação. Sem o aviso, o custo de uma receita
          em rascunho seria indistinguível do de uma aprovada. */}
      {venda.itens_ficha_rascunho > 0 && (
        <Aviso tipo="info">
          {venda.itens_ficha_rascunho} item(ns) com custo vindo de{" "}
          <b>ficha técnica em rascunho</b>: a receita ainda não foi homologada, e este
          custo pode mudar quando ela for. O valor abaixo é o que se sabia no momento da
          venda — ele fica congelado, mesmo depois da homologação.
        </Aviso>
      )}
      {venda.itens_sem_vinculo > 0 && (
        <Aviso tipo="info">
          {venda.itens_sem_vinculo} item(ns) não acharam produto no cadastro.{" "}
          <Link href="/vendas/sem-vinculo" className="underline">
            resolver o de-para
          </Link>
        </Aviso>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Cartao titulo="Receita">
          <p className="text-[26px] font-bold tabular-nums">{reais(venda.receita)}</p>
          {Number(venda.desconto) > 0 && (
            <p className="mt-1 text-[13px] text-suave">
              desconto de {reais(Number(venda.desconto))} já descontado
            </p>
          )}
        </Cartao>
        <Cartao titulo={parcial ? "Custo teórico (parcial)" : "Custo teórico"}>
          <p className="text-[26px] font-bold tabular-nums">{reais(venda.custo_teorico)}</p>
          <p className="mt-1 text-[13px] text-suave">pela ficha, congelado na importação</p>
        </Cartao>
        <Cartao titulo={parcial ? "Margem (parcial)" : "Margem"}>
          <p className="text-[26px] font-bold tabular-nums">{reais(margem)}</p>
          <p className="mt-1 text-[13px] text-suave">
            {venda.receita > 0
              ? `${((margem / venda.receita) * 100).toFixed(1)}% da receita`
              : "—"}
          </p>
        </Cartao>
      </div>

      <Cartao titulo={`${venda.itens.length} item(ns)`}>
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead>
              <tr>
                <th>Produto</th>
                <th className="num">Qtd</th>
                <th className="num">Unitário</th>
                <th className="num">Total</th>
                <th className="num">Custo un.</th>
                <th>De onde veio o custo</th>
              </tr>
            </thead>
            <tbody>
              {venda.itens.map((i) => (
                <tr key={i.id}>
                  <td>
                    {i.id_produto ? (
                      <Link href={`/produtos/${i.id_produto}`} className="link-registro">
                        {i.produto}
                      </Link>
                    ) : (
                      <span className="text-suave">
                        {i.descricao_pdv ?? "—"} <Etiqueta cor="alerta">sem vínculo</Etiqueta>
                      </span>
                    )}
                    <span className="block text-[12.5px] text-suave">
                      {[i.produto_codigo, i.setor, i.categoria].filter(Boolean).join(" · ") ||
                        (i.codigo_pdv ? `código no PDV ${i.codigo_pdv}` : "")}
                    </span>
                  </td>
                  <td className="num tabular-nums">{Number(i.quantidade)}</td>
                  <td className="num tabular-nums">{reais(Number(i.valor_unitario))}</td>
                  <td className="num font-semibold tabular-nums">
                    {reais(Number(i.valor_total))}
                  </td>
                  <td className="num tabular-nums">
                    {i.custo_ficha_unitario === null
                      ? "—"
                      : reais(Number(i.custo_ficha_unitario))}
                  </td>
                  <td className="text-[13px] text-suave">
                    {ORIGEM_CUSTO[i.origem_custo ?? ""] ?? i.origem_custo ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Cartao>

      {/* ⚠️ Vender é sair do estoque. Esta tabela é a PROVA disso — e, quando a
          venda é cancelada, é onde se vê que o produto voltou para a prateleira
          em vez de sumir do caixa e do estoque ao mesmo tempo. */}
      <Cartao
        titulo="Movimento no estoque"
        descricao="O que esta venda tirou da prateleira — e o que o cancelamento devolveu."
      >
        {!venda.movimentos.length ? (
          <Vazio>
            Nenhum movimento. Item de venda só baixa estoque quando o produto controla
            estoque — combo e serviço não controlam.
          </Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Produto</th>
                  <th>Tipo</th>
                  <th>Local</th>
                  <th className="num">Qtd</th>
                  <th className="num">Custo</th>
                </tr>
              </thead>
              <tbody>
                {venda.movimentos.map((m) => (
                  <tr key={m.id} className={m.id_estorno_de ? "text-suave" : ""}>
                    <td>{m.produto}</td>
                    <td className="text-[13px]">
                      {m.tipo.toLowerCase().replace(/_/g, " ")}
                      {m.id_estorno_de && (
                        <span className="ml-2">
                          <Etiqueta cor="neutro">estorno</Etiqueta>
                        </span>
                      )}
                    </td>
                    <td className="text-[13px]">{m.local ?? "—"}</td>
                    <td className="num tabular-nums">{Number(m.quantidade)}</td>
                    <td className="num tabular-nums">
                      {m.custo_total === null ? "—" : reais(Number(m.custo_total))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      <p className="text-[13px] text-suave">
        Importada em {venda.importada_em ? new Date(venda.importada_em).toLocaleString("pt-BR") : "—"}
        {venda.usuario ? ` por ${venda.usuario}` : ""}
        {venda.id_externo ? ` · cupom ${venda.id_externo} no PDV` : ""}
      </p>

      {confirmando && (
        <Confirmacao
          titulo="Cancelar a venda"
          rotuloConfirmar="Cancelar a venda"
          perigo
          aoCancelar={() => setConfirmando(false)}
          aoConfirmar={() => {
            setConfirmando(false);
            void cancelar();
          }}
        >
          <p>
            Cancelar <b>{venda.documento ?? `a venda #${venda.id}`}</b>?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            Ela sai da receita e do CMV, e o que baixou do estoque <b>volta por estorno</b>. A
            venda não é apagada — o histórico continua fiel ao que o PDV mandou.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
