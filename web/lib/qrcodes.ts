/**
 * Os QR codes do Portal de Clientes — camada de service (regra da casa).
 *
 * 🔑 Pedido do dono (27/09/2026): o QR da pontuação, o do cardápio (vai na mesa), o da
 * reserva e o do site, organizados numa tela só (`/reservas/qrcodes`).
 */
import { api } from "@/lib/api";

export type TipoQr = "site" | "reserva" | "cardapio" | "fidelidade";

export type QrDaCasa = {
  tipo: TipoQr;
  nome: string;
  link: string;
  titulo: string;
  chamada: string;
  /** Onde costuma ficar — é a dica da tela, não uma regra. */
  onde: string;
  id_catalogo?: number;
  /** Falso quando o tipo existe mas não vale nesta loja (fidelidade desligada). */
  disponivel?: boolean;
  motivo?: string | null;
  metodo?: "QRCODE_MESA" | "CODIGO_CAIXA";
};

export type QrCodes = { site_url: string; tipos: QrDaCasa[] };

export type ImpressaoQr = {
  quantidade: number;
  tamanho: "P" | "M" | "G";
  titulo: string;
  chamada: string;
  extra: string;
  numerar: boolean;
  primeira_mesa: number;
};

export const listarQrCodes = () => api.get<QrCodes>("/reservas/qrcodes");

export const gravarEnderecoDoSite = (site_url: string) =>
  api.put<QrCodes & { message: string }>("/reservas/qrcodes/site", { site_url });

export function baixarQr(qr: QrDaCasa, p: ImpressaoQr) {
  const q = new URLSearchParams({
    tipo: qr.tipo,
    quantidade: String(p.quantidade),
    tamanho: p.tamanho,
    titulo: p.titulo,
    chamada: p.chamada,
    extra: p.extra,
    numerar: String(p.numerar),
    primeira_mesa: String(p.primeira_mesa),
  });
  if (qr.id_catalogo) q.set("id_catalogo", String(qr.id_catalogo));
  return api.baixar(`/reservas/qrcodes/pdf?${q}`);
}
