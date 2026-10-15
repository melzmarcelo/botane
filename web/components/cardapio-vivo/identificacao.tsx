"use client";

/**
 * A identificação OPCIONAL pelo telefone (fase 2, 115): liga o pedido ao cadastro e soma na
 * fidelidade, pelo método que a casa usa (QR da mesa marca na hora; código do caixa pede o
 * código que o atendente passa).
 *
 * 🔑 Quem não tem cadastro se cadastra ali mesmo (decisão do dono, 15/10/2026): nome e o
 * aceite do termo — e o que mais a loja exigir, que o servidor diz na recusa.
 * ⚠️ O telefone fica só nesta aba (`sessionStorage`) e NUNCA entra nos eventos de atenção.
 */

import { useState } from "react";
import { MesaService, type RespostaIdentificacao } from "@/lib/cardapio-vivo";
import type { Textos } from "./textos";

const CHAVE = "cardapio.telefone";

export function telefoneGuardado(): string | null {
  try {
    return sessionStorage.getItem(CHAVE);
  } catch {
    return null;
  }
}

type Props = { token: string; loja: number; t: Textos; aoIdentificar: (telefone: string, nome: string) => void };

export default function Identificacao({ token, loja, t, aoIdentificar }: Props) {
  const [fone, setFone] = useState("");
  const [nome, setNome] = useState("");
  const [extra, setExtra] = useState({ genero: "", cidade: "", nascimento: "" });
  const [termo, setTermo] = useState(false);
  const [pedirCadastro, setPedirCadastro] = useState<string[] | null>(null);
  const [textoTermo, setTextoTermo] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<RespostaIdentificacao | null>(null);
  const [codigo, setCodigo] = useState("");
  const [ocupado, setOcupado] = useState(false);

  async function enviar() {
    setOcupado(true);
    setErro(null);
    const corpo: Record<string, unknown> = { telefone: fone, aceite_termo: termo };
    if (nome.trim()) corpo.nome = nome.trim();
    if (extra.genero) corpo.genero = extra.genero;
    if (extra.cidade.trim()) corpo.cidade = extra.cidade.trim();
    if (extra.nascimento) corpo.nascimento = extra.nascimento;
    const r = await MesaService.identificar(token, corpo);
    setOcupado(false);
    if (!r.ok) {
      // 🔑 O servidor diz o que falta para o cadastro novo; a tela só mostra esses campos.
      if (r.status === 422) {
        const falta = ["nome"];
        if (/gênero/.test(r.erro)) falta.push("genero");
        if (/cidade/.test(r.erro)) falta.push("cidade");
        if (/nascimento/.test(r.erro)) falta.push("nascimento");
        setPedirCadastro(falta);
      }
      setErro(r.erro);
      return;
    }
    try { sessionStorage.setItem(CHAVE, r.dados.telefone); } catch { /* vale só agora */ }
    aoIdentificar(r.dados.telefone, r.dados.nome);
    // ⚠️ Cadastro antigo, termo novo: identifica (o pedido já sai no nome), mas para SOMAR na
    // fidelidade precisa aceitar o termo em vigor — a tela mostra só a caixa do termo.
    if (r.dados.fidelidade?.precisa_termo) {
      setPedirCadastro((p) => p ?? []);
      setErro(`${t.identificado(r.dados.nome)} ${t.aceitoTermo}.`);
      return;
    }
    setResultado(r.dados);
  }

  async function confirmarCodigo() {
    setOcupado(true);
    const r = await MesaService.confirmarCodigo(loja, resultado!.telefone, codigo.trim());
    setOcupado(false);
    if (r.ok) setResultado({ ...resultado!, fidelidade: { metodo: "CODIGO_CAIXA", marcou: true } });
    else setErro(r.erro);
  }

  async function lerTermo() {
    const r = await MesaService.termo(loja);
    if (r.ok) setTextoTermo(r.dados.secoes.flatMap((s) => [s.titulo ?? "", ...s.paragrafos]).filter(Boolean).join("\n\n"));
  }

  const campo = "w-full rounded-xl border border-current/20 bg-white/70 px-3 py-2.5 text-[15px]";

  if (resultado) {
    const f = resultado.fidelidade;
    return (
      <div className="rounded-2xl border border-current/15 p-4 text-sm" role="status">
        <p className="font-semibold">{t.identificado(resultado.nome)}</p>
        {f?.marcou && <p className="mt-1">{t.visitaMarcada}</p>}
        {f && f.marcou === false && f.motivo && <p className="mt-1 opacity-75">{f.motivo}</p>}
        {f?.aguardando_codigo && !f.marcou && (
          <div className="mt-2 flex gap-2">
            <input className={campo} inputMode="numeric" maxLength={6} placeholder={t.codigoCaixa}
                   value={codigo} onChange={(e) => setCodigo(e.target.value)} aria-label={t.codigoCaixa} />
            <button type="button" disabled={ocupado || codigo.trim().length < 4} onClick={() => void confirmarCodigo()}
                    className="shrink-0 rounded-full bg-[var(--cv-principal)] px-4 font-semibold text-white disabled:opacity-40">OK</button>
          </div>
        )}
        {erro && <p className="mt-2 text-red-700">{erro}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-current/15 p-4 text-sm">
      <p className="font-semibold">{t.identificar}</p>
      <input className={campo} inputMode="tel" autoComplete="tel" placeholder={t.telefone} aria-label={t.telefone}
             value={fone} onChange={(e) => setFone(e.target.value)} />
      {pedirCadastro && (
        <>
          <input className={campo} autoComplete="name" placeholder={t.seuNome} aria-label={t.seuNome}
                 value={nome} onChange={(e) => setNome(e.target.value)} />
          {pedirCadastro.includes("genero") && (
            <select className={campo} aria-label={t.genero} value={extra.genero}
                    onChange={(e) => setExtra({ ...extra, genero: e.target.value })}>
              <option value="">{t.genero}</option>
              <option value="FEMININO">Feminino</option><option value="MASCULINO">Masculino</option>
              <option value="OUTRO">Outro</option><option value="NAO_INFORMADO">Prefiro não dizer</option>
            </select>
          )}
          {pedirCadastro.includes("cidade") && (
            <input className={campo} placeholder={t.cidade} aria-label={t.cidade}
                   value={extra.cidade} onChange={(e) => setExtra({ ...extra, cidade: e.target.value })} />
          )}
          {pedirCadastro.includes("nascimento") && (
            <input className={campo} type="date" aria-label={t.nascimento}
                   value={extra.nascimento} onChange={(e) => setExtra({ ...extra, nascimento: e.target.value })} />
          )}
          <label className="flex items-start gap-2">
            <input type="checkbox" className="mt-1" checked={termo} onChange={(e) => setTermo(e.target.checked)} />
            <span>{t.aceitoTermo} · <button type="button" className="underline" onClick={() => void lerTermo()}>{t.verTermo}</button></span>
          </label>
          {textoTermo && <p className="max-h-40 overflow-y-auto whitespace-pre-line rounded-xl bg-white/60 p-3 text-xs">{textoTermo}</p>}
        </>
      )}
      {erro && <p className="text-red-700">{erro}</p>}
      <button type="button" disabled={ocupado || fone.replace(/\D/g, "").length < 10} onClick={() => void enviar()}
              className="rounded-full border border-current/30 py-2.5 font-semibold disabled:opacity-40">
        {t.continuar}
      </button>
    </div>
  );
}
