"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import CabecalhoTela from "@/components/cabecalho-tela";
import BotaoExportar from "@/components/exportar";
import { Aviso, Carregando, Cartao, Vazio } from "@/components/ui";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import { inteiro, qtd, reais } from "@/lib/numeros";
import { pedirMotivos, type AgruparMotivos, type PainelMotivos } from "@/lib/vendas-motivos";

import { eixoReais, GraficoBarras } from "../painel/graficos";
import { andar, dataBr, janela, MODOS, nomeDoRecorte, rotuloDoPonto, tituloDoPonto, type Modo } from "../painel/periodo";
import { MOTIVOS_VENDA } from "../tipos";

/**
 * Os documentos que não são venda, por MOTIVO (pedido do dono, 26/10/2026):
 * *"no painel de documentos filtros e quadros por motivos, onde podemos realizar a
 * impressão e comparativos"*.
 *
 * 🔑 **O custo é o que SAIU DO ESTOQUE**, a mesma conta das linhas de consumo interno
 * e de perdas do CMV; o custo pela ficha e o valor de referência vão ao lado.
 * 🔑 **Tudo na URL**, como o painel de vendas: o recorte vira link, e voltar de um
 * documento devolve o mesmo recorte.
 * 🔑 **Imprimir** usa o `@media print` da casa: some o menu e os botões, ficam o
 * período, os filtros e os quadros. ⚠️ Por isso o que filtra NÃO é `<button>` nos
 * cartões e nas tabelas — o print esconde todo botão, e o cartão sumiria do papel.
 * 🔑 **Imprimir (o relatório) leva o MESMO recorte** (`vendas-motivos`). ⚠️ O da tela
 * virou "Imprimir a tela" (28/10/2026): com "Baixar" renomeado para "Imprimir", eram
 * dois botões com o mesmo nome fazendo coisas diferentes.
 */

/** Uma cor por motivo, sempre a mesma — a cor segue o motivo, nunca a posição. */
const COR_MOTIVO: Record<string, string> = {
  CONSUMO_INTERNO: "#2c6a4a",
  PERDA: "#95332a",
  PREMIO: "#b07d1f",
  BRINDE: "#3b6aa0",
  OUTROS: "#7c857b",
};

function Variacao({ v }: { v: number | null }) {
  if (v === null) return <span className="text-suave">sem base para comparar</span>;
  // ⚠️ Aqui SUBIR é ruim: é custo que saiu sem receita.
  return (
    <span className={v > 0 ? "text-alerta" : "text-erva"}>
      {v > 0 ? "+" : ""}{v.toLocaleString("pt-BR")}%
    </span>
  );
}

