"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import CabecalhoTela from "@/components/cabecalho-tela";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import { pct, qtd } from "@/lib/numeros";
import { useSessao } from "@/lib/sessao";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import {
  analisar,
  aplicarPrecos,
  simular,
  type Analise,
  type ItemDaAnalise,
  type Simulacao,
  type Situacao,
} from "@/lib/precificacao";
import LinkProduto from "@/components/link-produto";

/**
 * Precificação — o que rever primeiro, e aplicar.
 *
 * 🔑 **Pedido do dono (05/10/2026)**, estudo em `docs/precificacao-estudo.md`.
 * Uma linha por produto VENDIDO no período, ordenada pelo que mais pesa no mês:
 * a diferença para o preço mínimo × a quantidade vendida. Quem vende abaixo do
 * custo vem na frente de todos.
 *
 * 🔑 **O sugerido é o PISO, não o alvo.** Produto vendido acima dele aparece
 * com a FOLGA e sem caixa de marcar — a tela não manda baixar preço.
 * ⚠️ **A conta é do servidor**, inclusive a do simulador: cada posição do
 * controle pergunta a ele. Uma segunda fórmula aqui divergiria da de verdade.
 * ⚠️ **O impacto é "se vender o mesmo"**: subir preço pode mudar a venda, e o
 * sistema não prevê isso. A tela diz.
 * ⚠️ **Aplicar vale na hora**; se o preço vai ao caixa, depende do parâmetro de
 * envio ao PDV da loja — a resposta do servidor diz qual foi o caso.
 */
const ROTULO: Record<Situacao, [string, "neutro" | "erva" | "alerta"]> = {
  prejuizo: ["prejuízo", "alerta"],
  abaixo: ["abaixo da margem", "alerta"],
  na_margem: ["na margem", "erva"],
  sem_custo: ["sem custo", "neutro"],
  sem_preco: ["sem preço", "neutro"],
  sem_conta: ["sem conta possível", "neutro"],
};

const COR_DA_PARTE: Record<string, string> = {
  custo: "#3d6fc4",
  lucro: "#2a8a5c",
  prejuizo: "var(--color-erro)",
};
// Os percentuais sobre a venda em tons neutros e distintos: quem carrega a
// leitura é o custo (azul) e o lucro (verde) — as mesmas cores da tela de Preços.
const TONS = ["#7b6a8c", "#8d8468", "#a08a5a", "#9a9d92", "#6f7f86", "#8a7772"];

const CHAVE_MARCADOS = "botane:precificacao:marcados";

