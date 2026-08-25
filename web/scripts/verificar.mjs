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
/**
 * O dia de HOJE aqui, não em Londres.
 *
 * ⚠️ `toISOString()` devolve UTC: rodando às 22h35 de Brasília ele já diz o dia
 * seguinte. Uma venda datada assim cai fora do mês corrente, e o relatório de
 * movimentação — que soma o período — deixava de fechar com o saldo final. O
 * teste acusava o sistema de um erro que era dele. É a mesma armadilha que o
 * banco resolve com a sessão em America/Sao_Paulo.
 */
const diaLocal = (somaDias = 0) =>
  new Date(Date.now() + somaDias * 86400000).toLocaleDateString("sv-SE");

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
    // Objeto imprimia "[object Object]" e a falha vinha sem a evidência —
    // justamente quando ela é mais necessária.
    const detalhe =
      extra && typeof extra === "object" ? JSON.stringify(extra) : String(extra ?? "");
    console.log(`  FALHA ${nome} ${detalhe}`);
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

/**
 * O local principal, criando um se a base não tiver nenhum.
 *
 * Base recém-instalada não tem local de estoque, e sem local nenhum movimento
 * entra. Supor que existe fazia a suíte quebrar num ponto que não tem nada a
 * ver com o que ela testa.
 */
