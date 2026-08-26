"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import { CORES, dataBr, Nota } from "./tipos";

/**
 * A lista das notas de entrada — só a lista.
 *
 * Digitar e conferir saíram daqui para páginas próprias (`/compras/nova` e
 * `/compras/[id]`). Os dois eram cartões que abriam no meio desta tela: o
 * formulário de digitação empurrava as notas para fora do campo de visão, e a
 * conferência mostrava a tabela de itens espremida entre a lista e o rodapé,
 * sem nunca somar o total. Cada coisa numa página se enxerga inteira.
 */

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

export default function PaginaCompras() {
  const router = useRouter();
  const aviso = useAviso();
  const { pode } = useSessao();
  const [notas, setNotas] = useState<Nota[] | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [busca, setBusca] = useState("");
  const [importados, setImportados] = useState<ResultadoXml[] | null>(null);
  const pag = usePaginacao("notas", { padrao: 50, filtros: [busca] });
  const entradaXml = useRef<HTMLInputElement>(null);

  /**
   * Uma página de notas, da mais recente para a mais antiga.
   *
   * ⚠️ A tela mostrava as 50 mais recentes e mais nada. Numa conta com 3.670
   * notas isso quer dizer que a compra do mês passado não existe — e nada
   * avisava: lista cheia e lista cortada são iguais na tela. Por isso o total
   * vem no `X-Total`, a busca vai ao servidor e há como pedir mais.
   */
  const carregar = useCallback(async () => {
    try {
      const q = new URLSearchParams(pag.parametros);
      if (busca.trim()) q.set("busca", busca.trim());
      // A lista e a FILA vêm juntas: a fila é da casa inteira e não depende de
      // qual página está aberta.
      const [n, pendentes] = await Promise.all([
        api.listar<Nota>(`/notas?${q}`),
        api.get<{ id: number }[]>("/notas/pendencias"),
      ]);
      setNotas(n.itens);
      pag.setTotal(n.total);
      setAPendentes(pendentes.length);
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca, pag.offset, pag.porPagina]);

  useEffect(() => {
    // Digitar dispara busca no servidor: um respiro evita uma consulta por tecla.
    const t = setTimeout(() => void carregar(), busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar, busca]);

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
      // Um arquivo só: abre a nota direto, que é o próximo passo de quem
      // importou. Vários: a lista dos arquivos lidos é a resposta, e é dela
      // que se escolhe qual conferir primeiro.
      const novas = r.resultados.filter((x) => x.status === "nova" && x.id);
      if (novas.length === 1 && novas[0].id) router.push(`/compras/${novas[0].id}`);
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

  /**
   * Tenta de novo achar o produto dos itens que ficaram pendentes.
   *
   * A ordem real das coisas é esta: chegam as notas, e só depois o cadastro
   * fica pronto (ou se importa o catálogo do Omie). Sem este botão, cada item
   * que não encontrou dono no dia da importação só sairia da fila na mão — numa
   * conta de verdade, 109 de 114 itens passaram a ter produto assim que o
   * catálogo chegou.
   */
  async function reconciliar() {
    setOcupado(true);
    try {
      const r = await api.post<{ vinculados: number; pendentes: number; message: string }>(
        "/notas/reconciliar",
      );
      if (r.vinculados) aviso.sucesso(r.message);
      else aviso.erro(r.message + " — cadastre os produtos ou importe o catálogo do Omie.");
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível reconciliar");
    } finally {
      setOcupado(false);
    }
  }

  /**
   * Cria o vínculo produto × fornecedor a partir das notas que já entraram.
   *
   * ⚠️ **O catálogo do Omie não diz quem fornece o quê** — quem sabe isso é a
   * nota. Até aqui o vínculo só nascia no LANÇAMENTO, para guardar o último
   * preço, e nota importada e ainda não lançada — o estado normal de quem
   * acabou de sincronizar — ficava de fora.
   */
  async function vincularFornecedores() {
    setOcupado(true);
    try {
      const r = await api.post<{ vinculos_criados: number; message: string }>(
        "/notas/vincular-fornecedores",
      );
      if (r.vinculos_criados) aviso.sucesso(r.message);
      else aviso.sucesso("Nenhum vínculo novo — as notas já estavam todas amarradas.");
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível vincular");
    } finally {
      setOcupado(false);
    }
  }

  // ⚠️ **A fila vem do SERVIDOR, não da página.** Esta conta somava `pendentes`
  // das notas que tinham vindo na página carregada e se chamava "a fila da casa
  // inteira" — verdade com 37 notas, mentira com 3.670: a nota pendente cai na
  // página 4 e o botão "Reconciliar" simplesmente some, com a pendência
  // continuando lá. É a mesma lição do `X-Total`: lista sem total é lista
  // mentirosa.
  const [aPendentes, setAPendentes] = useState(0);

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
            <Link href="/compras/nova" className="btn btn-secundario">
              Digitar nota
            </Link>
            {pode("integracao.omie") && (
              <button className="btn btn-secundario" onClick={sincronizar} disabled={ocupado}>
                Buscar no Omie
              </button>
            )}
            {aPendentes > 0 && (
              <button
                className="btn btn-secundario"
                onClick={reconciliar}
                disabled={ocupado}
                title="Procura de novo o produto dos itens pendentes"
              >
                Reconciliar {aPendentes} pendente(s)
              </button>
            )}
            {pode("compras.conciliar") && (
              <button
                className="btn btn-secundario"
                onClick={vincularFornecedores}
                disabled={ocupado}
                title="Amarra produto e fornecedor pelo que as notas já mostraram"
              >
                Vincular fornecedores
              </button>
            )}
          </div>
        )}
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

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
                  {r.id ? (
                    <Link href={`/compras/${r.id}`} className="text-left">
                      <span className="font-semibold hover:text-erva">
                        {r.numero ? `NF ${r.numero}` : r.arquivo}
                      </span>
                      <span className="block text-[13px] text-suave">
                        {`${r.fornecedor ?? ""} · ${r.itens ?? 0} item(ns)` +
                          (r.pendentes ? ` · ${r.pendentes} a vincular` : "")}
                      </span>
                    </Link>
                  ) : (
                    <span className="text-left">
                      <span className="font-semibold">
                        {r.numero ? `NF ${r.numero}` : r.arquivo}
                      </span>
                      <span className="block text-[13px] text-suave">{r.arquivo}</span>
                    </span>
                  )}
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

      <Cartao
        titulo={notas ? `${pag.total} nota(s)` : "Notas"}
        acao={
          <input
            className="campo w-[240px]"
            placeholder="Número da NF, fornecedor ou chave"
            aria-label="Buscar nota"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
        }
      >
        {!notas ? (
          <Carregando />
        ) : !notas.length ? (
          <Vazio>
            {busca
              ? "Nenhuma nota com esse número ou fornecedor."
              : "Nenhuma nota ainda. Importe um XML, digite a do mercado ou busque no Omie."}
          </Vazio>
        ) : (
          <ul className="flex flex-col gap-px bg-linha">
            {notas.map((n) => (
              <li
                key={n.id}
                className="flex flex-wrap items-center justify-between gap-3 bg-superficie py-3"
              >
                <Link href={`/compras/${n.id}`} className="min-w-0 text-left">
                  <span className="font-semibold hover:text-erva">
                    NF {n.numero ?? "—"} · {n.fornecedor ?? n.nome_emitente ?? "sem fornecedor"}
                  </span>
                  <span className="block text-[13px] text-suave">
                    {n.data_emissao ? dataBr(n.data_emissao) : "sem data"} · {n.itens} item(ns) ·{" "}
                    {reais(Number(n.valor_total))}
                  </span>
                </Link>
                <span className="flex items-center gap-2">
                  {n.pendentes > 0 && <Etiqueta cor="alerta">{n.pendentes} pendente(s)</Etiqueta>}
                  <Etiqueta cor={CORES[n.status]}>{n.status.toLowerCase()}</Etiqueta>
                </span>
              </li>
            ))}
          </ul>
        )}
        <Paginacao p={pag} rotulo="nota(s)" />
      </Cartao>
    </div>
  );
}
