"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Fornecedor, Local, ProdutoResumo, UnidadeMedida, reais } from "@/lib/cadastros";
import { Aviso, Campo, Cartao } from "@/components/ui";

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
  }[];
};

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
  const texto = (n: number | null | undefined) => (n ? String(n) : "");

  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [ums, setUms] = useState<UnidadeMedida[]>([]);
  const [idFornecedor, setIdFornecedor] = useState(texto(editando?.id_fornecedor));
  const [numeroNota, setNumeroNota] = useState(editando?.numero ?? "");
  const [serie, setSerie] = useState(editando?.serie ?? "");
  const [dataEmissao, setDataEmissao] = useState(
    () => editando?.data_emissao?.slice(0, 10) ?? new Date().toISOString().slice(0, 10),
  );
  const [frete, setFrete] = useState(texto(editando?.valor_frete));
  const [desconto, setDesconto] = useState(texto(editando?.valor_desconto));
  const [outros, setOutros] = useState(texto(editando?.valor_outros));
  const [idLocal, setIdLocal] = useState(texto(editando?.id_local));
  const [linhas, setLinhas] = useState<Linha[]>(
    editando?.itens.length
      ? editando.itens.map((i) => ({
          codigo: produtos.find((p) => p.id === i.id_produto)?.codigo ?? "",
          um: i.um_nota ?? "",
          id_produto: texto(i.id_produto),
          descricao: i.descricao_fornecedor ?? "",
          quantidade: String(Number(i.quantidade)),
          valor_unitario: String(Number(i.valor_unitario)),
          lote: i.lote_nf ?? "",
          validade: i.validade_nf?.slice(0, 10) ?? "",
        }))
      : [{ ...LINHA }, { ...LINHA }],
  );
  const [erro, setErro] = useState("");
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

  const preenchidas = linhas.filter((l) => (l.id_produto || l.descricao) && numero(l.quantidade) > 0);
  const totalProdutos = preenchidas.reduce(
    (soma, l) => soma + numero(l.quantidade) * numero(l.valor_unitario),
    0,
  );
  const total = totalProdutos + numero(frete) + numero(outros) - numero(desconto);

  /** O mesmo rateio por valor que o backend faz — para conferir antes de gravar. */
  const custos = useMemo(
    () =>
      preenchidas.map((l) => {
        const bruto = numero(l.quantidade) * numero(l.valor_unitario);
        const peso = totalProdutos > 0 ? bruto / totalProdutos : 0;
        const liquido = bruto + numero(frete) * peso + numero(outros) * peso - numero(desconto) * peso;
        return { linha: l, unitario: numero(l.quantidade) > 0 ? liquido / numero(l.quantidade) : 0 };
      }),
    [preenchidas, totalProdutos, frete, outros, desconto],
  );

  /**
   * Acha o produto pelo código digitado.
   *
   * Compara sem caixa e sem espaço porque o código vem de um papel: quem digita
   * escreve "p12" e o cadastro guarda "P0012".
   */
  const porCodigo = (codigo: string) => {
    const alvo = codigo.trim().toLowerCase();
    if (!alvo) return undefined;
    return produtos.find((p) => (p.codigo ?? "").toLowerCase() === alvo);
  };

  /** Preenche a linha inteira a partir do produto: descrição, unidade e código. */
  const comProduto = (linha: Linha, p: ProdutoResumo | undefined): Linha =>
    !p
      ? linha
      : {
          ...linha,
          id_produto: String(p.id),
          codigo: p.codigo ?? "",
          // A unidade da nota nasce igual à do estoque — é o caso comum. Quando
          // a nota vier em caixa, quem digita troca aqui e a conversão do
          // lançamento faz o resto.
          um: linha.um || p.um_estoque || "",
          descricao: linha.descricao || p.nome,
        };

  function mudar(indice: number, campo: keyof Linha, valor: string) {
    setLinhas((atuais) =>
      atuais.map((l, i) => {
        if (i !== indice) return l;
        const nova = { ...l, [campo]: valor };
        // Escolher o produto no combo preenche código, unidade e descrição.
        if (campo === "id_produto") {
          return valor
            ? comProduto(nova, produtos.find((p) => String(p.id) === valor))
            : { ...nova, codigo: "" };
        }
        return nova;
      }),
    );
  }

  /** Tab no campo de código: acha o produto e preenche o resto da linha. */
  function buscarPeloCodigo(indice: number) {
    setLinhas((atuais) =>
      atuais.map((l, i) => (i === indice ? comProduto(l, porCodigo(l.codigo)) : l)),
    );
  }

  async function gravar() {
    setErro("");
    if (!preenchidas.length) {
      setErro("Coloque ao menos um item com quantidade.");
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
          lote: l.lote || null,
          validade: l.validade || null,
        })),
      };
      const r = editando
        ? await api.put<{ id: number }>(`/notas/${editando.id}`, corpo)
        : await api.post<{ id: number }>("/notas", corpo);
      aoGravar(r.id ?? editando?.id ?? 0);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível gravar a nota");
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
      {erro && (
        <div className="mb-4">
          <Aviso tipo="erro">{erro}</Aviso>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo rotulo="Fornecedor">
          <select
            className="campo"
            value={idFornecedor}
            onChange={(e) => setIdFornecedor(e.target.value)}
          >
            <option value="">— sem fornecedor —</option>
            {fornecedores.map((f) => (
              <option key={f.id} value={f.id}>
                {f.nome}
              </option>
            ))}
          </select>
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
              <th className="num w-[112px] min-w-[112px]">Valor un.</th>
              <th className="w-[104px] min-w-[104px]">Lote</th>
              <th className="w-[160px] min-w-[160px]">Validade</th>
              <th className="num w-[104px] min-w-[104px]">Custo un.</th>
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
                      onBlur={() => buscarPeloCodigo(i)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          buscarPeloCodigo(i);
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
                    <select
                      className="campo"
                      value={linha.id_produto}
                      onChange={(e) => mudar(i, "id_produto", e.target.value)}
                    >
                      <option value="">— escolher depois —</option>
                      {produtos.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.nome}
                          {p.um_estoque ? ` (${p.um_estoque})` : ""}
                        </option>
                      ))}
                    </select>
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
                      className="campo"
                      value={linha.lote}
                      onChange={(e) => mudar(i, "lote", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo"
                      type="date"
                      value={linha.validade}
                      onChange={(e) => mudar(i, "validade", e.target.value)}
                    />
                  </td>
                  <td className="num mono text-suave">
                    {previsto ? reais(previsto.unitario) : "—"}
                  </td>
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
        <Campo rotulo="Entra no local">
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
          — o frete já está dividido entre os itens na coluna “custo un.”.
        </span>
      </p>
    </Cartao>
  );
}
