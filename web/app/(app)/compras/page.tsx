"use client";

import Link from "next/link";
import BotaoExportar from "@/components/exportar";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Paginacao, usePaginacao } from "@/components/paginacao";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Modal, Vazio } from "@/components/ui";
import { qtd } from "@/lib/numeros";
import { CORES, dataBr, Nota, rotuloStatus } from "./tipos";
import { useEstadoNaUrl } from "@/lib/estado-na-url";
import ExplicaTela from "@/components/explica-tela";
import LancarLote from "./lote";
import BarraDeFiltros, { useFiltrosNotas } from "./filtros-notas";
import { resumoNotas, type ResumoNotas } from "@/lib/compras";

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

/** O que a prévia dos arquivados devolve. */
type Arquivados = {
  itens: {
    id: number; id_nota: number; numero: string | null; status: string;
    fornecedor: string | null; descricao_fornecedor: string;
    quantidade: number; um_nota: string | null;
    codigo_arquivado: string; arquivado: string;
    destino: { id: number; codigo: string; nome: string } | null;
  }[];
  /** Corrente que morre em arquivado: ninguém ativo herdou, e escolher seria adivinhar. */
  sem_destino: unknown[];
  notas: number;
  produtos: number;
};

export default function PaginaCompras() {
  const router = useRouter();
  const aviso = useAviso();
  const { pode } = useSessao();
  const [notas, setNotas] = useState<Nota[] | null>(null);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [busca, setBusca] = useEstadoNaUrl<string>("busca", "");
  const [importados, setImportados] = useState<ResultadoXml[] | null>(null);
  const filtros = useFiltrosNotas();
  const [resumo, setResumo] = useState<ResumoNotas | null>(null);
  const pag = usePaginacao("notas", { padrao: 50, filtros: [busca, ...filtros.chaves] });
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
    // ⚠️ Espera a preferencia de "por pagina" ser resolvida: buscar antes
    // dispara a busca com o tamanho errado, e a resposta atrasada dela
    // sobrescreve a certa -- era o "seletor em 100, lista com 20".
    if (!pag.pronto) return;
    try {
      const q = new URLSearchParams(pag.parametros);
      if (busca.trim()) q.set("busca", busca.trim());
      filtros.aplicar(q);
      // 🔑 O total em reais do MESMO filtro (21/10/2026), em rota própria: a lista só
      // conta na primeira página, e o valor tem de continuar ao virar a página.
      const sem = new URLSearchParams();
      if (busca.trim()) sem.set("busca", busca.trim());
      resumoNotas(filtros.aplicar(sem)).then(setResumo).catch(() => setResumo(null));
      // A lista e a FILA vêm juntas: a fila é da casa inteira e não depende de
      // qual página está aberta.
      const [n, pendentes] = await Promise.all([
        api.listar<Nota>(`/notas?${q}`),
        api.get<{ id: number }[]>("/notas/pendencias"),
      ]);
      setNotas(n.itens);
      pag.setTotal(n.total);
      setAPendentes(pendentes.length);
      // 🔑 **Itens de nota ABERTA apontando para cadastro arquivado.** Depois
      // de uma fusão eles ficam órfãos: lançar assim poria o estoque num
      // cadastro morto, fora da ficha e fora do custo do sobrevivente. A
      // prévia é do servidor, e nota já LANÇADA fica de fora — lá o razão já
      // concorda com a nota, e mexer só na nota criaria a divergência.
      api.get<Arquivados>("/notas/arquivados/previa").then(setArquivados).catch(() => {});
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pag.pronto, busca, pag.offset, pag.porPagina, ...filtros.chaves]);

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

  /**
   * 🔑 **Atualizar do Omie, para todas as notas abertas** (09/10/2026, pedido do
   * dono: *"hoje temos o Atualizar do Omie somente quando estamos na nota"*). É o
   * botão da nota repetido para cada uma que ainda não foi lançada: traz valor
   * corrigido, item trocado e nota CANCELADA lá.
   *
   * ⚠️ **Em levas, e quem pede a próxima é esta tela.** Cada nota é uma consulta ao
   * Omie com 0,6 s de espera — trinta dão uns vinte segundos. Uma chamada só para
   * centenas morreria no tempo limite com metade feita. O servidor devolve
   * `proximo`, e o laço segue até ele vir nulo, mostrando onde está.
   */
  const [confirmandoSincronizar, setConfirmandoSincronizar] = useState(false);
  const [andamento, setAndamento] = useState("");

  /**
   * Relê do Omie as notas abertas, em levas, e devolve a frase do que mudou.
   *
   * ⚠️ Lança erro só quando a primeira leva falha; o resto vira frase, com o que já
   * foi conferido. Quem chama decide o que fazer com ela.
   */
  async function releituraDasAbertas(): Promise<{ frase: string; parou: boolean }> {
    type Leva = {
      conferidas: number; iguais: number; restantes: number; proximo: number | null;
      atualizadas: unknown[]; canceladas: unknown[]; nao_encontradas?: unknown[];
      falhas: { motivo: string }[]; parou_por_falhas: boolean; modo: string; message: string;
    };
    const soma = { conferidas: 0, atualizadas: 0, canceladas: 0, naoEncontradas: 0, falhas: 0 };
    let antesDe: number | null = null;
    let parou = false;
    let simulado = false;
    // ⚠️ Teto de voltas: se o servidor um dia devolvesse sempre o mesmo `proximo`,
    // o laço não pode rodar para sempre em cima da cota do Omie.
    for (let volta = 0; volta < 40; volta++) {
      const r: Leva = await api.post<Leva>("/notas/atualizar-do-omie", { antes_de: antesDe });
      soma.conferidas += r.conferidas;
      soma.atualizadas += r.atualizadas.length;
      soma.canceladas += r.canceladas.length;
      soma.naoEncontradas += r.nao_encontradas?.length ?? 0;
      soma.falhas += r.falhas.length;
      simulado = r.modo === "simulado";
      parou = r.parou_por_falhas;
      if (!r.proximo) break;
      antesDe = r.proximo;
      setAndamento(`${soma.conferidas} conferida(s), faltam ${r.restantes}…`);
    }
    const nada = !soma.atualizadas && !soma.canceladas && !soma.naoEncontradas && !soma.falhas;
    const frase =
      soma.conferidas === 0
        ? "nenhuma nota do Omie aberta para reler"
        : `${soma.conferidas} nota(s) aberta(s) relida(s)` +
          (soma.atualizadas ? `, ${soma.atualizadas} com valor diferente` : "") +
          (soma.canceladas ? `, ${soma.canceladas} cancelada(s) lá` : "") +
          (soma.naoEncontradas ? `, ${soma.naoEncontradas} não encontrada(s) lá (excluídas)` : "") +
          (soma.falhas ? `, ${soma.falhas} não abriram` : "") +
          (nada ? " — nada mudou" : "") +
          (simulado ? " (modo simulado — dados de demonstração)" : "");
    return { frase, parou };
  }

  /**
   * 🔑 **Um botão só: Sincronizar** (pedido do dono, 20/10/2026: "criar um botão único
   * de Sincronizar, unindo o buscar no Omie e o atualizar do Omie"). Primeiro traz as
   * notas NOVAS; depois relê as que ainda não foram lançadas — valor corrigido, item
   * trocado, nota cancelada ou excluída lá.
   * ⚠️ Cada metade exige a chave dela: a busca é `integracao.omie`, a releitura é
   * `compras.notas`. Quem tem uma só faz a sua parte, e a frase diz qual.
   */
  async function sincronizar() {
    setConfirmandoSincronizar(false);
    setOcupado(true);
    setErro("");
    const partes: string[] = [];
    let falhou = false;
    try {
      if (pode("integracao.omie")) {
        setAndamento("buscando as novas…");
        try {
          // Sem período: a janela vai desde a última sincronização, com folga.
          const r = await api.post<{ novas: number; modo: string; message: string }>(
            "/omie/sincronizar",
          );
          partes.push(
            (r.message ?? "busca concluída") +
              (r.modo === "simulado" ? " (modo simulado — dados de demonstração)" : ""),
          );
        } catch (e) {
          falhou = true;
          partes.push(`a busca das novas falhou: ${e instanceof Error ? e.message : "sem resposta"}`);
        }
      }
      if (pode("compras.notas")) {
        setAndamento("relendo as abertas…");
        try {
          const r = await releituraDasAbertas();
          partes.push(r.frase);
          if (r.parou) {
            falhou = true;
            partes.push("parei: o Omie recusou várias notas seguidas — tente daqui a pouco");
          }
        } catch (e) {
          falhou = true;
          partes.push(`a releitura falhou: ${e instanceof Error ? e.message : "sem resposta"}`);
        }
      }
      const frase = partes.join(" · ");
      // ⚠️ Parar no meio é ERRO para quem lê: a frase verde faria parecer que acabou.
      (falhou ? aviso.erro : aviso.sucesso)(frase.charAt(0).toUpperCase() + frase.slice(1));
      await carregar();
    } finally {
      setAndamento("");
      setOcupado(false);
    }
  }

  /**
   * 🔑 **Antes do lote, a releitura** (pedido do dono, 20/10/2026: "no botão lançar as
   * conciliadas, antes de abrir a tela, rodar o Atualizar no Omie para garantir a
   * igualdade"). A prévia do lote só sai depois que as abertas estão iguais às do Omie:
   * a cancelada ou excluída lá não entra no estoque por estar desatualizada aqui.
   * ⚠️ Sem `compras.notas` não há releitura (a chave é dela) — o lote abre direto.
   * ⚠️ Releitura que falha NÃO abre o lote calado: a frase diz que ele pode estar velho.
   */
  async function abrirLote() {
    if (!pode("compras.notas")) {
      setVendoLote(true);
      return;
    }
    setOcupado(true);
    setAndamento("relendo do Omie…");
    try {
      const r = await releituraDasAbertas();
      if (r.parou) aviso.erro(`${r.frase}. O Omie recusou várias notas seguidas — a prévia pode estar desatualizada.`);
      else aviso.sucesso(`Antes do lote: ${r.frase}.`);
      await carregar();
    } catch (e) {
      aviso.erro(
        `Não deu para reler do Omie antes do lote (${e instanceof Error ? e.message : "sem resposta"}) — ` +
          "a prévia pode estar desatualizada.",
      );
    } finally {
      setAndamento("");
      setOcupado(false);
    }
    setVendoLote(true);
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
  const [arquivados, setArquivados] = useState<Arquivados | null>(null);
  const [vendoArquivados, setVendoArquivados] = useState(false);
  const [vendoLote, setVendoLote] = useState(false);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="rotulo">Compras</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Notas de entrada
          </h1>
          <ExplicaTela>
            A nota entra por onde for mais fácil — o XML que o fornecedor mandou, a digitação do
            cupom do mercado ou o Omie — e vira estoque avaliado do mesmo jeito. O que decide o
            custo não é o valor unitário da nota: é ele menos desconto, mais frete rateado,
            dividido pelo que realmente entra na prateleira.
          </ExplicaTela>
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
              aria-busy={ocupado} disabled={ocupado}
            >
              {ocupado ? "Lendo…" : "Importar XML"}
            </button>
            <Link href="/compras/nova" className="btn btn-secundario">
              Digitar nota
            </Link>
            {/* 🔑 Compras do período, por nota, fornecedor ou produto (23/10/2026). */}
            <BotaoExportar relatorio="compras" rotulo="Relatório de compras" />
            {/* 🔑 O lote fica sempre à vista para quem lança: a janela é que diz
                quantas estão prontas, quantas travam e o que destrava. */}
            {pode("compras.lancar") && (
              <button
                id="notas-lancar-conciliadas"
                className="btn btn-secundario"
                onClick={() => void abrirLote()}
                aria-busy={ocupado} disabled={ocupado}
                title="Relê do Omie as notas abertas e então lança de uma vez as conciliadas, com prévia"
              >
                Lançar as conciliadas
              </button>
            )}
            {/* 🔑 Um botão só (20/10/2026): buscar as novas + reler as abertas. Cada
                metade com a chave dela — a busca é da integração, a releitura de quem
                confere nota, e quem tem só uma das duas faz a sua parte. */}
            {(pode("integracao.omie") || pode("compras.notas")) && (
              <button
                id="notas-sincronizar"
                className="btn btn-secundario"
                onClick={() => setConfirmandoSincronizar(true)}
                aria-busy={ocupado} disabled={ocupado}
                title="Traz as notas novas do Omie e relê as que ainda não foram lançadas"
              >
                {andamento || "Sincronizar com o Omie"}
              </button>
            )}
            {(arquivados?.itens.length ?? 0) > 0 && (
              <button
                className="btn btn-secundario"
                onClick={() => setVendoArquivados(true)}
                title="Itens de nota aberta apontando para cadastro que foi fundido em outro"
              >
                {arquivados!.itens.length} item(ns) em cadastro arquivado
              </button>
            )}
            {aPendentes > 0 && (
              <button
                className="btn btn-secundario"
                onClick={reconciliar}
                aria-busy={ocupado} disabled={ocupado}
                title="Procura de novo o produto dos itens pendentes"
              >
                Reconciliar {aPendentes} pendente(s)
              </button>
            )}
            {pode("compras.conciliar") && (
              <button
                className="btn btn-secundario"
                onClick={vincularFornecedores}
                aria-busy={ocupado} disabled={ocupado}
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
            <button className="link-acao link-acao-erro" onClick={() => setImportados(null)}>
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
                      <span className="link-registro">
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
        titulo={notas
          ? `${pag.total} nota(s)${resumo && resumo.notas === pag.total ? ` · ${reais(resumo.valor)}` : ""}`
          : "Notas"}
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
        <BarraDeFiltros f={filtros} />
        {/* ⚠️ O valor do título é o que é COMPRA: cancelada e não encontrada no Omie
            ficam fora dele, e a frase diz quando há delas no filtro. */}
        {resumo && resumo.por_status.some((s) => s.status === "CANCELADA" || s.status === "NAO_ENCONTRADA") && (
          <p className="mb-2 text-[12.5px] text-suave">
            O valor não soma as canceladas nem as não encontradas no Omie.
          </p>
        )}
        {!notas ? (
          <Carregando />
        ) : !notas.length ? (
          <Vazio>
            {filtros.ativos
              ? "Nenhuma nota com esses filtros."
              : busca
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
                  <span className="link-registro">
                    NF {n.numero ?? "—"} · {n.fornecedor ?? n.nome_emitente ?? "sem fornecedor"}
                  </span>
                  <span className="block text-[13px] text-suave">
                    {n.data_emissao ? dataBr(n.data_emissao) : "sem data"} · {n.itens} item(ns) ·{" "}
                    {reais(Number(n.valor_total))}
                  </span>
                </Link>
                <span className="flex items-center gap-2">
                  {n.pendentes > 0 && <Etiqueta cor="alerta">{n.pendentes} pendente(s)</Etiqueta>}
                  <Etiqueta cor={CORES[n.status]}>{rotuloStatus(n.status)}</Etiqueta>
                </span>
              </li>
            ))}
          </ul>
        )}
        <Paginacao p={pag} rotulo="nota(s)" />
      </Cartao>

      {/* 🔑 **A prévia inteira antes do botão único** (pedido do dono). São
          dezenas de linhas de uma vez, e aprovar uma a uma seria um dia de
          trabalho — mas repontar às cegas é pior. A janela mostra de onde para
          onde cada item vai, e o botão faz tudo o que está listado. */}
      {confirmandoSincronizar && (
        <Confirmacao
          titulo="Sincronizar com o Omie?"
          rotuloConfirmar="Sincronizar"
          aoConfirmar={() => void sincronizar()}
          aoCancelar={() => setConfirmandoSincronizar(false)}
        >
          <p>
            Duas coisas, nesta ordem: as notas <b>novas</b> do Omie entram, e cada nota que
            ainda não foi lançada é <b>relida</b> de lá — valor corrigido, item trocado e nota{" "}
            <b>cancelada</b> ou <b>excluída</b> chegam aqui. Os produtos que você já vinculou
            são mantidos.
          </p>
          <p className="mt-2 text-[13.5px] text-suave">
            É uma consulta por nota, com uma pequena espera entre elas para não bloquear a
            conta no Omie — com muitas notas abertas leva alguns minutos. Nota já lançada
            não é mexida.
          </p>
        </Confirmacao>
      )}

      {vendoLote && (
        <LancarLote aoFechar={() => setVendoLote(false)} aoLancar={() => void carregar()} />
      )}

      {vendoArquivados && arquivados && (
        <Modal
          titulo="Itens apontando para cadastro arquivado"
          descricao={`${arquivados.itens.length} item(ns) em ${arquivados.notas} nota(s) ainda não lançada(s)`}
          aoFechar={() => setVendoArquivados(false)}
          largura="900px"
          rodape={
            <div className="flex flex-wrap items-center justify-end gap-3">
              <span className="text-[13px] text-suave">
                Nota já lançada fica de fora: lá o razão concorda com a nota.
              </span>
              <button
                className="btn btn-secundario"
                onClick={() => setVendoArquivados(false)}
              >
                Fechar
              </button>
              <button
                className="btn btn-primario"
                aria-busy={ocupado} disabled={ocupado}
                onClick={async () => {
                  setOcupado(true);
                  try {
                    const r = await api.post<{ message: string }>(
                      "/notas/arquivados/repontar", {});
                    aviso.sucesso(r.message);
                    setVendoArquivados(false);
                    await carregar();
                  } catch (e) {
                    aviso.erro(e instanceof Error ? e.message : "Não foi possível repontar");
                  } finally {
                    setOcupado(false);
                  }
                }}
              >
                {ocupado ? "Repontando…" : `Repontar os ${arquivados.itens.length}`}
              </button>
            </div>
          }
        >
          <Aviso tipo="info">
            Estes itens apontam para um cadastro que foi <b>fundido em outro</b>. Lançar
            assim poria o estoque no cadastro arquivado — fora da ficha e fora do custo do
            que está em uso. Como as notas <b>ainda não foram lançadas</b>, nada entrou no
            razão e dá para corrigir.
          </Aviso>

          {arquivados.sem_destino.length > 0 && (
            <Aviso tipo="erro">
              Outros <b>{arquivados.sem_destino.length}</b> item(ns) apontam para cadastro
              arquivado que <b>ninguém ativo herdou</b> — não há para onde repontar sozinho.
              Esses precisam de escolha na tela da nota.
            </Aviso>
          )}

          <div className="mt-4 grid-rolante">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Nota</th>
                  <th>Item</th>
                  <th className="num">Qtd</th>
                  <th>Aponta para (arquivado)</th>
                  <th>Passa a apontar para</th>
                </tr>
              </thead>
              <tbody>
                {arquivados.itens.map((l) => (
                  <tr key={l.id}>
                    <td className="whitespace-nowrap">
                      <Link href={`/compras/${l.id_nota}`} className="link-acao">
                        NF {l.numero ?? "—"}
                      </Link>
                      <span className="block text-[12px] text-suave">
                        {l.fornecedor ?? "—"}
                      </span>
                    </td>
                    <td className="text-[13.5px]">{l.descricao_fornecedor}</td>
                    <td className="num whitespace-nowrap">
                      {qtd(l.quantidade)} {l.um_nota ?? ""}
                    </td>
                    <td className="text-[13.5px] text-suave">
                      <span className="mono">{l.codigo_arquivado}</span> {l.arquivado}
                    </td>
                    <td className="text-[13.5px] font-medium text-erva">
                      <span className="mono">{l.destino?.codigo}</span> {l.destino?.nome}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
    </div>
  );
}