export default function PaginaPrecificacao() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const [dados, setDados] = useState<Analise | null>(null);
  const [erro, setErro] = useState("");
  const [marcados, setMarcados] = useState<Set<number>>(new Set());
  // 🔑 **O produto aberto mora na URL** (06/10/2026, pedido do dono: ir ao cadastro
  // e voltar *"continuando no mesmo contexto"*). Quem abre a simulação de um
  // prato, vai ao cadastro dele e volta encontra a mesma linha aberta — e não a
  // lista fechada, tendo de achar o prato de novo.
  const [abertoNaUrl, setAbertoNaUrl] = useEstadoNaUrl<string>("aberto", "");
  const aberto = abertoNaUrl ? Number(abertoNaUrl) : null;
  const setAberto = (id: number | null) => setAbertoNaUrl(id ? String(id) : "");
  // ⚠️ **As caixas marcadas ficam na ABA, não na URL**: podem ser centenas, e uma
  // URL com trezentos ids não é link que se mande a ninguém. Sobrevivem à ida ao
  // cadastro e somem ao aplicar ou ao fechar a aba.
  const marcadosLidos = useRef(false);
  useEffect(() => {
    try {
      const guardados = JSON.parse(sessionStorage.getItem(CHAVE_MARCADOS) || "[]");
      if (Array.isArray(guardados) && guardados.length) setMarcados(new Set(guardados));
    } catch {
      // Armazenamento bloqueado: a tela só volta sem as marcas, como antes.
    }
    marcadosLidos.current = true;
  }, []);
  useEffect(() => {
    if (!marcadosLidos.current) return;
    try {
      sessionStorage.setItem(CHAVE_MARCADOS, JSON.stringify([...marcados]));
    } catch {
      // idem
    }
  }, [marcados]);
  const [confirmando, setConfirmando] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const podeAplicar = pode("precificacao.aplicar");

  const carregar = useCallback(async () => {
    try {
      setDados(await analisar());
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const itens = dados?.itens ?? [];
  const mexe = (i: ItemDaAnalise) => i.sugerido !== null && (i.diferenca ?? 0) > 0.005;
  const escolhidos = itens.filter((i) => marcados.has(i.id_produto) && mexe(i));
  const impactoEscolhido = escolhidos.reduce((s, i) => s + (i.impacto ?? 0), 0);
  const itemAberto = itens.find((i) => i.id_produto === aberto) ?? null;

  const alternar = (id: number) =>
    setMarcados((atuais) => {
      const novos = new Set(atuais);
      if (novos.has(id)) novos.delete(id);
      else novos.add(id);
      return novos;
    });

  async function aplicar() {
    setOcupado(true);
    try {
      const r = await aplicarPrecos(escolhidos.map((i) => ({ id_produto: i.id_produto, preco: i.sugerido! })));
      aviso.sucesso(r.message);
      setMarcados(new Set());
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível aplicar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Precificação"
        titulo="Precificação"
        explica={
          <>
            Os produtos vendidos nos últimos {dados.dias} dias, comparados com o menor preço que
            paga os impostos, as taxas, o custo de manter a casa aberta e a margem configurada.
          </>
        }
        acoes={
          <Link href="/precificacao/configuracao" className="btn btn-secundario">
            Configuração
          </Link>
        }
      />

      {!dados.configurada && (
        <Aviso tipo="info">
          <b>A precificação ainda não foi configurada{dados.origem ? ` em ${dados.origem}` : ""}.</b>{" "}
          Sem os percentuais e a margem não há preço sugerido.{" "}
          <Link href="/precificacao/configuracao" className="underline">
            configurar agora
          </Link>
        </Aviso>
      )}
      {dados.somente_leitura && dados.configurada && (
        <Aviso tipo="info">
          Esta loja usa a configuração de <b>{dados.origem}</b>.
        </Aviso>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Ladrilho rotulo="Abaixo da margem" valor={`${dados.resumo.abaixo} de ${dados.resumo.com_conta}`}
                  sub="entre os que têm custo e preço" />
        <Ladrilho rotulo="Vendendo com prejuízo" valor={String(dados.resumo.prejuizo)}
                  erro={dados.resumo.prejuizo > 0} sub="preço abaixo do custo direto e das taxas" />
        <Ladrilho rotulo="Diferença no mês" valor={reais(dados.resumo.impacto)}
                  sub="corrigindo todos, com o volume atual" />
        <Ladrilho rotulo="Sem custo, sem sugestão" valor={String(dados.resumo.sem_custo)}
                  sub="falta ficha técnica ou custo de compra" />
      </div>

      <Cartao
        titulo="O que rever primeiro"
        descricao="Primeiro o que está abaixo da margem, pelo que mais pesa no mês. Quem já está acima do mínimo aparece com a folga."
        acao={
          podeAplicar ? (
            <span className="flex flex-wrap items-center gap-3">
              {escolhidos.length > 0 && (
                <span className="mono text-[13px] text-suave">no mês: +{reais(impactoEscolhido)}</span>
              )}
              <button className="btn btn-primario" disabled={escolhidos.length === 0 || ocupado}
                      aria-busy={ocupado} onClick={() => setConfirmando(true)}>
                {escolhidos.length ? `Aplicar ${escolhidos.length} preço(s)` : "Aplicar preços"}
              </button>
            </span>
          ) : undefined
        }
      >
        {itens.length === 0 ? (
          <Vazio>Nenhum produto vendido nos últimos {dados.dias} dias.</Vazio>
        ) : (
          <div className="grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  {podeAplicar && <th className="w-[40px]"><span className="sr-only">Aplicar</span></th>}
                  <th>Produto</th>
                  <th className="num">Custo direto</th>
                  <th className="num">Preço atual</th>
                  <th className="num">Lucro líquido</th>
                  <th className="num">Mínimo sugerido</th>
                  <th className="num">Diferença</th>
                  <th className="num">Vendido</th>
                  <th className="num">Impacto no mês</th>
                </tr>
              </thead>
              <tbody>
                {itens.map((i) => {
                  const [rotulo, cor] = ROTULO[i.situacao];
                  return (
                    <tr key={i.id_produto}
                        className={`cursor-pointer ${aberto === i.id_produto ? "bg-erva-claro" : ""}`}
                        onClick={() => setAberto(aberto === i.id_produto ? null : i.id_produto)}>
                      {podeAplicar && (
                        <td onClick={(e) => e.stopPropagation()}>
                          <input type="checkbox" className="h-4 w-4 cursor-pointer accent-erva"
                                 checked={marcados.has(i.id_produto)} disabled={!mexe(i)}
                                 onChange={() => alternar(i.id_produto)}
                                 aria-label={`Aplicar o preço sugerido em ${i.nome}`} />
                        </td>
                      )}
                      <td>
                        <LinkProduto id={i.id_produto} className="font-semibold">{i.nome}</LinkProduto>
                        <span className="block text-[12.5px] text-suave">
                          {[i.categoria, i.setor].filter(Boolean).join(" · ") || "sem categoria"}
                          {i.margem_alvo_pct !== null && ` · margem alvo ${pct(i.margem_alvo_pct)}`}
                        </span>
                      </td>
                      <td className="num whitespace-nowrap tabular-nums">{reais(i.custo_direto)}</td>
                      <td className="num whitespace-nowrap tabular-nums">{reais(i.preco)}</td>
                      <td className="num">
                        <span className="tabular-nums">{pct(i.lucro_pct)}</span>
                        <span className="block whitespace-nowrap"><Etiqueta cor={cor}>{rotulo}</Etiqueta></span>
                      </td>
                      <td className="num whitespace-nowrap font-semibold tabular-nums">{reais(i.sugerido)}</td>
                      <td className="num whitespace-nowrap tabular-nums">
                        {i.diferenca === null ? "—" : mexe(i) ? `+${reais(i.diferenca)}`
                          // ⚠️ Em cima do piso não há folga nem falta: "folga de -R$ 0,00"
                          // é o que saía, e é ruído.
                          : Math.abs(i.diferenca) < 0.005 ? <span className="text-suave">no mínimo</span>
                            : <span className="text-suave">folga de {reais(-i.diferenca)}</span>}
                      </td>
                      <td className="num tabular-nums">{qtd(i.vendido)}</td>
                      <td className="num whitespace-nowrap font-semibold tabular-nums">
                        {i.impacto === null ? "—" : `+${reais(i.impacto)}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-3 text-[13px] text-suave">
          Impacto = se vender a mesma quantidade com o preço sugerido. Subir preço pode mudar a
          venda; o sistema não prevê isso. Clique num produto para ver a conta dele.
        </p>
      </Cartao>

      {/* ⚠️ A lista tem até 200 linhas e o detalhe nasce DEPOIS dela: sem rolar até
          ele, clicar num produto parecia não fazer nada. */}
      {itemAberto && (
        <div ref={(no) => no?.scrollIntoView({ behavior: "smooth", block: "nearest" })} key={itemAberto.id_produto}>
          <Detalhe item={itemAberto} />
        </div>
      )}

      {confirmando && (
        <Confirmacao titulo="Aplicar os preços" rotuloConfirmar={`Aplicar ${escolhidos.length}`}
                     ocupado={ocupado} aoCancelar={() => setConfirmando(false)}
                     aoConfirmar={() => {
                       setConfirmando(false);
                       void aplicar();
                     }}>
          <p>
            <b>{escolhidos.length} produto(s)</b> passam para o preço mínimo sugerido. O preço novo
            vale no sistema a partir de agora.
          </p>
          <ul className="mt-3 max-h-[30vh] overflow-y-auto text-[14px]">
            {escolhidos.map((i) => (
              <li key={i.id_produto} className="flex justify-between gap-3 border-t border-linha py-1.5">
                <span className="truncate">{i.nome}</span>
                <span className="mono whitespace-nowrap">{reais(i.preco)} → {reais(i.sugerido)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[13.5px] text-suave">
            Se a loja envia cadastro ao PDV, os produtos integrados entram na fila de envio; se
            não envia, o caixa continua com o preço antigo — a resposta diz qual foi o caso.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}

function Ladrilho({ rotulo, valor, sub, erro }: { rotulo: string; valor: string; sub: string; erro?: boolean }) {
  return (
    <div className="cartao p-4">
      <p className="rotulo">{rotulo}</p>
      <p className={`mono mt-1 whitespace-nowrap text-[20px] font-bold leading-tight ${erro ? "text-erro" : ""}`}>
        {valor}
      </p>
      <p className="mt-1 text-[12.5px] leading-snug text-suave">{sub}</p>
    </div>
  );
}

/** A barra "de cada venda": para onde vai cada real, a um dado preço. */
function Barra({ s }: { s: Simulacao }) {
  let tom = 0;
  const fatias = s.partes.map((p) => ({
    ...p,
    cor: COR_DA_PARTE[p.tipo] ?? TONS[tom++ % TONS.length],
    // O prejuízo não ocupa largura dentro do preço: ele é o que FALTA.
    largura: p.tipo === "prejuizo" ? 0 : Math.max(p.valor, 0),
  }));
  const total = fatias.reduce((soma, f) => soma + f.largura, 0) || 1;
  return (
    <>
      <div className="flex h-[34px] gap-[2px] overflow-hidden rounded-lg" role="img"
           aria-label={`A ${reais(s.preco)}: ${fatias.map((f) => `${f.nome} ${reais(f.valor)}`).join(", ")}`}>
        {fatias.filter((f) => f.largura > 0).map((f) => (
          <span key={f.nome} style={{ flex: f.largura / total, background: f.cor }} title={`${f.nome}: ${reais(f.valor)}`} />
        ))}
      </div>
      <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-suave">
        {fatias.map((f) => (
          <span key={f.nome} className="inline-flex items-center gap-1.5">
            <i className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: f.cor }} />
            {f.nome} <b className={`mono font-medium ${f.tipo === "prejuizo" ? "text-erro" : "text-tinta"}`}>{reais(f.valor)}</b>
          </span>
        ))}
      </p>
    </>
  );
}

/** A conta de UM produto: no preço atual, no sugerido, e num preço à escolha. */
function Detalhe({ item }: { item: ItemDaAnalise }) {
  const [atual, setAtual] = useState<Simulacao | null>(null);
  const [sugerida, setSugerida] = useState<Simulacao | null>(null);
  const [livre, setLivre] = useState<Simulacao | null>(null);
  const [preco, setPreco] = useState<number>(item.preco ?? item.sugerido ?? 0);
  const [erro, setErro] = useState("");
  const espera = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setAtual(null);
    setSugerida(null);
    setLivre(null);
    setErro("");
    setPreco(item.preco ?? item.sugerido ?? 0);
    if (item.custo_direto === null) return;
    const falhou = (e: unknown) => setErro(e instanceof Error ? e.message : "Falha ao simular");
    if (item.preco) simular(item.id_produto, item.preco).then((s) => { setAtual(s); setLivre(s); }).catch(falhou);
    if (item.sugerido) simular(item.id_produto, item.sugerido).then(setSugerida).catch(falhou);
  }, [item.id_produto, item.preco, item.sugerido, item.custo_direto]);

  const limites = useMemo(() => {
    const base = Math.max(item.sugerido ?? 0, item.preco ?? 0, item.custo_direto ?? 0);
    return { min: Math.max(0.5, (item.custo_direto ?? 1) * 0.8), max: base * 1.5 || 10 };
  }, [item.sugerido, item.preco, item.custo_direto]);

  function mover(valor: number) {
    setPreco(valor);
    // ⚠️ A conta é do servidor; o respiro evita uma chamada por pixel arrastado.
    if (espera.current) clearTimeout(espera.current);
    espera.current = setTimeout(() => {
      simular(item.id_produto, valor).then(setLivre).catch(() => {});
    }, 180);
  }

  return (
    <Cartao titulo={item.nome}
            descricao={item.origem_custo ? `De onde vem o custo: ${item.origem_custo.replace(/_/g, " ")}` : undefined}
            acao={<Link href={`/precos?produto=${item.id_produto}`} className="link-acao">ver preço × custo no tempo</Link>}>
      {item.custo_direto === null ? (
        <Aviso tipo="info">
          <b>Este produto ainda não tem custo conhecido.</b> Sem custo não há preço sugerido nem
          conta a mostrar.{" "}
          <Link href={`/produtos/${item.id_produto}`} className="underline">abrir o produto</Link>
        </Aviso>
      ) : erro ? (
        <Aviso tipo="erro">{erro}</Aviso>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.2fr_.8fr]">
          <div className="flex flex-col gap-4">
            {atual && (
              <div>
                <p className="rotulo mb-2">De cada venda, no preço atual ({reais(atual.preco)})</p>
                <Barra s={atual} />
              </div>
            )}
            {sugerida && (
              <div>
                <p className="rotulo mb-2">No mínimo sugerido ({reais(sugerida.preco)})</p>
                <Barra s={sugerida} />
              </div>
            )}
            {!atual && !sugerida && <Carregando />}
          </div>
          <div>
            <label className="block">
              <span className="rotulo-campo">E se o preço fosse…</span>
              <input type="range" className="mt-3 w-full accent-erva" min={limites.min} max={limites.max}
                     step={0.1} value={preco} onChange={(e) => mover(Number(e.target.value))} />
            </label>
            <div className="mt-3 grid grid-cols-3 gap-2">
              <Numero rotulo="Preço" valor={reais(preco)} />
              <Numero rotulo="Lucro por unidade" valor={livre ? reais(livre.lucro) : "…"}
                      sub={livre ? pct(livre.lucro_pct) : ""} erro={!!livre && livre.lucro < 0} />
              <Numero rotulo={`No mês (${qtd(item.vendido)})`}
                      valor={livre ? reais(livre.lucro * item.vendido) : "…"} erro={!!livre && livre.lucro < 0} />
            </div>
          </div>
        </div>
      )}
    </Cartao>
  );
}

function Numero({ rotulo, valor, sub, erro }: { rotulo: string; valor: string; sub?: string; erro?: boolean }) {
  return (
    <div className="rounded-xl border border-linha p-3">
      <p className="text-[12px] text-suave">{rotulo}</p>
      <p className={`mono mt-1 text-[15px] font-semibold leading-tight ${erro ? "text-erro" : ""}`}>{valor}</p>
      {sub && <p className="text-[12px] text-suave">{sub}</p>}
    </div>
  );
}
