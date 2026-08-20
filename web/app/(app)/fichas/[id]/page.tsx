"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { ProdutoResumo, UnidadeMedida, reais } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";

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
  tempo_preparo_min: number | null;
  modo_preparo: string | null;
  alergenos: string | null;
  observacao: string | null;
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
  const [cabecalho, setCabecalho] = useState({
    rendimento_qtd: "1", rendimento_um: "", porcoes: "1", tempo_preparo_min: "",
    modo_preparo: "", alergenos: "", observacao: "",
  });
  const [itens, setItens] = useState<Item[]>([{ ...ITEM_VAZIO }]);
  const [produzidos, setProduzidos] = useState<ProdutoResumo[]>([]);
  const [insumos, setInsumos] = useState<ProdutoResumo[]>([]);
  const [fichas, setFichas] = useState<FichaListada[]>([]);
  const [ums, setUms] = useState<UnidadeMedida[]>([]);
  const [carregando, setCarregando] = useState(!nova);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    Promise.all([
      api.get<ProdutoResumo[]>("/produtos?tipo=PRODUZIDO"),
      api.get<ProdutoResumo[]>("/produtos"),
      api.get<UnidadeMedida[]>("/unidades-medida"),
      api.get<FichaListada[]>("/fichas"),
    ])
      .then(([prod, todos, u, fs]) => {
        setProduzidos(prod);
        setInsumos(todos.filter((p) => p.controla_estoque));
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

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setSalvando(true);
    setErro("");
    const corpo = {
      rendimento_qtd: num(cabecalho.rendimento_qtd) ?? 1,
      rendimento_um: texto(cabecalho.rendimento_um),
      porcoes: num(cabecalho.porcoes) ?? 1,
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

  if (carregando) return <Carregando />;

  return (
    <form onSubmit={salvar} className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <Link href="/fichas" className="link-voltar">
            fichas técnicas
          </Link>
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
          {!nova && podeEditar && travada && (
            <button
              type="button"
              className="btn btn-secundario"
              onClick={() => acao("nova-versao", "", (r) => `/fichas/${r.id}`)}
            >
              Criar nova versão
            </button>
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
          <Campo rotulo="Produto" className="lg:col-span-2">
            {nova ? (
              <select
                className="campo"
                required
                value={idProduto}
                onChange={(e) => setIdProduto(e.target.value)}
              >
                <option value="">— escolha —</option>
                {produzidos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nome}
                  </option>
                ))}
              </select>
            ) : (
              <input className="campo" value={ficha?.produto ?? ""} disabled />
            )}
            {nova && !produzidos.length && (
              <span className="mt-1 block text-[12.5px] text-alerta">
                Nenhum produto do tipo &quot;produzido&quot;.{" "}
                <Link href="/produtos/novo" className="underline">
                  cadastrar
                </Link>
              </span>
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
                value={cabecalho.rendimento_qtd}
                onChange={(e) => setCabecalho({ ...cabecalho, rendimento_qtd: e.target.value })}
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
          </Campo>
          <Campo rotulo="Porções" dica="divide o custo total">
            <input
              className="campo mono"
              type="number"
              step="0.01"
              min="0.01"
              disabled={!editavel}
              value={cabecalho.porcoes}
              onChange={(e) => setCabecalho({ ...cabecalho, porcoes: e.target.value })}
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
                  <label className="min-w-0">
                    <span className="rotulo">Insumo ou preparo</span>
                    <select
                      className="campo mt-1.5"
                      disabled={!editavel}
                      value={alvo}
                      onChange={(e) => {
                        const [tipo, valor] = e.target.value.split(":");
                        setItens((l) =>
                          l.map((x, j) =>
                            j === i
                              ? {
                                  ...x,
                                  id_insumo: tipo === "ins" ? Number(valor) : null,
                                  id_subficha: tipo === "sub" ? Number(valor) : null,
                                }
                              : x,
                          ),
                        );
                      }}
                    >
                      <option value="">— escolha —</option>
                      <optgroup label="Insumos e produtos">
                        {insumos.map((p) => (
                          <option key={`ins:${p.id}`} value={`ins:${p.id}`}>
                            {p.nome} {p.um_estoque ? `(${p.um_estoque})` : ""}
                          </option>
                        ))}
                      </optgroup>
                      {!!opcoesSubficha.length && (
                        <optgroup label="Preparos com ficha">
                          {opcoesSubficha.map((f) => (
                            <option key={`sub:${f.id}`} value={`sub:${f.id}`}>
                              {f.produto} (v{f.versao})
                            </option>
                          ))}
                        </optgroup>
                      )}
                    </select>
                  </label>
                  <label>
                    <span className="rotulo">Bruta</span>
                    <input
                      className="campo mono mt-1.5"
                      type="number"
                      step="0.0001"
                      min="0"
                      disabled={!editavel}
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
                          ? reais(Number(item.custo_total))
                          : "—"}
                      </span>
                    )}
                    {editavel && (
                      <button
                        type="button"
                        className="rotulo pb-2 hover:text-erro"
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
                        {item.qtd_estoque.toLocaleString("pt-BR", { maximumFractionDigits: 4 })}{" "}
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
                  {c.valor !== null && c.valor !== undefined ? reais(Number(c.valor)) : "—"}
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
