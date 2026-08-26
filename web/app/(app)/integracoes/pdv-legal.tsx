"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useAviso } from "@/components/aviso-flutuante";
import { useSessao } from "@/lib/sessao";
import { Aviso, Campo, Carregando, Cartao, Etiqueta } from "@/components/ui";

/**
 * PDV Legal — a credencial e o teste de conexão.
 *
 * ⚠️ **Só isto, e a tela diz por quê.** O `POST /token` da Tablet Cloud é a
 * única parte da API documentada publicamente; o catálogo de endpoints — vendas
 * do dia, itens, cancelamentos, cardápio — fica no portal de parceiros, fechado.
 * Sem ele, importador é endereço adivinhado.
 *
 * Uma tela com um botão de testar e nada mais parece incompleta; **dizer o que
 * falta e por quê** é a diferença entre "pela metade" e "até aqui dá".
 */

type Config = {
  configurada: boolean;
  modo: string;
  ativa: boolean;
  username: string | null;
  password: string | null;
  client_id: string | null;
  client_secret: string | null;
  ultimo_status: string | null;
  ultima_mensagem: string | null;
  importador_disponivel: boolean;
  pendencia: string;
};

const VAZIO = {
  username: "",
  password: "",
  client_id: "",
  client_secret: "",
  modo: "simulado",
  ativa: false,
};

export default function PdvLegal() {
  const aviso = useAviso();
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
      setForm({ ...VAZIO, modo: c.modo, ativa: c.ativa });
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
      });
      aviso.sucesso("Credencial do PDV Legal salva, cifrada. Ela não volta pela tela.");
      await carregar();
    } catch (err) {
      aviso.erro(err instanceof Error ? err.message : "Não foi possível salvar");
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
        {/* ⚠️ O aviso vem PRIMEIRO. Uma tela com um botão de testar e mais nada
            parece um pedaço faltando; dizer o que falta, por quê e o que roda
            no lugar é a diferença entre "incompleto" e "até aqui dá". */}
        {!cfg.importador_disponivel && (
          <Aviso tipo="info">
            Por enquanto esta tela só <b>guarda a credencial e testa a conexão</b>. {cfg.pendencia}{" "}
            A autenticação é a única parte da API que a Tablet Cloud publica; escrever o
            importador sem o catálogo seria adivinhar endereço.
          </Aviso>
        )}

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
