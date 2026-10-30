"use client";

import { useState } from "react";
import { useSessao } from "@/lib/sessao";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Cartao, SeletorDeArquivo, Vazio } from "@/components/ui";
import Voltar from "@/components/voltar";
import ExplicaTela from "@/components/explica-tela";
import BotaoExportar from "@/components/exportar";
import { reclassificar, ResultadoReclassificacao } from "@/lib/produto-reclassificar";

import { plural } from "@/lib/numeros";
/**
 * Reclassificar produtos por planilha: tipo, categoria, setor e local padrão.
 *
 * 🔑 **Pedido do dono (23/10/2026)**, com o documento "Tabelas tipo, categoria, setor" da
 * casa: cada um dos ~1.500 produtos com o SEU destino. A alteração múltipla põe o mesmo
 * valor em vários; aqui cada linha da planilha diz o seu.
 *
 * ⚠️ **Prévia antes, sempre.** O botão de aplicar só aparece depois dela, e reenvia o
 * MESMO arquivo — o servidor reclassifica de novo, então o que mudou entre a prévia e o
 * clique (alguém desativou uma categoria) volta como recusa, não como surpresa.
 */
export default function PaginaReclassificar() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const podeEditar = pode("cadastros.produtos");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<ResultadoReclassificacao | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  async function enviar(simular: boolean) {
    if (!arquivo) return;
    setOcupado(true);
    setErro("");
    try {
      const r = await reclassificar(arquivo, simular);
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

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Voltar href="/produtos">produtos</Voltar>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">
          Reclassificar por planilha
        </h1>
        <ExplicaTela>
          Tipo, categoria, setor e local padrão de muitos produtos de uma vez, cada um com o seu.
        </ExplicaTela>
      </header>

      <Cartao titulo="1. Exporte a planilha do cadastro" descricao="Escolha “planilha” na janela.">
        <p className="mb-3 max-w-[70ch] text-[13.5px] leading-snug text-suave">
          Corrija no Excel só as colunas <b>Tipo</b>, <b>Categoria</b>, <b>Setor</b> e{" "}
          <b>Local padrão</b>, pelo nome, como aparecem nas Tabelas de apoio. Célula vazia ou igual
          ao que já está não muda nada; as outras colunas são ignoradas. Salve como CSV.
        </p>
        <BotaoExportar relatorio="produtos" />
      </Cartao>

      <Cartao titulo="2. Mande de volta" descricao="Primeiro a prévia: nada é gravado sem você confirmar.">
        <div className="flex flex-wrap items-center gap-3">
          <SeletorDeArquivo
            id="planilha-reclassificar"
            accept=".csv,text/csv"
            disabled={!podeEditar}
            rotulo="Escolher a planilha"
            arquivo={arquivo}
            onEscolher={(f) => { setArquivo(f); setPrevia(null); }}
          />
          <button
            type="button"
            className="btn btn-secundario"
            disabled={!arquivo || ocupado || !podeEditar}
            aria-busy={ocupado}
            onClick={() => void enviar(true)}
          >
            Ver prévia
          </button>
        </div>
        {!podeEditar && (
          <p className="mt-2 text-[13px] text-suave">Reclassificar pede a permissão de cadastrar produtos.</p>
        )}
      </Cartao>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {previa && (
        <Cartao
          titulo={previa.aplicado ? "Aplicado" : "Prévia"}
          descricao={`${plural(previa.linhas, "linha", "linhas")} na planilha — ${previa.message}`}
        >
          {!previa.aplicado && previa.mudam.length > 0 && (
            <div className="mb-4">
              <button
                type="button"
                className="btn btn-primario"
                disabled={ocupado}
                aria-busy={ocupado}
                onClick={() => void enviar(false)}
              >
                Aplicar em {plural(previa.mudam.length, "produto", "produtos")}
              </button>
            </div>
          )}

          {previa.recusados.length > 0 && (
            <div className="mb-5">
              {/* ⚠️ As recusas ANTES da lista do que muda: são o que dá para consertar
                  na planilha, e uma lista longa de mudanças as empurraria para o fim. */}
              <Aviso tipo="erro">
                {plural(previa.recusados.length, "linha", "linhas")} não {previa.aplicado ? "foram" : "serão"} aplicadas.
                Corrija na planilha e mande de novo — as outras não dependem delas.
              </Aviso>
              <div className="mt-3 grid-rolante">
                <table className="tabela" id="reclassificar-recusados">
                  <thead>
                    <tr><th className="num">Linha</th><th>Código</th><th>Produto</th><th>Por quê</th></tr>
                  </thead>
                  <tbody>
                    {previa.recusados.slice(0, 300).map((r) => (
                      <tr key={`${r.linha}-${r.codigo}`}>
                        <td className="num">{r.linha}</td>
                        <td className="mono">{r.codigo}</td>
                        <td>{r.nome ?? "—"}</td>
                        <td className="text-[13px]">{r.motivo}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!previa.mudam.length ? (
            <Vazio>Nenhum produto muda com esta planilha.</Vazio>
          ) : (
            <div className="grid-rolante">
              <table className="tabela" id="reclassificar-mudam">
                <thead>
                  <tr><th>Código</th><th>Produto</th><th>Antes</th><th>Depois</th></tr>
                </thead>
                <tbody>
                  {previa.mudam.slice(0, 500).map((m) => (
                    <tr key={m.id}>
                      <td className="mono">{m.codigo}</td>
                      <td>{m.nome}</td>
                      <td className="text-[13px]">{campos(m.de)}</td>
                      <td className="text-[13px] font-semibold">{campos(m.para)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {previa.mudam.length > 500 && (
                <p className="mt-2 text-[12.5px] text-suave">
                  Mostrando 500 de {previa.mudam.length} — o botão aplica em todos.
                </p>
              )}
            </div>
          )}
        </Cartao>
      )}
    </div>
  );
}
