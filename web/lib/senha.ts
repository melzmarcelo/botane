/**
 * Tamanho mínimo de senha — o mesmo número que a API cobra.
 *
 * ⚠️ **A regra de verdade é do servidor** (`api/config.py`, `SENHA_MINIMA`):
 * `minLength` no input só evita a viagem, e um formulário que promete um
 * tamanho e recebe 422 do outro lado faz a pessoa achar que digitou errado.
 * Ao mudar lá, mude aqui — e vice-versa.
 */
export const SENHA_MINIMA = 6;

/** "Mínimo de 6 caracteres." — para não escrever o número na frase. */
export const dicaSenha = `Mínimo de ${SENHA_MINIMA} caracteres.`;
