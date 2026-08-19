"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Fornecedor, Local, ProdutoResumo, reais } from "@/lib/cadastros";
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
  id_produto: string;
  descricao: string;
  quantidade: string;
  valor_unitario: string;
  lote: string;
  validade: string;
};

const LINHA: Linha = {
  id_produto: "",
  descricao: "",
  quantidade: "",
  valor_unitario: "",
  lote: "",
  validade: "",
};

const numero = (texto: string) => Number((texto || "0").replace(",", ".")) || 0;

export default function NotaManual({
  produtos,
  locais,
  aoGravar,
  aoFechar,
}: {
  produtos: ProdutoResumo[];
  locais: Local[];
  aoGravar: (id: number) => void;
  aoFechar: () => void;
}) {
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [idFornecedor, setIdFornecedor] = useState("");
  const [numeroNota, setNumeroNota] = useState("");
  const [serie, setSerie] = useState("");
  const [dataEmissao, setDataEmissao] = useState(() => new Date().toISOString().slice(0, 10));
  const [frete, setFrete] = useState("");
  const [desconto, setDesconto] = useState("");
  const [outros, setOutros] = useState("");
  const [idLocal, setIdLocal] = useState("");
  const [linhas, setLinhas] = useState<Linha[]>([{ ...LINHA }, { ...LINHA }]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    void api
      .get<Fornecedor[]>("/fornecedores")
      .then(setFornecedores)
      .catch(() => setFornecedores([]));
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

  function mudar(indice: number, campo: keyof Linha, valor: string) {
    setLinhas((atuais) =>
      atuais.map((l, i) => {
        if (i !== indice) return l;
        const nova = { ...l, [campo]: valor };
        // Escolher o produto preenche a descrição: a nota digitada guarda o que
        // estava escrito no papel, e o padrão razoável é o nome do produto.
        if (campo === "id_produto" && valor && !l.descricao) {
          nova.descricao = produtos.find((p) => String(p.id) === valor)?.nome ?? "";
        }
        return nova;
      }),
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
      const r = await api.post<{ id: number }>("/notas", {
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
          valor_unitario: numero(l.valor_unitario),
          lote: l.lote || null,
          validade: l.validade || null,
        })),
      });
      aoGravar(r.id);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível gravar a nota");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <Cartao
      titulo="Digitar nota de entrada"
      descricao="Para a compra que não tem XML: mercado, feira, açougue."
      acao={
        <div className="flex items-center gap-2">
          <button className="btn btn-primario" onClick={gravar} disabled={ocupado}>
            {ocupado ? "Gravando…" : "Gravar nota"}
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
            <tr>
              <th className="w-[34%]">Produto</th>
              <th>Descrição na nota</th>
              <th className="num">Qtd</th>
              <th className="num">Valor un.</th>
              <th>Lote</th>
              <th>Validade</th>
              <th className="num">Custo un.</th>
            </tr>
          </thead>
          <tbody>
            {linhas.map((linha, i) => {
              const previsto = custos.find((c) => c.linha === linha);
              return (
                <tr key={i}>
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
                      className="campo mono w-[90px] text-right"
                      inputMode="decimal"
                      value={linha.quantidade}
                      onChange={(e) => mudar(i, "quantidade", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo mono w-[100px] text-right"
                      inputMode="decimal"
                      value={linha.valor_unitario}
                      onChange={(e) => mudar(i, "valor_unitario", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo w-[100px]"
                      value={linha.lote}
                      onChange={(e) => mudar(i, "lote", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      className="campo w-[140px]"
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
