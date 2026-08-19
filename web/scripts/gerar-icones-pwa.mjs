/**
 * Gera os ícones do PWA a partir de um desenho vetorial, com sharp.
 *
 *   node scripts/gerar-icones-pwa.mjs
 *
 * Roda **na mão**, não no build: o desenho quase nunca muda e os PNGs vão para
 * o git. Se o cliente trocar a marca, é rodar de novo.
 *
 * São três formatos porque cada sistema recorta de um jeito:
 *
 * * `icone-192/512`  — o ícone comum, com a margem já no desenho.
 * * `icone-maskable`  — o Android recorta em círculo, folha ou quadrado
 *   arredondado conforme o aparelho. O que sobra garantido é o círculo central
 *   de 80% (a "zona segura"): o desenho fica menor e o fundo sangra até a borda.
 * * `apple-touch-icon` — o iPhone não recorta nem arredonda o que recebe, e não
 *   entende transparência: precisa do fundo pintado no próprio arquivo.
 */

import sharp from "sharp";
import { mkdirSync } from "node:fs";

const ERVA = "#2c6a4a";
const PAPEL = "#f3f5ef";
const LATAO = "#d9b168";

/**
 * A marca: uma xícara fumegante com o creme desenhado na boca.
 * Tudo em `path`, sem texto: fonte de sistema em SVG renderiza diferente em
 * cada máquina, e o ícone tem de sair igual em qualquer uma.
 *
 * @param escala fração do quadro ocupada pelo desenho (o maskable usa menos)
 */
const desenho = (escala) => {
  // O desenho não é centrado no quadro: o vapor sobe até y=54, a xícara desce
  // até y=382 e a asa puxa a massa para a direita. Escalar em torno de (256,256)
  // deixaria o ícone visivelmente alto e à esquerda — o que só aparece quando o
  // maskable encolhe o desenho. Escala-se em torno do centro REAL da figura, e
  // esse centro vai para o meio do quadro.
  const t = `translate(256 256) scale(${escala}) translate(-266 -218)`;
  return `
  <g transform="${t}">
    <!-- vapor: três traços que sobem, o do meio mais alto -->
    <path d="M212 150 q-14 -22 0 -44 q14 -22 0 -44" fill="none" stroke="${PAPEL}"
          stroke-width="13" stroke-linecap="round" opacity="0.75"/>
    <path d="M256 140 q-16 -26 0 -52 q16 -26 0 -52" fill="none" stroke="${PAPEL}"
          stroke-width="13" stroke-linecap="round" opacity="0.9"/>
    <path d="M300 150 q-14 -22 0 -44 q14 -22 0 -44" fill="none" stroke="${PAPEL}"
          stroke-width="13" stroke-linecap="round" opacity="0.75"/>

    <!-- xícara: trapézio de boca larga, com a asa à direita -->
    <path d="M132 196 h248 l-26 150 a44 44 0 0 1 -43 36 h-110 a44 44 0 0 1 -43 -36 z"
          fill="${PAPEL}"/>
    <path d="M372 232 h26 a44 44 0 0 1 0 88 h-38" fill="none" stroke="${PAPEL}"
          stroke-width="22" stroke-linecap="round"/>

    <!-- o creme na boca da xícara, com o risco do desenho de barista -->
    <path d="M256 250 q54 -6 76 -46 q6 62 -76 66 q-82 -4 -76 -66 q22 40 76 46 z"
          fill="${LATAO}"/>
    <path d="M180 204 q40 30 76 46 q36 -16 76 -46" fill="none" stroke="${ERVA}"
          stroke-width="7" stroke-linecap="round" opacity="0.35"/>
  </g>`;
};

const svg = (escala, raio) => Buffer.from(
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
     <rect width="512" height="512" rx="${raio}" fill="${ERVA}"/>
     ${desenho(escala)}
   </svg>`,
);

mkdirSync("public", { recursive: true });

const arquivos = [
  // [nome, lado, escala do desenho, raio do fundo]
  ["public/icone-192.png", 192, 0.78, 96],
  ["public/icone-512.png", 512, 0.78, 96],
  // Maskable: fundo quadrado (o sistema é quem arredonda) e desenho menor,
  // para sobreviver ao recorte em círculo.
  ["public/icone-maskable-512.png", 512, 0.6, 0],
  // iPhone: quadrado, sem raio — ele aplica o próprio.
  ["public/apple-touch-icon.png", 180, 0.78, 0],
  ["public/favicon-32.png", 32, 0.82, 0],
];

for (const [nome, lado, escala, raio] of arquivos) {
  await sharp(svg(escala, raio)).resize(lado, lado).png().toFile(nome);
  console.log(`  ${nome} (${lado}px)`);
}
console.log("ícones gerados.");
