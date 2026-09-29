"use client";

import { useEffect, useState } from "react";

import { useAviso } from "@/components/aviso-flutuante";
import { Etiqueta } from "@/components/ui";
import { corrigir, gerar, obter, type TipoTraduzivel, type Traducao } from "@/lib/traducao";

/**
 * As versões em inglês e alemão do que o cliente lê no site — do produto, da categoria, da
 * subcategoria ou do catálogo.
 *
 * 🔑 Pedido do dono (decidido em 29/09/2026): Claude Haiku traduz ao salvar; aqui se confere
 * e se corrige. ⚠️ O campo corrigido à mão fica marcado e a tradução automática NÃO o
 * sobrescreve; "gerar de novo" o devolve ao automático.
 * ⚠️ Sem a chave da Anthropic, a tradução automática fica desligada — a tela diz isso, e os
 * campos continuam editáveis à mão.
 */
const IDIOMAS = [
  { v: "en" as const, r: "Inglês" },
  { v: "de" as const, r: "Alemão" },
];
const ROTULO = { nome: "Nome", descricao: "Descrição" };

export default function Traducoes({ tipo, id, aoMudar }: {
  tipo: TipoTraduzivel; id: number; aoMudar?: () => void;
}) {
  const aviso = useAviso();
  const [t, setT] = useState<Traducao | null>(null);
  const [form, setForm] = useState<{ en: Record<string, string>; de: Record<string, string> }>({ en: {}, de: {} });
  const [ocupado, setOcupado] = useState(false);

  function montar(x: Traducao) {
    setT(x);
    setForm({
      en: Object.fromEntries(x.campos.map((c) => [c, x.en[c] ?? ""])),
      de: Object.fromEntries(x.campos.map((c) => [c, x.de[c] ?? ""])),
    });
  }

  // ⚠️ Resposta atrasada NÃO sobrescreve o que a pessoa já digitou: sem o `vivo`, a segunda
  // busca (o React de desenvolvimento roda o efeito duas vezes; a rede lenta faz o mesmo)
  // chegava depois da digitação e zerava o campo — e "Salvar" gravava vazio.
  useEffect(() => {
    let vivo = true;
    obter(tipo, id).then((x) => { if (vivo) montar(x); }).catch(() => { if (vivo) setT(null); });
    return () => { vivo = false; };
  }, [tipo, id]);

  if (!t) return null;
  const temOrigem = t.campos.some((c) => (t.origem[c] ?? "").trim());

  async function salvar() {
    if (!t) return;
    setOcupado(true);
    try {
      const r = await corrigir(tipo, id, form);
      montar(r);
      aviso.sucesso(r.message);
      aoMudar?.();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível salvar a tradução");
    } finally {
      setOcupado(false);
    }
  }

  async function gerarDeNovo() {
    setOcupado(true);
    try {
      const r = await gerar(tipo, id);
      montar(r);
      aviso.sucesso(r.message);
      aoMudar?.();
    } catch (e) {
      aviso.erro(e instanceof Error ? e.message : "Não foi possível traduzir agora");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-linha p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="rotulo-campo">Para o site em inglês e alemão</span>
        <span className="flex flex-wrap items-center gap-2">
          {t.desatualizada && <Etiqueta cor="alerta">o português mudou</Etiqueta>}
          {!t.ligada && <Etiqueta>tradução automática desligada</Etiqueta>}
          {t.ligada && temOrigem && (
            <button type="button" className="link-acao text-[13px]" disabled={ocupado}
                    onClick={() => void gerarDeNovo()}
                    title="Traduz de novo — inclusive o que foi corrigido à mão">
              {ocupado ? "…" : "gerar de novo"}
            </button>
          )}
        </span>
      </div>
      {!temOrigem ? (
        <p className="text-[13px] text-suave">Sem texto em português, não há o que traduzir.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {IDIOMAS.map((i) => (
            <div key={i.v} className="flex flex-col gap-2">
              <b className="text-[13px]">{i.r}</b>
              {t.campos.filter((c) => (t.origem[c] ?? "").trim()).map((c) => {
                const manual = t.editada.includes(t.colunas[c][i.v]);
                return (
                  <label key={c} className="flex flex-col gap-1">
                    <span className="text-[12px] text-suave">
                      {ROTULO[c]}{manual ? " · corrigido à mão" : ""}
                    </span>
                    {c === "descricao" ? (
                      <textarea className="campo" rows={2} maxLength={700} value={form[i.v][c] ?? ""}
                                placeholder={t.ligada ? "será traduzido ao salvar" : "em branco = o site mostra o português"}
                                onChange={(e) => setForm({ ...form, [i.v]: { ...form[i.v], [c]: e.target.value } })} />
                    ) : (
                      <input className="campo" maxLength={160} value={form[i.v][c] ?? ""}
                             placeholder={t.ligada ? "será traduzido ao salvar" : "em branco = o site mostra o português"}
                             onChange={(e) => setForm({ ...form, [i.v]: { ...form[i.v], [c]: e.target.value } })} />
                    )}
                  </label>
                );
              })}
            </div>
          ))}
        </div>
      )}
      {temOrigem && (
        <div className="flex justify-end">
          <button type="button" className="btn btn-secundario" disabled={ocupado} aria-busy={ocupado}
                  onClick={() => void salvar()}>
            Salvar tradução
          </button>
        </div>
      )}
    </div>
  );
}
