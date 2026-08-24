"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";

type Venda = {
  id: number;
  data: string;
  origem: string;
  canal: string | null;
  documento: string | null;
  valor_total: number;
  cancelada: boolean;
  itens: number;
  sem_custo: number;
};

type Pendencia = {
  codigo_pdv: string | null;
  descricao_pdv: string | null;
  ocorrencias: number;
  quantidade: number;
  receita: number;
};

type Linha = { codigo: string; descricao: string; quantidade: number; valor_unitario: number };

/**
 * Converte a planilha colada (ou o CSV do PDV) em linhas.
 * Aceita ponto e vírgula, vírgula ou tabulação; e número no formato brasileiro.
 */
function lerPlanilha(texto: string): { linhas: Linha[]; erros: string[] } {
  const linhas: Linha[] = [];
  const erros: string[] = [];
  texto
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean)
    .forEach((bruta, i) => {
      const partes = bruta.split(/[;\t]|,(?=\s*[^\d])/).map((p) => p.trim());
      if (partes.length < 3) {
        erros.push(`linha ${i + 1}: esperava código; descrição; quantidade; valor`);
        return;
      }
      const [codigo, descricao, q, v] = [
        partes[0],
        partes[1] ?? "",
        partes[2] ?? "",
        partes[3] ?? "0",
      ];
      const numero = (s: string) => Number(s.replace(/\./g, "").replace(",", ".")) || 0;
      const quantidade = numero(q);
      if (!quantidade) {
        erros.push(`linha ${i + 1}: quantidade inválida (${q})`);
        return;
      }
      linhas.push({ codigo, descricao, quantidade, valor_unitario: numero(v) });
    });
  return { linhas, erros };
}

const PRODUTOS = fonteProdutos();

