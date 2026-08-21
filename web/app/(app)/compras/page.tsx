"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Local, ProdutoResumo, reais } from "@/lib/cadastros";
import BuscaCadastro, { rotuloDe } from "@/components/busca-cadastro";
import { fonteProdutos, ItemBusca } from "@/lib/busca-cadastro";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import NotaManual, { NotaParaEditar } from "./nota-manual";

/** O que o servidor devolve para cada arquivo do lote de XMLs. */
type ResultadoXml = {
  arquivo: string;
  status: "nova" | "repetida" | "erro";
  erro?: string;
  avisos?: string[];
  id?: number;
  numero?: string | null;
  fornecedor?: string | null;
  itens?: number;
  pendentes?: number;
  valor_total?: number;
};

type Nota = {
  id: number;
  chave_nfe: string | null;
  numero: string | null;
  nome_emitente: string | null;
  fornecedor: string | null;
  data_emissao: string | null;
  valor_total: number;
  status: string;
  itens: number;
  pendentes: number;
};

type ItemNota = {
  id: number;
  seq: number;
  descricao_fornecedor: string;
  codigo_fornecedor: string | null;
  codigo_barras: string | null;
  quantidade: number;
  um_nota: string | null;
  valor_unitario: number;
  valor_frete_rateado: number;
  quantidade_convertida: number | null;
  custo_aquisicao_unitario: number | null;
  variacao_preco_pct: number | null;
  id_produto: number | null;
  produto: string | null;
  um_estoque: string | null;
  local_destino: string | null;
  sugestao_produto: number | null;
  sugestao_nome: string | null;
  sugestao_score: number | null;
  ignorado: boolean;
  lote_nf: string | null;
  validade_nf: string | null;
  valor_desconto: number;
  valor_acrescimo: number;
};

type NotaDetalhe = Nota & {
  itens_lista?: ItemNota[];
  // O detalhe traz o cabeçalho inteiro: é dele que o formulário de correção
  // se enche.
  origem: string;
  id_fornecedor: number | null;
  serie: string | null;
  valor_frete: number;
  valor_desconto: number;
  valor_outros: number;
  id_local: number | null;
};

const CORES: Record<string, "erva" | "alerta" | "neutro"> = {
  LANCADA: "erva",
  CONCILIADA: "alerta",
  IMPORTADA: "neutro",
};

// Item de nota vira movimento de estoque: só produto que controla estoque.
const PRODUTOS = fonteProdutos((p) => p.controla_estoque);

