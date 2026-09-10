/** Como o sistema MOSTRA número — um lugar só.
 *
 * 🔑 **O banco declara TRÊS famílias, e a tela mostrava tudo como se fosse
 * uma.** Não é questão de gosto: está na escala das colunas.
 *
 * | família          | coluna                                   | escala |
 * |------------------|------------------------------------------|--------|
 * | valor            | `custo_total`, `valor_total`, `preco_venda` | `numeric(18,2)` |
 * | custo unitário   | `custo_unitario`, `custo_medio`, `ultimo_preco`, `custo_referencia`, `custo_ficha_unitario` | `numeric(18,6)` |
 * | quantidade       | `quantidade`                              | `numeric(18,4)` |
 *
 * Valor é dinheiro que se SOMA numa nota — duas casas, e a terceira não existe.
 * Custo unitário é o que se MULTIPLICA por mil pratos, e é onde meio centavo
 * vira erro de verdade: `services/custos.py` guarda seis casas de propósito
 * (`CASAS_CUSTO`), e mostrá-lo com duas joga fora o que ele foi feito para ter.
 *
 * ⚠️ **`custo()` não INVENTA casa: ele para de esconder a que existe.** Quem
 * custa R$ 20,00 continua "R$ 20,00" — o mínimo é duas e o Intl apara o zero à
 * direita sozinho. Só quem tem fração aparece maior, que é exatamente quando o
 * número precisa ser lido inteiro.
 *
 * ⚠️ **Um número por família, não um por tela.** `qtd` estava definido oito
 * vezes, com três casas em cinco arquivos e quatro em três — o mesmo saldo
 * escrito de dois jeitos conforme a tela. `pct` estava em quatro. Divergência
 * assim não se descobre lendo o código: descobre-se quando alguém confere duas
 * telas e acha que uma delas mente.
 */

/** Dinheiro que se soma: sempre duas casas. */
export const reais = (v: number | string | null | undefined) =>
  v === null || v === undefined || v === ""
    ? "—"
    : Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** Custo de UMA unidade: até seis casas, como no banco.
 *
 * ⚠️ O mínimo de duas é o que impede "R$ 2,8" de aparecer onde se espera
 * dinheiro; o máximo de seis é o que impede R$ 0,169020 de virar R$ 0,17 —
 * 0,6% de erro que reaparece multiplicado na ficha. */
export const custo = (v: number | string | null | undefined) =>
  v === null || v === undefined || v === ""
    ? "—"
    : Number(v).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL",
        minimumFractionDigits: 2,
        maximumFractionDigits: 6,
      });

/** Quantidade: até quatro casas, como no banco, sem zero à toa.
 *
 * ⚠️ Mínimo ZERO de propósito: saldo de 132 unidades é "132", não "132,0000".
 * Quem tem fração mostra a fração. */
export const qtd = (n: number | string | null | undefined) =>
  n === null || n === undefined || n === ""
    ? "—"
    : Number(n).toLocaleString("pt-BR", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 4,
      });

/** Percentual. Uma casa é o padrão da casa (food cost, margem, variação). */
export const pct = (n: number | string | null | undefined, casas = 1) =>
  n === null || n === undefined || n === ""
    ? "—"
    : `${Number(n).toLocaleString("pt-BR", {
        minimumFractionDigits: casas,
        maximumFractionDigits: casas,
      })}%`;

/** Inteiro (contagem de coisas: pedidos, itens, pessoas). */
export const inteiro = (n: number | string | null | undefined) =>
  n === null || n === undefined || n === ""
    ? "—"
    : Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 0 });

// ---------------------------------------------------------------------------
// Entrada de dinheiro
// ---------------------------------------------------------------------------

/** O texto digitado vira "1.234,56" — centavos primeiro, como caixa de banco.
 *
 * 🔑 **Só os dígitos contam.** Quem digita "12" quer R$ 0,12 e continua para
 * "1234" = R$ 12,34: o valor cresce pela direita, e não há como o cursor ficar
 * do lado errado da vírgula. É a forma que todo caixa e todo aplicativo de
 * banco usam, e a única em que apagar um caractere faz o que se espera.
 *
 * ⚠️ **`type="number"` não serve para dinheiro** e era o que estava lá. Ele
 * aceita "1e5" e "1.2.3", mostra setinha de incremento em cima de um preço,
 * e no teclado pt-BR a vírgula — que é o separador daqui — simplesmente não
 * entra em parte dos navegadores: quem digitava "12,50" via "12". Some o
 * separador de milhar também, então R$ 1234567 aparece sem nenhuma âncora
 * para o olho conferir a ordem de grandeza. */
export function mascaraMoeda(texto: string): string {
  const digitos = texto.replace(/\D/g, "").slice(0, 13);
  if (!digitos) return "";
  const centavos = Number(digitos);
  return (centavos / 100).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** O que a máscara mostra vira o número que vai ao servidor. Vazio é `null` —
 * "sem preço" e "de graça" são coisas diferentes, e o servidor distingue. */
export function moedaParaNumero(texto: string): number | null {
  const digitos = texto.replace(/\D/g, "");
  return digitos ? Number(digitos) / 100 : null;
}

/** O número que veio do servidor vira o texto da máscara. */
export function numeroParaMoeda(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  return Number(v).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
