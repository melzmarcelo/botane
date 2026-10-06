"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import CabecalhoTela from "@/components/cabecalho-tela";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Confirmacao } from "@/components/ui";
import { reais } from "@/lib/cadastros";
import { pct } from "@/lib/numeros";
import { useSessao } from "@/lib/sessao";
import {
  faturamentoRecente,
  gravarConfig,
  lerConfig,
  listarCategorias,
  listarSetores,
  simplesEfetivo,
  type Arredondamento,
  type ConfigDePrecificacao,
  type TipoDeLinha,
} from "@/lib/precificacao";

/**
 * A configuração da Precificação desta loja.
 *
 * 🔑 **Decisões do dono (05/10/2026)** — o estudo é `docs/precificacao-estudo.md`:
 * a configuração é POR LOJA e uma loja pode SEGUIR a de outra (aí, aqui, é só
 * consulta); e cada linha vale para TUDO, para uma CATEGORIA ou para um SETOR —
 * a mais específica de mesmo nome substitui a geral.
 *
 * ⚠️ **A tela não faz a conta do preço.** Ela soma os percentuais para mostrar
 * o total (soma é soma), mas quem divide o custo e arredonda é o servidor: uma
 * segunda fórmula aqui divergiria na primeira regra nova.
 * ⚠️ **Salvar substitui a configuração inteira**, como a tabela de unidades do
 * produto — a tela manda como ela ficou.
 */
type LinhaDaTela = {
  chave: number;
  nome: string;
  tipo: TipoDeLinha;
  valor: string;
  /** "TUDO", "C:<id da categoria>" ou "S:<id do setor>" — um seletor só. */
  vale: string;
};

let proximaChave = 1;

const paraTela = (k: ConfigDePrecificacao): LinhaDaTela[] =>
  k.linhas.map((l) => ({
    chave: proximaChave++,
    nome: l.nome,
    tipo: l.tipo,
    valor: String(l.valor).replace(".", ","),
    vale: l.alcance === "CATEGORIA" ? `C:${l.id_categoria}` : l.alcance === "SETOR" ? `S:${l.id_setor}` : "TUDO",
  }));

const numero = (t: string) => Number(t.replace(/\./g, "").replace(",", ".")) || 0;

