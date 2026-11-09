import { moedaParaNumero, numeroParaMoeda } from "@/lib/numeros";
import type { BemDetalhe, BemForm } from "@/lib/patrimonio";

/**
 * O formulário da ficha do bem, que atravessa as abas Dados do bem, Garantia e Preventiva.
 * 🔑 **O estado mora na página, não na aba**: a aba só monta quando está aberta, e o Salvar
 * do cabeçalho grava o que foi mexido em qualquer uma delas.
 */
export type Form = Record<string, string>;
export type Muda = (k: string) => (e: { target: { value: string } }) => void;

const TEXTOS = ["descricao", "apelido", "marca", "modelo", "numero_serie", "fornecedor",
  "nota_fiscal", "assistencia", "assistencia_contato", "observacao", "motivo_baixa"] as const;
const DATAS = ["data_compra", "garantia_ate", "ultima_preventiva", "data_baixa"] as const;
const ESCOLHAS = ["tensao", "criticidade", "situacao", "id_setor", "id_local"] as const;

export const VAZIO: Form = { situacao: "EM_USO" };

export function paraForm(b: BemDetalhe): Form {
  const f: Form = {};
  for (const k of [...TEXTOS, ...DATAS, ...ESCOLHAS]) {
    const v = (b as unknown as Record<string, unknown>)[k];
    f[k] = v === null || v === undefined ? "" : String(v);
  }
  f.preventiva_meses = b.preventiva_meses ? String(b.preventiva_meses) : "";
  f.vida_util_anos = b.vida_util_anos ? String(b.vida_util_anos) : "";
  f.id_produto = b.id_produto ? String(b.id_produto) : "";
  f.valor_compra = b.valor_compra !== null ? numeroParaMoeda(b.valor_compra) : "";
  return f;
}

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
  c.vida_util_anos = f.vida_util_anos ? Number(f.vida_util_anos) : null;
  // Fora do baixado a data não vale (o banco limpa); vazia na baixa, o banco põe hoje.
  if (c.situacao !== "BAIXADO") c.data_baixa = null;
  c.valor_compra = f.valor_compra ? moedaParaNumero(f.valor_compra) : null;
  return c;
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
