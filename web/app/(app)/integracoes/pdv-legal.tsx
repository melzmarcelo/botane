"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useRouter } from "next/navigation";
import { useSessao } from "@/lib/sessao";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";

/**
 * PDV Legal — a credencial, o teste de conexão e a busca das vendas.
 *
 * ⚠️ **A senha e o token do grupo nunca voltam do servidor**, nem para
 * preencher o campo: os inputs abrem VAZIOS e o que está guardado aparece na
 * dica, mascarado. Um campo preenchido com bolinhas seria enviado de volta como
 * bolinhas no primeiro salvar — e a credencial de verdade se perderia.
 */

type Config = {
  configurada: boolean;
  modo: string;
  ativa: boolean;
  username: string | null;
  password: string | null;
  client_id: string | null;
  client_secret: string | null;
  ultima_sincronizacao: string | null;
  ultimo_status: string | null;
  ultima_mensagem: string | null;
  importador_disponivel: boolean;
  filiais: string | null;
  agenda_frequencia: string;
  agenda_hora: number;
  agenda_janela_dias: number | null;
  /** Quando o agendador RODOU — não é o mesmo que ter trazido venda. */
  agenda_rodou_em: string | null;
  agenda_ultimo_erro: string | null;
  /** A agenda grava venda, e venda tem dono. Sem assinatura ela recusa rodar. */
  agenda_assinada: boolean;
};

const VAZIO = {
  username: "",
  password: "",
  client_id: "",
  client_secret: "",
  modo: "simulado",
  ativa: false,
  filiais: "",
  agenda_frequencia: "MANUAL",
  agenda_hora: "4",
  agenda_janela_dias: "",
};

