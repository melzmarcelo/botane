"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import {
  Categoria,
  Fornecedor,
  Local,
  reais,
  Setor,
  TIPOS_PRODUTO,
  UnidadeMedida,
} from "@/lib/cadastros";
import BotaoExportar from "@/components/exportar";
import {
  Aviso,
  Campo,
  CampoMoeda,
  Carregando,
  Cartao,
  Confirmacao,
  Etiqueta,
} from "@/components/ui";
import { moedaParaNumero, numeroParaMoeda } from "@/lib/numeros";
import BuscaCadastro from "@/components/busca-cadastro";
import { fonteFornecedores, ItemBusca } from "@/lib/busca-cadastro";
import CodigosDoProduto, { CodigoExterno } from "./codigos";
import ComposicaoKit from "./kit";
import CustoDoProduto from "./custo";
import LocaisDoProduto from "./locais";
import UnidadesDeCompra from "./unidades";
import Vincular from "./vincular";
import Voltar from "@/components/voltar";

type VinculoFornecedor = {
  id_fornecedor: number;
  fornecedor?: string;
  codigo_no_fornecedor: string | null;
  embalagem: string | null;
  fator: number;
  ultimo_preco: number | null;
  preferencial: boolean;
};

type Form = {
  codigo: string;
  nome: string;
  nome_curto: string;
  tipo: string;
  id_categoria: string;
  id_setor: string;
  producao_propria: boolean;
  modo_producao: string;
  controla_estoque: boolean;
  um_estoque: string;
  um_compra: string;
  fator_compra: string;
  id_local_padrao: string;
  id_local_venda: string;
  perecivel: boolean;
  validade_dias: string;
  controla_lote: boolean;
  integrado_pdv: boolean;
  controla_validade: boolean;
  estoque_minimo: string;
  estoque_maximo: string;
  ncm: string;
  cest: string;
  marca: string;
  peso_liquido: string;
  peso_bruto: string;
  codigo_barras: string;
  observacao: string;
  preco_venda: string;
  status: string;
  ativo: boolean;
};

const VAZIO: Form = {
  codigo: "", nome: "", nome_curto: "", tipo: "INSUMO", id_categoria: "", id_setor: "",
  producao_propria: false, modo_producao: "PARA_ESTOQUE", controla_estoque: true, um_estoque: "", um_compra: "",
  fator_compra: "1", id_local_padrao: "", id_local_venda: "", perecivel: false, validade_dias: "", controla_lote: false,
  integrado_pdv: false,
  controla_validade: false, estoque_minimo: "", estoque_maximo: "", ncm: "",
  cest: "", marca: "", peso_liquido: "", peso_bruto: "",
  codigo_barras: "", observacao: "", preco_venda: "", status: "ATIVO", ativo: true,
};

const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));
const texto = (v: string) => (v.trim() === "" ? null : v.trim());

const FORNECEDORES = fonteFornecedores();