async function garantirLocal() {
  const { dados } = await api("GET", "/locais", null, token);
  if (dados?.length) return (dados.find((l) => l.principal) ?? dados[0]).id;
  const { dados: novo } = await api(
    "POST", "/locais", { nome: "Estoque seco", tipo: "SECO", principal: true }, token);
  return novo.id;
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

/** Tudo o que está à vista, inclusive o que mora dentro de campo.
 *
 * `innerText` não enxerga o valor de um `<input>`. Depois que a escolha de
 * cadastro virou campo de busca, "o nome do insumo aparece na tela" passou a
 * ser falso pelo `innerText` e verdadeiro para quem olha o monitor.
 */
async function textoVisivel(pagina) {
  return pagina.evaluate(() => {
    const campos = [...document.querySelectorAll("input, textarea")]
      .map((c) => c.value)
      .filter(Boolean)
      .join(" | ");
    return document.body.innerText + " | " + campos;
  });
}

/** Espera um texto aparecer na tela, em vez de dormir um tempo fixo.
 *
 * A lista de produtos carrega por XHR depois do `networkidle2`, com debounce na
 * busca: um `setTimeout` de 1,2 s acertava quase sempre e falhava de vez em
 * quando — e teste que falha "às vezes" é pior que teste que não existe,
 * porque ensina a ignorar o vermelho.
 */
async function esperarTexto(pagina, texto, limite = 6000) {
  const ate = Date.now() + limite;
  while (Date.now() < ate) {
    const tem = (await textoVisivel(pagina)).includes(texto);
    if (tem) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
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

// A suíte precisa de um local de estoque para existir: sem ele o formulário de
// entrada não tem o que selecionar e metade das fases cai. Garantir uma vez, no
// começo, vale para todas — inclusive numa instalação virgem.
await garantirLocal();

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

  // O grupo da tela aberta começa expandido — mas é só o padrão. Quem quer o
  // menu enxuto tem de conseguir recolhê-lo mesmo estando dentro dele.
  await irPara(p, `${WEB}/empresa`);
  await new Promise((r) => setTimeout(r, 1200));
  const grupoDaTela = () =>
    p.evaluate(() => {
      const b = [...document.querySelectorAll("aside button")]
        .find((x) => /administra/i.test(x.innerText));
      const link = [...document.querySelectorAll("aside a")]
        .find((x) => x.textContent === "Empresa");
      return { aberto: b?.getAttribute("aria-expanded"), visivel: link?.offsetParent !== null };
    });
  const antesDoClique = await grupoDaTela();
  checar("o grupo da tela aberta começa expandido", antesDoClique.aberto === "true",
    antesDoClique);
  await p.evaluate(() => {
    [...document.querySelectorAll("aside button")]
      .find((x) => /administra/i.test(x.innerText))?.click();
  });
  await new Promise((r) => setTimeout(r, 500));
  const depoisDoClique = await grupoDaTela();
  checar("mas pode ser recolhido mesmo com a tela dele aberta",
    depoisDoClique.aberto === "false" && depoisDoClique.visivel === false, depoisDoClique);
  await irPara(p, `${WEB}/empresa`);
  await new Promise((r) => setTimeout(r, 1200));
  checar("e continua recolhido ao voltar para a tela",
    (await grupoDaTela()).aberto === "false");
  // Deixa aberto de novo: as fases seguintes clicam em links do menu.
  await p.evaluate(() => {
    [...document.querySelectorAll("aside button")]
      .find((x) => /administra/i.test(x.innerText))?.click();
  });
  await new Promise((r) => setTimeout(r, 400));

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

  // O aviso de "criado" ficava no TOPO, e o botão de salvar está no fim de um
  // formulário longo: quem clicava não via confirmação nenhuma. Agora ele
  // flutua preso ao rodapé — e leva junto o caminho para cadastrar o próximo.
  const avisoCriou = await p.evaluate(() => {
    const el = document.querySelector("[data-aviso]");
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      tipo: el.getAttribute("data-aviso"),
      texto: el.innerText,
      fixo: getComputedStyle(el.parentElement).position === "fixed",
      naTela: r.top >= 0 && r.bottom <= window.innerHeight && r.width > 0,
    };
  });
  checar("o aviso de sucesso aparece", avisoCriou?.tipo === "ok", avisoCriou);
  checar("preso à tela, à vista de qualquer rolagem",
    avisoCriou?.fixo === true && avisoCriou?.naTela === true, avisoCriou);
  checar("com o nome do que foi criado",
    (avisoCriou?.texto ?? "").includes(nomeProduto), avisoCriou?.texto);
  checar("e o caminho para cadastrar o próximo",
    /cadastrar outro/i.test(avisoCriou?.texto ?? ""), avisoCriou?.texto);
  await foto(p, "15-produto");

  // Voltar tem de parecer um controle, não legenda da tela.
  const voltar = await p.evaluate(() => {
    const el = document.querySelector(".link-voltar");
    if (!el) return null;
    const e = getComputedStyle(el);
    return { borda: e.borderTopWidth, tag: el.tagName, tamanho: e.fontSize };
  });
  checar("o voltar é um controle, não um rótulo",
    voltar?.tag === "A" && parseFloat(voltar?.borda ?? "0") > 0
      && parseFloat(voltar?.tamanho ?? "0") >= 13, voltar);

  // ⚠️ `?busca=` na URL não filtra nada: a busca é estado da tela. Com 2.000
  // produtos na base — uma conta real —, abrir a lista e esperar ver o que
  // acabou de ser criado é esperar a sorte. Procura-se como se procura.
  await p.goto(`${WEB}/produtos`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 600));
  const campoBuscaProduto = (await p.$$('input[placeholder="nome, código ou código de barras"]'))[0];
  await campoBuscaProduto.type(nomeProduto);
  await new Promise((r) => setTimeout(r, 1200));
  const naLista = await esperarTexto(p, nomeProduto);
  checar("produto aparece na lista quando procurado pelo nome", naLista, nomeProduto);

  // Limpa: desativa o produto criado pelo teste.
  if (criou) {
    const idProduto = p.url().match(/produtos\/(\d+)/)?.[1];
    await api("DELETE", `/produtos/${idProduto}`, null, token);
  }

  // As quatro tabelas num item só. "Tabelas de apoio" não é o nome de nada que
  // se procura, então a TELA diz o que tem dentro.
  const menuCadastros = await p.evaluate(() =>
    [...document.querySelectorAll("nav a")].map((a) => a.textContent?.trim()));
  checar("as tabelas de apoio ficam num item só", menuCadastros.includes("Tabelas de apoio"),
    menuCadastros);

  // O endereço de cada aba vale por si — dá para guardar e voltar direto.
  await irPara(p, `${WEB}/cadastros?aba=locais`);
  await new Promise((r) => setTimeout(r, 1200));
  const abaLocais = await p.evaluate(() => ({
    titulo: document.querySelector("h1")?.textContent?.trim(),
    diz: /locais de estoque/i.test(document.body.innerText),
    cartao: [...document.querySelectorAll("h2")].map((h) => h.textContent?.trim()),
  }));
  checar("o endereço abre direto na aba pedida",
    abaLocais.cartao.includes("Locais de estoque"), abaLocais);
  checar("e a tela nomeia o que tem dentro",
    abaLocais.titulo === "Tabelas de apoio" && abaLocais.diz, abaLocais);

  // Nas tabelas de apoio o formulário fica ACIMA da lista: cadastrar é o que se
  // vai fazer ali, e rolar a lista inteira para achar o campo é atrito bobo.
  await irPara(p, `${WEB}/cadastros`);
  await new Promise((r) => setTimeout(r, 1200));
  const ordemCadastro = await p.evaluate(() => {
    const form = document.querySelector("main form");
    const lista = document.querySelector("main ul, main table");
    if (!form) return { erro: "sem formulário" };
    if (!lista || lista.offsetParent === null) return { formY: 0, listaY: null };
    return {
      formY: Math.round(form.getBoundingClientRect().top),
      listaY: Math.round(lista.getBoundingClientRect().top),
    };
  });
  checar("o cadastro fica acima da lista nas tabelas de apoio",
    ordemCadastro.listaY === null || ordemCadastro.formY < ordemCadastro.listaY,
    ordemCadastro);

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
  // linha 1: 500 g de farinha. O item da ficha também virou busca: insumos do
  // servidor e preparos com ficha na mesma lista.
  const buscaItem = await p.$('input[aria-label="Buscar insumo ou preparo"]');
  checar("o item da ficha se escolhe por busca", !!buscaItem);
  await buscaItem.type(`Tela farinha ${marca}`);
  await p.keyboard.press("Tab");
  await new Promise((r) => setTimeout(r, 1200));
  const itemEscolhido = await p.evaluate(
    () => document.querySelector('input[aria-label="Buscar insumo ou preparo"]')?.value ?? "");
  checar("e o Tab preenche a linha", itemEscolhido.includes(`Tela farinha ${marca}`),
    itemEscolhido);
  await numeros[2].type("500");
  const selectsUm = await p.$$("select");
  await selectsUm[2].select("G");                    // 0 produto, 1 rendimento_um, 2 unidade
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
    const textoCozinha = await textoVisivel(p);
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
    ["/ajustes", "18c-ajustes"],
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

  // Abrir a contagem PELO BOTÃO. Só carregar a tela não bastava: o seletor de
  // local mostrava o nome do local e mandava o pedido sem ele, e a resposta era
  // "Local não encontrado" com o local à vista.
  const { dados: invAbertos } = await api("GET", "/inventarios", null, token);
  for (const i of invAbertos ?? []) {
    if (i.status === "ABERTO") await api("DELETE", `/inventarios/${i.id}`, null, token);
  }
  // A contagem congela o que TEM saldo no local: sem nada em estoque ela nasce
  // vazia, e a checagem do filtro passaria por não ter o que filtrar.
  const { dados: locaisInv } = await api("GET", "/locais", null, token);
  const localInv = (locaisInv ?? []).find((l) => l.principal) ?? (locaisInv ?? [])[0];
  const { dados: insumoInv } = await api("POST", "/produtos",
    { nome: `Inv tela ${m4}`, tipo: "INSUMO", um_estoque: "KG" }, token);
  await api("POST", "/estoque/entradas",
    { id_produto: insumoInv.id, quantidade: 3, custo_unitario: 5, id_local: localInv?.id },
    token);
  await p.goto(`${WEB}/inventario`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1100));
  const localEscolhido = await p.evaluate(() => {
    const s = document.querySelector("select");
    return s ? { valor: s.value, texto: s.options[s.selectedIndex]?.text } : null;
  });
  checar("o seletor de local vem preenchido", !!localEscolhido?.valor, localEscolhido);
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (x) => x.textContent === "Abrir inventário");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 1600));
  const textoInv = await p.evaluate(() => document.body.innerText);
  // Contar tem tela própria: quem conta anda pela despensa com o celular, e
  // uma tabela de dez colunas não serve na mão.
  checar("abrir a contagem leva para a tela dela", /\/inventario\/\d+/.test(p.url()), p.url());
  const telaContagem = await p.evaluate(() => {
    const rotulos = [...document.querySelectorAll("span.rotulo")].map((x) => x.textContent);
    const campo = document.querySelector('input[inputmode="decimal"]');
    return {
      achar: rotulos.includes("Achar produto"),
      contei: rotulos.includes("Contei"),
      unidade: rotulos.includes("Unidade"),
      progresso: /contado\(s\)/.test(document.body.innerText),
      // Abaixo de 16px o iPhone dá zoom no foco e a tela salta a cada campo.
      tamanhoFonte: campo ? parseFloat(getComputedStyle(campo).fontSize) : 0,
    };
  });
  checar("a contagem tem campo por produto, com unidade",
    telaContagem.contei && telaContagem.unidade, telaContagem);
  checar("com o progresso à vista e busca", telaContagem.progresso && telaContagem.achar,
    telaContagem);
  checar("e campo grande o bastante para o celular não dar zoom",
    telaContagem.tamanhoFonte >= 16, telaContagem.tamanhoFonte);
  // O seletor de unidade não pode parecer travado: quem estoca em KG conta em
  // G sem cadastrar nada, e quem precisa de caixa tem de achar o caminho.
  const seletorUnidade = await p.evaluate(() => {
    const s = [...document.querySelectorAll("select")].find(
      (x) => x.closest("label")?.textContent?.includes("Unidade"));
    return s
      ? {
          desabilitado: s.disabled,
          opcoes: [...s.options].map((o) => o.value),
          caminho: !!document.body.innerText.match(/contar em outra embalagem/i),
        }
      : null;
  });
  checar("o seletor de unidade não fica travado",
    seletorUnidade && seletorUnidade.desabilitado === false, seletorUnidade);
  checar("e traz as unidades da mesma grandeza, sem cadastro nenhum",
    (seletorUnidade?.opcoes?.length ?? 0) > 1, seletorUnidade?.opcoes);
  checar("com o caminho para cadastrar outra embalagem", seletorUnidade?.caminho === true,
    seletorUnidade);
  await foto(p, "20c-contagem");

  // Digitar grava sozinho: contagem que só existe na tela até um "salvar tudo"
  // no fim é contagem que se perde.
  await p.evaluate(() => {
    const c = document.querySelector('input[inputmode="decimal"]');
    const set = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    // ⚠️ Sem FOCAR antes, `blur()` não dispara nada — e é o blur que grava.
    c.focus();
    set.call(c, "7");
    c.dispatchEvent(new Event("input", { bubbles: true }));
    c.blur();
  });
  await new Promise((r) => setTimeout(r, 1600));
  const { dados: invDepois } = await api("GET", `/inventarios/${p.url().match(/\d+$/)[0]}`,
    null, token);
  checar("o que se digita grava sozinho, sem botão de salvar",
    (invDepois.itens ?? []).some((i) => Number(i.qtd_contada) === 7), invDepois.contados);

  // A agenda de produção: planejar e registrar são momentos diferentes.
  // ⚠️ A suíte GARANTE uma linha planejada. Sem isso o bloco da confirmação
  // ficava sem botão em que clicar e passava em silêncio — e checagem que não
  // roda é pior que checagem que falha. (Linha produzida sai da agenda: é uma
  // lista de tarefa, não um histórico.)
  const { dados: fichasProd } = await api("GET", "/fichas", null, token);
  const homologada = (fichasProd ?? []).find((f) => f.status === "HOMOLOGADA");
  if (homologada) {
    const amanhaISO = diaLocal(1);
    await api("POST", "/producao-agenda",
      { id_produto: homologada.id_produto, data_prevista: amanhaISO, quantidade: 3 }, token);
  }
  checar("há ficha homologada para a agenda usar", !!homologada, fichasProd?.length);

  await irPara(p, `${WEB}/producao`);
  await new Promise((r) => setTimeout(r, 1400));
  const agenda = await p.evaluate(() => {
    const texto = document.body.innerText;
    const abas = [...document.querySelectorAll("nav button")].map((b) => b.textContent?.trim());
    return {
      temAbas: abas.includes("Agenda") && abas.includes("Registrar o que foi feito"),
      agendaPrimeiro: /Agendar produção/i.test(texto),
      naoMexe: /não mexe no estoque/i.test(texto),
    };
  });
  checar("produção separa agenda de registro", agenda.temAbas, agenda);
  checar("e a agenda abre primeiro, com o plano à vista",
    agenda.agendaPrimeiro && agenda.naoMexe, agenda);
  await foto(p, "19b-agenda-producao");

  // O nome da linha abre a FOLHA da produção: quanto de cada insumo, quanto
  // existe no local e o que falta — antes de ligar o forno.
  const alvoFolha = await p.evaluate(() => {
    const a = [...document.querySelectorAll("a")].find((x) =>
      /\/producao\/\d+$/.test(x.getAttribute("href") ?? ""));
    return a ? a.getAttribute("href") : null;
  });
  // ⚠️ Navegar de verdade, não `a.click()` de dentro da página: o clique
  // sintético saía sem a navegação do Next e a checagem media a tela errada.
  if (alvoFolha) await irPara(p, `${WEB}${alvoFolha}`);
  const abriuFolha = alvoFolha && /\/producao\/\d+$/.test(p.url());
  checar("a linha da agenda abre a folha da produção", !!abriuFolha, [alvoFolha, p.url()]);
  if (abriuFolha) {
    await new Promise((r) => setTimeout(r, 1600));
    const folha = await p.evaluate(() => {
      const cab = [...document.querySelectorAll("th")].map((t) => t.textContent?.trim());
      return {
        colunas: ["Insumo", "Por unidade", "Total", "Tem no local"].every((c) =>
          cab.includes(c)),
        rende: /A receita rende/i.test(document.body.innerText),
        falta: /tem tudo|item\(ns\) faltando/i.test(document.body.innerText),
      };
    });
    checar("com quantidade por unidade e total", folha.colunas, folha);
    checar("dizendo quantas vezes a receita é feita", folha.rende, folha);
    checar("e se tem tudo ou o que falta", folha.falta, folha);
    await foto(p, "19d-folha-producao");
    // Volta para a agenda: as checagens seguintes são de lá, e ficar na folha
    // faria a próxima medir o campo errado (aqui o rótulo é "Quantidade").
    await irPara(p, `${WEB}/producao`);
    await new Promise((r) => setTimeout(r, 1300));
  }

  // Produzir uma linha da agenda: quantidade à vista e confirmação do sistema,
  // não a caixa do navegador. `window.prompt` trava o Chrome do teste e, no uso
  // real, é fonte de sistema com botão em inglês.
  const semPrompt = await p.evaluate(() => {
    const campos = [...document.querySelectorAll("span.rotulo")].map((x) => x.textContent);
    return { temCampoQtd: campos.includes("produz"), usaPrompt: false };
  });
  const linhaAgendada = await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent === "Produzir");
    if (!b) return false;
    b.click();
    return true;
  });
  if (linhaAgendada) {
    await new Promise((r) => setTimeout(r, 800));
    const dialogo = await p.evaluate(() => {
      const d = document.querySelector('[role="dialog"]');
      return d ? { titulo: d.getAttribute("aria-label"), texto: d.innerText } : null;
    });
    checar("produzir pergunta antes, no padrão do sistema",
      dialogo?.titulo === "Confirmar a produção", dialogo);
    checar("dizendo o que a ação faz e que não se desfaz",
      /baixa os ingredientes/i.test(dialogo?.texto ?? "")
        && /estorno/i.test(dialogo?.texto ?? ""), dialogo?.texto?.slice(0, 140));
    checar("e a quantidade fica no campo da linha, não no diálogo",
      semPrompt.temCampoQtd, semPrompt);
    await foto(p, "19c-confirmar-producao");
    await p.evaluate(() => {
      const d = document.querySelector('[role="dialog"]');
      [...(d?.querySelectorAll("button") ?? [])].find(
        (b) => b.textContent === "Cancelar")?.click();
    });
    await new Promise((r) => setTimeout(r, 500));
  }

  // Contagem CEGA: o esperado não aparece na tela nem sai do servidor.
  // ⚠️ Só há uma contagem aberta por local: sem fechar a de cima, o POST volta
  // 409 e o bloco inteiro passaria em silêncio — checagem que não roda é pior
  // que checagem que falha.
  for (const inv of (await api("GET", "/inventarios", null, token)).dados ?? []) {
    if (inv.status === "ABERTO") await api("DELETE", `/inventarios/${inv.id}`, null, token);
  }
  const { dados: invCega } = await api("POST", "/inventarios",
    { id_local: localInv?.id, cega: true }, token);
  checar("abre a contagem cega", !!invCega?.id, invCega);
  if (invCega?.id) {
    await irPara(p, `${WEB}/inventario/${invCega.id}`);
    await new Promise((r) => setTimeout(r, 1500));
    const cega = await p.evaluate(() => {
      const rotulos = [...document.querySelectorAll("span.rotulo")].map((x) => x.textContent);
      return {
        avisa: /Contagem cega/i.test(document.body.innerText),
        temSistema: rotulos.includes("Sistema"),
        temContei: rotulos.includes("Contei"),
      };
    });
    checar("a contagem cega avisa que é cega", cega.avisa, cega);
    checar("e não mostra o saldo do sistema", cega.temSistema === false && cega.temContei, cega);
    await foto(p, "20d-contagem-cega");
    await api("DELETE", `/inventarios/${invCega.id}`, null, token);
  }

  await api("DELETE", `/produtos/${insumoInv.id}`, null, token);

  // O sintoma que originou tudo isto: o seletor mostrava o local e o pedido
  // saía sem ele. Agora a contagem abre — e o título traz o nome do local.
  checar("a contagem abre sem dizer que o local não existe",
    !/Local não encontrado/i.test(textoInv) && /Contagem ·/.test(textoInv),
    textoInv.slice(0, 140));

  // Filtrar o razão. O razão cresce todo dia; sem filtro, achar um movimento
  // vira rolagem — e a planilha tem de sair com o MESMO recorte da tela.
  await p.goto(`${WEB}/estoque`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1100));
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent === "Movimentos");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 1200));
  const filtrosRazao = await p.evaluate(() => {
    const rotulos = [...document.querySelectorAll("span.rotulo")].map((x) => x.textContent);
    return { rotulos, temData: !!document.querySelector('input[type="date"]') };
  });
  checar("o razão tem filtro de período",
    filtrosRazao.rotulos.includes("De") && filtrosRazao.rotulos.includes("Até")
      && filtrosRazao.temData, filtrosRazao);
  checar("e filtro por produto e tipo de movimento",
    filtrosRazao.rotulos.includes("Produto") && filtrosRazao.rotulos.includes("Movimento"),
    filtrosRazao.rotulos);
  // A lupa também nos FILTROS: texto traz os cinco cafés, a lupa fixa um só.
  const temLupaNoFiltro = await p.evaluate(
    () => document.querySelectorAll('button[aria-label="Buscar produto"]').length);
  checar("o filtro do razão tem a lupa de busca", temLupaNoFiltro > 0, temLupaNoFiltro);
  await p.evaluate(() => {
    document.querySelector('button[aria-label="Buscar produto"]')?.click();
  });
  await new Promise((r) => setTimeout(r, 900));
  await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    d?.querySelector("li button")?.click();
  });
  await new Promise((r) => setTimeout(r, 1200));
  const fixado = await p.evaluate(() => ({
    etiqueta: !!document.querySelector('button[aria-label="tirar o filtro de produto"]'),
    texto: document.body.innerText,
  }));
  checar("escolher na lupa fixa o produto como etiqueta", fixado.etiqueta === true, fixado.etiqueta);
  checar("e o razão passa a mostrar só ele",
    /lançamento\(s\) no filtro/.test(fixado.texto), fixado.texto.slice(0, 200));
  await foto(p, "18e-razao-produto-fixado");
  await p.evaluate(() => {
    document.querySelector('button[aria-label="tirar o filtro de produto"]')?.click();
  });
  await new Promise((r) => setTimeout(r, 1000));

  const antesFiltro = await p.evaluate(() =>
    document.querySelectorAll("table tbody tr").length);
  await p.evaluate(() => {
    const campos = [...document.querySelectorAll('input[type="date"]')];
    const set = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    for (const c of campos) {
      set.call(c, "1999-01-01");
      c.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });
  await new Promise((r) => setTimeout(r, 1400));
  const depoisFiltro = await p.evaluate(() => document.body.innerText);
  checar("filtrar por um período sem movimento esvazia a lista",
    /Nenhum movimento com esses filtros/.test(depoisFiltro),
    [antesFiltro, depoisFiltro.slice(0, 120)]);
  await foto(p, "18b-razao-filtrado");

  // Lançar é tela própria: saldos é onde se CONSULTA. Os quatro botões viraram
  // Estoque ▸ Ajustes, e da tela de saldos sobra o atalho.
  await p.goto(`${WEB}/estoque`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1100));
  const saldosSemForm = await p.evaluate(() => {
    const textos = [...document.querySelectorAll("button, a")].map((x) => x.textContent?.trim());
    return {
      lancar: textos.includes("Lançar ajuste"),
      antigos: ["Entrada", "Saída", "Perda", "Transferir"].filter((t) => textos.includes(t)),
    };
  });
  checar("saldos deixou de ter os botões de lançamento",
    saldosSemForm.antigos.length === 0, saldosSemForm.antigos);
  checar("e ganhou o atalho para os ajustes", saldosSemForm.lancar === true, saldosSemForm);

  await irPara(p, `${WEB}/ajustes`);
  await new Promise((r) => setTimeout(r, 1200));
  const telaAjustes = await p.evaluate(() => {
    const texto = document.body.innerText;
    const escolhido = document.querySelector('[aria-pressed="true"]');
    return {
      tipos: ["Entrada", "Saída", "Perda", "Transferência"].filter((t) => texto.includes(t)),
      escolhido: escolhido?.textContent?.trim().slice(0, 8) ?? null,
      temCusto: /custo unit[áa]rio/i.test(texto),
    };
  });
  checar("a tela de ajustes oferece os quatro tipos", telaAjustes.tipos.length === 4,
    telaAjustes.tipos);
  checar("com um já escolhido e o formulário montado para ele",
    telaAjustes.escolhido?.startsWith("Entrada") && telaAjustes.temCusto, telaAjustes);

  // A busca de cadastro: digitar o nome e dar Tab preenche sozinho, sem combo.
  // Combobox serve até umas dezenas de linhas; com dois mil insumos vira rolo.
  const campoBusca = await p.$('input[aria-label="Buscar produto"]');
  checar("o produto se escolhe por busca, não por combobox", !!campoBusca);
  await campoBusca.type(`Est tela ${m4}`);
  await p.keyboard.press("Tab");
  await new Promise((r) => setTimeout(r, 1200));
  const preencheu = await p.evaluate(
    () => document.querySelector('input[aria-label="Buscar produto"]')?.value ?? "");
  checar("um resultado só: o Tab preenche e segue",
    preencheu.includes(`Est tela ${m4}`), preencheu);

  // Mais de um resultado tem de abrir a janela de pesquisa, já filtrada.
  await p.evaluate(() => {
    const c = document.querySelector('input[aria-label="Buscar produto"]');
    const set = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    set.call(c, "Est");
    c.dispatchEvent(new Event("input", { bubbles: true }));
    // O Tab anterior levou o foco para a lupa: sem devolvê-lo ao campo, o
    // próximo Tab não dispara blur nenhum e a busca nunca acontece.
    c.focus();
  });
  await p.keyboard.press("Tab");
  await new Promise((r) => setTimeout(r, 1400));
  const janela = await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    return d ? { titulo: d.getAttribute("aria-label"), linhas: d.querySelectorAll("li").length }
             : null;
  });
  checar("mais de um resultado abre a janela de pesquisa", janela?.titulo === "Buscar produto",
    janela);
  checar("e a janela já vem com o filtro digitado", (janela?.linhas ?? 0) > 1, janela);
  await foto(p, "18d-busca-cadastro");
  // Escolher na janela devolve o foco ao campo, para seguir no teclado.
  await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    if (!d) return;
    [...d.querySelectorAll("li button")].find((b) => b.textContent.includes("Est tela"))?.click();
  });
  await new Promise((r) => setTimeout(r, 700));
  const depoisDaJanela = await p.evaluate(() => ({
    fechou: !document.querySelector('[role="dialog"]'),
    campo: document.activeElement?.getAttribute("aria-label"),
  }));
  checar("escolher fecha a janela e devolve o foco ao campo",
    depoisDaJanela.fechou && depoisDaJanela.campo === "Buscar produto", depoisDaJanela);

  // Entrada pela tela: 10 kg a R$ 20,00.
  const numEstoque = await p.$$("input[type=number]");
  await numEstoque[0].type("10");
  await numEstoque[1].type("20");
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (x) => x.textContent === "Lançar entrada");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 1600));
  const textoEstoque = await p.evaluate(() => document.body.innerText);
  checar("entrada pela tela mostra o novo custo médio", /custo médio: R\$\s?20,00/i.test(textoEstoque),
    textoEstoque.match(/.{0,60}custo médio.{0,20}/i)?.[0]);
  await foto(p, "21-ajuste-entrada");

  // O formulário fica aberto e limpo: quem ajusta um item ajusta o próximo.
  const depoisDeLancar = await p.evaluate(() => {
    const qtd = [...document.querySelectorAll("input[type=number]")][0];
    return { limpo: qtd?.value === "", aindaTem: !!qtd };
  });
  checar("o formulário continua aberto e limpo para o próximo",
    depoisDeLancar.aindaTem && depoisDeLancar.limpo, depoisDeLancar);
  const nosRecentes = await p.evaluate(() => document.body.innerText.includes("Últimos ajustes"));
  checar("e o ajuste aparece na lista dos últimos", nosRecentes);

  const { dados: saldos } = await api("GET", `/estoque/saldos?busca=${m4}`, null, token);
  checar("saldo gravado pela tela", saldos.length === 1 && Number(saldos[0].quantidade) === 10,
    saldos);
  checar("valor em estoque = 200,00", saldos[0] && Number(saldos[0].valor) === 200,
    saldos[0]?.valor);

  await api("DELETE", `/produtos/${insumo4.id}`, null, token);

  console.log("7. CMV (etapa 6)");
  const m6 = Date.now().toString().slice(-5);
  const hoje6 = diaLocal();
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
  const codigosDaFixture = ["CAF-500", "LEI-INT", "TOM-CX"];
  for (const c of codigosDaFixture) {
    await api("DELETE", `/notas/vinculos/${c}`, null, token);
  }
  // O de-para resolve por código do fornecedor, por código do Omie e por EAN —
  // apagar só o vínculo não basta. A suíte de API cria produtos a partir dos
  // itens destas mesmas fixtures; se algum sobrar, a nota entra conciliada e a
  // fase abaixo (que prova a pendência) não tem o que provar.
  for (const c of codigosDaFixture) {
    const { dados: achados } = await api(
      "GET", `/produtos?busca=${c}&incluir_inativos=true`, null, token);
    for (const pr of achados ?? []) {
      if (pr.codigo === c) await api("DELETE", `/produtos/${pr.id}`, null, token);
    }
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

  // Abre a nota da fixture e confere que o lançamento está barrado. ⚠️ Procura
  // pelo número: numa base com notas de uma conta real, a 4812 fica fora da
  // primeira página e o clique não achava botão nenhum — o teste então lia o
  // cabeçalho da casa e falhava sem dizer por quê.
  const campoBuscaNota = (await p.$$('input[aria-label="Buscar nota"]'))[0];
  checar("a lista de notas tem busca", !!campoBuscaNota);
  await campoBuscaNota.type("4812");
  await new Promise((r) => setTimeout(r, 1400));
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      x.textContent.includes("NF 4812"));
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 1200));
  const textoNota = await p.evaluate(() => document.body.innerText);
  checar("a nota abre com os itens", /CAFE EM GRAO/i.test(textoNota), textoNota.slice(0, 100));
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

  // A trava da conciliação se prova AQUI, e não na nota do Omie: o código do
  // azeite é novo a cada rodada, então o item não tem produto nenhum de quem
  // ser. Na nota do Omie a prova evaporava assim que o catálogo entrava na
  // base e os itens passavam a se vincular sozinhos — o teste continuava
  // "passando" sem exercitar trava alguma.
  checar("a tela explica por que não dá para lançar",
    /sem produto vinculado/i.test(textoXml), textoXml.slice(0, 200));
  const lancarDesabilitado = await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      x.textContent === "Lançar no estoque");
    return b ? b.disabled : null;
  });
  checar("o botão de lançar fica desabilitado", lancarDesabilitado === true, lancarDesabilitado);
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
  // ⚠️ Precisa ter unidade: a checagem logo abaixo afirma que a linha vem
  // preenchida com a unidade do estoque. O catálogo do Omie cria rascunhos SEM
  // unidade de propósito, e pegar "o primeiro que controla estoque" caía num
  // deles — o teste falhava dizendo do produto o que era verdade do rascunho.
  const insumoNota = produtosNota.find((x) => x.controla_estoque && x.um_estoque);
  await p.goto(`${WEB}/compras`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1100));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")].find((x) => x.textContent === "Digitar nota")?.click();
  });
  await new Promise((r) => setTimeout(r, 900));
  const seletoresNota = await p.$$("select");
  checar("o formulário de digitação abre", seletoresNota.length >= 3, seletoresNota.length);

  // Digitar o código e dar Tab tem de trazer o produto: quem copia de um papel
  // não quer soltar o teclado para caçar no combo.
  const codigoNota = (await api("GET", `/produtos/${insumoNota.id}`, null, token)).dados.codigo;
  const campoCodigo = (await p.$$('input[placeholder="P0001"]'))[0];
  checar("a linha tem campo de código", !!campoCodigo);
  await campoCodigo.type(codigoNota.toLowerCase());
  await p.keyboard.press("Tab");
  // A busca do código vai ao SERVIDOR — não adianta olhar antes da volta. Duas
  // armadilhas aqui, as duas do TESTE e não do produto:
  //   1. esperar pelo NOME não serve: "Café" já está no cabeçalho da casa, e a
  //      espera terminava no mesmo instante em que começava;
  //   2. o primeiro `input[aria-label="Buscar produto"]` da página pode ser o
  //      da CONCILIAÇÃO de uma nota aberta, que fica vazio para sempre.
  // Por isso tudo sai da LINHA do código digitado, e com espera de verdade.
  const naLinhaDoCodigo = () =>
    p.evaluate(() => {
      const linha = document.querySelector('input[placeholder="P0001"]')?.closest("tr");
      if (!linha) return null;
      const valor = (sel) => linha.querySelector(sel)?.value ?? null;
      return {
        codigo: valor('input[placeholder="P0001"]'),
        produto: valor('input[aria-label="Buscar produto"]'),
        unidade: valor("select"),
      };
    });

  let porCodigo = null;
  for (const ate = Date.now() + 8000; Date.now() < ate; ) {
    porCodigo = await naLinhaDoCodigo();
    if (porCodigo?.produto) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  await foto(p, "30b-codigo-na-linha");
  checar("o código traz o produto ao sair do campo",
    (porCodigo?.produto ?? "").includes(insumoNota.nome ?? ""), porCodigo);
  checar("e normaliza o que foi digitado", porCodigo?.codigo === codigoNota, porCodigo);
  checar("a unidade vem preenchida com a do estoque",
    porCodigo?.unidade === (insumoNota.um_estoque ?? "UN"), porCodigo);

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

  // Corrigir a nota digitada, pela tela, antes de ela virar estoque.
  await p.evaluate(() => {
    [...document.querySelectorAll("button")].find((x) => x.textContent === "Corrigir")?.click();
  });
  await new Promise((r) => setTimeout(r, 1200));
  const textoCorrigir = await p.evaluate(() => document.body.innerText);
  checar("a nota digitada oferece correção", /Corrigir a nota/i.test(textoCorrigir),
    textoCorrigir.slice(0, 160));
  checar("e explica que dá para mexer antes de lançar",
    /ainda não virou estoque/i.test(textoCorrigir));
  // O formulário volta preenchido: é o que separa corrigir de digitar de novo.
  const veioPreenchido = await p.evaluate(() => {
    const qtd = [...document.querySelectorAll('input[inputmode="decimal"]')][0];
    return qtd ? qtd.value : null;
  });
  checar("o formulário volta com o que foi digitado", Number(veioPreenchido) > 0, veioPreenchido);
  await foto(p, "29d-corrigir-nota");
  await p.evaluate(() => {
    [...document.querySelectorAll("button")].find((x) => /cancelar/i.test(x.textContent))?.click();
  });
  await new Promise((r) => setTimeout(r, 500));

  // Limpeza: as duas notas do teste saem, para a próxima rodada começar limpa.
  const { dados: notasDoTesteXml } = await api("GET", "/notas?limite=30", null, token);
  for (const n of notasDoTesteXml ?? []) {
    if (n.chave_nfe === chaveNota || (n.origem === "MANUAL" && !n.numero)) {
      await api("DELETE", `/notas/${n.id}`, null, token);
    }
  }

  console.log("7a. combo: uma linha do PDV que vale por dois produtos");
  const marcaKit = String(Date.now()).slice(-6);
  const idLocalKit = await garantirLocal();
  const { dados: bebida } = await api("POST", "/produtos", {
    nome: `Combo bebida ${marcaKit}`, tipo: "REVENDA", um_estoque: "UN",
  }, token);
  await api("POST", "/estoque/entradas", {
    id_produto: bebida.id, quantidade: 10, custo_unitario: 3, id_local: idLocalKit,
  }, token);
  const { dados: comboTela } = await api("POST", "/produtos", {
    nome: `Combo tela ${marcaKit}`, tipo: "KIT", um_estoque: "UN",
  }, token);

  await irPara(p, `${WEB}/produtos/${comboTela.id}`);
  await new Promise((r) => setTimeout(r, 1600));
  const textoKit = await p.evaluate(() => document.body.innerText);
  checar("produto KIT ganha o cartão de composição", /O que vai no combo/i.test(textoKit),
    textoKit.slice(0, 140));
  checar("e avisa que sem composição não há custo",
    /monte a composição/i.test(textoKit), textoKit.slice(-200));

  // Monta a composição pela tela, do jeito que o cliente faria. O componente
  // também virou busca: um combo pode apontar para qualquer produto da casa.
  const buscasKit = await p.$$('input[aria-label="Buscar produto"]');
  const buscaComponente = buscasKit[buscasKit.length - 1];
  checar("o componente do combo se escolhe por busca", !!buscaComponente);
  await buscaComponente.type(`Combo bebida ${marcaKit}`);
  await p.keyboard.press("Tab");
  await esperarTexto(p, `Combo bebida ${marcaKit}`, 6000);
  await new Promise((r) => setTimeout(r, 400));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((x) => /gravar composição/i.test(x.textContent))?.click();
  });
  await new Promise((r) => setTimeout(r, 1800));
  const textoGravado = await p.evaluate(() => document.body.innerText);
  checar("a composição grava pela tela", /componente\(s\)/i.test(textoGravado),
    textoGravado.slice(0, 160));
  checar("e o custo do combo aparece", /R\$\s*3,00/.test(textoGravado),
    textoGravado.slice(-260));
  await foto(p, "37-combo");

  const { dados: kitApi } = await api("GET", `/produtos/${comboTela.id}/kit`, null, token);
  checar("a API confirma o custo somado", Number(kitApi.custo) === 3, kitApi.custo);
  checar("e diz que a composição está completa", kitApi.origem === "kit", kitApi.origem);

  for (const id of [comboTela.id, bebida.id]) await api("DELETE", `/produtos/${id}`, null, token);

  // O que mexe no razão pergunta antes — e a pergunta é do sistema, não do
  // navegador: `window.confirm` não tem onde dizer o que a ação faz.
  await irPara(p, `${WEB}/estoque`);
  await new Promise((r) => setTimeout(r, 1200));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")].find((x) => x.textContent === "Movimentos")?.click();
  });
  await new Promise((r) => setTimeout(r, 1400));
  const clicouEstornar = await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (x) => x.textContent?.trim() === "estornar");
    if (!b) return false;
    b.click();
    return true;
  });
  checar("o razão oferece estornar", clicouEstornar, clicouEstornar);
  if (clicouEstornar) {
    await new Promise((r) => setTimeout(r, 700));
    const d = await p.evaluate(() => {
      const el = document.querySelector('[role="dialog"]');
      return el ? { titulo: el.getAttribute("aria-label"), texto: el.innerText } : null;
    });
    checar("estornar pergunta antes, no padrão do sistema",
      d?.titulo === "Confirmar o estorno", d);
    checar("explicando que o original continua no razão",
      /continua no razão/i.test(d?.texto ?? ""), d?.texto?.slice(0, 120));
    await p.evaluate(() => {
      const el = document.querySelector('[role="dialog"]');
      [...(el?.querySelectorAll("button") ?? [])].find(
        (b) => b.textContent === "Cancelar")?.click();
    });
    await new Promise((r) => setTimeout(r, 500));
    const fechou = await p.evaluate(() => !document.querySelector('[role="dialog"]'));
    checar("e cancelar não estorna nada", fechou, fechou);
  }

  // A movimentação por produto: a conta que EXPLICA o CMV, e que fecha o mês
  // junto com ele.
  await irPara(p, `${WEB}/cmv`);
  await new Promise((r) => setTimeout(r, 1500));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((x) => x.textContent === "Movimentação do estoque")?.click();
  });
  await new Promise((r) => setTimeout(r, 1800));
  const mov = await p.evaluate(() => {
    const texto = document.body.innerText;
    const cabecalhos = [...document.querySelectorAll("th")].map((t) => t.textContent?.trim());
    return {
      colunas: ["Inicial", "Entradas", "Saídas", "Final"].every((c) => cabecalhos.includes(c)),
      situacao: /mês (aberto|fechado)/i.test(texto),
      fecha: /a conta fecha/i.test(texto),
      naoFecha: /A conta não fecha/i.test(texto),
    };
  });
  checar("a movimentação mostra inicial, entradas, saídas e final", mov.colunas, mov);
  checar("e diz se o mês está aberto ou congelado", mov.situacao, mov);
  checar("com a identidade conferida na própria tela", mov.fecha && !mov.naoFecha, mov);
  await foto(p, "24b-movimentacao");

  console.log("7b. relatórios do dono: onde pesa e o que subiu");
  await irPara(p, `${WEB}/cmv`);
  await new Promise((r) => setTimeout(r, 1500));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((x) => /onde pesa/i.test(x.textContent))?.click();
  });
  await new Promise((r) => setTimeout(r, 2000));
  const textoDono = await p.evaluate(() => document.body.innerText);
  checar("a aba de relatórios do dono abre", /Onde o custo pesa/i.test(textoDono),
    textoDono.slice(0, 140));
  checar("explica que a soma dos grupos é o CMV",
    /soma dos grupos é o CMV/i.test(textoDono));
  checar("e traz o relatório de preços junto",
    /O que subiu de preço/i.test(textoDono));

  // O número que a tela mostra tem de ser o mesmo que a API devolve.
  const hojeIso = diaLocal();
  const { dados: gruposApi } = await api(
    "GET", `/cmv/por-grupo?inicio=${hojeIso}&fim=${hojeIso}&agrupar=setor`, null, token);
  // Só faz sentido somar 100% quando há CMV no período: numa base recém-limpa,
  // entrada sem saída dá CMV zero, e a participação de cada grupo é zero também
  // — o que está certo, não é falha.
  const totalCmv = gruposApi.reduce((t, g) => t + Math.abs(Number(g.cmv)), 0);
  if (totalCmv > 0.01) {
    const soma = gruposApi.reduce((t, g) => t + Number(g.participacao_pct), 0);
    checar("as participações somam 100%", Math.abs(soma - 100) < 0.5, soma);
  } else {
    checar("as participações somam 100%", true, "sem CMV no período");
  }

  // Trocar de setor para categoria tem de recarregar a tabela.
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((x) => x.textContent.trim() === "por categoria")?.click();
  });
  await new Promise((r) => setTimeout(r, 1500));
  checar("dá para trocar para categoria",
    /por categoria/i.test(await p.evaluate(() => document.body.innerText)));
  await foto(p, "36-relatorios-dono");

  console.log("8c. FEFO: o lote que vence antes sai antes");
  const marcaLote = String(Date.now()).slice(-6);
  const localFefo = await garantirLocal();
  const { dados: perecivel } = await api("POST", "/produtos", {
    nome: `Creme FEFO ${marcaLote}`, tipo: "INSUMO", um_estoque: "UN",
    controla_lote: true, controla_validade: true, perecivel: true,
  }, token);
  // O lote que vence DEPOIS entra primeiro, de propósito: se o sistema seguisse
  // a ordem de entrada em vez da validade, o teste passaria por engano.
  for (const [lote, validade] of [[`TARDE${marcaLote}`, "2026-11-30"],
                                  [`CEDO${marcaLote}`, "2026-09-08"]]) {
    await api("POST", "/estoque/entradas", {
      id_produto: perecivel.id, quantidade: 6, custo_unitario: 4,
      id_local: localFefo, lote, validade,
    }, token);
  }

  await irPara(p, `${WEB}/estoque`);
  await new Promise((r) => setTimeout(r, 1400));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")].find((x) => /movimentos/i.test(x.textContent))?.click();
  });
  await new Promise((r) => setTimeout(r, 1200));
  const textoLotes = await p.evaluate(() => document.body.innerText);
  checar("a tela lista os lotes em estoque", /Lotes em estoque/i.test(textoLotes),
    textoLotes.slice(0, 120));
  checar("e explica que a ordem é a da saída",
    /vence antes sai antes/i.test(textoLotes));
  // A ordem na tela é a ordem da fila: o que vence antes aparece antes.
  const ordem = await p.evaluate((m) => {
    const linhas = [...document.querySelectorAll("tr")].map((t) => t.innerText);
    return linhas.filter((t) => t.includes(m)).map((t) => (t.includes("CEDO") ? "CEDO" : "TARDE"));
  }, marcaLote);
  checar("o que vence antes aparece primeiro na fila",
    ordem[0] === "CEDO", ordem);
  await foto(p, "35-lotes");

  // A baixa tem de dizer de qual pote saiu.
  const { dados: baixa } = await api("POST", "/estoque/saidas", {
    tipo: "SAIDA_PERDA", id_produto: perecivel.id, quantidade: 8,
    id_local: localFefo, id_motivo_perda: 1,
  }, token);
  checar("a saída quebra em dois lotes", (baixa.lotes ?? []).length === 2, baixa.lotes);
  checar("começando pelo que vence antes",
    (baixa.lotes?.[0]?.lote ?? "").startsWith("CEDO"), baixa.lotes);
  // "6", não "6.0000": a frase é lida pela cozinha, não por um sistema.
  checar("e a resposta já vem em português de prateleira",
    /Saída lançada: 6 do lote CEDO/.test(baixa.message ?? ""), baixa.message);

  const { dados: sobrou } = await api(
    "GET", `/estoque/lotes?id_produto=${perecivel.id}`, null, token);
  checar("o lote consumido some da lista", !sobrou.some((l) => l.lote.startsWith("CEDO")),
    sobrou.map((l) => l.lote));
  checar("e o outro fica com o que sobrou",
    Number(sobrou.find((l) => l.lote.startsWith("TARDE"))?.quantidade) === 4, sobrou);

  await api("DELETE", `/produtos/${perecivel.id}`, null, token);

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

  // O Início é a tela que o dono abre: tem de responder o mês inteiro de um
  // olhar, e responder com número verdadeiro.
  await p.goto(`${WEB}/`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1600));
  const textoInicio = await p.evaluate(() => document.body.innerText);
  checar("o Início mostra o resumo de alertas",
    listaAlertas.length === 0 || /Precisa da sua atenção/i.test(textoInicio),
    textoInicio.slice(0, 160));
  checar("e traz os indicadores do mês", /Custo do que saiu/i.test(textoInicio),
    textoInicio.slice(0, 200));
  checar("com o valor parado em estoque", /Parado na prateleira/i.test(textoInicio));
  checar("e o peso de cada setor", /Onde o custo pesa/i.test(textoInicio));

  // A regra que não pode afrouxar: sem venda importada, food cost é
  // DESCONHECIDO. Zero ali pareceria um resultado excelente.
  const { dados: painel } = await api("GET", "/inicio", null, token);
  const semVenda = (painel.dinheiro?.receita_mes ?? 0) === 0;
  checar("sem venda no mês, o food cost não vira 0%",
    !semVenda || painel.dinheiro?.food_cost_pct === null, painel.dinheiro?.food_cost_pct);
  checar("e a tela mostra o traço em vez do zero",
    !semVenda || /—/.test(textoInicio), semVenda);

  // Quem não pode ver dinheiro não recebe dinheiro — nem zerado.
  const { dados: sessaoCoz } = await api(
    "POST", "/auth/login", { email: COZINHA.email, senha: COZINHA.senha });
  if (sessaoCoz?.access_token) {
    const { dados: painelCoz } = await api("GET", "/inicio", null, sessaoCoz.access_token);
    checar("cozinha não recebe os números de dinheiro no Início",
      painelCoz.dinheiro === null, painelCoz.dinheiro);
    checar("mas continua vendo o que precisa fazer",
      Array.isArray(painelCoz.alertas), painelCoz.alertas);
  }

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

  // O menu tem submenus: o grupo precisa ser aberto antes de o link existir na
  // tela. O teste passa pelo mesmo caminho que a pessoa passa.
  const grupoFechado = await c.evaluate(() => {
    const b = [...document.querySelectorAll("aside button")]
      .find((x) => /administra/i.test(x.innerText));
    return b ? b.getAttribute("aria-expanded") === "false" : null;
  });
  checar("grupo do menu começa recolhido", grupoFechado === true, grupoFechado);
  await c.evaluate(() => {
    [...document.querySelectorAll("aside button")]
      .find((x) => /administra/i.test(x.innerText))?.click();
  });
  await new Promise((r) => setTimeout(r, 500));
  const abriu = await c.evaluate(() =>
    [...document.querySelectorAll("aside a")].some(
      (x) => x.textContent === "Empresa" && x.offsetParent !== null,
    ));
  checar("e abre ao tocar no grupo", abriu);

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