export default function PdvLegal() {
  const aviso = useAviso();
  const router = useRouter();
  const { pode } = useSessao();
  const podeConfigurar = pode("admin.integracoes");

  const [cfg, setCfg] = useState<Config | null>(null);
  const [form, setForm] = useState(VAZIO);
  const [erro, setErro] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const c = await api.get<Config>("/pdv/config");
      setCfg(c);
      // ⚠️ Os campos voltam VAZIOS, não mascarados: um campo com bolinhas
      // dentro seria enviado de volta como bolinhas no primeiro salvar. O que
      // já está guardado aparece na etiqueta ao lado, não no input.
      setForm({
        ...VAZIO,
        modo: c.modo,
        ativa: c.ativa,
        filiais: c.filiais ?? "",
        agenda_frequencia: c.agenda_frequencia ?? "MANUAL",
        agenda_hora: String(c.agenda_hora ?? 4),
        agenda_janela_dias: c.agenda_janela_dias ? String(c.agenda_janela_dias) : "",
      });
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
    try {
      await api.put("/pdv/config", {
        username: form.username || null,
        password: form.password || null,
        client_id: form.client_id || null,
        client_secret: form.client_secret || null,
        modo: form.modo,
        ativa: form.ativa,
        filiais: form.filiais,
        agenda_frequencia: form.agenda_frequencia,
        agenda_hora: Number(form.agenda_hora || 4),
        // Vazio = janela automática. `Number("")` é 0, que o servidor recusa —
        // e a recusa falaria de um campo deixado em branco de propósito.
        agenda_janela_dias: form.agenda_janela_dias ? Number(form.agenda_janela_dias) : null,
      });
      aviso.sucesso("Credencial do PDV Legal salva, cifrada. Ela não volta pela tela.");
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  /**
   * Traz os cupons e os grava como venda.
   *
   * ⚠️ A busca é **dia a dia** no servidor: o `cupom/get` do PDV devolve no
   * máximo 100 registros num intervalo de até 10 dias, exceto quando a data
   * inicial é igual à final. Uma casa com 48 cupons por dia estoura os 100 em
   * três dias — e o corte seria mudo.
   */
  async function sincronizar() {
    setOcupado(true);
    try {
      const r = await api.post<{ message: string; sem_vinculo?: number }>(
        "/pdv/sincronizar",
      );
      aviso.sucesso(r.message, (r.sem_vinculo ?? 0) > 0
        ? { texto: "ver itens sem vínculo", ao: () => router.push("/vendas") }
        : undefined);
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível buscar as vendas");
    } finally {
      setOcupado(false);
    }
  }

  /**
   * Traz o cardápio e monta o de-para.
   *
   * ⚠️ O que a cascata **não** faz é casar código com código: o número do
   * cardápio e o código da casa são espaços de nome diferentes, e casá-los
   * ligou REDBULL a LIMÃO TAITY numa base real. Vinculam o de-para que já
   * existe e o nome idêntico; semelhança vira dica no rascunho, e só.
   */
  async function importarCardapio() {
    setOcupado(true);
    try {
      const r = await api.post<{
        message: string;
        criados: number;
        sem_custo: number;
      }>("/pdv/cardapio");
      aviso.sucesso(
        r.sem_custo > 0
          ? `${r.message}. ${r.sem_custo} item(ns) ainda sem custo — falta a ficha técnica.`
          : r.message,
        r.criados > 0
          ? { texto: "ver os rascunhos criados", ao: () => router.push("/produtos") }
          : undefined,
      );
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível importar o cardápio");
    } finally {
      setOcupado(false);
    }
  }

  async function testar() {
    setOcupado(true);
    try {
      const r = await api.post<{ ok: boolean; modo: string; detalhe: string }>("/pdv/testar");
      if (r.ok) aviso.sucesso(`Conexão ${r.modo}: ${r.detalhe}`);
      else aviso.erro(`Não autenticou (${r.modo}): ${r.detalhe}`);
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível testar");
    } finally {
      setOcupado(false);
    }
  }

  if (erro && !cfg) return <Aviso tipo="erro">{erro}</Aviso>;
  if (!cfg) return <Carregando />;

  const campos = [
    { campo: "username" as const, rotulo: "Usuário de integração", guardado: cfg.username },
    { campo: "password" as const, rotulo: "Senha", guardado: cfg.password, senha: true },
    {
      campo: "client_id" as const,
      rotulo: "client_id",
      dica: "o código do grupo econômico",
      guardado: cfg.client_id,
    },
    {
      campo: "client_secret" as const,
      rotulo: "client_secret",
      dica: "o token do grupo econômico",
      guardado: cfg.client_secret,
      senha: true,
    },
  ];

  return (
    <Cartao
      titulo="PDV Legal"
      descricao="As vendas que alimentam o CMV teórico."
      acao={
        cfg.configurada ? (
          <Etiqueta cor={cfg.ultimo_status === "ERRO" ? "alerta" : "erva"}>
            {cfg.modo}
          </Etiqueta>
        ) : undefined
      }
    >
      <div className="flex flex-col gap-5">
        <form className="flex flex-col gap-4" onSubmit={salvar}>
          <div className="grid gap-4 sm:grid-cols-2">
            {campos.map((c) => (
              <Campo
                key={c.campo}
                rotulo={c.rotulo}
                dica={
                  c.guardado
                    ? `guardado: ${c.guardado} — deixe em branco para manter`
                    : c.dica
                }
              >
                <input
                  className="campo mono"
                  type={c.senha ? "password" : "text"}
                  autoComplete="off"
                  disabled={!podeConfigurar}
                  placeholder={c.guardado ? "•••• (mantém o que está guardado)" : ""}
                  value={form[c.campo]}
                  onChange={(e) => setForm({ ...form, [c.campo]: e.target.value })}
                />
              </Campo>
            ))}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {/* ⚠️ Em branco o servidor descobre sozinho — uma casa com uma
                filial só não deveria digitar o código dela. Só é obrigatório
                quando há mais de uma: aí somar todas mudaria o CMV de cada. */}
            <Campo rotulo="Filiais" dica="em branco = descobre sozinho">
              <input
                className="campo mono"
                disabled={!podeConfigurar}
                placeholder="37622 ou 10,20,30"
                value={form.filiais}
                onChange={(e) => setForm({ ...form, filiais: e.target.value })}
              />
            </Campo>
            <Campo rotulo="Modo" dica="real exige os quatro campos preenchidos">
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

          {/* ⚠️ A busca automática existe pela mesma razão que a do Omie: venda
              de sábado que ninguém importa é receita que falta no CMV do fim de
              semana — e a variância sai boa demais, porque o teórico não conta
              o que foi vendido. */}
          <section id="agenda-pdv" className="rounded border border-linha bg-fundo p-4">
            <p className="rotulo">Buscar vendas sozinho</p>
            <p className="mt-1 max-w-[70ch] text-[13px] leading-snug text-suave">
              Sem agendamento, alguém precisa abrir esta tela e clicar em Buscar vendas todo
              dia. O que não for buscado não entra no CMV daquele período.
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
                <Campo
                  rotulo="A que hora"
                  dica="0 a 23 — depois do fechamento do caixa"
                >
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
                  dica="em branco = desde a última venda importada"
                >
                  <input
                    className="campo mono"
                    type="number"
                    min={1}
                    max={60}
                    placeholder="automático"
                    disabled={!podeConfigurar}
                    value={form.agenda_janela_dias}
                    onChange={(e) => setForm({ ...form, agenda_janela_dias: e.target.value })}
                  />
                </Campo>
              )}
            </div>

            {/* ⚠️ Cada DIA da janela é uma requisição ao PDV — é o único jeito
                sem teto de 100 cupons. O aviso diz a conta, porque "a cada hora"
                não parece caro até alguém multiplicar. */}
            {form.agenda_frequencia === "HORARIA" && (
              <p className="mt-3 text-[13px] leading-snug text-alerta">
                A cada hora são 24 buscas por dia, e cada busca faz{" "}
                <b>uma requisição por dia da janela</b>. Se a casa fecha o caixa uma vez, uma
                vez por dia traz exatamente o mesmo resultado.
              </p>
            )}

            {/* ⚠️ Duas datas diferentes: quando o agendador RODOU e quando
                alguma venda chegou. Sem as duas, "não roda" e "roda e não acha
                nada" ficam indistinguíveis — e a segunda é o normal de domingo. */}
            {cfg.agenda_rodou_em && (
              <p className="mt-3 text-[13px] text-suave">
                Última tentativa automática em{" "}
                {new Date(cfg.agenda_rodou_em).toLocaleString("pt-BR")}
                {cfg.ultima_sincronizacao && (
                  <>
                    {" · "}última venda nova em{" "}
                    {new Date(cfg.ultima_sincronizacao).toLocaleString("pt-BR")}
                  </>
                )}
              </p>
            )}
            {cfg.agenda_frequencia !== "MANUAL" && !cfg.agenda_assinada && (
              <div className="mt-3">
                <Aviso tipo="info">
                  A agenda não sabe quem a ligou, e venda tem dono — ela vai recusar rodar.
                  Salve o agendamento de novo para assiná-lo.
                </Aviso>
              </div>
            )}
            {cfg.agenda_ultimo_erro && (
              <div className="mt-3">
                <Aviso tipo="erro">
                  A última busca automática falhou: {cfg.agenda_ultimo_erro}. O agendador{" "}
                  <b>não insiste</b> — a próxima tentativa é no horário seguinte, porque
                  repetir uma credencial recusada só queima tentativa de login.
                </Aviso>
              </div>
            )}
          </section>

          <p className="text-[13px] leading-snug text-suave">
            A senha e o token do grupo são guardados <b>cifrados</b> e nunca voltam pela API —
            a tela mostra só os últimos dígitos. O Bearer token do PDV vale cerca de seis horas
            e fica só na memória do servidor: reiniciar pede um novo, o que é barato.
          </p>

          <div className="flex flex-wrap gap-2">
            {podeConfigurar && (
              <button className="btn btn-primario" type="submit" disabled={ocupado}>
                Salvar
              </button>
            )}
            <button
              className="btn btn-secundario"
              type="button"
              onClick={testar}
              disabled={ocupado}
            >
              Testar conexão
            </button>
            {cfg.configurada && (
              <>
                <button
                  className="btn btn-secundario"
                  type="button"
                  onClick={sincronizar}
                  disabled={ocupado}
                  title="Traz os cupons do PDV e grava como venda"
                >
                  Buscar vendas
                </button>
                {/* ⚠️ Sem o cardápio, a venda entra e o CMV teórico é ZERO: a
                    receita aparece, o CMV real aparece, e a variância não tem
                    com o que comparar. O botão fica ao lado do de buscar
                    porque é a outra metade do mesmo trabalho. */}
                <button
                  className="btn btn-secundario"
                  type="button"
                  onClick={importarCardapio}
                  disabled={ocupado}
                  title="Traz os itens do cardápio e liga aos pratos daqui"
                >
                  Importar cardápio
                </button>
              </>
            )}
          </div>
        </form>

        {/* ⚠️ O resultado do último teste fica GRAVADO. Quem configurou fecha a
            tela, e a próxima pessoa precisa ver que a última tentativa não
            passou — sem isso, "configurada" pareceria "funcionando". */}
        {cfg.ultimo_status && (
          <p className="text-[13px] text-suave">
            Último teste: <b>{cfg.ultimo_status === "OK" ? "passou" : "falhou"}</b>
            {cfg.ultima_mensagem ? ` — ${cfg.ultima_mensagem}` : ""}
          </p>
        )}
      </div>
    </Cartao>
  );
}
