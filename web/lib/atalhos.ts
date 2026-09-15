/**
 * Os atalhos do menu — as telas que ESTA pessoa abre todo dia, no topo.
 *
 * 🔑 **Nasceram para ocupar o espaço que já estava vazio** (15/09/2026). A
 * lateral mostrava seis títulos de grupo numa coluna de 900px: cerca de 85%
 * dela não fazia nada, enquanto toda navegação custava dois cliques. E o menu
 * não sabia que a cozinha não usa as mesmas telas que o escritório.
 *
 * ⚠️ **Fica no navegador, não no banco.** É preferência de quem usa, do mesmo
 * tipo de "qual grupo eu deixei aberto" — e guardá-la no servidor obrigaria uma
 * tabela, uma rota e uma permissão para decidir a ordem de cinco links.
 */
export const CHAVE_ATALHOS = "botane.atalhos";

/** Cinco é o teto: atalho demais é o menu de novo, só que sem os grupos. */
export const TETO_ATALHOS = 5;

/**
 * O que vem marcado antes de alguém escolher.
 *
 * ⚠️ **Semear é de propósito.** Uma seção vazia esperando que a pessoa
 * descubra o alfinete é um recurso que ninguém encontra — e estes quatro são o
 * caminho do dia da casa. Quem quiser outro troca em dois cliques; quem tirar
 * todos fica sem a seção, e ela NÃO volta a se semear (o que manda é a chave
 * existir, não a lista ter conteúdo).
 */
export const ATALHOS_SUGERIDOS = ["/produtos", "/estoque", "/compras", "/cmv"];

export function lerAtalhos(disponiveis: string[]): string[] {
  if (typeof window === "undefined") return [];
  let guardado: string[] | null = null;
  try {
    const cru = localStorage.getItem(CHAVE_ATALHOS);
    if (cru !== null) {
      const lido: unknown = JSON.parse(cru);
      if (Array.isArray(lido)) guardado = lido.filter((h): h is string => typeof h === "string");
    }
  } catch {
    guardado = null;
  }
  const lista = guardado ?? ATALHOS_SUGERIDOS;
  // ⚠️ Sempre pela lista do que a pessoa PODE abrir: permissão revogada, loja
  // trocada ou módulo desligado deixariam um atalho para um 403.
  return lista.filter((h) => disponiveis.includes(h)).slice(0, TETO_ATALHOS);
}

export function gravarAtalhos(lista: string[]) {
  try {
    localStorage.setItem(CHAVE_ATALHOS, JSON.stringify(lista.slice(0, TETO_ATALHOS)));
  } catch {
    /* navegador sem armazenamento: o menu continua funcionando, só não lembra */
  }
}