export default function PaginaVendas() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeImportar = pode("cmv.painel") || pode("cmv.fechamento");

  const [lista, setLista] = useState<Venda[] | null>(null);
  const [pendencias, setPendencias] = useState<Pendencia[]>([]);
  const [erro, setErro] = useState("");
  const [confirmando, setConfirmando] = useState<Venda | null>(null);
  const [ocupado, setOcupado] = useState(false);

  const [data, setData] = useState(new Date().toISOString().slice(0, 10));
  const [documento, setDocumento] = useState("");
  const [texto, setTexto] = useState("");
  const [manual, setManual] = useState({ id_produto: "", quantidade: "", valor_unitario: "", rotulo: "" });

  const carregar = useCallback(async () => {
    try {
      const [v, p] = await Promise.all([
        api.get<Venda[]>("/vendas?limite=100"),
        api.get<Pendencia[]>("/vendas/sem-vinculo"),
      ]);
      setLista(v);
      setPendencias(p);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const previa = lerPlanilha(texto);

  async function importar(e: FormEvent) {
    e.preventDefault();
    if (!previa.linhas.length) {
      aviso.erro("Nada para importar.");
      return;
    }
    setOcupado(true);
    setErro("");
    try {
      const r = await api.post<{
        importadas: number;
        repetidas: number;
        itens: number;
        itens_sem_vinculo: number;
      }>("/vendas/importar", {
        vendas: [
          {
            data,
            documento: documento || null,
            origem: "PLANILHA",
            itens: previa.linhas.map((l) => ({
              codigo: l.codigo || null,
              descricao: l.descricao || null,
              quantidade: l.quantidade,
              valor_unitario: l.valor_unitario,
            })),
          },
        ],
      });
      aviso.sucesso(
        `${r.importadas} venda(s), ${r.itens} item(ns).` +
          (r.itens_sem_vinculo
            ? ` ${r.itens_sem_vinculo} item(ns) não encontraram produto — veja a fila abaixo.`
            : "") +
          (r.repetidas ? ` ${r.repetidas} já existia(m).` : ""),
      );
      setTexto("");
      setDocumento("");
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível importar");
    } finally {
      setOcupado(false);
    }
  }

  async function lancarManual(e: FormEvent) {
    e.preventDefault();
    setOcupado(true);
    setErro("");
    try {
      await api.post("/vendas/importar", {
        vendas: [
          {
            data,
            origem: "MANUAL",
            itens: [
              {
                id_produto: Number(manual.id_produto),
                quantidade: Number(manual.quantidade.replace(",", ".")),
                valor_unitario: Number(manual.valor_unitario.replace(",", ".")),
              },
            ],
          },
        ],
      });
      aviso.sucesso("Venda lançada.");
      setManual({ id_produto: "", quantidade: "", valor_unitario: "", rotulo: "" });
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível lançar");
    } finally {
      setOcupado(false);
    }
  }

  async function cancelar(v: Venda) {
    try {
      await api.delete(`/vendas/${v.id}`);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível cancelar");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">CMV</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Vendas</h1>
        <p className="mt-1 max-w-[66ch] text-suave">
          As vendas alimentam o CMV teórico: quantidade vendida × custo da ficha na data. O
          custo é congelado na importação — corrigir uma receita amanhã não reescreve o mês
          passado. Quando a API do PDV Legal abrir, a fonte muda e o resto fica igual.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {!!pendencias.length && (
        <Cartao
          titulo="Itens vendidos sem produto no cadastro"
          descricao="Enquanto estiverem aqui, esta receita não entra no CMV teórico."
        >
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Código no PDV</th>
                  <th>Descrição</th>
                  <th className="num">Vezes</th>
                  <th className="num">Qtd</th>
                  <th className="num">Receita</th>
                </tr>
              </thead>
              <tbody>
                {pendencias.map((p, i) => (
                  <tr key={i}>
                    <td className="mono">{p.codigo_pdv ?? "—"}</td>
                    <td>{p.descricao_pdv ?? "—"}</td>
                    <td className="num">{p.ocorrencias}</td>
                    <td className="num">{Number(p.quantidade)}</td>
                    <td className="num">{reais(Number(p.receita))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-[13px] text-suave">
            Cadastre o produto com o mesmo <b>código</b> (ou nome exato) e importe de novo —
            o vínculo passa a valer para as próximas.
          </p>
        </Cartao>
      )}

      {podeImportar && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <Cartao
            titulo="Importar planilha"
            descricao="Cole as linhas do relatório do PDV: código; descrição; quantidade; valor unitário."
          >
            <form onSubmit={importar} className="flex flex-col gap-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <Campo rotulo="Data das vendas">
                  <input
                    className="campo"
                    type="date"
                    required
                    value={data}
                    onChange={(e) => setData(e.target.value)}
                  />
                </Campo>
                <Campo rotulo="Documento" dica="reimportar o mesmo não duplica">
                  <input
                    className="campo"
                    placeholder="fechamento-2026-08-19"
                    value={documento}
                    onChange={(e) => setDocumento(e.target.value)}
                  />
                </Campo>
              </div>
              <Campo rotulo="Linhas">
                <textarea
                  className="campo mono min-h-[150px] text-[13px]"
                  placeholder={"P0012; Café latte; 14; 12,00\nP0033; Pão de queijo; 40; 6,50"}
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                />
              </Campo>

              {!!previa.linhas.length && (
                <p className="text-[13.5px] text-suave">
                  {previa.linhas.length} linha(s) reconhecida(s) ·{" "}
                  {reais(
                    previa.linhas.reduce((s, l) => s + l.quantidade * l.valor_unitario, 0),
                  )}{" "}
                  no total
                </p>
              )}
              {!!previa.erros.length && (
                <Aviso tipo="erro">{previa.erros.slice(0, 3).join(" · ")}</Aviso>
              )}

              <div>
                <button
                  className="btn btn-primario"
                  type="submit"
                  disabled={ocupado || !previa.linhas.length}
                >
                  {ocupado ? "Importando…" : "Importar"}
                </button>
              </div>
            </form>
          </Cartao>

          <Cartao titulo="Lançar uma venda" descricao="Para acerto pontual.">
            <form onSubmit={lancarManual} className="flex flex-col gap-4">
              <Campo rotulo="Produto">
                <BuscaCadastro
                  fonte={PRODUTOS}
                  required
                  selecionado={
                    manual.id_produto
                      ? { id: Number(manual.id_produto), rotulo: manual.rotulo }
                      : null
                  }
                  aoEscolher={(item: ItemBusca | null) =>
                    setManual({
                      ...manual,
                      id_produto: item ? String(item.id) : "",
                      rotulo: item ? rotuloDe(item) : "",
                    })
                  }
                />
              </Campo>
              <div className="grid grid-cols-2 gap-4">
                <Campo rotulo="Quantidade">
                  <input
                    className="campo mono"
                    type="number"
                    step="0.001"
                    min="0.001"
                    required
                    value={manual.quantidade}
                    onChange={(e) => setManual({ ...manual, quantidade: e.target.value })}
                  />
                </Campo>
                <Campo rotulo="Valor unitário">
                  <input
                    className="campo mono"
                    type="number"
                    step="0.01"
                    min="0"
                    required
                    value={manual.valor_unitario}
                    onChange={(e) => setManual({ ...manual, valor_unitario: e.target.value })}
                  />
                </Campo>
              </div>
              <button className="btn btn-secundario" type="submit" disabled={ocupado}>
                Lançar
              </button>
            </form>
          </Cartao>
        </div>
      )}

      <Cartao titulo="Vendas recentes">
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>Nenhuma venda importada ainda.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Data</th>
                  <th>Origem</th>
                  <th>Documento</th>
                  <th className="num">Itens</th>
                  <th className="num">Valor</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {lista.map((v) => (
                  <tr key={v.id} className={v.cancelada ? "opacity-55" : ""}>
                    <td className="mono whitespace-nowrap">
                      {new Date(v.data + "T12:00:00").toLocaleDateString("pt-BR")}
                    </td>
                    <td>
                      {v.origem.toLowerCase()}
                      {v.canal && <span className="text-suave"> · {v.canal.toLowerCase()}</span>}
                    </td>
                    <td className="mono text-[13px]">{v.documento ?? "—"}</td>
                    <td className="num">
                      {v.itens}
                      {v.sem_custo > 0 && (
                        <span className="ml-2">
                          <Etiqueta cor="alerta">{v.sem_custo} sem custo</Etiqueta>
                        </span>
                      )}
                    </td>
                    <td className="num font-semibold">{reais(Number(v.valor_total))}</td>
                    <td className="text-right">
                      {!v.cancelada && podeImportar && (
                        <button
                          className="rotulo hover:text-erro"
                          onClick={() => setConfirmando(v)}
                        >
                          cancelar
                        </button>
                      )}
                      {v.cancelada && <Etiqueta cor="alerta">cancelada</Etiqueta>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      {confirmando && (
        <Confirmacao
          titulo="Cancelar a venda"
          rotuloConfirmar="Cancelar a venda"
          perigo
          aoCancelar={() => setConfirmando(null)}
          aoConfirmar={() => {
            const v = confirmando;
            setConfirmando(null);
            void cancelar(v);
          }}
        >
          <p>
            Cancelar a venda <b>{confirmando.documento ?? `#${confirmando.id}`}</b>?
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            Ela sai do CMV e da receita, mas NÃO é apagada — o histórico continua fiel ao que
            o PDV mandou.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
