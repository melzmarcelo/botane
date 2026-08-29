"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import BuscaCadastro from "@/components/busca-cadastro";
import FiltroMultiplo from "@/components/filtro-multiplo";
import { useAviso } from "@/components/aviso-flutuante";
import { Aviso, Campo, Carregando, Modal } from "@/components/ui";
import { api } from "@/lib/api";
import { fonteProdutos } from "@/lib/busca-cadastro";

/**
 * Baixar deixou de ser um clique cego.
 *
 * Antes, cada tela tinha um botão que despejava a planilha inteira: o cadastro
 * de produtos saía com os 3.226, sempre, e a posição de estoque com todos os
 * locais. Agora o botão abre esta janela — os filtros PERTINENTES àquele
 * processo, todos de escolha múltipla, e a escolha entre planilha e PDF.
 *
 * 🔑 **Quem diz quais são os filtros é o SERVIDOR** (`GET /exportar/catalogo`).
 * Escrever a lista aqui criaria a segunda cópia do que já existe lá — e ela
 * divergiria **calada**: a tela ofereceria um filtro que o servidor ignora, o
 * arquivo sairia com mais linhas do que se pediu, e nada denunciaria.
 *
 * ⚠️ **A prévia diz quantas linhas viriam ANTES do botão.** É a mesma ideia da
 * prévia do inventário: numa base real o filtro em branco traz o cadastro
 * inteiro, e descobrir isso depois custa abrir um arquivo de 3.226 linhas para
 * ver que não era aquilo.
 */

type Opcao = { valor: string | number; nome: string };

type FiltroDoServidor = {
  nome: string;
  tipo: "periodo" | "multipla" | "produtos" | "texto" | "numero";
  rotulo: string;
  ajuda: string;
  opcoes?: Opcao[];
};

type RelatorioDoServidor = {
  chave: string;
  rotulo: string;
  descricao: string;
  filtros: FiltroDoServidor[];
};

type Previa = { linhas: number; titulo: string; cabe_no_pdf: boolean; maximo_pdf: number };

export type ValoresIniciais = Record<string, unknown>;

/**
 * O catálogo é pedido UMA vez por carregamento da página, não por botão.
 *
 * ⚠️ Duas telas têm dois botões (o CMV tem o do cabeçalho e o da aba), e sem o
 * cache cada um pediria o próprio catálogo — que resolve 99 locais, 70
 * categorias e 37 setores no servidor. A promessa é compartilhada: quem chegar
 * enquanto a primeira está no ar espera a MESMA, em vez de abrir outra.
 */
let catalogoEmCurso: Promise<RelatorioDoServidor[]> | null = null;

function pedirCatalogo(): Promise<RelatorioDoServidor[]> {
  if (!catalogoEmCurso) {
    catalogoEmCurso = api.get<RelatorioDoServidor[]>("/exportar/catalogo").catch((e) => {
      // Falha não pode virar cache: a próxima tentativa tem de ir ao servidor.
      catalogoEmCurso = null;
      throw e;
    });
  }
  return catalogoEmCurso;
}

