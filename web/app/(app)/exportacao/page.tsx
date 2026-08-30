"use client";

import { useCallback, useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Carregando, Cartao, Confirmacao, Etiqueta, Vazio } from "@/components/ui";
import { Paginacao, fatiar, usePaginacao } from "@/components/paginacao";
import { api } from "@/lib/api";
import { reais } from "@/lib/cadastros";
import { useSessao } from "@/lib/sessao";

/**
 * Exportação para o PDV — o que daqui ainda não está no cardápio de lá.
 *
 * 🔑 **A aba "pendentes" é uma CONSULTA, não uma tabela.** O servidor compara o
 * que seria enviado agora com o que foi enviado da última vez, e pergunta ao
 * PDV o que já existe do outro lado. Uma fila mantida à mão precisaria ser
 * alimentada em todo lugar que salva um cadastro — e o próximo lugar, que vai
 * existir, nasceria sem ela.
 *
 * ⚠️ **`ADOTAR` é o caso mais comum na primeira vez, e é o que evita o
 * desastre.** Os 30 grupos do cardápio existem há anos e nunca souberam do
 * Botané; sem reconhecê-los, o primeiro envio criaria 29 duplicados. Adotar é
 * um update que só grava o nosso código lá — nome, cor e situação ficam como
 * estão.
 */

type Item = {
  tipo: string;
  id_registro: number;
  nome: string;
  acao: string;
  corpo: Record<string, unknown>;
  codigo_pdv: string | null;
  nome_no_pdv: string | null;
  /** O que impede este registro de sair, dito com as palavras da casa. */
  impedimento: string | null;
  /** O preço daqui e o que está na tabela do PDV — os dois, para comparar. */
  preco: number | null;
  preco_no_pdv: number | null;
};

type Erro = {
  tipo: string;
  id_registro: number;
  nome: string;
  acao: string;
  erro: string;
  enviado: Record<string, unknown> | null;
  quando: string;
};

type Fila = { pendentes: Item[]; integrados: Item[]; erros: Erro[] };

type Aba = "pendentes" | "integrados" | "erros";

const COR_DA_ACAO: Record<string, "neutro" | "erva" | "alerta"> = {
  ADOTAR: "erva",
  CRIAR: "erva",
  ATUALIZAR: "neutro",
  DESATIVAR: "alerta",
};

const EXPLICA: Record<string, string> = {
  ADOTAR: "já existe no PDV com este nome — o envio só grava o vínculo, sem mexer no resto",
  CRIAR: "não existe no PDV — será cadastrado",
  ATUALIZAR: "existe e mudou aqui",
  DESATIVAR: "saiu da integração aqui — será desativado lá",
};

/**
 * ⚠️ A mesma ação quer dizer coisas diferentes nas duas abas: em **pendentes**
 * é o que VAI acontecer; em **integrados**, o que ACONTECEU. "desativar" e
 * "desativada" são o antes e o depois do mesmo clique.
 */
function estadoIntegrado(i: Item): { rotulo: string; explica: string } {
  if (i.acao !== "DESATIVAR") return { rotulo: "no cardápio", explica: "" };
  const ativoLa = (i.corpo as { ativo_no_pdv?: boolean }).ativo_no_pdv;
  if (i.tipo === "SETOR")
    return {
      rotulo: "fora da integração",
      explica:
        "saiu daqui, mas continua vinculado no PDV — a impressora não tem como ser " +
        "desativada pela API. Remarcar aqui o reconhece de novo, sem recriar.",
    };
  return {
    rotulo: ativoLa === false ? "desativada" : "fora da integração",
    explica:
      ativoLa === false
        ? "desativada no cardápio do PDV — não aparece mais para quem vende"
        : "saiu daqui e continua ativa no PDV",
  };
}

