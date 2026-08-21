import { api } from "@/lib/api";

/**
 * As fontes de busca de cadastro.
 *
 * Combobox serve até umas dezenas de linhas. Uma casa com dois mil insumos
 * transforma o `<select>` num rolo impossível — e o navegador ainda desiste de
 * desenhar a lista inteira. Aqui a busca vai ao SERVIDOR: digita-se código ou
 * nome, e só o que casa desce.
 *
 * Cada fonte diz de onde vêm os registros e como mostrá-los. Quem usa não
 * precisa saber de rota nem de parâmetro — só escolhe a fonte.
 */

export type ItemBusca = {
  id: number;
  codigo: string | null;
  nome: string;
  /** Linha de baixo no resultado: unidade, categoria, CNPJ… */
  detalhe?: string | null;
  /** Guardado para quem escolhe precisar de mais que id e nome. */
  bruto?: Record<string, unknown>;
};

export type FonteBusca = {
  titulo: string;
  placeholder: string;
  /** Como chamar UMA linha desta fonte, para as frases da tela. */
  singular: string;
  buscar: (termo: string, limite: number) => Promise<{ itens: ItemBusca[]; total: number }>;
};

type ProdutoBruto = {
  id: number;
  codigo: string;
  nome: string;
  um_estoque: string | null;
  categoria: string | null;
  tipo: string;
  controla_estoque: boolean;
};

/**
 * Produtos. `filtro` recorta o que faz sentido em cada tela — na ficha só entra
 * o que se consome, no ajuste só o que tem estoque.
 */
export function fonteProdutos(
  filtro?: (p: ProdutoBruto) => boolean,
  extra = "",
): FonteBusca {
  return {
    titulo: "Buscar produto",
    placeholder: "código ou nome",
    singular: "produto",
    async buscar(termo, limite) {
      const q = new URLSearchParams({ limite: String(limite) });
      if (termo.trim()) q.set("busca", termo.trim());
      const { itens, total } = await api.listar<ProdutoBruto>(
        `/produtos?${q}${extra ? `&${extra}` : ""}`,
      );
      const filtrados = filtro ? itens.filter(filtro) : itens;
      return {
        itens: filtrados.map((p) => ({
          id: p.id,
          codigo: p.codigo,
          nome: p.nome,
          detalhe: [p.um_estoque, p.categoria].filter(Boolean).join(" · ") || null,
          bruto: p as unknown as Record<string, unknown>,
        })),
        // O total é o do servidor; filtrar no cliente só pode diminuir, e
        // mostrar "12 de 300" quando 288 foram descartados aqui mentiria.
        total: filtro ? filtrados.length : total,
      };
    },
  };
}

type FornecedorBruto = {
  id: number;
  nome: string;
  nome_fantasia: string | null;
  cnpj: string | null;
  cidade: string | null;
};

export function fonteFornecedores(): FonteBusca {
  return {
    titulo: "Buscar fornecedor",
    placeholder: "nome, fantasia ou CNPJ",
    singular: "fornecedor",
    async buscar(termo, limite) {
      const q = new URLSearchParams({ limite: String(limite) });
      if (termo.trim()) q.set("busca", termo.trim());
      const { itens, total } = await api.listar<FornecedorBruto>(`/fornecedores?${q}`);
      return {
        itens: itens.map((f) => ({
          id: f.id,
          codigo: f.cnpj,
          nome: f.nome_fantasia || f.nome,
          detalhe: [f.nome_fantasia ? f.nome : null, f.cidade].filter(Boolean).join(" · ") || null,
          bruto: f as unknown as Record<string, unknown>,
        })),
        total,
      };
    },
  };
}
