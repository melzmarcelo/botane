"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import CabecalhoTela from "@/components/cabecalho-tela";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta, Modal, Vazio } from "@/components/ui";
import { useSessao } from "@/lib/sessao";
import {
  Catalogo,
  Gravar,
  Opcoes,
  ROTULO_SITUACAO,
  Situacao,
  atualizar,
  criar,
  excluir,
  listar,
  opcoes as pedirOpcoes,
} from "@/lib/catalogos";

/**
 * O cadastro de catálogos — a capa do que a casa publica para o cliente.
 *
 * 🔑 **Pedido do dono (21/09/2026):** *"vamos iniciar pelo cadastro de
 * catálogos. Onde teremos o cabeçalho do catálogo, origem — neste momento
 * somente vamos ter PDF —, o nome dele no site do cliente, o período de
 * publicação, a situação: rascunho, ativo, inativo."*
 *
 * 🔑 **É do site de RESERVAS** (correção do dono no mesmo dia). A origem é um
 * PDF importado, e a tela só existe com o módulo de Reservas ligado nesta
 * loja — o menu a esconde e as rotas recusam.
 *
 * ⚠️ **É a CAPA, e só ela.** Os itens do catálogo são a próxima fatia, e a tela
 * diz isso em vez de deixar a pessoa procurando onde se acrescenta um prato.
 *
 * 🔑 **"No ar" é uma coluna PRÓPRIA, separada da situação.** Um catálogo ATIVO
 * cujo período terminou ontem não está publicado — mostrar os dois como iguais
 * faria a casa procurar no site um cardápio que saiu do ar sozinho. Quem decide
 * é o servidor, porque é ele que sabe que dia é hoje na loja.
 */
const dia = (d: string | null) =>
  d ? new Date(d + "T12:00").toLocaleDateString("pt-BR") : null;

/** O período em palavras — as duas pontas são opcionais e querem dizer coisas
 *  diferentes, então a frase muda com o que existe. "—" em cada ponta separada
 *  faria ler "de nada até nada" para o cardápio permanente da casa. */
function periodoEmPalavras(c: Catalogo): string {
  const de = dia(c.publica_de);
  const ate = dia(c.publica_ate);
  if (de && ate) return `${de} a ${ate}`;
  if (de) return `de ${de}, sem prazo`;
  if (ate) return `até ${ate}`;
  return "sem período — vale enquanto estiver ativo";
}

/**
 * ⚠️ **Sem `origem` aqui, e isto custou uma rodada da bateria.** A primeira
 * versão trazia `origem: "PDV"` escrito — a sigla errada —, e o `<select>`
 * **mentiu**: o valor não estava entre as opções vindas do servidor, então o
 * navegador MOSTRAVA "PDF" (a primeira) enquanto o estado continuava "PDV". A
 * tela dizia uma coisa e o POST mandava outra, e o 422 falava de uma origem que
 * ninguém tinha escolhido.
 * 🔑 **Quem diz qual é a origem padrão é o SERVIDOR**, pela primeira de
 * `/catalogos/opcoes`. Uma sigla escrita aqui é a segunda cópia da lista — e
 * esta já provou que diverge calada.
 */
const VAZIO: Gravar = {
  nome: "",
  publica_de: "",
  publica_ate: "",
  situacao: "RASCUNHO",
  observacao: "",
};

