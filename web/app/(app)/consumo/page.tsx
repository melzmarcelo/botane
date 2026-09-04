"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hoje, primeiroDiaDoMes } from "@/lib/datas";
import { reais } from "@/lib/cadastros";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Aviso, Campo, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { dataBr } from "../vendas/tipos";

/**
 * Períodos de consumo — o ciclo que se abre, acumula e se fecha no pagamento.
 *
 * 🔑 **Pedido do dono (04/09/2026):** "o Administrador vai e abre um periodo de
 * X dias, de tal dia a tal dia. ai todos os consumos vão para este periodo. ai
 * quando for realizado o pagamento e fecha este periodo."
 *
 * ⚠️ **O fechamento leva TUDO que está em aberto até a data final**, inclusive
 * consumo anterior ao início que ninguém pagou — deixá-lo de fora faria o saldo
 * daquela pessoa ficar errado para sempre. Como isso surpreende, a tela DIZ
 * quantos cupons vêm de antes, antes de o botão ser clicado.
 */

type Linha = {
  id_pessoa: number;
  pessoa: string;
  cupom_base: string | null;
  cupons: number;
  itens: number;
  total_cheio: number;
  desconto: number;
  total: number;
  desde?: string;
  ate?: string;
};

type Periodo = {
  id: number;
  nome: string | null;
  inicio: string;
  fim: string;
  status: "ABERTO" | "FECHADO";
  aberto_em: string;
  fechado_em: string | null;
  observacao: string | null;
  abriu: string | null;
  fechou: string | null;
  pessoas: number;
  total: number;
};

type Previa = {
  anteriores: number;
  no_periodo: number;
  depois: number;
  desde: string | null;
};

type Resposta = {
  periodos: Periodo[];
  aberto: Periodo | null;
  em_aberto: Linha[];
  previa: Previa | null;
  total_em_aberto: number;
};

