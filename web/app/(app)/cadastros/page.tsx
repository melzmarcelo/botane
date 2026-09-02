"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import {
  Categoria,
  GRANDEZAS,
  Local,
  Setor,
  TIPOS_CATEGORIA,
  TIPOS_LOCAL,
  UnidadeMedida,
} from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { Paginacao, fatiar, usePaginacao } from "@/components/paginacao";
import GruposCmv from "./grupos-cmv";

type Aba = "setores" | "locais" | "categorias" | "unidades" | "grupos-cmv";

const ABAS: { id: Aba; nome: string; chave: string; explica: string }[] = [
  {
    id: "setores",
    nome: "Setores",
    chave: "cadastros.setores",
    explica:
      "Organização do trabalho: cozinha, bar, confeitaria. Serve para destinar consumo interno, agrupar produção e filtrar o CMV por área.",
  },
  {
    id: "locais",
    nome: "Locais de estoque",
    chave: "cadastros.locais",
    explica:
      "Onde a coisa fica fisicamente e tem saldo: estoque seco, câmara fria, freezer. Não confundir com setor.",
  },
  {
    id: "categorias",
    nome: "Categorias",
    chave: "cadastros.categorias",
    explica:
      "Árvore de classificação dos produtos. É por ela que a curva ABC e o CMV por grupo vão se organizar.",
  },
  {
    id: "unidades",
    nome: "Unidades de medida",
    chave: "cadastros.unidades_medida",
    explica:
      "Quilo, litro, unidade. O fator converte para a base da grandeza (g, ml, un). Quantas unidades vêm na caixa é do produto, não daqui.",
  },
  {
    id: "grupos-cmv",
    nome: "Grupos do CMV",
    chave: "cmv.grupos",
    explica:
      "Separa no painel de CMV o que não é comida. Cada grupo junta um ou mais tipos de produto — e um tipo só pode estar num grupo.",
  },
];

