"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { fatiar, Paginacao, usePaginacao } from "@/components/paginacao";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";

/**
 * A movimentação do período, produto a produto.
 *
 * O CMV é uma linha só: estoque inicial + compras − estoque final. Ela diz o
 * RESULTADO e não diz de onde veio. Esta tabela é a conta por produto — o que
 * tinha, o que entrou, o que saiu, o que sobrou —, que é o que se confere
 * contra a prateleira e o que vai para o contador.
 *
 * Mês FECHADO vem congelado do fechamento; mês aberto é calculado na hora. A
 * tela diz qual dos dois, porque mandar adiante um número que ainda pode mudar
 * é exatamente o que este relatório existe para evitar.
 */

type Linha = {
  id_produto: number;
  codigo: string | null;
  produto: string;
  um_estoque: string | null;
  categoria: string | null;
  setor: string | null;
  qtd_inicial: number;
  valor_inicial: number;
  qtd_entradas: number;
  valor_entradas: number;
  qtd_saidas: number;
  valor_saidas: number;
  qtd_final: number;
  valor_final: number;
  custo_medio_final: number;
};

type Resposta = {
  inicio: string;
  fim: string;
  congelado: boolean;
  competencia: string | null;
  /** Preenchido quando o recorte cai DENTRO de um mês fechado sem ser ele. */
  mes_fechado: { competencia: string; inicio: string; fim: string } | null;
  produtos: number;
  total: {
    valor_inicial: number;
    valor_entradas: number;
    valor_saidas: number;
    valor_final: number;
  };
  linhas: Linha[];
};

const qtd = (n: number | string) =>
  Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 3 });

