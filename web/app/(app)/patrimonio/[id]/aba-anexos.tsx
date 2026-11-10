"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Cartao, Confirmacao, SeletorDeArquivo, Vazio } from "@/components/ui";
import { urlArquivo } from "@/lib/api";
import { anexar, apagarAnexo, dataBr, type Anexo, type BemDetalhe } from "@/lib/patrimonio";

const ACEITA = "image/png,image/jpeg,image/webp,application/pdf";

/** "1,4 MB", "320 KB". */
function tamanho(b: number) {
  return b >= 1024 * 1024 ? `${(b / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`
    : `${Math.max(1, Math.round(b / 1024))} KB`;
}

/**
 * Aba Fotos e documentos (157): as fotos do bem e os PDFs — nota, manual, certificado da
 * garantia, laudo do técnico.
 * 🔑 **Guardados no BANCO**, como a logo e a foto da ficha: o disco do App Platform some a cada
 * deploy. A primeira foto vira a capa da ficha (aba Dados do bem).
 * ⚠️ Os ids `anexo-arquivo`, `anexo-enviar`, `anexos-fotos` e `anexos-documentos` são os da bateria.
 */
export default function AbaAnexos({ bem, podeAnexar, aoMudar }: {
  bem: BemDetalhe; podeAnexar: boolean; aoMudar: () => void;
}) {
  const aviso = useAviso();
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [apagando, setApagando] = useState<Anexo | null>(null);
  const fotos = bem.anexos.filter((a) => a.tipo === "FOTO");
  const documentos = bem.anexos.filter((a) => a.tipo === "DOCUMENTO");

  async function enviar() {
    if (!arquivo) return;
    setEnviando(true);
    try {
      aviso.sucesso((await anexar(bem.id, arquivo)).message);
      setArquivo(null);
      aoMudar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível anexar");
    } finally {
      setEnviando(false);
    }
  }

  async function confirmarApagar() {
    if (!apagando) return;
    try {
      aviso.sucesso((await apagarAnexo(apagando.id)).message);
      aoMudar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível apagar");
    } finally {
      setApagando(null);
    }
  }

  const botaoApagar = (a: Anexo) => podeAnexar && (
    <button type="button" className="link-acao text-[13px]" onClick={() => setApagando(a)}
            aria-label={`apagar ${a.nome}`}>apagar</button>
  );

  return (
    <div className="flex flex-col gap-6">
      {podeAnexar && (
        <Cartao titulo="Anexar" descricao="Foto (PNG, JPG ou WEBP, até 2 MB) ou PDF (até 10 MB).">
          <div className="flex flex-wrap items-center gap-3">
            <SeletorDeArquivo id="anexo-arquivo" accept={ACEITA} arquivo={arquivo} onEscolher={setArquivo}
                              disabled={enviando} rotulo="Escolher foto ou PDF" />
            <button type="button" className="btn btn-primario" id="anexo-enviar"
                    disabled={!arquivo || enviando} aria-busy={enviando} onClick={() => void enviar()}>
              Anexar
            </button>
          </div>
        </Cartao>
      )}

      <Cartao titulo="Fotos" descricao={fotos.length ? "A primeira é a capa da ficha." : undefined}>
        {fotos.length ? (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4" id="anexos-fotos">
            {fotos.map((a) => (
              <li key={a.id} className="flex min-w-0 flex-col gap-1.5">
                <a href={urlArquivo(a.url) ?? "#"} target="_blank" rel="noreferrer">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={`${urlArquivo(a.url)}?w=480`} alt={a.nome} loading="lazy"
                       className="aspect-[4/3] w-full rounded-lg border border-linha object-cover" />
                </a>
                <div className="flex items-center justify-between gap-2 text-[12.5px] text-suave">
                  <span className="truncate" title={a.nome}>{dataBr(a.criado_em)}</span>
                  {botaoApagar(a)}
                </div>
              </li>
            ))}
          </ul>
        ) : <Vazio>Nenhuma foto do bem.</Vazio>}
      </Cartao>

      <Cartao titulo="Documentos">
        {documentos.length ? (
          <ul className="flex flex-col divide-y divide-linha" id="anexos-documentos">
            {documentos.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <a href={urlArquivo(a.url) ?? "#"} target="_blank" rel="noreferrer"
                   className="link-acao min-w-0 truncate text-[14.5px] font-semibold">{a.nome}</a>
                <span className="flex items-center gap-3 text-[12.5px] text-suave">
                  {tamanho(a.bytes)} · {dataBr(a.criado_em)}{a.enviado_por ? ` · ${a.enviado_por}` : ""}
                  {botaoApagar(a)}
                </span>
              </li>
            ))}
          </ul>
        ) : <Vazio>Nenhum documento — a nota, o manual ou o certificado da garantia podem ficar aqui.</Vazio>}
      </Cartao>

      {apagando && (
        <Confirmacao titulo="Apagar este anexo?" perigo rotuloConfirmar="Apagar"
                     aoConfirmar={() => void confirmarApagar()} aoCancelar={() => setApagando(null)}>
          <b>{apagando.nome}</b> sai do bem e não tem como voltar.
        </Confirmacao>
      )}
    </div>
  );
}
