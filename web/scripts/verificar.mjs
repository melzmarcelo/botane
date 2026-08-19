/**
 * Verificação de ponta a ponta da etapa 1, no Chrome de verdade.
 *
 *   node scripts/verificar.mjs            (API na 9200 e web na 3100 de pé)
 *
 * Faz login como admin, passa pelas telas, tira foto de cada uma, e depois
 * entra como um usuário de Cozinha para conferir que o menu de administração
 * nem aparece — e que a rota, chamada na unha, é barrada pelo servidor.
 */

import puppeteer from "puppeteer-core";
import { mkdirSync, writeFileSync } from "node:fs";

const CHROME =
  process.env.CHROME_PATH ?? "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const WEB = "http://127.0.0.1:3100";
const API = "http://127.0.0.1:9200";
const FOTOS = "scripts/_fotos";

const ADMIN = { email: "admin@botane.com.br", senha: "botane123" };
const COZINHA = { email: "cozinha.teste@botane.com.br", senha: "cozinha12345" };

let ok = 0;
const falhas = [];
const checar = (nome, condicao, extra = "") => {
  if (condicao) {
    ok++;
    console.log(`  ok   ${nome}`);
  } else {
    falhas.push(nome);
    console.log(`  FALHA ${nome} ${extra}`);
  }
};

async function api(metodo, caminho, corpo, token) {
  const r = await fetch(API + caminho, {
    method: metodo,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  const texto = await r.text();
  return { status: r.status, dados: texto ? JSON.parse(texto) : null };
}

async function entrar(pagina, quem) {
  await pagina.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
  await pagina.type('input[type="email"]', quem.email);
  await pagina.type('input[type="password"]', quem.senha);
  await Promise.all([
    pagina.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}),
    pagina.click('button[type="submit"]'),
  ]);
  await new Promise((r) => setTimeout(r, 1200));
}

const foto = (pagina, nome) => pagina.screenshot({ path: `${FOTOS}/${nome}.png`, fullPage: true });

// ---- prepara um usuário de Cozinha, via API ----
const login = await api("POST", "/auth/login", ADMIN);
if (login.status !== 200) {
  console.error("API não respondeu ao login do admin:", login.status, login.dados);
  process.exit(1);
}
const token = login.dados.access_token;
const papeis = (await api("GET", "/papeis", null, token)).dados;
const idCozinha = papeis.find((p) => p.nome === "Cozinha").id;
const usuarios = (await api("GET", "/usuarios?incluir_inativos=true", null, token)).dados;
const jaExiste = usuarios.find((u) => u.email === COZINHA.email);
if (jaExiste) {
  await api("PUT", `/usuarios/${jaExiste.id}`,
    { ativo: true, senha: COZINHA.senha, papeis: [{ id_papel: idCozinha }] }, token);
} else {
  await api("POST", "/usuarios",
    { nome: "Teste Cozinha", email: COZINHA.email, senha: COZINHA.senha,
      papeis: [{ id_papel: idCozinha }] }, token);
}

mkdirSync(FOTOS, { recursive: true });
const navegador = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  args: ["--no-sandbox", "--window-size=1440,1000"],
  defaultViewport: { width: 1440, height: 1000 },
});

