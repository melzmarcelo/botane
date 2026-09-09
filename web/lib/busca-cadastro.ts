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
  /**
   * 🔑 **`offset` existe para a janela PAGINAR de verdade** (09/09/2026,
   * pedido do dono). Antes ela só sabia "mostrar mais": pedia
   * `limite = 25 x pagina` e trazia tudo DESDE O COMEÇO de novo — para chegar
   * ao fim de 3.183 produtos, buscaria os 3.183. Com o deslocamento, cada
   * página é uma página.
   */
  buscar: (
    termo: string,
    limite: number,
    offset?: number,
  ) => Promise<{
    itens: ItemBusca[];
    /**
     * ⚠️ **`null` quer dizer "o servidor nao disse", nao "zero".** O total sai
     * numa consulta separada e SO na primeira pagina — virar a pagina nao muda
     * o total, e recontar custaria a tabela inteira a cada clique. Quem chama
     * guarda o que ja tinha; trocar o nulo por `itens.length` devolve o tamanho
     * da PAGINA e faz o rodape sumir na pagina 2, que foi exatamente o defeito.
     */
    total: number | null;
  }>;
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
/**
 * ⚠️ **O recorte vai no `extra`, que e query do SERVIDOR — nao ha filtro de
 * cliente.** Havia um, e ele quebrava a paginacao de duas formas: o total
 * passava a ser o tamanho da PAGINA (entao nunca existia segunda pagina) e uma
 * pagina de 25 com um registro descartado mostrava 24. Recorte que o servidor
 * sabe fazer nao se faz no navegador — `controla_estoque`, `tipo` e
 * `excluir_id` sao parametros de `/produtos`.
 */
export function fonteProdutos(extra = ""): FonteBusca {
  return {
    titulo: "Buscar produto",
    placeholder: "código ou nome",
    singular: "produto",
    async buscar(termo, limite, offset = 0) {
      const q = new URLSearchParams({ limite: String(limite) });
      if (offset) q.set("offset", String(offset));
      if (termo.trim()) q.set("busca", termo.trim());
      const { itens, total } = await api.listar<ProdutoBruto>(
        `/produtos?${q}${extra ? `&${extra}` : ""}`,
      );
      return {
        itens: itens.map((p) => ({
          id: p.id,
          codigo: p.codigo,
          nome: p.nome,
          detalhe: [p.um_estoque, p.categoria].filter(Boolean).join(" · ") || null,
          bruto: p as unknown as Record<string, unknown>,
        })),
        // ⚠️ Cru, inclusive o nulo: quem chama e que sabe o que ja tinha.
        total,
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
    async buscar(termo, limite, offset = 0) {
      // 🔑 **Só quem VENDE para a casa** (04/09/2026). A tabela de pessoas passou
      // a guardar funcionário e sócio; sem este recorte, o seletor de fornecedor
      // da nota viraria uma lista de gente da casa.
      const q = new URLSearchParams({ limite: String(limite), so_fornecedores: "true" });
      if (offset) q.set("offset", String(offset));
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

/**
 * Todas as PESSOAS — não só quem vende para a casa.
 *
 * 🔑 **A mesma janela de pesquisa do produto** (04/09/2026, relato do dono:
 * "na busca da pessoa, coloca o mesmo padrão do produto, com o combobox fica
 * ruim a visualização"). Um `<select>` de 800 nomes não se percorre: o nome
 * inteiro não cabe, não há busca, e a política de cupom — que é o motivo de
 * escolher a pessoa — fica invisível.
 *
 * ⚠️ **Sem `so_fornecedores`, de propósito.** Quem se escolhe num cupom é
 * justamente quem NÃO vende para a casa: funcionário, sócio.
 */
export function fontePessoas(): FonteBusca {
  return {
    titulo: "Buscar pessoa",
    placeholder: "nome ou CNPJ",
    singular: "pessoa",
    async buscar(termo, limite, offset = 0) {
      const q = new URLSearchParams({ limite: String(limite) });
      if (offset) q.set("offset", String(offset));
      if (termo.trim()) q.set("busca", termo.trim());
      const { itens, total } = await api.listar<FornecedorBruto>(`/fornecedores?${q}`);
      return {
        itens: itens.map((f) => {
          const p = f as unknown as {
            cupom_base?: string; cupom_desconto_pct?: number; fornecedor?: boolean;
          };
          // 🔑 **A política aparece na LINHA da busca.** Escolher a pessoa muda
          // o valor do cupom; descobrir isso só depois de lançar seria tarde.
          const politica = [
            p.cupom_base === "CUSTO" ? "pelo custo" : null,
            Number(p.cupom_desconto_pct) > 0 ? `${Number(p.cupom_desconto_pct)}% off` : null,
            p.fornecedor ? "fornecedor" : null,
          ].filter(Boolean).join(" · ");
          return {
            id: f.id,
            codigo: f.cnpj,
            nome: f.nome_fantasia || f.nome,
            detalhe: politica || (f.cidade ?? null),
            bruto: f as unknown as Record<string, unknown>,
          };
        }),
        total,
      };
    },
  };
}

/**
 * Fonte a partir de uma lista JÁ CARREGADA.
 *
 * Nem tudo vem do servidor: as fichas homologadas, por exemplo, já estão na
 * tela e são poucas por natureza. A janela de pesquisa é a mesma — o que muda
 * é de onde os registros vêm, e quem usa não precisa saber a diferença.
 */
export function fonteDaLista(
  titulo: string,
  singular: string,
  itens: ItemBusca[],
  placeholder = "código ou nome",
): FonteBusca {
  return {
    titulo,
    placeholder,
    singular,
    async buscar(termo, limite, offset = 0) {
      const alvo = termo.trim().toLowerCase();
      const casam = itens.filter(
        (i) =>
          !alvo ||
          i.nome.toLowerCase().includes(alvo) ||
          (i.codigo ?? "").toLowerCase().includes(alvo),
      );
      // ⚠️ Esta fonte ja tem a lista INTEIRA na memoria (sao poucas por
      // natureza), entao aqui o corte e mesmo no navegador -- e o `total`
      // continua sendo o do filtro, nao o da pagina.
      return { itens: casam.slice(offset, offset + limite), total: casam.length };
    },
  };
}
