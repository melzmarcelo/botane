"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useSessao } from "@/lib/sessao";
import {
  Categoria,
  Fornecedor,
  Setor,
  TIPOS_PRODUTO,
  UnidadeMedida,
} from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";
import ComposicaoKit from "./kit";

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
  controla_estoque: boolean;
  um_estoque: string;
  um_compra: string;
  fator_compra: string;
  perecivel: boolean;
  validade_dias: string;
  controla_lote: boolean;
  controla_validade: boolean;
  estoque_minimo: string;
  estoque_maximo: string;
  ncm: string;
  codigo_barras: string;
  observacao: string;
  preco_venda: string;
  status: string;
  ativo: boolean;
};

const VAZIO: Form = {
  codigo: "", nome: "", nome_curto: "", tipo: "INSUMO", id_categoria: "", id_setor: "",
  producao_propria: false, controla_estoque: true, um_estoque: "", um_compra: "",
  fator_compra: "1", perecivel: false, validade_dias: "", controla_lote: false,
  controla_validade: false, estoque_minimo: "", estoque_maximo: "", ncm: "",
  codigo_barras: "", observacao: "", preco_venda: "", status: "ATIVO", ativo: true,
};

const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));
const texto = (v: string) => (v.trim() === "" ? null : v.trim());

export default function FormularioProduto() {
  const { id } = useParams<{ id: string }>();
  const novo = id === "novo";
  const router = useRouter();
  const { pode } = useSessao();
  const podeEditar = pode("cadastros.produtos");

  const [f, setF] = useState<Form>(VAZIO);
  const [vinculos, setVinculos] = useState<VinculoFornecedor[]>([]);
  const [categorias, setCategorias] = useState<Categoria[]>([]);
  const [setores, setSetores] = useState<Setor[]>([]);
  const [ums, setUms] = useState<UnidadeMedida[]>([]);
  const [fornecedores, setFornecedores] = useState<Fornecedor[]>([]);
  const [carregando, setCarregando] = useState(!novo);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<Categoria[]>("/categorias"),
      api.get<Setor[]>("/setores"),
      api.get<UnidadeMedida[]>("/unidades-medida"),
      api.get<Fornecedor[]>("/fornecedores"),
    ])
      .then(([c, s, u, fo]) => {
        setCategorias(c);
        setSetores(s);
        setUms(u);
        setFornecedores(fo);
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
      })
      .catch((e) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, [id, novo]);

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
    setOk("");
  }

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    setOk("");
    const corpo = {
      codigo: texto(f.codigo),
      nome: f.nome.trim(),
      nome_curto: texto(f.nome_curto),
      tipo: f.tipo,
      id_categoria: num(f.id_categoria),
      id_setor: num(f.id_setor),
      producao_propria: f.producao_propria,
      controla_estoque: f.controla_estoque,
      um_estoque: texto(f.um_estoque),
      um_compra: texto(f.um_compra),
      fator_compra: num(f.fator_compra) ?? 1,
      perecivel: f.perecivel,
      validade_dias: num(f.validade_dias),
      controla_lote: f.controla_lote,
      controla_validade: f.controla_validade,
      estoque_minimo: num(f.estoque_minimo),
      estoque_maximo: num(f.estoque_maximo),
      ncm: texto(f.ncm),
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
        setOk("Produto criado.");
      } else {
        await api.put(`/produtos/${id}`, { ...corpo, ativo: f.ativo });
        setOk("Produto salvo.");
      }
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setSalvando(false);
    }
  }

  async function revisar() {
    try {
      await api.post(`/produtos/${id}/revisar`);
      setF((a) => ({ ...a, status: "ATIVO" }));
      setOk("Produto revisado — agora ele pode entrar no estoque.");
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível revisar");
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
          <Link href="/produtos" className="rotulo hover:text-erva">
            ‹ produtos
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
        {podeEditar && (
          <div className="flex gap-2">
            {!novo && f.status === "RASCUNHO" && (
              <button type="button" className="btn btn-secundario" onClick={revisar}>
                Revisar e ativar
              </button>
            )}
            <button className="btn btn-primario" type="submit" disabled={salvando}>
              {salvando ? "Salvando…" : novo ? "Criar produto" : "Salvar"}
            </button>
          </div>
        )}
      </header>

      {!podeEditar && <Aviso tipo="info">Você tem acesso de leitura a esta tela.</Aviso>}
      {erro && <Aviso tipo="erro">{erro}</Aviso>}
      {ok && <Aviso tipo="ok">{ok}</Aviso>}

      <Cartao titulo="Identificação">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Campo rotulo="Nome" className="sm:col-span-2">
            <input
              className="campo"
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
          <Campo rotulo="Nome curto" dica="para o cardápio e o PDV">
            <input
              className="campo"
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
          <Campo rotulo="Preço de venda" dica="grava com data de vigência">
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

      <Cartao titulo="Estoque">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
          <Campo rotulo="NCM">
            <input
              className="campo mono"
              disabled={!podeEditar}
              value={f.ncm}
              onChange={(e) => set("ncm", e.target.value)}
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
          ].map((i) => (
            <li
              key={i.campo}
              className="flex items-start gap-3 bg-superficie p-4 last:sm:col-span-2"
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
                  <select
                    className="campo mt-1.5"
                    disabled={!podeEditar}
                    value={v.id_fornecedor}
                    onChange={(e) =>
                      setVinculos((l) =>
                        l.map((x, j) =>
                          j === i ? { ...x, id_fornecedor: Number(e.target.value) } : x,
                        ),
                      )
                    }
                  >
                    {fornecedores.map((fo) => (
                      <option key={fo.id} value={fo.id}>
                        {fo.nome}
                      </option>
                    ))}
                  </select>
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
                      className="rotulo pb-2 hover:text-erro"
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