export default function PaginaCatalogos() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeEditar = pode("catalogos.editar");

  const [lista, setLista] = useState<Catalogo[] | null>(null);
  const [op, setOp] = useState<Opcoes | null>(null);
  const [filtro, setFiltro] = useState<Situacao | "">("");
  const [erro, setErro] = useState("");
  // `null` = janela fechada; `0` = catálogo novo; id = editando aquele.
  const [editando, setEditando] = useState<number | null>(null);
  const [f, setF] = useState<Gravar>(VAZIO);
  const [salvando, setSalvando] = useState(false);
  const [apagando, setApagando] = useState<Catalogo | null>(null);

  const carregar = useCallback(async () => {
    setErro("");
    try {
      setLista(await listar(filtro));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, [filtro]);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  // ⚠️ O vocabulário é pedido UMA vez, e ao servidor: origem e situação são
  // listas dele, e uma cópia aqui divergiria calada no dia da segunda origem.
  useEffect(() => {
    pedirOpcoes().then(setOp).catch(() => setOp(null));
  }, []);

  function abrir(c?: Catalogo) {
    setEditando(c ? c.id : 0);
    setF(
      c
        ? {
            nome: c.nome,
            origem: c.origem,
            publica_de: c.publica_de ?? "",
            publica_ate: c.publica_ate ?? "",
            situacao: c.situacao,
            observacao: c.observacao ?? "",
          }
        // ⚠️ A origem do catálogo NOVO vem do servidor, nunca escrita aqui.
        : { ...VAZIO, origem: op?.origens[0] },
    );
  }

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    try {
      // ⚠️ **Data vazia vira `null`, não `""`.** O servidor lê nulo como "sem
      // prazo"; string vazia seria uma data inválida e o 422 falaria de
      // formato, não da decisão que a pessoa tomou.
      const corpo: Gravar = {
        ...f,
        publica_de: f.publica_de || null,
        publica_ate: f.publica_ate || null,
        observacao: f.observacao || null,
      };
      const r = editando ? await atualizar(editando, corpo) : await criar(corpo);
      aviso.sucesso(
        editando ? `Catálogo “${r.nome}” salvo.` : `Catálogo “${r.nome}” criado.`,
      );
      setEditando(null);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function confirmarExclusao() {
    if (!apagando) return;
    try {
      const r = await excluir(apagando.id);
      aviso.sucesso(r.message);
      setApagando(null);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível excluir");
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        caminho="Reservas"
        titulo={<>Catálogos</>}
        explica={
          <>
            A capa do que o site de reservas apresenta ao cliente: o nome que aparece
            lá, de quando até quando vale e se está no ar. Hoje a origem é um PDF; os itens
            de cada catálogo vêm a seguir.
          </>
        }
        acoes={
          <div className="nao-imprimir flex flex-wrap items-end gap-2">
            <label>
              <span className="rotulo-campo">Situação</span>
              {/* ⚠️ A largura mora no INVÓLUCRO: `.campo` tem `width:100%` fora
                  de camada e ganha da utilitária do Tailwind. */}
              <span className="mt-1.5 block w-[160px]">
                <select
                  className="campo"
                  value={filtro}
                  onChange={(e) => setFiltro(e.target.value as Situacao | "")}
                >
                  <option value="">Todas</option>
                  {(op?.situacoes ?? []).map((s) => (
                    <option key={s} value={s}>
                      {ROTULO_SITUACAO[s]}
                    </option>
                  ))}
                </select>
              </span>
            </label>
            {podeEditar && (
              <button type="button" className="btn btn-primario" onClick={() => abrir()}>
                Novo catálogo
              </button>
            )}
          </div>
        }
      />

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      <Cartao
        titulo="Os catálogos desta loja"
        descricao="Primeiro o que está no ar, depois o que ainda vai entrar."
      >
        {!lista ? (
          <Carregando />
        ) : !lista.length ? (
          <Vazio>
            {filtro
              ? "Nenhum catálogo nesta situação."
              : "Nenhum catálogo ainda. O primeiro nasce como rascunho — dá para nomeá-lo e só publicar depois de conferir."}
          </Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Nome no site do cliente</th>
                  <th>Origem</th>
                  <th>Publicação</th>
                  <th>Situação</th>
                  <th>No ar hoje</th>
                  {podeEditar && <th></th>}
                </tr>
              </thead>
              <tbody>
                {lista.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <span className="font-medium">{c.nome}</span>
                      {c.observacao && (
                        <span className="block text-[12.5px] text-suave">{c.observacao}</span>
                      )}
                    </td>
                    <td className="text-[13px] text-suave">{c.origem}</td>
                    <td className="text-[13px]">{periodoEmPalavras(c)}</td>
                    <td>
                      <Etiqueta
                        cor={
                          c.situacao === "ATIVO"
                            ? "erva"
                            : c.situacao === "RASCUNHO"
                              ? "alerta"
                              : "neutro"
                        }
                      >
                        {ROTULO_SITUACAO[c.situacao]}
                      </Etiqueta>
                    </td>
                    {/* 🔑 A coluna que responde "o cliente está vendo isto?".
                        Ativo com período vencido aparece como NÃO. */}
                    <td className="text-[13px]">
                      {c.publicado_hoje ? (
                        <span className="font-semibold text-erva">no ar</span>
                      ) : (
                        <span className="text-suave">não</span>
                      )}
                    </td>
                    {podeEditar && (
                      <td className="text-right whitespace-nowrap">
                        <button type="button" className="link-acao" onClick={() => abrir(c)}>
                          alterar
                        </button>
                        {/* ⚠️ Excluir só aparece no RASCUNHO. O resto se inativa
                            — alguém leu aquele cardápio, e apagá-lo tira do
                            sistema o que a casa publicou. O servidor recusa de
                            todo jeito; aqui o botão nem se oferece. */}
                        {c.situacao === "RASCUNHO" && (
                          <button
                            type="button"
                            className="link-acao link-acao-erro ml-3"
                            onClick={() => setApagando(c)}
                          >
                            excluir
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      {editando !== null && (
        <Modal
          titulo={editando ? "Alterar catálogo" : "Novo catálogo"}
          descricao="O cabeçalho — os itens vêm depois."
          aoFechar={() => setEditando(null)}
          largura="560px"
          rodape={
            <div className="flex justify-end gap-2">
              <button type="button" className="btn btn-secundario" onClick={() => setEditando(null)}>
                Cancelar
              </button>
              <button
                type="submit"
                form="form-catalogo"
                className="btn btn-primario"
                aria-busy={salvando}
                disabled={salvando}
              >
                {salvando ? "Salvando…" : "Salvar"}
              </button>
            </div>
          }
        >
          <form id="form-catalogo" onSubmit={salvar} className="flex flex-col gap-4">
            <Campo
              rotulo="Nome no site do cliente"
              dica="É o que o cliente lê. Quem opera reconhece pelo mesmo nome."
            >
              <input
                className="campo"
                id="catalogo-nome"
                required
                minLength={2}
                maxLength={120}
                placeholder="Cardápio de verão"
                value={f.nome ?? ""}
                onChange={(e) => setF({ ...f, nome: e.target.value })}
              />
            </Campo>

            <div className="grid gap-4 sm:grid-cols-2">
              <Campo rotulo="Origem" dica="Hoje só PDF — o arquivo que o site apresenta.">
                {/* ⚠️ **`value` sempre entre as `options`.** Um valor de fora
                    faz o navegador exibir a primeira sem mexer no estado — a
                    tela mostra uma coisa e manda outra, e foi assim que "PDV"
                    chegou ao servidor com "PDF" na tela. */}
                <select
                  className="campo"
                  id="catalogo-origem"
                  value={f.origem ?? op?.origens[0] ?? ""}
                  onChange={(e) => setF({ ...f, origem: e.target.value })}
                >
                  {(op?.origens ?? []).map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </Campo>
              <Campo rotulo="Situação" dica="Rascunho não aparece para o cliente.">
                <select
                  className="campo"
                  id="catalogo-situacao"
                  value={f.situacao ?? "RASCUNHO"}
                  onChange={(e) => setF({ ...f, situacao: e.target.value as Situacao })}
                >
                  {(op?.situacoes ?? []).map((s) => (
                    <option key={s} value={s}>
                      {ROTULO_SITUACAO[s]}
                    </option>
                  ))}
                </select>
              </Campo>
            </div>

            {/* ⚠️ **As duas pontas são opcionais, e a dica diz o que o vazio
                quer dizer.** Sem isso a pessoa preenche "até" com uma data
                inventada para o cardápio permanente da casa. */}
            <div className="grid gap-4 sm:grid-cols-2">
              <Campo rotulo="Publica de" dica="Em branco: vale desde já.">
                <input
                  className="campo"
                  id="catalogo-de"
                  type="date"
                  value={f.publica_de ?? ""}
                  onChange={(e) => setF({ ...f, publica_de: e.target.value })}
                />
              </Campo>
              <Campo rotulo="Publica até" dica="Em branco: vale sem prazo.">
                <input
                  className="campo"
                  id="catalogo-ate"
                  type="date"
                  value={f.publica_ate ?? ""}
                  onChange={(e) => setF({ ...f, publica_ate: e.target.value })}
                />
              </Campo>
            </div>

            <Campo rotulo="Observação" dica="Para a casa, não para o cliente.">
              <input
                className="campo"
                id="catalogo-observacao"
                maxLength={500}
                value={f.observacao ?? ""}
                onChange={(e) => setF({ ...f, observacao: e.target.value })}
              />
            </Campo>
          </form>
        </Modal>
      )}

      {apagando && (
        <Confirmacao
          titulo={`Excluir “${apagando.nome}”?`}
          rotuloConfirmar="Excluir"
          perigo
          aoConfirmar={confirmarExclusao}
          aoCancelar={() => setApagando(null)}
        >
          {/* ⚠️ A frase diz o que a ação FAZ, não só "tem certeza" — regra da
              casa para toda confirmação. */}
          Ele ainda é rascunho, então nunca esteve no ar. Isto não se desfaz.
        </Confirmacao>
      )}
    </div>
  );
}
