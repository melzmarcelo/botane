"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import BotaoExportar from "@/components/exportar";
import ExplicaTela from "@/components/explica-tela";
import { Aviso, Cartao, SeletorDeArquivo, Vazio } from "@/components/ui";
import Voltar from "@/components/voltar";
import { importar, type ResultadoImportacao } from "@/lib/patrimonio";
import { useSessao } from "@/lib/sessao";

import { plural } from "@/lib/numeros";
/**
 * Importar os bens por planilha — a de inventário de equipamentos da casa (.xlsx, uma
 * aba por setor) ou a exportada do Patrimônio (corrigida no Excel e mandada de volta).
 *
 * ⚠️ **Prévia antes, sempre**: o botão de importar só aparece depois dela, e reenvia o
 * MESMO arquivo — o servidor confere de novo, então o que mudou no meio volta como recusa.
 * 🔑 A segunda importação da mesma planilha ATUALIZA (acha cada bem pelo código da casa,
 * ou pela plaqueta), e célula vazia não apaga o que foi cadastrado na tela.
 */
export default function ImportarPatrimonio() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const podeCadastrar = pode("patrimonio.cadastrar");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [sugestoes, setSugestoes] = useState(true);
  const [previa, setPrevia] = useState<ResultadoImportacao | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  async function enviar(simular: boolean) {
    if (!arquivo) return;
    setOcupado(true);
    setErro("");
    try {
      const r = await importar(arquivo, simular, sugestoes);
      setPrevia(r);
      if (!simular) aviso.sucesso(r.message);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível ler a planilha");
    } finally {
      setOcupado(false);
    }
  }

  const campos = (r: Record<string, string | null>) =>
    Object.entries(r).map(([k, v]) => (
      <span key={k} className="block">
        <span className="text-suave">{k}:</span> {v ?? "—"}
      </span>
    ));
  const onde = (x: { aba: string; linha: number }) => (x.aba ? `${x.aba} · ${x.linha}` : String(x.linha));
  const total = previa ? previa.novos.length + previa.mudam.length : 0;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Voltar href="/patrimonio">patrimônio</Voltar>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">Importar planilha</h1>
        <ExplicaTela>
          Os equipamentos de uma vez: a planilha de inventário da casa (uma aba por setor) ou a
          planilha baixada daqui, corrigida no Excel.
        </ExplicaTela>
      </header>

      <Cartao titulo="Como a planilha é lida">
        <ul className="ml-5 list-disc text-[13.5px] leading-relaxed text-suave">
          <li>Cada aba com a coluna <b>Equipamento</b> é lida; as outras (Resumo, Como usar) são puladas.</li>
          <li>O <b>setor</b> vem da linha “Setor no sistema Botané” da aba; o <b>local</b>, da coluna
            “Local no sistema” (OUTRO = sem local). Pelo nome, como nas Tabelas de apoio.</li>
          <li>O <b>código da casa</b> (BAR-02) vira o código de busca do bem: importar de novo
            atualiza, não duplica. A plaqueta ganha um código fixo (PAT-0001).</li>
          <li>Linha de origem <b>“Sugestão”</b> entra como <b>A confirmar</b> — fora dos alertas
            até alguém conferir que o equipamento existe.</li>
          <li>Célula vazia não muda nada. Próxima preventiva e status são calculados aqui.</li>
        </ul>
        <div className="mt-3">
          <BotaoExportar relatorio="patrimonio" rotulo="Gerar a planilha atual" />
        </div>
      </Cartao>

      <Cartao titulo="Mande a planilha" descricao="Primeiro a prévia: nada é gravado sem você confirmar.">
        <div className="flex flex-wrap items-center gap-3">
          <SeletorDeArquivo id="patrimonio-arquivo" accept=".xlsx,.csv,text/csv" disabled={!podeCadastrar}
                            rotulo="Escolher a planilha" arquivo={arquivo}
                            onEscolher={(f) => { setArquivo(f); setPrevia(null); }} />
          <label className="flex items-center gap-2 text-[14px]">
            <input type="checkbox" id="patrimonio-sugestoes" checked={sugestoes}
                   onChange={(e) => { setSugestoes(e.target.checked); setPrevia(null); }} />
            Incluir as sugestões (como “A confirmar”)
          </label>
          <button type="button" className="btn btn-secundario" id="patrimonio-previa"
                  disabled={!arquivo || ocupado || !podeCadastrar} aria-busy={ocupado}
                  onClick={() => void enviar(true)}>
            Ver prévia
          </button>
        </div>
        {!podeCadastrar && (
          <p className="mt-2 text-[13px] text-suave">Importar pede a permissão de cadastrar patrimônio.</p>
        )}
      </Cartao>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {previa && (
        <Cartao titulo={previa.aplicado ? "Importado" : "Prévia"}
                descricao={`${plural(previa.linhas, "linha", "linhas")} na planilha — ${previa.message}`}>
          {!previa.aplicado && total > 0 && (
            <div className="mb-4">
              <button type="button" className="btn btn-primario" id="patrimonio-aplicar"
                      disabled={ocupado} aria-busy={ocupado} onClick={() => void enviar(false)}>
                Importar {plural(total, "bem", "bens")}
              </button>
            </div>
          )}

          {previa.recusados.length > 0 && (
            <div className="mb-5">
              <Aviso tipo="erro">
                {plural(previa.recusados.length, "linha", "linhas")} {previa.aplicado ? "não entraram" : "não vão entrar"}.
                Corrija na planilha e mande de novo — as outras não dependem delas.
              </Aviso>
              <div className="mt-3 grid-rolante">
                <table className="tabela" id="patrimonio-recusados">
                  <thead><tr><th>Aba · linha</th><th>Equipamento</th><th>Por quê</th></tr></thead>
                  <tbody>
                    {previa.recusados.map((r) => (
                      <tr key={`${r.aba}-${r.linha}`}>
                        <td className="mono">{onde(r)}</td>
                        <td>{r.descricao}</td>
                        <td className="text-[13px]">{r.motivo}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {previa.novos.length > 0 && (
            <div className="mb-5">
              <h3 className="mb-2 font-semibold">{previa.aplicado ? "Cadastrados" : "Novos"} ({previa.novos.length})</h3>
              <div className="grid-rolante">
                <table className="tabela" id="patrimonio-novos">
                  <thead><tr><th>Aba · linha</th>{previa.aplicado && <th>Plaqueta</th>}<th>Equipamento</th><th>Dados</th></tr></thead>
                  <tbody>
                    {previa.novos.map((n) => (
                      <tr key={`${n.aba}-${n.linha}`}>
                        <td className="mono">{onde(n)}</td>
                        {previa.aplicado && <td className="mono">{n.codigo}</td>}
                        <td>{n.descricao}</td>
                        <td className="text-[13px]">{campos(n.campos)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {previa.mudam.length > 0 && (
            <div>
              <h3 className="mb-2 font-semibold">{previa.aplicado ? "Atualizados" : "Mudam"} ({previa.mudam.length})</h3>
              <div className="grid-rolante">
                <table className="tabela" id="patrimonio-mudam">
                  <thead><tr><th>Plaqueta</th><th>Equipamento</th><th>Antes</th><th>Depois</th></tr></thead>
                  <tbody>
                    {previa.mudam.map((m) => (
                      <tr key={m.id}>
                        <td className="mono">{m.codigo}</td>
                        <td>{m.descricao}</td>
                        <td className="text-[13px]">{campos(m.de)}</td>
                        <td className="text-[13px] font-semibold">{campos(m.para)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!total && !previa.recusados.length && <Vazio>Nada muda com esta planilha.</Vazio>}
        </Cartao>
      )}
    </div>
  );
}
