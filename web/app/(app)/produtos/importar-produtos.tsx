"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Etiqueta, Modal, Vazio } from "@/components/ui";

import { plural } from "@/lib/numeros";
/**
 * Importar produtos do PDV ou do Omie — só os que ainda não existem aqui, e só os marcados.
 *
 * 🔑 **O pedido do dono (22/10/2026):** *"colocar um botão Importar, ao clicar vai aparecer,
 * deseja importar produtos, opções do PDV ou do Omie. Aí realiza a busca e mostra os novos
 * produtos, com um checkbox, padrão marcado, para verificar quais o cliente quer importar.
 * Na opção PDV, atualizar os preços também, mas isto não precisa aprovação"*.
 *
 * ⚠️ **A busca do PDV JÁ GRAVA os preços** (é a parte sem aprovação); a dos novos só lista.
 * Quem cria é o segundo clique, com a lista do que ficou marcado. Os dois caminhos são os
 * mesmos importadores do cardápio e do catálogo: o produto nasce rascunho, como sempre.
 */

type Origem = "pdv" | "omie";

type Novo = {
  codigo: string;
  nome: string;
  // PDV
  nome_curto?: string | null;
  grupo?: string | null;
  ativo?: boolean;
  preco?: number | null;
  // Omie
  codigo_omie?: string | null;
  um?: string | null;
  familia?: string | null;
  ncm?: string | null;
};

type Busca = { novos: Novo[]; message: string; precos?: number };

const NOMES: Record<Origem, string> = { pdv: "PDV Legal", omie: "Omie" };