export default function PaginaConfiguracaoDePrecificacao() {
  const { eu, pode, unidade } = useSessao();
  const aviso = useAviso();
  const [k, setK] = useState<ConfigDePrecificacao | null>(null);
  const [linhas, setLinhas] = useState<LinhaDaTela[]>([]);
  const [arredondamento, setArredondamento] = useState<Arredondamento>("NOVENTA");
  const [categorias, setCategorias] = useState<{ id: number; nome: string }[]>([]);
  const [setores, setSetores] = useState<{ id: number; nome: string }[]>([]);
  const [faturamento, setFaturamento] = useState<{ mes: string; receita: number }[]>([]);
  const [fixas, setFixas] = useState("");
  const [rbt, setRbt] = useState("");
  const [seguir, setSeguir] = useState("");
  const [confirmando, setConfirmando] = useState<"seguir" | "propria" | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const podeEditar = pode("precificacao.configurar");
  const outrasLojas = (eu?.unidades ?? []).filter((u) => u.id !== unidade);

  const receber = useCallback((c: ConfigDePrecificacao) => {
    setK(c);
    setLinhas(paraTela(c));
    setArredondamento(c.arredondamento);
  }, []);

  useEffect(() => {
    lerConfig()
      .then(receber)
      .catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar"));
    listarCategorias().then(setCategorias).catch(() => {});
    listarSetores().then(setSetores).catch(() => {});
    // A calculadora é de quem configura; quem só consulta não a vê.
    if (podeEditar) faturamentoRecente().then(setFaturamento).catch(() => {});
  }, [receber, podeEditar]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!k) return <Carregando />;

  const travada = k.somente_leitura || !podeEditar;
  const mudar = (chave: number, campo: Partial<LinhaDaTela>) =>
    setLinhas((ls) => ls.map((l) => (l.chave === chave ? { ...l, ...campo } : l)));
  const acrescentar = (tipo: TipoDeLinha, nome: string) =>
    setLinhas((ls) => [...ls, { chave: proximaChave++, nome, tipo, valor: "", vale: "TUDO" }]);
  const tirar = (chave: number) => setLinhas((ls) => ls.filter((l) => l.chave !== chave));
  /** Preenche (ou cria) a linha GERAL de um nome — é o que as calculadoras fazem. */
  const usar = (nome: string, valor: number) => {
    const texto = valor.toFixed(1).replace(".", ",");
    setLinhas((ls) => {
      const alvo = ls.find((l) => l.tipo === "PERCENTUAL" && l.vale === "TUDO"
        && l.nome.trim().toLowerCase() === nome.toLowerCase());
      return alvo
        ? ls.map((l) => (l === alvo ? { ...l, valor: texto } : l))
        : [...ls, { chave: proximaChave++, nome, tipo: "PERCENTUAL", valor: texto, vale: "TUDO" }];
    });
  };

  const gerais = linhas.filter((l) => l.vale === "TUDO");
  const somaGeral = gerais.filter((l) => l.tipo === "PERCENTUAL").reduce((s, l) => s + numero(l.valor), 0);
  const margemGeral = gerais.filter((l) => l.tipo === "MARGEM").reduce((s, l) => s + numero(l.valor), 0);
  const mediaFaturamento = faturamento.length
    ? faturamento.reduce((s, m) => s + m.receita, 0) / faturamento.length
    : 0;
  const operacional = mediaFaturamento > 0 && numero(fixas) > 0 ? (numero(fixas) / mediaFaturamento) * 100 : null;
  const simples = numero(rbt) > 0 ? simplesEfetivo(numero(rbt)) : null;

  async function enviar(corpo: Parameters<typeof gravarConfig>[0]) {
    setOcupado(true);
    try {
      const r = await gravarConfig(corpo);
      receber(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  const salvar = () =>
    enviar({
      id_unidade_origem: null,
      arredondamento,
      linhas: linhas.map((l) => ({
        nome: l.nome.trim(),
        tipo: l.tipo,
        valor: numero(l.valor),
        alcance: l.vale.startsWith("C:") ? "CATEGORIA" : l.vale.startsWith("S:") ? "SETOR" : "TUDO",
        id_categoria: l.vale.startsWith("C:") ? Number(l.vale.slice(2)) : null,
        id_setor: l.vale.startsWith("S:") ? Number(l.vale.slice(2)) : null,
      })),
    });

  const tabela = (tipo: TipoDeLinha, unidadeDoValor: string, novoNome: string, rotuloNovo: string) => (
    <>
      <div className="grid-rolante">
        <table className="tabela">
          <thead>
            <tr>
              <th>Linha</th>
              <th>Vale para</th>
              <th className="num">{unidadeDoValor}</th>
              {!travada && <th />}
            </tr>
          </thead>
          <tbody>
            {linhas.filter((l) => l.tipo === tipo).map((l) => (
              <tr key={l.chave}>
                <td>
                  <input className="campo" value={l.nome} disabled={travada} aria-label="Nome da linha"
                         onChange={(e) => mudar(l.chave, { nome: e.target.value })} />
                </td>
                <td>
                  <select className="campo" value={l.vale} disabled={travada} aria-label="Vale para"
                          onChange={(e) => mudar(l.chave, { vale: e.target.value })}>
                    <option value="TUDO">tudo</option>
                    <optgroup label="Só uma categoria">
                      {categorias.map((c) => <option key={c.id} value={`C:${c.id}`}>{c.nome}</option>)}
                    </optgroup>
                    <optgroup label="Só um setor">
                      {setores.map((s) => <option key={s.id} value={`S:${s.id}`}>{s.nome}</option>)}
                    </optgroup>
                  </select>
                </td>
                <td className="num">
                  <input className="campo w-[110px] text-right tabular-nums" inputMode="decimal"
                         value={l.valor} disabled={travada} aria-label={`Valor de ${l.nome}`}
                         onChange={(e) => mudar(l.chave, { valor: e.target.value })} />
                </td>
                {!travada && (
                  <td>
                    <button className="btn btn-terciario btn-pequeno" onClick={() => tirar(l.chave)}>
                      tirar
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {!linhas.some((l) => l.tipo === tipo) && (
              <tr><td colSpan={4} className="text-suave">Nenhuma linha ainda.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {!travada && (
        <button className="btn btn-secundario btn-pequeno mt-3" onClick={() => acrescentar(tipo, novoNome)}>
          {rotuloNovo}
        </button>
      )}
    </>
  );

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Precificação"
        titulo="Configuração"
        explica={
          <>
            O que sai de cada real vendido — imposto, taxa do cartão, o custo de manter a casa
            aberta — e quanto a casa quer que sobre. É com isso que a Precificação calcula o
            menor preço que cada produto pode ter.
          </>
        }
        acoes={<Link href="/precificacao" className="btn btn-secundario">Ver a precificação</Link>}
      />

      {k.somente_leitura && (
        <Aviso tipo="info">
          <b>Somente visualização.</b> Esta loja segue a configuração de <b>{k.origem}</b>; para
          alterar, troque para essa loja no seletor do topo.
          {podeEditar && (
            <>
              {" "}
              <button className="underline" onClick={() => setConfirmando("propria")}>
                voltar a ter configuração própria
              </button>
            </>
          )}
        </Aviso>
      )}
      {!k.somente_leitura && k.seguida_por.length > 0 && (
        <Aviso tipo="info">
          Esta configuração também vale para {k.seguida_por.map((s) => s.nome).join(", ")}, que a
          {k.seguida_por.length > 1 ? " seguem" : " segue"}.
        </Aviso>
      )}

      {/* ⚠️ Só com mais de uma loja: numa casa só não há quem seguir, e o campo
          seria um a mais para responder sempre igual. */}
      {podeEditar && !k.somente_leitura && outrasLojas.length > 0 && k.seguida_por.length === 0 && (
        <Cartao titulo="De quem é a configuração"
                descricao="A loja pode ter a própria ou seguir a de outra. Seguindo outra, aqui fica só para consulta.">
          <div className="flex flex-wrap items-end gap-3">
            <label className="min-w-[240px] flex-1">
              <span className="rotulo-campo">Seguir a configuração de</span>
              <select className="campo mt-1.5" value={seguir} onChange={(e) => setSeguir(e.target.value)}>
                <option value="">— esta loja tem a própria —</option>
                {outrasLojas.map((u) => (
                  <option key={u.id} value={u.id}>{u.apelido ?? u.nome}</option>
                ))}
              </select>
            </label>
            <button className="btn btn-secundario" disabled={!seguir || ocupado}
                    onClick={() => setConfirmando("seguir")}>
              Passar a seguir
            </button>
          </div>
        </Cartao>
      )}

      <Cartao titulo="O que sai de cada real vendido"
              descricao="Percentuais sobre o PREÇO de venda. Uma linha de mesmo nome para uma categoria ou um setor substitui a geral — categoria ganha de setor.">
        {tabela("PERCENTUAL", "% da venda", "Nova linha", "+ Acrescentar linha")}
        <p className="mono mt-3 text-[13px] text-suave">
          linhas que valem para tudo: {pct(somaGeral)} · com a margem da loja: {pct(somaGeral + margemGeral)}
        </p>
        {somaGeral + margemGeral >= 100 && (
          <Aviso tipo="erro">
            A soma chegou a {pct(somaGeral + margemGeral)}. Com 100% ou mais não existe preço que
            pague a conta — reveja os percentuais.
          </Aviso>
        )}
      </Cartao>

      <Cartao titulo="Quanto a casa quer que sobre"
              descricao="A margem de lucro, também sobre a venda. Uma margem para uma categoria ou um setor substitui a da loja.">
        {tabela("MARGEM", "% da venda", "Margem", "+ Acrescentar margem")}
        <label className="mt-4 block max-w-[280px]">
          <span className="rotulo-campo">Arredondar o preço sugerido</span>
          <select className="campo mt-1.5" value={arredondamento} disabled={travada}
                  onChange={(e) => setArredondamento(e.target.value as Arredondamento)}>
            <option value="NOVENTA">para cima, em ,90</option>
            <option value="MEIO">para cima, em ,00 ou ,50</option>
            <option value="NENHUM">sem arredondar</option>
          </select>
        </label>
      </Cartao>

      <Cartao titulo="Custos por unidade vendida"
              descricao="O que acompanha o produto e não está na ficha técnica: embalagem de viagem, sachê, canudo. Se já está na ficha, não informe aqui — entraria duas vezes.">
        {tabela("VALOR", "R$ por unidade", "Embalagem", "+ Acrescentar custo")}
      </Cartao>

      {!travada && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Cartao titulo="Calculadora do custo operacional"
                  descricao="O que a casa gasta para estar aberta, como percentual do faturamento.">
            <div className="flex flex-wrap items-end gap-3">
              <label>
                <span className="rotulo-campo">Despesa fixa mensal (R$)</span>
                <input className="campo mt-1.5 w-[170px]" inputMode="decimal" value={fixas}
                       onChange={(e) => setFixas(e.target.value)} />
              </label>
              <div>
                <span className="rotulo-campo">Faturamento médio</span>
                <p className="mono mt-2.5 text-[15px]">{mediaFaturamento ? reais(mediaFaturamento) : "—"}</p>
              </div>
              <div>
                <span className="rotulo-campo">Resultado</span>
                <p className="mono mt-2 text-[19px] font-semibold">{operacional === null ? "—" : pct(operacional)}</p>
              </div>
              <button className="btn btn-secundario btn-pequeno" disabled={operacional === null}
                      onClick={() => operacional !== null && usar("Custo operacional", operacional)}>
                usar este percentual
              </button>
            </div>
            <p className="mt-3 text-[13px] text-suave">
              {faturamento.length
                ? `Vendas dos últimos meses fechados: ${faturamento.map((m) => `${m.mes.slice(5)}/${m.mes.slice(2, 4)} ${reais(m.receita)}`).join(" · ")}. É uma média — mês fraco faz o percentual subir.`
                : "Ainda não há mês fechado com vendas para calcular a média."}
            </p>
          </Cartao>

          <Cartao titulo="Calculadora do Simples Nacional"
                  descricao="A alíquota que vale é a efetiva, não a da tabela (Anexo I, comércio).">
            <div className="flex flex-wrap items-end gap-3">
              <label>
                <span className="rotulo-campo">Faturamento dos últimos 12 meses (R$)</span>
                <input className="campo mt-1.5 w-[200px]" inputMode="decimal" value={rbt}
                       onChange={(e) => setRbt(e.target.value)} />
              </label>
              <div>
                <span className="rotulo-campo">Alíquota efetiva</span>
                <p className="mono mt-2 text-[19px] font-semibold">
                  {numero(rbt) > 0 ? (simples === null ? "fora do Simples" : pct(simples)) : "—"}
                </p>
              </div>
              <button className="btn btn-secundario btn-pequeno" disabled={simples === null}
                      onClick={() => simples !== null && usar("Impostos", simples)}>
                usar em Impostos
              </button>
            </div>
            <Aviso tipo="info">
              <b>Estimativa para precificar, não apuração fiscal.</b> Confirme o percentual com a
              contabilidade — o sistema não emite nota de venda nem apura imposto.
            </Aviso>
          </Cartao>
        </div>
      )}

      {!travada && (
        <div className="flex justify-end">
          <button className="btn btn-primario" aria-busy={ocupado} disabled={ocupado} onClick={salvar}>
            {ocupado ? "Salvando…" : "Salvar configuração"}
          </button>
        </div>
      )}

      {confirmando === "seguir" && (
        <Confirmacao titulo="Seguir a configuração de outra loja" rotuloConfirmar="Passar a seguir"
                     ocupado={ocupado} aoCancelar={() => setConfirmando(null)}
                     aoConfirmar={() => {
                       setConfirmando(null);
                       void enviar({ id_unidade_origem: Number(seguir), arredondamento, linhas: [] });
                     }}>
          <p>
            Esta loja passa a usar a configuração de{" "}
            <b>{outrasLojas.find((u) => String(u.id) === seguir)?.apelido
              ?? outrasLojas.find((u) => String(u.id) === seguir)?.nome}</b>, e esta tela fica só
            para consulta.
          </p>
          <p className="mt-3 text-[13.5px] text-suave">
            Os preços sugeridos desta loja passam a sair de lá. Dá para voltar atrás a qualquer
            momento.
          </p>
        </Confirmacao>
      )}
      {confirmando === "propria" && (
        <Confirmacao titulo="Voltar a ter configuração própria" rotuloConfirmar="Ter a própria"
                     ocupado={ocupado} aoCancelar={() => setConfirmando(null)}
                     aoConfirmar={() => {
                       setConfirmando(null);
                       // ⚠️ Sem linhas de propósito: o servidor COPIA a que era seguida
                       // como ponto de partida.
                       void enviar({ id_unidade_origem: null, arredondamento, linhas: [] });
                     }}>
          <p>
            Esta loja deixa de seguir <b>{k.origem}</b> e começa com uma cópia da configuração de
            lá, que você pode alterar em seguida.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
