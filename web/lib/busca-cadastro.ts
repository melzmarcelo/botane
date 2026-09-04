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
      // A janela pede sempre a primeira página, então o total vem. O `??` é a
      // rede: sem cabeçalho, o que se sabe é o tamanho do que veio.
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
        total: filtro ? filtrados.length : (total ?? itens.length),
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
      // 🔑 **Só quem VENDE para a casa** (04/09/2026). A tabela de pessoas passou
      // a guardar funcionário e sócio; sem este recorte, o seletor de fornecedor
      // da nota viraria uma lista de gente da casa.
      const q = new URLSearchParams({ limite: String(limite), so_fornecedores: "true" });
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
        total: total ?? itens.length,
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
    async buscar(termo, limite) {
      const q = new URLSearchParams({ limite: String(limite) });
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
        total: total ?? itens.length,
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
    async buscar(termo, limite) {
      const alvo = termo.trim().toLowerCase();
      const casam = itens.filter(
        (i) =>
          !alvo ||
          i.nome.toLowerCase().includes(alvo) ||
          (i.codigo ?? "").toLowerCase().includes(alvo),
      );
      return { itens: casam.slice(0, limite), total: casam.length };
    },
  };
}
