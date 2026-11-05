import { api } from "@/lib/api";

/**
 * As preferências de tela de quem está usando (migração 148, `routers/preferencias.py`).
 *
 * 🔑 Ficam no servidor, e não no navegador: o grid arrumado no escritório aparece igual no tablet.
 * A chave nomeia a tela (`grade:produtos`); o valor é um JSON livre de cada tela.
 */
export const lerPreferencia = <T,>(chave: string) =>
  api.get<{ valor: T | null }>(`/preferencias/${encodeURIComponent(chave)}`).then((r) => r.valor);

export const gravarPreferencia = (chave: string, valor: unknown) =>
  api.put<{ ok: boolean }>(`/preferencias/${encodeURIComponent(chave)}`, { valor });
