"use client";

/**
 * A aba Arquivo do catálogo de PDF: o que o site exibe.
 *
 * 🔑 **Pedido do dono (21/09/2026):** *"criei o catálogo, agora tenho que poder
 * carregar o PDF, neste caso para ele ser exibido."* Morava numa coluna da lista;
 * desde a reforma de 15/10/2026 o catálogo de PDF também tem página, como o
 * montado — a lista só mostra e abre.
 * ⚠️ O `<input>` é `sr-only` dentro de um rótulo `relative`: um absoluto sem
 * ancestral posicionado escapa e faz a página rolar de lado (330 px medidos).
 */

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Cartao, Confirmacao } from "@/components/ui";
import * as cat from "@/lib/catalogos";

/** 1,4 MB — não 1468006 bytes: quem confere lê o tamanho de relance. */
const tamanho = (b: number | null) => {
  if (!b) return "";
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`;
  return `${(b / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
};

export default function AbaArquivo({ capa, podeEditar, aoMudar }: {
  capa: cat.Catalogo; podeEditar: boolean; aoMudar: () => Promise<void>;
}) {
  const aviso = useAviso();
  const [enviando, setEnviando] = useState(false);
  const [tirando, setTirando] = useState(false);

  async function enviar(arquivo: File | undefined) {
    if (!arquivo) return;
    setEnviando(true);
    try {
      const r = await cat.enviarArquivo(capa.id, arquivo);
      await aoMudar();
      aviso.sucesso(`PDF de “${r.nome}” carregado.`);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível enviar o PDF");
    } finally {
      setEnviando(false);
    }
  }

  async function tirar() {
    try {
      const r = await cat.removerArquivo(capa.id);
      setTirando(false);
      await aoMudar();
      aviso.sucesso(`O PDF de “${r.nome}” foi removido.`);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível remover o PDF");
    }
  }

  return (
    <Cartao titulo="O PDF" descricao="O arquivo que o site de reservas mostra ao cliente. Até 10 MB.">
      <div className="flex flex-col gap-4">
        {/* ⚠️ Ativo sem PDF é AVISADO: o site anuncia um cardápio e não tem o que mostrar. */}
        {!capa.arquivo_url && capa.situacao === "ATIVO" && (
          <Aviso tipo="erro">Está ativo e sem PDF — o site não tem o que exibir.</Aviso>
        )}
        {capa.arquivo_url ? (
          <p className="text-[14px]">
            {/* `rel="noreferrer"`: abre para conferir, sem dar à aba nova acesso a esta. */}
            <a className="link-registro" href={cat.enderecoDoArquivo(capa.arquivo_url)} target="_blank" rel="noreferrer">
              {capa.arquivo_nome ?? "ver o PDF"}
            </a>
            <span className="ml-2 text-[13px] text-suave">
              {tamanho(capa.arquivo_bytes)}
              {capa.arquivo_em && ` · ${new Date(capa.arquivo_em).toLocaleDateString("pt-BR")}`}
            </span>
          </p>
        ) : (
          <p className="text-[14px] text-suave">Nenhum PDF ainda.</p>
        )}
        {podeEditar && (
          <div className="flex flex-wrap items-center gap-3">
            <label className={`btn btn-primario relative cursor-pointer ${enviando ? "opacity-60" : ""}`}>
              {enviando ? "Enviando…" : capa.arquivo_url ? "Trocar PDF" : "Carregar PDF"}
              <input type="file" accept="application/pdf,.pdf" id={`arquivo-catalogo-${capa.id}`} className="sr-only"
                     disabled={enviando}
                     onChange={(e) => { void enviar(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            {capa.arquivo_url && (
              <button type="button" className="link-acao link-acao-erro" onClick={() => setTirando(true)}>
                tirar PDF
              </button>
            )}
          </div>
        )}
      </div>
      {tirando && (
        <Confirmacao titulo={`Tirar o PDF de “${capa.nome}”?`} rotuloConfirmar="Tirar o PDF" perigo
                     aoConfirmar={() => void tirar()} aoCancelar={() => setTirando(false)}>
          O catálogo continua cadastrado, com o nome e o período. O que sai é o arquivo
          {capa.situacao === "ATIVO" && <> — e ele está <b>ativo</b>, então o site fica sem nada para mostrar</>}
          . Para pôr outro, use “Trocar PDF”.
        </Confirmacao>
      )}
    </Cartao>
  );
}
