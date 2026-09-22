"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ErroApi, urlArquivo } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Aviso, Campo, Carregando, Cartao, Confirmacao, Etiqueta, Modal, Vazio } from "@/components/ui";
import CabecalhoTela from "@/components/cabecalho-tela";
import * as cat from "@/lib/catalogos";

/**
 * O cardápio montado aqui dentro: categorias, subcategorias e produtos.
 *
 * 🔑 **Pedido do dono (22/09/2026):** *"quando for esta origem, ao listar os
 * catálogos, ao clicar sobre vai abrir uma nova página para configuração.
 * Neste, podemos criar Categorias (exemplo: Menu Principal) e suas
 * SubCategorias (exemplo: Pra Dividir), cada item terá o Nome, Descrição e uma
 * foto. Após isto, podemos vincular os produtos disponíveis no PDV para a
 * subcategoria. Somente produtos ativos."*
 *
 * ⚠️ **Página própria, e não uma janela.** São três níveis que se olham juntos
 * — a categoria, o que ela divide e o que está pendurado —, e isso não cabe num
 * modal sem virar rolagem dentro de rolagem. A lista de catálogos continua
 * sendo o cadastro da CAPA; aqui é o miolo.
 */
export default function ConfigurarCatalogo() {
  const { id } = useParams<{ id: string }>();
  const idCatalogo = Number(id);
  const { pode } = useSessao();
  const podeEditar = pode("catalogos.editar");
  const aviso = useAviso();

  const [capa, setCapa] = useState<cat.Catalogo | null>(null);
  const [conteudo, setConteudo] = useState<cat.Conteudo | null>(null);
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    try {
      const [c, k] = await Promise.all([
        cat.obter(idCatalogo),
        cat.conteudo(idCatalogo),
      ]);
      setCapa(c);
      setConteudo(k);
      setErro("");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    } finally {
      setCarregando(false);
    }
  }, [idCatalogo]);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  // ------------------------------------------------------------- seções ---
  /** A janela de nome/descrição serve categoria E subcategoria: os campos são
   *  os mesmos, e duas janelas iguais divergiriam na primeira correção. */
  const [editando, setEditando] = useState<{
    tipo: cat.TipoDeSecao;
    /** Nulo = criando. */
    id: number | null;
    /** A quem ela pertence: o catálogo (categoria) ou a categoria (subcategoria). */
    idPai: number;
    nome: string;
    descricao: string;
    ordem: string;
  } | null>(null);
  const [salvando, setSalvando] = useState(false);

  async function salvarSecao() {
    if (!editando) return;
    const corpo = {
      nome: editando.nome.trim(),
      descricao: editando.descricao.trim() || null,
      ordem: Number(editando.ordem || 0),
    };
    setSalvando(true);
    try {
      if (editando.tipo === "categoria") {
        if (editando.id) await cat.atualizarCategoria(editando.id, corpo);
        else await cat.criarCategoria(editando.idPai, corpo);
      } else if (editando.id) {
        await cat.atualizarSubcategoria(editando.id, corpo);
      } else {
        await cat.criarSubcategoria(editando.idPai, corpo);
      }
      setEditando(null);
      await recarregar();
      aviso.sucesso(editando.id ? "Alterado." : "Criado.");
    } catch (e) {
      aviso.erro(e instanceof ErroApi ? e.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  /** ⚠️ Apagar leva subcategorias e produtos junto — por isso confirma, e a
   *  frase diz QUANTOS itens vão embora. */
  const [apagando, setApagando] = useState<{
    tipo: cat.TipoDeSecao;
    id: number;
    nome: string;
    itens: number;
  } | null>(null);

  async function confirmarApagar() {
    if (!apagando) return;
    try {
      if (apagando.tipo === "categoria") await cat.excluirCategoria(apagando.id);
      else await cat.excluirSubcategoria(apagando.id);
      setApagando(null);
      await recarregar();
      aviso.sucesso("Removido.");
    } catch (e) {
      aviso.erro(e instanceof ErroApi ? e.message : "Não foi possível remover");
    }
  }

  // -------------------------------------------------------------- fotos ---
  const seletorDaFoto = useRef<HTMLInputElement>(null);
  const [alvoDaFoto, setAlvoDaFoto] = useState<{
    tipo: cat.TipoDeSecao;
    id: number;
  } | null>(null);
  const [enviandoFoto, setEnviandoFoto] = useState(false);

  async function enviarFoto(arquivo: File | undefined) {
    if (!arquivo || !alvoDaFoto) return;
    setEnviandoFoto(true);
    try {
      await cat.enviarFotoDaSecao(alvoDaFoto.tipo, alvoDaFoto.id, arquivo);
      await recarregar();
      aviso.sucesso("Foto atualizada.");
    } catch (e) {
      aviso.erro(e instanceof ErroApi ? e.message : "Não foi possível enviar");
    } finally {
      setEnviandoFoto(false);
      setAlvoDaFoto(null);
      // ⚠️ Zera o valor: sem isto, escolher o MESMO arquivo de novo — que é o
      // que se faz depois de um erro — não dispara `change`.
      if (seletorDaFoto.current) seletorDaFoto.current.value = "";
    }
  }

  async function tirarFoto(tipo: cat.TipoDeSecao, idSecao: number) {
    try {
      await cat.removerFotoDaSecao(tipo, idSecao);
      await recarregar();
      aviso.sucesso("Foto removida.");
    } catch (e) {
      aviso.erro(e instanceof ErroApi ? e.message : "Não foi possível remover");
    }
  }

  // --------------------------------------------------------- recolher -----
  /**
   * As seções fechadas.
   *
   * 🔑 **Pedido do dono (22/09/2026):** *"permitir recolher a categoria e
   * subcategoria para a tela não ficar tão longa."*
   * ⚠️ **Nascem ABERTAS.** Um cardápio que abre todo fechado esconde o que a
   * pessoa veio conferir, e obriga um clique por seção antes de qualquer
   * trabalho. Quem quer a tela curta recolhe — e a escolha fica de pé enquanto
   * a tela estiver aberta, inclusive depois de salvar uma seção.
   */
  const [fechadas, setFechadas] = useState<Set<string>>(new Set());
  const chaveDa = (tipo: cat.TipoDeSecao, id: number) => `${tipo}-${id}`;
  const estaFechada = (tipo: cat.TipoDeSecao, id: number) =>
    fechadas.has(chaveDa(tipo, id));
  function alternar(tipo: cat.TipoDeSecao, id: number) {
    setFechadas((atual) => {
      const nova = new Set(atual);
      const k = chaveDa(tipo, id);
      if (nova.has(k)) nova.delete(k);
      else nova.add(k);
      return nova;
    });
  }
  /** Recolher tudo de uma vez — o atalho de quem veio só conferir a estrutura. */
  function recolherTudo(fechar: boolean) {
    if (!fechar) return setFechadas(new Set());
    const todas = new Set<string>();
    (conteudo?.categorias ?? []).forEach((c) => {
      todas.add(chaveDa("categoria", c.id));
      c.subcategorias.forEach((sc) => todas.add(chaveDa("subcategoria", sc.id)));
    });
    setFechadas(todas);
  }

  // ----------------------------------------------------------- produtos ---
  /** Onde o produto escolhido vai ser pendurado. */
  const [pendurando, setPendurando] = useState<{
    idCategoria: number;
    idSubcategoria: number | null;
    onde: string;
  } | null>(null);
  const [busca, setBusca] = useState("");
  const [achados, setAchados] = useState<cat.ProdutoDisponivel[]>([]);
  const [procurando, setProcurando] = useState(false);

  useEffect(() => {
    if (!pendurando) return;
    let valeu = true;
    setProcurando(true);
    // ⚠️ Espera antes de consultar: digitar "café" dispararia quatro buscas, e
    // a resposta do "c" pode chegar depois da do "café" e mandar na tela.
    const t = setTimeout(() => {
      cat
        .produtosDisponiveis(busca)
        .then((r) => valeu && setAchados(r))
        .catch(() => valeu && setAchados([]))
        .finally(() => valeu && setProcurando(false));
    }, 350);
    return () => {
      valeu = false;
      clearTimeout(t);
    };
  }, [busca, pendurando]);

  async function pendurar(idProduto: number) {
    if (!pendurando) return;
    try {
      const r = await cat.vincularProduto(pendurando.idCategoria, {
        id_produto: idProduto,
        id_subcategoria: pendurando.idSubcategoria,
      });
      await recarregar();
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof ErroApi ? e.message : "Não foi possível vincular");
    }
  }

  /**
   * Sobe ou desce um produto dentro da lista dele.
   *
   * 🔑 **A lista inteira é renumerada e enviada de uma vez** (10, 20, 30…): o
   * servidor grava o que recebe, sem adivinhar. ⚠️ Trocar só os dois vizinhos
   * deixaria empates quando duas listas antigas tivessem a mesma ordem — e
   * empate na ordenação vira posição que depende do acaso da consulta.
   */
  async function mover(itens: cat.ItemDoCatalogo[], indice: number, passo: number) {
    const destino = indice + passo;
    if (destino < 0 || destino >= itens.length) return;
    const fila = [...itens];
    [fila[indice], fila[destino]] = [fila[destino], fila[indice]];
    const ordens = fila.map((i, n) => ({ id: i.id, ordem: (n + 1) * 10 }));

    // 🔑 **A tela troca as duas linhas NA HORA, e só depois avisa o servidor.**
    // ⚠️ Recarregar a árvore a cada clique custava 2,5s num cardápio de 59
    // produtos — medido. Mover um item três posições eram sete segundos de
    // espera, e no meio deles a lista pulava três vezes. O reordenar é uma
    // troca de lugar: ou a pessoa vê acontecer, ou ela clica de novo achando
    // que não pegou.
    const posicao = new Map(ordens.map((o) => [o.id, o.ordem]));
    setConteudo((atual) => {
      if (!atual) return atual;
      const trocar = (lista: cat.ItemDoCatalogo[]) =>
        lista.some((i) => posicao.has(i.id))
          ? [...lista]
              .map((i) => ({ ...i, ordem: posicao.get(i.id) ?? i.ordem }))
              .sort((a, b) => a.ordem - b.ordem)
          : lista;
      return {
        ...atual,
        categorias: atual.categorias.map((c) => ({
          ...c,
          itens: trocar(c.itens),
          subcategorias: c.subcategorias.map((sc) => ({ ...sc, itens: trocar(sc.itens) })),
        })),
      };
    });

    try {
      await cat.reordenarItens(ordens);
    } catch (e) {
      aviso.erro(e instanceof ErroApi ? e.message : "Não foi possível reordenar");
      // ⚠️ **Falhando, a tela volta ao que o SERVIDOR tem.** Deixar a ordem
      // otimista de pé seria mostrar um cardápio que não existe — e a pessoa
      // sairia achando que gravou.
      await recarregar();
    }
  }

  async function tirarProduto(idItem: number) {
    try {
      const r = await cat.desvincularProduto(idItem);
      await recarregar();
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof ErroApi ? e.message : "Não foi possível remover");
    }
  }

  if (carregando) return <Carregando />;
  if (erro) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!capa || !conteudo) return <Aviso tipo="erro">Catálogo não encontrado.</Aviso>;

  /** A lista de produtos de uma seção — a mesma para categoria e subcategoria. */
  function ListaDeItens({
    itens,
    idCategoria,
    idSubcategoria,
    onde,
  }: {
    itens: cat.ItemDoCatalogo[];
    idCategoria: number;
    idSubcategoria: number | null;
    onde: string;
  }) {
    return (
      <div className="mt-2">
        {itens.length === 0 ? (
          <p className="py-2 text-[13.5px] text-suave">Nenhum produto aqui ainda.</p>
        ) : (
          <ul className="flex flex-col gap-px bg-linha text-[14.5px]">
            {itens.map((i, n) => (
              <li
                key={i.id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-superficie py-2"
              >
                {/* A foto do PRODUTO, que vem da aba Catálogo dele. */}
                <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded border border-linha bg-superficie2">
                  {i.foto_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={urlArquivo(i.foto_url) ?? undefined}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span className="text-[10px] text-suave">sem</span>
                  )}
                </span>
                {/* 🔑 **O nome que o CLIENTE vai ler vem primeiro.** A tela
                    de configuração mostra o cardápio, não o cadastro — e quando
                    a casa escreveu um nome de vitrine, é ele que sai no site.
                    ⚠️ O nome do cadastro fica ao lado, em cinza, para quem veio
                    procurar o produto reconhecê-lo. */}
                <Link href={`/produtos/${i.id_produto}`} className="link-registro">
                  {i.nome_catalogo || i.produto}
                </Link>
                {i.nome_catalogo && (
                  <span className="text-[12.5px] text-suave">{i.produto}</span>
                )}
                <span className="mono text-[12.5px] text-suave">{i.codigo}</span>
                {/* ⚠️ **Marcado quando saiu de linha DEPOIS de entrar.** Sem
                    isto a casa publica um prato que não vende mais e só
                    descobre pelo cliente. */}
                {!i.ativo && <Etiqueta cor="alerta">produto inativo</Etiqueta>}
                {!i.informacao_adicional && (
                  <span className="text-[12.5px] text-suave">sem descrição</span>
                )}
                {podeEditar && (
                  <span className="ml-auto flex items-center gap-3">
                    {/* 🔑 **Subir e descer, não arrastar.** Arrastar é
                        agradável no mouse e ruim no toque, e esta tela também
                        se usa no celular — onde o arrasto disputa com a rolagem
                        da página. ⚠️ O primeiro não sobe e o último não desce:
                        botão que não faz nada ensina a duvidar dos outros. */}
                    <button
                      type="button"
                      className="link-acao"
                      disabled={n === 0}
                      aria-label={`subir ${i.nome_catalogo || i.produto}`}
                      onClick={() => void mover(itens, n, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="link-acao"
                      disabled={n === itens.length - 1}
                      aria-label={`descer ${i.nome_catalogo || i.produto}`}
                      onClick={() => void mover(itens, n, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="link-acao link-acao-erro"
                      onClick={() => void tirarProduto(i.id)}
                    >
                      tirar
                    </button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {podeEditar && (
          <button
            type="button"
            className="link-acao mt-2"
            onClick={() => {
              setBusca("");
              setAchados([]);
              setPendurando({ idCategoria, idSubcategoria, onde });
            }}
          >
            + pôr um produto
          </button>
        )}
      </div>
    );
  }

  /** Quantos produtos uma categoria tem, contando os das subcategorias. */
  const totalDa = (c: cat.Categoria) =>
    c.itens.length + c.subcategorias.reduce((t, s) => t + s.itens.length, 0);

  /**
   * O botão que abre e fecha uma seção.
   *
   * ⚠️ **A contagem fica NO botão.** Seção fechada sem número é uma caixa que
   * não diz o que guarda — e a pessoa abre uma por uma só para descobrir onde
   * está o que procura.
   */
  function Recolher({
    tipo,
    id,
    itens,
  }: {
    tipo: cat.TipoDeSecao;
    id: number;
    itens: number;
  }) {
    const fechada = estaFechada(tipo, id);
    return (
      <button
        type="button"
        className="link-acao"
        aria-expanded={!fechada}
        onClick={() => alternar(tipo, id)}
      >
        {fechada ? `▸ abrir (${itens})` : "▾ recolher"}
      </button>
    );
  }

  /** A moldura da foto de uma seção, com trocar e tirar. */
  function FotoDaSecao({
    tipo,
    secao,
  }: {
    tipo: cat.TipoDeSecao;
    secao: cat.Secao;
  }) {
    return (
      <div className="flex items-center gap-3">
        <span className="flex h-14 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-linha bg-superficie2">
          {secao.foto_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={urlArquivo(secao.foto_url) ?? undefined}
              alt={secao.nome}
              className="h-full w-full object-cover"
            />
          ) : (
            <span className="text-[11px] text-suave">sem foto</span>
          )}
        </span>
        {podeEditar && (
          <span className="flex flex-col gap-1">
            <button
              type="button"
              className="link-acao"
              disabled={enviandoFoto}
              onClick={() => {
                setAlvoDaFoto({ tipo, id: secao.id });
                // ⚠️ O clique no input precisa sair DEPOIS de o alvo estar no
                // estado: o `onChange` lê `alvoDaFoto`, e sem a espera ele leria
                // o valor anterior.
                setTimeout(() => seletorDaFoto.current?.click(), 0);
              }}
            >
              {secao.foto_url ? "trocar foto" : "pôr foto"}
            </button>
            {secao.foto_url && (
              <button
                type="button"
                className="link-acao link-acao-erro"
                onClick={() => void tirarFoto(tipo, secao.id)}
              >
                tirar foto
              </button>
            )}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <CabecalhoTela
        titulo={capa.nome}
        explica="O cardápio que o site de reservas mostra: as seções e os produtos de cada uma."
        acoes={
          <>
            <Link href="/catalogos" className="btn btn-secundario">
              ← catálogos
            </Link>
            {/* 🔑 O atalho de quem veio só conferir a estrutura do cardápio. */}
            {conteudo.categorias.length > 0 && (
              <button
                type="button"
                className="btn btn-secundario"
                onClick={() => recolherTudo(fechadas.size === 0)}
              >
                {fechadas.size === 0 ? "Recolher tudo" : "Abrir tudo"}
              </button>
            )}
            {podeEditar && (
              <button
                type="button"
                className="btn btn-primario"
                onClick={() =>
                  setEditando({
                    tipo: "categoria",
                    id: null,
                    idPai: idCatalogo,
                    nome: "",
                    descricao: "",
                    ordem: String((conteudo.categorias.length + 1) * 10),
                  })
                }
              >
                Nova categoria
              </button>
            )}
          </>
        }
      />

      {/* ⚠️ **O catálogo em RASCUNHO não está no ar**, e dizer isso aqui evita
          a casa montar o cardápio inteiro e achar que publicou. */}
      {capa.situacao !== "ATIVO" && (
        <Aviso tipo="info">
          Este catálogo está como <b>{cat.ROTULO_SITUACAO[capa.situacao]}</b> — o site
          ainda não o mostra. Publique em{" "}
          <Link href="/catalogos" className="text-erva underline underline-offset-2">
            Catálogos
          </Link>{" "}
          quando ele estiver pronto.
        </Aviso>
      )}

      {/* O seletor de arquivo é um só, fora da vista; quem chama é cada botão. */}
      <input
        ref={seletorDaFoto}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(e) => void enviarFoto(e.target.files?.[0])}
      />

      {conteudo.categorias.length === 0 ? (
        <Vazio>
          O cardápio está vazio. Comece por uma categoria — “Menu Principal”,
          “Bebidas”. Dentro dela vêm as subcategorias e os produtos.
        </Vazio>
      ) : (
        conteudo.categorias.map((c) => (
          <Cartao
            key={c.id}
            titulo={c.nome}
            descricao={c.descricao ?? undefined}
            acao={
              <span className="flex flex-wrap items-center gap-3">
                {/* 🔑 **Recolher vale para quem só LÊ também** — está fora do
                    `podeEditar`: a tela longa incomoda igual. */}
                <Recolher tipo="categoria" id={c.id} itens={totalDa(c)} />
                {podeEditar && (
                <>
                  <button
                    type="button"
                    className="link-acao"
                    onClick={() =>
                      setEditando({
                        tipo: "subcategoria",
                        id: null,
                        idPai: c.id,
                        nome: "",
                        descricao: "",
                        ordem: String((c.subcategorias.length + 1) * 10),
                      })
                    }
                  >
                    + subcategoria
                  </button>
                  <button
                    type="button"
                    className="link-acao"
                    onClick={() =>
                      setEditando({
                        tipo: "categoria",
                        id: c.id,
                        idPai: idCatalogo,
                        nome: c.nome,
                        descricao: c.descricao ?? "",
                        ordem: String(c.ordem),
                      })
                    }
                  >
                    alterar
                  </button>
                  <button
                    type="button"
                    className="link-acao link-acao-erro"
                    onClick={() =>
                      setApagando({
                        tipo: "categoria",
                        id: c.id,
                        nome: c.nome,
                        itens:
                          c.itens.length +
                          c.subcategorias.reduce((t, s) => t + s.itens.length, 0),
                      })
                    }
                  >
                    excluir
                  </button>
                </>
                )}
              </span>
            }
          >
            {/* ⚠️ **Fechada, o miolo não é DESENHADO** — e não apenas escondido
                com CSS. Uma categoria com trinta produtos continuaria montando
                trinta linhas invisíveis, e a tela que se queria encurtar seguiria
                pesada do mesmo jeito. */}
            {estaFechada("categoria", c.id) ? null : (
            <div className="flex flex-col gap-5">
              <FotoDaSecao tipo="categoria" secao={c} />

              {/* 🔑 **Os produtos soltos vêm ANTES das subcategorias.** Eles são
                  da categoria inteira; mostrá-los depois faria parecer que
                  pertencem à última subdivisão. */}
              <div>
                <span className="rotulo">Produtos direto nesta categoria</span>
                <ListaDeItens
                  itens={c.itens}
                  idCategoria={c.id}
                  idSubcategoria={null}
                  onde={c.nome}
                />
              </div>

              {c.subcategorias.map((s) => (
                <div key={s.id} className="border-l-2 border-linha2 pl-3">
                  <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                    <span className="text-[15px] font-semibold">{s.nome}</span>
                    <span className="flex gap-3">
                      <Recolher tipo="subcategoria" id={s.id} itens={s.itens.length} />
                      {podeEditar && (
                      <>
                        <button
                          type="button"
                          className="link-acao"
                          onClick={() =>
                            setEditando({
                              tipo: "subcategoria",
                              id: s.id,
                              idPai: c.id,
                              nome: s.nome,
                              descricao: s.descricao ?? "",
                              ordem: String(s.ordem),
                            })
                          }
                        >
                          alterar
                        </button>
                        <button
                          type="button"
                          className="link-acao link-acao-erro"
                          onClick={() =>
                            setApagando({
                              tipo: "subcategoria",
                              id: s.id,
                              nome: s.nome,
                              itens: s.itens.length,
                            })
                          }
                        >
                          excluir
                        </button>
                      </>
                      )}
                    </span>
                  </div>
                  {s.descricao && !estaFechada("subcategoria", s.id) && (
                    <p className="mt-0.5 text-[13.5px] text-suave">{s.descricao}</p>
                  )}
                  {!estaFechada("subcategoria", s.id) && (
                    <div className="mt-2">
                      <FotoDaSecao tipo="subcategoria" secao={s} />
                    </div>
                  )}
                  {estaFechada("subcategoria", s.id) ? null : (
                    <ListaDeItens
                      itens={s.itens}
                      idCategoria={c.id}
                      idSubcategoria={s.id}
                      onde={`${c.nome} ▸ ${s.nome}`}
                    />
                  )}
                </div>
              ))}
            </div>
            )}
          </Cartao>
        ))
      )}

      {/* --------------------------------------------- a janela da seção --- */}
      {editando && (
        <Modal
          titulo={`${editando.id ? "Alterar" : "Nova"} ${
            editando.tipo === "categoria" ? "categoria" : "subcategoria"
          }`}
          aoFechar={() => setEditando(null)}
          rodape={
            <>
              <button
                type="button"
                className="btn btn-secundario"
                onClick={() => setEditando(null)}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="btn btn-primario"
                aria-busy={salvando}
                disabled={salvando || editando.nome.trim().length < 2}
                onClick={() => void salvarSecao()}
              >
                Salvar
              </button>
            </>
          }
        >
          <div className="flex flex-col gap-4">
            <Campo rotulo="Nome" dica="É o que o cliente lê no cardápio.">
              <input
                id="secao-nome"
                className="campo"
                maxLength={120}
                autoFocus
                value={editando.nome}
                onChange={(e) => setEditando({ ...editando, nome: e.target.value })}
              />
            </Campo>
            <Campo rotulo="Descrição" dica="Opcional. Aparece abaixo do nome.">
              <textarea
                id="secao-descricao"
                className="campo"
                rows={3}
                maxLength={500}
                value={editando.descricao}
                onChange={(e) => setEditando({ ...editando, descricao: e.target.value })}
              />
            </Campo>
            {/* ⚠️ **A ordem é do CARDÁPIO, não alfabética**: "Entradas" antes de
                "Sobremesas" é a sequência da refeição, e só a casa sabe qual é. */}
            <Campo rotulo="Ordem" dica="Menor aparece primeiro. Nada a ver com ordem alfabética.">
              <span className="block w-[96px]">
                <input
                  id="secao-ordem"
                  className="campo mono"
                  inputMode="numeric"
                  value={editando.ordem}
                  onChange={(e) =>
                    setEditando({ ...editando, ordem: e.target.value.replace(/\D/g, "") })
                  }
                />
              </span>
            </Campo>
            <p className="text-[13px] text-suave">
              A foto se põe depois de salvar, na própria lista.
            </p>
          </div>
        </Modal>
      )}

      {/* ------------------------------------------ a janela dos produtos --- */}
      {pendurando && (
        <Modal
          titulo="Pôr um produto"
          aoFechar={() => setPendurando(null)}
          rodape={
            <button
              type="button"
              className="btn btn-secundario"
              onClick={() => setPendurando(null)}
            >
              Fechar
            </button>
          }
        >
          <div className="flex flex-col gap-4">
            <p className="text-[13.5px] text-suave">
              Entrando em <b>{pendurando.onde}</b>.
            </p>
            <Campo
              rotulo="Procurar"
              dica="Só produtos ativos e vendidos no PDV aparecem aqui."
            >
              <input
                id="busca-produto"
                className="campo"
                autoFocus
                placeholder="nome ou código"
                value={busca}
                onChange={(e) => setBusca(e.target.value)}
              />
            </Campo>
            {procurando ? (
              <p className="text-[13.5px] text-suave">Procurando…</p>
            ) : achados.length === 0 ? (
              <p className="text-[13.5px] text-suave">
                Nenhum produto encontrado. ⚠️ O cardápio do site mostra só o que está
                no balcão: o produto precisa estar <b>ativo</b> e ir ao <b>PDV</b>.
              </p>
            ) : (
              <ul className="lista-rolante flex flex-col gap-px bg-linha text-[14.5px]">
                {achados.map((p) => (
                  <li
                    key={p.id}
                    className="flex flex-wrap items-center gap-x-3 gap-y-1 bg-superficie py-2"
                  >
                    <span className="mono text-[12.5px] text-suave">{p.codigo}</span>
                    <span>{p.nome}</span>
                    <button
                      type="button"
                      className="link-acao ml-auto"
                      onClick={() => void pendurar(p.id)}
                    >
                      pôr
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Modal>
      )}

      {apagando && (
        <Confirmacao
          titulo={`Excluir "${apagando.nome}"?`}
          aoConfirmar={() => void confirmarApagar()}
          aoCancelar={() => setApagando(null)}
          rotuloConfirmar="Excluir"
          perigo
        >
          {/* 🔑 A frase diz QUANTOS produtos saem junto: apagar uma seção com
              trinta itens dentro não pode ser um clique sem consequência. */}
          <p>
            {apagando.itens > 0
              ? `${apagando.itens} produto(s) saem do cardápio junto. Os produtos continuam cadastrados — o que se desfaz é o vínculo.`
              : "Não há produto nenhum pendurado aqui."}
            {apagando.tipo === "categoria" &&
              " As subcategorias dela também são removidas."}
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
