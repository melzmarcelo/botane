"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { api, ErroApi, urlArquivo } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { ProdutoResumo, UnidadeMedida, reais } from "@/lib/cadastros";
import BotaoExportar from "@/components/exportar";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, FonteBusca, ItemBusca } from "@/lib/busca-cadastro";
import Voltar from "@/components/voltar";
import DuplicarFicha from "./duplicar";
import DestinosDaFicha from "./destinos";

import { custo, qtd } from "@/lib/numeros";
type Item = {
  id_insumo: number | null;
  id_subficha: number | null;
  nome?: string;
  qtd_bruta: string;
  qtd_liquida: string;
  um: string;
  fator_coccao: string;
  observacao: string;
  custo_total?: number | null;
  custo_unitario?: number | null;
  origem_custo?: string;
  aviso?: string | null;
  qtd_estoque?: number | null;
  conversao?: string | null;
  um_estoque?: string | null;
};

type Ficha = {
  id: number;
  id_produto: number;
  produto: string;
  codigo: string;
  versao: number;
  status: string;
  rendimento_qtd: number;
  rendimento_um: string | null;
  porcoes: number;
  /** Quanto vale uma porção, na unidade do rendimento. Nulo = ninguém informou. */
  porcao_qtd: number | null;
  tempo_preparo_min: number | null;
  modo_preparo: string | null;
  alergenos: string | null;
  observacao: string | null;
  foto_url: string | null;
  homologada_por: string | null;
  itens: Record<string, unknown>[];
  custo_total: number | null;
  custo_por_porcao: number | null;
  itens_sem_custo: number | null;
  custo_completo: boolean | null;
  ve_custo: boolean;
};

type FichaListada = { id: number; id_produto: number; produto: string; versao: number; status: string };

const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));
const texto = (v: string) => (v.trim() === "" ? null : v.trim());

const ITEM_VAZIO: Item = {
  id_insumo: null, id_subficha: null, qtd_bruta: "", qtd_liquida: "", um: "",
  fator_coccao: "1", observacao: "",
};

