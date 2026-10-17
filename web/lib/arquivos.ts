/**
 * Os arquivos guardados sem dono — camada de service.
 *
 * 🔑 Pedido do dono (17/10/2026): uma varredura que LISTA os arquivos que nenhum registro aponta
 * mais e apaga só depois de conferidos. A conferência é refeita no servidor na hora de apagar.
 */

import { api } from "@/lib/api";

export type ArquivoOrfao = { nome: string; dono: string; tipo: string; bytes: number; criado_em: string };

export type Orfaos = {
  orfaos: ArquivoOrfao[];
  orfaos_n: number;
  orfaos_bytes: number;
  total_n: number;
  total_bytes: number;
};

export const ArquivosService = {
  orfaos: () => api.get<Orfaos>("/empresa/arquivos-orfaos"),
  apagarOrfaos: (nomes: string[]) =>
    api.post<{ apagados: number; bytes: number; message: string }>("/empresa/arquivos-orfaos/apagar", { nomes }),
};

/** 4957753 → "4,7 MB". */
export function tamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} KB`;
  return `${(bytes / 1048576).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`;
}

/** De quem o arquivo era, pelo nome com que foi guardado ("cartao-video-57" → "vídeo de cartão"). */
export function origemDoArquivo(dono: string): string {
  const regras: [RegExp, string][] = [
    [/^cartao-(video|capa)-/, "vídeo de cartão"], [/^cartao-/, "foto de cartão"],
    [/^anuncio-(video|capa)-/, "vídeo de anúncio"], [/^anuncio-/, "foto de anúncio"],
    [/^(categoria|subcategoria)-(video|capa)-/, "vídeo de seção"], [/^(categoria|subcategoria)-/, "foto de seção"],
    [/^(video|capa)-/, "vídeo de produto"], [/^produto-/, "foto de produto"],
    [/^ficha-/, "foto de ficha"], [/^catalogo-/, "PDF de catálogo"],
    [/logo/, "logo"],
  ];
  return regras.find(([r]) => r.test(dono))?.[1] ?? "outro";
}
