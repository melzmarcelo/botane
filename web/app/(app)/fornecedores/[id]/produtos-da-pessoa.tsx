"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { Paginacao, fatiar, usePaginacao } from "@/components/paginacao";

/**
 * O que esta pessoa fornece — e por quanto, da última vez.
 *
 * 🔑 **Pedido do dono (09/09/2026):** *"no cadastro de pessoas, criar um grupo
 * dos produtos que a pessoa/fornecedor está vinculado"*. A ficha já dizia
 * **quantos** (`12 produto(s)`), e o número sozinho não responde a pergunta que
 * se faz olhando para ela: *o que a gente compra deste aqui?* — para descobrir,
 * era preciso ir à lista de produtos e filtrar um por um.
 *
 * ⚠️ **O preço é POR UNIDADE DE ESTOQUE**, nunca por embalagem. Ao lado do
 * fator, a conta fica conferível: caixa com 12, R$ 2,50 a unidade, R$ 30,00 a
 * caixa. Mostrar só o preço deixaria "R$ 2,50" parecendo o preço da caixa.
 *
 * ⚠️ **Só os ATIVOS, e de dez em dez** (decisão do dono, 09/09/2026). A primeira
 * versão trazia o inativo marcado e a lista inteira: na base real isso encheu o
 * cartão de cadastro arquivado e empurrou o resto da ficha para fora da tela.
 * O recorte é do servidor; o corte de dez é daqui.
 *
 * ⚠️ **Tamanho FIXO, sem seletor.** Um cartão dentro de uma ficha tem espaço
 * decidido pelo layout, não por quem olha — oferecer 100 ali não faria sentido,
 * e a escolha não teria por que ser lembrada.
 */

type Vinculo = {
  id: number;
  codigo: string;
  nome: string;
  um_estoque: string | null;
  ativo: boolean;
  status: string;
  codigo_no_fornecedor: string | null;
  embalagem: string | null;
  fator: number | null;
  ultimo_preco: number | null;
  ultima_compra: string | null;
  preferencial: boolean;
};

const dataBr = (d: string | null) =>
  d ? new Date(d.slice(0, 10) + "T00:00").toLocaleDateString("pt-BR") : "—";

export default function ProdutosDaPessoa({ id }: { id: number }) {
  const [itens, setItens] = useState<Vinculo[] | null>(null);
  const [erro, setErro] = useState("");
  // ⚠️ **`prefixoUrl` mesmo havendo uma lista só**: a ficha pode ganhar outra
  // amanhã, e as duas escreveriam `p` na mesma URL — virar a página de uma
  // levaria a outra junto, sem ninguém ligar uma coisa à outra.
  // ⚠️ A lista vem INTEIRA do servidor e o corte é aqui: são dezenas de linhas,
  // não milhares, e paginar no banco custaria uma ida a mais por página para
  // economizar nada.
  const pag = usePaginacao("pessoa-produtos", { padrao: 10, prefixoUrl: "pr" });

  const carregar = useCallback(async () => {
    try {
      const r = await api.get<Vinculo[]>(`/fornecedores/${id}/produtos`);
      setItens(r);
      pag.setTotal(r.length);
    } catch (e) {
      // Erro de CARREGAMENTO é mensagem no cartão, não aviso flutuante: o aviso
      // some, e quem abriu a ficha ficaria com um bloco vazio sem explicação.
      setErro(e instanceof Error ? e.message : "Falha ao carregar os produtos");
      setItens([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  if (!itens) return <Carregando />;

  return (
    <Cartao
      titulo="Produtos desta pessoa"
      descricao={
        itens.length
          ? `${itens.length} produto(s) ativo(s) — o preço é por unidade de estoque.`
          : "O vínculo nasce sozinho quando uma nota dela é lançada."
      }
    >
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {!itens.length ? (
        // ⚠️ **Vazio EXPLICA, não só constata.** Ninguém cadastra este vínculo à
        // mão: ele nasce do lançamento da nota. Sem essa frase, "nenhum produto"
        // parece um campo que faltou preencher.
        <Vazio>
          Nenhum produto vinculado ainda. O vínculo se cria sozinho ao lançar uma nota de
          entrada desta pessoa, ou ao vincular um item de nota a um produto.
        </Vazio>
      ) : (
        <div className="overflow-x-auto">
          <table className="tabela">
            <thead>
              <tr>
                <th>Produto</th>
                <th>Código dele</th>
                <th>Embalagem</th>
                <th className="text-right">Último preço</th>
                <th>Última compra</th>
              </tr>
            </thead>
            <tbody>
              {fatiar(itens, pag).map((v) => (
                <tr key={v.id}>
                  <td>
                    <Link href={`/produtos/${v.id}`} className="link-registro">
                      {v.nome}
                    </Link>
                    <span className="ml-2 inline-flex gap-1">
                      {/* 🔑 O preferencial é o que a cascata de custo escolhe
                          primeiro quando dois fornecedores vendem o mesmo. */}
                      {v.preferencial && <Etiqueta cor="erva">preferencial</Etiqueta>}
                      {/* ⚠️ Não há etiqueta de "inativo": o servidor já não
                          manda inativo. Deixá-la aqui seria código que nunca
                          roda, e o próximo leitor concluiria que a lista traz
                          arquivado — que é justamente o que ela não traz.
                          🔑 O RASCUNHO fica: ele é ATIVO e vendável, mas ainda
                          sem ficha, e é o que explica um custo que não fecha. */}
                      {v.status === "RASCUNHO" && <Etiqueta cor="alerta">rascunho</Etiqueta>}
                    </span>
                    <span className="block text-[12.5px] text-suave">{v.codigo}</span>
                  </td>
                  <td className="mono text-[13px]">{v.codigo_no_fornecedor ?? "—"}</td>
                  <td className="text-[13px] text-suave">
                    {v.embalagem || v.fator ? (
                      <>
                        {v.embalagem ?? "—"}
                        {/* Fator 1 não informa nada: "1 UN = 1 UN" é ruído em
                            toda linha de quem não usa embalagem. */}
                        {v.fator && Number(v.fator) !== 1
                          ? ` × ${Number(v.fator).toLocaleString("pt-BR")}`
                          : ""}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="mono text-right">
                    {v.ultimo_preco === null ? (
                      "—"
                    ) : (
                      <>
                        {reais(v.ultimo_preco)}
                        <span className="block text-[12.5px] text-suave">
                          por {v.um_estoque ?? "un"}
                        </span>
                      </>
                    )}
                  </td>
                  <td className="text-[13px] text-suave">{dataBr(v.ultima_compra)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* Dez por página, sem seletor: o tamanho é do cartão, não de quem
              olha. Ver `semTamanho` em `components/paginacao`. */}
          <Paginacao p={pag} rotulo="produto(s)" semTamanho />
        </div>
      )}
    </Cartao>
  );
}
