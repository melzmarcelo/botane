/**
 * Datas do dia de HOJE aqui, não em Londres.
 *
 * ⚠️ `new Date().toISOString().slice(0, 10)` devolve o dia em **UTC**. Às 22h
 * de Brasília já é o dia seguinte lá — e a tela de Vendas propunha amanhã como
 * data da importação. Num restaurante que fecha às 23h, isso quer dizer que a
 * venda do dia inteiro entraria no dia seguinte: o CMV do mês fecha errado, o
 * relatório de movimentação não bate com o saldo, e ninguém desconfia da data.
 *
 * O banco resolve o mesmo problema com a sessão em `America/Sao_Paulo`. Aqui a
 * conta é do navegador, então a regra é: para virar TEXTO `aaaa-mm-dd`, sempre
 * por estas funções. `sv-SE` é o truque conhecido — é o formato ISO no fuso de
 * quem está olhando.
 */

export const diaLocal = (d: Date = new Date()): string => d.toLocaleDateString("sv-SE");

/** O dia de hoje, como a pessoa na frente da tela o chama. */
export const hoje = (): string => diaLocal();

/** Hoje mais (ou menos) N dias — amanhã é `somarDias(1)`. */
export const somarDias = (dias: number, base: Date = new Date()): string => {
  const d = new Date(base);
  d.setDate(d.getDate() + dias);
  return diaLocal(d);
};

/** Hoje mais (ou menos) N meses — o mês passado é `somarMeses(-1)`. */
export const somarMeses = (meses: number, base: Date = new Date()): string => {
  const d = new Date(base);
  d.setMonth(d.getMonth() + meses);
  return diaLocal(d);
};

/** O primeiro dia do mês corrente. */
export const primeiroDiaDoMes = (base: Date = new Date()): string =>
  diaLocal(new Date(base.getFullYear(), base.getMonth(), 1));