export default function Movimentacao({ inicio, fim }: { inicio: string; fim: string }) {
  const [dados, setDados] = useState<Resposta | null>(null);
  const [erro, setErro] = useState("");
  const [busca, setBusca] = useState("");
  const pag = usePaginacao("movimentacao", { padrao: 50, filtros: [busca, inicio, fim] });

  const carregar = useCallback(async () => {
    setDados(null);
    try {
      setDados(
        await api.get<Resposta>(`/cmv/movimentacao?inicio=${inicio}&fim=${fim}`),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [inicio, fim]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // ⚠️ Calculado ANTES das saídas antecipadas: o efeito que segue é um hook, e
  // hook depois de um `return` condicional muda de ordem entre renders.
  const alvo = busca.trim().toLowerCase();
  const filtradas = !dados
    ? []
    : alvo
      ? dados.linhas.filter(
          (l) =>
            l.produto.toLowerCase().includes(alvo) ||
            (l.codigo ?? "").toLowerCase().includes(alvo),
        )
      : dados.linhas;

  const quantas = filtradas.length;
  useEffect(() => {
    pag.setTotal(quantas);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quantas]);

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!dados) return <Carregando />;

  // ⚠️ Aqui a paginação é do NAVEGADOR, e é a exceção que confirma a regra: o
  // rodapé precisa somar TODAS as linhas para a identidade fechar, então o
  // relatório vem inteiro do servidor de propósito. Fatiar o que já está na
  // mão não esconde nada — o total continua sendo o de tudo, e o rodapé diz.
  const linhas = fatiar(filtradas, pag);

  // A conta que a tabela inteira tem de fechar. Se não fechar, o problema é do
  // razão e não do relatório — e é melhor ver isso aqui do que no inventário.
  //
  // ⚠️ A folga acompanha o TAMANHO do relatório. Cada linha sai arredondada em
  // centavos e o rodapé soma as linhas arredondadas — de propósito, para o
  // rodapé fechar com a coluna que a pessoa confere a mão. Num relatório de
  // centenas de produtos isso dá alguns centavos de diferença, que não são erro
  // de razão nenhum: com a folga fixa de cinco centavos, uma base real acusava
  // "a conta não fecha" toda vez, e um alarme que sempre toca ninguém escuta.
  const t = dados.total;
  const diferenca = t.valor_inicial + t.valor_entradas - t.valor_saidas - t.valor_final;
  const folga = Math.max(0.05, 0.005 * dados.produtos);
  const confere = Math.abs(diferenca) < folga;

  return (
    <Cartao
      titulo="Movimentação do estoque"
      descricao="O que cada produto tinha, o que entrou, o que saiu e o que sobrou."
      acao={
        dados.congelado ? (
          <Etiqueta cor="erva">mês fechado · congelado</Etiqueta>
        ) : (
          <Etiqueta cor="alerta">mês aberto · ainda muda</Etiqueta>
        )
      }
    >
      {dados.mes_fechado && (
        <div className="mb-4">
          <Aviso tipo="info">
            Este recorte cai dentro de um mês já fechado. O número definitivo é o do mês
            inteiro ({new Date(dados.mes_fechado.inicio + "T12:00").toLocaleDateString("pt-BR")}{" "}
            a {new Date(dados.mes_fechado.fim + "T12:00").toLocaleDateString("pt-BR")}) — é ele
            que fica congelado e é ele que vai para o contador.
          </Aviso>
        </div>
      )}

      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <label className="min-w-0 flex-1 sm:max-w-[320px]">
          <span className="rotulo">Achar produto</span>
          <input
            className="campo mt-1.5"
            placeholder="produto ou código"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        </label>
        <p className="pb-2 text-[13px] text-suave">
          {alvo
            ? `${linhas.length} de ${dados.produtos} produto(s)`
            : `${dados.produtos} produto(s)`}
        </p>
      </div>

      {!dados.linhas.length ? (
        <Vazio>Nenhum produto se moveu neste período.</Vazio>
      ) : !linhas.length ? (
        <Vazio>Nenhum produto com “{busca}”.</Vazio>
      ) : (
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead>
              <tr>
                <th>Produto</th>
                <th className="num">Inicial</th>
                <th className="num">Entradas</th>
                <th className="num">Saídas</th>
                <th className="num">Final</th>
                <th className="num">Custo médio</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((l) => (
                <tr key={l.id_produto}>
                  <td>
                    <span className="font-medium">{l.produto}</span>
                    <span className="block text-[12.5px] text-suave">
                      <span className="mono">{l.codigo}</span>
                      {l.categoria ? ` · ${l.categoria}` : ""}
                    </span>
                  </td>
                  {/* Quantidade em cima, dinheiro embaixo: quem confere a
                      prateleira olha a quantidade; quem fecha o mês, o valor. */}
                  <td className="num whitespace-nowrap">
                    {qtd(l.qtd_inicial)} {l.um_estoque ?? ""}
                    <span className="block text-[12.5px] text-suave">
                      {reais(Number(l.valor_inicial))}
                    </span>
                  </td>
                  <td className="num whitespace-nowrap text-erva">
                    {Number(l.qtd_entradas) > 0 ? "+" : ""}
                    {qtd(l.qtd_entradas)}
                    <span className="block text-[12.5px] text-suave">
                      {reais(Number(l.valor_entradas))}
                    </span>
                  </td>
                  <td className="num whitespace-nowrap text-erro">
                    {Number(l.qtd_saidas) > 0 ? "−" : ""}
                    {qtd(l.qtd_saidas)}
                    <span className="block text-[12.5px] text-suave">
                      {reais(Number(l.valor_saidas))}
                    </span>
                  </td>
                  <td className="num whitespace-nowrap font-semibold">
                    {qtd(l.qtd_final)} {l.um_estoque ?? ""}
                    <span className="block text-[12.5px] font-normal text-suave">
                      {reais(Number(l.valor_final))}
                    </span>
                  </td>
                  <td className="num mono text-[13px] text-suave">
                    {reais(Number(l.custo_medio_final))}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-linha2 font-semibold">
                {/* O total é sempre de TUDO: filtrar a vista não pode mudar o
                    número que fecha o mês. */}
                <td>Total {alvo ? "— de todos, não do filtro" : ""}</td>
                <td className="num">{reais(t.valor_inicial)}</td>
                <td className="num text-erva">{reais(t.valor_entradas)}</td>
                <td className="num text-erro">{reais(t.valor_saidas)}</td>
                <td className="num">{reais(t.valor_final)}</td>
                <td></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      <Paginacao p={pag} rotulo="produto(s)" />

      <p className="mt-4 text-[13.5px] leading-snug text-suave">
        {confere ? (
          <>
            Inicial + entradas − saídas = final, e a conta fecha. Entradas e saídas aqui são{" "}
            <b>todas</b> — compra, produção, transferência, perda e ajuste —, por isso a soma
            não é o CMV: o CMV conta só a compra.
          </>
        ) : (
          <span className="text-erro">
            A conta não fecha por {reais(Math.abs(diferenca))} (inicial + entradas − saídas ≠
            final). Isso é do razão, não deste relatório. A causa quase sempre é a mesma: saída
            lançada com <b>saldo negativo</b> — ela sai por um custo provisório, e a entrada que
            chega depois revaloriza o que já tinha saído. Procure os produtos com saldo abaixo de
            zero no período e lance a entrada que faltava.
          </span>
        )}
      </p>
    </Cartao>
  );
}
