/**
 * A contagem de inventário — camada de service (regra da casa: página não chama `api`).
 * A tela de contagem nasceu chamando a API direto; o que entra novo mora aqui.
 */
import { api } from "@/lib/api";

/**
 * Inclui na contagem ABERTA um produto achado na prateleira que não estava na lista
 * (migração 096). Devolve a contagem inteira de novo, já com a linha nova.
 */
export const incluirNaContagem = <T,>(idInventario: number | string, idProduto: number,
                                      idLocal: number | null) =>
  api.post<T>(`/inventarios/${idInventario}/incluir`, {
    id_produto: idProduto,
    id_local: idLocal,
  });
