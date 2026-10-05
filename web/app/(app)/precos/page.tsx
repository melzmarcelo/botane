"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import { fonteProdutos, type ItemBusca } from "@/lib/busca-cadastro";
import { reais } from "@/lib/cadastros";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { pct } from "@/lib/numeros";
import { evolucaoPrecoCusto, type EvolucaoPrecoCusto } from "@/lib/precos";
import GraficoDegrau, { COR_CUSTO, COR_PRECO } from "./grafico";

/**
 * Preço × custo de um produto ao longo do tempo — a primeira tela da Precificação.
 *
 * 🔑 **Pedido do dono (05/10/2026):** *"selecionar um produto e ver em forma de
 * gráfico de linhas a evolução de preço × custo"*. O estudo inteiro está em
 * `docs/precificacao-estudo.md`; esta tela só LÊ, com o que o sistema já guarda.
 *
 * 🔑 **O produto mora na URL** (`?produto=`): a tela é destino de link — da
 * margem por prato, da fila de fichas, de uma conversa — e um gráfico que não
 * se consegue apontar é um gráfico que se refaz toda vez.
 *
 * ⚠️ **A distância entre as duas linhas É a margem bruta.** Ela tem um gráfico
 * próprio logo abaixo, em percentual; os dois não dividem o mesmo desenho.
 * ⚠️ **A tela diz de onde vem o custo e o que falta nele** — o custo da ficha
 * só existe nos dias em que houve venda, e mostrá-lo como linha contínua faria
 * parecer que o sistema sabe o que não sabe.
 */
const JANELAS = [
  { meses: "3", nome: "3 meses" },
  { meses: "6", nome: "6 meses" },
  { meses: "12", nome: "12 meses" },
  { meses: "24", nome: "24 meses" },
];

