"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Aviso, Campo, Cartao } from "@/components/ui";

/**
 * Configuração do envio de e-mail.
 *
 * Enquanto ninguém preencher isto, a recuperação de senha continua funcionando:
 * o sistema grava a mensagem em arquivo e o administrador entrega o link na
 * mão pela tela de Usuários. O SMTP só automatiza o que já funciona.
 */

type Config = {
  configurada: boolean;
  modo: string;
  ativa: boolean;
  servidor: string | null;
  porta: number | null;
  seguranca: string;
  usuario: string | null;
  remetente_nome: string | null;
  remetente_email: string | null;
  senha: string | null;
  ultimo_status: string | null;
  ultima_mensagem: string | null;
  pasta_simulado: string;
};

export default function EmailSmtp() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const carregar = useCallback(async () => {
    try {
      const c = await api.get<Config>("/email/config");
      setCfg(c);
      setForm({
        servidor: c.servidor ?? "",
        porta: c.porta ? String(c.porta) : "",
        seguranca: c.seguranca ?? "starttls",
        usuario: c.usuario ?? "",
        senha: "",
        remetente_nome: c.remetente_nome ?? "",
        remetente_email: c.remetente_email ?? "",
        modo: c.modo,
      });
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Falha ao carregar");
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  async function salvar() {
    setOcupado(true);
    setErro("");
    setOk("");
    try {
      await api.put("/email/config", {
        servidor: form.servidor || null,
        porta: form.porta ? Number(form.porta) : null,
        seguranca: form.seguranca,
        usuario: form.usuario || null,
        // Campo em branco mantém a senha guardada — a tela só mostra mascarada.
        senha: form.senha || null,
        remetente_nome: form.remetente_nome || null,
        remetente_email: form.remetente_email || null,
        modo: form.modo,
        ativa: form.modo === "real",
      });
      setOk("Configuração salva.");
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível salvar");
    } finally {
      setOcupado(false);
    }
  }

  async function testar() {
    setOcupado(true);
    setErro("");
    setOk("");
    try {
      const eu = await api.get<{ email: string }>("/auth/me");
      const r = await api.post<{ detalhe: string }>("/email/testar", { para: eu.email });
      setOk(r.detalhe);
      await carregar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "O envio de teste falhou");
    } finally {
      setOcupado(false);
    }
  }

  if (!cfg) return null;

  return (
    <Cartao
      titulo="Envio de e-mail"
      descricao="Usado hoje pela recuperação de senha."
      acao={
        <div className="flex flex-wrap items-center gap-2">
          <button className="btn btn-secundario" onClick={testar} disabled={ocupado}>
            Enviar teste para mim
          </button>
          <button className="btn btn-primario" onClick={salvar} disabled={ocupado}>
            Salvar
          </button>
        </div>
      }
    >
      {erro && (
        <div className="mb-4">
          <Aviso tipo="erro">{erro}</Aviso>
        </div>
      )}
      {ok && (
        <div className="mb-4">
          <Aviso tipo="ok">{ok}</Aviso>
        </div>
      )}

      {cfg.modo !== "real" && (
        <div className="mb-4">
          <Aviso tipo="info">
            <b>Sem servidor de e-mail.</b> Nada é enviado de verdade: as mensagens são gravadas
            em <span className="mono text-[13px]">{cfg.pasta_simulado}</span>. A recuperação de
            senha continua funcionando — o administrador gera o link na tela de Usuários e
            entrega para a pessoa.
          </Aviso>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Campo rotulo="Servidor SMTP">
          <input
            className="campo"
            value={form.servidor}
            placeholder="smtp.seudominio.com.br"
            onChange={(e) => setForm({ ...form, servidor: e.target.value })}
          />
        </Campo>
        <Campo rotulo="Porta">
          <input
            className="campo mono"
            inputMode="numeric"
            value={form.porta}
            placeholder="587"
            onChange={(e) => setForm({ ...form, porta: e.target.value })}
          />
        </Campo>
        <Campo rotulo="Segurança">
          <select
            className="campo"
            value={form.seguranca}
            onChange={(e) => setForm({ ...form, seguranca: e.target.value })}
          >
            <option value="starttls">STARTTLS (587)</option>
            <option value="ssl">SSL (465)</option>
            <option value="nenhuma">Sem criptografia</option>
          </select>
        </Campo>
        <Campo rotulo="Situação">
          <select
            className="campo"
            value={form.modo}
            onChange={(e) => setForm({ ...form, modo: e.target.value })}
          >
            <option value="simulado">Gravar em arquivo</option>
            <option value="real">Enviar de verdade</option>
          </select>
        </Campo>
        <Campo rotulo="Usuário">
          <input
            className="campo"
            value={form.usuario}
            autoComplete="off"
            onChange={(e) => setForm({ ...form, usuario: e.target.value })}
          />
        </Campo>
        <Campo rotulo={`Senha ${cfg.senha ? `(guardada: ${cfg.senha})` : ""}`}>
          <input
            className="campo"
            type="password"
            autoComplete="new-password"
            placeholder={cfg.senha ? "deixe em branco para manter" : ""}
            value={form.senha}
            onChange={(e) => setForm({ ...form, senha: e.target.value })}
          />
        </Campo>
        <Campo rotulo="Remetente (nome)">
          <input
            className="campo"
            value={form.remetente_nome}
            placeholder="Botané Deli e Café"
            onChange={(e) => setForm({ ...form, remetente_nome: e.target.value })}
          />
        </Campo>
        <Campo rotulo="Remetente (e-mail)">
          <input
            className="campo"
            value={form.remetente_email}
            onChange={(e) => setForm({ ...form, remetente_email: e.target.value })}
          />
        </Campo>
      </div>

      {cfg.ultima_mensagem && (
        <p className="mt-4 text-[13.5px] text-suave">
          Último teste: <b>{cfg.ultimo_status}</b> — {cfg.ultima_mensagem}
        </p>
      )}
    </Cartao>
  );
}
