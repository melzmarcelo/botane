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
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";
import BuscaCadastro from "@/components/busca-cadastro";
import { fonteFornecedores, ItemBusca } from "@/lib/busca-cadastro";
import ComposicaoKit from "./kit";
import UnidadesDeCompra from "./unidades";
import Vincular from "./vincular";

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
  fator_compra: "1", id_local_padrao: "", perecivel: false, validade_dias: "", controla_lote: false,
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
  const [carregando, setCarregando] = useState(!novo);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<Categoria[]>("/categorias"),
      api.get<Setor[]>("/setores"),
      api.get<UnidadeMedida[]>("/unidades-medida"),
      api.get<Fornecedor[]>("/fornecedores"),
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

  useEffect(() => {
    if (novo) return;
    api
      .get<Record<string, unknown>>(`/produtos/${id}`)
      .then((p) => {
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
        // ⚠️ O campo do formulário mostra o preço DA CASA, não o resolvido:
        // senão, editar um produto numa filial que cobra diferente gravaria o
        // preço dela como se fosse o da casa.
        const casa = p.preco_casa as number | null;
        setPrecoCasa(casa ?? null);
        setF((atual) => ({ ...atual, preco_venda: casa === null || casa === undefined ? "" : String(casa) }));
        const daLoja = p.preco_loja as number | null;
        setPrecoLoja(daLoja === null || daLoja === undefined ? "" : String(daLoja));
      })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, [id, novo]);

  async function salvarPrecoDaLoja(valor: number | null) {
    setSalvandoPreco(true);
    try {
      const r = await api.put<{ message: string }>(`/produtos/${id}/preco-loja`, {
        preco_venda: valor,
      });
      setPrecoLoja(valor === null ? "" : String(valor));
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

  async function salvar(e: FormEvent) {
    e.preventDefault();
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
      preco_venda: num(f.preco_venda),
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
        router.replace(`/produtos/${r.id}`);
        // Quem cadastra um produto costuma cadastrar o próximo. O caminho para
        // isso vai junto do aviso, em vez de exigir voltar à lista e achar o
        // botão de novo.
        aviso.sucesso(`${f.nome.trim()} criado.`, {
          texto: "cadastrar outro",
          ao: () => router.push("/produtos/novo"),
        });
      } else {
        await api.put(`/produtos/${id}`, { ...corpo, ativo: f.ativo });
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
          <Link href="/produtos" className="link-voltar">
            produtos
          </Link>
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
            <input
              className="campo mono"
              type="number"
              step="0.01"
              min="0"
              disabled={!podeEditar}
              value={f.preco_venda}
              onChange={(e) => set("preco_venda", e.target.value)}
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
              <input
                className="campo mono"
                type="number"
                step="0.01"
                min="0"
                disabled={!podeEditar}
                placeholder={precoCasa === null ? "" : String(precoCasa)}
                value={precoLoja}
                onChange={(e) => setPrecoLoja(e.target.value)}
              />
            </Campo>
            {podeEditar && (
              <>
                <button
                  type="button"
                  className="btn btn-primario"
                  disabled={salvandoPreco}
                  onClick={() => void salvarPrecoDaLoja(precoLoja.trim() === "" ? null : Number(precoLoja))}
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

      <Cartao titulo="Estoque">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* O local é do PRODUTO: uma nota traz congelado e seco na mesma
              folha, e um local por nota obrigaria a lançar duas vezes. */}
          <Campo rotulo="Local de estoque" dica="onde este produto entra">
            <select
              className="campo"
              disabled={!podeEditar}
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
