"use client";

import { useState } from "react";
import { useAviso } from "@/components/aviso-flutuante";
import { Cartao, Confirmacao, Vazio } from "@/components/ui";
import { ArquivosService, origemDoArquivo, tamanho, type Orfaos } from "@/lib/arquivos";

import { plural } from "@/lib/numeros";
/**
 * Administração → Empresa → Arquivos sem dono.
 *
 * 🔑 **Pedido do dono (17/10/2026)**: fotos e vídeos ficam no banco, e até a 1.1.108 excluir uma
 * seção deixava a mídia dela para trás. A varredura só roda quando alguém pede (é uma consulta
 * que olha todas as colunas de arquivo), MOSTRA o que achou, e apaga depois da confirmação.
 */
export default function ArquivosSemDono() {
  const aviso = useAviso();
  const [dados, setDados] = useState<Orfaos | null>(null);
  const [procurando, setProcurando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [apagando, setApagando] = useState(false);

  async function procurar() {
    setProcurando(true);
    try {
      setDados(await ArquivosService.orfaos());
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível procurar os arquivos");
    } finally {
      setProcurando(false);
    }
  }

  async function apagar() {
    if (!dados) return;
    setApagando(true);
    try {
      const r = await ArquivosService.apagarOrfaos(dados.orfaos.map((o) => o.nome));
      aviso.sucesso(`${r.message} ${tamanho(r.bytes)} liberados.`);
      setConfirmando(false);
      await procurar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível apagar");
    } finally {
      setApagando(false);
    }
  }

  const grupos = new Map<string, { n: number; bytes: number }>();
  for (const o of dados?.orfaos ?? []) {
    const g = grupos.get(origemDoArquivo(o.dono)) ?? { n: 0, bytes: 0 };
    grupos.set(origemDoArquivo(o.dono), { n: g.n + 1, bytes: g.bytes + o.bytes });
  }

  return (
    <Cartao titulo="Arquivos sem dono"
            descricao="Fotos, vídeos e PDFs guardados que nenhum produto, seção, cartão, anúncio ou catálogo usa mais. Ocupam o banco e o backup. Os enviados há menos de um dia ficam de fora."
            acao={<button type="button" className="btn btn-secundario" id="orfaos-procurar"
                          aria-busy={procurando} disabled={procurando} onClick={() => void procurar()}>
              {procurando ? "Procurando…" : dados ? "Procurar de novo" : "Procurar"}</button>}>
      {!dados ? null : dados.orfaos_n === 0 ? (
        <Vazio>Nenhum arquivo sem dono. Guardados: {dados.total_n} ({tamanho(dados.total_bytes)}).</Vazio>
      ) : (
        <div className="flex flex-col gap-4" id="orfaos-resultado">
          <p className="text-[14.5px]">
            <strong>{dados.orfaos_n}</strong> de {dados.total_n} arquivos guardados não têm dono —{" "}
            <strong>{tamanho(dados.orfaos_bytes)}</strong> de {tamanho(dados.total_bytes)}.
          </p>
          <table className="tabela w-full max-w-[520px]">
            <thead><tr><th>Era</th><th className="text-right">Arquivos</th><th className="text-right">Tamanho</th></tr></thead>
            <tbody>
              {[...grupos.entries()].sort((a, b) => b[1].bytes - a[1].bytes).map(([nome, g]) => (
                <tr key={nome}><td>{nome}</td><td className="mono text-right">{g.n}</td>
                  <td className="mono text-right">{tamanho(g.bytes)}</td></tr>
              ))}
            </tbody>
          </table>
          <details className="text-[13px]">
            <summary className="link-acao cursor-pointer">ver um por um</summary>
            <ul className="mt-2 max-h-72 overflow-y-auto">
              {dados.orfaos.map((o) => (
                <li key={o.nome} className="mono py-0.5">
                  {o.nome} <span className="text-suave">· {tamanho(o.bytes)} · {new Date(o.criado_em).toLocaleDateString("pt-BR")}</span>
                </li>
              ))}
            </ul>
          </details>
          <div>
            <button type="button" className="btn btn-secundario link-acao-erro" id="orfaos-apagar"
                    onClick={() => setConfirmando(true)}>Apagar os {dados.orfaos_n}</button>
          </div>
        </div>
      )}
      {confirmando && dados && (
        <Confirmacao titulo={`Apagar ${plural(dados.orfaos_n, "arquivo", "arquivos")} sem dono?`} rotuloConfirmar="Apagar" perigo
                     ocupado={apagando} aoConfirmar={() => void apagar()} aoCancelar={() => setConfirmando(false)}>
          Libera {tamanho(dados.orfaos_bytes)}. Não há desfazer — mas só sai o que, na hora de apagar, continuar
          sem nenhum registro apontando para ele.
        </Confirmacao>
      )}
    </Cartao>
  );
}