export default function PaginaPrecos() {
  const [idNaUrl, setIdNaUrl] = useEstadoNaUrl<string>("produto", "", { atraso: 0 });
  const [meses, setMeses] = useEstadoNaUrl<string>("meses", "12", { atraso: 0 });
  const [escolhido, setEscolhido] = useState<{ id: number; rotulo: string } | null>(null);
  const [dados, setDados] = useState<EvolucaoPrecoCusto | null>(null);
  const [erro, setErro] = useState("");
  const [comoTabela, setComoTabela] = useState(false);
  const fonte = useMemo(() => fonteProdutos(), []);

  const idProduto = /^\d+$/.test(idNaUrl) ? Number(idNaUrl) : null;

  useEffect(() => {
    if (idProduto === null) {
      setDados(null);
      setEscolhido(null);
      return;
    }
    let vivo = true;
    setErro("");
    evolucaoPrecoCusto(idProduto, Number(meses) || 12)
      .then((d) => {
        if (!vivo) return;
        setDados(d);
        // O campo mostra o RÓTULO: quem chega pelo link só trouxe o id.
        setEscolhido({ id: d.produto.id, rotulo: rotuloDe({ id: d.produto.id, codigo: d.produto.codigo, nome: d.produto.nome }) });
      })
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar"));
    return () => {
      vivo = false;
    };
  }, [idProduto, meses]);

  const pontos = dados?.pontos ?? [];
  const datas = pontos.map((p) => p.data);
  const primeiro = pontos[0];
  const ultimo = pontos[pontos.length - 1];
  const primeiroCusto = pontos.find((p) => p.custo !== null);
  const primeiraMargem = pontos.find((p) => p.margem_pct !== null);
  const variacao = (de: number | null | undefined, para: number | null | undefined) =>
    de && para !== null && para !== undefined ? pct((para / de - 1) * 100) : "—";
  const maiorValor = Math.max(0, ...pontos.flatMap((p) => [p.preco ?? 0, p.custo ?? 0]));
  const casasDoEixo = maiorValor < 10 ? 1 : 0;
  const marcas = (dados?.mudancas_de_preco ?? [])
    .map((d) => datas.indexOf(d))
    .filter((i) => i >= 0);

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Preços"
        titulo="Preço × custo"
        explica={
          <>
            Como o preço de venda e o custo de um produto andaram no tempo. A distância entre as
            duas linhas é a margem — vê-la fechar é o sinal de que o custo subiu e o preço ficou
            parado.
          </>
        }
      />

      <Cartao>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="min-w-0 flex-1">
            <span className="rotulo-campo">Produto</span>
            <BuscaCadastro
              className="mt-1.5"
              fonte={fonte}
              selecionado={escolhido}
              autoFocus={idProduto === null}
              aoEscolher={(item: ItemBusca | null) => {
                setEscolhido(item ? { id: item.id, rotulo: rotuloDe(item) } : null);
                setIdNaUrl(item ? String(item.id) : "");
              }}
            />
          </label>
          <label className="sm:w-[200px]">
            <span className="rotulo-campo">Período</span>
            <select className="campo mt-1.5" value={meses} onChange={(e) => setMeses(e.target.value)}>
              {JANELAS.map((j) => (
                <option key={j.meses} value={j.meses}>
                  últimos {j.nome}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Cartao>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {idProduto === null ? (
        <Cartao>
          <Vazio>Escolha um produto para ver como o preço e o custo dele andaram.</Vazio>
        </Cartao>
      ) : !dados ? (
        !erro && <Carregando />
      ) : (
        <>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Ladrilho
              rotulo="Preço de venda"
              valor={`${reais(primeiro?.preco)} → ${reais(ultimo?.preco)}`}
              sub={`${variacao(primeiro?.preco, ultimo?.preco)} · ${dados.mudancas_de_preco.length} mudança(s)`}
            />
            <Ladrilho
              rotulo="Custo"
              valor={`${reais(primeiroCusto?.custo)} → ${reais(ultimo?.custo)}`}
              sub={primeiroCusto ? variacao(primeiroCusto.custo, ultimo?.custo) : "sem custo conhecido"}
            />
            <Ladrilho
              rotulo="Margem bruta"
              valor={`${pct(primeiraMargem?.margem_pct)} → ${pct(ultimo?.margem_pct)}`}
              sub={
                primeiraMargem && ultimo?.margem_pct !== null && ultimo?.margem_pct !== undefined
                  ? `${(ultimo.margem_pct - (primeiraMargem.margem_pct ?? 0)).toLocaleString("pt-BR", {
                      maximumFractionDigits: 1,
                      signDisplay: "always",
                    })} ponto(s)`
                  : "precisa de preço e de custo"
              }
            />
            <Ladrilho
              rotulo="Preço médio cobrado"
              valor={reais(dados.praticado.preco_medio)}
              sub={
                dados.praticado.quantidade > 0
                  ? "nas vendas do período, com desconto"
                  : "sem venda no período"
              }
            />
          </div>

          <Cartao
            titulo="Preço de venda e custo, em reais"
            acao={
              <button
                className="btn btn-secundario btn-pequeno"
                aria-pressed={comoTabela}
                onClick={() => setComoTabela((v) => !v)}
              >
                {comoTabela ? "ver o gráfico" : "ver como tabela"}
              </button>
            }
          >
            {comoTabela ? (
              <div className="grid-rolante">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>A partir de</th>
                      <th className="num">Preço</th>
                      <th className="num">Custo</th>
                      <th className="num">Margem</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pontos.map((p) => (
                      <tr key={p.data}>
                        <td>{new Date(p.data + "T12:00:00").toLocaleDateString("pt-BR")}</td>
                        <td className="num tabular-nums">{reais(p.preco)}</td>
                        <td className="num tabular-nums">{reais(p.custo)}</td>
                        <td className="num tabular-nums">{pct(p.margem_pct)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <>
                {/* A legenda existe sempre que há duas séries — a identidade nunca
                    depende só da cor: a linha do custo é tracejada. */}
                <p className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-suave">
                  <span className="inline-flex items-center gap-1.5">
                    <svg width="26" height="10" aria-hidden="true">
                      <line x1="0" y1="5" x2="26" y2="5" stroke={COR_PRECO} strokeWidth="2.5" />
                    </svg>
                    Preço de venda
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <svg width="26" height="10" aria-hidden="true">
                      <line x1="0" y1="5" x2="26" y2="5" stroke={COR_CUSTO} strokeWidth="2.5"
                            strokeDasharray="6 4" />
                    </svg>
                    Custo
                  </span>
                  <span>◆ mudança de preço</span>
                </p>
                <GraficoDegrau
                  datas={datas}
                  altura={300}
                  partirDoZero
                  rotulo={`Preço de venda e custo de ${dados.produto.nome}, de ${dados.inicio} a ${dados.fim}`}
                  // ⚠️ As casas do eixo são do GRÁFICO, não de cada rótulo: decidir
                  // por valor dava "R$ 16" e "R$ 8,1" na mesma régua.
                  noEixo={(v) => `R$ ${v.toFixed(casasDoEixo).replace(".", ",")}`}
                  noValor={(v) => reais(v)}
                  naDica={(i) => [
                    { rotulo: "Preço", valor: reais(pontos[i].preco) },
                    { rotulo: "Custo", valor: reais(pontos[i].custo) },
                    { rotulo: "Margem", valor: pct(pontos[i].margem_pct) },
                  ]}
                  series={[
                    { nome: "Preço", cor: COR_PRECO, valores: pontos.map((p) => p.preco), marcas },
                    { nome: "Custo", cor: COR_CUSTO, tracejada: true, valores: pontos.map((p) => p.custo) },
                  ]}
                />
                {primeiro?.preco == null && ultimo?.preco == null && (
                  <p className="mt-2 text-[13.5px] text-suave">
                    Este produto não tem preço de venda cadastrado.{" "}
                    <Link href={`/produtos/${dados.produto.id}`} className="link-acao">
                      abrir o produto
                    </Link>
                  </p>
                )}
              </>
            )}
          </Cartao>

          {!comoTabela && pontos.some((p) => p.margem_pct !== null) && (
            <Cartao titulo="Margem bruta, em % do preço">
              <GraficoDegrau
                datas={datas}
                altura={170}
                partirDoZero={false}
                rotulo={`Margem bruta de ${dados.produto.nome}, em percentual do preço`}
                noEixo={(v) => `${v.toFixed(0)}%`}
                noValor={(v) => pct(v)}
                naDica={(i) => [{ rotulo: "Margem", valor: pct(pontos[i].margem_pct) }]}
                series={[{ nome: "Margem", cor: COR_PRECO, valores: pontos.map((p) => p.margem_pct) }]}
              />
            </Cartao>
          )}

          <Aviso tipo="info">
            {dados.fonte_custo === "vendas" ? (
              <>
                <b>De onde vem o custo:</b> o custo da ficha técnica congelado em cada venda — o que
                o produto custava no dia em que foi vendido. Dia sem venda não tem ponto novo: a
                linha segue o último custo conhecido.
              </>
            ) : dados.fonte_custo === "razao" ? (
              <>
                <b>De onde vem o custo:</b> o custo médio do estoque depois de cada movimento,
                guardado no razão.
              </>
            ) : (
              <>
                <b>Este produto ainda não tem custo conhecido.</b> Sem ficha técnica nem compra
                lançada, não há linha de custo nem margem — só o preço.{" "}
                <Link href={`/produtos/${dados.produto.id}`} className="underline">
                  abrir o produto
                </Link>
              </>
            )}
          </Aviso>
        </>
      )}
    </div>
  );
}

function Ladrilho({ rotulo, valor, sub }: { rotulo: string; valor: string; sub: string }) {
  return (
    <div className="cartao p-4">
      <p className="rotulo">{rotulo}</p>
      <p className="mono mt-1 whitespace-nowrap text-[18px] font-bold leading-tight tracking-tight">
        {valor}
      </p>
      <p className="mt-1 text-[12.5px] leading-snug text-suave">{sub}</p>
    </div>
  );
}
