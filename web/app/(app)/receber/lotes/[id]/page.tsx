"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Vazio } from "@/components/ui";
import Voltar from "@/components/voltar";
import { reais } from "@/lib/cadastros";
import { hoje } from "@/lib/datas";
import {
  baixarLote, cancelarLote, estornarBaixa, lote as buscarLote, receberLote, tirarDocumento,
  type FormaPagamento, type Formas, type Lote,
} from "@/lib/receber";
import { useSessao } from "@/lib/sessao";
import { TabelaPorDocumento, type LinhaDocumento } from "../../../vendas/por-pessoa/tabelas-documento";
import { dataBr } from "../../../vendas/tipos";
import { EtiquetaDoLote } from "../../lotes";

/**
 * Um lote de cobrança: o valor congelado, os documentos, o relatório e a baixa.
 *
 * 🔑 **O relatório se BAIXA e se manda por fora** (decisão do dono, 22/10/2026).
 * ⚠️ **Baixa só do lote inteiro.** O que a pessoa não pagou sai do lote antes
 * ("tirar do lote") e volta para em aberto, para o próximo.
 */
export default function PaginaLote() {
  const { id } = useParams<{ id: string }>();
  const idLote = Number(id);
  const aviso = useAviso();
  const { pode } = useSessao();
  const gerir = pode("consumo.periodos");

  const [dados, setDados] = useState<{ lote: Lote; documentos: LinhaDocumento[];
                                       formas: Formas } | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [baixando, setBaixando] = useState(false);
  const [recebidoEm, setRecebidoEm] = useState(hoje());
  const [forma, setForma] = useState<FormaPagamento>("PIX");
  const [obs, setObs] = useState("");
  const [pergunta, setPergunta] = useState<null | "cancelar" | "estornar" | { tirar: LinhaDocumento }>(null);

  const carregar = useCallback(async () => {
    try {
      setDados(await buscarLote(idLote));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Lote não encontrado");
    }
  }, [idLote]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  async function agir(acao: () => Promise<{ message: string }>) {
    setOcupado(true);
    try {
      const r = await acao();
      aviso.sucesso(r.message);
      setPergunta(null);
      setBaixando(false);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível concluir");
    } finally {
      setOcupado(false);
    }
  }

  async function baixar(formato: "pdf" | "csv") {
    try {
      await baixarLote(idLote, formato);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gerar o relatório");
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;
  const { lote, documentos, formas } = dados;
  const emCobranca = lote.status === "ABERTO";

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Voltar href="/receber">contas a receber</Voltar>
          <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
            Lote nº {lote.id}
          </h1>
          <p className="mt-1 text-suave">
            <Link href={`/fornecedores/${lote.id_pessoa}`} className="link-registro">
              {lote.pessoa}
            </Link>{" "}
            · documentos {lote.desde ? `de ${dataBr(lote.desde)} ` : ""}até {dataBr(lote.ate)} ·{" "}
            <EtiquetaDoLote status={lote.status} />
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button id="lote-pdf" className="btn btn-secundario" onClick={() => baixar("pdf")}>
            Imprimir
          </button>
          <button className="btn btn-secundario" onClick={() => baixar("csv")}>
            Planilha
          </button>
          {gerir && emCobranca && (
            <>
              <button id="lote-dar-baixa" className="btn btn-primario" onClick={() => setBaixando(true)}>
                Dar baixa
              </button>
              <button className="btn btn-secundario" onClick={() => setPergunta("cancelar")}>
                Cancelar lote
              </button>
            </>
          )}
          {gerir && lote.status === "RECEBIDO" && (
            <button id="lote-estornar" className="btn btn-secundario" onClick={() => setPergunta("estornar")}>
              Estornar baixa
            </button>
          )}
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <Cartao titulo={lote.status === "RECEBIDO" ? "Recebido" : "A cobrar"}>
          <p id="lote-total" className="text-[26px] font-bold tabular-nums">{reais(lote.total)}</p>
          <p className="mt-1 text-[13px] text-suave">
            {lote.cupons} documento(s) · {reais(lote.total_cheio)} cheio, {reais(lote.desconto)} de desconto
          </p>
        </Cartao>
        <Cartao titulo="Gerado">
          <p className="text-[18px] font-semibold">{dataBr(lote.criado_em.slice(0, 10))}</p>
          <p className="mt-1 text-[13px] text-suave">
            {lote.criou ? `por ${lote.criou}` : ""}
            {lote.observacao ? ` · ${lote.observacao}` : ""}
          </p>
        </Cartao>
        <Cartao titulo="Baixa">
          {lote.status === "RECEBIDO" ? (
            <>
              <p id="lote-baixa" className="text-[18px] font-semibold">
                {lote.recebido_em ? dataBr(lote.recebido_em) : "—"} ·{" "}
                {lote.forma_pagamento ? formas[lote.forma_pagamento] : "—"}
              </p>
              <p className="mt-1 text-[13px] text-suave">
                {lote.baixou ? `por ${lote.baixou}` : ""}
                {lote.observacao_baixa ? ` · ${lote.observacao_baixa}` : ""}
              </p>
            </>
          ) : (
            <p className="text-suave">
              {lote.status === "CANCELADO"
                ? "Lote cancelado — os documentos voltaram para em aberto."
                : "Aguardando o pagamento."}
            </p>
          )}
        </Cartao>
      </div>

      {baixando && (
        <Cartao titulo="Dar baixa no lote" descricao="O lote inteiro foi pago. Se faltou alguma parte, tire o documento do lote antes.">
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              void agir(() => receberLote(lote.id, {
                recebido_em: recebidoEm, forma_pagamento: forma, observacao: obs.trim() || null,
              }));
            }}
          >
            <div className="grid gap-4 sm:grid-cols-3">
              <Campo rotulo="Recebido em">
                <input id="baixa-data" className="campo" type="date" required value={recebidoEm}
                  onChange={(e) => setRecebidoEm(e.target.value)} />
              </Campo>
              <Campo rotulo="Forma">
                <select id="baixa-forma" className="campo" value={forma}
                  onChange={(e) => setForma(e.target.value as FormaPagamento)}>
                  {(Object.keys(formas) as FormaPagamento[]).map((f) => (
                    <option key={f} value={f}>{formas[f]}</option>
                  ))}
                </select>
              </Campo>
              <Campo rotulo="Observação" dica="opcional — ex.: o que foi trocado na permuta">
                <input id="baixa-obs" className="campo" maxLength={500} value={obs}
                  onChange={(e) => setObs(e.target.value)} />
              </Campo>
            </div>
            <div className="flex gap-2">
              <button id="baixa-confirmar" className="btn btn-primario" type="submit"
                aria-busy={ocupado} disabled={ocupado}>
                Confirmar baixa de {reais(lote.total)}
              </button>
              <button type="button" className="btn btn-secundario" onClick={() => setBaixando(false)}>
                Cancelar
              </button>
            </div>
          </form>
        </Cartao>
      )}

      <Cartao titulo={`${documentos.length} documento(s)`} descricao="Cada cupom, com os itens.">
        {!documentos.length ? (
          <Vazio>Nenhum documento neste lote.</Vazio>
        ) : (
          <div className="flex flex-col gap-4">
            <TabelaPorDocumento linhas={documentos} comItens />
            {gerir && emCobranca && (
              <div className="flex flex-wrap gap-x-4 gap-y-2 text-[13.5px]">
                <span className="text-suave">Tirar do lote (volta para em aberto):</span>
                {documentos.map((d) => (
                  <button key={d.id_venda} className="link-acao" data-tirar={d.id_venda}
                    onClick={() => setPergunta({ tirar: d })}>
                    {d.documento || `#${d.id_venda}`} ({dataBr(d.data)})
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </Cartao>

      {pergunta === "cancelar" && (
        <Confirmacao titulo="Cancelar o lote?" rotuloConfirmar="Cancelar o lote" perigo
          rotuloCancelar="Voltar" ocupado={ocupado}
          aoConfirmar={() => agir(() => cancelarLote(lote.id))} aoCancelar={() => setPergunta(null)}>
          Os {lote.cupons} documento(s) voltam para <b>em aberto</b> e podem entrar num novo lote.
          O lote cancelado fica no histórico.
        </Confirmacao>
      )}
      {pergunta === "estornar" && (
        <Confirmacao titulo="Estornar a baixa?" rotuloConfirmar="Estornar" rotuloCancelar="Voltar"
          ocupado={ocupado}
          aoConfirmar={() => agir(() => estornarBaixa(lote.id))} aoCancelar={() => setPergunta(null)}>
          O lote volta a estar <b>em cobrança</b>, com os mesmos documentos e o mesmo valor.
        </Confirmacao>
      )}
      {pergunta && typeof pergunta === "object" && (
        <Confirmacao titulo="Tirar o documento do lote?" rotuloConfirmar="Tirar do lote"
          rotuloCancelar="Voltar" ocupado={ocupado}
          aoConfirmar={() => agir(() => tirarDocumento(lote.id, pergunta.tirar.id_venda))}
          aoCancelar={() => setPergunta(null)}>
          O documento <b>{pergunta.tirar.documento || `#${pergunta.tirar.id_venda}`}</b> (
          {reais(pergunta.tirar.total)}) volta para em aberto e o valor do lote é refeito.
          {documentos.length === 1 && " Como é o último, o lote é cancelado."}
        </Confirmacao>
      )}
    </div>
  );
}
