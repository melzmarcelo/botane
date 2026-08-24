"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { reais } from "@/lib/cadastros";
import { Aviso, Campo, Carregando, Cartao, Etiqueta, Vazio } from "@/components/ui";
import EmailSmtp from "./email-smtp";
import NotasOmie from "./notas-omie";

type Config = {
  configurada: boolean;
  modo: string;
  ativa: boolean;
  app_key: string | null;
  app_secret: string | null;
  tag_fornecedor: string | null;
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

type Conferencia = {
  produto: string;
  codigo_omie: string;
  saldo_botane: number;
  saldo_omie: number;
  custo_medio_botane: number;
  cmc_omie: number;
  diferenca: number;
  divergente: boolean;
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
  });
  const [conferencia, setConferencia] = useState<Conferencia[] | null>(null);
  const [vinculos, setVinculos] = useState<Vinculo[]>([]);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const c = await api.get<Config>("/omie/config");
      setCfg(c);
      setForm({ app_key: "", app_secret: "", modo: c.modo, ativa: c.ativa,
                tag_fornecedor: c.tag_fornecedor ?? "" });
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

  async function conferir() {
    setOcupado(true);
    setErro("");
    try {
      setConferencia(await api.get<Conferencia[]>("/omie/conferencia"));
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
          </div>
          <p className="mt-3 text-[13px] text-suave">
            O catálogo entra como <b>rascunho</b>: nasce com nome, NCM e EAN, e só entra no
            estoque depois que alguém definir a unidade e o fator de conversão.
          </p>
        </Cartao>
      )}

      {conferencia && (
        <Cartao
          titulo="Custo médio daqui × CMC do Omie"
          descricao="Divergência quer dizer que alguma entrada não foi conciliada de um dos lados."
        >
          {!conferencia.length ? (
            <Vazio>Nenhum produto com código do Omie para comparar.</Vazio>
          ) : (
            <div className="overflow-x-auto">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Produto</th>
                    <th className="num">Saldo aqui</th>
                    <th className="num">Saldo Omie</th>
                    <th className="num">Custo médio</th>
                    <th className="num">CMC Omie</th>
                    <th className="num">Diferença</th>
                  </tr>
                </thead>
                <tbody>
                  {conferencia.map((c) => (
                    <tr key={c.codigo_omie} className={c.divergente ? "" : "opacity-70"}>
                      <td className="font-semibold">{c.produto}</td>
                      <td className="num">{Number(c.saldo_botane)}</td>
                      <td className="num text-suave">{Number(c.saldo_omie)}</td>
                      <td className="num">{reais(Number(c.custo_medio_botane))}</td>
                      <td className="num text-suave">{reais(Number(c.cmc_omie))}</td>
                      <td className={`num ${c.divergente ? "font-semibold text-erro" : ""}`}>
                        {reais(Number(c.diferenca))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