export default function PaginaCadastros() {
  const aviso = useAviso();
  const { pode, eu } = useSessao();
  // Dica de interface: com o envio desligado, a marca não tem o que decidir.
  const enviaAoPdv = !!eu?.enviar_ao_pdv;
  // A aba vem da URL: é o que permite o menu apontar direto para "Locais de
  // estoque" e o endereço continuar valendo quando alguém o guarda.
  const busca = useSearchParams();
  const router = useRouter();
  const pedida = busca.get("aba") as Aba | null;
  // ⚠️ **Sem `?aba=`, abre a PRIMEIRA aba — e a primeira que a pessoa pode
  // ver.** O padrão era `"locais"`, escrito à mão: entrar pelo menu caía na
  // segunda aba, com a primeira ali do lado, marcada como não escolhida. E
  // quem não tivesse permissão de locais caía numa aba vazia sem entender.
  const primeira = (ABAS.find((a) => pode(a.chave)) ?? ABAS[0]).id;
  const aba: Aba = ABAS.some((a) => a.id === pedida) ? (pedida as Aba) : primeira;
  const setAba = (nova: Aba) => router.replace(`/cadastros?aba=${nova}`);
  /**
   * 🔑 **"Poucos por natureza" deixou de ser verdade.** Estas tabelas ficaram
   * FORA da paginação de propósito, com o argumento de que rodapé de página em
   * lista de três linhas é ruído. Numa base real são **180 locais, 86
   * categorias e 52 setores** — e a lista inteira numa página só empurra o
   * formulário de cadastro para fora da tela e obriga a rolar para achar o
   * registro que se quer corrigir.
   *
   * ⚠️ **Aqui o corte é do NAVEGADOR, e isso não é a mentira que a regra da
   * casa proíbe.** A regra existe para lista que pode crescer sem teto: trazer
   * 3.226 produtos e fatiar aqui deixaria a lista cortada por um `LIMIT` que
   * ninguém vê. Estas cinco vêm INTEIRAS do servidor porque a tela também as
   * usa para editar, e o rodapé conta o que ela realmente tem em mãos — o total
   * é o total de verdade, não uma promessa.
   *
   * ⚠️ A aba entra como FILTRO: trocar de aba volta para a primeira página,
   * senão quem estava na página 5 dos locais cairia numa tela vazia nas
   * unidades de medida.
   */
  const [mostrarInativos, setMostrarInativos] = useState(false);
  const pag = usePaginacao("cadastros", { filtros: [aba, mostrarInativos] });
  const [setores, setSetores] = useState<Setor[] | null>(null);
  const [locais, setLocais] = useState<Local[] | null>(null);
  const [categorias, setCategorias] = useState<Categoria[] | null>(null);
  const [ums, setUms] = useState<UnidadeMedida[] | null>(null);
  const [erro, setErro] = useState("");

  // formulários de criação, um por aba
  const [novoSetor, setNovoSetor] = useState("");
  const [novoLocal, setNovoLocal] = useState({ nome: "", tipo: "SECO" });
  const [novaCategoria, setNovaCategoria] = useState({ nome: "", id_pai: "", tipo: "INSUMO" });
  const [novaUm, setNovaUm] = useState({ sigla: "", nome: "", grandeza: "UNIDADE", fator_base: "1" });

  /**
   * 🔑 **Dava para criar e desativar, e não dava para CORRIGIR.** Os quatro PUT
   * existem no servidor desde o começo; a tela só nunca os ofereceu. Um setor
   * cadastrado com o nome errado no primeiro dia ficava errado para sempre — e
   * o jeito de "consertar" era desativar e criar outro, que deixa o histórico
   * apontando para um cadastro morto.
   *
   * ⚠️ **A correção usa o MESMO formulário do cadastro**, e não uma janela nem
   * campos na linha: criar e corrigir têm a mesma forma, para o olho reconhecer
   * — é o corte que Fornecedores e Usuários já usam. O botão troca de palavra e
   * aparece um "cancelar" ao lado.
   * ⚠️ Com 180 locais, o formulário está fora da tela quando se clica em
   * "editar" na linha 90: por isso ele é trazido para a vista.
   */
  const [editando, setEditando] = useState<{ aba: Aba; id: number | string } | null>(null);
  const editandoAqui = editando?.aba === aba ? editando : null;

  function limparFormularios() {
    setNovoSetor("");
    setNovoLocal({ nome: "", tipo: "SECO" });
    setNovaCategoria({ nome: "", id_pai: "", tipo: "INSUMO" });
    setNovaUm({ sigla: "", nome: "", grandeza: "UNIDADE", fator_base: "1" });
  }

  function comecarEdicao(id: number | string, preencher: () => void) {
    setEditando({ aba, id });
    preencher();
    // ⚠️ `requestAnimationFrame` e não `scrollIntoView` direto: o formulário só
    // ganha os valores no render seguinte, e rolar antes disso leva a pessoa a
    // um formulário que ainda está vazio.
    requestAnimationFrame(() =>
      document.getElementById("form-apoio")?.scrollIntoView({ block: "center" }));
  }

  function cancelarEdicao() {
    setEditando(null);
    limparFormularios();
  }

  // ⚠️ Trocar de aba com uma edição aberta deixaria o formulário da outra aba
  // preenchido com os dados desta — e o botão dizendo "Salvar" para um registro
  // que não está mais na tela.
  useEffect(() => {
    if (editando && editando.aba !== aba) cancelarEdicao();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aba]);

  /**
   * 🔑 **A lista abre com o que está EM USO.** O inativo continuava aparecendo,
   * só com a opacidade baixa — e numa base com histórico ele é a maioria: quem
   * procura um local para corrigir percorre uma lista cheia de coisa que não se
   * usa mais. É o mesmo corte de Produtos, com a mesma caixinha.
   * ⚠️ **O corte é do SERVIDOR** — os quatro endpoints já tinham o parâmetro, e
   * o padrão deles sempre foi "só os ativos": era esta tela que pedia todos.
   * ⚠️ Desativar não é apagar, aqui: cadastro com uso vira inativo e continua
   * respondendo pelo histórico. Por isso a caixinha, e não um filtro escondido.
   */
  const carregar = useCallback(async () => {
    try {
      const q = mostrarInativos ? "true" : "false";
      const [s, l, c, u] = await Promise.all([
        api.get<Setor[]>(`/setores?incluir_inativos=${q}`),
        api.get<Local[]>(`/locais?incluir_inativos=${q}`),
        api.get<Categoria[]>(`/categorias?incluir_inativas=${q}`),
        api.get<UnidadeMedida[]>(`/unidades-medida?incluir_inativas=${q}`),
      ]);
      setSetores(s);
      setLocais(l);
      setCategorias(c);
      setUms(u);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [mostrarInativos]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function acao(fn: () => Promise<unknown>, mensagem: string) {
    setErro("");
    try {
      await fn();
      aviso.sucesso(mensagem);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível concluir");
    }
  }

  // O total é o da aba VISÍVEL: um rodapé dizendo "de 180" numa lista de 10
  // unidades de medida seria pior que rodapé nenhum.
  const quantosNaAba =
    aba === "setores"
      ? setores?.length
      : aba === "locais"
        ? locais?.length
        : aba === "categorias"
          ? categorias?.length
          : aba === "unidades"
            ? ums?.length
            : 0;
  const { setTotal } = pag;
  useEffect(() => {
    setTotal(quantosNaAba ?? 0);
  }, [quantosNaAba, setTotal]);

  const podeAba = (a: Aba) => pode(ABAS.find((x) => x.id === a)!.chave);
  const atual = ABAS.find((a) => a.id === aba)!;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Cadastros</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
          Tabelas de apoio
        </h1>
        {/* O título não diz o que tem dentro, e "tabelas de apoio" não é o nome
            de nada que alguém procura: quem precisa do local de estoque procura
            "local de estoque". Por isso a lista vem escrita aqui. */}
        <p className="mt-1 max-w-[68ch] text-suave">
          <b className="font-semibold text-tinta">
            Setores, locais de estoque, categorias e unidades de medida
          </b>{" "}
          — as quatro listas que o cadastro de produto usa. Mexer aqui muda como o estoque e o
          CMV vão se organizar depois: vale acertar antes de cadastrar o primeiro insumo.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <nav className="flex flex-wrap gap-1 border-b border-linha">
        {ABAS.map((a) => (
          <button
            key={a.id}
            onClick={() => {
              setAba(a.id);
            }}
            className={`-mb-px border-b-2 px-3 py-2 text-[14.5px] ${
              aba === a.id
                ? "border-erva font-semibold text-erva"
                : "border-transparent text-suave hover:text-tinta"
            }`}
          >
            {a.nome}
          </button>
        ))}
      </nav>

      <div className="-mt-3 flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-[70ch] text-[14px] text-suave">{atual.explica}</p>
        {/* Mesma caixinha de Produtos, no mesmo lugar do olho: quem procura um
            cadastro antigo sabe onde ligá-la. */}
        <label className="flex shrink-0 items-center gap-2 text-[14px] text-suave">
          <input
            type="checkbox"
            checked={mostrarInativos}
            onChange={(e) => setMostrarInativos(e.target.checked)}
          />
          mostrar inativos
        </label>
      </div>

      {/* ---------------------------------------------------------- setores */}
      {/* ⚠️ A marca só aparece com o envio LIGADO. Um controle para um recurso
          desligado é ruído: quem cadastra um setor hoje não tem o que decidir
          sobre um envio que não acontece. O valor gravado NÃO se perde quando o
          envio é desligado — desligar não é desmarcar. */}
      {aba === "setores" && (
        <Cartao titulo="Setores">
          {!setores ? (
            <Carregando />
          ) : (
            <>
              {podeAba("setores") && (
                <form
                  id="form-apoio"
                  className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end"
                  onSubmit={(e: FormEvent) => {
                    e.preventDefault();
                    const alvo = editandoAqui;
                    void acao(async () => {
                      if (alvo) await api.put(`/setores/${alvo.id}`, { nome: novoSetor });
                      else await api.post("/setores", { nome: novoSetor });
                      setNovoSetor("");
                      setEditando(null);
                    }, alvo ? "Setor corrigido." : "Setor criado.");
                  }}
                >
                  <label className="min-w-0 flex-1">
                    <span className="rotulo">{editandoAqui ? "Corrigir setor" : "Novo setor"}</span>
                    <input
                      className="campo mt-1.5"
                      required
                      minLength={2}
                      value={novoSetor}
                      onChange={(e) => setNovoSetor(e.target.value)}
                    />
                  </label>
                  <button className="btn btn-secundario" type="submit">
                    {editandoAqui ? "Salvar" : "Adicionar"}
                  </button>
                  {editandoAqui && (
                    <button type="button" className="link-acao" onClick={cancelarEdicao}>
                      cancelar
                    </button>
                  )}
                </form>
              )}
              {/* A lista pinta o próprio fundo para separar as linhas; vazia, ela
                  virava um bloco cinza sem conteúdo. Sem itens, não há lista. */}
              {!setores.length && <Vazio>Nenhum setor.</Vazio>}
              <ul className="flex flex-col gap-px bg-linha empty:hidden">
                {fatiar(setores, pag).map((s) => (
                  <li
                    key={s.id}
                    className={`flex items-center justify-between gap-3 bg-superficie py-2.5 ${
                      s.ativo ? "" : "opacity-55"
                    }`}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="font-medium">{s.nome}</span>
                      {enviaAoPdv && s.integrado_pdv && (
                        <Etiqueta cor="erva">PDV</Etiqueta>
                      )}
                    </span>
                    {podeAba("setores") && (
                      <span className="flex gap-3">
                        {enviaAoPdv && (
                          <button
                            className="link-acao"
                            onClick={() =>
                              acao(
                                () =>
                                  api.put(`/setores/${s.id}`, {
                                    integrado_pdv: !s.integrado_pdv,
                                  }),
                                s.integrado_pdv
                                  ? "Setor fora do envio ao PDV."
                                  : "Setor entra no envio ao PDV.",
                              )
                            }
                          >
                            {s.integrado_pdv ? "tirar do PDV" : "integrar ao PDV"}
                          </button>
                        )}
                        <button
                          className="link-acao"
                          onClick={() => comecarEdicao(s.id, () => setNovoSetor(s.nome))}
                        >
                          editar
                        </button>
                        <button
                          className="link-acao"
                          onClick={() =>
                            acao(
                              () => api.put(`/setores/${s.id}`, { ativo: !s.ativo }),
                              s.ativo ? "Setor desativado." : "Setor reativado.",
                            )
                          }
                        >
                          {s.ativo ? "desativar" : "reativar"}
                        </button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <Paginacao p={pag} rotulo="setor(es)" />

            </>
          )}
        </Cartao>
      )}

      {/* ---------------------------------------------------------- locais */}
      {aba === "locais" && (
        <Cartao titulo="Locais de estoque">
          {!locais ? (
            <Carregando />
          ) : (
            <>
              {podeAba("locais") && (
                <form
                  id="form-apoio"
                  className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end"
                  onSubmit={(e: FormEvent) => {
                    e.preventDefault();
                    const alvo = editandoAqui;
                    void acao(async () => {
                      if (alvo) await api.put(`/locais/${alvo.id}`, novoLocal);
                      else await api.post("/locais", novoLocal);
                      setNovoLocal({ nome: "", tipo: "SECO" });
                      setEditando(null);
                    }, alvo ? "Local corrigido." : "Local criado.");
                  }}
                >
                  <label className="min-w-0 flex-1">
                    <span className="rotulo">{editandoAqui ? "Corrigir local" : "Novo local"}</span>
                    <input
                      className="campo mt-1.5"
                      required
                      minLength={2}
                      value={novoLocal.nome}
                      onChange={(e) => setNovoLocal({ ...novoLocal, nome: e.target.value })}
                    />
                  </label>
                  <label className="sm:w-[180px]">
                    <span className="rotulo">Tipo</span>
                    <select
                      className="campo mt-1.5"
                      value={novoLocal.tipo}
                      onChange={(e) => setNovoLocal({ ...novoLocal, tipo: e.target.value })}
                    >
                      {TIPOS_LOCAL.map((t) => (
                        <option key={t} value={t}>
                          {t.toLowerCase()}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button className="btn btn-secundario" type="submit">
                    {editandoAqui ? "Salvar" : "Adicionar"}
                  </button>
                  {editandoAqui && (
                    <button type="button" className="link-acao" onClick={cancelarEdicao}>
                      cancelar
                    </button>
                  )}
                </form>
              )}
              {!locais.length && <Vazio>Nenhum local de estoque.</Vazio>}
              <ul className="flex flex-col gap-px bg-linha empty:hidden">
                {fatiar(locais, pag).map((l) => (
                  <li
                    key={l.id}
                    className={`flex flex-wrap items-center justify-between gap-3 bg-superficie py-2.5 ${
                      l.ativo ? "" : "opacity-55"
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <span className="font-medium">{l.nome}</span>
                      <Etiqueta>{l.tipo.toLowerCase()}</Etiqueta>
                      {l.principal && <Etiqueta cor="erva">padrão</Etiqueta>}
                    </span>
                    {podeAba("locais") && (
                      <span className="flex gap-3">
                        <button
                          className="link-acao"
                          onClick={() =>
                            comecarEdicao(l.id, () => setNovoLocal({ nome: l.nome, tipo: l.tipo }))
                          }
                        >
                          editar
                        </button>
                        {!l.principal && l.ativo && (
                          <button
                            className="link-acao"
                            onClick={() =>
                              acao(
                                () => api.put(`/locais/${l.id}`, { principal: true }),
                                "Local padrão trocado.",
                              )
                            }
                          >
                            tornar padrão
                          </button>
                        )}
                        <button
                          className="link-acao"
                          onClick={() =>
                            acao(
                              () => api.put(`/locais/${l.id}`, { ativo: !l.ativo }),
                              l.ativo ? "Local desativado." : "Local reativado.",
                            )
                          }
                        >
                          {l.ativo ? "desativar" : "reativar"}
                        </button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <Paginacao p={pag} rotulo="local(is)" />

            </>
          )}
        </Cartao>
      )}

      {/* ---------------------------------------------------------- categorias */}
      {aba === "categorias" && (
        <Cartao titulo="Categorias">
          {!categorias ? (
            <Carregando />
          ) : (
            <>
              {podeAba("categorias") && (
                <form
                  id="form-apoio"
                  className="mb-4 grid gap-3 sm:grid-cols-[1fr_200px_160px_auto] sm:items-end"
                  onSubmit={(e: FormEvent) => {
                    e.preventDefault();
                    const alvo = editandoAqui;
                    void acao(async () => {
                      const corpo = {
                        nome: novaCategoria.nome,
                        tipo: novaCategoria.tipo,
                        id_pai: novaCategoria.id_pai ? Number(novaCategoria.id_pai) : null,
                      };
                      if (alvo) await api.put(`/categorias/${alvo.id}`, corpo);
                      else await api.post("/categorias", corpo);
                      setNovaCategoria({ nome: "", id_pai: "", tipo: "INSUMO" });
                      setEditando(null);
                    }, alvo ? "Categoria corrigida." : "Categoria criada.");
                  }}
                >
                  <Campo rotulo={editandoAqui ? "Corrigir categoria" : "Nova categoria"}>
                    <input
                      className="campo"
                      required
                      minLength={2}
                      value={novaCategoria.nome}
                      onChange={(e) => setNovaCategoria({ ...novaCategoria, nome: e.target.value })}
                    />
                  </Campo>
                  <Campo rotulo="Dentro de">
                    <select
                      className="campo"
                      value={novaCategoria.id_pai}
                      onChange={(e) =>
                        setNovaCategoria({ ...novaCategoria, id_pai: e.target.value })
                      }
                    >
                      <option value="">— raiz —</option>
                      {categorias
                        .filter((c) => c.ativo)
                        // ⚠️ Corrigindo uma categoria, ela e as filhas saem da
                        // lista de pais: dentro de si mesma seria um ciclo, e a
                        // consulta recursiva da árvore entraria em laço. Quem
                        // de fato barra é o servidor (400 com frase) — a lista
                        // só evita oferecer o que vai ser recusado.
                        .filter((c) => {
                          const alvo = editandoAqui
                            && categorias.find((x) => x.id === editandoAqui.id);
                          if (!alvo) return true;
                          return c.id !== alvo.id && !c.caminho.startsWith(`${alvo.caminho} `);
                        })
                        .map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.caminho}
                          </option>
                        ))}
                    </select>
                  </Campo>
                  <Campo rotulo="Tipo">
                    <select
                      className="campo"
                      value={novaCategoria.tipo}
                      onChange={(e) => setNovaCategoria({ ...novaCategoria, tipo: e.target.value })}
                    >
                      {TIPOS_CATEGORIA.map((t) => (
                        <option key={t} value={t}>
                          {t.toLowerCase()}
                        </option>
                      ))}
                    </select>
                  </Campo>
                  <div className="flex items-center gap-3">
                    <button className="btn btn-secundario" type="submit">
                      {editandoAqui ? "Salvar" : "Adicionar"}
                    </button>
                    {editandoAqui && (
                      <button type="button" className="link-acao" onClick={cancelarEdicao}>
                        cancelar
                      </button>
                    )}
                  </div>
                </form>
              )}
              {!categorias.length && <Vazio>Nenhuma categoria.</Vazio>}
              <ul className="flex flex-col gap-px bg-linha empty:hidden">
                {fatiar(categorias, pag).map((c) => (
                  <li
                    key={c.id}
                    className={`flex flex-wrap items-center justify-between gap-3 bg-superficie py-2.5 ${
                      c.ativo ? "" : "opacity-55"
                    }`}
                    style={{ paddingLeft: `${c.nivel * 20}px` }}
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{c.nome}</span>
                      <Etiqueta>{c.tipo.toLowerCase()}</Etiqueta>
                      {!!c.produtos && <Etiqueta cor="erva">{c.produtos} produto(s)</Etiqueta>}
                      {enviaAoPdv && c.integrado_pdv && <Etiqueta cor="erva">PDV</Etiqueta>}
                    </span>
                    {podeAba("categorias") && (
                      <span className="flex gap-3">
                        <button
                          className="link-acao"
                          onClick={() =>
                            comecarEdicao(c.id, () =>
                              setNovaCategoria({
                                nome: c.nome,
                                // ⚠️ O pai vem como TEXTO: o `<select>` compara
                                // por string, e um número aqui deixaria a
                                // categoria-mãe aparecendo como "— raiz —".
                                id_pai: c.id_pai ? String(c.id_pai) : "",
                                tipo: c.tipo,
                              }))
                          }
                        >
                          editar
                        </button>
                        {enviaAoPdv && (
                          <button
                            className="link-acao"
                            onClick={() =>
                              acao(
                                () =>
                                  api.put(`/categorias/${c.id}`, {
                                    integrado_pdv: !c.integrado_pdv,
                                  }),
                                c.integrado_pdv
                                  ? "Categoria fora do envio ao PDV."
                                  : "Categoria entra no envio ao PDV.",
                              )
                            }
                          >
                            {c.integrado_pdv ? "tirar do PDV" : "integrar ao PDV"}
                          </button>
                        )}
                        <button
                          className="link-acao"
                          onClick={() =>
                            acao(
                              () => api.put(`/categorias/${c.id}`, { ativo: !c.ativo }),
                              c.ativo ? "Categoria desativada." : "Categoria reativada.",
                            )
                          }
                        >
                          {c.ativo ? "desativar" : "reativar"}
                        </button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
              <Paginacao p={pag} rotulo="categoria(s)" />

            </>
          )}
        </Cartao>
      )}

      {/* ---------------------------------------------------------- unidades */}
      {/* ⚠️ Em componente próprio: esta tela já é longa, e o editor de grupos
          tem estado seu (o formulário de edição abre em linha). */}
      {aba === "grupos-cmv" && (
        <Cartao titulo="Grupos do CMV">
          <GruposCmv />
        </Cartao>
      )}

      {aba === "unidades" && (
        <Cartao titulo="Unidades de medida">
          {!ums ? (
            <Carregando />
          ) : (
            <>
              {podeAba("unidades") && (
                <form
                  id="form-apoio"
                  className="mb-4 grid gap-3 sm:grid-cols-[110px_1fr_180px_140px_auto] sm:items-end"
                  onSubmit={(e: FormEvent) => {
                    e.preventDefault();
                    const alvo = editandoAqui;
                    void acao(async () => {
                      if (alvo) {
                        // ⚠️ A SIGLA não vai no corpo: ela é a chave primária, e
                        // dela dependem produto, ficha, item de nota e razão.
                        // Renomear seria repontar tudo isso — quem quer outra
                        // sigla cria outra unidade.
                        await api.put(`/unidades-medida/${alvo.id}`, {
                          nome: novaUm.nome,
                          grandeza: novaUm.grandeza,
                          fator_base: Number(novaUm.fator_base),
                        });
                      } else {
                        await api.post("/unidades-medida", {
                          ...novaUm,
                          fator_base: Number(novaUm.fator_base),
                        });
                      }
                      setNovaUm({ sigla: "", nome: "", grandeza: "UNIDADE", fator_base: "1" });
                      setEditando(null);
                    }, alvo ? "Unidade corrigida." : "Unidade criada.");
                  }}
                >
                  <Campo
                    rotulo="Sigla"
                    dica={editandoAqui ? "não muda: é a chave" : undefined}
                  >
                    <input
                      className="campo mono"
                      required
                      maxLength={6}
                      disabled={!!editandoAqui}
                      value={novaUm.sigla}
                      onChange={(e) => setNovaUm({ ...novaUm, sigla: e.target.value.toUpperCase() })}
                    />
                  </Campo>
                  <Campo rotulo="Nome">
                    <input
                      className="campo"
                      required
                      minLength={2}
                      value={novaUm.nome}
                      onChange={(e) => setNovaUm({ ...novaUm, nome: e.target.value })}
                    />
                  </Campo>
                  <Campo rotulo="Grandeza">
                    <select
                      className="campo"
                      value={novaUm.grandeza}
                      onChange={(e) => setNovaUm({ ...novaUm, grandeza: e.target.value })}
                    >
                      {GRANDEZAS.map((g) => (
                        <option key={g} value={g}>
                          {g.toLowerCase()}
                        </option>
                      ))}
                    </select>
                  </Campo>
                  <Campo rotulo="Fator base">
                    <input
                      className="campo mono"
                      type="number"
                      step="0.000001"
                      min="0.000001"
                      value={novaUm.fator_base}
                      onChange={(e) => setNovaUm({ ...novaUm, fator_base: e.target.value })}
                    />
                  </Campo>
                  <div className="flex items-center gap-3">
                    <button className="btn btn-secundario" type="submit">
                      {editandoAqui ? "Salvar" : "Adicionar"}
                    </button>
                    {editandoAqui && (
                      <button type="button" className="link-acao" onClick={cancelarEdicao}>
                        cancelar
                      </button>
                    )}
                  </div>
                </form>
              )}
              <div className="overflow-x-auto">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Sigla</th>
                      <th>Nome</th>
                      <th>Grandeza</th>
                      <th className="num">Fator base</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {fatiar(ums, pag).map((u) => (
                      <tr key={u.sigla} className={u.ativo ? "" : "opacity-55"}>
                        <td className="mono font-semibold">{u.sigla}</td>
                        <td>{u.nome}</td>
                        <td className="text-suave">{u.grandeza.toLowerCase()}</td>
                        <td className="num">{Number(u.fator_base)}</td>
                        <td className="text-right">
                          {podeAba("unidades") && (
                            <span className="flex justify-end gap-3">
                            <button
                              className="link-acao"
                              onClick={() =>
                                comecarEdicao(u.sigla, () =>
                                  setNovaUm({
                                    sigla: u.sigla,
                                    nome: u.nome,
                                    grandeza: u.grandeza,
                                    fator_base: String(u.fator_base),
                                  }))
                              }
                            >
                              editar
                            </button>
                            <button
                              className="link-acao"
                              onClick={() =>
                                acao(
                                  () =>
                                    api.put(`/unidades-medida/${u.sigla}`, { ativo: !u.ativo }),
                                  u.ativo ? "Unidade desativada." : "Unidade reativada.",
                                )
                              }
                            >
                              {u.ativo ? "desativar" : "reativar"}
                            </button>
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              <Paginacao p={pag} rotulo="unidade(s)" />
              </div>

            </>
          )}
        </Cartao>
      )}
    </div>
  );
}
