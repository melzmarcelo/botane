"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { hoje } from "@/lib/datas";
import { useAviso } from "@/components/aviso-flutuante";
import { reais } from "@/lib/cadastros";
import { Aviso, Campo, Cartao, Etiqueta, Vazio } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fontePessoas, fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";
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
const PESSOAS = fontePessoas();

type ItemManual = {
  id_produto: string;
  rotulo: string;
  quantidade: string;
  valor_unitario: string;
};

const ITEM_VAZIO: ItemManual = { id_produto: "", rotulo: "", quantidade: "", valor_unitario: "" };

/** O que o servidor responde quando perguntam quanto o cupom vai sair. */
type Previa = {
  politica: string | null;
  /** Linhas que a política "pelo custo" não conseguiu custear. */
  sem_custo: number;
  itens: {
    id_produto: number | null;
    valor_unitario_cheio: number;
    valor_unitario: number;
    mudou: boolean;
    total: number;
  }[];
  total_cheio: number;
  total: number;
  desconto: number;
};

/** A pessoa e a política que ela carrega para o cupom. */
type PessoaCupom = {
  id: number;
  nome: string;
  cupom_base?: "VENDA" | "CUSTO";
  cupom_desconto_pct?: number;
};

export default function PaginaLancarVenda() {
  const router = useRouter();
  const aviso = useAviso();

  const [aba, setAba] = useState<"manual" | "planilha">("manual");
  const [ocupado, setOcupado] = useState(false);

  const [data, setData] = useState(hoje());
  const [documento, setDocumento] = useState("");
  const [canal, setCanal] = useState("");
  // 🔑 **A pessoa do cupom** (04/09/2026, pedido do dono). Sem ela, a venda sai
  // pelo preço de venda — que é o normal. Informando-a, o servidor aplica a
  // política dela: o custo no lugar do preço, ou o preço com desconto.
  // 🔑 **A pessoa se ESCOLHE pela janela de pesquisa**, não por combobox
  // (04/09/2026, relato do dono). Uma lista de 800 nomes num `<select>` não se
  // percorre, e a política — que é o motivo de escolher a pessoa — some.
  // ⚠️ A política vem no `bruto` da escolha: sem uma segunda busca, e sem a
  // lista inteira na memória da tela.
  const [pessoa, setPessoa] = useState<{ id: number; rotulo: string } | null>(null);
  const [politica, setPolitica] = useState<PessoaCupom | null>(null);

  const mudaAlgo =
    !!politica && (politica.cupom_base === "CUSTO" || Number(politica.cupom_desconto_pct) > 0);
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

  // 🔑 **A prévia do que vai sair** (04/09/2026, pedido do dono: "gostaria que
  // o valor fosse ajustado ao digitar para ter esta percepção visual"). Antes a
  // tela só AVISAVA que o servidor ia ajustar; o número aparecia depois de
  // gravar, e quem lançava não tinha como conferir o que ia cobrar.
  //
  // ⚠️ **Quem calcula é o SERVIDOR, pelo mesmo código do lançamento.** O
  // desconto a tela até saberia aplicar, mas o CUSTO vem da cascata da ficha —
  // e a segunda implementação divergiria no dia em que a cascata mudasse.
  const [cupomPrevia, setCupomPrevia] = useState<Previa | null>(null);
  const corpoPrevia = JSON.stringify(
    prontos.map((i) => ({
      id_produto: Number(i.id_produto),
      quantidade: Number(i.quantidade.replace(",", ".")) || 0,
      valor_unitario: Number(i.valor_unitario.replace(",", ".")) || 0,
    })),
  );
  useEffect(() => {
    // Sem política não há o que prever: o total local já é o valor final, e
    // pedir ao servidor seria uma requisição por tecla digitada para nada.
    const lista = JSON.parse(corpoPrevia) as object[];
    if (!mudaAlgo || !pessoa || !lista.length) {
      setCupomPrevia(null);
      return;
    }
    let valeu = true;
    const t = setTimeout(() => {
      api
        .post<Previa>("/vendas/previa", { id_pessoa: pessoa.id, itens: lista })
        // ⚠️ **Resposta atrasada de um pedido velho é DESCARTADA.** Sem o
        // `valeu`, digitar rápido faria a resposta de dois itens atrás
        // sobrescrever a atual, e a tela mostraria um valor que não é o do que
        // está na tela.
        .then((r) => valeu && setCupomPrevia(r))
        .catch(() => valeu && setCupomPrevia(null));
    }, 350);
    return () => {
      valeu = false;
      clearTimeout(t);
    };
  }, [corpoPrevia, mudaAlgo, pessoa]);

  /** O que a linha `n` vai custar de verdade — ou nada, se não muda. */
  function ajustada(n: number) {
    if (!cupomPrevia) return null;
    // ⚠️ A prévia só traz as linhas PRONTAS, e o índice delas não é o da tela.
    const ordem = itens.filter((i) => i.id_produto && Number(i.quantidade.replace(",", ".")) > 0);
    const pos = ordem.indexOf(itens[n]);
    return pos >= 0 ? cupomPrevia.itens[pos] ?? null : null;
  }

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
            id_pessoa: pessoa ? pessoa.id : null,
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
            id_pessoa: pessoa ? pessoa.id : null,
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
          {/* 🔑 **Para quem é esta venda** (04/09/2026, pedido do dono). Sem
              pessoa, sai pelo preço de venda — o normal. Com ela, o servidor
              aplica a política do cadastro: o custo no lugar do preço, ou o
              preço com desconto. */}
          <Campo rotulo="Para quem" dica="opcional — muda o valor do cupom">
            <BuscaCadastro
              fonte={PESSOAS}
              selecionado={pessoa}
              aoEscolher={(item: ItemBusca | null) => {
                setPessoa(item ? { id: item.id, rotulo: rotuloDe(item) } : null);
                setPolitica(
                  item ? (item.bruto as unknown as PessoaCupom) : null,
                );
              }}
            />
          </Campo>
        </div>

        {/* ⚠️ **A consequência dita ANTES de lançar** (pedido do dono:
            "apresente uma mensagem", "demonstrando isto"). Um cupom que sai por
            outro valor sem explicar por quê é indistinguível de erro de
            digitação — e o servidor repete a frase na resposta, para valer
            também para quem lançou por outro caminho. */}
        {mudaAlgo && (
          <div className="mt-4">
            <Aviso tipo="info">
              Esta venda vai sair{" "}
              {politica!.cupom_base === "CUSTO" ? (
                <>
                  <b>pelo custo</b> de cada item — o preço de venda é ignorado
                </>
              ) : (
                <>pelo preço de venda</>
              )}
              {Number(politica!.cupom_desconto_pct) > 0 && (
                <>
                  , com <b>{Number(politica!.cupom_desconto_pct)}% de desconto</b>
                </>
              )}
              . Quem calcula é o servidor, e o valor gravado é o que aparece na venda.
            </Aviso>
          </div>
        )}

        {/* ⚠️ **A diferença que seria silenciosa** (04/09/2026). Linha sem custo
            conhecido sai pelo preço CHEIO dentro de um cupom "pelo custo" — e
            sem este aviso quem lança presume que a política valeu para tudo, e
            só descobre na hora de cobrar. O desconto também não se aplica ali:
            10% sobre o preço de venda não é 10% sobre o custo. */}
        {cupomPrevia && cupomPrevia.sem_custo > 0 && (
          <div className="mt-3">
            <Aviso tipo="info">
              <b>{cupomPrevia.sem_custo} item(ns) sem custo conhecido</b> — esses saem
              pelo preço de venda, porque o sistema não sabe quanto custam. Cadastre a
              ficha técnica ou o custo do produto para que a política valha para eles.
            </Aviso>
          </div>
        )}
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
                      {mudaAlgo ? "Preço cheio" : "Valor unitário"}
                    </th>
                    {/* ⚠️ **Coluna à parte, e o campo editável continua com o
                        preço CHEIO.** Pôr o valor já ajustado dentro do campo
                        faria o envio levar o descontado, e o servidor
                        descontaria de novo: 20% viraria 36%, calado. */}
                    {mudaAlgo && (
                      <th className="num" style={{ width: 130, minWidth: 130 }}>
                        Sai por
                      </th>
                    )}
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
                          aoEscolher={(item: ItemBusca | null) => {
                            // 🔑 **O preço vem junto do produto** (04/09/2026,
                            // relato do dono: escolhi o produto e o valor não
                            // veio). Ele já viaja na lista (`bruto.preco_venda`)
                            // e ninguém o usava — quem lançava relia o preço na
                            // tela do produto e digitava de novo.
                            // ⚠️ **Só preenche o que está EM BRANCO.** Sobrescrever
                            // um valor digitado apagaria a correção de quem
                            // cobrou diferente, que é o motivo de o campo ser
                            // editável.
                            const preco = Number(
                              (item?.bruto as { preco_venda?: number } | undefined)
                                ?.preco_venda ?? 0,
                            );
                            trocar(n, {
                              id_produto: item ? String(item.id) : "",
                              rotulo: item ? rotuloDe(item) : "",
                              ...(preco > 0 && !itens[n].valor_unitario.trim()
                                ? { valor_unitario: String(preco) }
                                : {}),
                            });
                          }}
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
                      {mudaAlgo && (
                        <td className="num tabular-nums">
                          {(() => {
                            const a = ajustada(n);
                            if (!a) return <span className="text-suave">—</span>;
                            return a.mudou ? (
                              <b className="text-destaque">{reais(a.valor_unitario)}</b>
                            ) : (
                              // Linha que a política não muda (item sem custo
                              // conhecido, na base CUSTO) sai pelo preço de
                              // tabela — e dizer isso evita que quem lança
                              // pense que o desconto falhou.
                              <span className="text-suave">{reais(a.valor_unitario)}</span>
                            );
                          })()}
                        </td>
                      )}
                      <td className="num tabular-nums">
                        {reais(
                          ajustada(n)
                            ? (Number(i.quantidade.replace(",", ".")) || 0) *
                                (ajustada(n)!.valor_unitario ?? 0)
                            : (Number(i.quantidade.replace(",", ".")) || 0) *
                                (Number(i.valor_unitario.replace(",", ".")) || 0),
                        )}
                      </td>
                      <td className="text-right">
                        {itens.length > 1 && (
                          <button
                            type="button"
                            className="link-acao link-acao-erro"
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
              {/* 🔑 **Cheio, desconto e cobrado — os três** (pedido do dono).
                  Só o total final não deixaria ninguém conferir o desconto, que
                  é justamente o número que o funcionário vai querer ver. */}
              <p className="text-[15px]">
                {cupomPrevia && cupomPrevia.desconto > 0 ? (
                  <>
                    <span className="text-suave">cheio </span>
                    <span className="tabular-nums line-through text-suave">
                      {reais(cupomPrevia.total_cheio)}
                    </span>
                    <span className="text-suave"> · desconto </span>
                    <span className="tabular-nums">{reais(cupomPrevia.desconto)}</span>
                    <span className="text-suave"> · total </span>
                    <b className="tabular-nums">{reais(cupomPrevia.total)}</b>
                  </>
                ) : (
                  <>
                    <span className="text-suave">total </span>
                    <b className="tabular-nums">{reais(cupomPrevia ? cupomPrevia.total : totalManual)}</b>
                  </>
                )}
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
