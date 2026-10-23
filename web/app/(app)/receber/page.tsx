"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BotaoExportar from "@/components/exportar";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Campo, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import { hoje } from "@/lib/datas";
import { emAberto, gerarLotes, type EmAberto } from "@/lib/receber";
import { useSessao } from "@/lib/sessao";
import { dataBr } from "../vendas/tipos";
import DocumentosDaPessoa from "./documentos";
import ListaDeLotes from "./lotes";

/**
 * Contas a receber do consumo — o que está em aberto, os lotes e a baixa.
 *
 * 🔑 **Pedido do dono (22/10/2026):** *"tirar esta questão de períodos [...] Ai ter
 * uma espécie de contas a receber. onde em um determinado dia, o usuário pode emitir
 * um relatório com os valores em aberto em determinado período. e pode, por exemplo,
 * gerar um lote, e quando receber, fazer a baixa destes documentos."*
 * ⚠️ **Um lote por pessoa** (decisão do dono): marcar várias pessoas gera um lote
 * para cada uma — cada um com o seu relatório e a sua baixa.
 */
export default function PaginaContasAReceber() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const gerir = pode("consumo.periodos");

  const [de, setDe] = useState("");
  const [ate, setAte] = useState("");
  const [dados, setDados] = useState<EmAberto | null>(null);
  const [erro, setErro] = useState("");
  const [marcadas, setMarcadas] = useState<Set<number>>(new Set());
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [aberta, setAberta] = useState<{ id: number; nome: string } | null>(null);
  // Muda a cada lote gerado, para a lista de lotes recarregar.
  const [versao, setVersao] = useState(0);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      setDados(await emAberto(de || undefined, ate || undefined));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível carregar o que está em aberto");
    }
  }, [de, ate]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const linhas = dados?.linhas ?? [];
  // ⚠️ Sem ninguém marcado, o lote é de TODOS os da lista — o "gerar da quinzena".
  const alvo = marcadas.size ? linhas.filter((l) => marcadas.has(l.id_pessoa)) : linhas;
  const totalAlvo = alvo.reduce((s, l) => s + Number(l.total), 0);
  // 🔑 A data de corte do lote é o "até" do filtro; sem ele, hoje.
  const corte = ate || hoje();

  function marcar(id: number) {
    setMarcadas((m) => {
      const n = new Set(m);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  async function gerar() {
    setOcupado(true);
    try {
      const r = await gerarLotes({
        ate: corte,
        de: de || null,
        ids_pessoa: alvo.map((l) => l.id_pessoa),
      });
      aviso.sucesso(r.message);
      setConfirmando(false);
      setMarcadas(new Set());
      setVersao((v) => v + 1);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar os lotes");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Vendas</p>
          <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
            Contas a receber
          </h1>
          <ExplicaTela>
            O consumo das pessoas que ainda não foi cobrado, os lotes de cobrança e a baixa
            quando o pagamento chega.
          </ExplicaTela>
        </div>
        <div className="flex flex-wrap gap-2">
          <BotaoExportar
            relatorio="consumo-pessoa"
            rotulo="Baixar relatório"
            iniciais={{
              situacao_consumo: "aberto",
              inicio: de,
              fim: ate,
              pessoas: [...marcadas],
              detalhe: ["sintetico"],
            }}
          />
          <Link href="/vendas/por-pessoa" className="btn btn-secundario">
            Consumo por pessoa
          </Link>
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Cartao titulo="Em aberto">
          <p id="receber-total-aberto" className="text-[26px] font-bold tabular-nums">
            {reais(dados?.total ?? 0)}
          </p>
          <p className="mt-1 text-[13px] text-suave">
            {linhas.length} pessoa(s) com consumo ainda não cobrado
          </p>
        </Cartao>
        <Cartao titulo="Em cobrança">
          <p className="text-[26px] font-bold tabular-nums">{reais(dados?.em_cobranca ?? 0)}</p>
          <p className="mt-1 text-[13px] text-suave">
            {dados?.lotes_em_cobranca ?? 0} lote(s) enviados, esperando o pagamento
          </p>
        </Cartao>
        <Cartao titulo="Desconto concedido">
          <p className="text-[26px] font-bold tabular-nums">{reais(dados?.desconto ?? 0)}</p>
          <p className="mt-1 text-[13px] text-suave">no que está em aberto</p>
        </Cartao>
      </div>

      <Cartao
        titulo="Em aberto"
        descricao="Marque as pessoas para gerar o lote só delas; sem marcar, o lote é de todas da lista."
      >
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <Campo rotulo="Documentos de" dica="todas as datas, se em branco">
              <input id="receber-de" className="campo" type="date" value={de}
                onChange={(e) => setDe(e.target.value)} />
            </Campo>
            <Campo rotulo="Até" dica="é a data de corte do lote; em branco, hoje">
              <input id="receber-ate" className="campo" type="date" value={ate}
                onChange={(e) => setAte(e.target.value)} />
            </Campo>
            {gerir && (
              <div className="flex items-end">
                <button
                  id="receber-gerar"
                  className="btn btn-primario"
                  disabled={!alvo.length || ocupado}
                  onClick={() => setConfirmando(true)}
                >
                  {marcadas.size ? `Gerar ${alvo.length} lote(s)` : "Gerar lotes de todos"}
                </button>
              </div>
            )}
          </div>

          {erro ? (
            <Aviso tipo="erro">{erro}</Aviso>
          ) : !dados ? (
            <p className="text-suave">carregando…</p>
          ) : !linhas.length ? (
            <Vazio>Ninguém com consumo em aberto neste recorte.</Vazio>
          ) : (
            <div className="grid-rolante">
              <table className="tabela" id="receber-em-aberto">
                <thead>
                  <tr>
                    {gerir && <th className="w-8"></th>}
                    <th>Pessoa</th>
                    <th>Desde</th>
                    <th className="num">Docs</th>
                    <th className="num">Cheio</th>
                    <th className="num">Desconto</th>
                    <th className="num">A cobrar</th>
                    <th className="num">Em cobrança</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {linhas.map((l) => (
                    <tr key={l.id_pessoa} data-pessoa={l.id_pessoa}>
                      {gerir && (
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`Marcar ${l.pessoa}`}
                            checked={marcadas.has(l.id_pessoa)}
                            onChange={() => marcar(l.id_pessoa)}
                          />
                        </td>
                      )}
                      <td className="min-w-[180px]">
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
                      <td className="whitespace-nowrap text-suave">{dataBr(l.desde)}</td>
                      <td className="num tabular-nums">{l.cupons}</td>
                      <td className="num tabular-nums text-suave">{reais(l.total_cheio)}</td>
                      <td className="num tabular-nums">{reais(l.desconto)}</td>
                      <td className="num font-semibold tabular-nums">{reais(l.total)}</td>
                      <td className="num tabular-nums text-suave">
                        {l.em_cobranca ? reais(l.em_cobranca) : "—"}
                      </td>
                      <td className="whitespace-nowrap text-right">
                        <button
                          className="link-acao"
                          data-documentos={l.id_pessoa}
                          onClick={() => setAberta({ id: l.id_pessoa, nome: l.pessoa })}
                        >
                          documentos
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Cartao>

      {aberta && (
        <DocumentosDaPessoa
          pessoa={aberta}
          de={de}
          ate={corte}
          gerir={gerir}
          aoFechar={() => setAberta(null)}
          aoGerar={async () => {
            setAberta(null);
            setVersao((v) => v + 1);
            await carregar();
          }}
        />
      )}

      <ListaDeLotes versao={versao} />

      {confirmando && (
        <Confirmacao
          titulo={alvo.length === 1 ? "Gerar o lote?" : `Gerar ${alvo.length} lotes?`}
          rotuloConfirmar="Gerar"
          ocupado={ocupado}
          aoConfirmar={gerar}
          aoCancelar={() => setConfirmando(false)}
        >
          <p id="receber-confirma">
            {alvo.length === 1 ? (
              <>Um lote para <b>{alvo[0].pessoa}</b></>
            ) : (
              <>Um lote para cada uma das <b>{alvo.length} pessoas</b></>
            )}
            , com o que está em aberto {de ? <>de <b>{dataBr(de)}</b> </> : ""}até{" "}
            <b>{dataBr(corte)}</b> — total de <b>{reais(totalAlvo)}</b>. Os documentos passam a
            estar <b>em cobrança</b> e não aceitam mais itens nem cancelamento até a baixa (ou
            até saírem do lote).
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
