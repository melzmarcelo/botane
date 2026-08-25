"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { hoje } from "@/lib/datas";
import { useAviso } from "@/components/aviso-flutuante";
import { Fornecedor, Local, ProdutoResumo, UnidadeMedida, reais } from "@/lib/cadastros";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteFornecedores, fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";
import { Campo, Cartao } from "@/components/ui";

/**
 * Digitar a nota inteira na mão — o caminho de quem comprou no mercado, no
 * açougue da esquina ou no hortifrúti que só dá cupom.
 *
 * A conta do rodapé é a mesma do backend, e está aqui de propósito: quem digita
 * precisa ver o custo por unidade **antes** de gravar, senão só descobre o erro
 * de vírgula depois que o custo médio já se mexeu.
 */

type Linha = {
  /** O código do produto, digitado ou preenchido ao escolher no combo. */
  codigo: string;
  id_produto: string;
  descricao: string;
  /** A unidade DA NOTA. Nasce igual à do estoque e muda quando a nota vem em
   *  outra: caixa, fardo, dúzia. É ela que manda na conversão do lançamento. */
  um: string;
  quantidade: string;
  valor_unitario: string;
  desconto: string;
  acrescimo: string;
  lote: string;
  validade: string;
};

const LINHA: Linha = {
  codigo: "",
  id_produto: "",
  descricao: "",
  um: "",
  quantidade: "",
  valor_unitario: "",
  desconto: "",
  acrescimo: "",
  lote: "",
  validade: "",
};

const numero = (texto: string) => Number((texto || "0").replace(",", ".")) || 0;

/** A nota que está sendo corrigida, quando for o caso. */
export type NotaParaEditar = {
  id: number;
  id_fornecedor: number | null;
  numero: string | null;
  serie: string | null;
  data_emissao: string | null;
  valor_frete: number;
  valor_desconto: number;
  valor_outros: number;
  id_local: number | null;
  itens: {
    id_produto: number | null;
    descricao_fornecedor: string;
    quantidade: number;
    valor_unitario: number;
    lote_nf: string | null;
    validade_nf: string | null;
    um_nota: string | null;
    valor_desconto: number;
    valor_acrescimo: number;
  }[];
};

// Só produto que controla estoque entra numa nota de entrada.
const PRODUTOS = fonteProdutos((p) => p.controla_estoque);
const FORNECEDORES = fonteFornecedores();

