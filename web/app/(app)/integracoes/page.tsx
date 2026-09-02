"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import EmailSmtp from "./email-smtp";
import NotasOmie from "./notas-omie";
import PdvLegal from "./pdv-legal";

type Config = {
  configurada: boolean;
  modo: string;
  ativa: boolean;
  app_key: string | null;
  app_secret: string | null;
  tag_fornecedor: string | null;
  agenda_frequencia: string;
  agenda_hora: number;
  agenda_janela_dias: number | null;
  /** Quando o agendador RODOU — não é o mesmo que ter trazido nota. */
  agenda_rodou_em: string | null;
  agenda_ultimo_erro: string | null;
  ultima_sincronizacao: string | null;
  ultimo_status: string | null;
  ultima_mensagem: string | null;
  historico: {
    chamada: string;
    status: string;
    registros: number;
    mensagem: string | null;
    modo: string;
    iniciado_em: string;
  }[];
};

type LinhaConferencia = {
  id_produto: number;
  codigo: string;
  produto: string;
  um_estoque: string | null;
  codigo_omie: string;
  saldo_botane: number;
  saldo_omie: number;
  diferenca_saldo: number;
  custo_medio_botane: number;
  cmc_omie: number;
  diferenca_custo: number;
  divergente: boolean;
};

/**
 * ⚠️ A resposta é um OBJETO, não uma lista.
 *
 * Lista sozinha não conseguia dizer quantos foram conferidos, quantos produtos
 * do Omie não têm cadastro aqui, nem que a varredura parou no teto de páginas —
 * e "lista vazia" se lê como "está tudo certo" quando pode ser "não achei
 * nenhum produto". Foi exatamente o que aconteceu: a chamada estava quebrada
 * desde sempre e o sintoma teria sido uma tabela vazia.
 */
type Conferencia = {
  linhas: LinhaConferencia[];
  conferidos: number;
  sem_cadastro_aqui: number;
  divergentes: number;
  truncado: boolean;
  message: string;
};

/** O custo médio do Omie para os produtos que aqui não têm custo nenhum. */
type CustosIniciais = {
  linhas: {
    id_produto: number;
    codigo: string;
    produto: string;
    custo_omie: number;
    ja_era_referencia: boolean;
  }[];
  produtos: number;
  conferidos: number;
  sem_cadastro_aqui: number;
  ja_tinham_custo: number;
  sem_custo_no_omie: number;
  /** Falso na prévia, verdadeiro depois de gravar. */
  aplicado: boolean;
  truncado: boolean;
  message: string;
};

type Vinculo = {
  codigo: string;
  descricao_externa: string | null;
  produto: string;
  codigo_produto: string;
  fator: number;
  confirmado_por: string | null;
};