export default function PaginaConsumoPeriodos() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const gerir = pode("consumo.periodos");

  const [dados, setDados] = useState<Resposta | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [abrindo, setAbrindo] = useState(false);
  const [confirmando, setConfirmando] = useState(false);

  const [inicio, setInicio] = useState(primeiroDiaDoMes());
  const [fim, setFim] = useState(hoje());
  const [nome, setNome] = useState("");

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      setDados(await api.get<Resposta>("/consumo/periodos"));
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function abrir(e: FormEvent) {
    e.preventDefault();
    setOcupado(true);
    try {
      await api.post("/consumo/periodos", { inicio, fim, nome: nome.trim() || null });
      aviso.sucesso("Período aberto");
      setAbrindo(false);
      setNome("");
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível abrir o período");
    } finally {
      setOcupado(false);
    }
  }

  async function fechar() {
    if (!dados?.aberto) return;
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(
        `/consumo/periodos/${dados.aberto.id}/fechar`, {});
      aviso.sucesso(r.message);
      setConfirmando(false);
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível fechar");
    } finally {
      setOcupado(false);
    }
  }

  async function reabrir(id: number) {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/consumo/periodos/${id}/reabrir`, {});
      aviso.sucesso(r.message);
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível reabrir");
    } finally {
      setOcupado(false);
    }
  }

  const aberto = dados?.aberto ?? null;
  const emAberto = dados?.em_aberto ?? [];
  const previa = dados?.previa ?? null;
  // O último fechado é o único que se reabre — reabrir um antigo devolveria
  // para "em aberto" vendas que os ciclos seguintes já cobraram.
  const ultimoFechado = (dados?.periodos ?? []).find((p) => p.status === "FECHADO");

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[24px] font-bold tracking-tight sm:text-[30px]">
            Períodos de consumo
          </h1>
          <p className="mt-1 text-suave">
            O ciclo que acumula o consumo do pessoal e se fecha no pagamento.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link href="/vendas/por-pessoa" className="btn btn-secundario">
            Consumo por pessoa
          </Link>
          {gerir && !aberto && (
            <button className="btn btn-primario" onClick={() => setAbrindo(true)}>
              Abrir período
            </button>
          )}
          {gerir && aberto && (
            <button
              className="btn btn-primario"
              onClick={() => setConfirmando(true)}
              disabled={ocupado}
            >
              Fechar período
            </button>
          )}
        </div>
      </header>

      {abrindo && (
        <Cartao titulo="Abrir período" descricao="Um por loja de cada vez.">
          <form onSubmit={abrir} className="flex flex-col gap-4">
            <div className="grid gap-4 sm:grid-cols-3">
              <Campo rotulo="De">
                <input className="campo" type="date" required value={inicio}
                  onChange={(e) => setInicio(e.target.value)} />
              </Campo>
              <Campo rotulo="Até">
                <input className="campo" type="date" required value={fim}
                  onChange={(e) => setFim(e.target.value)} />
              </Campo>
              <Campo rotulo="Nome" dica="opcional — as datas já identificam">
                <input className="campo" placeholder="Setembro/1ª quinzena"
                  value={nome} onChange={(e) => setNome(e.target.value)} />
              </Campo>
            </div>
            <div className="flex gap-2">
              <button className="btn btn-primario" type="submit" disabled={ocupado}>
                {ocupado ? "Abrindo…" : "Abrir"}
              </button>
              <button type="button" className="btn btn-secundario"
                onClick={() => setAbrindo(false)}>
                Cancelar
              </button>
            </div>
          </form>
        </Cartao>
      )}

      {/* ⚠️ **A consequência dita ANTES do clique.** Fechar reescreve centenas de
          vendas de uma vez, e o que vem de antes do início é a parte que
          surpreende — é justamente ela que precisa aparecer aqui. */}
      {confirmando && aberto && (
        <Cartao titulo="Fechar o período?">
          <Aviso tipo="info">
            Vai cobrar <b>{reais(dados?.total_em_aberto ?? 0)}</b> de{" "}
            <b>{emAberto.length} pessoa(s)</b>, marcando os cupons como pagos.
            {previa && previa.anteriores > 0 && (
              <>
                {" "}
                <b>
                  {previa.anteriores} cupom(ns) são anteriores a{" "}
                  {dataBr(aberto.inicio)}
                </b>{" "}
                e entram junto: é consumo que ainda não foi pago, e deixá-lo de fora
                faria o saldo dessas pessoas ficar errado para sempre.
              </>
            )}
            {previa && previa.depois > 0 && (
              <>
                {" "}
                {previa.depois} cupom(ns) posteriores a {dataBr(aberto.fim)} ficam para o
                próximo ciclo.
              </>
            )}
          </Aviso>
          <div className="mt-4 flex gap-2">
            <button className="btn btn-primario" onClick={fechar} disabled={ocupado}>
              {ocupado ? "Fechando…" : "Fechar e cobrar"}
            </button>
            <button className="btn btn-secundario" onClick={() => setConfirmando(false)}>
              Cancelar
            </button>
          </div>
        </Cartao>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <Cartao titulo="Em aberto agora">
          <p className="text-[26px] font-bold tabular-nums">
            {reais(dados?.total_em_aberto ?? 0)}
          </p>
          <p className="mt-1 text-[13px] text-suave">
            {emAberto.length} pessoa(s) com consumo não fechado
          </p>
        </Cartao>
        <Cartao titulo="Ciclo atual">
          {aberto ? (
            <>
              <p className="text-[18px] font-semibold">
                {aberto.nome || `${dataBr(aberto.inicio)} a ${dataBr(aberto.fim)}`}
              </p>
              <p className="mt-1 text-[13px] text-suave">
                {dataBr(aberto.inicio)} a {dataBr(aberto.fim)}
                {aberto.abriu ? ` · aberto por ${aberto.abriu}` : ""}
              </p>
            </>
          ) : (
            <p className="text-suave">
              Nenhum período aberto. O consumo continua sendo registrado e entra no
              próximo ciclo.
            </p>
          )}
        </Cartao>
        <Cartao titulo="Já fechados">
          <p className="text-[26px] font-bold tabular-nums">
            {(dados?.periodos ?? []).filter((p) => p.status === "FECHADO").length}
          </p>
          <p className="mt-1 text-[13px] text-suave">ciclos pagos</p>
        </Cartao>
      </div>

      <Cartao titulo={`Em aberto — ${emAberto.length} pessoa(s)`}>
        {carregando ? (
          <p className="text-suave">carregando…</p>
        ) : !emAberto.length ? (
          <Vazio>Ninguém com consumo em aberto.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Pessoa</th>
                  <th>Desde</th>
                  <th className="num">Cupons</th>
                  <th className="num">Cheio</th>
                  <th className="num">Desconto</th>
                  <th className="num">A cobrar</th>
                </tr>
              </thead>
              <tbody>
                {emAberto.map((l) => (
                  <tr key={l.id_pessoa}>
                    <td>
                      <Link href={`/fornecedores/${l.id_pessoa}`} className="link-registro">
                        {l.pessoa}
                      </Link>
                      {l.cupom_base === "CUSTO" && (
                        <>
                          {" "}
                          <Etiqueta cor="neutro">pelo custo</Etiqueta>
                        </>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-suave">
                      {l.desde ? dataBr(l.desde) : "—"}
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
        )}
      </Cartao>

      <Cartao titulo="Ciclos" descricao="O mais recente primeiro.">
        {!(dados?.periodos ?? []).length ? (
          <Vazio>Nenhum período criado ainda.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Período</th>
                  <th>Situação</th>
                  <th className="num">Pessoas</th>
                  <th className="num">Cobrado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {(dados?.periodos ?? []).map((p) => (
                  <tr key={p.id}>
                    <td className="whitespace-nowrap">
                      <Link href={`/consumo/${p.id}`} className="link-registro">
                        {p.nome || `${dataBr(p.inicio)} a ${dataBr(p.fim)}`}
                      </Link>
                      <span className="block text-[12.5px] text-suave">
                        {dataBr(p.inicio)} a {dataBr(p.fim)}
                      </span>
                    </td>
                    <td>
                      {p.status === "ABERTO" ? (
                        <Etiqueta cor="erva">aberto</Etiqueta>
                      ) : (
                        <>
                          <Etiqueta cor="neutro">fechado</Etiqueta>
                          {p.fechou && (
                            <span className="block text-[12.5px] text-suave">
                              por {p.fechou}
                            </span>
                          )}
                        </>
                      )}
                    </td>
                    <td className="num tabular-nums">
                      {p.status === "FECHADO" ? p.pessoas : "—"}
                    </td>
                    <td className="num font-semibold tabular-nums">
                      {p.status === "FECHADO" ? reais(p.total) : "—"}
                    </td>
                    <td className="text-right">
                      {/* ⚠️ Só o ÚLTIMO fechado se reabre: reabrir um antigo
                          devolveria para "em aberto" vendas que os ciclos
                          seguintes já cobraram, e a mesma dívida seria cobrada
                          duas vezes. */}
                      {gerir && p.status === "FECHADO" && p.id === ultimoFechado?.id &&
                        !aberto && (
                        <button
                          className="link-acao"
                          onClick={() => reabrir(p.id)}
                          disabled={ocupado}
                          title="Desfaz o fechamento e devolve os cupons para em aberto"
                        >
                          reabrir
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>
    </div>
  );
}