export default function PaginaExportacao() {
  const aviso = useAviso();
  const { eu } = useSessao();
  const [fila, setFila] = useState<Fila | null>(null);
  const [erroTela, setErroTela] = useState("");
  const [aba, setAba] = useState<Aba>("pendentes");
  const [enviando, setEnviando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  // 🔑 **Sem seleção, o único botão da tela manda TUDO.** Com 119 pendentes,
  // quem quer conferir o envio de UM cadastro não tem como — e o clique
  // reescreve o cardápio inteiro de quem está vendendo. A chave é
  // `tipo-id_registro` porque id sozinho colide entre produto e categoria.
  const [marcados, setMarcados] = useState<Set<string>>(new Set());
  /**
   * ⚠️ **Aqui o corte é do NAVEGADOR de propósito** — é a mesma exceção da
   * movimentação do CMV. A fila não é uma consulta com `LIMIT`: ela é DERIVADA,
   * comparando cada cadastro marcado com o cardápio inteiro do PDV. Paginar no
   * servidor não pouparia trabalho nenhum, e o botão "Enviar" precisa saber de
   * todos os pendentes, não dos vinte que estão à vista.
   *
   * ⚠️ A aba entra como filtro: são três listas de tamanhos muito diferentes
   * (630 integrados contra zero erros), e continuar na página 8 ao trocar de
   * aba mostraria uma tela vazia.
   */
  const pag = usePaginacao("exportacao-pdv", { filtros: [aba] });

  const carregar = useCallback(async () => {
    setErroTela("");
    try {
      setFila(await api.get<Fila>("/pdv/envio/fila"));
    } catch (e) {
      // ⚠️ Erro de CARREGAMENTO fica inline: é ele que explica a tela vazia.
      setFila(null);
      setErroTela(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function enviar(itens?: Item[]) {
    setEnviando(true);
    try {
      const r = await api.post<{ enviados: number; falhas: number; message: string }>(
        "/pdv/envio",
        // ⚠️ Corpo vazio quer dizer "tudo o que está pendente" — é o servidor
        // que decide, relendo a fila. Mandar a lista da tela como se fosse a
        // fila faria o envio agir sobre uma fotografia velha.
        itens?.length ? { itens: itens.map((i) => ({ tipo: i.tipo, id_registro: i.id_registro })) } : {},
      );
      if (r.falhas) aviso.erro(r.message);
      else aviso.sucesso(r.message);
      setMarcados(new Set());
      await carregar();
      if (r.falhas) setAba("erros");
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível enviar");
    } finally {
      setEnviando(false);
      setConfirmando(false);
    }
  }

  if (!eu?.enviar_ao_pdv) {
    return (
      <div className="flex flex-col gap-6">
        <header>
          <p className="rotulo">Cadastros</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight">Exportação para o PDV</h1>
        </header>
        <Aviso tipo="info">
          O envio ao PDV está desligado. Ligue em <b>Integrações ▸ PDV Legal</b>, em
          &ldquo;Enviar informações ao PDV&rdquo;.
        </Aviso>
      </div>
    );
  }

  const pendentes = fila?.pendentes ?? [];
  const chave = (i: Item) => `${i.tipo}-${i.id_registro}`;
  const selecionados = pendentes.filter((i) => marcados.has(chave(i)));
  // Sem nada marcado, o botão vale por todos — é o caminho comum.
  const aEnviar = selecionados.length ? selecionados : pendentes;
  const desativacoes = aEnviar.filter((p) => p.acao === "DESATIVAR").length;
  const daAba: (Item | Erro)[] =
    aba === "pendentes" ? pendentes : aba === "integrados" ? (fila?.integrados ?? []) : (fila?.erros ?? []);
  const { setTotal } = pag;
  useEffect(() => {
    setTotal(daAba.length);
  }, [daAba.length, setTotal]);

  // As linhas desta página — usadas pela tabela e pela caixinha do cabeçalho,
  // que marca a PÁGINA e não a fila inteira.
  const naPagina = fatiar(
    aba === "pendentes" ? pendentes : (fila?.integrados ?? []),
    pag,
  );

  function alternar(i: Item) {
    setMarcados((m) => {
      const n = new Set(m);
      if (!n.delete(chave(i))) n.add(chave(i));
      return n;
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="rotulo">Cadastros</p>
          <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">
            Exportação para o PDV
          </h1>
          <p className="mt-1 max-w-[68ch] text-suave">
            O que está marcado como integrado aqui e ainda não chegou ao cardápio do PDV.
            Nada sai sozinho — o envio é sempre disparado por alguém.
          </p>
        </div>
        {!!pendentes.length && (
          <button
            className="btn btn-primario"
            disabled={enviando}
            onClick={() => (desativacoes ? setConfirmando(true) : void enviar(selecionados))}
          >
            {enviando
              ? "Enviando…"
              : selecionados.length
                ? `Enviar ${selecionados.length} selecionado(s)`
                : `Enviar ${pendentes.length} pendente(s)`}
          </button>
        )}
      </header>

      {erroTela && <Aviso tipo="erro">{erroTela}</Aviso>}

      <nav className="flex gap-1 border-b border-linha">
        {(
          [
            ["pendentes", "Pendentes", pendentes.length],
            ["integrados", "Integrados", fila?.integrados.length ?? 0],
            ["erros", "Erros", fila?.erros.length ?? 0],
          ] as const
        ).map(([id, nome, n]) => (
          <button
            key={id}
            onClick={() => setAba(id)}
            className={`-mb-px border-b-2 px-3 py-2 text-[14.5px] ${
              aba === id
                ? "border-erva font-semibold text-erva"
                : "border-transparent text-suave hover:text-tinta"
            }`}
          >
            {nome} ({n})
          </button>
        ))}
      </nav>

      {!fila ? (
        <Carregando />
      ) : (
        <Cartao>
          {aba === "erros" ? (
            !fila.erros.length ? (
              <Vazio>Nenhum erro.</Vazio>
            ) : (
              <>
              <ul className="flex flex-col gap-px bg-linha">
                {(fatiar(fila.erros, pag) as Erro[]).map((e) => (
                  <li key={`${e.tipo}-${e.id_registro}`} className="bg-superficie py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{e.nome}</span>
                      <Etiqueta>{e.tipo.toLowerCase()}</Etiqueta>
                      <Etiqueta cor="alerta">{e.acao.toLowerCase()}</Etiqueta>
                    </div>
                    <p className="mt-1 text-[13.5px] text-erro">{e.erro}</p>
                    {/* ⚠️ O corpo enviado fica à vista: "erro 400" sozinho não
                        diz o que ajustar — com o que foi mandado ao lado, quem
                        olha vê que faltou o grupo ou que o nome já existe. */}
                    {e.enviado && (
                      <pre className="mono mt-1.5 overflow-x-auto rounded bg-superficie2 p-2 text-[12px] text-suave">
                        {JSON.stringify(e.enviado)}
                      </pre>
                    )}
                  </li>
                ))}
              </ul>
              <Paginacao p={pag} rotulo="erro(s)" />
              </>
            )
          ) : (aba === "pendentes" ? pendentes : fila.integrados).length === 0 ? (
            <Vazio>
              {aba === "pendentes"
                ? "Nada pendente — o PDV está com tudo o que está marcado aqui."
                : "Nada integrado ainda."}
            </Vazio>
          ) : (
            <>
              <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    {aba === "pendentes" && (
                      <th className="w-[38px]">
                        <input
                          type="checkbox"
                          aria-label="marcar todos"
                          // ⚠️ Marca a PÁGINA, não a fila inteira: uma caixinha
                          // no cabeçalho de uma tabela paginada que selecionasse
                          // 600 linhas invisíveis seria uma armadilha — e quem
                          // quer mandar tudo já tem o botão, que sem seleção
                          // vale por todos.
                          checked={
                            !!naPagina.length && naPagina.every((i) => marcados.has(chave(i)))
                          }
                          onChange={(e) => {
                            const daPagina = new Set(naPagina.map(chave));
                            setMarcados((m) => {
                              const n = new Set(m);
                              daPagina.forEach((k) => (e.target.checked ? n.add(k) : n.delete(k)));
                              return n;
                            });
                          }}
                        />
                      </th>
                    )}
                    <th>O quê</th>
                    <th>Nome</th>
                    <th>{aba === "pendentes" ? "Ação" : "Situação"}</th>
                    <th>No PDV</th>
                  </tr>
                </thead>
                <tbody>
                  {naPagina.map((i) => (
                    <tr key={`${i.tipo}-${i.id_registro}`}>
                      {aba === "pendentes" && (
                        <td>
                          <input
                            type="checkbox"
                            aria-label={`marcar ${i.nome}`}
                            checked={marcados.has(chave(i))}
                            onChange={() => alternar(i)}
                          />
                        </td>
                      )}
                      <td className="text-[13px] text-suave">{i.tipo.toLowerCase()}</td>
                      <td className="font-medium">{i.nome}</td>
                      <td>
                        {aba === "pendentes" ? (
                          <>
                            <Etiqueta cor={COR_DA_ACAO[i.acao] ?? "neutro"}>
                              {i.acao.toLowerCase()}
                            </Etiqueta>
                            <span className="mt-0.5 block text-[12.5px] leading-snug text-suave">
                              {EXPLICA[i.acao]}
                            </span>
                            {/* ⚠️ O que trava aparece ANTES do clique. Sem isto
                                a pessoa manda, espera, e recebe a frase do PDV
                                — que não nomeia a categoria nem diz o caminho. */}
                            {/* 🔑 **Preço divergente era INVISÍVEL dos dois lados.**
                                Com o Botané dono do preço, o cardápio parou de
                                trazê-lo e a fila comparava só nome e grupo: o
                                valor alterado no PDV não constava aqui, e o
                                envio seguinte o sobrescrevia calado. Os dois
                                juntos, porque "atualizar" sozinho faria abrir o
                                PDV para saber qual dos dois está velho. */}
                            {i.preco != null &&
                              i.preco_no_pdv != null &&
                              Number(i.preco) !== Number(i.preco_no_pdv) && (
                                <span className="mt-0.5 block text-[12.5px] leading-snug text-alerta">
                                  preço {reais(Number(i.preco))} aqui · {reais(Number(i.preco_no_pdv))}{" "}
                                  no PDV
                                </span>
                              )}
                            {i.impedimento && (
                              <span className="mt-1 block text-[12.5px] leading-snug text-erro">
                                {i.impedimento}
                              </span>
                            )}
                          </>
                        ) : (
                          <>
                            <Etiqueta cor={i.acao === "DESATIVAR" ? "alerta" : "erva"}>
                              {estadoIntegrado(i).rotulo}
                            </Etiqueta>
                            {!!estadoIntegrado(i).explica && (
                              <span className="mt-0.5 block max-w-[52ch] text-[12.5px] leading-snug text-suave">
                                {estadoIntegrado(i).explica}
                              </span>
                            )}
                          </>
                        )}
                      </td>
                      <td className="mono text-[13px] text-suave">
                        {i.nome_no_pdv ? (
                          <>
                            {i.nome_no_pdv}
                            {i.codigo_pdv ? ` · ${i.codigo_pdv}` : ""}
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
              {/* ⚠️ FORA do `overflow-x-auto`: dentro dele, numa tabela larga o
                  rodapé sai da vista junto com as colunas da direita — e o
                  controle de página é justamente o que não pode sumir. */}
              <Paginacao
                p={pag}
                rotulo={aba === "pendentes" ? "pendente(s)" : "integrado(s)"}
              />
            </>
          )}
        </Cartao>
      )}

      {/* ⚠️ Desativar mexe no cardápio de quem está vendendo — pergunta antes,
          e diz o que a ação FAZ, não só "tem certeza". */}
      {confirmando && (
        <Confirmacao
          titulo="Enviar ao PDV"
          rotuloConfirmar="Enviar"
          ocupado={enviando}
          aoConfirmar={() => void enviar(selecionados)}
          aoCancelar={() => setConfirmando(false)}
        >
          <p>
            São {aEnviar.length} registro(s), e {desativacoes} deles{" "}
            <b>serão desativados no cardápio do PDV</b> — deixam de aparecer para quem
            vende. Os demais são cadastros ou vínculos.
          </p>
        </Confirmacao>
      )}
    </div>
  );
}
