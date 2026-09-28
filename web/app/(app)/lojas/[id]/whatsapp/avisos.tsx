"use client";

import { useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Campo, Cartao, Etiqueta } from "@/components/ui";
import { testarWhatsapp, type GravarWhatsapp, type WhatsappDaLoja } from "@/lib/whatsapp";

/**
 * Os avisos: cada um liga/desliga, com o NOME do modelo na Meta, idioma e antecedência.
 *
 * 🔑 O texto de cada aviso vem pronto para a loja cadastrar o modelo na Meta: {{n}} são as
 * variáveis, na ordem mostrada. Mensagem que a casa inicia é SEMPRE um modelo aprovado.
 */
const NOME_VARIAVEL: Record<string, string> = {
  nome: "primeiro nome", casa: "nome da casa", data: "data", hora: "hora", pessoas: "pessoas",
  premio: "prêmio", vence: "vencimento", codigo: "código do prêmio",
};

export default function AvisosDoWhatsapp({
  dados,
  form,
  aoMudar,
  podeEditar,
  idLoja,
  aoTestar,
}: {
  dados: WhatsappDaLoja;
  form: GravarWhatsapp;
  aoMudar: (f: GravarWhatsapp) => void;
  podeEditar: boolean;
  idLoja: number;
  aoTestar: () => void;
}) {
  const aviso = useAviso();
  const [fone, setFone] = useState("");
  const [testando, setTestando] = useState<string | null>(null);

  const mudar = (evento: string, campo: "ativo" | "modelo" | "idioma" | "antecedencia", v: unknown) =>
    aoMudar({
      ...form,
      avisos: form.avisos.map((a) => (a.evento === evento ? { ...a, [campo]: v } : a)),
    });

  async function testar(evento: string) {
    if (!fone.trim()) {
      aviso.erro("Informe um telefone com DDD para o teste.");
      return;
    }
    setTestando(evento);
    try {
      const r = await testarWhatsapp(idLoja, fone, evento);
      aviso.sucesso(r.message);
      aoTestar();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível testar");
    } finally {
      setTestando(null);
    }
  }

  return (
    <Cartao
      titulo="Avisos"
      descricao="O que a loja envia, e quando. Salve depois de mudar."
      acao={
        <Campo rotulo="Telefone para teste">
          <input className="campo mono w-[170px]" inputMode="tel" placeholder="(47) 99999-9999"
                 value={fone} onChange={(e) => setFone(e.target.value)} />
        </Campo>
      }
    >
      <ul className="flex flex-col gap-3">
        {dados.avisos.map((a) => {
          const f = form.avisos.find((x) => x.evento === a.evento)!;
          return (
            <li key={a.evento} className="rounded-[10px] border border-[var(--color-linha)] p-3">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <label className="flex items-start gap-3">
                  <input type="checkbox" className="mt-1" disabled={!podeEditar} checked={f.ativo}
                         onChange={(e) => mudar(a.evento, "ativo", e.target.checked)} />
                  <span>
                    <b className="text-[14.5px]">{a.nome}</b>{" "}
                    <Etiqueta cor={a.categoria === "Marketing" ? "alerta" : "neutro"}>{a.categoria}</Etiqueta>
                    <span className="block text-[12.5px] text-suave">{a.quando}</span>
                  </span>
                </label>
                <button type="button" className="link-acao text-[13px]" disabled={testando !== null}
                        onClick={() => void testar(a.evento)}>
                  {testando === a.evento ? "enviando…" : "enviar teste"}
                </button>
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_110px_150px]">
                <Campo rotulo="Nome do modelo na Meta">
                  <input className="campo mono" disabled={!podeEditar} value={f.modelo}
                         onChange={(e) => mudar(a.evento, "modelo", e.target.value)} />
                </Campo>
                <Campo rotulo="Idioma">
                  <input className="campo mono" disabled={!podeEditar} value={f.idioma}
                         onChange={(e) => mudar(a.evento, "idioma", e.target.value)} />
                </Campo>
                {a.unidade ? (
                  <Campo rotulo={`Antecedência (${a.unidade})`}>
                    <input className="campo mono" type="number" min={0} max={720} disabled={!podeEditar}
                           value={f.antecedencia ?? ""}
                           onChange={(e) => mudar(a.evento, "antecedencia",
                             e.target.value === "" ? null : Number(e.target.value))} />
                  </Campo>
                ) : <span />}
              </div>
              <details className="mt-2 text-[13px]">
                <summary className="cursor-pointer text-suave">Texto do modelo para cadastrar na Meta</summary>
                <p className="mt-2 whitespace-pre-wrap rounded-[8px] bg-[var(--color-superficie2)] p-2.5">
                  {a.texto}
                </p>
                <p className="mt-1 text-suave">
                  Variáveis:{" "}
                  {a.variaveis.map((v, i) => `{{${i + 1}}} = ${NOME_VARIAVEL[v] ?? v}`).join(" · ")}
                  {a.botoes && <> · Botões de resposta rápida: <b>{a.botoes.join(" / ")}</b> (nesta ordem)</>}
                </p>
                <button type="button" className="link-acao mt-1"
                        onClick={() => void navigator.clipboard?.writeText(a.texto)}>
                  copiar texto
                </button>
              </details>
            </li>
          );
        })}
      </ul>
    </Cartao>
  );
}