export default function EditorFicha() {
  const aviso = useAviso();
  const { id } = useParams<{ id: string }>();
  const nova = id === "nova";
  const router = useRouter();
  const { pode } = useSessao();
  const podeEditar = pode("fichas.editar");
  const podeHomologar = pode("fichas.homologar");
  const veCusto = pode("fichas.custos");

  const [ficha, setFicha] = useState<Ficha | null>(null);
  const [idProduto, setIdProduto] = useState("");
  const [rotuloProduto, setRotuloProduto] = useState("");
  const [cabecalho, setCabecalho] = useState({
    rendimento_qtd: "1", rendimento_um: "", porcoes: "1", porcao_qtd: "",
    tempo_preparo_min: "",
    modo_preparo: "", alergenos: "", observacao: "",
  });
  const [itens, setItens] = useState<Item[]>([{ ...ITEM_VAZIO }]);
  const [fichas, setFichas] = useState<FichaListada[]>([]);
  const [enviandoFoto, setEnviandoFoto] = useState(false);
  /**
   * 🔑 **A soma dos ingredientes, como SUGESTÃO** (12/09/2026, pedido do dono:
   * *"de onde vem o rendimento? tem como ser gerado automaticamente? o sistema
   * que a cliente usa soma todos os ingredientes"*).
   *
   * ⚠️ **Sugestão, nunca escrita sozinha.** `rendimento_qtd` DIVIDE o consumo na
   * produção (`lotes = quantidade ÷ rendimento`): recalcular ao salvar mudaria o
   * custo unitário de tudo que a ficha produz, calado. E há receita em que a soma
   * não é o rendimento — massa que descansa, calda que reduz de propósito. Quem
   * decide é quem lê; o botão "usar" é de um clique.
   *
   * ⚠️ **A conta vem do SERVIDOR** (`POST /fichas/rendimento-sugerido`): converter
   * G/ML/UN aqui seria uma segunda régua de conversão, e ela divergiria da do
   * motor de custos no primeiro ajuste.
   */
  const [sugestao, setSugestao] = useState<{
    qtd: number;
    um: string;
    itens_fora: { nome: string; um: string | null }[];
    assumiu_densidade: boolean;
  } | null>(null);
  const seletorFoto = useRef<HTMLInputElement>(null);
  // 🔑 **Na tela de CRIAR a ficha ainda não tem id, e a foto não teria para
  // onde ir.** A primeira versão simplesmente escondia o cartão ali — e quem
  // estava cadastrando o prato, com a foto na mão, não achava onde pôr. Agora
  // a imagem fica guardada aqui e sobe assim que a ficha nasce.
  const [fotoPendente, setFotoPendente] = useState<File | null>(null);
  const [previaFoto, setPrevia] = useState<string | null>(null);
  const [ums, setUms] = useState<UnidadeMedida[]>([]);
  const [carregando, setCarregando] = useState(!nova);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<UnidadeMedida[]>("/unidades-medida"),
      api.get<FichaListada[]>("/fichas"),
    ])
      .then(([u, fs]) => {
        setUms(u);
        setFichas(fs);
      })
      .catch((e) => setErro(e.message));
  }, []);

  const carregar = async () => {
    const f = await api.get<Ficha>(`/fichas/${id}`);
    setFicha(f);
    setIdProduto(String(f.id_produto));
    setCabecalho({
      rendimento_qtd: String(f.rendimento_qtd ?? 1),
      rendimento_um: f.rendimento_um ?? "",
      porcoes: String(f.porcoes ?? 1),
      porcao_qtd: f.porcao_qtd === null || f.porcao_qtd === undefined
        ? "" : String(f.porcao_qtd),
      tempo_preparo_min: f.tempo_preparo_min?.toString() ?? "",
      modo_preparo: f.modo_preparo ?? "",
      alergenos: f.alergenos ?? "",
      observacao: f.observacao ?? "",
    });
    setItens(
      f.itens.map((i) => ({
        id_insumo: (i.id_insumo as number) ?? null,
        id_subficha: (i.id_subficha as number) ?? null,
        nome: i.nome as string,
        qtd_bruta: String(i.qtd_bruta ?? ""),
        qtd_liquida: i.qtd_liquida === null || i.qtd_liquida === undefined ? "" : String(i.qtd_liquida),
        um: (i.um as string) ?? "",
        fator_coccao: String(i.fator_coccao ?? 1),
        observacao: (i.observacao as string) ?? "",
        custo_total: i.custo_total as number | null,
        custo_unitario: i.custo_unitario as number | null,
        origem_custo: i.origem_custo as string,
        aviso: i.aviso as string | null,
        qtd_estoque: i.qtd_estoque as number | null,
        conversao: i.conversao as string | null,
        um_estoque: i.um_estoque as string | null,
      })),
    );
  };

  useEffect(() => {
    if (nova) return;
    carregar()
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, nova]);

  const travada = ficha?.status === "HOMOLOGADA" || ficha?.status === "ARQUIVADA";
  const editavel = podeEditar && !travada;

  // A prévia local do arquivo escolhido, antes de existir URL no servidor.
  // ⚠️ `revokeObjectURL` na limpeza: sem ele cada troca de arquivo deixa um
  // blob preso na memória da aba.
  useEffect(() => {
    if (!fotoPendente) {
      setPrevia(null);
      return;
    }
    const url = URL.createObjectURL(fotoPendente);
    setPrevia(url);
    return () => URL.revokeObjectURL(url);
  }, [fotoPendente]);

  /** 🔑 A foto do prato pronto — o que a cozinha compara com o que está na mão.

      ⚠️ Vale mesmo com a ficha HOMOLOGADA, ao contrário do resto do formulário.
      O prato só pode ser fotografado depois de feito, e ele é feito depois de a
      ficha ser publicada: exigir uma versão nova para pendurar a imagem criaria
      uma versão que não difere em nada, e cada versão carrega custo histórico. */
  async function enviarFoto(arquivo: File) {
    setEnviandoFoto(true);
    try {
      const corpo = new FormData();
      corpo.append("arquivo", arquivo);
      const r = await api.upload<{ foto_url: string }>(`/fichas/${id}/foto`, corpo);
      setFicha((f) => (f ? { ...f, foto_url: r.foto_url } : f));
      aviso.sucesso("Foto atualizada.");
    } catch (err) {
      aviso.erro(err instanceof ErroApi ? err.message : "Não foi possível enviar a imagem");
    } finally {
      setEnviandoFoto(false);
      // Sem isto, escolher o MESMO arquivo de novo não dispara o `change`.
      if (seletorFoto.current) seletorFoto.current.value = "";
    }
  }

  async function removerFoto() {
    try {
      await api.delete(`/fichas/${id}/foto`);
      setFicha((f) => (f ? { ...f, foto_url: null } : f));
      aviso.sucesso("Foto removida.");
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível remover");
    }
  }

  const corpoItens = () =>
    itens
      .filter((i) => (i.id_insumo || i.id_subficha) && num(i.qtd_bruta))
      .map((i, ordem) => ({
        id_insumo: i.id_insumo,
        id_subficha: i.id_subficha,
        qtd_bruta: num(i.qtd_bruta),
        qtd_liquida: num(i.qtd_liquida),
        um: texto(i.um),
        fator_coccao: num(i.fator_coccao) ?? 1,
        observacao: texto(i.observacao),
        ordem,
      }));

  // ⚠️ **Debounce, e só com o que já dá para somar.** A pessoa digita "2", "25",
  // "250" no mesmo campo: pedir a cada tecla seria três pedidos e duas respostas
  // fora de ordem. E sem item nenhum não há soma — o cartão não mostra nada em
  // vez de mostrar zero, que pareceria uma afirmação.
  useEffect(() => {
    if (!editavel) return;
    const corpo = corpoItens();
    if (!corpo.length) {
      setSugestao(null);
      return;
    }
    let valeu = true;
    const t = setTimeout(() => {
      api
        .post<typeof sugestao>("/fichas/rendimento-sugerido", {
          itens: corpo,
          um: texto(cabecalho.rendimento_um),
        })
        .then((r) => valeu && setSugestao(r))
        .catch(() => valeu && setSugestao(null));
    }, 600);
    return () => {
      valeu = false;
      clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editavel, JSON.stringify(itens), cabecalho.rendimento_um]);

  /** Porções e tamanho da porção são o MESMO dado visto de dois lados.
   *
   * 🔑 **Pedido do dono:** *"hoje temos somente a quantidade de porções, mas
   * podemos ter ao contrário: informar os gramas/kg/un e ele calcular quantas
   * porções rende"*.
   *
   * ⚠️ **Mexer num recalcula o OUTRO, e só na digitação.** Fazer isso num efeito
   * sobre os três campos criaria ida e volta: porções mexe no tamanho, que mexe
   * nas porções. Aqui cada mão escreve uma vez.
   * ⚠️ **Trocar o rendimento mantém o TAMANHO e refaz as porções** — quando o
   * tamanho foi informado. É o que a cozinha fixa: mais massa não muda a fatia,
   * muda quantas fatias saem.
   */
  function mudarRendimento(valor: string) {
    setCabecalho((c) => {
      const tamanho = num(c.porcao_qtd);
      const rend = num(valor);
      if (!tamanho || !rend) return { ...c, rendimento_qtd: valor };
      const porcoes = Math.round((rend / tamanho) * 100) / 100;
      return { ...c, rendimento_qtd: valor, porcoes: porcoes > 0 ? String(porcoes) : c.porcoes };
    });
  }

  function mudarPorcoes(valor: string) {
    setCabecalho((c) => {
      const rend = num(c.rendimento_qtd);
      const porcoes = num(valor);
      if (!rend || !porcoes) return { ...c, porcoes: valor };
      const tamanho = Math.round((rend / porcoes) * 10000) / 10000;
      return { ...c, porcoes: valor, porcao_qtd: tamanho > 0 ? String(tamanho) : "" };
    });
  }

  function mudarPorcao(valor: string) {
    setCabecalho((c) => {
      const rend = num(c.rendimento_qtd);
      const tamanho = num(valor);
      if (!rend || !tamanho) return { ...c, porcao_qtd: valor };
      const porcoes = Math.round((rend / tamanho) * 100) / 100;
      return { ...c, porcao_qtd: valor, porcoes: porcoes > 0 ? String(porcoes) : c.porcoes };
    });
  }

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    const corpo = {
      rendimento_qtd: num(cabecalho.rendimento_qtd) ?? 1,
      rendimento_um: texto(cabecalho.rendimento_um),
      porcoes: num(cabecalho.porcoes) ?? 1,
      // ⚠️ Vazio vai como NULO, não como 1: "ninguém informou o tamanho" é
      // diferente de "a porção vale uma unidade".
      porcao_qtd: num(cabecalho.porcao_qtd),
      tempo_preparo_min: num(cabecalho.tempo_preparo_min),
      modo_preparo: texto(cabecalho.modo_preparo),
      alergenos: texto(cabecalho.alergenos),
      observacao: texto(cabecalho.observacao),
      itens: corpoItens(),
    };
    try {
      if (nova) {
        const r = await api.post<{ id: number }>("/fichas", {
          ...corpo,
          id_produto: Number(idProduto),
        });
        // ⚠️ **A ficha JÁ EXISTE daqui em diante.** Se o envio da foto falhar,
        // a mensagem tem de dizer isso — "não foi possível salvar" mandaria a
        // pessoa cadastrar tudo de novo e criaria uma segunda ficha do mesmo
        // prato. Por isso o try é só do upload, e a frase é outra.
        if (fotoPendente) {
          try {
            const fd = new FormData();
            fd.append("arquivo", fotoPendente);
            await api.upload(`/fichas/${r.id}/foto`, fd);
            setFotoPendente(null);
          } catch (errFoto) {
            aviso.erro(
              `Ficha criada, mas a foto não subiu: ${
                errFoto instanceof Error ? errFoto.message : "falha no envio"
              }. Envie de novo na tela da ficha.`,
            );
          }
        }
        router.replace(`/fichas/${r.id}`);
        // Criar uma ficha e não dizer nada era o pior caso: a tela trocava de
        // endereço e nada confirmava que gravou.
        aviso.sucesso("Ficha criada.", {
          texto: "criar outra",
          ao: () => router.push("/fichas/nova"),
        });
      } else {
        await api.put(`/fichas/${id}`, corpo);
        await carregar();
        aviso.sucesso("Ficha salva.");
      }
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function acao(caminho: string, mensagem: string, irPara?: (r: { id: number }) => string) {
    setErro("");
    try {
      const r = await api.post<{ id: number }>(`/fichas/${id}/${caminho}`);
      if (irPara) router.push(irPara(r));
      else {
        await carregar();
        aviso.sucesso(mensagem);
      }
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível concluir");
    }
  }

  const opcoesSubficha = useMemo(
    () => fichas.filter((f) => String(f.id) !== id && f.status !== "ARQUIVADA"),
    [fichas, id],
  );

  /**
   * A linha da ficha aceita duas coisas: um insumo do cadastro ou um preparo
   * com ficha própria. Os insumos são muitos e vêm do servidor; os preparos são
   * poucos e já estão carregados — a busca junta os dois numa lista só.
   *
   * ⚠️ O id do preparo entra NEGATIVO. É o que deixa produto 5 e ficha 5
   * conviverem na mesma lista sem se confundirem, e decodificar é só olhar o
   * sinal.
   */
  /**
   * O que esta ficha PRODUZ — só produto produzido, buscado no servidor.
   *
   * ⚠️ O filtro do tipo vai como parâmetro da consulta (`extra`), não como
   * peneira no navegador: filtrar depois cortaria a página trazida e a busca
   * diria "nenhum resultado" para um prato que existe na página seguinte.
   */
  const fonteProduzidos = useMemo<FonteBusca>(
    () => ({
      ...fonteProdutos("tipo=PRODUZIDO"),
      titulo: "Buscar produto produzido",
      singular: "produto",
    }),
    [],
  );

  const fonteInsumoOuPreparo = useMemo<FonteBusca>(() => {
    const produtos = fonteProdutos("controla_estoque=true");
    return {
      titulo: "Buscar insumo ou preparo",
      placeholder: "código ou nome",
      singular: "insumo",
      // ⚠️ **Fonte COMPOSTA: preparos em memoria + produtos do servidor.** Ela
      // ignorava o `offset` e repetia os preparos em TODA pagina — na pagina 2
      // apareceriam de novo, empurrando os produtos e mentindo o total. Agora os
      // preparos entram so na primeira pagina, e o deslocamento dos produtos
      // desconta o espaco que eles ocuparam.
      async buscar(termo, limite, offset = 0) {
        const alvo = termo.trim().toLowerCase();
        const preparos: ItemBusca[] = opcoesSubficha
          .filter((f) => !alvo || (f.produto ?? "").toLowerCase().includes(alvo))
          .map((f) => ({
            id: -f.id,
            codigo: null,
            nome: f.produto,
            detalhe: `preparo com ficha · v${f.versao}`,
          }));
        const naPrimeira = offset === 0 ? preparos : [];
        const r = await produtos.buscar(
          termo,
          limite - naPrimeira.length,
          Math.max(0, offset - preparos.length),
        );
        return {
          itens: [...naPrimeira, ...r.itens],
          // ⚠️ Nulo continua nulo: e "o servidor nao disse", e quem chama guarda
          // o que ja tinha. Somar os preparos a um nulo daria o numero deles.
          total: r.total === null ? null : r.total + preparos.length,
        };
      },
    };
  }, [opcoesSubficha]);

  if (carregando) return <Carregando />;

  return (
    <form onSubmit={salvar} className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Voltar href="/fichas">
            fichas técnicas
          </Voltar>
          <h1 className="mt-1 break-words text-[26px] font-bold tracking-tight sm:text-[30px]">
            {nova ? "Nova ficha" : ficha?.produto}
          </h1>
          {ficha && (
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <Etiqueta>v{ficha.versao}</Etiqueta>
              <Etiqueta cor={ficha.status === "HOMOLOGADA" ? "erva" : "alerta"}>
                {ficha.status.toLowerCase()}
              </Etiqueta>
              {ficha.homologada_por && (
                <span className="text-[13px] text-suave">por {ficha.homologada_por}</span>
              )}
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {/* ⚠️ A ficha existe para ser SEGUIDA, e quem segue está de pé na
              cozinha — não na frente do monitor. Sem o papel, a receita fica
              presa numa tela que ninguém leva para perto do fogão.
              O custo NÃO sai para quem não tem `fichas.custos`: quem esconde é
              o servidor, senão o PDF viraria a porta lateral que a regra do
              router de fichas existe para fechar. */}
          {!nova && ficha && (
            <BotaoExportar
              relatorio={`ficha/${ficha.id}`}
              rotulo="Imprimir ficha"
              formatoPadrao="pdf"
              avulso={{
                rotulo: `Ficha técnica — ${ficha.produto}`,
                descricao:
                  "O cartão da receita, para pendurar na cozinha. Em PDF sai pronto para imprimir.",
              }}
            />
          )}
          {!nova && podeEditar && travada && (
            <button
              type="button"
              className="btn btn-secundario"
              onClick={() => acao("nova-versao", "", (r) => `/fichas/${r.id}`)}
            >
              Criar nova versão
            </button>
          )}
          {/* ⚠️ **Aparece em rascunho TAMBÉM**, ao contrário de "nova versão":
              copiar não muda esta ficha, e a base de uma receita nova costuma
              estar justamente na que ainda se está escrevendo. */}
          {!nova && podeEditar && ficha && (
            <DuplicarFicha
              idFicha={ficha.id}
              produtoAtual={ficha.produto}
              fichasDoSistema={fichas}
            />
          )}
          {!nova && podeHomologar && ficha?.status === "RASCUNHO" && (
            <button
              type="button"
              className="btn btn-secundario"
              onClick={() => acao("homologar", "Ficha homologada — agora é a versão em uso.")}
            >
              Homologar
            </button>
          )}
          {editavel && (
            <button className="btn btn-primario" type="submit" disabled={salvando}>
              {salvando ? "Salvando…" : nova ? "Criar ficha" : "Salvar"}
            </button>
          )}
        </div>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {travada && (
        <Aviso tipo="info">
          {ficha?.status === "HOMOLOGADA"
            ? "Ficha homologada não é editável — mudar a receita publicada mudaria o custo já apurado. Crie uma nova versão."
            : "Ficha arquivada: só leitura."}
        </Aviso>
      )}
      {!podeEditar && <Aviso tipo="info">Você tem acesso de leitura às fichas.</Aviso>}

      <Cartao titulo="O que esta ficha produz">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* ⚠️ **BUSCA, não `<select>`.** A lista vinha de
              `/produtos?tipo=PRODUZIDO` e o endpoint pagina: eram os 200
              primeiros em ordem alfabética. Enquanto a casa tinha dezenas de
              pratos ninguém notou; ao importar o cardápio do PDV (627 itens), o
              prato que se queria virou invisível — e o pior é que o `<select>`
              não tem como dizer isso. A tela ficava certa, o produto simplesmente
              não estava lá, e o formulário recusava salvar sem explicar.
              Produto NÃO é "poucos por natureza": é exatamente o caso para que
              `BuscaCadastro` existe. */}
          <Campo rotulo="Produto" className="lg:col-span-2">
            {nova ? (
              <BuscaCadastro
                fonte={fonteProduzidos}
                required
                selecionado={
                  idProduto ? { id: Number(idProduto), rotulo: rotuloProduto } : null
                }
                aoEscolher={(item: ItemBusca | null) => {
                  setIdProduto(item ? String(item.id) : "");
                  setRotuloProduto(item ? rotuloDe(item) : "");
                }}
              />
            ) : (
              <input className="campo" value={ficha?.produto ?? ""} disabled />
            )}
          </Campo>
          <Campo rotulo="Rendimento" dica="quanto sai da receita inteira">
            <div className="flex gap-2">
              <input
                className="campo mono"
                type="number"
                step="0.001"
                min="0.001"
                disabled={!editavel}
                aria-label="Rendimento da receita"
                value={cabecalho.rendimento_qtd}
                onChange={(e) => mudarRendimento(e.target.value)}
              />
              <select
                className="campo w-[110px]"
                disabled={!editavel}
                value={cabecalho.rendimento_um}
                onChange={(e) => setCabecalho({ ...cabecalho, rendimento_um: e.target.value })}
              >
                <option value="">un.</option>
                {ums.map((u) => (
                  <option key={u.sigla} value={u.sigla}>
                    {u.sigla}
                  </option>
                ))}
              </select>
            </div>
            {/* 🔑 **De onde vem o rendimento**: da soma dos ingredientes, quando
                eles sabem dizer. Fica ao lado do campo, com o número à vista e um
                clique para usar — nunca escrito sozinho. */}
            {sugestao && sugestao.qtd > 0 && (
              <p className="mt-1.5 text-[12.5px] leading-snug text-suave">
                A soma dos ingredientes dá{" "}
                <b className="mono text-tinta">
                  {qtd(sugestao.qtd)} {sugestao.um}
                </b>
                {editavel && (
                  <>
                    {" · "}
                    <button
                      type="button"
                      className="link-acao"
                      onClick={() =>
                        mudarRendimento(String(sugestao.qtd).replace(",", "."))
                      }
                    >
                      usar
                    </button>
                  </>
                )}
                {sugestao.assumiu_densidade && (
                  <span className="block">
                    considerando <b>1 ML = 1 G</b> nos líquidos.
                  </span>
                )}
                {sugestao.itens_fora.length > 0 && (
                  <span className="block text-alerta">
                    fora da conta:{" "}
                    {sugestao.itens_fora.map((x) => `${x.nome} (${x.um ?? "—"})`).join(", ")} —
                    cadastre o peso de uma unidade no produto para ele entrar.
                  </span>
                )}
              </p>
            )}
          </Campo>
          <Campo rotulo="Porções" dica="divide o custo total">
            <input
              className="campo mono"
              type="number"
              step="0.01"
              min="0.01"
              disabled={!editavel}
              aria-label="Porções da receita"
              value={cabecalho.porcoes}
              onChange={(e) => mudarPorcoes(e.target.value)}
            />
          </Campo>
          {/* 🔑 **A conta nos dois sentidos** (pedido do dono, 12/09/2026): com o
              tamanho da porção, informar o rendimento dá as porções — e informar
              as porções dá o tamanho. Um é o outro de cabeça para baixo.
              ⚠️ Vazio mostra o valor DERIVADO como sugestão do campo, sem gravar:
              nulo quer dizer "ninguém informou". */}
          <Campo
            rotulo="Cada porção tem"
            dica={`na unidade do rendimento${cabecalho.rendimento_um ? ` (${cabecalho.rendimento_um})` : ""}`}
          >
            <input
              className="campo mono"
              type="number"
              step="0.0001"
              min="0.0001"
              disabled={!editavel}
              aria-label="Tamanho da porção"
              value={cabecalho.porcao_qtd}
              placeholder={
                num(cabecalho.rendimento_qtd) && num(cabecalho.porcoes)
                  ? String(
                      Math.round(
                        (num(cabecalho.rendimento_qtd)! / num(cabecalho.porcoes)!) * 10000,
                      ) / 10000,
                    ).replace(".", ",")
                  : ""
              }
              onChange={(e) => mudarPorcao(e.target.value)}
            />
          </Campo>
        </div>
      </Cartao>

      <Cartao
        titulo="Ingredientes"
        descricao="A quantidade bruta é a que sai do estoque — é ela que custa. A líquida é o que sobra depois de limpar."
        acao={
          editavel ? (
            <button
              type="button"
              className="btn btn-secundario"
              onClick={() => setItens((l) => [...l, { ...ITEM_VAZIO }])}
            >
              Adicionar linha
            </button>
          ) : undefined
        }
      >
        <div className="flex flex-col gap-3">
          {itens.map((item, i) => {
            const alvo = item.id_subficha ? `sub:${item.id_subficha}` : item.id_insumo ? `ins:${item.id_insumo}` : "";
            const fc =
              num(item.qtd_bruta) && num(item.qtd_liquida)
                ? (num(item.qtd_bruta)! / num(item.qtd_liquida)!).toFixed(3)
                : null;
            return (
              <div key={i} className="rounded border border-linha p-3">
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_90px_90px_90px_auto]">
                  <div className="min-w-0">
                    <span className="rotulo">Insumo ou preparo</span>
                    <div className="mt-1.5">
                      {/* Ficha homologada é para LER: a cozinha quer o nome do
                          insumo, não um campo de busca desabilitado — e texto
                          dentro de input não é texto para quem lê a tela. */}
                      {!editavel ? (
                        <p className="py-1.5 text-[15px] font-medium">
                          {item.nome || "—"}
                        </p>
                      ) : (
                      <BuscaCadastro
                        fonte={fonteInsumoOuPreparo}
                        selecionado={
                          alvo
                            ? {
                                id: item.id_subficha ? -item.id_subficha : item.id_insumo!,
                                rotulo: item.nome ?? "",
                              }
                            : null
                        }
                        aoEscolher={(escolhido: ItemBusca | null) =>
                          setItens((l) =>
                            l.map((x, j) =>
                              j === i
                                ? {
                                    ...x,
                                    // Negativo é preparo; positivo é insumo.
                                    id_insumo:
                                      escolhido && escolhido.id > 0 ? escolhido.id : null,
                                    id_subficha:
                                      escolhido && escolhido.id < 0 ? -escolhido.id : null,
                                    nome: escolhido?.nome ?? "",
                                  }
                                : x,
                            ),
                          )
                        }
                      />
                      )}
                    </div>
                  </div>
                  <label>
                    <span className="rotulo">Bruta</span>
                    <input
                      className="campo mono mt-1.5"
                      type="number"
                      step="0.0001"
                      min="0"
                      disabled={!editavel}
                      aria-label={`Quantidade bruta do item ${i + 1}`}
                      value={item.qtd_bruta}
                      onChange={(e) =>
                        setItens((l) =>
                          l.map((x, j) => (j === i ? { ...x, qtd_bruta: e.target.value } : x)),
                        )
                      }
                    />
                  </label>
                  <label>
                    <span className="rotulo">Líquida</span>
                    <input
                      className="campo mono mt-1.5"
                      type="number"
                      step="0.0001"
                      min="0"
                      disabled={!editavel}
                      aria-label={`Quantidade líquida do item ${i + 1}`}
                      value={item.qtd_liquida}
                      onChange={(e) =>
                        setItens((l) =>
                          l.map((x, j) => (j === i ? { ...x, qtd_liquida: e.target.value } : x)),
                        )
                      }
                    />
                  </label>
                  <label>
                    <span className="rotulo">Unidade</span>
                    <select
                      className="campo mt-1.5"
                      disabled={!editavel}
                      value={item.um}
                      onChange={(e) =>
                        setItens((l) =>
                          l.map((x, j) => (j === i ? { ...x, um: e.target.value } : x)),
                        )
                      }
                    >
                      <option value="">—</option>
                      {ums.map((u) => (
                        <option key={u.sigla} value={u.sigla}>
                          {u.sigla}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="flex items-end justify-between gap-3 lg:flex-col lg:items-end lg:justify-end">
                    {veCusto && (
                      <span className="mono pb-2 text-[14px]">
                        {item.custo_total !== null && item.custo_total !== undefined
                          ? custo(Number(item.custo_total))
                          : "—"}
                      </span>
                    )}
                    {editavel && (
                      <button
                        type="button"
                        className="link-acao link-acao-erro mb-2"
                        onClick={() => setItens((l) => l.filter((_, j) => j !== i))}
                      >
                        remover
                      </button>
                    )}
                  </div>
                </div>

                <div className="mt-2 flex flex-wrap items-center gap-3 text-[12.5px] text-suave">
                  {fc && (
                    <span>
                      fator de correção <b className="mono text-tinta">{fc}</b>
                    </span>
                  )}
                  {/* Quanto a receita tira do estoque. A receita fala em caixa,
                      o razão baixa pacote — sem isto à vista, a diferença só
                      aparece no inventário do fim do mês. */}
                  {item.conversao && item.conversao !== "mesma" && item.qtd_estoque != null && (
                    <span>
                      no estoque{" "}
                      <b className="mono text-tinta">
                        {qtd(item.qtd_estoque)}{" "}
                        {item.um_estoque}
                      </b>
                    </span>
                  )}
                  {veCusto && item.origem_custo === "sem_custo" && (
                    <span className="text-alerta">sem preço conhecido</span>
                  )}
                  {veCusto && item.origem_custo === "subficha_incompleta" && (
                    <span className="text-alerta">a sub-ficha tem item sem preço</span>
                  )}
                  {item.aviso && <span className="text-erro">{item.aviso}</span>}
                  {/* 🔑 **O fator de cocção finalmente tem onde ser digitado.** A
                      coluna existe desde a migração 006 com "muda rendimento, não
                      custo" escrito nela, e a tela nunca a ofereceu: ficava 1 em
                      toda ficha. Bolo perde água no forno (0,88), arroz ganha
                      (2,5) — sem isso a soma dos ingredientes dá o rendimento
                      CRU. ⚠️ Não entra no custo, como a coluna sempre disse: o
                      custo é do que saiu do estoque. */}
                  <label className="flex items-center gap-1.5">
                    <span>cocção</span>
                    <input
                      className="campo mono w-[76px] py-1 text-right text-[13px]"
                      type="number"
                      step="0.01"
                      min="0.01"
                      disabled={!editavel}
                      aria-label={`fator de cocção de ${item.nome || "item"}`}
                      value={item.fator_coccao}
                      onChange={(e) =>
                        setItens((l) =>
                          l.map((x, j) => (j === i ? { ...x, fator_coccao: e.target.value } : x)),
                        )
                      }
                    />
                  </label>
                  <input
                    className="campo ml-auto max-w-[280px] py-1 text-[13px]"
                    placeholder="observação da linha"
                    disabled={!editavel}
                    value={item.observacao}
                    onChange={(e) =>
                      setItens((l) =>
                        l.map((x, j) => (j === i ? { ...x, observacao: e.target.value } : x)),
                      )
                    }
                  />
                </div>
              </div>
            );
          })}
        </div>

        {veCusto && ficha && (
          <div className="mt-5 grid gap-px overflow-hidden rounded border border-linha bg-linha sm:grid-cols-3">
            {[
              { rotulo: "Custo da receita", valor: ficha.custo_total },
              { rotulo: "Custo por porção", valor: ficha.custo_por_porcao, destaque: true },
              {
                rotulo: `Por ${ficha.rendimento_um ?? "unidade"} rendida`,
                valor:
                  ficha.custo_total !== null && ficha.rendimento_qtd
                    ? Number(ficha.custo_total) / Number(ficha.rendimento_qtd)
                    : null,
              },
            ].map((c) => (
              <div key={c.rotulo} className="bg-superficie p-4">
                <p className="rotulo">{c.rotulo}</p>
                <p
                  className={`mono mt-1 text-[19px] ${c.destaque ? "font-bold text-erva" : ""}`}
                >
                  {c.valor !== null && c.valor !== undefined ? custo(Number(c.valor)) : "—"}
                </p>
              </div>
            ))}
            {ficha.custo_completo === false && (
              <p className="bg-superficie px-4 pb-4 text-[13px] text-alerta sm:col-span-3">
                {ficha.itens_sem_custo} item(ns) sem preço conhecido — o total acima é parcial.
                O preço vem da última compra registrada no fornecedor.
              </p>
            )}
          </div>
        )}
      </Cartao>

      {/* 🔑 **Os destinos da receita** (migração 066, pedido do dono). Só em
          ficha que já existe: o destino aponta para uma prateleira e precisa do
          id da ficha para ser gravado — numa ficha nova não há onde pendurá-lo.
          ⚠️ Fica DEPOIS dos ingredientes: o rendimento por destino só faz sentido
          quando já se sabe o que a receita leva. */}
      {!nova && ficha && (
        <DestinosDaFicha
          idFicha={ficha.id}
          rendimentoDaFicha={Number(ficha.rendimento_qtd ?? 1)}
          um={ficha.rendimento_um}
          editavel={editavel}
          aoGravar={() => void carregar()}
        />
      )}

      <Cartao titulo="Preparo">
        <div className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo rotulo="Tempo de preparo (min)">
              <input
                className="campo mono"
                type="number"
                min="0"
                disabled={!editavel}
                value={cabecalho.tempo_preparo_min}
                onChange={(e) =>
                  setCabecalho({ ...cabecalho, tempo_preparo_min: e.target.value })
                }
              />
            </Campo>
            <Campo rotulo="Alérgenos" dica="glúten, lactose, castanhas…">
              <input
                className="campo"
                disabled={!editavel}
                value={cabecalho.alergenos}
                onChange={(e) => setCabecalho({ ...cabecalho, alergenos: e.target.value })}
              />
            </Campo>
          </div>
          <Campo rotulo="Modo de preparo">
            <textarea
              className="campo min-h-[140px]"
              disabled={!editavel}
              value={cabecalho.modo_preparo}
              onChange={(e) => setCabecalho({ ...cabecalho, modo_preparo: e.target.value })}
            />
          </Campo>
        </div>
      </Cartao>

      {/* 🔑 **A foto do prato pronto.** A ficha existe para ser SEGUIDA, e
          quem segue está de pé na cozinha: "está pronto?" é uma pergunta
          visual, e nenhuma descrição de montagem responde o que a imagem
          responde. Ela sai junto no PDF, que é o papel que fica pendurado.
          ⚠️ **O cartão aparece TAMBÉM ao criar a ficha.** Ele já esteve escondido
          ali, porque a ficha ainda não tem id e a foto não teria para onde ir —
          e quem estava cadastrando o prato, com a foto na mão, não achava onde
          pô-la. Agora a imagem fica guardada e sobe assim que a ficha nasce. */}
      <Cartao
        titulo="Foto do prato"
        descricao={
          nova
            ? "Como ele deve chegar à mesa. Ela sobe junto quando você criar a ficha."
            : "Como ele deve chegar à mesa. Sai junto na ficha impressa."
        }
      >
        <div className="flex flex-wrap items-start gap-5">
          <div className="flex h-32 w-32 shrink-0 items-center justify-center overflow-hidden rounded-[10px] border border-linha bg-papel">
            {previaFoto || ficha?.foto_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                // A prévia local manda quando existe: é o arquivo que a pessoa
                // acabou de escolher, e ainda não há nada no servidor.
                src={previaFoto ?? urlArquivo(ficha?.foto_url) ?? ""}
                alt={`Foto de ${ficha?.produto ?? "prato"}`}
                className="h-full w-full object-cover"
              />
            ) : (
              <span className="rotulo text-center leading-tight">sem<br />foto</span>
            )}
          </div>
          {podeEditar ? (
            <div className="flex min-w-0 flex-col items-start gap-2">
              {/* ⚠️ **O seletor de arquivo do navegador fica ESCONDIDO, e quem
                  aparece é um botão da casa** — é o corte da tela de Empresa,
                  e ele existe por dois motivos. O controle nativo tem a cara do
                  sistema operacional (muda em cada máquina) e não se parece com
                  nada mais do sistema: o dono olhou a tela e não achou o botão.
                  ⚠️ O `id` fica no input, não no botão: é ele que o teste
                  preenche, e `uploadFile` funciona em campo escondido. */}
              <input
                ref={seletorFoto}
                id="foto-da-ficha"
                type="file"
                accept="image/png,image/jpeg,image/webp"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  // Ficha que ainda não existe: guarda e sobe no "Criar ficha".
                  if (nova) setFotoPendente(f);
                  else void enviarFoto(f);
                }}
              />
              <button
                type="button"
                className="btn btn-secundario"
                disabled={enviandoFoto}
                onClick={() => seletorFoto.current?.click()}
              >
                {enviandoFoto
                  ? "Enviando…"
                  : fotoPendente || ficha?.foto_url
                    ? "Trocar imagem"
                    // ⚠️ Na ficha que ainda não existe é ESCOLHER, não enviar:
                    // nada sobe até o "Criar ficha", e prometer envio aqui
                    // faria a pessoa achar que já foi.
                    : nova
                      ? "Escolher imagem"
                      : "Enviar imagem"}
              </button>
              {(fotoPendente || ficha?.foto_url) && (
                <button
                  type="button"
                  className="link-acao link-acao-erro"
                  onClick={() => {
                    if (fotoPendente) {
                      setFotoPendente(null);
                      if (seletorFoto.current) seletorFoto.current.value = "";
                    } else {
                      void removerFoto();
                    }
                  }}
                >
                  {fotoPendente ? "tirar a imagem escolhida" : "remover"}
                </button>
              )}
              <span className="text-[12.5px] text-suave">
                PNG, JPG ou WEBP, até 2 MB.
                {nova && " Ela é enviada quando a ficha for criada."}
                {/* ⚠️ A foto vale mesmo com a ficha publicada: o prato só
                    existe para ser fotografado DEPOIS de pronto. */}
                {travada && " A ficha está publicada, mas a foto ainda pode ser trocada."}
              </span>
            </div>
          ) : (
            <p className="text-[13px] text-suave">
              Você tem acesso de leitura: a foto só pode ser trocada por quem edita fichas.
            </p>
          )}
        </div>
      </Cartao>

      {editavel && (
        <div className="flex justify-end gap-2">
          <Link href="/fichas" className="btn btn-secundario">
            Voltar
          </Link>
          <button className="btn btn-primario" type="submit" disabled={salvando}>
            {salvando ? "Salvando…" : nova ? "Criar ficha" : "Salvar"}
          </button>
        </div>
      )}
    </form>
  );
}