export default function ImportarProdutos({
  origens,
  aoFechar,
  aoImportar,
}: {
  /** As que esta pessoa pode usar — a permissão de cada integração. */
  origens: Origem[];
  aoFechar: () => void;
  /** Recarrega a lista de trás. */
  aoImportar: () => void;
}) {
  const aviso = useAviso();
  const [origem, setOrigem] = useState<Origem | null>(null);
  const [busca, setBusca] = useState<Busca | null>(null);
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  const [filtro, setFiltro] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  async function buscar(o: Origem) {
    setOrigem(o);
    setBusca(null);
    setErro("");
    setBuscando(true);
    try {
      const r = await api.post<Busca>(`/${o}/produtos-novos`, {});
      setBusca(r);
      // 🔑 Padrão MARCADO (pedido do dono): quem abre quer importar; desmarca a exceção.
      setMarcados(new Set(r.novos.map((n) => n.codigo)));
      // O preço já entrou: a lista de trás mostra preço, e precisa recarregar mesmo
      // que ninguém importe nada.
      if (r.precos) aoImportar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível buscar");
    } finally {
      setBuscando(false);
    }
  }

  async function importar() {
    if (!origem || !marcados.size) return;
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>(`/${origem}/produtos-novos/importar`, {
        codigos: [...marcados],
      });
      aviso.sucesso(r.message);
      aoImportar();
      aoFechar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível importar");
    } finally {
      setOcupado(false);
    }
  }

  const alvo = filtro.trim().toLowerCase();
  const visiveis = (busca?.novos ?? []).filter(
    (n) =>
      !alvo ||
      n.nome.toLowerCase().includes(alvo) ||
      (n.nome_curto ?? "").toLowerCase().includes(alvo) ||
      n.codigo.toLowerCase().includes(alvo) ||
      (n.codigo_omie ?? "").toLowerCase().includes(alvo),
  );
  const todosVisiveisMarcados = visiveis.length > 0 && visiveis.every((n) => marcados.has(n.codigo));

  function alternar(codigo: string) {
    const novo = new Set(marcados);
    if (novo.has(codigo)) novo.delete(codigo);
    else novo.add(codigo);
    setMarcados(novo);
  }

  function alternarVisiveis() {
    const novo = new Set(marcados);
    visiveis.forEach((n) => (todosVisiveisMarcados ? novo.delete(n.codigo) : novo.add(n.codigo)));
    setMarcados(novo);
  }

  return (
    <Modal
      titulo={origem ? `Importar produtos do ${NOMES[origem]}` : "Importar produtos"}
      descricao={
        origem
          ? "Só os que ainda não estão no cadastro. Desmarque o que não quer trazer."
          : "De onde você quer importar produtos?"
      }
      aoFechar={aoFechar}
      largura="900px"
      rodape={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-[13px] text-suave">
            {busca ? `${marcados.size} de ${plural(busca.novos.length, "marcado", "marcados")}` : ""}
          </span>
          <div className="flex gap-2">
            <button type="button" className="btn btn-secundario" onClick={aoFechar}>
              {busca && !busca.novos.length ? "Fechar" : "Cancelar"}
            </button>
            {busca && !!busca.novos.length && (
              <button
                id="importar-marcados"
                type="button"
                className="btn btn-primario"
                aria-busy={ocupado}
                disabled={ocupado || !marcados.size}
                onClick={() => void importar()}
              >
                {ocupado ? "Importando…" : `Importar ${marcados.size}`}
              </button>
            )}
          </div>
        </div>
      }
    >
      {erro && (
        <div className="mb-4">
          <Aviso tipo="erro">{erro}</Aviso>
        </div>
      )}

      {/* 🔑 A pergunta primeiro: PDV ou Omie. Só aparece a origem que a pessoa pode usar. */}
      {!origem && (
        <div className="grid gap-3 sm:grid-cols-2">
          {origens.map((o) => (
            <button
              key={o}
              id={`importar-de-${o}`}
              type="button"
              className="rounded border border-linha bg-superficie2 px-4 py-4 text-left hover:border-destaque"
              onClick={() => void buscar(o)}
            >
              <b className="text-[15px]">{NOMES[o]}</b>
              <span className="mt-1 block text-[13px] text-suave">
                {o === "pdv"
                  ? "Os itens do cardápio que não estão aqui. Os preços de venda são atualizados na busca."
                  : "Os produtos do catálogo que não estão aqui."}
              </span>
            </button>
          ))}
        </div>
      )}

      {buscando && <Carregando>Buscando no {origem ? NOMES[origem] : ""}…</Carregando>}

      {busca && (
        <div className="flex flex-col gap-4">
          <Aviso tipo="info">{busca.message}</Aviso>

          {!busca.novos.length ? (
            <Vazio>Nenhum produto novo: tudo o que há lá já está no cadastro.</Vazio>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <input
                  className="campo max-w-[320px]"
                  placeholder="filtrar por nome ou código"
                  value={filtro}
                  onChange={(e) => setFiltro(e.target.value)}
                />
                <button type="button" className="link-acao" onClick={alternarVisiveis}>
                  {todosVisiveisMarcados ? "desmarcar" : "marcar"}{" "}
                  {alvo ? "os filtrados" : "todos"}
                </button>
              </div>
              <div className="grid-rolante max-h-[46vh] overflow-y-auto">
                <table className="tabela" id="tabela-novos">
                  <thead>
                    <tr>
                      <th style={{ width: 36 }}>
                        <input
                          type="checkbox"
                          aria-label="marcar todos"
                          checked={todosVisiveisMarcados}
                          onChange={alternarVisiveis}
                        />
                      </th>
                      <th>Produto</th>
                      {origem === "pdv" ? (
                        <>
                          <th>Grupo</th>
                          <th className="num">Preço</th>
                          <th>No cardápio</th>
                        </>
                      ) : (
                        <>
                          <th>Unidade</th>
                          <th>Família</th>
                          <th>NCM</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {visiveis.map((n) => (
                      <tr key={n.codigo}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`importar ${n.nome}`}
                            checked={marcados.has(n.codigo)}
                            onChange={() => alternar(n.codigo)}
                          />
                        </td>
                        <td>
                          {n.nome}
                          <span className="block text-[12.5px] text-suave">
                            {origem === "pdv"
                              ? [n.codigo, n.nome_curto && n.nome_curto !== n.nome ? n.nome_curto : null]
                                  .filter(Boolean).join(" · ")
                              : n.codigo_omie || n.codigo}
                          </span>
                        </td>
                        {origem === "pdv" ? (
                          <>
                            <td>{n.grupo ?? "—"}</td>
                            <td className="num tabular-nums">{n.preco ? reais(n.preco) : "—"}</td>
                            <td>
                              {n.ativo ? (
                                <Etiqueta cor="erva">sim</Etiqueta>
                              ) : (
                                // ⚠️ Fora do cardápio nasce INATIVO (regra do importador).
                                <Etiqueta>fora — nasce inativo</Etiqueta>
                              )}
                            </td>
                          </>
                        ) : (
                          <>
                            <td>{n.um ?? "—"}</td>
                            <td>{n.familia ?? "—"}</td>
                            <td className="mono text-[13px]">{n.ncm ?? "—"}</td>
                          </>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[13px] text-suave">
                Os marcados entram como <b>rascunho</b>, como em toda importação: a revisão
                continua sendo aqui.
              </p>
            </>
          )}
        </div>
      )}
    </Modal>
  );
}
