"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";

/**
 * Os cadastros que têm exatamente o mesmo nome — o caso do ABACATE, em lote.
 *
 * 🔑 **O catálogo do Omie cria um cadastro por CÓDIGO**, e o mesmo abacate
 * aparece uma vez para cada fornecedor que já o vendeu. Juntar de dois em dois
 * pela tela do Vincular resolve, mas com centenas de repetidos ninguém percorre
 * a lista — e o trabalho não é feito.
 *
 * 🔑 **Esta tela DETECTA; quem decide é quem está olhando.** É a distinção que
 * o projeto já pagou uma vez: existiu uma cascata que vinculava sozinha por
 * semelhança de nome e foi removida, porque errava nos dois sentidos. Nome
 * IDÊNTICO é um sinal muito mais forte que semelhança — mas continua sendo um
 * sinal, e a fusão não tem desfazer. Por isso a lista vem inteira, com os
 * códigos de cada cadastro à vista, e nada acontece sem clique.
 *
 * ⚠️ **O exemplo que ensina a olhar antes**: "VALE-PRESENTE" pode ser três
 * valores diferentes com o mesmo nome. Juntá-los seria perder a distinção que
 * o cardápio faz.
 */

type Item = {
  id: number;
  codigo: string;
  nome: string;
  codigo_omie: string | null;
  codigo_pdv: string | null;
  tipo: string;
  controla_estoque: boolean;
  um_estoque: string | null;
  categoria: string | null;
  movimentos: number;
  travas: string[];
};

type Grupo = {
  nome: string;
  quantos: number;
  id_principal: number;
  itens: Item[];
  pode: boolean;
  impedidos: number[];
};