/** Os valores viram query string: lista repete a chave, vazio não vai. */
function comoQuery(valores: ValoresIniciais): string {
  const q = new URLSearchParams();
  for (const [chave, valor] of Object.entries(valores)) {
    if (valor === null || valor === undefined || valor === "") continue;
    if (Array.isArray(valor)) {
      for (const v of valor) q.append(chave, String(v));
    } else {
      q.set(chave, String(valor));
    }
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

function Dialogo({
  relatorio,
  iniciais,
  avulso,
  formatoPadrao,
  aoFechar,
}: {
  relatorio: string;
  iniciais: ValoresIniciais;
  /**
   * ⚠️ O padrão é planilha porque a maioria dos relatórios é para CONFERIR.
   * Mas há documentos cujo destino é o papel — a ficha técnica que fica
   * pendurada na cozinha e a folha de contagem —, e ali abrir em "planilha"
   * faz a pessoa escolher errado por inércia.
   */
  formatoPadrao?: "csv" | "pdf";
  /**
   * Um relatório de UM registro — a folha de contagem de um inventário. Não
   * está no catálogo (não tem recorte a oferecer: é aquele inventário), então a
   * janela pula os filtros e pergunta só o formato.
   */
  avulso?: { rotulo: string; descricao: string };
  aoFechar: () => void;
}) {
  const aviso = useAviso();
  const [rel, setRel] = useState<RelatorioDoServidor | null>(
    avulso ? { chave: relatorio, ...avulso, filtros: [] } : null,
  );
  const [erro, setErro] = useState("");
  const [valores, setValores] = useState<ValoresIniciais>(iniciais);
  const [formato, setFormato] = useState<"csv" | "pdf">(formatoPadrao ?? "csv");
  const [previa, setPrevia] = useState<Previa | null>(null);
  const [contando, setContando] = useState(false);
  const [baixando, setBaixando] = useState(false);
  // Os produtos escolhidos guardam o rótulo junto: a etiqueta precisa do nome,
  // e o servidor só recebe o id. Vêm semeados quando a TELA já tinha um produto
  // fixado — é o que faz o arquivo bater com o que está à vista.
  const [produtos, setProdutos] = useState<{ id: number; rotulo: string }[]>(
    Array.isArray(iniciais.produtos)
      ? (iniciais.produtos as { id: number; rotulo: string }[])
      : [],
  );

  useEffect(() => {
    if (avulso) return;
    let vivo = true;
    pedirCatalogo()
      .then((lista) => {
        if (!vivo) return;
        const achado = lista.find((r) => r.chave === relatorio);
        if (!achado) setErro("Este relatório não está disponível para o seu acesso.");
        setRel(achado ?? null);
      })
      .catch((e) => vivo && setErro(e.message ?? "Falha ao carregar os filtros."));
    return () => {
      vivo = false;
    };
  }, [relatorio, avulso]);

  const query = useMemo(
    () => comoQuery({ ...valores, produtos: produtos.map((p) => p.id) }),
    [valores, produtos],
  );

  // ⚠️ A prévia é PEDIDA ao servidor, com um respiro: sem o atraso, cada
  // caixinha marcada dispara uma contagem, e o razão de um mês custa segundos.
  useEffect(() => {
    if (!rel || avulso) return;
    setContando(true);
    const t = setTimeout(() => {
      api
        .get<Previa>(`/exportar/${rel.chave}/previa${query}`)
        .then(setPrevia)
        .catch(() => setPrevia(null))
        .finally(() => setContando(false));
    }, 450);
    return () => clearTimeout(t);
  }, [rel, query, avulso]);

  const trocar = useCallback(
    (nome: string, valor: unknown) => setValores((v) => ({ ...v, [nome]: valor })),
    [],
  );

  async function baixar() {
    if (!rel) return;
    setBaixando(true);
    try {
      // A extensão vai no CAMINHO: é ela que decide o formato, e assim a URL
      // que gerou o arquivo nunca discorda do arquivo.
      await api.baixar(`/exportar/${rel.chave}.${formato}${query}`);
      aviso.sucesso(
        formato === "pdf" ? "PDF gerado." : "Planilha gerada.",
      );
      aoFechar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao gerar o arquivo.");
    } finally {
      setBaixando(false);
    }
  }

  const naoCabeNoPdf = formato === "pdf" && previa && !previa.cabe_no_pdf;

  return (
    <Modal
      titulo={rel ? `Baixar — ${rel.rotulo}` : "Baixar"}
      descricao={rel?.descricao}
      aoFechar={aoFechar}
      largura="680px"
      /* ⚠️ Fora da rolagem: com cinco filtros a janela passa da altura da tela,
         e um botão de baixar que rolou para fora da vista é um botão que não
         existe. A contagem fica ao lado dele porque é o número que se olha
         imediatamente antes de clicar. */
      rodape={
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[13.5px] text-suave">
            {avulso
              ? ""
              : contando
                ? "contando…"
                : previa
                  ? `${previa.linhas.toLocaleString("pt-BR")} linha(s) neste recorte`
                  : "—"}
          </p>
          <div className="flex gap-2">
            <button type="button" className="btn btn-secundario" onClick={aoFechar}>
              Cancelar
            </button>
            <button
              type="button"
              className="btn btn-primario"
              onClick={() => void baixar()}
              disabled={baixando || !!naoCabeNoPdf || !!erro}
            >
              {baixando ? "Gerando…" : formato === "pdf" ? "Baixar PDF" : "Baixar planilha"}
            </button>
          </div>
        </div>
      }
    >
      {erro ? (
        <Aviso tipo="erro">{erro}</Aviso>
      ) : !rel ? (
        <Carregando />
      ) : (
        <div className="flex flex-col gap-5">
          {!rel.filtros.length ? (
            <p className="text-[14px] text-suave">Este relatório sai inteiro, sem recorte.</p>
          ) : (
            <div className="grid gap-5 sm:grid-cols-2">
              {rel.filtros.map((f) => {
                if (f.tipo === "periodo") {
                  return (
                    <div key={f.nome} className="flex flex-col gap-2 sm:col-span-2">
                      <div>
                        <span className="rotulo">{f.rotulo}</span>
                        <p className="mt-0.5 text-[12.5px] text-suave">{f.ajuda}</p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <input
                          type="date"
                          className="campo w-auto"
                          value={String(valores.inicio ?? "")}
                          onChange={(e) => trocar("inicio", e.target.value)}
                        />
                        <span className="text-[13px] text-suave">até</span>
                        <input
                          type="date"
                          className="campo w-auto"
                          value={String(valores.fim ?? "")}
                          onChange={(e) => trocar("fim", e.target.value)}
                        />
                      </div>
                    </div>
                  );
                }

                if (f.tipo === "multipla") {
                  return (
                    <FiltroMultiplo
                      key={f.nome}
                      titulo={f.rotulo}
                      ajuda={f.ajuda}
                      opcoes={f.opcoes ?? []}
                      escolhidos={(valores[f.nome] as (string | number)[]) ?? []}
                      aoTrocar={(v) => trocar(f.nome, v)}
                    />
                  );
                }

                if (f.tipo === "produtos") {
                  // ⚠️ Produto NÃO vira lista de caixinhas: são milhares. Vai
                  // pela busca da casa, que pergunta ao servidor, e o que se
                  // escolhe fica como etiqueta — para a lista curta não parecer
                  // curta por acaso.
                  return (
                    <div key={f.nome} className="flex min-w-0 flex-col sm:col-span-2">
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="rotulo">{f.rotulo}</span>
                        {produtos.length > 0 && (
                          <button
                            type="button"
                            className="link-acao"
                            onClick={() => setProdutos([])}
                          >
                            limpar
                          </button>
                        )}
                      </div>
                      <p className="mt-0.5 text-[12.5px] text-suave">
                        {produtos.length ? `${produtos.length} escolhido(s)` : f.ajuda}
                      </p>
                      <BuscaCadastro
                        className="mt-2"
                        fonte={fonteProdutos()}
                        selecionado={null}
                        aoEscolher={(item) => {
                          if (!item) return;
                          setProdutos((l) =>
                            l.some((p) => p.id === item.id)
                              ? l
                              : [...l, { id: item.id, rotulo: item.nome }],
                          );
                        }}
                      />
                      {produtos.length > 0 && (
                        <ul className="mt-2 flex flex-wrap gap-1.5">
                          {produtos.map((p) => (
                            <li
                              key={p.id}
                              className="flex items-center gap-1.5 rounded-full border border-erva bg-erva-claro px-2.5 py-1 text-[12.5px] text-erva"
                            >
                              {p.rotulo}
                              <button
                                type="button"
                                aria-label={`tirar ${p.rotulo}`}
                                className="text-[15px] leading-none"
                                onClick={() =>
                                  setProdutos((l) => l.filter((x) => x.id !== p.id))
                                }
                              >
                                ×
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  );
                }

                return (
                  <Campo key={f.nome} rotulo={f.rotulo} dica={f.ajuda}>
                    <input
                      className="campo"
                      type={f.tipo === "numero" ? "number" : "text"}
                      value={String(valores[f.nome] ?? "")}
                      onChange={(e) => trocar(f.nome, e.target.value)}
                    />
                  </Campo>
                );
              })}
            </div>
          )}

          <div>
            <span className="rotulo">Formato</span>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              {(
                [
                  {
                    id: "csv" as const,
                    nome: "Planilha",
                    diz: "Abre no Excel e soma. É a que se confere linha a linha.",
                  },
                  {
                    id: "pdf" as const,
                    nome: "PDF",
                    diz: "Para ler, imprimir ou mandar ao contador. Não se edita.",
                  },
                ]
              ).map((op) => (
                <button
                  key={op.id}
                  type="button"
                  aria-pressed={formato === op.id}
                  onClick={() => setFormato(op.id)}
                  className={`rounded border p-3 text-left transition-colors ${
                    formato === op.id
                      ? "border-erva bg-erva-claro"
                      : "border-linha2 bg-superficie hover:border-erva"
                  }`}
                >
                  <span className="block font-display text-[15px] font-semibold">
                    {op.nome}
                  </span>
                  <span className="mt-0.5 block text-[12.5px] leading-snug text-suave">
                    {op.diz}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {naoCabeNoPdf && (
            <Aviso tipo="erro">
              São {previa!.linhas.toLocaleString("pt-BR")} linhas — o PDF para acima de{" "}
              {previa!.maximo_pdf.toLocaleString("pt-BR")}, porque vira um arquivo de
              milhares de páginas que ninguém abre. Estreite o filtro ou baixe a planilha,
              que não tem teto.
            </Aviso>
          )}

        </div>
      )}
    </Modal>
  );
}

/**
 * O botão de baixar de uma tela. Uma linha por tela — a janela vem junto.
 *
 * ⚠️ `iniciais` semeia a janela com o que a TELA já está filtrando. Sem isso,
 * filtrar na tela e clicar em baixar daria outro arquivo — e quem conferisse os
 * dois acharia que um dos dois mente.
 */
export default function BotaoExportar({
  relatorio,
  iniciais = {},
  rotulo = "Baixar",
  className = "btn btn-secundario",
  avulso,
  formatoPadrao,
}: {
  relatorio: string;
  iniciais?: ValoresIniciais;
  rotulo?: string;
  className?: string;
  avulso?: { rotulo: string; descricao: string };
  formatoPadrao?: "csv" | "pdf";
}) {
  const [aberto, setAberto] = useState(false);
  // ⚠️ Quem decide se o botão existe é o CATÁLOGO, não uma cópia da regra de
  // permissão escrita aqui: `/cmv` abre com `cmv.painel` e a exportação exige
  // `cmv.relatorios`, então havia quem visse o botão e só descobrisse ao abrir
  // a janela. Enquanto a resposta não chega o botão fica de fora — piscar um
  // controle que some é pior que ele aparecer meio segundo depois.
  const [permitido, setPermitido] = useState<boolean | null>(avulso ? true : null);
  useEffect(() => {
    if (avulso) return;
    let vivo = true;
    pedirCatalogo()
      .then((lista) => vivo && setPermitido(lista.some((r) => r.chave === relatorio)))
      // Falha ao listar não pode ESCONDER a exportação de quem tem direito a
      // ela: o botão fica, e a janela explica o que houve.
      .catch(() => vivo && setPermitido(true));
    return () => {
      vivo = false;
    };
  }, [relatorio, avulso]);

  if (!permitido) return null;

  return (
    <>
      <button type="button" className={className} onClick={() => setAberto(true)}>
        {rotulo}
      </button>
      {aberto && (
        <Dialogo
          relatorio={relatorio}
          iniciais={iniciais}
          avulso={avulso}
          formatoPadrao={formatoPadrao}
          aoFechar={() => setAberto(false)}
        />
      )}
    </>
  );
}