export default function PaginaIntegracoes() {
  const aviso = useAviso();
  const { pode } = useSessao();
  const podeConfigurar = pode("admin.integracoes");

  const [cfg, setCfg] = useState<Config | null>(null);
  const [form, setForm] = useState({
    app_key: "", app_secret: "", modo: "simulado", ativa: false,
    tag_fornecedor: "Fornecedor",
    agenda_frequencia: "MANUAL", agenda_hora: "3", agenda_janela_dias: "",
  });
  const [conferencia, setConferencia] = useState<Conferencia | null>(null);
  // 🔑 **O custo inicial dos produtos.** Medido na base: 2.323 produtos ativos
  // que controlam estoque sem custo nenhum — nunca entrou nota deles aqui e não
  // há preço de fornecedor. Sem custo não há ficha, nem CMV teórico, nem
  // margem: o prato entra na conta valendo zero e o food cost sai bom demais.
  const [custos, setCustos] = useState<CustosIniciais | null>(null);
  const [vinculos, setVinculos] = useState<Vinculo[]>([]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const c = await api.get<Config>("/omie/config");
      setCfg(c);
      setForm({ app_key: "", app_secret: "", modo: c.modo, ativa: c.ativa,
                tag_fornecedor: c.tag_fornecedor ?? "",
                agenda_frequencia: c.agenda_frequencia ?? "MANUAL",
                agenda_hora: String(c.agenda_hora ?? 3),
                agenda_janela_dias: c.agenda_janela_dias ? String(c.agenda_janela_dias) : "" });
      setVinculos(await api.get<Vinculo[]>("/notas/vinculos"));
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function salvar(e: FormEvent) {
    e.preventDefault();
    setOcupado(true);
    setErro("");
    try {
      await api.put("/omie/config", {
        app_key: form.app_key || null,
        app_secret: form.app_secret || null,
        tag_fornecedor: form.tag_fornecedor || null,
        modo: form.modo,
        ativa: form.ativa,
        agenda_frequencia: form.agenda_frequencia,
        agenda_hora: Number(form.agenda_hora || 3),
        // Vazio = janela automática. `Number("")` é 0, que o servidor recusa —
        // e a recusa falaria de um campo que a pessoa deixou em branco de
        // propósito.
        agenda_janela_dias: form.agenda_janela_dias
          ? Number(form.agenda_janela_dias)
          : null,
      });
      aviso.sucesso("Integração salva. A chave fica cifrada e não volta pela tela.");
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  async function testar() {
    setOcupado(true);
    setErro("");
    try {
      const r = await api.post<{ ok: boolean; modo: string; detalhe: string }>("/omie/testar");
      if (r.ok) aviso.sucesso(`Conexão ${r.modo}: ${r.detalhe}`);
      else aviso.erro(`Não respondeu (${r.modo}): ${r.detalhe}`);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha no teste");
    } finally {
      setOcupado(false);
    }
  }

  async function acao(caminho: string, mensagem: (r: Record<string, number>) => string) {
    setOcupado(true);
    setErro("");
    try {
      const r = await api.post<Record<string, number>>(caminho);
      aviso.sucesso(mensagem(r));
      await carregar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível concluir");
    } finally {
      setOcupado(false);
    }
  }

  async function verCustos() {
    setOcupado(true);
    setErro("");
    try {
      // ⚠️ **A prévia SEMPRE antes.** Com 2.323 produtos, descobrir o efeito
      // depois é tarde: a mesma varredura, sem gravar nada.
      setCustos(await api.get<CustosIniciais>("/omie/custos-iniciais/previa"));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha ao consultar os custos");
    } finally {
      setOcupado(false);
    }
  }

  async function aplicarCustos() {
    setOcupado(true);
    try {
      const r = await api.post<CustosIniciais>("/omie/custos-iniciais");
      setCustos(r);
      aviso.sucesso(r.message);
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível aplicar");
    } finally {
      setOcupado(false);
    }
  }

  async function conferir() {
    setOcupado(true);
    setErro("");
    try {
      setConferencia(await api.get<Conferencia>("/omie/conferencia"));
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Falha na conferência");
    } finally {
      setOcupado(false);
    }
  }

  if (!cfg) return <Carregando />;

  return (
    <div className="flex flex-col gap-6">
      <header>
        <p className="rotulo">Administração</p>
        <h1 className="mt-1 text-[26px] font-bold tracking-tight sm:text-[30px]">Integrações</h1>
        <p className="mt-1 max-w-[66ch] text-suave">
          O que o Botané troca com o mundo lá fora: as notas do Omie e o envio de e-mail. Nada
          aqui é pré-requisito — o sistema opera inteiro sem nenhum dos dois.
        </p>
      </header>

      {erro && <Aviso tipo="erro">{erro}</Aviso>}

      {cfg.modo === "simulado" && (
        <Aviso tipo="info">
          <b>Modo simulado.</b> As notas e produtos vêm de respostas de demonstração gravadas
          aqui, não da conta do cliente. Tudo o que você vê funcionando — de-para, rateio,
          conversão, lançamento — é o mesmo código que vai rodar com a credencial real.
        </Aviso>
      )}

      <Cartao
        titulo="Credenciais do Omie"
        descricao="app_key e app_secret de um app de integração da conta do cliente."
        acao={
          <span className="flex items-center gap-2">
            <Etiqueta cor={cfg.modo === "real" ? "erva" : "alerta"}>{cfg.modo}</Etiqueta>
            {cfg.ativa && <Etiqueta cor="erva">ativa</Etiqueta>}
          </span>
        }
      >
        <form onSubmit={salvar} className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo
              rotulo="app_key"
              dica={cfg.app_key ? `guardada: ${cfg.app_key}` : "ainda não configurada"}
            >
              <input
                className="campo mono"
                disabled={!podeConfigurar}
                placeholder={cfg.app_key ? "deixe em branco para manter" : ""}
                value={form.app_key}
                onChange={(e) => setForm({ ...form, app_key: e.target.value })}
              />
            </Campo>
            <Campo
              rotulo="app_secret"
              dica={cfg.app_secret ? `guardado: ${cfg.app_secret}` : "ainda não configurado"}
            >
              <input
                className="campo mono"
                type="password"
                disabled={!podeConfigurar}
                placeholder={cfg.app_secret ? "deixe em branco para manter" : ""}
                value={form.app_secret}
                onChange={(e) => setForm({ ...form, app_secret: e.target.value })}
              />
            </Campo>
            {/* ⚠️ No Omie, cliente e fornecedor moram na MESMA lista, separados
                por etiqueta. Sem esta, importar o cadastro trouxe 888 clientes
                de uma conta real para dentro dos fornecedores. */}
            <Campo
              rotulo="Etiqueta de fornecedor no Omie"
              dica="lá, cliente e fornecedor estão na mesma lista — em branco traz todo mundo"
            >
              <input
                className="campo"
                disabled={!podeConfigurar}
                placeholder="Fornecedor"
                value={form.tag_fornecedor}
                onChange={(e) => setForm({ ...form, tag_fornecedor: e.target.value })}
              />
            </Campo>
            <Campo rotulo="Modo" dica="simulado usa dados de demonstração">
              <select
                className="campo"
                disabled={!podeConfigurar}
                value={form.modo}
                onChange={(e) => setForm({ ...form, modo: e.target.value })}
              >
                <option value="simulado">simulado</option>
                <option value="real">real</option>
              </select>
            </Campo>
            <label className="flex items-end gap-2 pb-2">
              <input
                type="checkbox"
                className="mb-2 h-4 w-4 accent-erva"
                disabled={!podeConfigurar}
                checked={form.ativa}
                onChange={(e) => setForm({ ...form, ativa: e.target.checked })}
              />
              <span className="pb-1.5 text-[14px]">integração ativa</span>
            </label>
          </div>

          <p className="text-[13px] text-suave">
            A chave é guardada cifrada e nunca volta pela API — a tela mostra só os últimos
            dígitos. Na fase 1 o Botané <b>só lê</b> do Omie: nada é escrito lá.
          </p>

          {/* ⚠️ **A busca automática nasce desligada.** Cada busca consome cota
              da conta, e o Omie bloqueia quem consome demais — o bloqueio pega a
              integração inteira. Ligar é decisão de quem paga a conta. */}
          {/* ⚠️ O id existe para o teste de tela: a página tem DOIS blocos de
              agenda (este e o do PDV), e "o primeiro select com HORARIA"
              deixaria de identificar qual é qual no dia em que a ordem mudasse. */}
          <section id="agenda-omie" className="rounded border border-linha bg-fundo p-4">
            <p className="rotulo">Buscar notas sozinho</p>
            <p className="mt-1 max-w-[70ch] text-[13px] leading-snug text-suave">
              Nota que chega na sexta e ninguém busca até segunda é nota que não entrou no
              estoque — e o CMV do fim de semana sai com compra a menos. Com o agendamento, o
              sistema procura sozinho.
            </p>

            <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Campo rotulo="Com que frequência">
                <select
                  className="campo"
                  disabled={!podeConfigurar}
                  value={form.agenda_frequencia}
                  onChange={(e) => setForm({ ...form, agenda_frequencia: e.target.value })}
                >
                  <option value="MANUAL">manual — só quando eu clicar</option>
                  <option value="HORARIA">a cada hora</option>
                  <option value="DIARIA">uma vez por dia</option>
                </select>
              </Campo>

              {/* Cada frequência pede uma pergunta diferente, e só uma. */}
              {form.agenda_frequencia === "DIARIA" && (
                <Campo rotulo="A que hora" dica="0 a 23 — de madrugada o Omie está vazio">
                  <input
                    className="campo mono"
                    type="number"
                    min={0}
                    max={23}
                    disabled={!podeConfigurar}
                    value={form.agenda_hora}
                    onChange={(e) => setForm({ ...form, agenda_hora: e.target.value })}
                  />
                </Campo>
              )}

              {form.agenda_frequencia !== "MANUAL" && (
                <Campo
                  rotulo="Varrer quantos dias para trás"
                  dica="em branco = desde a última busca"
                >
                  <input
                    className="campo mono"
                    type="number"
                    min={1}
                    max={365}
                    placeholder="automático"
                    disabled={!podeConfigurar}
                    value={form.agenda_janela_dias}
                    onChange={(e) => setForm({ ...form, agenda_janela_dias: e.target.value })}
                  />
                </Campo>
              )}
            </div>

            {form.agenda_frequencia === "HORARIA" && (
              <p className="mt-3 text-[13px] leading-snug text-alerta">
                A cada hora são 24 buscas por dia. O Omie limita o uso e{" "}
                <b>bloqueia a integração inteira</b> quando alguém passa do ponto — se a casa
                não recebe nota de hora em hora, uma vez por dia entrega o mesmo resultado por
                um vinte e quatro avos da cota.
              </p>
            )}

            {/* ⚠️ Duas datas diferentes: quando o agendador RODOU e quando
                alguma nota chegou. Sem as duas, "não roda" e "roda e não acha
                nada" ficam indistinguíveis — e a segunda é o normal. */}
            {cfg?.agenda_rodou_em && (
              <p className="mt-3 text-[13px] text-suave">
                Última tentativa automática em{" "}
                {new Date(cfg.agenda_rodou_em).toLocaleString("pt-BR")}
                {cfg.ultima_sincronizacao && (
                  <>
                    {" · "}última nota nova em{" "}
                    {new Date(cfg.ultima_sincronizacao).toLocaleString("pt-BR")}
                  </>
                )}
              </p>
            )}
            {cfg?.agenda_ultimo_erro && (
              <div className="mt-3">
                <Aviso tipo="erro">
                  A última busca automática falhou: {cfg.agenda_ultimo_erro}. O agendador{" "}
                  <b>não insiste</b> — a próxima tentativa é no horário seguinte, porque repetir
                  em cima de um bloqueio do Omie só o prolonga.
                </Aviso>
              </div>
            )}
          </section>

          <div className="flex flex-wrap gap-2">
            {podeConfigurar && (
              <button className="btn btn-primario" type="submit" disabled={ocupado}>
                Salvar
              </button>
            )}
            <button className="btn btn-secundario" type="button" onClick={testar} disabled={ocupado}>
              Testar conexão
            </button>
          </div>
        </form>
      </Cartao>

      {pode("integracao.omie") && <NotasOmie />}

      {/* O PDV Legal fica ao lado do Omie porque é a outra ponta da mesma
          conta: um traz o que entrou (nota), o outro o que saiu (venda). */}
      {(pode("integracao.pdv") || pode("admin.integracoes")) && <PdvLegal />}

      {pode("integracao.omie") && (
        <Cartao
          titulo="Trazer outros dados do Omie"
          descricao={
            cfg.ultima_sincronizacao
              ? `última sincronização em ${new Date(cfg.ultima_sincronizacao).toLocaleString("pt-BR")}`
              : "nenhuma sincronização ainda"
          }
        >
          <div className="flex flex-wrap gap-2">
            <button
              className="btn btn-secundario"
              disabled={ocupado}
              onClick={() =>
                acao(
                  "/omie/importar-catalogo",
                  (r) => `${r.criados} produto(s) criado(s) em rascunho`,
                )
              }
            >
              Importar catálogo de produtos
            </button>
            <button
              className="btn btn-secundario"
              disabled={ocupado}
              onClick={() =>
                acao(
                  "/omie/importar-fornecedores",
                  (r) =>
                    `${r.criados} fornecedor(es) criado(s), ${r.completados} completado(s)`,
                )
              }
            >
              Importar fornecedores
            </button>
            <button
              className="btn btn-secundario"
              disabled={ocupado}
              onClick={() =>
                acao(
                  "/omie/importar-fornecedores?apenas_completar=true",
                  (r) => `${r.completados} fornecedor(es) completado(s)`,
                )
              }
              title="Não cria ninguém: só preenche o que está em branco nos que já existem"
            >
              Só completar os que já existem
            </button>
            <button className="btn btn-secundario" onClick={conferir} disabled={ocupado}>
              Conferir estoque com o Omie
            </button>
            <button
              className="btn btn-secundario"
              onClick={verCustos}
              disabled={ocupado}
              title="Traz o custo médio do Omie para os produtos que aqui não têm custo nenhum"
            >
              Trazer o custo inicial
            </button>
          </div>
          <p className="mt-3 text-[13px] text-suave">
            O catálogo entra como <b>rascunho</b>: nasce com nome, NCM e EAN, e só entra no
            estoque depois que alguém definir a unidade e o fator de conversão.
          </p>
        </Cartao>
      )}

      {/* 🔑 **O custo inicial.** Sem custo não há ficha, nem CMV teórico, nem
          margem — o prato entra na conta valendo zero e o food cost sai bom
          demais, sem nada denunciando. O Omie já sabe o número.
          ⚠️ **É REFERÊNCIA, não movimento**: nada entra no razão e nenhum saldo
          muda. E a tela precisa DIZER isso antes do botão, senão quem clica
          espera ver o estoque encher. */}
      {custos && (
        <Cartao
          titulo="Custo inicial vindo do Omie"
          descricao="Para os produtos que aqui não têm custo nenhum — nem médio do razão, nem preço de fornecedor."
        >
          <p className="mb-3 text-[13.5px]">{custos.message}</p>
          <Aviso tipo="info">
            Isto grava um <b>custo de referência</b>: nada entra no razão e nenhum saldo muda. O
            CMV real continua saindo do que a casa comprou e contou — o que isto destrava é a
            ficha, o CMV teórico e a margem de quem hoje entra na conta valendo zero.
            {" "}O custo médio do estoque e o preço do fornecedor continuam ganhando dele.
          </Aviso>
          {custos.truncado && (
            <div className="mt-3">
              <Aviso tipo="erro">
                A varredura parou no teto de páginas — há mais produtos no Omie.
              </Aviso>
            </div>
          )}
          {!custos.linhas.length ? (
            <p className="mt-3 text-[13.5px] text-suave">
              {custos.conferidos
                ? "Nenhum produto sem custo entre os que existem dos dois lados — não há o que trazer."
                : "Nenhum produto conferido: o catálogo do Omie ainda não foi importado."}
            </p>
          ) : (
            <>
              <div className="mt-3 overflow-x-auto">
                {/* O id existe para a checagem apontar para ESTA tabela: a tela
                    de Integrações tem outras, e "a primeira que casa" mede a
                    errada. */}
                <table className="tabela" id="custos-iniciais">
                  <thead>
                    <tr>
                      <th>Código</th>
                      <th>Produto</th>
                      <th className="num">Custo no Omie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {custos.linhas.slice(0, 200).map((c) => (
                      <tr key={c.id_produto}>
                        <td className="mono">{c.codigo}</td>
                        <td>
                          {c.produto}
                          {/* Já tinha referência de uma rodada anterior: o
                              número novo substitui. Referência sobrescreve
                              referência, nunca custo de verdade. */}
                          {c.ja_era_referencia && (
                            <span className="ml-2">
                              <Etiqueta>já tinha referência</Etiqueta>
                            </span>
                          )}
                        </td>
                        <td className="num">{reais(c.custo_omie)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {custos.linhas.length > 200 && (
                <p className="mt-2 text-[12.5px] text-suave">
                  Mostrando 200 de {custos.produtos} — o botão aplica em todos.
                </p>
              )}
              {!custos.aplicado && (
                <div className="mt-4">
                  <button className="btn btn-primario" onClick={aplicarCustos} disabled={ocupado}>
                    {ocupado ? "Aplicando…" : `Aplicar em ${custos.produtos} produto(s)`}
                  </button>
                </div>
              )}
            </>
          )}
        </Cartao>
      )}

      {conferencia && (
        <Cartao
          titulo="Estoque daqui × posição no Omie"
          descricao="Divergência quer dizer que alguma entrada não foi conciliada de um dos lados."
        >
          {/* ⚠️ O resumo vem ANTES da tabela, e diz o que a tabela não diz:
              quantos foram conferidos e quantos produtos do Omie não têm
              cadastro aqui. Sem ele, uma lista curta se lê como "quase tudo
              certo" quando pode ser "quase nada foi comparado". */}
          <p className="mb-3 text-[13.5px]">{conferencia.message}</p>
          {conferencia.truncado && (
            <div className="mb-3">
              <Aviso tipo="erro">
                A varredura parou no teto de páginas — <b>há mais produtos no Omie</b> que não
                entraram nesta comparação.
              </Aviso>
            </div>
          )}
          {!conferencia.linhas.length ? (
            <Vazio>
              {conferencia.conferidos
                ? "Nenhuma divergência: saldo e custo médio batem com o Omie."
                : "Nenhum produto com código do Omie para comparar."}
            </Vazio>
          ) : (
            <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Produto</th>
                    <th className="num">Saldo aqui</th>
                    <th className="num">Saldo Omie</th>
                    <th className="num">Dif. saldo</th>
                    <th className="num">Custo médio</th>
                    <th className="num">CMC Omie</th>
                    <th className="num">Dif. custo</th>
                  </tr>
                </thead>
                <tbody>
                  {conferencia.linhas.slice(0, 200).map((c) => (
                    <tr key={c.codigo_omie}>
                      <td>
                        <Link href={`/produtos/${c.id_produto}`} className="link-registro">
                          {c.produto}
                        </Link>
                        <span className="block text-[12px] text-suave">
                          <span className="mono">{c.codigo}</span>
                          {c.um_estoque ? ` · ${c.um_estoque}` : ""}
                        </span>
                      </td>
                      <td className="num tabular-nums">{Number(c.saldo_botane)}</td>
                      <td className="num tabular-nums text-suave">{Number(c.saldo_omie)}</td>
                      <td
                        className={`num tabular-nums ${
                          Math.abs(Number(c.diferenca_saldo)) > 0.001
                            ? "font-semibold text-erro"
                            : ""
                        }`}
                      >
                        {Number(c.diferenca_saldo)}
                      </td>
                      <td className="num tabular-nums">{reais(Number(c.custo_medio_botane))}</td>
                      <td className="num tabular-nums text-suave">{reais(Number(c.cmc_omie))}</td>
                      <td
                        className={`num tabular-nums ${
                          Math.abs(Number(c.diferenca_custo)) > 0.01
                            ? "font-semibold text-erro"
                            : ""
                        }`}
                      >
                        {reais(Number(c.diferenca_custo))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {conferencia.linhas.length > 200 && (
                <p className="mt-2 text-[13px] text-suave">
                  Mostrando as 200 maiores diferenças de {conferencia.linhas.length}.
                </p>
              )}
            </div>
          )}
        </Cartao>
      )}

      <Cartao
        titulo="De-para aprendido"
        descricao="Cada vínculo confirmado uma vez faz as próximas notas entrarem sozinhas."
      >
        {!vinculos.length ? (
          <Vazio>Nenhum vínculo ainda.</Vazio>
        ) : (
          <div className="overflow-x-auto">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Código no Omie</th>
                  <th>Descrição de lá</th>
                  <th>Produto daqui</th>
                  <th className="num">Fator</th>
                  <th>Quem confirmou</th>
                </tr>
              </thead>
              <tbody>
                {vinculos.map((v) => (
                  <tr key={v.codigo}>
                    <td className="mono">{v.codigo}</td>
                    <td className="text-suave">{v.descricao_externa ?? "—"}</td>
                    <td className="font-semibold">{v.produto}</td>
                    <td className="num">{Number(v.fator)}</td>
                    <td className="text-suave">{v.confirmado_por ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Cartao>

      <EmailSmtp />

      <Cartao titulo="Últimas chamadas" descricao="O que foi pedido ao Omie, e o que voltou.">
        {!cfg.historico.length ? (
          <Vazio>Nada registrado ainda.</Vazio>
        ) : (
          <ul className="flex flex-col gap-px bg-linha">
            {cfg.historico.map((h, i) => (
              <li key={i} className="flex flex-wrap items-center gap-3 bg-superficie py-2.5">
                <Etiqueta cor={h.status === "OK" ? "erva" : h.status === "ERRO" ? "alerta" : "neutro"}>
                  {h.status.toLowerCase()}
                </Etiqueta>
                <span className="mono text-[13px]">{h.chamada}</span>
                <span className="text-[13px] text-suave">
                  {h.registros} registro(s) · {h.modo}
                </span>
                <span className="mono ml-auto text-[12px] text-suave">
                  {new Date(h.iniciado_em).toLocaleString("pt-BR")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Cartao>
    </div>
  );
}
