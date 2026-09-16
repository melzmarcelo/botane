"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { qtd } from "@/lib/numeros";
import { Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import BotaoExportar from "@/components/exportar";

/**
 * A apuração ABERTA nos documentos que a compõem — a memória de cálculo.
 *
 * 🔑 **Pedido da contabilidade (02/09/2026), agora como TELA** (16/09/2026,
 * protótipo aprovado pelo dono). A apuração dizia o resultado em dez linhas e
 * não dizia de ONDE cada linha veio; perguntado *"estes R$ 237 mil de compras,
 * de quais notas são?"*, o sistema não tinha resposta. O documento existe em PDF
 * desde então — e a pergunta nasce **olhando o painel**, não baixando arquivo.
 *
 * 🔑 **O quadro 4 vem PRIMEIRO, ao contrário do PDF.** No papel a ordem é a da
 * conta; na tela, a ordem é a da dúvida — e a dúvida é sempre "por que a soma
 * das notas não é a linha Compras?". Nesta base ele responde alto: 132 notas
 * somam R$ 10.661 e as entradas digitadas sem nota somam R$ 241.703.
 *
 * ⚠️ **O corte é das LISTAS, nunca dos totais.** O estoque final tem 1.331
 * produtos; os rodapés somam a tabela inteira e a tela diz quanto está mostrando
 * — uma lista cortada em silêncio se lê como lista completa.
 */
type Quadro = {
  linhas: Record<string, unknown>[];
  total: number;
  mostrando: number;
  soma: number;
};

type Memoria = {
  inicio: string;
  fim: string;
  vespera: string;
  fechado: boolean;
  metodo: string;
  composicao: { linha: string; valor: number; quadro: string | null; posicao: string | null }[];
  estoque_inicial: Quadro;
  compras_por_nota: Quadro;
  estoque_final: Quadro;
  conciliacao: { linha: string; valor: number }[];
};

const dia = (d: string | null) => (d ? new Date(d + "T12:00").toLocaleDateString("pt-BR") : "");
const num = (v: unknown) => (typeof v === "number" ? v : Number(v ?? 0));
const txt = (v: unknown) => (v == null || v === "" ? "—" : String(v));

function QuadroEstoque({ q, titulo, posicao }: { q: Quadro; titulo: string; posicao: string }) {
  return (
    <Cartao titulo={titulo} descricao={`Posição em ${posicao} · ${q.total} produto(s).`}>
      {!q.linhas.length ? (
        <Vazio>Nenhum produto com saldo nesta data.</Vazio>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Código</th><th>Produto</th><th>Un.</th><th>Categoria</th>
                  <th className="num">Quantidade</th><th className="num">Custo unitário</th>
                  <th className="num">Valor</th>
                </tr>
              </thead>
              <tbody>
                {q.linhas.map((l) => (
                  <tr key={String(l.id_produto)}>
                    <td className="mono text-[12.5px]">{txt(l.codigo)}</td>
                    <td>{txt(l.produto)}</td>
                    <td className="text-[13px] text-suave">{txt(l.um_estoque)}</td>
                    <td className="text-[13px] text-suave">{txt(l.categoria)}</td>
                    {/* ⚠️ Saldo NEGATIVO em vermelho: é produto que saiu sem ter
                        entrado, e ele diminui o estoque final — ou seja,
                        AUMENTA o CMV. Passar batido esconde a causa. */}
                    <td className={`num ${num(l.quantidade) < 0 ? "text-erro" : ""}`}>
                      {qtd(num(l.quantidade))}
                    </td>
                    <td className="num text-suave">{reais(num(l.custo_unitario))}</td>
                    <td className={`num ${num(l.valor) < 0 ? "text-erro" : ""}`}>
                      {reais(num(l.valor))}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-linha2 font-semibold">
                  <td colSpan={6}>Soma dos {q.total} produto(s)</td>
                  <td className="num">{reais(q.soma)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
          {q.mostrando < q.total && (
            <p className="mt-3 text-[13px] text-suave">
              Mostrando {q.mostrando} de {q.total} — <b>o rodapé soma a tabela inteira</b>. Para a
              lista completa, baixe o documento.
            </p>
          )}
        </>
      )}
    </Cartao>
  );
}

export default function MemoriaDeCalculo({ inicio, fim }: { inicio: string; fim: string }) {
  const [m, setM] = useState<Memoria | null>(null);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    setM(null);
    setErro("");
    try {
      setM(await api.get<Memoria>(`/cmv/memoria?inicio=${inicio}&fim=${fim}&limite=200`));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [inicio, fim]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  if (erro) return <p className="text-[14px] text-erro">{erro}</p>;
  if (!m) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <Cartao
        titulo="A apuração, aberta nos documentos que a compõem"
        descricao="A resposta para “de onde veio este número?”."
        acao={
          <span className="nao-imprimir">
            <BotaoExportar
              relatorio="memoria-cmv"
              rotulo="Baixar em PDF"
              iniciais={{ inicio, fim }}
              formatoPadrao="pdf"
            />
          </span>
        }
      >
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead>
              <tr><th>Composição do CMV</th><th className="num">Valor</th><th>Aberto em</th></tr>
            </thead>
            <tbody>
              {m.composicao.map((c, i) => (
                <tr
                  key={c.linha}
                  className={i === m.composicao.length - 1 ? "font-semibold" : ""}
                >
                  <td>
                    {c.linha}
                    {c.posicao && (
                      <span className="text-suave"> (posição em {dia(c.posicao)})</span>
                    )}
                  </td>
                  <td className="num">{reais(c.valor)}</td>
                  <td className="text-[13px] text-suave">{c.quadro ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] text-suave">
          <span>
            <b className="text-tinta">Método de custeio:</b> {m.metodo}
          </span>
          <span className="flex items-center gap-2">
            <b className="text-tinta">Situação do período:</b>
            {m.fechado ? (
              <Etiqueta cor="erva">fechado (congelado)</Etiqueta>
            ) : (
              <Etiqueta cor="alerta">aberto — o número ainda pode mudar</Etiqueta>
            )}
          </span>
        </div>
      </Cartao>

      <Cartao
        titulo="Quadro 4 — Conciliação"
        descricao="Por que a soma das notas não é a linha “Compras”."
      >
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead>
              <tr><th>Da soma das notas até a linha Compras</th><th className="num">Valor</th></tr>
            </thead>
            <tbody>
              {m.conciliacao.map((c, i) => (
                <tr
                  key={c.linha}
                  className={i === m.conciliacao.length - 1 ? "border-t-2 border-linha2 font-semibold" : ""}
                >
                  <td>{c.linha}</td>
                  <td className="num">{reais(c.valor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Cartao>

      <Cartao
        titulo="Quadro 2 — Compras do período, por documento"
        descricao={`${m.compras_por_nota.total} documento(s). A coluna “Diferença” é onde mora o erro de lançamento.`}
      >
        {!m.compras_por_nota.linhas.length ? (
          <Vazio>Nenhuma entrada no período.</Vazio>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Documento</th><th>Fornecedor</th><th className="num">Entrada</th>
                    <th className="num">Itens</th><th className="num">Total da nota</th>
                    <th className="num">Entrou no estoque</th><th className="num">Diferença</th>
                  </tr>
                </thead>
                <tbody>
                  {m.compras_por_nota.linhas.map((l, i) => (
                    <tr key={`${l.id_nota ?? "sem"}-${i}`}>
                      <td className="mono text-[12.5px]">{txt(l.documento)}</td>
                      <td>{txt(l.fornecedor)}</td>
                      <td className="num text-[13px] text-suave">
                        {l.data_entrada ? dia(String(l.data_entrada)) : "—"}
                      </td>
                      <td className="num text-suave">{txt(l.itens)}</td>
                      <td className="num text-suave">
                        {l.valor_da_nota == null ? "—" : reais(num(l.valor_da_nota))}
                      </td>
                      <td className="num">{reais(num(l.valor_no_razao))}</td>
                      <td className={`num ${num(l.diferenca) < 0 ? "text-erro" : "text-suave"}`}>
                        {l.diferenca == null ? "—" : reais(num(l.diferenca))}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t-2 border-linha2 font-semibold">
                    <td colSpan={5}>Soma do que entrou no razão</td>
                    <td className="num">{reais(m.compras_por_nota.soma)}</td>
                    <td className="num text-[13px] font-normal text-suave">ver o quadro 4</td>
                  </tr>
                </tfoot>
              </table>
            </div>
            {/* ⚠️ Este quadro NÃO fecha com a linha "Compras", e é de propósito:
                falta a remessa entre lojas, que é compra do destino sem nota. O
                rodapé manda para o quadro 4 em vez de deixar a diferença solta. */}
            <p className="mt-3 text-[13px] leading-snug text-suave">
              Este quadro <b>não fecha</b> com a linha “Compras” — falta a remessa recebida de
              outra loja, que é compra do destino sem nota. Quem fecha a diferença é o quadro 4.
              {m.compras_por_nota.mostrando < m.compras_por_nota.total &&
                ` Mostrando ${m.compras_por_nota.mostrando} de ${m.compras_por_nota.total}; o rodapé soma todos.`}
            </p>
          </>
        )}
      </Cartao>

      <QuadroEstoque
        q={m.estoque_inicial}
        titulo="Quadro 1 — Estoque inicial, item a item"
        posicao={dia(m.vespera)}
      />
      <QuadroEstoque
        q={m.estoque_final}
        titulo="Quadro 3 — Estoque final, item a item"
        posicao={dia(m.fim)}
      />
    </div>
  );
}