export default function NotaManual({
  produtos,
  locais,
  aoGravar,
  aoFechar,
  editando,
}: {
  produtos: ProdutoResumo[];
  locais: Local[];
  aoGravar: (id: number) => void;
  aoFechar: () => void;
  /** Quando vem preenchida, o formulário corrige em vez de criar. */
  editando?: NotaParaEditar | null;
}) {
  const aviso = useAviso();
  const texto = (n: number | null | undefined) => (n ? String(n) : "");

  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [ums, setUms] = useState<UnidadeMedida[]>([]);
  // Fator de conversão por produto: { idProduto: { CX: 12, FD: 6 } }. Sem isto
  // a prévia do custo dividia pelo número de CAIXAS e mostrava R$ 20,60 onde o
  // custo real por unidade de estoque é R$ 1,72 — prévia que mente é pior que
  // prévia nenhuma.
  const [fatores, setFatores] = useState<Record<string, Record<string, number>>>({});
  const [idFornecedor, setIdFornecedor] = useState(texto(editando?.id_fornecedor));
  const [numeroNota, setNumeroNota] = useState(editando?.numero ?? "");
  const [serie, setSerie] = useState(editando?.serie ?? "");
  const [dataEmissao, setDataEmissao] = useState(
    () => editando?.data_emissao?.slice(0, 10) ?? hoje(),
  );
  const [frete, setFrete] = useState(texto(editando?.valor_frete));
  const [desconto, setDesconto] = useState(texto(editando?.valor_desconto));
  const [outros, setOutros] = useState(texto(editando?.valor_outros));
  const [idLocal, setIdLocal] = useState(texto(editando?.id_local));
  const [rotuloFornecedor, setRotuloFornecedor] = useState("");
  const [linhas, setLinhas] = useState<Linha[]>(
    editando?.itens.length
      ? editando.itens.map((i) => ({
          codigo: produtos.find((p) => p.id === i.id_produto)?.codigo ?? "",
          um: i.um_nota ?? "",
          id_produto: texto(i.id_produto),
          descricao: i.descricao_fornecedor ?? "",
          quantidade: String(Number(i.quantidade)),
          valor_unitario: String(Number(i.valor_unitario)),
          desconto: Number(i.valor_desconto) ? String(Number(i.valor_desconto)) : "",
          acrescimo: Number(i.valor_acrescimo) ? String(Number(i.valor_acrescimo)) : "",
          lote: i.lote_nf ?? "",
          validade: i.validade_nf?.slice(0, 10) ?? "",
        }))
      : [{ ...LINHA }, { ...LINHA }],
  );
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    void api
      .get<Fornecedor[]>("/fornecedores")
      .then(setFornecedores)
      .catch(() => setFornecedores([]));
    void api
      .get<UnidadeMedida[]>("/unidades-medida")
      .then(setUms)
      .catch(() => setUms([]));
    setIdLocal((atual) => atual || String(locais.find((l) => l.principal)?.id ?? locais[0]?.id ?? ""));
  }, [locais]);

  /** Busca a tabela de conversão do produto uma vez e guarda. */
  const carregarFatores = (idProduto: string) => {
    if (!idProduto || fatores[idProduto]) return;
    void api
      .get<{ um: string; fator: number }[]>(`/produtos/${idProduto}/unidades`)
      .then((us) =>
        setFatores((atuais) => ({
          ...atuais,
          [idProduto]: Object.fromEntries(us.map((u) => [u.um.toUpperCase(), Number(u.fator)])),
        })),
      )
      .catch(() => setFatores((atuais) => ({ ...atuais, [idProduto]: {} })));
  };

  /**
   * O que se sabe sobre cada produto CITADO nas linhas.
   *
   * A lista de `/produtos` traz uma página; a busca no servidor pode trazer
   * qualquer outro. Sem guardar o que a busca achou, a linha ficava sem
   * unidade de estoque e sem saber se controla lote — o combo antigo escondia
   * isso porque só oferecia o que já estava carregado.
   */
  const [cache, setCache] = useState<Record<string, ProdutoResumo>>({});
  const conhecido = (id: string): ProdutoResumo | undefined =>
    cache[id] ?? produtos.find((p) => String(p.id) === id);
  const guardar = (p: ProdutoResumo) => setCache((c) => ({ ...c, [String(p.id)]: p }));

  /** Quantas unidades de estoque a linha traz de fato. */
  const quantidadeEmEstoque = (l: Linha) => {
    const fator = fatores[l.id_produto]?.[(l.um || "").toUpperCase()] ?? 1;
    return numero(l.quantidade) * fator;
  };

  const unidadeDeEstoque = (l: Linha) => conhecido(l.id_produto)?.um_estoque ?? "";

  // Lote e validade só aparecem quando algum item pede: numa nota de mercearia
  // são duas colunas vazias empurrando o resto para fora da tela.
  const temLote = linhas.some(
    (l) =>
      (l.lote || l.validade) ||
      conhecido(l.id_produto)?.controla_lote,
  );

  const preenchidas = linhas.filter((l) => (l.id_produto || l.descricao) && numero(l.quantidade) > 0);

  /** O que a linha custa: quantidade x preço, menos desconto, mais acréscimo. */
  const totalDaLinha = (l: Linha) =>
    numero(l.quantidade) * numero(l.valor_unitario) - numero(l.desconto) + numero(l.acrescimo);

  const totalProdutos = preenchidas.reduce(
    (soma, l) => soma + numero(l.quantidade) * numero(l.valor_unitario),
    0,
  );
  // Os ajustes de item entram no total da nota junto com os da nota inteira.
  const ajustesDosItens = preenchidas.reduce(
    (soma, l) => soma - numero(l.desconto) + numero(l.acrescimo),
    0,
  );
  const total =
    totalProdutos + ajustesDosItens + numero(frete) + numero(outros) - numero(desconto);

  /** O mesmo rateio por valor que o backend faz — para conferir antes de gravar. */
  const custos = useMemo(
    () =>
      preenchidas.map((l) => {
        const bruto = numero(l.quantidade) * numero(l.valor_unitario);
        const peso = totalProdutos > 0 ? bruto / totalProdutos : 0;
        const liquido =
          bruto -
          numero(l.desconto) +
          numero(l.acrescimo) +
          numero(frete) * peso +
          numero(outros) * peso -
          numero(desconto) * peso;
        // Divide pela quantidade EM ESTOQUE: é por unidade de estoque que o
        // custo médio vive, não por caixa.
        const emEstoque = quantidadeEmEstoque(l);
        return { linha: l, unitario: emEstoque > 0 ? liquido / emEstoque : 0 };
      }),
    [preenchidas, totalProdutos, frete, outros, desconto, fatores],
  );

  /**
   * Acha o produto pelo código digitado, PERGUNTANDO AO SERVIDOR.
   *
   * Procurar na lista carregada só funcionava enquanto ela cabia inteira na
   * tela: com dois mil produtos, o código de um item da página seguinte
   * simplesmente "não existia". Compara sem caixa porque o código vem de um
   * papel — quem digita escreve "p12" e o cadastro guarda "P0012".
   */
  async function porCodigo(codigo: string): Promise<ProdutoResumo | undefined> {
    const alvo = codigo.trim().toLowerCase();
    if (!alvo) return undefined;
    const { itens } = await PRODUTOS.buscar(alvo, 25);
    const exato = itens.find((i) => (i.codigo ?? "").toLowerCase() === alvo);
    const achado = exato ?? (itens.length === 1 ? itens[0] : undefined);
    return achado?.bruto as ProdutoResumo | undefined;
  }

  /** Preenche a linha inteira a partir do produto: descrição, unidade e código. */
  const comProduto = (linha: Linha, p: ProdutoResumo | undefined): Linha => {
    if (!p) return linha;
    carregarFatores(String(p.id));
    return {
          ...linha,
          id_produto: String(p.id),
          codigo: p.codigo ?? "",
          // A unidade da nota nasce igual à do estoque — é o caso comum. Quando
          // a nota vier em caixa, quem digita troca aqui e a conversão do
          // lançamento faz o resto.
          um: linha.um || p.um_estoque || "",
      descricao: linha.descricao || p.nome,
    };
  };

  function mudar(indice: number, campo: keyof Linha, valor: string) {
    setLinhas((atuais) =>
      atuais.map((l, i) => {
        if (i !== indice) return l;
        const nova = { ...l, [campo]: valor };
        // Escolher o produto no combo preenche código, unidade e descrição.
        if (campo === "id_produto") {
          return valor ? comProduto(nova, conhecido(valor)) : { ...nova, codigo: "" };
        }
        if (campo === "um" && nova.id_produto) carregarFatores(nova.id_produto);
        return nova;
      }),
    );
  }

  /** Tab no campo de código: acha o produto e preenche o resto da linha. */
  async function buscarPeloCodigo(indice: number) {
    const codigo = linhas[indice]?.codigo ?? "";
    if (!codigo.trim()) return;
    const p = await porCodigo(codigo);
    if (p) guardar(p);
    setLinhas((atuais) => atuais.map((l, i) => (i === indice ? comProduto(l, p) : l)));
  }

  async function gravar() {
    if (!preenchidas.length) {
      aviso.erro("Coloque ao menos um item com quantidade.");
      return;
    }
    setOcupado(true);
    try {
      const corpo = {
        id_fornecedor: idFornecedor ? Number(idFornecedor) : null,
        numero: numeroNota || null,
        serie: serie || null,
        data_emissao: dataEmissao || null,
        data_entrada: dataEmissao || null,
        valor_frete: numero(frete),
        valor_desconto: numero(desconto),
        valor_outros: numero(outros),
        id_local: idLocal ? Number(idLocal) : null,
        itens: preenchidas.map((l) => ({
          id_produto: l.id_produto ? Number(l.id_produto) : null,
          descricao: l.descricao || null,
          quantidade: numero(l.quantidade),
          um: l.um || null,
          valor_unitario: numero(l.valor_unitario),
          valor_desconto: numero(l.desconto),
          valor_acrescimo: numero(l.acrescimo),
          lote: l.lote || null,
          validade: l.validade || null,
        })),
      };
      const r = editando
        ? await api.put<{ id: number }>(`/notas/${editando.id}`, corpo)
        : await api.post<{ id: number }>("/notas", corpo);
      aoGravar(r.id ?? editando?.id ?? 0);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível gravar a nota");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao
      titulo={editando ? `Corrigir a nota ${editando.numero ?? ""}`.trim() : "Digitar nota de entrada"}
      descricao={
        editando
          ? "Ela ainda não virou estoque: dá para mexer em tudo antes de lançar."
          : "Para a compra que não tem XML: mercado, feira, açougue."
      }
      acao={
        <div className="flex items-center gap-2">
          <button className="btn btn-primario" onClick={gravar} disabled={ocupado}>
            {ocupado ? "Gravando…" : editando ? "Gravar correção" : "Gravar nota"}
          </button>
          <button className="rotulo hover:text-erro" onClick={aoFechar}>
            cancelar
          </button>
        </div>
      }
    >

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo rotulo="Fornecedor">
          <BuscaCadastro
            fonte={FORNECEDORES}
            selecionado={
              idFornecedor
                ? {
                    id: Number(idFornecedor),
                    rotulo:
                      rotuloFornecedor ||
                      fornecedores.find((f) => String(f.id) === idFornecedor)?.nome ||
                      "",
                  }
                : null
            }
            aoEscolher={(item: ItemBusca | null) => {
              setIdFornecedor(item ? String(item.id) : "");
              setRotuloFornecedor(item ? item.nome : "");
            }}
          />
        </Campo>
        <Campo rotulo="Número">
          <input
            className="campo"
            value={numeroNota}
            onChange={(e) => setNumeroNota(e.target.value)}
            placeholder="cupom 4821"
          />
        </Campo>
        <Campo rotulo="Série">
          <input className="campo" value={serie} onChange={(e) => setSerie(e.target.value)} />
        </Campo>
        <Campo rotulo="Data">
          <input
            className="campo"
            type="date"
            value={dataEmissao}
            onChange={(e) => setDataEmissao(e.target.value)}
          />
        </Campo>
      </div>

      <div className="mt-5 overflow-x-auto">
        <table className="tabela">
          <thead>
            {/* A largura mora na COLUNA, não no campo: `.campo` é width:100% e
                vence a utilitária do Tailwind, então `w-[110px]` no input não
                fazia nada — o campo virava 100% de uma coluna estreita. */}
            <tr>
              {/* `min-w` e não só `w`: com `table-layout: auto` o navegador
                  ignora a largura sugerida quando falta espaço, e o select de
                  unidade chegou a 42px — estreito demais para caber "KG". */}
              <th className="w-[112px] min-w-[112px]">Código</th>
              <th className="w-[24%] min-w-[180px]">Produto</th>
              <th className="min-w-[150px]">Descrição na nota</th>
              <th className="num w-[92px] min-w-[92px]">Qtd</th>
              <th className="w-[92px] min-w-[92px]">Un.</th>
              <th className="num w-[104px] min-w-[104px]">Valor un.</th>
              <th className="num w-[92px] min-w-[92px]">Desc.</th>
              <th className="num w-[92px] min-w-[92px]">Acrésc.</th>
              <th className="num w-[110px] min-w-[110px]">Total do item</th>
              <th className="num w-[100px] min-w-[100px]">Custo un.</th>
              {temLote && <th className="w-[100px] min-w-[100px]">Lote</th>}
              {temLote && <th className="w-[150px] min-w-[150px]">Validade</th>}
            </tr>
          </thead>
          <tbody>
            {linhas.map((linha, i) => {
              const previsto = custos.find((c) => c.linha === linha);
              return (
                <tr key={i}>
                  <td>
                    <input
                      className={`campo mono ${
                        linha.codigo && !linha.id_produto ? "border-erro text-erro" : ""
                      }`}
                      value={linha.codigo}
                      placeholder="P0001"
                      onChange={(e) => mudar(i, "codigo", e.target.value)}
                      // Tab (ou sair do campo) já traz o produto: quem digita do
                      // papel não quer soltar o teclado para caçar no combo.
                      onBlur={() => void buscarPeloCodigo(i)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          void buscarPeloCodigo(i);
                        }
                      }}
                    />
                    {linha.codigo && !linha.id_produto && (
                      <span className="mt-1 block text-[11.5px] text-erro">
                        código não encontrado
                      </span>
                    )}
                  </td>
                  <td>
                    <BuscaCadastro
                      fonte={PRODUTOS}
                      selecionado={
                        linha.id_produto
                          ? {
                              id: Number(linha.id_produto),
                              rotulo: conhecido(linha.id_produto)?.nome ?? linha.descricao,
                            }
                          : null
                      }
                      aoEscolher={(item: ItemBusca | null) => {
                        if (item) guardar(item.bruto as unknown as ProdutoResumo);
                        mudar(i, "id_produto", item ? String(item.id) : "");
                      }}
                    />
                  </td>
                  <td>
                    <input
                      className="campo"
                      value={linha.descricao}
                      onChange={(e) => mudar(i, "descricao", e.target.value)}
                      placeholder="como está escrito no cupom"
                    />
                  </td>
                  <td>
                    <input
                      className="campo mono text-right"
                      inputMode="decimal"
                      value={linha.quantidade}
                      onChange={(e) => mudar(i, "quantidade", e.target.value)}
                    />
                  </td>
                  <td>
                    {/* A unidade DA NOTA. Vem a do estoque por padrão; muda
                        quando o fornecedor vendeu em caixa, fardo ou dúzia. */}
                    <select
                      className="campo"
                      value={linha.um}
                      onChange={(e) => mudar(i, "um", e.target.value)}
                    >
                      <option value="">—</option>
                      {ums.map((u) => (
                        <option key={u.sigla} value={u.sigla}>
                          {u.sigla}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      className="campo mono text-right"
                      inputMode="decimal"
                      value={linha.valor_unitario}
                      onChange={(e) => mudar(i, "valor_unitario", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo mono text-right"
                      inputMode="decimal"
                      value={linha.desconto}
                      onChange={(e) => mudar(i, "desconto", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo mono text-right"
                      inputMode="decimal"
                      value={linha.acrescimo}
                      onChange={(e) => mudar(i, "acrescimo", e.target.value)}
                    />
                  </td>
                  {/* O que a linha custa de fato — a conferência contra o papel
                      é aqui, antes de somar a nota inteira. */}
                  <td className="num mono font-semibold">
                    {totalDaLinha(linha) ? reais(totalDaLinha(linha)) : "—"}
                  </td>
                  {/* O custo por unidade de ESTOQUE: já com o frete rateado e a
                      conversão da embalagem. É outro número que o total da
                      linha, e é ele que vira custo médio. */}
                  <td className="num mono text-suave">
                    {previsto ? (
                      <>
                        {reais(previsto.unitario)}
                        {unidadeDeEstoque(linha) && (
                          <span className="block text-[11px]">
                            por {unidadeDeEstoque(linha)}
                          </span>
                        )}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  {temLote && (
                    <td>
                      <input
                        className="campo"
                        value={linha.lote}
                        onChange={(e) => mudar(i, "lote", e.target.value)}
                      />
                    </td>
                  )}
                  {temLote && (
                    <td>
                      <input
                        className="campo"
                        type="date"
                        value={linha.validade}
                        onChange={(e) => mudar(i, "validade", e.target.value)}
                      />
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <button
        className="btn btn-secundario mt-3"
        onClick={() => setLinhas([...linhas, { ...LINHA }])}
      >
        + item
      </button>

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo rotulo="Frete (R$)">
          <input
            className="campo mono text-right"
            inputMode="decimal"
            value={frete}
            onChange={(e) => setFrete(e.target.value)}
          />
        </Campo>
        <Campo rotulo="Desconto (R$)">
          <input
            className="campo mono text-right"
            inputMode="decimal"
            value={desconto}
            onChange={(e) => setDesconto(e.target.value)}
          />
        </Campo>
        <Campo rotulo="IPI / ST / outros (R$)">
          <input
            className="campo mono text-right"
            inputMode="decimal"
            value={outros}
            onChange={(e) => setOutros(e.target.value)}
          />
        </Campo>
        {/* Reserva, não regra: cada produto entra no local do CADASTRO dele.
            Este vale para o produto que ainda não tem um definido — congelado e
            seco vêm na mesma nota. */}
        <Campo rotulo="Local de reserva" dica="para produto sem local no cadastro">
          <select className="campo" value={idLocal} onChange={(e) => setIdLocal(e.target.value)}>
            {locais.map((l) => (
              <option key={l.id} value={l.id}>
                {l.nome}
              </option>
            ))}
          </select>
        </Campo>
      </div>

      <p className="mt-4 text-[14px]">
        {preenchidas.length} item(ns) · produtos {reais(totalProdutos)} · total da nota{" "}
        <b className="mono">{reais(total)}</b>
        <span className="text-suave">
          {" "}
          — o “custo un.” já traz o frete rateado e a conversão da embalagem: é ele que vira
          custo médio.
        </span>
      </p>
    </Cartao>
  );
}