export default function PaginaCompras() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const [notas, setNotas] = useState<Nota[] | null>(null);
  const [aberta, setAberta] = useState<(NotaDetalhe & { itens: ItemNota[] }) | null>(null);
  const [produtos, setProdutos] = useState<ProdutoResumo[]>([]);
  const [locais, setLocais] = useState<Local[]>([]);
  const [escolha, setEscolha] = useState<Record<number, string>>({});
  // O que mostrar no campo de cada item: a busca devolve o rótulo, e guardá-lo
  // evita ter de ir buscar o nome de novo só para desenhar a linha.
  const [rotuloEscolhido, setRotuloEscolhido] = useState<Record<number, string>>({});
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [digitando, setDigitando] = useState(false);
  const [corrigindo, setCorrigindo] = useState<NotaParaEditar | null>(null);
  const [importados, setImportados] = useState<ResultadoXml[] | null>(null);
  const entradaXml = useRef<HTMLInputElement>(null);

  const carregar = useCallback(async () => {
    try {
      const [n, p, l] = await Promise.all([
        api.get<Nota[]>("/notas?limite=50"),
        api.get<ProdutoResumo[]>("/produtos"),
        api.get<Local[]>("/locais"),
      ]);
      setNotas(n);
      setProdutos(p.filter((x) => x.controla_estoque));
      setLocais(l);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  /**
   * Abre a nota para conferência.
   *
   * `limparAvisos` existe porque quase toda ação (importar, digitar, lançar,
   * estornar) termina abrindo a nota — e limpar aqui apagaria a mensagem que a
   * ação acabou de escrever, deixando a tela muda depois de dar certo.
   */
  async function abrir(id: number, limparAvisos = true) {
    if (limparAvisos) {
      setErro("");
    }
    try {
      const nota = await api.get<NotaDetalhe & { itens: ItemNota[] }>(`/notas/${id}`);
      setAberta(nota);
      // Sugestão já vem marcada: confirmar é um clique, e nunca automático.
      setEscolha(
        Object.fromEntries(
          nota.itens
            .filter((i) => !i.id_produto && i.sugestao_produto)
            .map((i) => [i.id, String(i.sugestao_produto)]),
        ),
      );
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao abrir a nota");
    }
  }

  async function importarXml(arquivos: FileList | null) {
    if (!arquivos?.length) return;
    setOcupado(true);
    setErro("");
    setImportados(null);
    try {
      const corpo = new FormData();
      // O campo repete de propósito: o servidor recebe a lista inteira de uma
      // vez, e um arquivo ruim no meio não impede os outros de entrarem.
      Array.from(arquivos).forEach((a) => corpo.append("arquivos", a));
      const r = await api.upload<{ resultados: ResultadoXml[]; message: string }>(
        "/notas/importar-xml",
        corpo,
      );
      setImportados(r.resultados);
      aviso.sucesso(r.message);
      await carregar();
      const primeira = r.resultados.find((x) => x.status === "nova" && x.id);
      if (primeira?.id) await abrir(primeira.id, false);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível ler os arquivos");
    } finally {
      setOcupado(false);
      if (entradaXml.current) entradaXml.current.value = "";
    }
  }

  async function sincronizar() {
    setOcupado(true);
    setErro("");
    try {
      // Sem período: a janela vai desde a última sincronização, com folga. A
      // resposta já vem com a frase de qual janela foi usada.
      const r = await api.post<{ novas: number; modo: string; message: string }>(
        "/omie/sincronizar",
      );
      aviso.sucesso(
        (r.message ?? "Busca concluída") +
          (r.modo === "simulado" ? " (modo simulado — dados de demonstração)" : ""),
      );
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível sincronizar");
    } finally {
      setOcupado(false);
    }
  }

  async function vincular(item: ItemNota) {
    const id_produto = Number(escolha[item.id]);
    if (!id_produto) return;
    setOcupado(true);
    setErro("");
    try {
      await api.post(`/notas/itens/${item.id}/vincular`, { id_produto, aprender: true });
      await abrir(aberta!.id, false);
      await carregar();
      aviso.sucesso("Item vinculado — as próximas notas com esse código entram sozinhas.");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível vincular");
    } finally {
      setOcupado(false);
    }
  }

  /**
   * Cria o produto a partir do item da nota e vincula os dois.
   *
   * Nasce rascunho: a descrição, o NCM e o código de barras vêm da nota, mas
   * unidade e fator ninguém conferiu ainda — e rascunho não entra em ficha nem
   * em venda até alguém completar.
   */
  async function criarProduto(item: ItemNota) {
    setOcupado(true);
    setErro("");
    try {
      const r = await api.post<{ message: string }>(
        `/notas/itens/${item.id}/criar-produto`,
        {},
      );
      aviso.sucesso(r.message);
      await abrir(aberta!.id, false);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível criar o produto");
    } finally {
      setOcupado(false);
    }
  }

  async function ignorar(item: ItemNota) {
    setOcupado(true);
    try {
      await api.post(`/notas/itens/${item.id}/ignorar`);
      await abrir(aberta!.id, false);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível marcar");
    } finally {
      setOcupado(false);
    }
  }

  async function lancar() {
    if (!aberta) return;
    setOcupado(true);
    setErro("");
    try {
      const r = await api.post<{ itens_lancados: number; valor: number }>(
        `/notas/${aberta.id}/lancar`,
        {},
      );
      aviso.sucesso(
        `${r.itens_lancados} item(ns) no estoque, ${reais(Number(r.valor))} — o custo médio de cada insumo foi recalculado.`,
      );
      await abrir(aberta.id, false);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível lançar");
    } finally {
      setOcupado(false);
    }
  }

  async function estornar() {
    if (!aberta) return;
    setOcupado(true);
    setErro("");
    try {
      const r = await api.post<{ estornados: number }>(`/notas/${aberta.id}/estornar`);
      aviso.sucesso(`${r.estornados} movimento(s) estornado(s) — o razão guarda os dois lados.`);
      await abrir(aberta.id, false);
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível estornar");
    } finally {
      setOcupado(false);
    }
  }

  const pendentes = aberta?.itens.filter((i) => !i.id_produto && !i.ignorado) ?? [];
  // O local da nota é a reserva de quem não tem local no cadastro do produto.
  const localDaNota = locais.find((l) => l.id === aberta?.id_local)?.nome ?? "";

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Compras</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Notas de entrada
          </h1>
          <p className="mt-1 max-w-[66ch] text-suave">
            A nota entra por onde for mais fácil — o XML que o fornecedor mandou, a digitação do
            cupom do mercado ou o Omie — e vira estoque avaliado do mesmo jeito. O que decide o
            custo não é o valor unitário da nota: é ele menos desconto, mais frete rateado,
            dividido pelo que realmente entra na prateleira.
          </p>
        </div>
        {pode("compras.notas") && (
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={entradaXml}
              type="file"
              accept=".xml,text/xml,application/xml"
              multiple
              className="hidden"
              onChange={(e) => void importarXml(e.target.files)}
            />
            <button
              className="btn btn-primario"
              onClick={() => entradaXml.current?.click()}
              disabled={ocupado}
            >
              {ocupado ? "Lendo…" : "Importar XML"}
            </button>
            <button
              className="btn btn-secundario"
              onClick={() => {
                setDigitando(true);
                setAberta(null);
              }}
              disabled={ocupado}
            >
              Digitar nota
            </button>
            {pode("integracao.omie") && (
              <button className="btn btn-secundario" onClick={sincronizar} disabled={ocupado}>
                Buscar no Omie
              </button>
            )}
          </div>
        )}
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {corrigindo && (
        <NotaManual
          produtos={produtos}
          locais={locais}
          editando={corrigindo}
          aoFechar={() => setCorrigindo(null)}
          aoGravar={async (id) => {
            setCorrigindo(null);
            aviso.sucesso("Nota corrigida. Confira e lance no estoque.");
            await carregar();
            await abrir(id, false);
          }}
        />
      )}

      {digitando && (
        <NotaManual
          produtos={produtos}
          locais={locais}
          aoFechar={() => setDigitando(false)}
          aoGravar={async (id) => {
            setDigitando(false);
            aviso.sucesso("Nota registrada. Confira os itens e lance no estoque.");
            await carregar();
            await abrir(id, false);
          }}
        />
      )}

      {importados && (
        <Cartao
          titulo="Arquivos lidos"
          acao={
            <button className="rotulo hover:text-erro" onClick={() => setImportados(null)}>
              fechar
            </button>
          }
        >
          <ul className="flex flex-col gap-px bg-linha">
            {importados.map((r, i) => (
              <li key={i} className="bg-superficie py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <button
                    className="text-left"
                    onClick={() => r.id && void abrir(r.id)}
                    disabled={!r.id}
                  >
                    <span className="font-semibold">
                      {r.numero ? `NF ${r.numero}` : r.arquivo}
                    </span>
                    <span className="block text-[13px] text-suave">
                      {r.status === "erro"
                        ? r.arquivo
                        : `${r.fornecedor ?? ""} · ${r.itens ?? 0} item(ns)` +
                          (r.pendentes ? ` · ${r.pendentes} a vincular` : "")}
                    </span>
                  </button>
                  <Etiqueta
                    cor={
                      r.status === "nova" ? "erva" : r.status === "repetida" ? "neutro" : "alerta"
                    }
                  >
                    {r.status === "nova" ? "importada" : r.status}
                  </Etiqueta>
                </div>
                {r.erro && <p className="mt-1 text-[13px] text-erro">{r.erro}</p>}
                {r.avisos?.map((a, j) => (
                  <p key={j} className="mt-1 text-[13px] text-alerta">
                    {a}
                  </p>
                ))}
              </li>
            ))}
          </ul>
        </Cartao>
      )}

      {aberta && (
        <Cartao
          titulo={`NF ${aberta.numero ?? "—"} · ${aberta.fornecedor ?? aberta.nome_emitente ?? ""}`}
          descricao={
            aberta.chave_nfe
              ? `chave ${aberta.chave_nfe.slice(0, 8)}…${aberta.chave_nfe.slice(-6)}`
              : undefined
          }
          acao={
            <div className="flex flex-wrap items-center gap-2">
              <Etiqueta cor={CORES[aberta.status]}>{aberta.status.toLowerCase()}</Etiqueta>
              {aberta.status === "LANCADA" && pode("estoque.ajuste") && (
                <button className="btn btn-secundario" onClick={estornar} disabled={ocupado}>
                  Estornar
                </button>
              )}
              {/* Nota digitada e ainda não lançada se corrige: quem digitou vinte
                  itens acha o erro no item três, e descartar tudo era a única
                  saída. A que veio do XML não entra aqui — ela é o documento. */}
              {aberta.origem === "MANUAL" && aberta.status !== "LANCADA" &&
                pode("compras.notas") && (
                  <button
                    className="btn btn-secundario"
                    onClick={() => {
                      setCorrigindo({
                        id: aberta.id,
                        id_fornecedor: aberta.id_fornecedor ?? null,
                        numero: aberta.numero,
                        serie: aberta.serie ?? null,
                        data_emissao: aberta.data_emissao,
                        valor_frete: Number(aberta.valor_frete ?? 0),
                        valor_desconto: Number(aberta.valor_desconto ?? 0),
                        valor_outros: Number(aberta.valor_outros ?? 0),
                        id_local: aberta.id_local,
                        itens: aberta.itens.map((i) => ({
                          id_produto: i.id_produto,
                          descricao_fornecedor: i.descricao_fornecedor,
                          quantidade: Number(i.quantidade),
                          valor_unitario: Number(i.valor_unitario),
                          lote_nf: i.lote_nf ?? null,
                          validade_nf: i.validade_nf ?? null,
                          um_nota: i.um_nota ?? null,
                          valor_desconto: Number(i.valor_desconto ?? 0),
                          valor_acrescimo: Number(i.valor_acrescimo ?? 0),
                        })),
                      });
                      setAberta(null);
                      setDigitando(false);
                    }}
                  >
                    Corrigir
                  </button>
                )}
              {aberta.status !== "LANCADA" && pode("compras.lancar") && (
                <button
                  className="btn btn-primario"
                  onClick={lancar}
                  disabled={ocupado || !!pendentes.length}
                  title={pendentes.length ? "Há item sem produto vinculado" : undefined}
                >
                  Lançar no estoque
                </button>
              )}
              <button className="rotulo hover:text-erro" onClick={() => setAberta(null)}>
                fechar
              </button>
            </div>
          }
        >
          {!!pendentes.length && (
            <div className="mb-4">
              <Aviso tipo="info">
                {pendentes.length} item(ns) sem produto vinculado. A nota não entra no estoque
                enquanto isso — importar errado é pior que não importar.
              </Aviso>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Item da nota</th>
                  <th className="num">Qtd</th>
                  <th className="num">Valor un.</th>
                  <th className="num">Frete rateado</th>
                  <th>Produto no Botané</th>
                  <th>Entra em</th>
                  <th className="num">Custo real</th>
                </tr>
              </thead>
              <tbody>
                {aberta.itens.map((i) => (
                  <tr key={i.id} className={i.ignorado ? "opacity-55" : ""}>
                    <td>
                      <span className="font-semibold">{i.descricao_fornecedor}</span>
                      <span className="mono block text-[12px] text-suave">
                        {i.codigo_fornecedor ?? "—"}
                        {i.codigo_barras && ` · EAN ${i.codigo_barras}`}
                      </span>
                    </td>
                    <td className="num whitespace-nowrap">
                      {Number(i.quantidade)} {i.um_nota ?? ""}
                      {i.quantidade_convertida && (
                        <span className="block text-[12px] text-suave">
                          = {Number(i.quantidade_convertida)} {i.um_estoque ?? ""}
                        </span>
                      )}
                    </td>
                    <td className="num">{reais(Number(i.valor_unitario))}</td>
                    <td className="num text-suave">{reais(Number(i.valor_frete_rateado))}</td>
                    <td>
                      {i.id_produto ? (
                        <span className="font-medium text-erva">{i.produto}</span>
                      ) : i.ignorado ? (
                        <Etiqueta>fora do estoque</Etiqueta>
                      ) : pode("compras.conciliar") ? (
                        <div className="flex flex-col gap-1.5">
                          <BuscaCadastro
                            fonte={PRODUTOS}
                            selecionado={
                              escolha[i.id]
                                ? {
                                    id: Number(escolha[i.id]),
                                    rotulo: rotuloEscolhido[i.id] ?? "",
                                  }
                                : null
                            }
                            aoEscolher={(item: ItemBusca | null) => {
                              setEscolha({ ...escolha, [i.id]: item ? String(item.id) : "" });
                              setRotuloEscolhido((r) => ({
                                ...r,
                                [i.id]: item ? rotuloDe(item) : "",
                              }));
                            }}
                          />
                          {i.sugestao_nome && (
                            <span className="text-[12px] text-suave">
                              palpite: {i.sugestao_nome} ({Number(i.sugestao_score).toFixed(0)}%)
                            </span>
                          )}
                          <span className="flex gap-3">
                            <button
                              className="rotulo text-erva hover:underline"
                              onClick={() => void vincular(i)}
                              disabled={!escolha[i.id]}
                            >
                              vincular
                            </button>
                            {/* O insumo ainda não existe no cadastro: criar daqui
                                poupa sair da tela, cadastrar e voltar. */}
                            {pode("cadastros.produtos") && (
                              <button
                                className="rotulo hover:text-erva"
                                onClick={() => void criarProduto(i)}
                              >
                                criar produto
                              </button>
                            )}
                            <button
                              className="rotulo hover:text-erro"
                              onClick={() => void ignorar(i)}
                            >
                              não controla estoque
                            </button>
                          </span>
                        </div>
                      ) : (
                        <Etiqueta cor="alerta">pendente</Etiqueta>
                      )}
                    </td>
                    {/* Cada item vai para o local do CADASTRO do produto: a
                        mesma nota traz congelado e seco. Sem local no produto,
                        vale o da nota — e a coluna diz qual é. */}
                    <td className="whitespace-nowrap text-[13px]">
                      {i.id_produto ? (
                        i.local_destino ? (
                          <span>{i.local_destino}</span>
                        ) : (
                          <span className="text-suave">
                            {localDaNota || "local da nota"}
                            <span className="block text-[11.5px]">sem local no cadastro</span>
                          </span>
                        )
                      ) : (
                        <span className="text-suave">—</span>
                      )}
                    </td>
                    <td className="num">
                      {i.custo_aquisicao_unitario ? (
                        <>
                          <span className="font-semibold">
                            {reais(Number(i.custo_aquisicao_unitario))}
                          </span>
                          {i.variacao_preco_pct !== null && (
                            <span
                              className={`block text-[12px] ${
                                Number(i.variacao_preco_pct) > 10 ? "text-erro" : "text-suave"
                              }`}
                            >
                              {Number(i.variacao_preco_pct) > 0 ? "+" : ""}
                              {Number(i.variacao_preco_pct).toFixed(1)}% vs. última compra
                            </span>
                          )}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Cartao>
      )}

      <Cartao titulo={notas ? `${notas.length} nota(s)` : "Notas"}>
        {!notas ? (
          <Carregando />
        ) : !notas.length ? (
          <Vazio>
            Nenhuma nota ainda. Use &quot;Buscar no Omie&quot; — sem credencial, ele traz as
            notas de demonstração.
          </Vazio>
        ) : (
          <ul className="flex flex-col gap-px bg-linha">
            {notas.map((n) => (
              <li
                key={n.id}
                className="flex flex-wrap items-center justify-between gap-3 bg-superficie py-3"
              >
                <button className="min-w-0 text-left" onClick={() => void abrir(n.id)}>
                  <span className="font-semibold hover:text-erva">
                    NF {n.numero ?? "—"} · {n.fornecedor ?? n.nome_emitente ?? "sem fornecedor"}
                  </span>
                  <span className="block text-[13px] text-suave">
                    {n.data_emissao
                      ? new Date(n.data_emissao + "T12:00:00").toLocaleDateString("pt-BR")
                      : "sem data"}{" "}
                    · {n.itens} item(ns) · {reais(Number(n.valor_total))}
                  </span>
                </button>
                <span className="flex items-center gap-2">
                  {n.pendentes > 0 && <Etiqueta cor="alerta">{n.pendentes} pendente(s)</Etiqueta>}
                  <Etiqueta cor={CORES[n.status]}>{n.status.toLowerCase()}</Etiqueta>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Cartao>
    </div>
  );
}
