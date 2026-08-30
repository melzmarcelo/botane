/**
 * Passa por todas as telas com a base VAZIA e diz qual quebra.
 *
 * ⚠️ Tela com zero registro é o estado que ninguém testa e que o cliente vê no
 * primeiro dia. Divisão por zero, `lista[0]` e `.toFixed()` em nulo só aparecem
 * aqui — e aparecem na frente de quem está conhecendo o sistema.
 *
 * Não cria nada: só navega e lê. Some quando o cliente tiver dado.
 */
import puppeteer from "puppeteer-core";

const CHROME =
  process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const WEB = "http://127.0.0.1:3100";

const TELAS = [
  "/", "/produtos", "/produtos/novo", "/fornecedores",
  "/cadastros", "/fichas", "/fichas/nova", "/estoque", "/ajustes", "/producao",
  "/inventario", "/inventario/novo", "/compras", "/compras/nova",
  "/vendas", "/vendas/lancar", "/vendas/sem-vinculo", "/cmv",
  "/integracoes", "/lojas", "/usuarios", "/papeis", "/auditoria", "/empresa", "/ajuda",
];

const navegador = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--window-size=1440,1000"],
  defaultViewport: { width: 1440, height: 1000 },
  protocolTimeout: 60_000,
});
const p = await navegador.newPage();

const erros = [];
p.on("pageerror", (e) => erros.push(`JS: ${String(e).slice(0, 140)}`));
p.on("console", (m) => {
  if (m.type() === "error" && !/favicon|manifest/i.test(m.text())) {
    erros.push(`console: ${m.text().slice(0, 140)}`);
  }
});

await p.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
await p.type('input[type="email"]', "admin@botane.com.br");
await p.type('input[type="password"]', "botane123");
await Promise.all([
  p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}),
  p.click('button[type="submit"]'),
]);
await new Promise((r) => setTimeout(r, 1500));

let quebrou = 0;
for (const rota of TELAS) {
  erros.length = 0;
  try {
    await p.goto(WEB + rota, { waitUntil: "networkidle2", timeout: 30000 });
  } catch (e) {
    console.log(`  FALHA ${rota} — não carregou: ${String(e).slice(0, 60)}`);
    quebrou++;
    continue;
  }
  await new Promise((r) => setTimeout(r, 1400));
  const texto = await p.evaluate(() => document.body.innerText);
  const ruim = /Erro 5|Internal Server|Falha ao carregar|Application error|NaN|undefined/.test(
    texto,
  );
  const marca = ruim || erros.length ? "FALHA" : "  ok ";
  if (ruim || erros.length) quebrou++;
  const detalhe = ruim
    ? texto.match(/.{0,60}(Erro 5|Internal Server|Falha ao carregar|NaN|undefined).{0,40}/)?.[0]
    : erros[0] ?? "";
  console.log(`  ${marca} ${rota.padEnd(24)} ${String(detalhe).replace(/\s+/g, " ").slice(0, 95)}`);
}
console.log(`\n${TELAS.length - quebrou} de ${TELAS.length} telas limpas na base vazia`);
await navegador.close();
