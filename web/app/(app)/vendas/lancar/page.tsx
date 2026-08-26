"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import { hoje } from "@/lib/datas";
import { useAviso } from "@/components/aviso-flutuante";
import { reais } from "@/lib/cadastros";
import { Aviso, Campo, Cartao, Etiqueta, Vazio } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";
import { CANAIS, lerPlanilha } from "../tipos";

/**
 * Lançar venda — à mão ou colando a planilha.
 *
 * Tem página própria pelo mesmo motivo que a digitação de nota: os dois
 * formulários viviam no topo da lista e empurravam as vendas — que são o
 * assunto de `/vendas` — para baixo da dobra. Aqui cada um cabe inteiro.
 *
 * ⚠️ **Os dois caminhos chegam ao MESMO `/vendas/importar`.** É ele que resolve
 * o de-para, congela o custo da ficha e baixa o estoque. Um atalho que gravasse
 * direto daria duas contas de CMV conforme quem lançou.
 */

const PRODUTOS = fonteProdutos();

type ItemManual = {
  id_produto: string;
  rotulo: string;
  quantidade: string;
  valor_unitario: string;
};

const ITEM_VAZIO: ItemManual = { id_produto: "", rotulo: "", quantidade: "", valor_unitario: "" };

export default function PaginaLancarVenda() {
  const router = useRouter();
  const aviso = useAviso();

  const [aba, setAba] = useState<"manual" | "planilha">("manual");
  const [ocupado, setOcupado] = useState(false);

  const [data, setData] = useState(hoje());
  const [documento, setDocumento] = useState("");
  const [canal, setCanal] = useState("");
  const [itens, setItens] = useState<ItemManual[]>([{ ...ITEM_VAZIO }]);
  const [texto, setTexto] = useState("");

  const previa = lerPlanilha(texto);
  const totalManual = itens.reduce(
    (s, i) =>
      s +
      (Number(i.quantidade.replace(",", ".")) || 0) *
        (Number(i.valor_unitario.replace(",", ".")) || 0),
    0,
  );
  const prontos = itens.filter((i) => i.id_produto && Number(i.quantidade.replace(",", ".")) > 0);

  function trocar(indice: number, mudanca: Partial<ItemManual>) {
    setItens(itens.map((i, n) => (n === indice ? { ...i, ...mudanca } : i)));
  }

  /** Manda o lote e leva quem lançou para a venda que acabou de nascer. */
  async function enviar(corpo: object, quantos: number) {
    setOcupado(true);
    try {
      const r = await api.post<{
        importadas: number;
        repetidas: number;
        itens: number;
        itens_sem_vinculo: number;
        message: string;
      }>("/vendas/importar", corpo);
      aviso.sucesso(
        r.message +
          (r.itens_sem_vinculo
            ? ` · ${r.itens_sem_vinculo} item(ns) não acharam produto no cadastro`
            : ""),
        { texto: "ver as vendas", ao: () => router.push("/vendas") },
      );
      if (!r.importadas) {
        // ⚠️ Zero importadas com o documento repetido é o caso normal de quem
        // clicou duas vezes — dizer "importado" ali seria mentir.
        aviso.erro("Nada foi gravado: já existe uma venda com esse documento.");
        return;
      }
      router.push("/vendas");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : `Não foi possível lançar ${quantos} item(ns)`);
    } finally {
      setOcupado(false);
    }
  }

  function lancarManual(e: FormEvent) {
    e.preventDefault();
    if (!prontos.length) {
      aviso.erro("Escolha ao menos um produto com quantidade.");
      return;
    }
    void enviar(
      {
        vendas: [
          {
            data,
            documento: documento || null,
            canal: canal || null,
            origem: "MANUAL",
            itens: prontos.map((i) => ({
              id_produto: Number(i.id_produto),
              quantidade: Number(i.quantidade.replace(",", ".")),
              valor_unitario: Number(i.valor_unitario.replace(",", ".")) || 0,
            })),
          },
        ],
      },
      prontos.length,
    );
  }

  function importarPlanilha(e: FormEvent) {
    e.preventDefault();
    if (!previa.linhas.length) {
      aviso.erro("Nada para importar.");
      return;
    }
    void enviar(
      {
        vendas: [
          {
            data,
            documento: documento || null,
            canal: canal || null,
            origem: "PLANILHA",
            itens: previa.linhas.map((l) => ({
              codigo: l.codigo || null,
              descricao: l.descricao || null,
              quantidade: l.quantidade,
              valor_unitario: l.valor_unitario,
            })),
          },
        ],
      },
      previa.linhas.length,
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/vendas" className="link-voltar">
          vendas
        </Link>
        <h1 className="mt-1 text-[24px] font-bold tracking-tight sm:text-[30px]">Lançar venda</h1>
        <p className="mt-2 max-w-[70ch] text-suave">
          À mão, para o acerto pontual; ou colando o fechamento do PDV. O custo da ficha é
          congelado agora — e o que controla estoque <b>baixa da prateleira</b> no mesmo
          lançamento.
        </p>
      </header>

      <div className="flex gap-2">
        {(["manual", "planilha"] as const).map((a) => (
          <button
            key={a}
            className={`btn ${aba === a ? "btn-primario" : "btn-secundario"}`}
            onClick={() => setAba(a)}
            type="button"
          >
            {a === "manual" ? "À mão" : "Colar planilha"}
          </button>
        ))}
      </div>

      <Cartao titulo="Cabeçalho" descricao="Vale para os dois jeitos de lançar.">
        <div className="grid gap-4 sm:grid-cols-3">
          <Campo rotulo="Data da venda">
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
              placeholder="fechamento-2026-08-26"
              value={documento}
              onChange={(e) => setDocumento(e.target.value)}
            />
          </Campo>
          <Campo rotulo="Canal" dica="opcional">
            <select className="campo" value={canal} onChange={(e) => setCanal(e.target.value)}>
              <option value="">não informar</option>
              {Object.entries(CANAIS).map(([v, r]) => (
                <option key={v} value={v}>
                  {r}
                </option>
              ))}
            </select>
          </Campo>
        </div>
      </Cartao>

      {aba === "manual" ? (
        <Cartao titulo="Itens" descricao="Um por linha. A busca aceita código ou nome.">
          <form onSubmit={lancarManual} className="flex flex-col gap-4">
            <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    <th style={{ minWidth: 260 }}>Produto</th>
                    <th className="num" style={{ width: 120, minWidth: 120 }}>
                      Qtd
                    </th>
                    <th className="num" style={{ width: 140, minWidth: 140 }}>
                      Valor unitário
                    </th>
                    <th className="num" style={{ width: 120, minWidth: 120 }}>
                      Total
                    </th>
                    <th style={{ width: 40 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {itens.map((i, n) => (
                    <tr key={n}>
                      <td>
                        <BuscaCadastro
                          fonte={PRODUTOS}
                          selecionado={
                            i.id_produto ? { id: Number(i.id_produto), rotulo: i.rotulo } : null
                          }
                          aoEscolher={(item: ItemBusca | null) =>
                            trocar(n, {
                              id_produto: item ? String(item.id) : "",
                              rotulo: item ? rotuloDe(item) : "",
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          className="campo mono"
                          type="number"
                          step="0.001"
                          min="0"
                          value={i.quantidade}
                          onChange={(e) => trocar(n, { quantidade: e.target.value })}
                        />
                      </td>
                      <td>
                        <input
                          className="campo mono"
                          type="number"
                          step="0.01"
                          min="0"
                          value={i.valor_unitario}
                          onChange={(e) => trocar(n, { valor_unitario: e.target.value })}
                        />
                      </td>
                      <td className="num tabular-nums">
                        {reais(
                          (Number(i.quantidade.replace(",", ".")) || 0) *
                            (Number(i.valor_unitario.replace(",", ".")) || 0),
                        )}
                      </td>
                      <td className="text-right">
                        {itens.length > 1 && (
                          <button
                            type="button"
                            className="rotulo hover:text-erro"
                            onClick={() => setItens(itens.filter((_, x) => x !== n))}
                          >
                            tirar
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                className="btn btn-secundario"
                onClick={() => setItens([...itens, { ...ITEM_VAZIO }])}
              >
                Mais um item
              </button>
              <p className="text-[15px]">
                <span className="text-suave">total </span>
                <b className="tabular-nums">{reais(totalManual)}</b>
              </p>
            </div>

            <div>
              <button
                className="btn btn-primario"
                type="submit"
                disabled={ocupado || !prontos.length}
              >
                {ocupado ? "Lançando…" : `Lançar ${prontos.length || ""} item(ns)`}
              </button>
            </div>
          </form>
        </Cartao>
      ) : (
        <Cartao
          titulo="Colar planilha"
          descricao="As linhas do relatório do PDV: código; descrição; quantidade; valor unitário."
        >
          <form onSubmit={importarPlanilha} className="flex flex-col gap-4">
            <Campo rotulo="Linhas">
              <textarea
                className="campo mono min-h-[180px] text-[13px]"
                placeholder={"P0012; Café latte; 14; 12,00\nP0033; Pão de queijo; 40; 6,50"}
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
              />
            </Campo>

            {/* ⚠️ A prévia mostra o que o sistema ENTENDEU, não o que foi colado.
                Separador errado vira uma linha só com tudo dentro, e sem a
                prévia isso só apareceria depois de gravar. */}
            {previa.linhas.length ? (
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Código</th>
                      <th>Descrição</th>
                      <th className="num">Qtd</th>
                      <th className="num">Unitário</th>
                      <th className="num">Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previa.linhas.slice(0, 12).map((l, n) => (
                      <tr key={n}>
                        <td className="mono text-[13px]">{l.codigo || "—"}</td>
                        <td>{l.descricao || "—"}</td>
                        <td className="num tabular-nums">{l.quantidade}</td>
                        <td className="num tabular-nums">{reais(l.valor_unitario)}</td>
                        <td className="num tabular-nums">
                          {reais(l.quantidade * l.valor_unitario)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {previa.linhas.length > 12 && (
                  <p className="mt-2 text-[13px] text-suave">
                    e mais {previa.linhas.length - 12} linha(s).
                  </p>
                )}
              </div>
            ) : (
              <Vazio>Cole as linhas acima para ver a prévia.</Vazio>
            )}

            {!!previa.linhas.length && (
              <p className="text-[13.5px] text-suave">
                {previa.linhas.length} linha(s) reconhecida(s) ·{" "}
                <b>
                  {reais(previa.linhas.reduce((s, l) => s + l.quantidade * l.valor_unitario, 0))}
                </b>{" "}
                no total
              </p>
            )}
            {!!previa.erros.length && (
              <Aviso tipo="erro">
                {previa.erros.slice(0, 3).join(" · ")}
                {previa.erros.length > 3 && ` · e mais ${previa.erros.length - 3}`}
              </Aviso>
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
      )}

      <p className="text-[13px] text-suave">
        Vem tudo do PDV Legal?{" "}
        <Link href="/integracoes" className="underline">
          ligue a busca automática
        </Link>{" "}
        <Etiqueta cor="neutro">a cada hora ou uma vez por dia</Etiqueta>
      </p>
    </div>
  );
}