try {
  const p = await navegador.newPage();
  // O 403 da fase 3 é o comportamento esperado (servidor barrando a Cozinha);
  // só interessa erro fora disso.
  let coletando = true;
  const erros = [];
  const anotar = (t) => {
    if (coletando && !/favicon|hmr|_next\/static/.test(t)) erros.push(t);
  };
  p.on("pageerror", (e) => anotar(String(e)));
  p.on("console", (m) => m.type() === "error" && anotar(m.text()));

  console.log("1. login do administrador");
  await p.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
  await foto(p, "01-login");
  await entrar(p, ADMIN);
  const url = p.url();
  // Depende de o admin já ter trocado a senha ou não — o que importa é ter entrado.
  checar("admin entra no app", !url.includes("/login"), url);
  await p.goto(`${WEB}/trocar-senha`, { waitUntil: "networkidle2" });
  await foto(p, "02-trocar-senha");

  console.log("2. telas de administração");
  for (const [rota, nome] of [
    ["/", "03-inicio"],
    ["/empresa", "04-empresa"],
    ["/lojas", "05-lojas"],
    ["/usuarios", "06-usuarios"],
    ["/papeis", "07-papeis"],
    ["/auditoria", "08-auditoria"],
  ]) {
    await p.goto(WEB + rota, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 900));
    const texto = await p.evaluate(() => document.body.innerText);
    checar(`${rota} carrega sem erro visível`, !/Erro 5|Não autenticado|Failed to fetch/.test(texto),
      texto.slice(0, 90));
    await foto(p, nome);
  }

  const menu = await p.evaluate(() => document.querySelector("aside")?.innerText ?? "");
  checar("menu do admin traz Empresa", menu.includes("Empresa"));
  checar("menu do admin traz Papéis", menu.includes("Papéis"));
  checar("menu do admin traz Auditoria", menu.includes("Auditoria"));

  console.log("3. usuário de Cozinha");
  coletando = false;
  await p.evaluate(() => localStorage.clear());
  await entrar(p, COZINHA);
  await new Promise((r) => setTimeout(r, 800));
  // Este usuário nasceu agora pela API: senha definida por outra pessoa
  // obriga a troca no primeiro acesso.
  checar("usuário novo cai na troca de senha obrigatória",
    p.url().includes("/trocar-senha"), p.url());
  await p.goto(WEB + "/", { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 700));
  await foto(p, "09-cozinha-inicio");
  const menuCozinha = await p.evaluate(() => document.querySelector("aside")?.innerText ?? "");
  checar("cozinha NÃO vê Empresa no menu", !menuCozinha.includes("Empresa"), menuCozinha);
  checar("cozinha NÃO vê Usuários no menu", !menuCozinha.includes("Usuários"));
  checar("cozinha NÃO vê Auditoria no menu", !menuCozinha.includes("Auditoria"));

  // Digitar a rota na barra de endereço não abre porta nenhuma: quem barra é a API.
  await p.goto(`${WEB}/usuarios`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 900));
  const textoBarrado = await p.evaluate(() => document.body.innerText);
  checar("cozinha na rota /usuarios recebe recusa do servidor",
    /Sem permissão/i.test(textoBarrado), textoBarrado.slice(0, 90));
  await foto(p, "10-cozinha-barrada");

  checar("nenhum erro de JavaScript nas telas de admin", erros.length === 0,
    erros.slice(0, 2).join(" | "));

  console.log("4. cadastros (etapa 2)");
  // A fase 3 deixou a sessão da Cozinha no localStorage (que é do domínio, não
  // da aba): sem voltar como admin, as telas viriam em modo leitura.
  await entrar(p, ADMIN);
  for (const [rota, nome] of [
    ["/produtos", "12-produtos"],
    ["/fornecedores", "13-fornecedores"],
    ["/cadastros", "14-tabelas"],
  ]) {
    await p.goto(WEB + rota, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 1000));
    const texto = await p.evaluate(() => document.body.innerText);
    checar(`${rota} carrega`, !/Erro 5|Não autenticado|Falha ao carregar/.test(texto),
      texto.slice(0, 90));
    await foto(p, nome);
  }

  // Cadastro de um produto pela tela, do jeito que o cliente faria.
  await p.goto(`${WEB}/produtos/novo`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  const nomeProduto = `Teste tela ${Date.now().toString().slice(-5)}`;
  await p.type('input[required]', nomeProduto);
  await p.select("select", "INSUMO");
  const selects = await p.$$("select");
  // ordem dos selects: tipo, categoria, setor, um_estoque, um_compra
  await selects[3].select("KG");
  await Promise.all([
    p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}),
    p.click('button[type="submit"]'),
  ]);
  await new Promise((r) => setTimeout(r, 1500));
  const criou = /\/produtos\/\d+/.test(p.url());
  checar("cadastra produto pela tela", criou, p.url());
  await foto(p, "15-produto");

  await p.goto(`${WEB}/produtos?busca=Teste tela`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  const naLista = await p.evaluate((n) => document.body.innerText.includes(n), nomeProduto);
  checar("produto aparece na lista", naLista);

  // Limpa: desativa o produto criado pelo teste.
  if (criou) {
    const idProduto = p.url().match(/produtos\/(\d+)/)?.[1];
    await api("DELETE", `/produtos/${idProduto}`, null, token);
  }

  console.log("5. fichas técnicas (etapa 3)");
  // Cenário montado pela API: insumo com preço + produto produzido.
  const marca = Date.now().toString().slice(-5);
  const { dados: forn } = await api("POST", "/fornecedores",
    { nome: `Tela Fornecedor ${marca}` }, token);
  const { dados: insumo } = await api("POST", "/produtos", {
    nome: `Tela farinha ${marca}`, tipo: "INSUMO", um_estoque: "KG",
    fornecedores: [{ id_fornecedor: forn.id, ultimo_preco: 8, fator: 1, preferencial: true }],
  }, token);
  const { dados: bolo } = await api("POST", "/produtos",
    { nome: `Tela bolo ${marca}`, tipo: "PRODUZIDO", um_estoque: "UN" }, token);

  await p.goto(`${WEB}/fichas/nova`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1300));
  const camposFicha = await p.$$("select");
  await camposFicha[0].select(String(bolo.id));      // produto
  await p.$$eval("input[type=number]", (els) => {
    els[0].value = "";
  });
  // Ordem dos campos numéricos: 0 rendimento, 1 porções, 2 bruta, 3 líquida, 4 tempo.
  const numeros = await p.$$("input[type=number]");
  // clickCount:3 não seleciona o conteúdo de input[type=number] no Chrome —
  // sem o ctrl+A o valor novo entra colado no que já estava (1 + 8 = 18).
  const trocar = async (campo, valor) => {
    await campo.click();
    await p.keyboard.down("Control");
    await p.keyboard.press("KeyA");
    await p.keyboard.up("Control");
    await campo.type(valor);
  };
  await trocar(numeros[0], "2");
  await trocar(numeros[1], "8");
  // linha 1: 500 g de farinha
  const selectsAgora = await p.$$("select");
  await selectsAgora[2].select(`ins:${insumo.id}`);  // 0 produto, 1 rendimento_um, 2 item
  await numeros[2].type("500");
  const selectsUm = await p.$$("select");
  await selectsUm[3].select("G");                    // unidade do item
  await Promise.all([
    p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}),
    p.click('button[type="submit"]'),
  ]);
  await new Promise((r) => setTimeout(r, 1800));
  const criouFicha = /\/fichas\/\d+/.test(p.url());
  checar("cria ficha pela tela", criouFicha, p.url());
  await foto(p, "16-ficha");

  if (criouFicha) {
    const idFicha = p.url().match(/fichas\/(\d+)/)?.[1];
    // 500 g × R$ 8,00/kg = R$ 4,00 ÷ 8 porções = R$ 0,50
    const { dados: f } = await api("GET", `/fichas/${idFicha}`, null, token);
    checar("custo da ficha calculado na tela", Math.abs(Number(f.custo_total) - 4) < 0.01,
      f.custo_total);
    checar("custo por porção calculado", Math.abs(Number(f.custo_por_porcao) - 0.5) < 0.01,
      f.custo_por_porcao);
    const textoFicha = await p.evaluate(() => document.body.innerText);
    checar("a tela mostra o custo por porção", /0,50/.test(textoFicha),
      textoFicha.slice(0, 60));

    // A cozinha vê a receita e não vê dinheiro — na tela, não só na API.
    await p.evaluate(() => localStorage.clear());
    await entrar(p, COZINHA);
    await p.goto(`${WEB}/fichas/${idFicha}`, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 1300));
    const textoCozinha = await p.evaluate(() => document.body.innerText);
    checar("cozinha vê a receita", /Tela farinha/.test(textoCozinha), textoCozinha.slice(0, 80));
    checar("cozinha NÃO vê custo na tela", !/R\$/.test(textoCozinha),
      textoCozinha.match(/.{0,30}R\$.{0,20}/)?.[0]);
    await foto(p, "17-ficha-cozinha");
    await entrar(p, ADMIN);

    await api("DELETE", `/fichas/${idFicha}`, null, token);
  }
  await api("DELETE", `/produtos/${insumo.id}`, null, token);
  await api("DELETE", `/produtos/${bolo.id}`, null, token);
  await api("DELETE", `/fornecedores/${forn.id}`, null, token);

  console.log("6. estoque (etapa 4)");
  const m4 = Date.now().toString().slice(-5);
  const { dados: insumo4 } = await api("POST", "/produtos",
    { nome: `Est tela ${m4}`, tipo: "INSUMO", um_estoque: "KG" }, token);

  for (const [rota, nome] of [
    ["/estoque", "18-estoque"],
    ["/producao", "19-producao"],
    ["/inventario", "20-inventario"],
  ]) {
    await p.goto(WEB + rota, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 1100));
    const texto = await p.evaluate(() => document.body.innerText);
    checar(`${rota} carrega`, !/Erro 5|Não autenticado|Falha ao carregar/.test(texto),
      texto.slice(0, 90));
    await foto(p, nome);
  }

  // Entrada pela tela: 10 kg a R$ 20,00.
  await p.goto(`${WEB}/estoque`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1100));
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent === "Entrada");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 600));
  const selEstoque = await p.$$("select");
  await selEstoque[0].select(String(insumo4.id));
  const numEstoque = await p.$$("input[type=number]");
  await numEstoque[0].type("10");
  await numEstoque[1].type("20");
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent === "Lançar");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 1600));
  const textoEstoque = await p.evaluate(() => document.body.innerText);
  checar("entrada pela tela mostra o novo custo médio", /custo médio: R\$\s?20,00/i.test(textoEstoque),
    textoEstoque.match(/.{0,60}custo médio.{0,20}/i)?.[0]);
  await foto(p, "21-estoque-entrada");

  const { dados: saldos } = await api("GET", `/estoque/saldos?busca=${m4}`, null, token);
  checar("saldo gravado pela tela", saldos.length === 1 && Number(saldos[0].quantidade) === 10,
    saldos);
  checar("valor em estoque = 200,00", saldos[0] && Number(saldos[0].valor) === 200,
    saldos[0]?.valor);

  await api("DELETE", `/produtos/${insumo4.id}`, null, token);

  console.log("7. CMV (etapa 6)");
  const m6 = Date.now().toString().slice(-5);
  const hoje6 = new Date().toISOString().slice(0, 10);
  // Cenário: insumo comprado, ficha homologada, produção e venda pela planilha.
  const { dados: ins6 } = await api("POST", "/produtos",
    { nome: `Cmv tela insumo ${m6}`, tipo: "INSUMO", um_estoque: "KG" }, token);
  const { dados: prod6 } = await api("POST", "/produtos",
    { nome: `Cmv tela prato ${m6}`, tipo: "PRODUZIDO", um_estoque: "UN" }, token);
  await api("POST", "/estoque/entradas",
    { id_produto: ins6.id, quantidade: 20, custo_unitario: 10 }, token);
  const { dados: fic6 } = await api("POST", "/fichas", {
    id_produto: prod6.id, rendimento_qtd: 1, rendimento_um: "UN", porcoes: 1,
    itens: [{ id_insumo: ins6.id, qtd_bruta: 0.5, um: "KG" }],
  }, token);
  await api("POST", `/fichas/${fic6.id}/homologar`, null, token);
  await api("POST", "/estoque/producoes",
    { id_produto: prod6.id, quantidade: 10 }, token);

  for (const [rota, nome] of [["/vendas", "22-vendas"], ["/cmv", "23-cmv"]]) {
    await p.goto(WEB + rota, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 1200));
    const texto = await p.evaluate(() => document.body.innerText);
    checar(`${rota} carrega`, !/Erro 5|Não autenticado|Falha ao carregar/.test(texto),
      texto.slice(0, 90));
    await foto(p, nome);
  }

  // Importa a venda colando a planilha, do jeito que o cliente faria.
  await p.goto(`${WEB}/vendas`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  const doc6 = `TELA-${m6}`;
  await p.evaluate((d) => {
    const campos = [...document.querySelectorAll("input")];
    const alvo = campos.find((c) => c.placeholder?.includes("fechamento-"));
    if (alvo) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(alvo, d);
      alvo.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }, doc6);
  const area = await p.$("textarea");
  await area.type(`${prod6.codigo}; Prato de teste; 10; 30,00`);
  await new Promise((r) => setTimeout(r, 400));
  const textoPrevia = await p.evaluate(() => document.body.innerText);
  checar("a tela reconhece a linha colada", /1 linha\(s\) reconhecida/.test(textoPrevia),
    textoPrevia.match(/.{0,40}reconhecid.{0,30}/)?.[0]);
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent === "Importar");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 1800));
  const textoImport = await p.evaluate(() => document.body.innerText);
  checar("importa a venda pela tela", /1 venda\(s\), 1 item/.test(textoImport),
    textoImport.slice(0, 120));
  await foto(p, "24-vendas-importada");

  // A conta: 10 pratos a 5,00 de custo = 50,00 de CMV teórico; receita 300,00.
  const { dados: ap } = await api("GET", `/cmv/apuracao?inicio=${hoje6}&fim=${hoje6}`, null, token);
  checar("CMV teórico entra na apuração", Number(ap.cmv_teorico) >= 50,
    ap.cmv_teorico);
  checar("receita entra na apuração", Number(ap.receita) >= 300, ap.receita);

  await p.goto(`${WEB}/cmv?`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1500));
  const textoCmv = await p.evaluate(() => document.body.innerText);
  checar("painel mostra CMV real e teórico",
    /CMV REAL/i.test(textoCmv) && /CMV TEÓRICO/i.test(textoCmv), textoCmv.slice(0, 80));
  checar("painel mostra a variância", /VARIÂNCIA/i.test(textoCmv));
  checar("painel mostra food cost", /FOOD COST/i.test(textoCmv));
  checar("curva ABC aparece com classe", /Curva ABC/i.test(textoCmv));
  await foto(p, "25-cmv-painel");

  // Limpeza do cenário.
  const { dados: vendas6 } = await api("GET", `/vendas?inicio=${hoje6}&fim=${hoje6}`, null, token);
  for (const v of vendas6.filter((x) => x.documento === doc6)) {
    await api("DELETE", `/vendas/${v.id}`, null, token);
  }
  await api("DELETE", `/fichas/${fic6.id}`, null, token);
  await api("DELETE", `/produtos/${ins6.id}`, null, token);
  await api("DELETE", `/produtos/${prod6.id}`, null, token);

  console.log("8. Omie (etapa 5)");
  // Limpa o que rodadas anteriores importaram das fixtures.
  const { dados: notasAntigas } = await api("GET", "/omie/notas", null, token);
  for (const n of notasAntigas ?? []) {
    if ((n.chave_nfe ?? "").startsWith("35260812345678")) {
      if (n.status === "LANCADA") await api("POST", `/omie/notas/${n.id}/estornar`, null, token);
      await api("DELETE", `/omie/notas/${n.id}`, null, token);
    }
  }
  for (const c of ["CAF-500", "LEI-INT", "TOM-CX"]) {
    await api("DELETE", `/omie/vinculos/${c}`, null, token);
  }

  for (const [rota, nome] of [["/integracoes", "26-integracoes"], ["/compras", "27-compras"]]) {
    await p.goto(WEB + rota, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 1200));
    const texto = await p.evaluate(() => document.body.innerText);
    checar(`${rota} carrega`, !/Erro 5|Não autenticado|Falha ao carregar/.test(texto),
      texto.slice(0, 90));
    await foto(p, nome);
  }

  // O texto tem de vir da tela de integrações, não da última do laço.
  await p.goto(`${WEB}/integracoes`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  const textoInt = await p.evaluate(() => document.body.innerText);
  checar("a tela avisa que está em modo simulado", /modo simulado/i.test(textoInt),
    textoInt.slice(0, 120));
  checar("a credencial aparece mascarada",
    /•/.test(textoInt) || /não configurada/i.test(textoInt), textoInt.slice(0, 200));

  // Sincroniza pela tela de compras e concilia um item.
  await p.goto(`${WEB}/compras`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1100));
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      x.textContent === "Buscar no Omie");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 2500));
  const textoCompras = await p.evaluate(() => document.body.innerText);
  checar("sincroniza pela tela", /nota\(s\) nova\(s\)/i.test(textoCompras),
    textoCompras.slice(0, 120));
  checar("a nota chega com pendência de de-para", /pendente/i.test(textoCompras));
  await foto(p, "28-compras-sincronizado");

  // Abre a primeira nota e confere que o lançamento está barrado.
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      x.textContent.includes("NF 4812"));
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 1200));
  const textoNota = await p.evaluate(() => document.body.innerText);
  checar("a nota abre com os itens", /CAFE EM GRAO/i.test(textoNota), textoNota.slice(0, 100));
  checar("a tela explica por que não dá para lançar",
    /sem produto vinculado/i.test(textoNota), textoNota.slice(0, 150));
  const lancarDesabilitado = await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      x.textContent === "Lançar no estoque");
    return b ? b.disabled : null;
  });
  checar("o botão de lançar fica desabilitado", lancarDesabilitado === true, lancarDesabilitado);
  await foto(p, "29-conciliacao");

  await api("DELETE", "/omie/vinculos/CAF-500", null, token);

  console.log("9. celular (390 x 844)");
  const c = await navegador.newPage();
  await c.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  await c.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
  await c.screenshot({ path: `${FOTOS}/m1-login.png`, fullPage: true });
  await entrar(c, ADMIN);
  await c.goto(WEB + "/", { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 900));

  const larguraCorpo = await c.evaluate(() => ({
    scroll: document.documentElement.scrollWidth,
    janela: window.innerWidth,
  }));
  checar("não há rolagem horizontal no celular",
    larguraCorpo.scroll <= larguraCorpo.janela + 1, JSON.stringify(larguraCorpo));

  const gavetaEscondida = await c.evaluate(() => {
    const a = document.querySelector("aside");
    return a ? a.getBoundingClientRect().right <= 1 : false;
  });
  checar("menu começa fechado no celular", gavetaEscondida);
  await c.screenshot({ path: `${FOTOS}/m2-inicio.png`, fullPage: true });

  await c.click('button[aria-label="Abrir menu"]');
  await new Promise((r) => setTimeout(r, 500));
  const gavetaAberta = await c.evaluate(() => {
    const a = document.querySelector("aside");
    return a ? a.getBoundingClientRect().left >= -1 : false;
  });
  checar("hambúrguer abre a gaveta", gavetaAberta);
  await c.screenshot({ path: `${FOTOS}/m3-menu.png` });

  // Navegar fecha a gaveta sozinho.
  await c.evaluate(() => {
    const l = [...document.querySelectorAll("aside a")].find((x) => x.textContent === "Empresa");
    l?.click();
  });
  await new Promise((r) => setTimeout(r, 1200));
  const fechouSozinha = await c.evaluate(() => {
    const a = document.querySelector("aside");
    return a ? a.getBoundingClientRect().right <= 1 : false;
  });
  checar("gaveta fecha ao navegar", fechouSozinha);
  await c.screenshot({ path: `${FOTOS}/m4-empresa.png`, fullPage: true });

  const semEstouro = await c.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth + 1,
  );
  checar("formulário da empresa cabe na tela do celular", semEstouro);

  console.log("10. logo da empresa");
  // PNG 1x1 de verdade, para o servidor validar a imagem e não só o content-type
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    "base64",
  );
  writeFileSync(`${FOTOS}/_logo-teste.png`, png);

  await p.goto(`${WEB}/empresa`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 900));
  const entradaArquivo = await p.$('input[type="file"]');
  checar("tela da empresa tem seletor de imagem", !!entradaArquivo);
  await entradaArquivo.uploadFile(`${FOTOS}/_logo-teste.png`);
  await new Promise((r) => setTimeout(r, 1800));
  const temImagem = await p.evaluate(
    () => !!document.querySelector('img[alt="Logo da empresa"]'),
  );
  checar("logo aparece depois do envio", temImagem);
  await foto(p, "11-logo");

  // Um .txt disfarçado precisa ser recusado pelo servidor.
  writeFileSync(`${FOTOS}/_falso.png`, "isto nao e uma imagem");
  await (await p.$('input[type="file"]')).uploadFile(`${FOTOS}/_falso.png`);
  await new Promise((r) => setTimeout(r, 1500));
  const textoErro = await p.evaluate(() => document.body.innerText);
  checar("arquivo que não é imagem é recusado",
    /não aceito|não é uma imagem|Formato/i.test(textoErro), textoErro.slice(0, 80));

  const logoNoMenu = await p.evaluate(() => !!document.querySelector("aside img"));
  checar("logo aparece no topo do menu", logoNoMenu);

  // Tira a logo de teste: a real é a que o cliente subir.
  await api("DELETE", "/empresa/logo", null, token);
} finally {
  await navegador.close();
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((f) => console.log(`  - ${f}`));
console.log(`fotos em ${FOTOS}`);
process.exit(falhas.length ? 1 : 0);
