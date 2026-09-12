/** Como o sistema MOSTRA número — um lugar só.
 *
 * 🔑 **O banco declara TRÊS famílias de número**, e a escala de cada coluna diz
 * quanta precisão existe para ser guardada:
 *
 * | família          | coluna                                   | escala |
 * |------------------|------------------------------------------|--------|
 * | valor            | `custo_total`, `valor_total`, `preco_venda` | `numeric(18,2)` |
 * | custo unitário   | `custo_unitario`, `custo_medio`, `ultimo_preco`, `custo_referencia`, `custo_ficha_unitario` | `numeric(18,6)` |
 * | quantidade       | `quantidade`                              | `numeric(18,4)` |
 *
 * A escala da coluna manda no que se GRAVA; a tela é outra conversa.
 *
 * ⚠️ **Dinheiro aparece com DUAS casas, seja valor ou custo unitário** (pedido
 * do dono, 12/09/2026). As seis casas continuam inteiras onde importam — no
 * banco, na conta do servidor e no campo de digitação (`numeroParaCusto`) —,
 * mas a tela mostrava "R$ 0,169020" no meio de uma lista de preços e o número
 * ficava mais difícil de ler do que de entender. Quem precisa do dígito fino
 * tem a memória de cálculo e a exportação, não a linha da tabela.
 *
 * ⚠️ **Arredondar é da EXIBIÇÃO, e só dela.** `custo()` nunca toca no que é
 * enviado ao servidor: quem salva usa `moedaParaNumero`/`textoParaNumero`, e o
 * campo de custo continua aceitando e devolvendo as seis casas.
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

/** Custo de UMA unidade: duas casas na tela, como todo dinheiro daqui.
 *
 * 🔑 **Mesma régua de `reais()`, nome próprio de propósito.** As duas famílias
 * continuam separadas no código porque são separadas no banco — `custo_medio` é
 * `numeric(18,6)` e `valor_total` é `numeric(18,2)`. Guardar a distinção numa
 * função com nome deixa a régua da exibição em UM lugar: se um dia a tela
 * quiser o dígito fino de volta, muda aqui e vale nas trinta e poucas telas.
 *
 * ⚠️ **R$ 0,169020 vira "R$ 0,17" na tela, e isso é aceito.** O número cheio
 * não se perde: ele é o que o servidor multiplica na ficha e o que sai na
 * memória de cálculo e na exportação. */
export const custo = (v: number | string | null | undefined) => reais(v);

/** Quantas casas a LOJA quer ver na quantidade (`parametros.casas_decimais_qtd`).
 *
 * 🔑 **Era ajuste morto**: existia no banco desde a migração 001, a tela de
 * Lojas o oferecia e ninguém o lia — mexer ali não mudava nada. Agora chega
 * pelo `/auth/me` e a sessão o define ANTES de qualquer tela pintar.
 *
 * ⚠️ **Variável de módulo, e é seguro por causa de duas coisas do próprio
 * sistema**: o layout de `(app)` segura toda tela enquanto o `/auth/me` não
 * responde, e trocar de loja no seletor recarrega a página inteira, de
 * propósito. Não há, portanto, tela pintada com o valor velho — nem no
 * servidor, que não renderiza nada de dentro de `(app)` antes da sessão.
 * Um contexto de React exigiria trocar `qtd(x)` por `fmt.qtd(x)` em dez
 * arquivos para resolver um problema que estas duas garantias já resolvem.
 *
 * ⚠️ O padrão é 3, o mesmo do banco. */
let casasQtd = 3;

export function definirCasasQtd(n: number | null | undefined) {
  if (typeof n === "number" && n >= 0 && n <= 6) casasQtd = n;
}

/** Quantidade, nas casas que a loja pediu (até 4, que é a escala do banco).
 *
 * ⚠️ Mínimo ZERO de propósito: saldo de 132 unidades é "132", não "132,0000".
 * Quem tem fração mostra a fração.
 * ⚠️ **A loja pode pedir 0, e aí a EXIBIÇÃO arredonda** — 0,5 KG aparece como
 * "1". É o que o ajuste quer dizer ("0 a 6", na tela de Lojas), e vale só para
 * a tela: o que está gravado no razão não muda uma casa.
 * ⚠️ Pedir 5 ou 6 não inventa dígito: `quantidade` é `numeric(18,4)`, então o
 * teto real continua sendo quatro. */
export const qtd = (n: number | string | null | undefined) =>
  n === null || n === undefined || n === ""
    ? "—"
    : Number(n).toLocaleString("pt-BR", {
        minimumFractionDigits: 0,
        maximumFractionDigits: Math.min(casasQtd, 4),
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

/** Texto digitado à mão vira número — vírgula OU ponto, com ou sem milhar.
 *
 * ⚠️ **"1.234" é ambíguo e a regra decide pelo contexto**: havendo vírgula no
 * texto, o ponto só pode ser milhar ("1.234,56" → 1234.56); não havendo, o
 * ponto é decimal, porque é o que sai de quem digita rápido no teclado
 * numérico ("1.5" → 1.5). Tratar sempre como milhar transformaria 1,5 kg de
 * fermento em 15; sempre como decimal quebraria todo valor acima de mil.
 */
export function textoParaNumero(texto: string): number | null {
  const t = texto.trim();
  if (!t) return null;
  const limpo = t.includes(",") ? t.replace(/\./g, "").replace(",", ".") : t;
  const n = Number(limpo);
  return Number.isFinite(n) ? n : null;
}

/** Custo unitário para o campo: até seis casas, sem zero à toa.
 *
 * ⚠️ **Não força duas casas como `numeroParaMoeda`.** Aqui um custo de 2,5 fica
 * "2,5": o campo é de digitação, e completar com zeros o que a pessoa ainda
 * está escrevendo faz o cursor brigar com ela. Quem EXIBE custo usa `custo()`,
 * que tem o mínimo de duas porque ali é leitura. */
export function numeroParaCusto(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  return Number(v).toLocaleString("pt-BR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 6,
    useGrouping: false,
  });
}