export default function Duplicados() {
  const { pode } = useSessao();
  const aviso = useAviso();
  const [grupos, setGrupos] = useState<Grupo[] | null>(null);
  const [soOmie, setSoOmie] = useState(false);
  const [baixar, setBaixar] = useState(true);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [confirmando, setConfirmando] = useState<Grupo | null>(null);

  const carregar = useCallback(async () => {
    setGrupos(null);
    try {
      setGrupos(
        await api.get<Grupo[]>(`/produtos/duplicados?so_do_omie=${soOmie}`),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [soOmie]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function juntar(g: Grupo) {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string }>("/produtos/duplicados/fundir", {
        id_principal: g.id_principal,
        // ⚠️ Os ids que ESTÃO na tela: entre ver a lista e confirmar, uma
        // importação pode ter criado mais um cadastro com aquele nome.
        ids_que_saem: g.itens.filter((i) => i.id !== g.id_principal).map((i) => i.id),
        baixar_vendas: baixar,
      });
      aviso.sucesso(`${g.nome}: ${r.message}`);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível juntar");
    } finally {
      setOcupado(false);
      setConfirmando(null);
      // ⚠️ **Recarrega DEU CERTO OU NÃO.** A lista só se atualizava no caminho
      // de sucesso, e uma resposta perdida no meio — o servidor grava, o
      // navegador não recebe — deixava na tela um grupo que já não existe.
      // Quem clicasse de novo mandaria uma fusão já feita, e a mensagem de
      // erro que voltasse não teria relação com o que a pessoa está vendo. A
      // lista é a verdade do servidor: depois de mexer, pergunta-se de novo.
      await carregar();
    }
  }

  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;

  const podeEditar = pode("cadastros.produtos");
  const prontos = (grupos ?? []).filter((g) => g.pode);

  return (
    <div className="flex flex-col gap-6">
      <header>
        <Link href="/produtos" className="link-voltar">
          produtos
        </Link>
        <h1 className="mt-1 text-[26px] font-bold leading-tight tracking-tight sm:text-[32px]">
          Cadastros com o mesmo nome
        </h1>
        <p className="mt-1 max-w-[70ch] text-suave">
          O catálogo do Omie cria um cadastro por código — e o mesmo abacate aparece uma vez
          para cada fornecedor que já o vendeu. Aqui eles ficam lado a lado para você juntar de
          uma vez.
        </p>
      </header>

      {/* 🔑 O aviso vem ANTES da lista, e não depois: quem lê a lista primeiro
          já começou a clicar. */}
      <Aviso tipo="info">
        <b>Nome igual não é prova de que é o mesmo produto.</b> Dentro do catálogo do Omie quase
        sempre é — mas <i>VALE-PRESENTE</i> pode ser três valores diferentes, e o importador
        apara nomes longos no tamanho do campo, o que faz dois nomes diferentes chegarem aqui
        iguais. Confira os códigos de cada linha antes de juntar. <b>A fusão não tem desfazer.</b>
      </Aviso>

      <div className="flex flex-wrap items-center gap-4">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            className="h-4 w-4 accent-erva"
            checked={soOmie}
            onChange={(e) => setSoOmie(e.target.checked)}
          />
          <span className="text-[14px]">só os que vieram do Omie</span>
        </label>
        {podeEditar && (
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-erva"
              checked={baixar}
              onChange={(e) => setBaixar(e.target.checked)}
            />
            <span className="text-[14px]">
              baixar do estoque o que foi vendido e nunca saiu{" "}
              <span className="text-suave">— senão a falta vira ajuste de inventário</span>
            </span>
          </label>
        )}
      </div>

      {!grupos ? (
        <Carregando />
      ) : !grupos.length ? (
        <Vazio>
          Nenhum cadastro repetido pelo nome
          {soOmie ? " entre os que vieram do Omie" : ""}. Nada a juntar — e esta é a boa
          notícia.
        </Vazio>
      ) : (
        <>
          <p className="text-[14px] text-suave">
            {grupos.length} nome(s) repetido(s), {prontos.length} pronto(s) para juntar.
          </p>
          {grupos.map((g) => (
            <Cartao
              key={g.nome}
              titulo={g.nome}
              descricao={`${g.quantos} cadastros com este nome`}
              acao={
                podeEditar && g.pode ? (
                  <button
                    type="button"
                    className="btn btn-secundario"
                    disabled={ocupado}
                    onClick={() => setConfirmando(g)}
                  >
                    Juntar os {g.quantos}
                  </button>
                ) : undefined
              }
            >
              {!g.pode && (
                // ⚠️ Dois com história não se juntam: unir dois razões exigiria
                // reescrever movimento, e o custo médio resultante seria invenção.
                <Aviso tipo="info">
                  Mais de um destes já tem história (movimento no razão, mês fechado, inventário
                  ou produção). Junte pela tela de cada produto o que der, ou deixe como está —
                  unir dois históricos de estoque não é possível.
                </Aviso>
              )}
              <div className="overflow-x-auto">
                <table className="tabela mt-2">
                  <thead>
                    <tr>
                      <th>Código</th>
                      <th>Omie</th>
                      <th>PDV</th>
                      <th>Categoria</th>
                      <th className="num">Movimentos</th>
                      <th>Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {g.itens.map((i) => (
                      <tr key={i.id}>
                        <td className="mono">
                          <Link href={`/produtos/${i.id}`} className="link-registro">
                            {i.codigo}
                          </Link>
                        </td>
                        <td className="mono">{i.codigo_omie ?? "—"}</td>
                        <td className="mono">{i.codigo_pdv ?? "—"}</td>
                        <td>{i.categoria ?? "—"}</td>
                        <td className="num">{i.movimentos}</td>
                        <td>
                          {i.id === g.id_principal ? (
                            <Etiqueta cor="erva">fica</Etiqueta>
                          ) : i.travas.length ? (
                            <span className="text-[12.5px] text-alerta">
                              {i.travas.join(" · ")}
                            </span>
                          ) : (
                            <span className="text-[12.5px] text-suave">vira inativo</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Cartao>
          ))}
        </>
      )}

      {confirmando && (
        <Confirmacao
          titulo={`Juntar os ${confirmando.quantos} cadastros de “${confirmando.nome}”?`}
          rotuloConfirmar="Juntar"
          ocupado={ocupado}
          aoConfirmar={() => void juntar(confirmando)}
          aoCancelar={() => setConfirmando(null)}
        >
          Os códigos do Omie e do PDV de todos passam a cair no cadastro que fica, e os demais
          viram inativos. <b>Isso não tem desfazer.</b>
        </Confirmacao>
      )}
    </div>
  );
}