export default function FormularioProduto() {
  const [vinculando, setVinculando] = useState(false);
  const aviso = useAviso();
  const { id } = useParams<{ id: string }>();
  const novo = id === "novo";
  const router = useRouter();
  const { pode, eu } = useSessao();
  // 🔑 O preço por loja só faz sentido com mais de uma: com uma só, "da casa"
  // e "desta loja" são a mesma coisa, e o bloco seria ruído.
  const variasLojas = (eu?.unidades.length ?? 0) > 1;
  const [precoLoja, setPrecoLoja] = useState("");
  const [precoCasa, setPrecoCasa] = useState<number | null>(null);
  /**
   * 🔑 **Com UMA loja só, o campo edita o preço que VALE** (09/09/2026,
   * relatado pelo dono: *"no grid aparece o preço de venda, mas ao consultar o
   * produto o preço está vazio; este produto veio do PDV"*).
   *
   * O preço tem dois donos possíveis: o da casa (`id_unidade` nulo) e o da
   * loja. O que vem do PDV nasce **da loja**, de propósito — `tabelapreco` é
   * por filial. O grid mostra o resolvido (loja primeiro); o formulário mostra
   * só o da casa. E o bloco "Preço nesta loja" só aparece para quem tem mais de
   * uma loja. Resultado com uma loja: o preço ficava **invisível e não
   * editável** — 637 produtos do PDV na base de teste.
   *
   * ⚠️ **Nada muda com VÁRIAS lojas.** Lá a separação tem razão de ser: editar
   * um produto numa filial não pode gravar o preço dela como o da casa. Aqui,
   * "casa" e "loja" são a mesma coisa para quem olha.
   *
   * ⚠️ Grava de volta no MESMO dono de onde veio: preço que nasceu da loja
   * continua na loja. Escrevê-lo na casa criaria uma segunda linha vigente e a
   * loja continuaria mandando — o número editado não teria efeito nenhum.
   */
  const [precoEhDaLoja, setPrecoEhDaLoja] = useState(false);
  const [salvandoPreco, setSalvandoPreco] = useState(false);
  const enviaAoPdv = !!eu?.enviar_ao_pdv;
  const podeEditar = pode("cadastros.produtos");

  const [f, setF] = useState<Form>(VAZIO);
  const [vinculos, setVinculos] = useState<VinculoFornecedor[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [setores, setSetores] = useState<Setor[]>([]);
  const [ums, setUms] = useState<UnidadeMedida[]>([]);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [locais, setLocais] = useState<Local[]>([]);
  // 🔑 As prateleiras escolhidas na tela de CRIAR. Sem id não há para onde
  // gravar, então ficam aqui e sobem logo depois do `POST /produtos` — mesmo
  // caminho da foto da ficha.
  const [locaisPendentes, setLocaisPendentes] = useState<number[]>([]);
  const [carregando, setCarregando] = useState(!novo);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<Categoria[]>("/categorias"),
      api.get<Setor[]>("/setores"),
      api.get<UnidadeMedida[]>("/unidades-medida"),
      api.get<Fornecedor[]>("/fornecedores?so_fornecedores=true"),
      api.get<Local[]>("/locais"),
    ])
      .then(([c, s, u, fo, lo]) => {
        setCategorias(c);
        setSetores(s);
        setUms(u);
        setFornecedores(fo);
        setLocais(lo);
      })
      .catch((e) => setErro(e.message));
  }, []);

  // 🔑 Os códigos de fora que caem neste produto — o de-para que a fusão e o
  // vínculo de nota criaram. Guardado à parte do formulário porque não é campo
  // do cadastro: é o que o mundo lá fora chama este produto.
  const [codigos, setCodigos] = useState<CodigoExterno[]>([]);
  const [recarga, setRecarga] = useState(0);

  /**
   * 🔑 **A previa da troca de unidade, ao vivo** (09/09/2026, relato do dono:
   * "conforme vou mexendo no fator de conversao o custo nao e ajustado em tempo
   * real"). Trocar a unidade CONVERTE o custo no servidor — e o numero so
   * aparecia depois de gravar, quando ja nao havia volta.
   *
   * ⚠️ Aconteceu com uma caixa de 1.000 unidades a R$ 33,99: um fator
   * invertido dividiu por mil, o custo virou R$ 0,03 e nada avisou.
   * ⚠️ **E o mesmo engano ao contrario multiplica** (12/09/2026, pedido do
   * dono): o custo que dispara nao some da vista como o zero, mas contamina
   * toda ficha que usa o insumo. `custo_salto` diz de que lado foi.
   */
  const [previaUnidade, setPreviaUnidade] = useState<{
    muda: boolean;
    pode: boolean;
    motivo?: string;
    /** "zera", "dispara" ou nulo — o custo dando um salto de ordem de grandeza
     *  num dos dois sentidos. Os dois pedem confirmação. */
    custo_salto?: "zera" | "dispara" | null;
    resumo?: string;
    conversoes?: { campo: string; de: number; para: number }[];
  } | null>(null);
  const [confirmandoCusto, setConfirmandoCusto] = useState(false);

  useEffect(() => {
    if (novo) return;
    api
      .get<Record<string, unknown>>(`/produtos/${id}`)
      .then((p) => {
        setCodigos((p.codigos_externos as CodigoExterno[]) ?? []);
        setF({
          ...VAZIO,
          ...Object.fromEntries(
            Object.entries(VAZIO).map(([k, padrao]) => {
              const v = p[k as keyof typeof p];
              if (typeof padrao === "boolean") return [k, !!v];
              return [k, v === null || v === undefined ? "" : String(v)];
            }),
          ),
        } as Form);
        setVinculos((p.fornecedores as VinculoFornecedor[]) ?? []);
        // ⚠️ Com VÁRIAS lojas o campo mostra o preço DA CASA, não o resolvido:
        // senão, editar um produto numa filial que cobra diferente gravaria o
        // preço dela como se fosse o da casa. Com uma loja só, essa distinção
        // não existe para quem olha — e esconder o preço da loja deixava o
        // campo vazio num produto que o grid mostra com preço. Ver
        // `precoEhDaLoja`.
        const casa = p.preco_casa as number | null;
        const daLoja = p.preco_loja as number | null;
        setPrecoCasa(casa ?? null);
        setPrecoLoja(numeroParaMoeda(daLoja));
        const umaLojaSo = (eu?.unidades.length ?? 0) <= 1;
        const daLojaVale = umaLojaSo && daLoja !== null && daLoja !== undefined;
        setPrecoEhDaLoja(daLojaVale);
        const noCampo = daLojaVale ? daLoja : casa;
        setF((atual) => ({
          ...atual,
          preco_venda: numeroParaMoeda(noCampo),
        }));
      })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, novo, recarga, eu?.unidades.length]);

  // ⚠️ So depois de a tela ter carregado, e so quando a unidade REALMENTE
  // mudou: pedir a previa a cada tecla do nome seria ruido no servidor.
  useEffect(() => {
    if (novo || carregando || !f.um_estoque) {
      setPreviaUnidade(null);
      return;
    }
    let valeu = true;
    const q = new URLSearchParams({ um_estoque: f.um_estoque });
    if (f.um_compra) q.set("um_compra", f.um_compra);
    if (f.fator_compra) q.set("fator_compra", f.fator_compra.replace(",", "."));
    const t = setTimeout(() => {
      api
        .get<typeof previaUnidade>(`/produtos/${id}/troca-de-unidade?${q}`)
        .then((r) => valeu && setPreviaUnidade(r))
        .catch(() => valeu && setPreviaUnidade(null));
    }, 400);
    return () => {
      valeu = false;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, novo, carregando, f.um_estoque, f.um_compra, f.fator_compra]);

  async function salvarPrecoDaLoja(valor: number | null) {
    setSalvandoPreco(true);
    try {
      const r = await api.put<{ message: string }>(`/produtos/${id}/preco-loja`, {
        preco_venda: valor,
      });
      setPrecoLoja(numeroParaMoeda(valor));
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar o preço");
    } finally {
      setSalvandoPreco(false);
    }
  }

  function set<K extends keyof Form>(campo: K, valor: Form[K]) {
    setF((atual) => {
      const proximo = { ...atual, [campo]: valor };
      // Produção própria só existe em produzido/kit — o servidor recusa o resto.
      if (campo === "tipo" && !["PRODUZIDO", "KIT"].includes(String(valor))) {
        proximo.producao_propria = false;
      }
      if (campo === "producao_propria" && valor === true && !["PRODUZIDO", "KIT"].includes(atual.tipo)) {
        proximo.tipo = "PRODUZIDO";
      }
      return proximo;
    });
  }

  async function salvar(e: FormEvent, confirmado = false) {
    e.preventDefault();
    // 🔑 **Pergunta ANTES de gravar quando o custo da um salto** — para
    // qualquer um dos dois lados. O servidor tambem recusa sem confirmacao:
    // esta janela existe para a pessoa ver os dois numeros e responder, nao
    // para ser a unica guarda.
    if (!confirmado && previaUnidade?.muda && previaUnidade.custo_salto) {
      setConfirmandoCusto(true);
      return;
    }
    setSalvando(true);
    setErro("");
    const corpo = {
      codigo: texto(f.codigo),
      nome: f.nome.trim(),
      nome_curto: texto(f.nome_curto),
      tipo: f.tipo,
      id_categoria: num(f.id_categoria),
      id_setor: num(f.id_setor),
      producao_propria: f.producao_propria,
      modo_producao: f.modo_producao,
      controla_estoque: f.controla_estoque,
      um_estoque: texto(f.um_estoque),
      um_compra: texto(f.um_compra),
      fator_compra: num(f.fator_compra) ?? 1,
      id_local_padrao: num(f.id_local_padrao),
      // ⚠️ Vazio vai como NULO: "não escolhi" é diferente de "o local zero", e é
      // o nulo que faz a venda continuar no local de estoque.
      id_local_venda: num(f.id_local_venda),
      perecivel: f.perecivel,
      validade_dias: num(f.validade_dias),
      controla_lote: f.controla_lote,
      controla_validade: f.controla_validade,
      integrado_pdv: f.integrado_pdv,
      estoque_minimo: num(f.estoque_minimo),
      estoque_maximo: num(f.estoque_maximo),
      ncm: texto(f.ncm),
      cest: texto(f.cest),
      marca: texto(f.marca),
      peso_liquido: num(f.peso_liquido),
      peso_bruto: num(f.peso_bruto),
      codigo_barras: texto(f.codigo_barras),
      observacao: texto(f.observacao),
      // ⚠️ Preço que veio da LOJA não sai no corpo do produto: ele é gravado
      // logo abaixo, pela rota da loja. Mandá-lo aqui abriria uma linha
      // vigente da CASA — e a da loja continuaria mandando, deixando o número
      // editado sem efeito nenhum.
      preco_venda: precoEhDaLoja ? undefined : moedaParaNumero(f.preco_venda),
      fornecedores: vinculos.map((v) => ({
        id_fornecedor: v.id_fornecedor,
        codigo_no_fornecedor: v.codigo_no_fornecedor,
        embalagem: v.embalagem,
        fator: Number(v.fator) || 1,
        ultimo_preco: v.ultimo_preco,
        preferencial: v.preferencial,
      })),
    };
    try {
      if (novo) {
        const r = await api.post<{ id: number }>("/produtos", corpo);
        // ⚠️ **Falhar aqui NÃO é "não foi possível salvar".** O produto já
        // existe deste ponto em diante, e a frase genérica mandaria cadastrar
        // tudo de novo — criando um segundo cadastro do mesmo item. Mesma
        // lição da foto da ficha.
        const naoForam: number[] = [];
        for (const idLocal of locaisPendentes) {
          try {
            await api.post(`/produtos/${r.id}/locais`, { id_local: idLocal });
          } catch {
            naoForam.push(idLocal);
          }
        }
        router.replace(`/produtos/${r.id}`);
        if (naoForam.length) {
          aviso.erro(
            `${f.nome.trim()} foi criado, mas ${naoForam.length} local(is) não foram` +
              " gravados. Acrescente-os no cartão “Onde este produto fica”.",
          );
        }
        // Quem cadastra um produto costuma cadastrar o próximo. O caminho para
        // isso vai junto do aviso, em vez de exigir voltar à lista e achar o
        // botão de novo.
        aviso.sucesso(`${f.nome.trim()} criado.`, {
          texto: "cadastrar outro",
          ao: () => router.push("/produtos/novo"),
        });
      } else {
        await api.put(`/produtos/${id}`, {
          ...corpo,
          ativo: f.ativo,
          confirmar_troca_de_unidade: confirmado,
        });
        // 🔑 **O preço que é DA LOJA é gravado pela rota da loja** — ver
        // `precoEhDaLoja`. Com uma loja só o campo edita o preço que vale, e
        // ele precisa voltar para o mesmo dono de onde veio: escrito na casa,
        // abriria uma segunda linha vigente, a da loja continuaria mandando, e
        // o número editado não teria efeito nenhum — com a tela dizendo que
        // salvou.
        // ⚠️ **Depois do PUT do produto, não antes.** Se a gravação do produto
        // falhar (uma troca de unidade recusada, por exemplo), o preço não pode
        // ter mudado sozinho.
        // ⚠️ Campo vazio APAGA o preço da loja (a rota trata nulo como
        // remoção), e aí o produto volta a valer o da casa — que é o que
        // "apagar o preço" quer dizer nesta tela.
        if (precoEhDaLoja) {
          const valor = moedaParaNumero(f.preco_venda);
          await api.put(`/produtos/${id}/preco-loja`, { preco_venda: valor ?? null });
        }
        // 🔑 **Reler o produto depois de salvar** (09/09/2026, relato do dono:
        // "preciso dar F5 para mostrar o custo certo"). O servidor TRANSFORMA o
        // que recebe: o nome vira maiuscula, e trocar a unidade de estoque
        // CONVERTE o custo — 60,00/CX vira 5,00/UN. Sem reler, a tela seguia
        // mostrando 60,00 exatamente no momento em que o numero acabara de
        // mudar, e so o F5 revelava. O `recarga` refaz a busca da tela e dos
        // cartoes que leem do servidor.
        setRecarga((n) => n + 1);
        aviso.sucesso(`${f.nome.trim()} salvo.`, {
          texto: "voltar para a lista",
          ao: () => router.push("/produtos"),
        });
      }
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function revisar() {
    try {
      await api.post(`/produtos/${id}/revisar`);
      setF((a) => ({ ...a, status: "ATIVO" }));
      aviso.sucesso("Produto revisado — agora ele pode entrar no estoque.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível revisar");
    }
  }

  if (carregando) return <Carregando />;

  const umEstoque = ums.find((u) => u.sigla === f.um_estoque);
  const umCompra = ums.find((u) => u.sigla === f.um_compra);
  const mostraFator = !!f.um_compra && f.um_compra !== f.um_estoque;

  return (
    <form onSubmit={salvar} className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Voltar href="/produtos">
            produtos
          </Voltar>
          <h1 className="mt-1 break-words text-[26px] font-bold tracking-tight sm:text-[30px]">
            {novo ? "Novo produto" : f.nome || "Produto"}
          </h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            {!novo && f.codigo && <Etiqueta>{f.codigo}</Etiqueta>}
            {f.status === "RASCUNHO" && <Etiqueta cor="alerta">rascunho</Etiqueta>}
            {!f.ativo && <Etiqueta cor="alerta">inativo</Etiqueta>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* ⚠️ Fora do `podeEditar`: levar os dados do produto para fora — para
              conferir uma compra, discutir preço com o fornecedor ou responder
              ao contador — é coisa de quem CONSULTA, não de quem edita. O bloco
              de estoque dentro do arquivo tem a permissão dele, no servidor. */}
          {!novo && (
            <BotaoExportar
              relatorio={`produto/${id}`}
              rotulo="Baixar"
              avulso={{
                rotulo: `Produto — ${f.nome || "sem nome"}`,
                descricao:
                  "Cadastro, saldo por local, embalagens, fornecedores e os últimos movimentos.",
              }}
            />
          )}
          {/* 🔑 **A memória de cálculo deste insumo** (pedido da contabilidade,
              02/09/2026): a resposta para "como você chegou nesse custo
              unitário?". Cada movimento do período com a CONTA do custo médio
              escrita na linha — `(saldo × médio + entrada × custo) ÷ novo
              saldo` —, para o número deixar de aparecer pronto e passar a se
              conferir na calculadora.
              ⚠️ O produto vem SEMEADO: é o que está na tela, e obrigar a
              procurá-lo de novo na janela seria pedir duas vezes a mesma coisa.
              ⚠️ Pede `estoque.saldos` — custo médio é dado de ESTOQUE, e não
              passa a ser de cadastro por estar na tela do produto. */}
          {!novo && f.controla_estoque && pode("estoque.saldos") && (
            <BotaoExportar
              relatorio="memoria-produto"
              rotulo="Memória de cálculo"
              formatoPadrao="pdf"
              iniciais={{
                produtos: [{ id: Number(id), rotulo: f.nome || `Produto ${id}` }],
              }}
            />
          )}
          {podeEditar && (
            <>
            {/* ⚠️ **O caminho para dizer que dois cadastros são o mesmo.** Não
                existe detector: "BEB CERV HEINEKEN 350ML" e "CERVEJA HEINEKEN
                PILSEN" são o mesmo produto e batem 63,8% de semelhança, e
                nenhum piso honesto os junta. Quem reconhece está aqui, olhando
                o produto. */}
            {!novo && (
              <button
                type="button"
                className="btn btn-secundario"
                onClick={() => setVinculando(true)}
                title="Dizer que outro cadastro é este mesmo produto"
              >
                Vincular
              </button>
            )}
            {!novo && f.status === "RASCUNHO" && (
              <button type="button" className="btn btn-secundario" onClick={revisar}>
                Revisar e ativar
              </button>
            )}
            <button className="btn btn-primario" type="submit" disabled={salvando}>
              {salvando ? "Salvando…" : novo ? "Criar produto" : "Salvar"}
            </button>
            </>
          )}
        </div>
      </header>

      {vinculando && (
        <Vincular
          idProduto={Number(id)}
          aoFechar={() => setVinculando(false)}
          aoFundir={() => {
            setVinculando(false);
            // Recarrega: o nome, a descrição curta e os códigos mudaram.
            router.refresh();
            window.location.reload();
          }}
        />
      )}

      {!podeEditar && <Aviso tipo="info">Você tem acesso de leitura a esta tela.</Aviso>}
      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {/* 🔑 **O que a troca de unidade vai fazer, enquanto se digita.** Era
          invisivel: o custo so mudava depois de gravar, e ai nao havia volta. */}
      {previaUnidade?.muda && !previaUnidade.pode && (
        <Aviso tipo="erro">{previaUnidade.motivo}</Aviso>
      )}
      {previaUnidade?.muda && previaUnidade.pode && (
        <Aviso tipo={previaUnidade.custo_salto ? "erro" : "info"}>
          <b>{previaUnidade.resumo}</b>
          {(previaUnidade.conversoes ?? []).map((c) => (
            <span key={c.campo} className="mt-1 block">
              {c.campo === "custo_referencia"
                ? "O custo passa de "
                : `${c.campo === "estoque_minimo" ? "O mínimo" : "O máximo"} passa de `}
              <b>{reais(c.de)}</b> para <b>{reais(c.para)}</b>
              {c.campo !== "custo_referencia" && " (na nova unidade)"}
            </span>
          ))}
          {previaUnidade.custo_salto && (
            <span className="mt-1 block">
              ⚠️ Isso{" "}
              {previaUnidade.custo_salto === "dispara" ? (
                <>
                  <b>multiplica o custo</b> de vez. Se o fator estiver invertido, esse
                  número passa a valer em toda ficha que usa este insumo
                </>
              ) : (
                <>
                  deixa o custo <b>praticamente zerado</b>. Se o fator estiver
                  invertido, o valor se perde e não volta
                </>
              )}{" "}
              — o sistema vai perguntar antes de gravar.
            </span>
          )}
        </Aviso>
      )}

      {confirmandoCusto && (
        <Confirmacao
          titulo={
            previaUnidade?.custo_salto === "dispara"
              ? "O custo vai multiplicar. Seguir assim?"
              : "O custo vai ficar zerado. Seguir assim?"
          }
          perigo
          rotuloConfirmar="Sim, gravar"
          ocupado={salvando}
          aoConfirmar={() => {
            setConfirmandoCusto(false);
            // ⚠️ O `as` existe porque `salvar` espera um evento de formulario e
            // aqui nao ha um: o que importa e o `preventDefault`, que o objeto
            // abaixo cumpre.
            void salvar({ preventDefault() {} } as React.FormEvent, true);
          }}
          aoCancelar={() => setConfirmandoCusto(false)}
        >
          {(previaUnidade?.conversoes ?? [])
            .filter((c) => c.campo === "custo_referencia")
            .map((c) => (
              <p key={c.campo}>
                O custo deste produto passa de <b>{reais(c.de)}</b> para{" "}
                <b>{reais(c.para)}</b>. {previaUnidade?.resumo}
              </p>
            ))}
          <p className="mt-2">
            {previaUnidade?.custo_salto === "dispara"
              ? `Se o fator de conversão estiver invertido, esse custo contamina toda
                 ficha que usa este insumo, e não há como desfazer pela tela.`
              : `Se o fator de conversão estiver invertido, o custo se perde e não há
                 como desfazer pela tela.`}
          </p>
        </Confirmacao>
      )}

      <Cartao titulo="Identificação">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* ⚠️ `uppercase` é só CSS, e é de propósito: o valor gravado é
              normalizado pelo BANCO (migração 036, gatilho), porque o nome do
              produto é escrito por cinco caminhos diferentes. A classe existe
              para quem digita ver, na hora, o que vai ficar salvo — em vez de
              descobrir depois que "Café latte" virou outra coisa. */}
          <Campo rotulo="Nome" className="sm:col-span-2" dica="fica em MAIÚSCULAS">
            <input
              className="campo uppercase"
              required
              minLength={2}
              disabled={!podeEditar}
              value={f.nome}
              onChange={(e) => set("nome", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Código" dica={novo ? "em branco, o sistema gera" : undefined}>
            <input
              className="campo mono"
              disabled={!podeEditar}
              value={f.codigo}
              onChange={(e) => set("codigo", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Nome curto" dica="para o cardápio e o PDV · MAIÚSCULAS">
            <input
              className="campo uppercase"
              disabled={!podeEditar}
              value={f.nome_curto}
              onChange={(e) => set("nome_curto", e.target.value)}
            />
          </Campo>

          <Campo rotulo="Tipo">
            <select
              className="campo"
              disabled={!podeEditar}
              value={f.tipo}
              onChange={(e) => set("tipo", e.target.value)}
            >
              {TIPOS_PRODUTO.map((t) => (
                <option key={t.valor} value={t.valor}>
                  {t.nome}
                </option>
              ))}
            </select>
            <span className="mt-1 block text-[12.5px] text-suave">
              {TIPOS_PRODUTO.find((t) => t.valor === f.tipo)?.ajuda}
            </span>
          </Campo>
          <Campo rotulo="Categoria">
            <select
              className="campo"
              disabled={!podeEditar}
              value={f.id_categoria}
              onChange={(e) => set("id_categoria", e.target.value)}
            >
              <option value="">—</option>
              {categorias.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.caminho}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Setor" dica="cozinha, bar, confeitaria">
            <select
              className="campo"
              disabled={!podeEditar}
              value={f.id_setor}
              onChange={(e) => set("id_setor", e.target.value)}
            >
              <option value="">—</option>
              {setores.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome}
                </option>
              ))}
            </select>
          </Campo>
        </div>
      </Cartao>

      <Cartao
        titulo="Unidade e conversão"
        descricao="A conta do custo por quilo mora aqui: é o que separa a caixa comprada do grama consumido."
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Campo rotulo="Unidade de estoque" dica="como se consome">
            <select
              className="campo"
              disabled={!podeEditar}
              value={f.um_estoque}
              onChange={(e) => set("um_estoque", e.target.value)}
            >
              <option value="">—</option>
              {ums.map((u) => (
                <option key={u.sigla} value={u.sigla}>
                  {u.sigla} · {u.nome}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Unidade de compra" dica="como vem do fornecedor">
            <select
              className="campo"
              disabled={!podeEditar}
              value={f.um_compra}
              onChange={(e) => set("um_compra", e.target.value)}
            >
              <option value="">—</option>
              {ums.map((u) => (
                <option key={u.sigla} value={u.sigla}>
                  {u.sigla} · {u.nome}
                </option>
              ))}
            </select>
          </Campo>
          <Campo
            rotulo="Fator de conversão"
            dica={
              mostraFator
                ? `1 ${umCompra?.sigla} = ? ${umEstoque?.sigla ?? "un. de estoque"}`
                : "1 quando compra e estoque usam a mesma unidade"
            }
          >
            <input
              className="campo mono"
              type="number"
              step="0.000001"
              min="0.000001"
              disabled={!podeEditar}
              value={f.fator_compra}
              onChange={(e) => set("fator_compra", e.target.value)}
            />
          </Campo>
          {/* ⚠️ Este é o preço da CASA. O da loja tem bloco próprio abaixo:
              fazer este campo gravar por loja faria o preço "da casa" nunca ser
              definido — cada filial teria o seu e nenhuma herdaria nada. */}
          <Campo
            rotulo={variasLojas ? "Preço de venda da casa" : "Preço de venda"}
            dica="grava com data de vigência"
          >
            <CampoMoeda
              valor={f.preco_venda}
              aoMudar={(v) => set("preco_venda", v)}
              desabilitado={!podeEditar}
            />
          </Campo>
        </div>
      </Cartao>

      {/* 🔑 **O preço da LOJA, e só com mais de uma.** O da casa vale para todas;
          este sobrepõe nesta. É a mesma forma da reserva do custo — o específico
          primeiro, o geral depois — e é o que permite a filial cobrar diferente
          sem recadastrar centenas de pratos que custam o mesmo nos dois lugares. */}
      {variasLojas && !novo && (
        <Cartao
          titulo="Preço nesta loja"
          descricao={
            precoCasa === null
              ? "Sem preço da casa: o que valer aqui vale só aqui."
              : `Sem um preço aqui, vale o da casa: ${reais(precoCasa)}.`
          }
        >
          <div className="flex flex-wrap items-end gap-3">
            <Campo rotulo="Preço" className="w-[180px]">
              <CampoMoeda
                valor={precoLoja}
                aoMudar={setPrecoLoja}
                desabilitado={!podeEditar}
                placeholder={numeroParaMoeda(precoCasa)}
              />
            </Campo>
            {podeEditar && (
              <>
                <button
                  type="button"
                  className="btn btn-primario"
                  disabled={salvandoPreco}
                  onClick={() => void salvarPrecoDaLoja(moedaParaNumero(precoLoja))}
                >
                  {salvandoPreco ? "Salvando…" : "Salvar preço daqui"}
                </button>
                {/* ⚠️ Apagar não é zerar: zero seria dizer que aqui o prato é de
                    graça. Limpar devolve o preço da casa. */}
                <button
                  type="button"
                  className="link-acao-erro"
                  disabled={salvandoPreco}
                  onClick={() => void salvarPrecoDaLoja(null)}
                >
                  usar o preço da casa
                </button>
              </>
            )}
          </div>
        </Cartao>
      )}

      {/* 🔑 **O custo, que não tinha onde ser consultado** (pedido do dono,
          03/09/2026). Fica ACIMA do cartão de Estoque porque é a pergunta que
          se faz primeiro ao abrir um insumo — e porque a "Memória de cálculo"
          do topo só explica o custo médio, que numa casa recém-importada ainda
          não existe.
          ⚠️ `estoque.saldos` é a mesma chave do botão de memória ao lado: custo
          é dado de estoque e não vira dado de cadastro por estar nesta tela. */}
      {!novo && f.controla_estoque && pode("estoque.saldos") && (
        <Cartao titulo="Custo">
          {/* ⚠️ `recarga` aqui NAO e enfeite: este cartao busca por conta
              propria, e sem ele continuaria mostrando o custo de antes do
              salvamento — que e justamente o que obrigava ao F5. */}
          <CustoDoProduto
            idProduto={Number(id)}
            um={f.um_estoque || null}
            recarga={recarga}
          />
        </Cartao>
      )}

      {/* 🔑 **O caso do açúcar de confeiteiro** (pedido do dono, 04/09/2026): o
          fornecedor manda o pacote de 1 kg e o de 500 g como produtos
          diferentes, e aqui os dois são o mesmo. Depois da fusão, a nota do de
          500 g entrava como 1 kg por unidade — o estoque dobrava calado.
          ⚠️ Só quando HÁ código: um produto cadastrado à mão e nunca vinculado
          não tem o que mostrar, e um cartão vazio em toda tela de produto seria
          ruído em troca de nada. */}
      {!novo && !!codigos.length && (
        <Cartao
          titulo="Códigos de fora, e quanto cada um vale"
          descricao="O que o Omie, o PDV e os fornecedores chamam deste produto — e quantas unidades de estoque vêm em cada um."
        >
          <CodigosDoProduto
            idProduto={Number(id)}
            codigos={codigos}
            umEstoque={f.um_estoque || null}
            podeEditar={podeEditar}
            aoMudar={() => setRecarga((n) => n + 1)}
          />
        </Cartao>
      )}

      <Cartao titulo="Estoque">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* O local é do PRODUTO: uma nota traz congelado e seco na mesma
              folha, e um local por nota obrigaria a lançar duas vezes. */}
          <Campo rotulo="Local de estoque" dica="onde este produto entra">
            <select
              className="campo"
              disabled={!podeEditar}
              aria-label="Local de estoque"
              value={f.id_local_padrao}
              onChange={(e) => set("id_local_padrao", e.target.value)}
            >
              <option value="">— o local da nota —</option>
              {locais.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nome}
                </option>
              ))}
            </select>
          </Campo>
          {/* 🔑 **De onde a VENDA baixa** (migração 066, pedido do dono: "podemos
              criar no produto mais de um local, qual seria o local de estoque que
              o PDV consome"). O campo acima fazia TRÊS papéis — a venda, o
              fallback do consumo de insumo e o destino da produção —, e pôr a
              vitrine nele fazia a receita da pizza comer a massa da vitrine.
              ⚠️ Vazio é o normal, e é o padrão: sem escolha, a venda continua
              saindo do local de estoque, como sempre saiu. */}
          <Campo rotulo="Local da venda" dica="de onde o PDV baixa">
            <select
              className="campo"
              disabled={!podeEditar}
              aria-label="Local da venda"
              value={f.id_local_venda}
              onChange={(e) => set("id_local_venda", e.target.value)}
            >
              <option value="">— o local de estoque —</option>
              {locais.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.nome}
                </option>
              ))}
            </select>
          </Campo>
          <Campo rotulo="Estoque mínimo" dica="alerta de ruptura">
            <input
              className="campo mono"
              type="number"
              step="0.001"
              disabled={!podeEditar}
              value={f.estoque_minimo}
              onChange={(e) => set("estoque_minimo", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Estoque máximo">
            <input
              className="campo mono"
              type="number"
              step="0.001"
              disabled={!podeEditar}
              value={f.estoque_maximo}
              onChange={(e) => set("estoque_maximo", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Validade (dias)" dica="a partir da entrada">
            <input
              className="campo mono"
              type="number"
              disabled={!podeEditar}
              value={f.validade_dias}
              onChange={(e) => set("validade_dias", e.target.value)}
            />
          </Campo>
          {/* ⚠️ **O EAN existia no formulário e não tinha campo na tela.** Era
              enviado ao salvar e lido pela conciliação da nota — nível 3 da
              cascata, o que casa o item do fornecedor com o produto certo —,
              mas ninguém conseguia ver nem digitar. Campo morto na direção
              inversa: o dado entrava só pela importação do Omie. */}
          <Campo rotulo="Código de barras (EAN/GTIN)" dica="casa o item da nota com este produto">
            <input
              className="campo mono"
              maxLength={20}
              inputMode="numeric"
              disabled={!podeEditar}
              value={f.codigo_barras}
              onChange={(e) => set("codigo_barras", e.target.value)}
            />
          </Campo>
          <Campo rotulo="NCM">
            <input
              className="campo mono"
              disabled={!podeEditar}
              value={f.ncm}
              onChange={(e) => set("ncm", e.target.value)}
            />
          </Campo>
          <Campo rotulo="CEST" dica="acompanha o NCM">
            <input
              className="campo mono"
              disabled={!podeEditar}
              value={f.cest}
              onChange={(e) => set("cest", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Marca" dica="separa dois “café 500g”">
            <input
              className="campo"
              maxLength={60}
              disabled={!podeEditar}
              value={f.marca}
              onChange={(e) => set("marca", e.target.value)}
            />
          </Campo>
          {/* ⚠️ Peso é conversão, não enfeite: o pacote entra por UN e a ficha
              consome em KG. O LÍQUIDO é o que interessa — o bruto inclui a
              embalagem, e ninguém cozinha o papelão. */}
          <Campo rotulo="Peso líquido" dica="o que dá para usar">
            <input
              className="campo mono"
              type="number"
              step="0.001"
              disabled={!podeEditar}
              value={f.peso_liquido}
              onChange={(e) => set("peso_liquido", e.target.value)}
            />
          </Campo>
          <Campo rotulo="Peso bruto" dica="com a embalagem">
            <input
              className="campo mono"
              type="number"
              step="0.001"
              disabled={!podeEditar}
              value={f.peso_bruto}
              onChange={(e) => set("peso_bruto", e.target.value)}
            />
          </Campo>
        </div>


        <ul className="mt-5 grid gap-px overflow-hidden rounded border border-linha bg-linha sm:grid-cols-2">
          {[
            {
              campo: "controla_estoque" as const,
              nome: "Controla estoque",
              explica: "Desligue para descartável avulso que você não quer contar.",
            },
            {
              campo: "producao_propria" as const,
              nome: "Produção própria",
              explica: "Tem ficha técnica. Só vale para produzido ou kit.",
            },
            {
              campo: "perecivel" as const,
              nome: "Perecível",
              explica: "Entra nos alertas de vencimento.",
            },
            {
              campo: "controla_lote" as const,
              nome: "Controla lote",
              explica: "Opcional no lançamento: o que não for identificado sai do saldo geral.",
            },
            {
              campo: "controla_validade" as const,
              nome: "Controla validade",
              explica: "Na saída, o sistema sugere o que vence primeiro.",
            },
            // ⚠️ Marca uma DECISÃO, não um fato derivado: quem já tem código
            // do PDV nasce marcado (e quem ganha o código depois também — quem
            // garante é o gatilho da 040). Mas um prato novo pode ser marcado
            // ANTES de existir lá, e um produto que veio de lá pode ser
            // desmarcado para o Botané não mexer nele.
            // ⚠️ Só aparece com o envio LIGADO na integração: controle para um
            // recurso desligado é ruído. Desligar o envio NÃO desmarca ninguém —
            // o valor gravado fica, e volta a aparecer quando religarem.
            ...(enviaAoPdv
              ? [
                  {
                    campo: "integrado_pdv" as const,
                    nome: "Integrado com PDV",
                    explica: "Este produto existe (ou deve existir) no cardápio do PDV.",
                  },
                ]
              : []),
          ].map((i, n, lista) => (
            <li
              key={i.campo}
              // ⚠️ O último só ocupa a linha inteira quando a lista é ÍMPAR —
              // senão sobra uma célula vazia ao lado dele.
              className={`flex items-start gap-3 bg-superficie p-4 ${
                n === lista.length - 1 && lista.length % 2 ? "sm:col-span-2" : ""
              }`}
            >
              <input
                id={i.campo}
                type="checkbox"
                className="mt-1 h-4 w-4 accent-erva"
                disabled={!podeEditar}
                checked={f[i.campo]}
                onChange={(e) => set(i.campo, e.target.checked)}
              />
              <label htmlFor={i.campo} className="cursor-pointer">
                <span className="block text-[14.5px] font-semibold">{i.nome}</span>
                <span className="mt-0.5 block text-[13px] leading-snug text-suave">
                  {i.explica}
                </span>
              </label>
            </li>
          ))}
        </ul>

        {/* Duas naturezas que o sistema tratava igual e não são: a massa de
            pizza fica pronta esperando; o café passado não existe parado. */}
        {f.producao_propria && (
          <div className="mt-4 border-t border-linha pt-4">
            <span className="rotulo">Como este produto é produzido</span>
            <ul className="mt-2 grid gap-3 sm:grid-cols-2">
              {[
                {
                  valor: "PARA_ESTOQUE",
                  nome: "Para estoque",
                  explica:
                    "Produz, guarda e sai depois — para venda ou para outra receita. Tem saldo, tem mínimo e entra na agenda de produção. É a massa de pizza.",
                },
                {
                  valor: "NA_HORA",
                  nome: "Na hora da venda",
                  explica:
                    "Não fica em estoque: a venda produz e baixa no mesmo instante, consumindo os insumos da ficha. É o café passado.",
                },
              ].map((m) => {
                const escolhido = f.modo_producao === m.valor;
                return (
                  <li key={m.valor}>
                    <label
                      className={`flex h-full cursor-pointer items-start gap-3 rounded border p-3.5 ${
                        escolhido ? "border-erva bg-erva-claro" : "border-linha2 bg-superficie"
                      }`}
                    >
                      <input
                        type="radio"
                        name="modo_producao"
                        className="mt-1 h-4 w-4 accent-erva"
                        disabled={!podeEditar}
                        checked={escolhido}
                        onChange={() => set("modo_producao", m.valor)}
                      />
                      <span>
                        <span
                          className={`block text-[14.5px] font-semibold ${
                            escolhido ? "text-erva" : ""
                          }`}
                        >
                          {m.nome}
                        </span>
                        <span className="mt-0.5 block text-[13px] leading-snug text-suave">
                          {m.explica}
                        </span>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </Cartao>

      <Cartao
        titulo="Fornecedores"
        descricao="De quem se compra, com que código e em que embalagem — é o que faz a nota entrar sozinha depois."
        acao={
          podeEditar && fornecedores.length ? (
            <button
              type="button"
              className="btn btn-secundario"
              onClick={() =>
                setVinculos((v) => [
                  ...v,
                  {
                    id_fornecedor: fornecedores.find((x) => !v.some((y) => y.id_fornecedor === x.id))
                      ?.id ?? fornecedores[0].id,
                    codigo_no_fornecedor: "",
                    embalagem: "",
                    fator: 1,
                    ultimo_preco: null,
                    preferencial: v.length === 0,
                  },
                ])
              }
            >
              Vincular fornecedor
            </button>
          ) : undefined
        }
      >
        {!fornecedores.length ? (
          <p className="text-[14.5px] text-suave">
            Nenhum fornecedor cadastrado ainda.{" "}
            <Link href="/fornecedores" className="text-erva underline">
              cadastrar
            </Link>
          </p>
        ) : !vinculos.length ? (
          <p className="text-[14.5px] text-suave">Nenhum fornecedor vinculado a este produto.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {vinculos.map((v, i) => (
              <li key={i} className="grid gap-3 rounded border border-linha p-3 sm:grid-cols-5">
                <label className="sm:col-span-2">
                  <span className="rotulo">Fornecedor</span>
                  <div className="mt-1.5">
                    <BuscaCadastro
                      fonte={FORNECEDORES}
                      disabled={!podeEditar}
                      selecionado={
                        v.id_fornecedor
                          ? {
                              id: v.id_fornecedor,
                              rotulo:
                                v.fornecedor ??
                                fornecedores.find((fo) => fo.id === v.id_fornecedor)?.nome ??
                                "",
                            }
                          : null
                      }
                      aoEscolher={(item: ItemBusca | null) =>
                        setVinculos((l) =>
                          l.map((x, j) =>
                            j === i
                              ? {
                                  ...x,
                                  id_fornecedor: item?.id ?? 0,
                                  fornecedor: item?.nome ?? "",
                                }
                              : x,
                          ),
                        )
                      }
                    />
                  </div>
                </label>
                <label>
                  <span className="rotulo">Código deles</span>
                  <input
                    className="campo mono mt-1.5"
                    disabled={!podeEditar}
                    value={v.codigo_no_fornecedor ?? ""}
                    onChange={(e) =>
                      setVinculos((l) =>
                        l.map((x, j) =>
                          j === i ? { ...x, codigo_no_fornecedor: e.target.value } : x,
                        ),
                      )
                    }
                  />
                </label>
                <label>
                  <span className="rotulo">Embalagem</span>
                  <input
                    className="campo mt-1.5"
                    placeholder="cx 12 un"
                    disabled={!podeEditar}
                    value={v.embalagem ?? ""}
                    onChange={(e) =>
                      setVinculos((l) =>
                        l.map((x, j) => (j === i ? { ...x, embalagem: e.target.value } : x)),
                      )
                    }
                  />
                </label>
                <div className="flex items-end justify-between gap-2">
                  <label className="flex items-center gap-2 pb-2">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-erva"
                      disabled={!podeEditar}
                      checked={v.preferencial}
                      onChange={(e) =>
                        setVinculos((l) =>
                          l.map((x, j) => ({
                            ...x,
                            preferencial: j === i ? e.target.checked : false,
                          })),
                        )
                      }
                    />
                    <span className="text-[13.5px]">principal</span>
                  </label>
                  {podeEditar && (
                    <button
                      type="button"
                      className="link-acao link-acao-erro mb-2"
                      onClick={() => setVinculos((l) => l.filter((_, j) => j !== i))}
                    >
                      remover
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Cartao>

      {/* 🔑 As prateleiras onde o produto mora — e o cartão aparece TAMBÉM na
          tela de criar, porque é ali que a pessoa está decidindo isso. Só para
          quem controla estoque: produto que não controla não tem prateleira. */}
      {f.controla_estoque && (
        <LocaisDoProduto
          idProduto={novo ? null : Number(id)}
          podeEditar={podeEditar}
          podeVerCusto={pode("estoque.saldos")}
          umEstoque={f.um_estoque || null}
          pendentes={locaisPendentes}
          aoMudarPendentes={setLocaisPendentes}
        />
      )}

      {/* A conversão também só existe depois do produto: ela aponta para ele. */}
      {!novo && f.controla_estoque && (
        <UnidadesDeCompra
          idProduto={Number(id)}
          umEstoque={f.um_estoque || null}
          podeEditar={podeEditar}
        />
      )}

      {/* Combo só faz sentido depois de o produto existir: a composição aponta
          para ele, e produto novo ainda não tem id. */}
      {!novo && f.tipo === "KIT" && (
        <ComposicaoKit
          idProduto={Number(id)}
          podeEditar={podeEditar}
          podeVerCusto={pode("fichas.custos")}
        />
      )}

      <Cartao titulo="Observações">
        <textarea
          className="campo min-h-[90px]"
          disabled={!podeEditar}
          value={f.observacao}
          onChange={(e) => set("observacao", e.target.value)}
        />
        {!novo && podeEditar && (
          <label className="mt-4 flex items-center gap-2">
            <input
              type="checkbox"
              className="h-4 w-4 accent-erva"
              checked={f.ativo}
              onChange={(e) => set("ativo", e.target.checked)}
            />
            <span className="text-[14px]">
              produto ativo <span className="text-suave">— inativo some das listas e das buscas</span>
            </span>
          </label>
        )}
      </Cartao>

      {podeEditar && (
        <div className="flex justify-end gap-2">
          <Link href="/produtos" className="btn btn-secundario">
            Voltar
          </Link>
          <button className="btn btn-primario" type="submit" disabled={salvando}>
            {salvando ? "Salvando…" : novo ? "Criar produto" : "Salvar"}
          </button>
        </div>
      )}
    </form>
  );
}
