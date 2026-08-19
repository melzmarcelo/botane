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

/**
 * Navega tolerando o frame trocar no meio do caminho.
 *
 * Com o service worker no ar, a navegação logo depois do login às vezes é
 * substituída por outra antes de terminar, e o puppeteer levanta
 * "detached Frame". Não é problema do sistema — quem usa não vê nada — mas
 * derruba o teste inteiro se não for tratado.
 */
async function irPara(pagina, url) {
  for (let tentativa = 0; tentativa < 3; tentativa++) {
    try {
      await pagina.goto(url, { waitUntil: "networkidle2" });
      return;
    } catch (e) {
      if (!/detached|Target closed|Navigating frame/i.test(String(e)) || tentativa === 2) throw e;
      await new Promise((r) => setTimeout(r, 800));
    }
  }
}

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
  const { dados: notasAntigas } = await api("GET", "/notas", null, token);
  for (const n of notasAntigas ?? []) {
    if ((n.chave_nfe ?? "").startsWith("35260812345678")) {
      if (n.status === "LANCADA") await api("POST", `/notas/${n.id}/estornar`, null, token);
      await api("DELETE", `/notas/${n.id}`, null, token);
    }
  }
  for (const c of ["CAF-500", "LEI-INT", "TOM-CX"]) {
    await api("DELETE", `/notas/vinculos/${c}`, null, token);
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

  await api("DELETE", "/notas/vinculos/CAF-500", null, token);

  console.log("8b. a nota que entra sem integração nenhuma");
  // A chave da NF-e é única: a marca da rodada entra nela para que a segunda
  // execução do teste importe de verdade, em vez de bater no de-duplicador.
  const marcaNota = String(Date.now()).slice(-6);
  const chaveNota = `42260899888877000166550010000088881${marcaNota}0000`.slice(0, 44);
  const caminhoXml = `${FOTOS}/_nota-exemplo.xml`;
  writeFileSync(
    caminhoXml,
    `<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
 <NFe><infNFe Id="NFe${chaveNota}" versao="4.00">
  <ide><nNF>8888${marcaNota}</nNF><serie>1</serie><mod>55</mod><dhEmi>2026-08-16T09:00:00-03:00</dhEmi></ide>
  <emit><CNPJ>99888877000166</CNPJ><xNome>Atacado do Vale ${marcaNota}</xNome></emit>
  <dest><CNPJ>11222333000181</CNPJ><xNome>Botane Deli e Cafe</xNome></dest>
  <det nItem="1"><prod><cProd>AZE-${marcaNota}</cProd><cEAN>SEM GTIN</cEAN>
   <xProd>AZEITE EXTRA VIRGEM 500ML</xProd><NCM>15091000</NCM><uCom>UN</uCom>
   <qCom>6.0000</qCom><vUnCom>32.0000</vUnCom><vProd>192.00</vProd><vFrete>12.00</vFrete>
  </prod><imposto><ICMS><ICMS00><vICMS>0.00</vICMS></ICMS00></ICMS></imposto></det>
  <total><ICMSTot><vProd>192.00</vProd><vFrete>12.00</vFrete><vNF>204.00</vNF></ICMSTot></total>
 </infNFe></NFe>
</nfeProc>`,
  );

  await p.goto(`${WEB}/compras`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1100));
  const entradaXmlTela = await p.$('input[type="file"]');
  checar("a tela de compras tem a porta do XML", !!entradaXmlTela);
  await entradaXmlTela.uploadFile(caminhoXml);
  await new Promise((r) => setTimeout(r, 2500));
  const textoXml = await p.evaluate(() => document.body.innerText);
  checar("o XML importa pela tela", /1 nota\(s\) importada\(s\)/i.test(textoXml),
    textoXml.slice(0, 160));
  checar("o arquivo aparece com o resultado", /Arquivos lidos/i.test(textoXml));
  checar("a nota abre sozinha com o item do XML",
    /AZEITE EXTRA VIRGEM/i.test(textoXml), textoXml.slice(0, 200));
  await foto(p, "29b-xml-importado");

  // O mesmo arquivo de novo: a chaveNota da NF-e é que impede a duplicação.
  await (await p.$('input[type="file"]')).uploadFile(caminhoXml);
  await new Promise((r) => setTimeout(r, 2200));
  const textoRepetido = await p.evaluate(() => document.body.innerText);
  checar("o mesmo XML não entra duas vezes",
    /repetida|já tinha sido importada/i.test(textoRepetido), textoRepetido.slice(0, 160));

  // Arquivo que não é nota: a recusa tem de explicar o que houve.
  writeFileSync(`${FOTOS}/_nao-e-nota.xml`, "<retEnviNFe><nRec>1</nRec></retEnviNFe>");
  await (await p.$('input[type="file"]')).uploadFile(`${FOTOS}/_nao-e-nota.xml`);
  await new Promise((r) => setTimeout(r, 2000));
  const textoRecusa = await p.evaluate(() => document.body.innerText);
  checar("arquivo que não é a nota é recusado com explicação",
    /recibo\/evento da nota/i.test(textoRecusa), textoRecusa.slice(0, 200));

  // Agora a digitação: a compra do mercado, que não tem XML nenhum.
  const { dados: produtosNota } = await api("GET", "/produtos", null, token);
  const insumoNota = produtosNota.find((x) => x.controla_estoque);
  await p.goto(`${WEB}/compras`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1100));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")].find((x) => x.textContent === "Digitar nota")?.click();
  });
  await new Promise((r) => setTimeout(r, 900));
  const seletoresNota = await p.$$("select");
  checar("o formulário de digitação abre", seletoresNota.length >= 3, seletoresNota.length);
  await seletoresNota[1].select(String(insumoNota.id));
  const numerosNota = await p.$$('input[inputmode="decimal"]');
  await numerosNota[0].type("2");
  await numerosNota[1].type("10");
  await new Promise((r) => setTimeout(r, 600));
  const textoPreviaNota = await p.evaluate(() => document.body.innerText);
  checar("a tela mostra o custo unitário antes de gravar",
    /R\$\s*10,00/.test(textoPreviaNota), textoPreviaNota.slice(-260));
  await foto(p, "29c-nota-digitada");

  await p.evaluate(() => {
    [...document.querySelectorAll("button")].find((x) => x.textContent === "Gravar nota")?.click();
  });
  await new Promise((r) => setTimeout(r, 2200));
  const textoGravadaNota = await p.evaluate(() => document.body.innerText);
  checar("a nota digitada grava e abre para conferência",
    /Nota registrada/i.test(textoGravadaNota), textoGravadaNota.slice(0, 160));
  checar("e já nasce pronta para lançar (sem pendência)",
    !/sem produto vinculado/i.test(textoGravadaNota), textoGravadaNota.slice(0, 200));

  // Limpeza: as duas notas do teste saem, para a próxima rodada começar limpa.
  const { dados: notasDoTesteXml } = await api("GET", "/notas?limite=30", null, token);
  for (const n of notasDoTesteXml ?? []) {
    if (n.chave_nfe === chaveNota || (n.origem === "MANUAL" && !n.numero)) {
      await api("DELETE", `/notas/${n.id}`, null, token);
    }
  }

  console.log("9. alertas e exportação");
  await p.goto(`${WEB}/alertas`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  const textoAlertas = await p.evaluate(() => document.body.innerText);
  checar("/alertas carrega",
    !/Erro 5|Não autenticado|Falha ao carregar/.test(textoAlertas), textoAlertas.slice(0, 90));
  checar("a tela lista pontos de atenção (ou diz que não há)",
    /ponto\(s\) de atenção|Nada pendente/i.test(textoAlertas), textoAlertas.slice(0, 140));
  await foto(p, "30-alertas");

  const { dados: listaAlertas } = await api("GET", "/alertas", null, token);
  checar("a API devolve alerta com ação e link",
    listaAlertas.length === 0 || (listaAlertas[0].acao && listaAlertas[0].href),
    listaAlertas[0]);

  // O resumo tem de aparecer no Início, que é a tela que o dono abre.
  await p.goto(`${WEB}/`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  const textoInicio = await p.evaluate(() => document.body.innerText);
  checar("o Início mostra o resumo de alertas",
    listaAlertas.length === 0 || /Precisa da sua atenção/i.test(textoInicio),
    textoInicio.slice(0, 160));

  // Botão de exportar presente nas telas que o oferecem.
  for (const [rota, nome] of [["/estoque", "estoque"], ["/cmv", "CMV"], ["/produtos", "produtos"]]) {
    await p.goto(WEB + rota, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 1100));
    const tem = await p.evaluate(() =>
      [...document.querySelectorAll("button")].some((b) => /Baixar planilha/i.test(b.textContent)));
    checar(`${nome} oferece baixar planilha`, tem);
  }
  await foto(p, "31-cmv-exportar");

  console.log("9a. esqueci minha senha, do pedido até entrar de novo");
  const marcaSenha = String(Date.now()).slice(-6);
  const emailSenha = `tela.senha.${marcaSenha}@botane.com.br`;
  const { dados: papeisSenha } = await api("GET", "/papeis", null, token);
  const { dados: criado } = await api("POST", "/usuarios", {
    nome: `Tela Senha ${marcaSenha}`, email: emailSenha, senha: "provisoria123",
    papeis: [{ id_papel: papeisSenha.find((x) => x.nome === "Cozinha").id }],
  }, token);

  // O pedido público: a tela nunca conta se o e-mail existe.
  await p.evaluate(() => localStorage.clear());
  await irPara(p, `${WEB}/login`);
  const temLink = await p.evaluate(() =>
    [...document.querySelectorAll("a")].some((a) => /esqueci minha senha/i.test(a.textContent)));
  checar("a entrada oferece 'esqueci minha senha'", temLink);

  await irPara(p, `${WEB}/esqueci-senha`);
  await p.type('input[type="email"]', `nao.existe.${marcaSenha}@botane.com.br`);
  await p.click('button[type="submit"]');
  await new Promise((r) => setTimeout(r, 1200));
  const textoInventado = await p.evaluate(() => document.body.innerText);
  checar("e-mail que não existe recebe a resposta neutra",
    /se este e-mail estiver cadastrado/i.test(textoInventado), textoInventado.slice(0, 140));
  checar("e a tela NÃO diz que o e-mail não existe",
    !/não encontrad|não existe|não cadastrado/i.test(textoInventado), textoInventado.slice(0, 140));
  await foto(p, "32-esqueci-senha");

  await irPara(p, `${WEB}/esqueci-senha`);
  await p.type('input[type="email"]', emailSenha);
  await p.click('button[type="submit"]');
  await new Promise((r) => setTimeout(r, 1200));
  const textoReal = await p.evaluate(() => document.body.innerText);
  checar("e-mail cadastrado recebe exatamente a mesma resposta",
    /se este e-mail estiver cadastrado/i.test(textoReal));

  // Link vencido/inventado: a tela recusa antes de pedir a senha.
  await irPara(p, `${WEB}/redefinir-senha?token=isto-nao-vale-nada`);
  await new Promise((r) => setTimeout(r, 1200));
  const textoRuim = await p.evaluate(() => document.body.innerText);
  checar("link inválido é recusado antes do formulário",
    /não vale mais/i.test(textoRuim), textoRuim.slice(0, 140));
  checar("e o formulário de senha nem aparece",
    (await p.$$('input[type="password"]')).length === 0);

  // O administrador gera o link pela tela de Usuários.
  await entrar(p, ADMIN);
  await irPara(p, `${WEB}/usuarios`);
  await new Promise((r) => setTimeout(r, 1200));
  const clicou = await p.evaluate((nome) => {
    const linha = [...document.querySelectorAll("tr")].find((t) => t.innerText.includes(nome));
    const b = linha && [...linha.querySelectorAll("button")]
      .find((x) => /esqueceu a senha/i.test(x.textContent));
    if (!b) return false;
    b.click();
    return true;
  }, `Tela Senha ${marcaSenha}`);
  checar("a tela de usuários oferece gerar o link", clicou);
  await new Promise((r) => setTimeout(r, 1500));
  const textoAdmin = await p.evaluate(() => document.body.innerText);
  checar("o link aparece para o administrador copiar",
    /redefinir-senha\?token=/.test(textoAdmin), textoAdmin.slice(0, 200));
  await foto(p, "33-link-admin");

  const linkGerado = (textoAdmin.match(/https?:\/\/\S*redefinir-senha\?token=\S+/) ?? [])[0];
  checar("e o link está completo", !!linkGerado, linkGerado);

  // A pessoa abre o link e escolhe a senha nova.
  await p.evaluate(() => localStorage.clear());
  await irPara(p, linkGerado);
  await new Promise((r) => setTimeout(r, 1400));
  const textoForm = await p.evaluate(() => document.body.innerText);
  checar("o link abre a tela com o nome de quem é",
    /Olá, Tela/i.test(textoForm), textoForm.slice(0, 160));
  const campos = await p.$$('input[type="password"]');
  checar("pede a senha duas vezes", campos.length === 2, campos.length);
  await campos[0].type("senhanova12345");
  await campos[1].type("senhanova-diferente");
  await p.click('button[type="submit"]');
  await new Promise((r) => setTimeout(r, 900));
  checar("senhas diferentes são recusadas na tela",
    /precisam ser iguais/i.test(await p.evaluate(() => document.body.innerText)));

  const campos2 = await p.$$('input[type="password"]');
  await campos2[1].click({ clickCount: 3 });
  await p.keyboard.down("Control");
  await p.keyboard.press("KeyA");
  await p.keyboard.up("Control");
  await campos2[1].type("senhanova12345");
  await foto(p, "34-redefinir-senha");
  await p.click('button[type="submit"]');
  await new Promise((r) => setTimeout(r, 2000));
  const textoPronto = await p.evaluate(() => document.body.innerText);
  checar("a senha é trocada pela tela", /senha alterada/i.test(textoPronto),
    textoPronto.slice(0, 160));
  checar("e a tela avisa que as sessões caíram",
    /sessões abertas foram encerradas/i.test(textoPronto), textoPronto.slice(0, 200));

  await entrar(p, { email: emailSenha, senha: "senhanova12345" });
  checar("a pessoa entra com a senha nova", !p.url().includes("/login"), p.url());

  await api("DELETE", `/usuarios/${criado.id}`, null, token);
  await entrar(p, ADMIN);

  console.log("9b. instalável no celular (PWA)");
  await p.goto(`${WEB}/`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1500));

  const manifesto = await p.evaluate(async () => {
    const link = document.querySelector('link[rel="manifest"]');
    if (!link) return null;
    const r = await fetch(link.getAttribute("href"));
    return r.ok ? r.json() : null;
  });
  checar("a página aponta para o manifesto", !!manifesto);
  checar("o manifesto abre em tela cheia", manifesto?.display === "standalone", manifesto?.display);
  checar("tem o nome curto que cabe embaixo do ícone",
    manifesto?.short_name === "Botané", manifesto?.short_name);
  // Sem os dois tamanhos o Chrome não oferece instalar; sem o maskable o
  // Android corta o desenho na forma do aparelho.
  const tamanhos = (manifesto?.icons ?? []).map((i) => `${i.sizes}:${i.purpose ?? ""}`);
  checar("traz ícone de 192 e de 512",
    tamanhos.some((t) => t.startsWith("192x192")) && tamanhos.some((t) => t.startsWith("512x512")),
    tamanhos);
  checar("traz o ícone recortável do Android",
    tamanhos.some((t) => t.includes("maskable")), tamanhos);

  const icones = await p.evaluate(async (lista) => {
    const r = await Promise.all(lista.map((u) => fetch(u).then((x) => [u, x.status, x.headers.get("content-type")])));
    return r;
  }, ["/icone-192.png", "/icone-512.png", "/icone-maskable-512.png", "/apple-touch-icon.png"]);
  checar("todos os arquivos de ícone existem de verdade",
    icones.every(([, status, tipo]) => status === 200 && tipo?.includes("image/png")), icones);

  // O nome antigo do meta é o que faz o iPhone abrir sem barra de endereço.
  const metaApple = await p.evaluate(() =>
    document.querySelector('meta[name="apple-mobile-web-app-capable"]')?.content);
  checar("declara o meta que o iPhone antigo entende", metaApple === "yes", metaApple);
  const iconeApple = await p.evaluate(() =>
    document.querySelector('link[rel="apple-touch-icon"]')?.getAttribute("href"));
  checar("aponta o ícone do iPhone", !!iconeApple, iconeApple);

  const registrou = await p.evaluate(async () => {
    const r = await navigator.serviceWorker.getRegistration();
    return r ? (r.active || r.installing || r.waiting)?.scriptURL ?? null : null;
  });
  checar("o service worker se registra sozinho", !!registrou, registrou);
  checar("e sabe que está em desenvolvimento (não cacheia estático)",
    (registrou ?? "").includes("dev=1"), registrou);

  // A regra que não pode afrouxar: nada da API guardado no cache do navegador.
  const cacheado = await p.evaluate(async () => {
    const nomes = await caches.keys();
    const urls = [];
    for (const nome of nomes) {
      const c = await caches.open(nome);
      urls.push(...(await c.keys()).map((r) => r.url));
    }
    return urls;
  });
  checar("nenhuma resposta da API foi para o cache",
    !cacheado.some((u) => u.includes(":9200")), cacheado.slice(0, 5));
  checar("mas a página de sem-conexão está guardada",
    cacheado.some((u) => u.endsWith("/offline")), cacheado);

  await p.goto(`${WEB}/offline`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 700));
  const textoOffline = await p.evaluate(() => document.body.innerText);
  checar("a página de sem-conexão diz o que fazer",
    /câmara fria|sinal/i.test(textoOffline), textoOffline.slice(0, 120));
  await foto(p, "31-offline");

  console.log("10. celular (390 x 844)");
  const c = await navegador.newPage();
  await c.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });
  await c.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
  await c.screenshot({ path: `${FOTOS}/m1-login.png`, fullPage: true });
  await entrar(c, ADMIN);
  await irPara(c, WEB + "/");
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

  console.log("11. logo da empresa");
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