export default function DocumentosPorMotivo() {
  const [modo, setModo] = useEstadoNaUrl<string>("modo", "mes");
  const [de, setDe] = useEstadoNaUrl<string>("de", "", { atraso: 0 });
  const [ate, setAte] = useEstadoNaUrl<string>("ate", "", { atraso: 0 });
  const [agrupar, setAgrupar] = useEstadoNaUrl<string>("agrupar", "semana");
  const [motivosUrl, setMotivosUrl] = useEstadoNaUrl<string>("motivos", "", { atraso: 0 });
  const [pessoa, setPessoa] = useEstadoNaUrl<string>("pessoa", "", { atraso: 0 });
  const [pessoaNome, setPessoaNome] = useEstadoNaUrl<string>("pessoa_nome", "", { atraso: 0 });

  const [p, setP] = useState<PainelMotivos | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [todosProdutos, setTodosProdutos] = useState(false);

  const motivos = motivosUrl ? motivosUrl.split(",").filter((m) => m in MOTIVOS_VENDA) : [];

  useEffect(() => {
    let vivo = true;
    setCarregando(true);
    setErro("");
    pedirMotivos({
      inicio: de || undefined, fim: ate || undefined,
      motivos: motivosUrl ? motivosUrl.split(",") : [],
      idPessoa: pessoa ? Number(pessoa) : null,
      agrupar: agrupar as AgruparMotivos,
    })
      .then((r) => vivo && setP(r))
      .catch((e) => vivo && setErro(e instanceof Error ? e.message : "Falha ao carregar"))
      .finally(() => vivo && setCarregando(false));
    return () => {
      vivo = false;
    };
  }, [de, ate, agrupar, motivosUrl, pessoa]);

  const m = (MODOS.some((x) => x.valor === modo) ? modo : "mes") as Modo;
  const inicio = de || p?.inicio || "";
  const fim = ate || p?.fim || "";

  function ir([novoDe, novoAte]: [string, string]) {
    setDe(novoDe);
    setAte(novoAte);
  }
  function trocarModo(novo: Modo) {
    setModo(novo);
    if (!inicio) return;
    ir(janela(novo, novo === "dia" ? fim : inicio, inicio, fim));
    if (novo === "dia" || novo === "semana") setAgrupar("dia");
  }
  function alternarMotivo(mot: string) {
    const novo = motivos.includes(mot) ? motivos.filter((x) => x !== mot) : [...motivos, mot];
    setMotivosUrl(novo.join(","));
  }
  function filtrarPessoa(id: number | null, nome: string) {
    if (!id || String(id) === pessoa) {
      setPessoa("");
      setPessoaNome("");
    } else {
      setPessoa(String(id));
      setPessoaNome(nome);
    }
  }

  const nomesMotivos = motivos.map((x) => MOTIVOS_VENDA[x]).join(", ");
  // O nome vem da URL (quem clicou na tabela) ou da própria tabela de pessoas.
  const nomePessoa = pessoaNome
    || p?.pessoas.find((x) => String(x.id_pessoa) === pessoa)?.nome || `#${pessoa}`;
  const t = p?.totais;
  const c = p?.comparacao;
  const sobre = c ? `${c.rotulo} (${dataBr(c.inicio)}${c.inicio !== c.fim ? ` a ${dataBr(c.fim)}` : ""})` : "";
  const produtos = p ? (todosProdutos ? p.produtos : p.produtos.slice(0, 15)) : [];

  return (
    <div className="space-y-4">
      <CabecalhoTela
        caminho="Vendas"
        titulo={<>Documentos por motivo {inicio && <span className="font-normal text-suave">· {nomeDoRecorte(m, inicio, fim)}</span>}</>}
        explica={
          <>
            Os documentos que não são venda — consumo interno, perda, prêmio, brinde e outros —
            ficam fora da receita e saem do estoque pelo custo. Aqui, quanto saiu de cada motivo,
            comparado com o período anterior de mesmo tamanho. Clique num motivo ou numa pessoa
            para filtrar. Documento cancelado não entra.
          </>
        }
        acoes={
          <div className="flex flex-wrap items-center gap-2">
            <Link href="/vendas?motivo=QUALQUER" className="btn btn-secundario">Documentos</Link>
            <button type="button" className="btn btn-secundario" id="motivos-imprimir"
                    onClick={() => window.print()}>
              Imprimir a tela
            </button>
            {inicio && (
              <BotaoExportar
                relatorio="vendas-motivos"
                iniciais={{
                  inicio, fim, agrupar,
                  ...(motivos.length ? { motivos_venda: motivos } : {}),
                  ...(pessoa ? { pessoas: [Number(pessoa)] } : {}),
                }}
              />
            )}
          </div>
        }
      />

      <Cartao className="nao-imprimir">
        <div className="flex flex-wrap items-center gap-3" id="motivos-filtros">
          <div className="flex overflow-hidden rounded-lg border border-linha" role="group" aria-label="recorte">
            {MODOS.map((x) => (
              <button key={x.valor} type="button" data-modo={x.valor}
                      className={`px-3 py-1.5 text-[13.5px] ${m === x.valor ? "bg-erva font-bold text-white" : "hover:bg-linha/40"}`}
                      onClick={() => trocarModo(x.valor)}>
                {x.nome}
              </button>
            ))}
          </div>
          {m === "periodo" ? (
            <div className="flex flex-wrap items-center gap-2 text-[13.5px]">
              <input type="date" className="campo py-1" style={{ width: "auto" }} id="motivos-de" aria-label="início"
                     value={inicio} onChange={(e) => e.target.value && setDe(e.target.value)} />
              <span className="text-suave">a</span>
              <input type="date" className="campo py-1" style={{ width: "auto" }} id="motivos-ate" aria-label="fim"
                     value={fim} onChange={(e) => e.target.value && setAte(e.target.value)} />
            </div>
          ) : m === "dia" ? (
            <input type="date" className="campo py-1" style={{ width: "auto" }} aria-label="dia"
                   value={inicio} onChange={(e) => e.target.value && ir([e.target.value, e.target.value])} />
          ) : null}
          <div className="flex items-center gap-1">
            <button type="button" className="link-acao seta-data" aria-label="recorte anterior"
                    disabled={!inicio || carregando} onClick={() => ir(andar(m, inicio, fim, -1))}>‹</button>
            <button type="button" className="link-acao seta-data" aria-label="próximo recorte"
                    disabled={!inicio || carregando} onClick={() => ir(andar(m, inicio, fim, 1))}>›</button>
          </div>
          {inicio !== fim && (
            <label className="flex items-center gap-2 text-[13.5px]">
              <span className="text-suave">evolução por</span>
              <select className="campo py-1" style={{ width: "auto" }} id="motivos-agrupar" value={agrupar}
                      onChange={(e) => setAgrupar(e.target.value)}>
                <option value="dia">dia</option>
                <option value="semana">semana</option>
                <option value="mes">mês</option>
              </select>
            </label>
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[13.5px]" id="motivos-escolha">
          <span className="text-suave">motivos:</span>
          {Object.entries(MOTIVOS_VENDA).map(([v, r]) => (
            <label key={v} className={`flex cursor-pointer items-center gap-1.5 rounded-full border px-2.5 py-1 ${
              motivos.includes(v) ? "border-erva bg-erva-claro" : "border-linha"}`}>
              <input type="checkbox" checked={motivos.includes(v)} data-motivo={v}
                     onChange={() => alternarMotivo(v)} />
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: COR_MOTIVO[v] }} />
              {r}
            </label>
          ))}
          {motivos.length > 0 && (
            <button type="button" className="link-acao text-[13px]" onClick={() => setMotivosUrl("")}>todos</button>
          )}
          {pessoa && (
            <span className="ml-2 flex items-center gap-1.5" id="motivos-pessoa">
              <span className="text-suave">pessoa:</span> <b>{nomePessoa}</b>
              <button type="button" className="link-acao text-[13px]" onClick={() => filtrarPessoa(null, "")}>tirar</button>
            </span>
          )}
        </div>
      </Cartao>

      {/* O que vale no papel: o recorte e os filtros, escritos. */}
      {inicio && (
        <p className="hidden text-[12pt] print:block">
          Período: {dataBr(inicio)} a {dataBr(fim)} · Motivos: {nomesMotivos || "todos"}
          {pessoa && <> · Pessoa: {nomePessoa}</>}
        </p>
      )}

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {!p && carregando && <Carregando />}

      {p && t && c && (
        <div className={`space-y-4 ${carregando ? "opacity-60" : ""}`} aria-busy={carregando}>
          <Cartao>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6" id="motivos-cartoes">
              <div className="min-w-0 rounded-lg border border-linha p-3" data-cartao-motivo="TOTAL">
                <p className="rotulo">Total</p>
                <p className="mono mt-1 text-[22px] font-bold leading-none">{reais(t.custo)}</p>
                <p className="mt-1 text-[12.5px] leading-snug text-suave">
                  {inteiro(t.documentos)} doc. · {qtd(t.itens)} itens
                </p>
                <p className="text-[12.5px]"><Variacao v={c.pct_custo} /></p>
              </div>
              {p.por_motivo.map((l) => (
                <div key={l.motivo} role="button" tabIndex={0} data-cartao-motivo={l.motivo}
                     title={motivos.length === 1 && motivos[0] === l.motivo ? "voltar a todos" : "filtrar por este motivo"}
                     onClick={() => setMotivosUrl(motivos.length === 1 && motivos[0] === l.motivo ? "" : l.motivo)}
                     onKeyDown={(e) => e.key === "Enter" && setMotivosUrl(l.motivo)}
                     className="min-w-0 cursor-pointer rounded-lg border border-linha p-3 hover:bg-linha/30"
                     style={{ borderLeft: `4px solid ${COR_MOTIVO[l.motivo]}` }}>
                  <p className="rotulo">{l.rotulo}</p>
                  <p className="mono mt-1 text-[22px] font-bold leading-none">{reais(l.custo)}</p>
                  <p className="mt-1 text-[12.5px] leading-snug text-suave">
                    {inteiro(l.documentos)} doc. · {qtd(l.itens)} itens
                  </p>
                  <p className="text-[12.5px]">
                    <Variacao v={l.pct_custo} />
                    {l.anterior.custo > 0 && (
                      <span className="text-suave"> · antes {reais(l.anterior.custo)}</span>
                    )}
                  </p>
                </div>
              ))}
            </div>
            <p className="mt-3 border-t border-dashed border-linha pt-2.5 text-[12.5px] text-suave" id="motivos-comparacao">
              Comparado com {sobre}: {reais(c.custo)} em {inteiro(c.documentos)} documento(s).
              {" "}Pela ficha, o período custaria {reais(t.custo_ficha)}; o valor de referência
              (o preço digitado, fora da receita) soma {reais(t.referencia)}.
              {p.perdas_ajuste && (
                <span id="motivos-perdas-ajuste">
                  {" "}Perdas lançadas em Ajustes no mesmo período, para comparar:{" "}
                  <b className="mono">{reais(p.perdas_ajuste.custo)}</b> (antes{" "}
                  {reais(p.perdas_ajuste.anterior)}, <Variacao v={p.perdas_ajuste.pct_custo} />) — o
                  detalhe está no painel de Estoque, aba Perdas.
                </span>
              )}
            </p>
          </Cartao>

          {t.documentos === 0 ? (
            <Cartao><Vazio>Nenhum documento com motivo neste recorte.</Vazio></Cartao>
          ) : (
            <>
              {p.serie.length > 1 && (
                <Cartao>
                  <h2 className="mb-1 text-[15px] font-bold">Evolução do custo, por motivo</h2>
                  <div className="mb-2 flex flex-wrap gap-3 text-[12.5px]" id="motivos-legenda">
                    {p.por_motivo.filter((l) => l.custo).map((l) => (
                      <span key={l.motivo} className="flex items-center gap-1.5">
                        <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: COR_MOTIVO[l.motivo] }} />
                        {l.rotulo}
                      </span>
                    ))}
                  </div>
                  <GraficoBarras
                    altura={240}
                    rotulo={`custo por motivo, por ${p.agrupar}, de ${dataBr(p.inicio)} a ${dataBr(p.fim)}`}
                    noEixo={eixoReais}
                    barras={p.serie.map((s) => ({
                      chave: s.periodo,
                      rotulo: rotuloDoPonto(p.agrupar, s.periodo),
                      titulo: tituloDoPonto(p.agrupar, s.periodo),
                      valor: s.custo,
                      partes: Object.keys(MOTIVOS_VENDA)
                        .filter((k) => s.por_motivo[k])
                        .map((k) => ({ chave: k, valor: s.por_motivo[k], cor: COR_MOTIVO[k] })),
                      dica: [
                        { rotulo: "total", valor: reais(s.custo) },
                        ...Object.keys(MOTIVOS_VENDA)
                          .filter((k) => s.por_motivo[k])
                          .map((k) => ({ rotulo: MOTIVOS_VENDA[k].toLowerCase(), valor: reais(s.por_motivo[k]) })),
                      ],
                    }))}
                  />
                </Cartao>
              )}

              <div className="grid gap-4 lg:grid-cols-2">
                <Cartao>
                  <h2 className="mb-2 text-[15px] font-bold">O que saiu do estoque</h2>
                  {produtos.length ? (
                    <table className="tabela" id="motivos-produtos">
                      <thead><tr><th>Produto</th><th className="num">Quantidade</th><th className="num">Custo</th><th className="num">Doc.</th></tr></thead>
                      <tbody>
                        {produtos.map((x) => (
                          <tr key={x.id_produto}>
                            <td className="text-[13.5px]"><span className="mono text-suave">{x.codigo}</span> {x.produto}</td>
                            <td className="num whitespace-nowrap">{qtd(x.quantidade)} {x.um_estoque ?? ""}</td>
                            <td className="num">{reais(x.custo)}</td>
                            <td className="num">{inteiro(x.documentos)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <Vazio>Nada saiu do razão — os itens não controlam estoque.</Vazio>
                  )}
                  {p.produtos.length > 15 && (
                    <button type="button" className="link-acao mt-2 text-[13px]" onClick={() => setTodosProdutos(!todosProdutos)}>
                      {todosProdutos ? "mostrar os 15 primeiros" : `mostrar todos (${p.produtos.length})`}
                    </button>
                  )}
                </Cartao>

                <div className="space-y-4">
                  <Cartao>
                    <h2 className="mb-2 text-[15px] font-bold">Por pessoa</h2>
                    <table className="tabela" id="motivos-pessoas">
                      <thead><tr><th>Pessoa</th><th className="num">Doc.</th><th className="num">Custo</th><th className="num">Referência</th></tr></thead>
                      <tbody>
                        {p.pessoas.map((x) => (
                          <tr key={x.id_pessoa ?? "sem"}
                              className={x.id_pessoa ? "cursor-pointer hover:bg-linha/30" : ""}
                              title={x.id_pessoa ? "filtrar por esta pessoa" : undefined}
                              onClick={() => x.id_pessoa && filtrarPessoa(x.id_pessoa, x.nome)}>
                            <td className={`text-[13.5px] ${String(x.id_pessoa) === pessoa ? "font-bold" : ""}`}>{x.nome}</td>
                            <td className="num">{inteiro(x.documentos)}</td>
                            <td className="num">{reais(x.custo)}</td>
                            <td className="num text-suave">{reais(x.referencia)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </Cartao>
                  {p.motivos_perda.length > 0 && (
                    <Cartao>
                      <h2 className="mb-2 text-[15px] font-bold">Perda, pelo motivo da perda</h2>
                      <table className="tabela" id="motivos-perda">
                        <thead><tr><th>Motivo da perda</th><th className="num">Doc.</th><th className="num">Custo</th></tr></thead>
                        <tbody>
                          {p.motivos_perda.map((x) => (
                            <tr key={x.id ?? "sem"}>
                              <td className="text-[13.5px]">{x.nome}</td>
                              <td className="num">{inteiro(x.documentos)}</td>
                              <td className="num">{reais(x.custo)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </Cartao>
                  )}
                </div>
              </div>

              <Cartao>
                <h2 className="mb-2 text-[15px] font-bold">Os documentos</h2>
                {p.documentos_cortados && (
                  <p className="mb-2 text-[12.5px] text-suave">
                    Mostrando os {p.documentos.length} mais recentes de {inteiro(t.documentos)} — o arquivo baixado traz todos.
                  </p>
                )}
                <div className="grid-rolante">
                  <table className="tabela" id="motivos-documentos">
                    <thead>
                      <tr>
                        <th>Data</th><th>Documento</th><th>Motivo</th><th>Pessoa</th><th>Observação</th>
                        <th className="num">Itens</th><th className="num">Custo</th><th className="num">Pela ficha</th>
                      </tr>
                    </thead>
                    <tbody>
                      {p.documentos.map((d) => (
                        <tr key={d.id}>
                          <td className="whitespace-nowrap">{dataBr(d.data)}</td>
                          <td><Link href={`/vendas/${d.id}`} className="link-registro">{d.documento ?? `#${d.id}`}</Link></td>
                          <td className="whitespace-nowrap">
                            <span className="mr-1.5 inline-block h-2.5 w-2.5 rounded-sm" style={{ background: COR_MOTIVO[d.motivo] }} />
                            {d.rotulo}
                          </td>
                          <td className="text-[13.5px]">{d.pessoa ?? "—"}</td>
                          <td className="text-[13.5px]">
                            {[d.motivo_perda, d.motivo_observacao].filter(Boolean).join(" — ") || "—"}
                          </td>
                          <td className="num">{qtd(d.itens)}</td>
                          <td className="num">{reais(d.custo)}</td>
                          <td className="num text-suave">{reais(d.custo_ficha)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Cartao>
            </>
          )}
        </div>
      )}
    </div>
  );
}
