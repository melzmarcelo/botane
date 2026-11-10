import { moedaParaNumero, numeroParaMoeda } from "@/lib/numeros";
import type { BemDetalhe, BemForm } from "@/lib/patrimonio";

/**
 * O formulário da ficha do bem, que atravessa as abas Dados do bem, Garantia e Preventiva.
 * 🔑 **O estado mora na página, não na aba**: a aba só monta quando está aberta, e o Salvar
 * do cabeçalho grava o que foi mexido em qualquer uma delas.
 * 157: o checklist da preventiva mora no formulário como texto, um item por linha.
 */
export type Form = Record<string, string>;
export type Muda = (k: string) => (e: { target: { value: string } }) => void;

const TEXTOS = ["descricao", "apelido", "marca", "modelo", "numero_serie", "fornecedor",
  "nota_fiscal", "assistencia", "assistencia_contato", "observacao", "motivo_baixa",
  "responsavel"] as const;
const DATAS = ["data_compra", "garantia_ate", "ultima_preventiva", "data_baixa"] as const;
const ESCOLHAS = ["tensao", "criticidade", "situacao", "id_setor", "id_local", "garantia_tipo"] as const;

export const VAZIO: Form = { situacao: "EM_USO" };

export function paraForm(b: BemDetalhe): Form {
  const f: Form = {};
  for (const k of [...TEXTOS, ...DATAS, ...ESCOLHAS]) {
    const v = (b as unknown as Record<string, unknown>)[k];
    f[k] = v === null || v === undefined ? "" : String(v);
  }
  f.preventiva_meses = b.preventiva_meses ? String(b.preventiva_meses) : "";
  f.garantia_meses = b.garantia_meses ? String(b.garantia_meses) : "";
  f.vida_util_anos = b.vida_util_anos ? String(b.vida_util_anos) : "";
  f.id_produto = b.id_produto ? String(b.id_produto) : "";
  f.valor_compra = b.valor_compra !== null ? numeroParaMoeda(b.valor_compra) : "";
  f.preventiva_checklist = (b.preventiva_checklist ?? []).join("\n");
  return f;
}

/** Os itens do checklist como estão no formulário (um por linha, sem os vazios). */
export const itensDoChecklist = (texto: string | undefined) =>
  (texto ?? "").split("\n").map((i) => i.trim()).filter(Boolean);

export function paraCorpo(f: Form): BemForm {
  const c: BemForm = {};
  for (const k of [...TEXTOS, ...DATAS]) c[k] = f[k]?.trim() || null;
  c.tensao = f.tensao || null;
  c.criticidade = f.criticidade || null;
  c.situacao = f.situacao || "EM_USO";
  c.id_setor = f.id_setor ? Number(f.id_setor) : null;
  c.id_local = f.id_local ? Number(f.id_local) : null;
  c.id_produto = f.id_produto ? Number(f.id_produto) : null;
  c.preventiva_meses = f.preventiva_meses ? Number(f.preventiva_meses) : null;
  c.garantia_meses = f.garantia_meses ? Number(f.garantia_meses) : null;
  c.garantia_tipo = f.garantia_tipo || null;
  c.vida_util_anos = f.vida_util_anos ? Number(f.vida_util_anos) : null;
  c.preventiva_checklist = itensDoChecklist(f.preventiva_checklist);
  // Fora do baixado a data não vale (o banco limpa); vazia na baixa, o banco põe hoje.
  if (c.situacao !== "BAIXADO") c.data_baixa = null;
  c.valor_compra = f.valor_compra ? moedaParaNumero(f.valor_compra) : null;
  return c;
}

/**
 * 157 — a data final da garantia: compra + meses. ⚠️ A MESMA soma do banco
 * (`date + make_interval(months => n)`): 31/01 + 1 mês = último dia de fevereiro. Sem compra
 * ou sem meses, devolve vazio — e aí vale o que a pessoa digitar.
 */
export function somarMeses(iso: string | undefined, meses: string | number | undefined): string {
  const n = Number(meses);
  if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso) || !n) return "";
  const [a, m, d] = [+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)];
  const alvo = new Date(Date.UTC(a, m + n, 1));
  const ultimo = new Date(Date.UTC(alvo.getUTCFullYear(), alvo.getUTCMonth() + 1, 0)).getUTCDate();
  alvo.setUTCDate(Math.min(d, ultimo));
  return alvo.toISOString().slice(0, 10);
}

/** "em 9 dias", "hoje", "há 3 dias" — o prazo que a faixa e as abas dizem. */
export function emDias(d: number | null | undefined): string {
  if (d === null || d === undefined) return "";
  if (d === 0) return "hoje";
  if (d === 1) return "amanhã";
  if (d > 0) return `em ${d} dias`;
  return d === -1 ? "há 1 dia" : `há ${-d} dias`;
}

/** Dias de hoje até uma data ISO, pelo calendário (sem fuso: a data é do dia da casa). */
export function diasAte(iso: string, hojeIso: string): number {
  const [a, b] = [iso, hojeIso].map((x) => Date.UTC(+x.slice(0, 4), +x.slice(5, 7) - 1, +x.slice(8, 10)));
  return Math.round((a - b) / 86_400_000);
}
