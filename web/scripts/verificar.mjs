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
  // `total` vem do X-Total quando a lista é paginada; nulo quando o servidor
  // não o manda (é o que ele faz ao virar a página, para não recontar).
  const cabecalho = r.headers.get("X-Total");
  return {
    status: r.status,
    dados: texto ? JSON.parse(texto) : null,
    total: cabecalho === null ? null : Number(cabecalho),
  };
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
 * Confere onde a sessão foi parar depois do login.
 *
 * ⚠️ É a única forma de provar a promessa "fecha quando eu fechar o navegador":
 * `sessionStorage` morre com a janela, `localStorage` não. Testar isso pela API
 * não prova nada — a escolha do armazenamento é do FRONT.
 */
async function ondeMoraASessao(pagina) {
  return pagina.evaluate(() => ({
    sessao: sessionStorage.getItem("botane.refresh") !== null,
    local: localStorage.getItem("botane.refresh") !== null,
  }));
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

/**
 * Fotografa a tela. **Nunca derruba a bateria.**
 *
 * ⚠️ `fullPage` numa página longa estoura o `protocolTimeout` do Chrome — já
 * aconteceu com o painel de CMV e voltou a acontecer quando Integrações ganhou
 * o segundo bloco de agenda. A foto é diagnóstico: perder uma é um aborrecimento,
 * perder a rodada inteira de 280 checagens por causa dela é outra coisa. Quando
 * a de página inteira falha, tenta a da janela; se essa também falhar, avisa e
 * segue.
 */
async function foto(pagina, nome) {
  try {
    await pagina.screenshot({ path: `${FOTOS}/${nome}.png`, fullPage: true });
  } catch {
    try {
      await pagina.screenshot({ path: `${FOTOS}/${nome}.png` });
      console.log(`  (foto ${nome}: página longa demais, saiu só a janela)`);
    } catch {
      console.log(`  (foto ${nome}: não saiu)`);
    }
  }
}

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

// ⚠️ **E precisa do ritmo MENSAL, garantido — não suposto.** Quase tudo daqui
// para baixo lê o período CORRENTE da loja: o painel de CMV, a tela inicial e a
// movimentação por produto. Com a loja em SEMANAL ou DIARIO, esses recortes
// ficam de poucos dias, e a identidade "inicial + entradas − saídas = final"
// abre por causa dos lançamentos retroativos que as outras suítes deixam na
// base (ver `docs/o-que-falta.md`). A fase 10a troca o ritmo de propósito e o
// devolve; aqui é a precondição de todo o resto.
await api("PUT", "/unidades/1/parametros",
  { ciclo_fechamento: "MENSAL", dia_fechamento_cmv: 1, fechamento_dia_semana: 7 }, token);

mkdirSync(FOTOS, { recursive: true });
const navegador = await puppeteer.launch({
  executablePath: CHROME,
  headless: "new",
  // ⚠️ **O perfil vai para o D:, não para o TEMP do C:.** Sem isto o Chrome
  // cria o `user-data-dir` no disco do sistema, que nesta máquina vive no
  // limite — e o sintoma não é "disco cheio": são erros de PROTOCOLO em pontos
  // diferentes a cada rodada ("Cannot navigate to invalid URL", "detached
  // Frame"), que parecem instabilidade do teste. É a mesma regra do resto do
  // projeto: nada deste repositório escreve volume no C:.
  userDataDir: "scripts/_chrome-perfil",
  args: ["--no-sandbox", "--window-size=1440,1000"],
  defaultViewport: { width: 1440, height: 1000 },
  // ⚠️ O padrão são 30 s, e a foto de página inteira de uma tela longa passa
  // disso nesta máquina. Sessenta dá folga sem esconder travamento de verdade.
  protocolTimeout: 60_000,
});

/** Desfazer registrado no caminho: roda no `finally`, dê certo ou não. */
const aoTerminar = [];

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

  // 🔑 **A promessa "fecha quando eu fechar o navegador" é aqui que se prova.**
  // Sem marcar "manter conectado", a sessão tem de ficar em `sessionStorage`,
  // que morre com a janela. Antes ficava sempre em `localStorage`: fechar o
  // navegador não encerrava nada e, num computador compartilhado, a sessão
  // ficava aberta para o próximo. A API não tem como testar isto — a escolha
  // do armazenamento é do front.
  const semManter = await ondeMoraASessao(p);
  checar("sem 'manter conectado', a sessão morre com o navegador",
    semManter.sessao && !semManter.local, semManter);

  // E com a caixinha marcada, o contrário — que é o que a pessoa pediu.
  const p2 = await navegador.newPage();
  await p2.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
  await p2.evaluate(() => { localStorage.clear(); sessionStorage.clear(); });
  await p2.goto(`${WEB}/login`, { waitUntil: "networkidle2" });
  await p2.type('input[type="email"]', ADMIN.email);
  await p2.type('input[type="password"]', ADMIN.senha);
  const caixa = await p2.$('input[type="checkbox"]');
  checar("a tela de login oferece 'manter conectado'", caixa !== null);
  if (caixa) await caixa.click();
  await Promise.all([
    p2.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}),
    p2.click('button[type="submit"]'),
  ]);
  await new Promise((r) => setTimeout(r, 1200));
  const comManter = await ondeMoraASessao(p2);
  checar("com 'manter conectado', a sessão sobrevive ao fechamento",
    comManter.local && !comManter.sessao, comManter);
  // ⚠️ Não deixar cópia nos dois: duas fontes divergentes fariam a leitura
  // devolver um token velho depois de um logout parcial.
  checar("e fica num lugar só, nunca nos dois",
    comManter.local !== comManter.sessao, comManter);
  await p2.close();
  // ⚠️ `localStorage` é do domínio: o login em p2 trocou a sessão de TODAS as
  // abas. Voltar como admin na página principal antes de seguir.
  await entrar(p, ADMIN);
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

  // ⚠️ **Pelo DOM, nao pelo `innerText`.** Com os grupos recolhidos o
  // `display: none` tira os itens do texto visivel — e a pergunta aqui e "o
  // menu OFERECE estas telas?", nao "elas estao a vista neste instante".
  const menu = await p.evaluate(() =>
    [...document.querySelectorAll("aside a")].map((a) => a.textContent.trim()).join(" | "));
  checar("menu do admin traz Empresa", menu.includes("Empresa"));
  checar("menu do admin traz Papéis", menu.includes("Papéis"));
  checar("menu do admin traz Auditoria", menu.includes("Auditoria"));

  // 🔑 **Todo grupo comeca RECOLHIDO, inclusive o da tela aberta.** Antes ele
  // se expandia sozinho, e o menu ia abrindo grupos conforme se navegava ate
  // nao caber na altura da tela. Quem diz "voce esta aqui" e a cor do titulo.
  await irPara(p, `${WEB}/empresa`);
  await new Promise((r) => setTimeout(r, 1200));
  const grupoDaTela = () =>
    p.evaluate(() => {
      const b = [...document.querySelectorAll("aside button")]
        .find((x) => /administra/i.test(x.innerText));
      const link = [...document.querySelectorAll("aside a")]
        .find((x) => x.textContent === "Empresa");
      return { aberto: b?.getAttribute("aria-expanded"),
               ativo: !!b?.className.includes("menu-grupo-ativo"),
               visivel: link?.offsetParent !== null };
    });
  const antesDoClique = await grupoDaTela();
  checar("o grupo da tela aberta começa recolhido", antesDoClique.aberto === "false",
    antesDoClique);
  checar("mas o titulo dele diz onde se esta", antesDoClique.ativo, antesDoClique);
  await p.evaluate(() => {
    [...document.querySelectorAll("aside button")]
      .find((x) => /administra/i.test(x.innerText))?.click();
  });
  await new Promise((r) => setTimeout(r, 500));
  const depoisDoClique = await grupoDaTela();
  checar("um clique abre o grupo e mostra os itens",
    depoisDoClique.aberto === "true" && depoisDoClique.visivel === true, depoisDoClique);
  await irPara(p, `${WEB}/empresa`);
  await new Promise((r) => setTimeout(r, 1200));
  // ⚠️ A escolha e da PESSOA e sobrevive a navegacao — o que nao sobrevive
  // e o login, que recolhe tudo de novo.
  checar("e continua aberto ao voltar para a tela",
    (await grupoDaTela()).aberto === "true");

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
  // ⚠️ **Pelo DOM tambem, e aqui a razao e mais forte:** com os grupos
  // recolhidos, "nao aparece no texto visivel" passaria para QUALQUER item,
  // inclusive os que a pessoa tem. A checagem negativa ficaria verde sem
  // provar nada — que e o pior tipo de teste.
  const menuCozinha = await p.evaluate(() =>
    [...document.querySelectorAll("aside a")].map((a) => a.textContent.trim()).join(" | "));
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

  // ⚠️ Tipo novo tem de CHEGAR à tela. `TIPOS` (api/models/produtos.py) e
  // `TIPOS_PRODUTO` (web/lib/cadastros.ts) são listas separadas: mexer só numa
  // faz o servidor aceitar um tipo que ninguém consegue escolher. É a lição do
  // EAN na direção inversa — e essa não quebra nada, só nunca aparece.
  const tiposNaTela = await p.evaluate(() =>
    [...(document.querySelector("select")?.options ?? [])].map((o) => o.value));
  checar("a tela oferece os sete tipos de produto", tiposNaTela.length === 7, tiposNaTela);
  checar("inclusive utensílios e enxoval", tiposNaTela.includes("UTENSILIO"), tiposNaTela);

  // A ajuda do tipo é o que explica a escolha a quem cadastra; sem ela
  // "Utensílios" fica indistinguível de "Material de limpeza".
  await p.select("select", "UTENSILIO");
  await new Promise((r) => setTimeout(r, 300));
  const ajudaUtensilio = await textoVisivel(p);
  checar("e explica que utensílio não é consumido pela receita",
    /quebra, some e é reposto/i.test(ajudaUtensilio),
    ajudaUtensilio.slice(0, 200));

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
  // ⚠️ A tela do produto carrega em várias chamadas; sob carga ela ainda não
  // pintou depois de 1,5 s, e as checagens dos campos fiscais viravam
  // "nenhum rótulo existe" — que se lê como campo REMOVIDO.
  // ⚠️ E esperar por `span.rotulo` não esperava nada: esse seletor existe
  // igual no formulário de cadastro, a tela de onde se acabou de sair. A
  // espera casava com a página velha e devolvia na hora. **Espere por algo que
  // só existe na tela de DESTINO** — aqui, o rótulo "NCM".
  await p
    .waitForFunction(
      () => [...document.querySelectorAll("span.rotulo")].some(
        (r) => r.textContent?.trim() === "NCM"),
      { timeout: 20000 })
    .catch(() => {});

  // ⚠️ **O EAN existia no formulário e não tinha campo na tela.** Era enviado ao
  // salvar e lido pela conciliação da nota, mas ninguém conseguia ver nem
  // digitar: o dado só entrava pela importação do Omie. Campo que o servidor
  // aceita e a tela não oferece é campo morto — e some sem ninguém notar.
  const fiscais = await p.evaluate(() => {
    const rotulos = [...document.querySelectorAll("span.rotulo")].map((r) =>
      r.textContent?.trim() ?? "");
    return {
      ean: rotulos.some((r) => /EAN\/GTIN/i.test(r)),
      ncm: rotulos.includes("NCM"),
      cest: rotulos.includes("CEST"),
      marca: rotulos.includes("Marca"),
      peso: rotulos.some((r) => /^Peso l/i.test(r)),
      // O vínculo com o Omie é interno: não se mostra a quem cadastra.
      omie: /Vínculo com o Omie|Código interno/i.test(document.body.innerText),
    };
  });
  // ⚠️ Baixar os dados do produto que se esta olhando fica FORA do bloco de
  // edicao: levar isso para fora — conferir uma compra, discutir preco com o
  // fornecedor, responder ao contador — e coisa de quem CONSULTA.
  const baixarProduto = await p.evaluate(() =>
    [...document.querySelectorAll("button")].some(
      (b) => b.textContent?.trim() === "Baixar"));
  checar("a tela do produto oferece baixar os dados dele", baixarProduto);


  checar("o formulário do produto tem o código de barras (EAN/GTIN)", fiscais.ean, fiscais);
  checar("e os campos que vêm do cadastro do Omie",
    fiscais.ncm && fiscais.cest && fiscais.marca && fiscais.peso, fiscais);
  checar("sem expor o vínculo interno com o Omie", !fiscais.omie, fiscais);

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

  // ⚠️ **Os dois tipos de aviso somem sozinhos** — antes o erro ficava até
  // alguém fechar, e uma pilha que não se limpa acaba tapando a tela em uso. O
  // sucesso sai em 6 s; o erro, em 14 (frase mais longa). A barrinha embaixo
  // anuncia isso: sem ela, o aviso sumindo parece a tela piscando.
  const barra = await p.evaluate(() => {
    const el = document.querySelector("[data-aviso]");
    const b = el?.querySelector("span[aria-hidden]:not([class*='font-display'])");
    return { tem: !!b, transform: b ? getComputedStyle(b).transform : null };
  });
  checar("o aviso mostra quanto falta para sumir", barra.tem, barra);

  // ⚠️ Com o ponteiro em cima, o relógio PARA: era o medo real de fechar
  // sozinho — a mensagem sumir no meio da leitura.
  await p.hover("[data-aviso]");
  await new Promise((r) => setTimeout(r, 2500));
  const pausado = await p.evaluate(() => !!document.querySelector("[data-aviso]"));
  checar("e não some enquanto o ponteiro está em cima", pausado);

  // Tirado o ponteiro, o tempo volta a correr e ele sai sozinho.
  await p.mouse.move(5, 5);
  await new Promise((r) => setTimeout(r, 7000));
  const sumiu = await p.evaluate(() => !document.querySelector("[data-aviso='ok']"));
  checar("tirando o ponteiro, o aviso de sucesso some sozinho", sumiu);

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

  // ⚠️ **Este bloco RECARREGA a tela e sai dela** — por isso vem aqui, depois
  // de tudo o que dependia do estado do cadastro recém-salvo. Posto antes, o
  // `reload` apagava o aviso flutuante e derrubava cinco checagens que não têm
  // nada a ver com o PDV. É a regra que já valia: teste que desvia tem de vir
  // no fim, ou voltar.
  // ⚠️ **A marca só aparece com o envio LIGADO.** Controle para um recurso
  // desligado é ruído: quem cadastra um produto hoje não tem o que decidir
  // sobre um envio que não acontece. Aqui se prova o PORTÃO — com o envio
  // desligado (o padrão) a caixinha não existe; ligado, ela aparece.
  const marcaDoPdv = () =>
    p.evaluate(() => {
      const c = document.querySelector("#integrado_pdv");
      return { existe: !!c, marcado: c ? c.checked : null,
               rotulo: /Integrado com PDV/.test(document.body.innerText) };
    });
  // ⚠️ **Não SUPÕE que o envio está desligado — desliga.** A casa pode estar com
  // ele ligado (foi o que aconteceu na primeira rodada depois de o dono ligá-lo),
  // e o teste acusava a tela de mostrar uma marca que ela deve mesmo mostrar.
  // Garante a precondição em vez de supô-la, e devolve o que achou no fim.
  const { dados: pdvAntesMarca } = await api("GET", "/pdv/config", null, token);
  const comEnvioAssim = (ligado) => api("PUT", "/pdv/config", {
    modo: pdvAntesMarca?.modo ?? "simulado", ativa: pdvAntesMarca?.ativa ?? false,
    enviar_ao_pdv: ligado,
    agenda_frequencia: pdvAntesMarca?.agenda_frequencia ?? "MANUAL",
    agenda_hora: pdvAntesMarca?.agenda_hora ?? 4,
    agenda_janela_dias: pdvAntesMarca?.agenda_janela_dias ?? null,
  }, token);
  const reporEnvio = () => comEnvioAssim(!!pdvAntesMarca?.enviar_ao_pdv);
  // Registrado ANTES de mexer: se o roteiro estourar no meio, a casa não fica
  // com o envio num estado que ninguém escolheu.
  aoTerminar.push(reporEnvio);

  await comEnvioAssim(false);
  await p.reload({ waitUntil: "networkidle2" });
  await p
    .waitForFunction(
      () => [...document.querySelectorAll("span.rotulo")].some(
        (r) => r.textContent?.trim() === "NCM"),
      { timeout: 20000 })
    .catch(() => {});
  const semEnvio = await marcaDoPdv();
  checar("com o envio desligado, a marca do PDV nem aparece",
    !semEnvio.existe && !semEnvio.rotulo, semEnvio);
  await comEnvioAssim(true);
  await p.reload({ waitUntil: "networkidle2" });
  await p
    .waitForFunction(
      () => [...document.querySelectorAll("span.rotulo")].some(
        (r) => r.textContent?.trim() === "NCM"),
      { timeout: 20000 })
    .catch(() => {});
  const comEnvio = await marcaDoPdv();
  checar("ligado o envio, a marca aparece no cadastro",
    comEnvio.existe && comEnvio.rotulo, comEnvio);
  // Produto recém-criado pela tela não tem código do PDV: nasce desmarcado.
  checar("e um produto novo nasce desmarcado", comEnvio.marcado === false, comEnvio);

  // E nas tabelas de apoio, onde a marca é do SETOR (a impressora do PDV) e da
  // CATEGORIA (o grupo dele).
  await irPara(p, `${WEB}/cadastros?aba=setores`);
  await new Promise((r) => setTimeout(r, 1500));
  const apoioComEnvio = await p.evaluate(() =>
    /integrar ao PDV|tirar do PDV/.test(document.body.innerText));
  checar("e nas tabelas de apoio o setor também", apoioComEnvio);

  // A tela de Exportação: só existe com o envio ligado, e é onde a fila mora.
  await irPara(p, `${WEB}/exportacao`);
  await new Promise((r) => setTimeout(r, 2500));
  const exportacao = await p.evaluate(() => {
    const texto = document.body.innerText;
    const abas = [...document.querySelectorAll("nav button")].map((b) => b.textContent ?? "");
    return {
      titulo: /Exporta..o para o PDV/.test(texto),
      // As três abas do ciclo: o que falta, o que foi, e o que deu errado.
      pendentes: abas.some((a) => /^Pendentes \(/.test(a.trim())),
      integrados: abas.some((a) => /^Integrados \(/.test(a.trim())),
      erros: abas.some((a) => /^Erros \(/.test(a.trim())),
      // ⚠️ Não pode dizer que o envio está desligado com ele LIGADO.
      recusou: /envio ao PDV est. desligado/i.test(texto),
    };
  });
  checar("a tela de exportação para o PDV existe", exportacao.titulo, exportacao);
  checar("com as três abas do ciclo",
    exportacao.pendentes && exportacao.integrados && exportacao.erros, exportacao);
  checar("e com o envio ligado ela não diz que está desligado",
    !exportacao.recusou, exportacao);
  // A fila de envio tambem pagina — e aqui o corte e do NAVEGADOR de proposito:
  // ela e derivada da comparacao com o cardapio inteiro, entao nao ha `LIMIT`
  // no servidor que a barateie, e o botao Enviar precisa saber de TODOS os
  // pendentes, nao dos vinte a vista.
  const pagFila = await p.evaluate(() => {
    const rodape = [...document.querySelectorAll("main span")]
      .find((e) => /^\d+.\d+ de /.test(e.textContent || ""));
    return {
      temRodape: !!rodape,
      texto: rodape?.textContent?.trim() ?? "",
      linhas: document.querySelectorAll("main tbody tr").length,
    };
  });
  if (pagFila.temRodape) {
    const porPagina = Number(pagFila.texto.match(/^\d+.(\d+)/)?.[1] ?? 0);
    checar("a fila do PDV mostra so a pagina pedida",
      pagFila.linhas === porPagina, pagFila);
  } else {
    checar("fila curta nao ganha rodape de pagina", true);
  }

  await foto(p, "30c-exportacao-pdv");

  await reporEnvio();

  // ⚠️ Desligado, o item some do menu e a tela explica — porta que abre numa
  // tela inútil é pior que porta nenhuma.
  await comEnvioAssim(false);
  await irPara(p, `${WEB}/exportacao`);
  await new Promise((r) => setTimeout(r, 1600));
  const desligada = await p.evaluate(() => ({
    explica: /envio ao PDV est. desligado/i.test(document.body.innerText),
    noMenu: [...document.querySelectorAll("aside a")].some(
      (a) => a.getAttribute("href") === "/exportacao"),
  }));
  checar("desligado, a tela explica em vez de listar", desligada.explica, desligada);
  checar("e o item sai do menu", !desligada.noMenu, desligada);
  await reporEnvio();

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

  // 🔑 **A lista abre com o que esta EM USO.** O inativo aparecia junto, so com
  // a opacidade baixa — e numa base com historico ele e a maioria. A checagem
  // afirma a PROPRIEDADE, nao a contagem do dia: marcar a caixinha nunca DIMINUI
  // a lista, e o que ela acrescenta e inativo.
  const semInativos = await p.evaluate(() => document.querySelectorAll("main ul > li").length);
  await p.evaluate(() => [...document.querySelectorAll('input[type="checkbox"]')]
    .find((c) => c.closest("label")?.innerText.toLowerCase().includes("inativos"))?.click());
  await new Promise((r) => setTimeout(r, 1500));
  const comInativos = await p.evaluate(() => document.querySelectorAll("main ul > li").length);
  checar("mostrar inativos nunca encolhe a lista de apoio",
    comInativos >= semInativos, { semInativos, comInativos });
  // Desmarca: as checagens seguintes contam com a lista no estado padrao.
  await p.evaluate(() => [...document.querySelectorAll('input[type="checkbox"]')]
    .find((c) => c.closest("label")?.innerText.toLowerCase().includes("inativos"))?.click());
  await new Promise((r) => setTimeout(r, 1200));

  // 🔑 **"Poucos por natureza" era suposicao, e a base real desmentiu**: 184
  // locais, 86 categorias, 52 setores. A checagem nao afirma "tem rodape" (isso
  // seria o estado do dia, e some depois de uma limpeza): afirma a
  // PROPRIEDADE — havendo rodape, a pagina mostra no maximo o tamanho escolhido,
  // e virar a pagina troca as linhas.
  const pagLocais = await p.evaluate(() => {
    const rodape = [...document.querySelectorAll("main span")]
      .find((e) => /^\d+.\d+ de /.test(e.textContent || ""));
    const linhas = document.querySelectorAll("main ul > li").length;
    const proxima = document.querySelector('button[aria-label="Próxima página"]');
    return {
      temRodape: !!rodape,
      texto: rodape?.textContent?.trim() ?? "",
      linhas,
      primeira: document.querySelector("main ul > li")?.textContent?.trim() ?? "",
      podeVirar: !!proxima && !proxima.disabled,
    };
  });
  if (pagLocais.temRodape) {
    const porPagina = Number(pagLocais.texto.match(/^\d+.(\d+)/)?.[1] ?? 0);
    checar("a lista de apoio mostra so a pagina pedida",
      pagLocais.linhas === porPagina, pagLocais);
    if (pagLocais.podeVirar) {
      await p.evaluate(() =>
        document.querySelector('button[aria-label="Próxima página"]')?.click());
      await new Promise((r) => setTimeout(r, 400));
      const outra = await p.evaluate(() =>
        document.querySelector("main ul > li")?.textContent?.trim() ?? "");
      checar("e virar a pagina troca as linhas", outra !== pagLocais.primeira,
        { antes: pagLocais.primeira.slice(0, 40), depois: outra.slice(0, 40) });
    }
  } else {
    checar("lista de apoio curta nao ganha rodape de pagina", true);
  }

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
  // ⚠️ **O produto da ficha virou BUSCA.** Era um `<select>` alimentado por
  // `/produtos?tipo=PRODUZIDO`, que pagina: eram os 200 primeiros em ordem
  // alfabética. Ao importar o cardápio do PDV (627 pratos), o produto recém
  // criado deixou de estar na lista — e o `<select>` não tem como dizer isso:
  // a tela ficava certa e o formulário recusava salvar sem explicar por quê.
  const buscaProduto = await p.$('input[aria-label="Buscar produto produzido"]');
  checar("o produto da ficha se escolhe por busca", !!buscaProduto);
  await buscaProduto.type(`Tela bolo ${marca}`);
  await p.keyboard.press("Tab");
  await new Promise((r) => setTimeout(r, 1200));
  // ⚠️ `.toUpperCase()`: o nome do produto e normalizado pelo BANCO (migracao
  // 036, gatilho), entao o que a tela mostra nunca e o que a suite digitou.
  checar("e o Tab acha o prato desta rodada",
    (await p.evaluate(() =>
      document.querySelector('input[aria-label="Buscar produto produzido"]')?.value ?? ""))
      .includes(`Tela bolo ${marca}`.toUpperCase()),
    await p.evaluate(() =>
      document.querySelector('input[aria-label="Buscar produto produzido"]')?.value ?? ""));
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
  checar("e o Tab preenche a linha",
       itemEscolhido.includes(`Tela farinha ${marca}`.toUpperCase()),
    itemEscolhido);
  await numeros[2].type("500");
  const selectsUm = await p.$$("select");
  // Sem o select do produto sobraram dois: 0 rendimento_um, 1 unidade do item.
  await selectsUm[1].select("G");
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

    // A ficha existe para ser SEGUIDA, e quem segue está de pé na cozinha —
    // não na frente do monitor. Sem o papel, a receita fica presa numa tela
    // que ninguém leva para perto do fogão.
    await p.evaluate(() => {
      [...document.querySelectorAll("button")]
        .find((b) => /Imprimir ficha/i.test(b.textContent ?? ""))
        ?.click();
    });
    await new Promise((r) => setTimeout(r, 2000));
    const janelaFicha = await p.evaluate(() => {
      const d = document.querySelector('[role="dialog"]');
      const texto = d?.innerText ?? "";
      const marcado = [...(d?.querySelectorAll("[aria-pressed]") ?? [])].find(
        (b) => b.getAttribute("aria-pressed") === "true");
      return {
        abriu: !!d,
        titulo: d?.querySelector("h2")?.textContent ?? "",
        // ⚠️ O padrão da ficha é PDF: o destino dela é o papel, e abrir em
        // "planilha" faz escolher errado por inércia.
        // ⚠️ `textContent` junta os dois <span> do cartão sem separador —
        // "PDFPara ler, imprimir…". Quem tem a quebra é `innerText`, e aqui o
        // que se quer é só saber QUAL cartão está marcado.
        escolhido: (marcado?.textContent ?? "").trim().startsWith("PDF") ? "PDF" : "outro",
        botao: [...(d?.querySelectorAll("button") ?? [])].some((b) =>
          /^Baixar PDF/.test(b.textContent?.trim() ?? "")),
      };
    });
    checar("a ficha tem botão de imprimir", janelaFicha.abriu, janelaFicha);
    checar("e a janela dela já vem em PDF",
      janelaFicha.escolhido === "PDF" && janelaFicha.botao, janelaFicha);
    await p.evaluate(() => {
      document.querySelector('[role="dialog"] [aria-label="fechar"]')?.click();
    });
    await new Promise((r) => setTimeout(r, 500));

    // A cozinha vê a receita e não vê dinheiro — na tela, não só na API.
    await p.evaluate(() => localStorage.clear());
    await entrar(p, COZINHA);
    await p.goto(`${WEB}/fichas/${idFicha}`, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 1300));
    const textoCozinha = await textoVisivel(p);
    checar("cozinha vê a receita", /TELA FARINHA/i.test(textoCozinha),
    textoCozinha.slice(0, 80));
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
  // ⚠️ Montar a contagem virou tela própria (`/inventario/novo`): com quatro
  // filtros e a prévia, o formulário não cabia mais no topo da lista. Aqui se
  // consulta; lá se monta.
  await p.goto(`${WEB}/inventario`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1100));
  const listaInv = await p.evaluate(() => ({
    temBotao: [...document.querySelectorAll("a")].some(
      (a) => a.textContent?.trim() === "Nova contagem"),
    // ⚠️ O rodapé de paginação TAMBÉM tem um select ("Registros por página"):
    // procurar "algum select" acusaria o formulário que já não existe.
    semFormulario: ![...document.querySelectorAll("span.rotulo")]
      .some((r) => r.textContent?.trim() === "Local"),
  }));
  checar("a lista tem o botão de nova contagem", listaInv.temBotao, listaInv);
  checar("e não carrega mais o formulário de abertura", listaInv.semFormulario, listaInv);

  await irPara(p, `${WEB}/inventario/novo`);
  await new Promise((r) => setTimeout(r, 1800));
  const noNovo = await p.evaluate(() => {
    const rotulos = [...document.querySelectorAll("span.rotulo")].map((x) =>
      x.textContent?.trim());
    // ⚠️ **Pelo RÓTULO, nunca pela posição.** Era "a última caixinha da
    // página" — e o cartão "Quem vai contar" passou a ter caixinhas depois
    // dela, fazendo a checagem medir a escala de uma pessoa. Mesma armadilha
    // do "primeiro elemento que casa", pela outra ponta.
    const cega = [...document.querySelectorAll('input[type="checkbox"]')]
      .find((c) => /contagem cega/i.test(c.closest("label")?.innerText ?? ""));
    return {
      filtros: ["Locais", "Setores", "Categorias", "Tipos de produto"].filter((f) =>
        rotulos.includes(f)),
      cegaMarcada: cega?.checked ?? null,
      previa: /linha\(s\) para contar/.test(document.body.innerText),
    };
  });
  checar("a tela nova oferece os quatro filtros", noNovo.filtros.length === 4, noNovo.filtros);
  // ⚠️ Cega MARCADA por padrão: ver o esperado transforma a contagem em
  // conferência, e a opção certa não pode depender de alguém lembrar.
  checar("com a contagem cega já marcada", noNovo.cegaMarcada === true, noNovo);
  checar("e a prévia diz quantas linhas viriam", noNovo.previa, noNovo);
  await foto(p, "28-inventario-novo");

  // Estreitar por LOCAL tem de mudar o número da prévia — é o que prova que o
  // filtro chega ao servidor, e não só ao estado da tela.
  const totalDaPrevia = () =>
    p.evaluate(() =>
      Number(document.body.innerText.match(/(\d+)\s*linha\(s\) para contar/)?.[1] ?? -1));
  const semFiltro = await totalDaPrevia();
  await p.evaluate((nome) => {
    const alvo = [...document.querySelectorAll("label")].find((l) =>
      l.textContent?.trim() === nome);
    alvo?.querySelector("input")?.click();
  }, localInv?.nome);
  await new Promise((r) => setTimeout(r, 1600));
  const comLocal = await totalDaPrevia();
  checar("escolher um local estreita a prévia", comLocal > 0 && comLocal <= semFiltro,
    [semFiltro, comLocal]);

  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (x) => x.textContent?.startsWith("Abrir contagem"));
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 2200));
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
  // ⚠️ "O primeiro select da tela" deixa de identificar assim que a base tem
  // dado de VERDADE: numa contagem de 257 linhas a primeira é a que a ordem
  // alfabética entregar, e caiu num rascunho do catálogo do Omie — produto SEM
  // unidade de estoque, cujo seletor legitimamente não tem o que oferecer. A
  // checagem acusava a tela de um defeito que era do dado. Cada suíte pergunta
  // pelo registro DELA. (E o nome está em MAIÚSCULAS: quem garante é o gatilho.)
  const seletorUnidade = await p.evaluate((nome) => {
    const cartao = [...document.querySelectorAll("li")].find(
      (l) => l.querySelector("p")?.textContent?.trim().toUpperCase() === nome);
    if (!cartao) return { achouCartao: false };
    const s = [...cartao.querySelectorAll("select")].find(
      (x) => x.closest("label")?.textContent?.includes("Unidade"));
    return s
      ? {
          achouCartao: true,
          desabilitado: s.disabled,
          opcoes: [...s.options].map((o) => o.value),
          caminho: !!document.body.innerText.match(/contar em outra embalagem/i),
        }
      : { achouCartao: true, semSeletor: true };
  }, `Inv tela ${m4}`.toUpperCase());
  checar("a contagem tem o produto desta rodada", seletorUnidade?.achouCartao === true,
    seletorUnidade);
  checar("o seletor de unidade não fica travado",
    seletorUnidade && seletorUnidade.desabilitado === false, seletorUnidade);
  checar("e traz as unidades da mesma grandeza, sem cadastro nenhum",
    (seletorUnidade?.opcoes?.length ?? 0) > 1, seletorUnidade?.opcoes);
  checar("com o caminho para cadastrar outra embalagem", seletorUnidade?.caminho === true,
    seletorUnidade);
  await foto(p, "20c-contagem");

  // Digitar grava sozinho: contagem que só existe na tela até um "salvar tudo"
  // no fim é contagem que se perde.
  // ⚠️ No cartão DESTA rodada, não no primeiro da lista: escrever 7 no rascunho
  // que a ordem alfabética entregou deixaria contagem em produto de terceiro.
  await p.evaluate((nome) => {
    const cartao = [...document.querySelectorAll("li")].find(
      (l) => l.querySelector("p")?.textContent?.trim().toUpperCase() === nome);
    const c = (cartao ?? document).querySelector('input[inputmode="decimal"]');
    const set = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    // ⚠️ Sem FOCAR antes, `blur()` não dispara nada — e é o blur que grava.
    c.focus();
    set.call(c, "7");
    c.dispatchEvent(new Event("input", { bubbles: true }));
    c.blur();
  }, `Inv tela ${m4}`.toUpperCase());
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
  // ⚠️ **Garante a ficha em vez de supô-la.** Numa base recém-limpa não há ficha
  // homologada nenhuma neste ponto do roteiro — a que a fase do CMV homologa só
  // aparece muito depois. O bloco todo passava a depender do resíduo da rodada
  // anterior, que é justamente o que uma suíte não pode fazer.
  const { dados: fichasProd } = await api("GET", "/fichas", null, token);
  let homologada = (fichasProd ?? []).find((f) => f.status === "HOMOLOGADA");
  if (!homologada) {
    const marcaFicha = String(Date.now()).slice(-5);
    const { dados: insFicha } = await api("POST", "/produtos",
      { nome: `Agenda insumo ${marcaFicha}`, tipo: "INSUMO", um_estoque: "KG" }, token);
    const { dados: prodFicha } = await api("POST", "/produtos",
      { nome: `Agenda preparo ${marcaFicha}`, tipo: "PRODUZIDO", um_estoque: "UN" }, token);
    const { dados: novaFicha } = await api("POST", "/fichas", {
      id_produto: prodFicha.id, rendimento_qtd: 1, rendimento_um: "UN", porcoes: 1,
      itens: [{ id_insumo: insFicha.id, qtd_bruta: 0.2, um: "KG" }],
    }, token);
    await api("POST", `/fichas/${novaFicha.id}/homologar`, null, token);
    homologada = { id: novaFicha.id, id_produto: prodFicha.id, status: "HOMOLOGADA" };
  }
  checar("há ficha homologada para a agenda usar", !!homologada, fichasProd?.length);
  const amanhaISO = diaLocal(1);
  await api("POST", "/producao-agenda",
    { id_produto: homologada.id_produto, data_prevista: amanhaISO, quantidade: 3 }, token);

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
    !/Local não encontrado/i.test(textoInv) && /CONTAGEM/i.test(textoInv),
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
      tipos: [
        "Entrada", "Saída", "Perda", "Transferência",
        "Ajuste de estoque", "Ajuste de custo",
      ].filter((t) => texto.includes(t)),
      escolhido: escolhido?.textContent?.trim().slice(0, 8) ?? null,
      temCusto: /custo unit[áa]rio/i.test(texto),
    };
  });
  // 🔑 **CINCO tipos, não quatro.** O ajuste de custo é mais um item da mesma
  // tela — mesma forma dos outros, um produto por vez. Contar aqui é o que
  // pega o tipo que some da lista por um erro de permissão ou de rótulo.
  checar("a tela de ajustes oferece os seis tipos", telaAjustes.tipos.length === 6,
    telaAjustes.tipos);
  checar("inclusive os dois que declaram a verdade em vez do movimento",
    telaAjustes.tipos.some((t) => /ajuste de custo/i.test(t))
      && telaAjustes.tipos.some((t) => /ajuste de estoque/i.test(t)),
    telaAjustes.tipos);

  // O ajuste de ESTOQUE pede a quantidade que a prateleira TEM — não o quanto
  // se moveu. É o que o separa de Entrada e Saída.
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      /ajuste de estoque/i.test(x.textContent ?? ""));
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 700));
  const formSaldo = await p.evaluate(() =>
    [...document.querySelectorAll(".rotulo")].map((r) => r.textContent?.trim() ?? ""));
  checar("no ajuste de estoque pede a quantidade que REALMENTE tem",
    formSaldo.some((r) => /realmente tem/i.test(r)), formSaldo);


  // O formulário se molda ao tipo. No custo isso quer dizer: SEM quantidade
  // (nada se move) e COM o custo certo.
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      /ajuste de custo/i.test(x.textContent ?? ""));
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 700));
  const formCusto = await p.evaluate(() => ({
    rotulos: [...document.querySelectorAll("span.rotulo, .rotulo")]
      .map((r) => r.textContent?.trim() ?? ""),
    texto: document.body.innerText,
  }));
  // ⚠️ Quantidade some de propósito: mostrá-la desabilitada sugeriria que
  // alguma quantidade se move, que é justamente o que NÃO acontece aqui.
  checar("no ajuste de custo não há campo de quantidade",
    !formCusto.rotulos.includes("Quantidade"), formCusto.rotulos);
  checar("e há o campo do custo médio certo",
    formCusto.rotulos.some((r) => /custo m[ée]dio certo/i.test(r)), formCusto.rotulos);
  checar("com a tela dizendo que a quantidade não muda",
    /quantidade n[ãa]o\s+muda/i.test(formCusto.texto),
    formCusto.texto.slice(0, 400));

  // ⚠️ **Voltar para /ajustes antes de seguir.** O bloco abaixo continua o
  // lançamento avulso e supõe estar nessa tela — sem isto ele procura os
  // campos numa página que não os tem e a suíte MORRE, longe da causa. Mesma
  // família da lição do localStorage: quem desvia, devolve.
  await irPara(p, `${WEB}/ajustes`);
  await new Promise((r) => setTimeout(r, 800));
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
    preencheu.includes(`Est tela ${m4}`.toUpperCase()), preencheu);

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
  // ⚠️ Escolhe pelo nome COMPLETO, com o marcador desta rodada. Antes procurava
  // só por "Est tela" — e produto com movimento não é apagado, vira inativo, de
  // modo que a base acumula um por rodada. A partir da segunda, o clique caía
  // no produto de OUTRO teste: a entrada de 10 kg ia para ele, o produto desta
  // rodada ficava com saldo zero e a checagem acusava a tela de não gravar.
  // Mesma regra das suítes de API: cada teste procura o registro DELE.
  // ⚠️ **Refina DENTRO da janela antes de clicar.** A janela abriu com "Est",
  // que numa base com várias rodadas traz dezenas de "Est tela NNNNN" — e o
  // produto desta rodada pode nem estar na página exibida. Digitar o marcador
  // no campo da própria janela é o que quem usa faria, e é o que garante que o
  // clique cai no registro DESTE teste. (Clicar no primeiro da lista mandaria a
  // entrada de 10 kg para o produto de outro teste — foi esse o bug.)
  await p.evaluate((alvo) => {
    const d = document.querySelector('[role="dialog"]');
    const campo = d?.querySelector("input");
    if (!campo) return;
    const set = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    set.call(campo, alvo);
    campo.dispatchEvent(new Event("input", { bubbles: true }));
  }, `Est tela ${m4}`.toUpperCase());
  await new Promise((r) => setTimeout(r, 1400));
  await p.evaluate((alvo) => {
    const d = document.querySelector('[role="dialog"]');
    if (!d) return;
    [...d.querySelectorAll("li button")].find((b) => b.textContent.includes(alvo))?.click();
  }, `Est tela ${m4}`.toUpperCase());
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

  // 🔑 **O seletor de local oferecia TODOS os locais da casa** — 93 numa base
  // real — enquanto o produto costuma estar em UM. Escolher o errado não dava
  // erro na hora: numa saída, o razão registrava a baixa por um local onde o
  // insumo nunca passou, criando saldo NEGATIVO com custo provisório. É o
  // mesmo defeito que a produção já teve.
  //
  // ⚠️ A checagem só vale AQUI, depois da entrada acima: antes de o produto
  // ter saldo não há o que filtrar. E vale no ajuste de estoque, não na
  // entrada — nesta a lista continua inteira de propósito, porque a primeira
  // entrada de um produto novo não tem saldo em lugar nenhum.
  const totalDeLocais = await p.evaluate(
    () => document.querySelectorAll("select")[0]?.options.length ?? 0);
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) =>
      /ajuste de estoque/i.test(x.textContent ?? ""));
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 600));
  const campoLocal = await p.$('input[aria-label="Buscar produto"]');
  if (campoLocal) {
    await campoLocal.type(`Est tela ${m4}`);
    await p.keyboard.press("Tab");
    await new Promise((r) => setTimeout(r, 1600));
  }
  const apos = await p.evaluate(() => {
    const s = document.querySelectorAll("select")[0];
    return {
      total: s?.options.length ?? 0,
      rotulos: [...(s?.options ?? [])].map((o) => o.textContent?.trim() ?? "").slice(0, 3),
    };
  });
  // Não afirmo um número: afirmo que ENCOLHEU, que é o que importa.
  checar("o local passa a oferecer só onde o produto tem saldo",
    apos.total > 0 && apos.total < totalDeLocais, { totalDeLocais, ...apos });
  // A quantidade no rótulo é o que faz a escolha ser consciente em vez de um
  // chute entre nomes de prateleira.
  checar("e mostra a quantidade ao lado do nome do local",
    apos.rotulos.some((r) => /—\s*\d/.test(r)), apos.rotulos);
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

  // ⚠️ Lançar saiu da lista para `/vendas/lancar`. Os dois formulários ocupavam
  // a primeira dobra e as vendas — o assunto da página — começavam abaixo do
  // campo de colar texto; com 1.375 vendas num mês isso é a tela errada.
  await p.goto(`${WEB}/vendas/lancar`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  const doc6 = `TELA-${m6}`;
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")]
      .find((x) => x.textContent?.trim() === "Colar planilha");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 500));
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
  await new Promise((r) => setTimeout(r, 500));
  const textoPrevia = await p.evaluate(() => document.body.innerText);
  checar("a tela reconhece a linha colada", /1 linha\(s\) reconhecida/.test(textoPrevia),
    textoPrevia.match(/.{0,40}reconhecid.{0,30}/)?.[0]);
  // ⚠️ A prévia mostra o que o sistema ENTENDEU, não o que foi colado: separador
  // errado vira uma linha só com tudo dentro, e sem isto só apareceria depois
  // de gravar.
  checar("e a prévia mostra a linha entendida", /Prato de teste/.test(textoPrevia),
    textoPrevia.slice(0, 120));
  await foto(p, "24-vendas-lancar");
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find((x) => x.textContent === "Importar");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 2200));
  const textoImport = await p.evaluate(() => document.body.innerText);
  checar("importa a venda pela tela", /1 venda\(s\) importada/.test(textoImport),
    textoImport.slice(0, 160));
  checar("e volta para a lista", /\/vendas$/.test(new URL(p.url()).pathname) ||
    p.url().endsWith("/vendas"), p.url());
  await foto(p, "24-vendas-importada");

  // ⚠️ **A busca do PDV vive na tela do ASSUNTO**, como o "Buscar no Omie" de
  // Compras. Quem abre Vendas para ver as vendas nao vai lembrar que a busca
  // mora em Integracoes -- e venda nao buscada e receita faltando no CMV.
  const botoesVendas = await p.evaluate(() =>
    [...document.querySelectorAll("button")].map((b) => b.textContent?.trim() ?? ""));
  checar("Vendas tem o botao Buscar no PDV",
    botoesVendas.some((x) => /Buscar no PDV/i.test(x)), botoesVendas.slice(0, 8));

  // ⚠️ A busca vai ao SERVIDOR. Com 1.375 vendas, filtrar a página carregada
  // acharia o documento só quando ele já estivesse na tela.
  await p.evaluate((d) => {
    const alvo = [...document.querySelectorAll("input")]
      .find((c) => c.placeholder?.includes("documento"));
    if (alvo) {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
      setter.call(alvo, d);
      alvo.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }, doc6);
  await new Promise((r) => setTimeout(r, 1400));
  checar("a busca da lista acha a venda desta rodada",
    (await textoVisivel(p)).includes(doc6), (await textoVisivel(p)).slice(0, 120));

  // A venda inteira numa página só: itens, custo congelado e o que saiu do
  // estoque. Antes a lista mostrava data, origem e total — e mais nada.
  const { dados: minhas } = await api("GET", `/vendas?busca=${doc6}`, null, token);
  checar("a lista devolve exatamente a venda buscada", minhas.length === 1, minhas.length);
  await p.goto(`${WEB}/vendas/${minhas[0].id}`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1400));
  const textoDet = await textoVisivel(p);
  checar("o detalhe da venda abre", /Receita/i.test(textoDet) && textoDet.includes(doc6),
    textoDet.slice(0, 140));
  // ⚠️ Procura o registro DESTA rodada, pelo nome com marca de tempo. "O
  // produto que contém X" cairia no de outra rodada — produto com movimento não
  // é apagado, vira inativo, e a base acumula um por rodada.
  checar("com o prato vendido", textoDet.includes(`Cmv tela prato ${m6}`.toUpperCase()),
    textoDet.slice(0, 220));
  checar("o custo teórico aparece", /Custo te[óo]rico/i.test(textoDet));
  // 10 pratos × 5,00 de ficha = 50,00 — o congelado, não o custo de hoje.
  checar("e vale os 50,00 da ficha", /50,00/.test(textoDet), textoDet.slice(0, 300));
  checar("o movimento no estoque aparece", /Movimento no estoque/i.test(textoDet));
  await foto(p, "24b-venda-detalhe");

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
  // ⚠️ **O modo volta ao que era no fim.** Esta fase exercita a importação
  // sobre as FIXTURES, e para isso a integração tem de estar em `simulado`.
  // Numa base onde o dono já configurou a conta de verdade, deixar como estava
  // faria o teste sincronizar 3.670 notas reais — e a conta do Omie bloqueia
  // quem consome demais. Trocar só o MODO não toca na credencial: a chave
  // guardada continua lá (é o que o `PUT /omie/config` sem `app_key` faz).
  const { dados: omieAntes } = await api("GET", "/omie/config", null, token);
  const modoOriginal = omieAntes?.modo ?? "simulado";
  if (modoOriginal !== "simulado") {
    await api("PUT", "/omie/config", { modo: "simulado", ativa: true }, token);
    // ⚠️ O restauro fica registrado ANTES de qualquer checagem, e roda no
    // `finally` do roteiro. Repor só no fim do bloco não bastou: uma quebra no
    // meio da fase deixou a integração em `simulado`, e a busca do dono passou
    // a não trazer nota nenhuma sem que nada explicasse por quê. É a mesma
    // lição do `preservar_credenciais` no lado da API.
    aoTerminar.push(() => api("PUT", "/omie/config",
      { modo: modoOriginal, ativa: true }, token));
  }
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
  // ⚠️ A fila de conciliação é da CASA INTEIRA e vem do servidor — antes a tela
  // somava só as notas da página carregada, e numa base com centenas de notas a
  // pendente caía na página 4 e o botão sumia. O teste confere pelo mesmo
  // caminho que a tela usa.
  const { dados: filaPendente } = await api("GET", "/notas/pendencias", null, token);
  checar("a fila de conciliação vem do servidor, não da página",
    Array.isArray(filaPendente), filaPendente);
  if ((filaPendente ?? []).length > 0) {
    checar("e a tela oferece reconciliar quando há pendência",
      /pendente/i.test(textoCompras), textoCompras.slice(0, 160));
  } else {
    checar("e a tela oferece reconciliar quando há pendência", true,
      "nenhum item pendente nesta base");
  }
  await foto(p, "28-compras-sincronizado");

  // Abre a nota da fixture e confere que o lançamento está barrado. ⚠️ Procura
  // pelo número: numa base com notas de uma conta real, a 4812 fica fora da
  // primeira página e o clique não achava botão nenhum — o teste então lia o
  // cabeçalho da casa e falhava sem dizer por quê.
  const campoBuscaNota = (await p.$$('input[aria-label="Buscar nota"]'))[0];
  checar("a lista de notas tem busca", !!campoBuscaNota);
  await campoBuscaNota.type("4812");
  await new Promise((r) => setTimeout(r, 1400));
  // A nota agora abre em PÁGINA PRÓPRIA: o item da lista é um link.
  const linkNota = await p.evaluate(() => {
    const a = [...document.querySelectorAll("a")].find((x) =>
      x.textContent.includes("NF 4812"));
    return a ? a.getAttribute("href") : null;
  });
  checar("a nota da lista leva para a página dela", !!linkNota, linkNota);
  await irPara(p, WEB + linkNota);
  await new Promise((r) => setTimeout(r, 1200));
  const textoNota = await p.evaluate(() => document.body.innerText);
  checar("a nota abre com os itens", /CAFE EM GRAO/i.test(textoNota), textoNota.slice(0, 100));
  // O que o dono pediu: as três áreas, no mesmo modelo da digitação.
  const areasNota = await p.evaluate(() => {
    const titulos = [...document.querySelectorAll("h2, h3")].map((h) => h.textContent?.trim());
    return {
      cabecalho: titulos.includes("Cabeçalho"),
      itens: titulos.includes("Itens"),
      total: titulos.includes("Total"),
      somaVisivel: /Total da nota/i.test(document.body.innerText),
    };
  });
  checar("a página tem cabeçalho, itens e total", areasNota.cabecalho && areasNota.itens
    && areasNota.total, areasNota);
  checar("e o total da nota aparece somado", areasNota.somaVisivel, areasNota);
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
  // Um arquivo só: a tela navega para a nota, que é o próximo passo de quem
  // importou. Esperar o ENDEREÇO mudar é mais confiável que esperar um tempo.
  for (const ate = Date.now() + 9000; Date.now() < ate; ) {
    if (/\/compras\/\d+$/.test(p.url())) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  checar("o XML importa pela tela e abre a nota",
    /\/compras\/\d+$/.test(p.url()), p.url());
  // A navegação termina antes de a nota carregar: esperar o ITEM aparecer, não
  // um tempo fixo, senão o teste lê a tela ainda vazia e culpa o sistema.
  await esperarTexto(p, "AZEITE EXTRA VIRGEM", 9000);
  const textoXml = await p.evaluate(() => document.body.innerText);
  checar("a nota abre com o item do XML",
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

  // O mesmo arquivo de novo: a chave da NF-e é que impede a duplicação. Volta
  // para a lista, que é onde mora a porta do XML.
  await irPara(p, `${WEB}/compras`);
  await new Promise((r) => setTimeout(r, 1100));
  await (await p.$('input[type="file"]')).uploadFile(caminhoXml);
  await new Promise((r) => setTimeout(r, 2500));
  const textoRepetido = await p.evaluate(() => document.body.innerText);
  checar("o mesmo XML não entra duas vezes",
    /repetida|já tinha sido importada/i.test(textoRepetido), textoRepetido.slice(0, 200));
  checar("o arquivo aparece com o resultado", /Arquivos lidos/i.test(textoRepetido));

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
  // A digitação tem PÁGINA PRÓPRIA: o formulário é longo, e aberto dentro da
  // lista empurrava as notas para fora da tela.
  await irPara(p, `${WEB}/compras`);
  await new Promise((r) => setTimeout(r, 1100));
  const linkDigitar = await p.evaluate(() => {
    const a = [...document.querySelectorAll("a")].find((x) =>
      x.textContent?.trim() === "Digitar nota");
    return a ? a.getAttribute("href") : null;
  });
  checar("digitar nota leva para a página dela", linkDigitar === "/compras/nova", linkDigitar);
  await irPara(p, `${WEB}/compras/nova`);
  await new Promise((r) => setTimeout(r, 1200));
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

  // Corrigir a nota digitada, pela tela, antes de ela virar estoque. O botão
  // virou LINK para a página de correção — a nota inteira já tem endereço.
  const linkCorrigir = await p.evaluate(() => {
    const a = [...document.querySelectorAll("a")].find((x) => x.textContent?.trim() === "Corrigir");
    return a ? a.getAttribute("href") : null;
  });
  checar("a nota digitada oferece o caminho da correção",
    /\/compras\/\d+\/editar$/.test(linkCorrigir ?? ""), linkCorrigir);
  await irPara(p, WEB + linkCorrigir);
  await new Promise((r) => setTimeout(r, 1400));
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
  const { dados: notasDoTesteXml } = await api("GET", "/notas?limite=60", null, token);
  for (const n of notasDoTesteXml ?? []) {
    if (n.chave_nfe === chaveNota || (n.origem === "MANUAL" && !n.numero)) {
      await api("DELETE", `/notas/${n.id}`, null, token);
    }
  }

  // Devolve a integração ao modo em que o dono a deixou. O `finally` faria
  // isso de qualquer jeito; aqui é para poder AFIRMAR que voltou.
  if (modoOriginal !== "simulado") {
    await api("PUT", "/omie/config", { modo: modoOriginal, ativa: true }, token);
    const { dados: omieDepois } = await api("GET", "/omie/config", null, token);
    checar("o modo da integração volta como estava", omieDepois?.modo === modoOriginal,
      omieDepois?.modo);
    checar("e a credencial continua configurada", omieDepois?.configurada === true, omieDepois);
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
      situacao: /período (aberto|fechado)/i.test(texto),
      fecha: /a conta fecha/i.test(texto),
      naoFecha: /A conta não fecha/i.test(texto),
    };
  });
  checar("a movimentação mostra inicial, entradas, saídas e final", mov.colunas, mov);
  checar("e diz se o período está aberto ou congelado", mov.situacao, mov);
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

  // ---- Baixar deixou de ser um clique cego ----
  // ⚠️ O botão de /produtos despejava os 3.226 do cadastro, SEMPRE. Agora abre
  // uma janela com os filtros pertinentes ao processo e a escolha do formato.
  // Quem diz quais são os filtros é o servidor: uma lista escrita no front
  // divergiria calada, e o arquivo sairia com mais linhas do que se pediu.
  const { dados: catalogo } = await api("GET", "/exportar/catalogo", null, token);
  checar("o servidor publica o catálogo de relatórios",
    Array.isArray(catalogo) && catalogo.length >= 8, catalogo?.length);
  const doCadastro = (catalogo ?? []).find((r) => r.chave === "produtos");
  checar("e cada relatório declara os filtros dele",
    (doCadastro?.filtros ?? []).map((f) => f.nome).includes("tipos_produto"),
    doCadastro?.filtros?.map((f) => f.nome));

  await p.goto(`${WEB}/produtos`, { waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1800));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((x) => /^Baixar/i.test(x.textContent?.trim() ?? ""))
      ?.click();
  });
  await new Promise((r) => setTimeout(r, 2400));
  const janelaExp = await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    const rotulos = [...(d?.querySelectorAll("span.rotulo") ?? [])].map((x) =>
      x.textContent?.trim());
    return {
      abriu: !!d,
      titulo: d?.querySelector("h2")?.textContent ?? "",
      rotulos,
      // A prévia diz quantas linhas viriam ANTES do botão.
      previa: /linha\(s\) neste recorte/.test(d?.innerText ?? ""),
      formatos: /Planilha/.test(d?.innerText ?? "") && /PDF/.test(d?.innerText ?? ""),
      caixinhas: (d?.querySelectorAll('input[type="checkbox"]') ?? []).length,
    };
  });
  checar("o Baixar abre a janelaExp de exportação", janelaExp.abriu, janelaExp);
  checar("com os filtros do processo, em escolha múltipla",
    janelaExp.rotulos.includes("Tipos de produto") && janelaExp.caixinhas > 3, janelaExp);
  checar("e a escolha entre planilha e PDF", janelaExp.formatos, janelaExp);
  checar("com a prévia de quantas linhas viriam", janelaExp.previa, janelaExp);
  await foto(p, "30b-exportar");

  // ⚠️ **A janela tem de CABER na tela.** Ela era do tamanho do conteúdo, e a
  // de exportação — cinco filtros — passava de mil pixels: num notebook os
  // últimos campos e o botão de baixar ficavam fora, e não havia barra de
  // rolagem em lugar nenhum (o corpo da página fica travado com a janela
  // aberta). A altura de 1000 do resto da bateria escondia isso, então esta
  // checagem MEDE numa tela de notebook de verdade.
  await p.setViewport({ width: 1440, height: 760 });
  await new Promise((r) => setTimeout(r, 700));
  const coube = await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    if (!d) return { achou: false };
    const corpo = d.children[1];
    corpo.scrollTop = corpo.scrollHeight;
    const botao = [...d.querySelectorAll("button")].find((b) =>
      /^Baixar (planilha|PDF)/.test(b.textContent?.trim() ?? ""));
    const cartao = d.getBoundingClientRect();
    const bb = botao?.getBoundingClientRect();
    return {
      achou: true,
      cabe: cartao.bottom <= window.innerHeight + 1 && cartao.top >= -1,
      rola: corpo.scrollHeight > corpo.clientHeight + 1,
      botaoAlcancavel: !!bb && bb.bottom <= window.innerHeight + 1 && bb.top >= 0,
    };
  });
  checar("a janela cabe na tela de um notebook", coube.cabe, coube);
  checar("com o miolo rolando por dentro", coube.rola, coube);
  // O botão fica FORA da rolagem: rolado até o fim, ele continua onde estava.
  checar("e o botão de baixar sempre à vista", coube.botaoAlcancavel, coube);
  await p.setViewport({ width: 1440, height: 1000 });
  await new Promise((r) => setTimeout(r, 500));
  // ⚠️ Fechar antes de seguir: janela aberta trava a rolagem do corpo, e o
  // bloco seguinte mediria uma tela que não rola.
  await p.evaluate(() => {
    document.querySelector('[role="dialog"] [aria-label="fechar"]')?.click();
  });
  await new Promise((r) => setTimeout(r, 600));

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
  // ⚠️ O rótulo encurtou de "Baixar planilha" para "Baixar" quando o botão
  // deixou de baixar e passou a ABRIR a janela — prometer planilha num botão
  // que agora também gera PDF seria mentir no próprio rótulo. A checagem
  // procura o botão, não a frase antiga.
  for (const [rota, nome] of [["/estoque", "estoque"], ["/cmv", "CMV"], ["/produtos", "produtos"]]) {
    await p.goto(WEB + rota, { waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 1600));
    const tem = await p.evaluate(() =>
      [...document.querySelectorAll("button")].some((b) =>
        /^Baixar/i.test(b.textContent?.trim() ?? "")));
    checar(`${nome} oferece baixar`, tem);
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

  console.log("10z. grupos do CMV: separar o que não é comida");
  // A casa monta os próprios grupos por tipo de produto. O que se prova aqui é
  // o que a tela promete: o tipo já usado aparece TRAVADO, dizendo onde está —
  // deixar escolher para depois levar 409 é fazer a pessoa descobrir a regra
  // errando.
  const marcaG = String(Date.now()).slice(-5);
  const gruposCriados = [];
  aoTerminar.push(async () => {
    for (const id of gruposCriados) await api("DELETE", `/cmv/grupos/${id}`, null, token);
  });

  // ⚠️ **Sem `?aba=`, abre a PRIMEIRA aba.** O padrão estava escrito à mão como
  // "locais" e entrar pelo menu caía na SEGUNDA, com a primeira ali do lado
  // marcada como não escolhida.
  await irPara(p, `${WEB}/cadastros`);
  await new Promise((r) => setTimeout(r, 1600));
  // ⚠️ Quem responde "que aba está aberta" é a FRASE que a tela mostra abaixo do
  // título — cada aba tem a sua. Procurar o botão marcado esbarra no menu
  // lateral, que também é feito de botões.
  const abaInicial = await p.evaluate(() => {
    const texto = document.body.innerText;
    return {
      setores: /Organização do trabalho/i.test(texto),
      locais: /Onde a coisa fica fisicamente/i.test(texto),
      url: location.search,
    };
  });
  checar("entrar em Tabelas de apoio abre a PRIMEIRA aba (Setores)",
    abaInicial.setores && !abaInicial.locais, abaInicial);

  await irPara(p, `${WEB}/cadastros?aba=grupos-cmv`);
  await new Promise((r) => setTimeout(r, 1800));
  checar("a aba Grupos do CMV existe em Tabelas de apoio",
    await p.evaluate(() => /grupos do cmv/i.test(document.body.innerText)));

  // ⚠️ A escolha que muda o NÚMERO: desmarcada, os tipos do grupo saem do CMV
  // real. Precisa estar à vista de quem monta o grupo, não escondida.
  const caixaCmv = await p.evaluate(() => {
    const rotulo = [...document.querySelectorAll("label")]
      .find((l) => /considerar no CMV real/i.test(l.textContent ?? ""));
    return {
      existe: !!rotulo,
      marcada: rotulo?.querySelector("input")?.checked ?? null,
      explica: /FICA DE FORA do CMV/i.test(document.body.innerText)
        || /entra na conta do CMV/i.test(document.body.innerText),
    };
  });
  checar("o grupo escolhe se entra no CMV real", caixaCmv.existe, caixaCmv);
  checar("marcada por padrão no grupo novo", caixaCmv.marcada === true, caixaCmv);
  checar("e a tela explica o que cada estado faz", caixaCmv.explica, caixaCmv);

  // Cria um grupo pela TELA, com um tipo livre.
  const { dados: livresAntes } = await api("GET", "/cmv/grupos/tipos-livres", null, token);
  const tipoLivre = (livresAntes?.tipos ?? [])[0];
  checar("há tipo de produto livre para o teste usar", !!tipoLivre, livresAntes);
  if (tipoLivre) {
    await p.evaluate((nome) => {
      const campo = [...document.querySelectorAll("input")]
        .find((i) => i.placeholder?.includes("Material de limpeza"));
      if (!campo) return;
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, "value").set;
      setter.call(campo, nome);
      campo.dispatchEvent(new Event("input", { bubbles: true }));
    }, `Teste tela ${marcaG}`);
    await p.evaluate((tipo) => {
      document.querySelector(`#tipo-novo-${tipo}`)?.click();
    }, tipoLivre);
    await new Promise((r) => setTimeout(r, 400));
    await p.evaluate(() => {
      [...document.querySelectorAll("button")]
        .find((b) => b.textContent === "Criar grupo")?.click();
    });
    await new Promise((r) => setTimeout(r, 1800));

    const { dados: depoisCriar } = await api("GET", "/cmv/grupos", null, token);
    const meu = (depoisCriar ?? []).find((g) => g.nome === `Teste tela ${marcaG}`);
    checar("o grupo criado pela tela chega ao servidor", !!meu, depoisCriar?.length);
    if (meu) {
      gruposCriados.push(meu.id);
      checar("com o tipo que foi marcado", meu.tipos.includes(tipoLivre), meu.tipos);
    }

    // ⚠️ O tipo agora está tomado: a caixa dele tem de aparecer DESABILITADA e
    // dizendo em que grupo está.
    await new Promise((r) => setTimeout(r, 600));
    const travado = await p.evaluate((tipo) => {
      const caixa = document.querySelector(`#tipo-novo-${tipo}`);
      const rotulo = document.querySelector(`label[for="tipo-novo-${tipo}"]`);
      return { existe: !!caixa, travada: caixa?.disabled ?? null,
               texto: rotulo?.textContent ?? "" };
    }, tipoLivre);
    checar("o tipo já usado fica travado na tela", travado.travada === true, travado);
    checar("e a tela diz em qual grupo ele está",
      /já está em/.test(travado.texto), travado.texto);
    // ⚠️ A foto é DESTA tela, não do painel de CMV: `fullPage` no painel — que
    // tem a composição, a ABC e a margem, todas longas — estourava o tempo do
    // protocolo do Chrome. E é aqui que a configuração se vê.
    await foto(p, "27-grupos-cmv");
  }

  // A linha do grupo aparece na conta do CMV, junto de Perdas e Ajustes.
  await irPara(p, `${WEB}/cmv`);
  await new Promise((r) => setTimeout(r, 2200));
  const noPainel = await p.evaluate(() => {
    const linhas = [...document.querySelectorAll("table tr")]
      .map((l) => l.textContent?.trim() ?? "");
    return {
      temPerdas: linhas.some((l) => l.startsWith("Perdas")),
      temGrupo: linhas.some((l) => /Material de limpeza|Teste tela/i.test(l)),
    };
  });
  checar("a conta do CMV continua mostrando Perdas", noPainel.temPerdas, noPainel);
  checar("e ganhou a linha do grupo por tipo de produto", noPainel.temGrupo, noPainel);

  console.log("10w. vincular dois cadastros do mesmo produto");
  // ⚠️ **Nao existe detector, e este bloco guarda o porque.** Um cruzamento por
  // semelhanca errava nos dois sentidos: nao achava "BEB CERV HEINEKEN 350ML"
  // contra "CERVEJA HEINEKEN PILSEN" -- o mesmo produto, 63,8% -- e juntava
  // "CAKE BOARD N19" com "CAKE BOARD N21", que sao tamanhos diferentes. Quem
  // reconhece produto e quem esta olhando a tela.
  const mVinc = Date.now().toString().slice(-5);
  const { dados: vincA } = await api("POST", "/produtos", {
    codigo: `TVINC-A-${mVinc}`, nome: `BEB CERV HEINEKEN 350ML ${mVinc}`,
    tipo: "REVENDA", um_estoque: "UN", controla_estoque: true, status: "ATIVO",
    codigo_omie: `771${mVinc}`,
  }, token);
  const { dados: vincB } = await api("POST", "/produtos", {
    codigo: `TVINC-B-${mVinc}`, nome: `CERVEJA HEINEKEN PILSEN ${mVinc}`,
    tipo: "PRODUZIDO", producao_propria: true, controla_estoque: false,
    status: "RASCUNHO", codigo_pdv: `991${mVinc}`, marca: "Heineken",
  }, token);
  aoTerminar.push(() => api("DELETE", `/produtos/${vincA.id}`, null, token));
  aoTerminar.push(() => api("DELETE", `/produtos/${vincB.id}`, null, token));

  await irPara(p, `${WEB}/produtos/${vincA.id}`);
  await new Promise((r) => setTimeout(r, 1800));
  const temBotao = await p.evaluate(() =>
    [...document.querySelectorAll("button")].some((b) => b.textContent?.trim() === "Vincular"));
  checar("a tela do produto tem o botao Vincular", temBotao);

  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (x) => x.textContent?.trim() === "Vincular");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 900));
  const busca = await p.$('input[aria-label="Buscar produto"]');
  checar("e abre a busca do outro cadastro", !!busca);
  if (busca) {
    await busca.type(`CERVEJA HEINEKEN PILSEN ${mVinc}`);
    await p.keyboard.press("Tab");
    await new Promise((r) => setTimeout(r, 1800));
    const previa = await textoVisivel(p);
    // ⚠️ A previa vem ANTES do botao porque fusao nao tem desfazer: quem
    // confirma precisa ver com que nome o produto vai ficar.
    checar("a previa mostra como fica", /Como fica/i.test(previa), previa.slice(0, 160));
    checar("a descricao vem do lado do Omie",
      previa.includes(`BEB CERV HEINEKEN 350ML ${mVinc}`), previa.slice(0, 260));
    checar("e a curta do lado do PDV",
      previa.includes(`CERVEJA HEINEKEN PILSEN ${mVinc}`), previa.slice(0, 260));
    checar("dizendo que o outro vira inativo", /vira inativo/i.test(previa));
    // ⚠️ Nada a baixar aqui (o lado do PDV nao vendeu), e a tela DIZ isso em vez
    // de calar: caixinha ausente sem explicacao lê como funcionalidade faltando.
    checar("e explica que nao ha o que baixar do estoque",
      /Nada a baixar do estoque/i.test(previa), previa.slice(0, 400));
    await foto(p, "32-vincular");

    await p.evaluate(() => {
      const b = [...document.querySelectorAll("button")].find(
        (x) => x.textContent?.trim() === "Vincular e fundir");
      b?.click();
    });
    await new Promise((r) => setTimeout(r, 2600));
    const { dados: depois } = await api("GET", `/produtos/${vincA.id}`, null, token);
    checar("a fusao pela tela junta os dois nomes",
      depois.nome === `BEB CERV HEINEKEN 350ML ${mVinc}`
      && depois.nome_curto === `CERVEJA HEINEKEN PILSEN ${mVinc}`,
      [depois.nome, depois.nome_curto]);
    checar("e os codigos das duas integracoes",
      depois.codigo_omie === `771${mVinc}` && depois.codigo_pdv === `991${mVinc}`,
      [depois.codigo_omie, depois.codigo_pdv]);
    const { dados: saiu } = await api("GET", `/produtos/${vincB.id}`, null, token);
    checar("e o outro ficou inativo, nao apagado", saiu.ativo === false, saiu.ativo);
  }

  console.log("10x. PDV Legal: a credencial e o que ainda falta");
  // ⚠️ **Só a autenticação existe, e a tela tem de DIZER isso.** O catálogo de
  // endpoints da Tablet Cloud não é público; um cartão com um botão de testar e
  // mais nada parece um pedaço faltando, e alguém abriria chamado por isso.
  await irPara(p, `${WEB}/integracoes`);
  await new Promise((r) => setTimeout(r, 2000));
  const pdv = await p.evaluate(() => {
    const texto = document.body.innerText;
    const rotulos = [...document.querySelectorAll("span.rotulo")].map((r) =>
      r.textContent?.trim() ?? "");
    const senhas = [...document.querySelectorAll('input[type="password"]')].length;
    return {
      temCartao: /PDV Legal/.test(texto),
      explica: /catálogo de endpoints/i.test(texto),
      dizPlanilha: /planilha/i.test(texto),
      campos: ["Usuário de integração", "client_id", "client_secret"].filter((c) =>
        rotulos.some((r) => r.startsWith(c))),
      senhasEscondidas: senhas,
      temFiliais: rotulos.includes("Filiais"),
      temBuscar: [...document.querySelectorAll("button")].some(
        (b) => b.textContent?.trim() === "Buscar vendas"),
      temCardapio: [...document.querySelectorAll("button")].some(
        (b) => b.textContent?.trim() === "Importar cardápio"),
      configurada: /guardado:/.test(texto),
    };
  });
  checar("a tela tem o cartão do PDV Legal", pdv.temCartao, pdv);
  checar("com os campos da credencial", pdv.campos.length === 3, pdv);
  checar("e o campo das filiais", pdv.temFiliais, pdv);
  // ⚠️ Senha e token do grupo em `type=password`: a tela de integrações fica
  // aberta na sala, e credencial à vista é credencial anotada.
  checar("senha e token do grupo escondidos", pdv.senhasEscondidas >= 2, pdv);
  // ⚠️ Com o catálogo em mãos (26/08/2026), a venda entra sozinha: o cartão
  // ganhou o botão de buscar. O aviso de "só guarda credencial" saiu junto.
  checar("e o botão de buscar vendas quando há credencial",
    pdv.temBuscar || !pdv.configurada, pdv);
  // ⚠️ Sem o cardápio a venda entra e o CMV teórico é ZERO — os dois botões são
  // as duas metades do mesmo trabalho, e um sem o outro entrega meia resposta.
  checar("e o de importar o cardápio, que é o que dá custo à venda",
    pdv.temCardapio || !pdv.configurada, pdv);
  await foto(p, "30-pdv-legal");

  console.log("10x2. conferencia de estoque com o Omie");
  // ⚠️ **Esta conferencia NUNCA funcionou ate 27/08/2026 e o simulado dizia que
  // sim.** `ListarPosEstoque` tem um dialeto de paginacao so dele, e o mapeador
  // lia `cCodigo` (o codigo da CASA no Omie) como `codigo_omie` (o id de la) --
  // nunca casava. O sintoma seria uma tabela VAZIA, que se le como "esta tudo
  // certo". Por isso a tela mostra o RESUMO antes da tabela.
  await irPara(p, `${WEB}/integracoes`);
  await new Promise((r) => setTimeout(r, 2000));
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (x) => /Conferir estoque|Confer[êe]ncia/i.test(x.textContent ?? ""));
    b?.click();
  });
  // ⚠️ **Espera pela RESPOSTA, não por um tempo fixo.** Contra a conta real a
  // varredura leva ~17 s (1.987 produtos em 10 páginas); um `setTimeout` de três
  // segundos reprovava a checagem por impaciência, não por defeito.
  let conf = "";
  for (let tentativa = 0; tentativa < 30; tentativa++) {
    await new Promise((r) => setTimeout(r, 1000));
    conf = await textoVisivel(p);
    if (/produto\(s\) conferido|Nenhum produto com c[óo]digo do Omie|Falha na confer/i.test(conf)) {
      break;
    }
  }
  checar("a conferencia de estoque responde",
    /produto\(s\) conferido|Nenhum produto com c[óo]digo do Omie/i.test(conf),
    conf.slice(0, 200));
  // ⚠️ O resumo diz o que a tabela nao diz: quantos foram conferidos e quantos
  // do Omie nao tem cadastro aqui. Lista curta sem ele le como "quase tudo bem".
  checar("e mostra o resumo antes da tabela",
    /conferido\(s\)/i.test(conf) || /Nenhum produto/i.test(conf), conf.slice(0, 200));
  await foto(p, "33-conferencia-estoque");

  console.log("10y. buscar notas do Omie sozinho");
  // ⚠️ A agenda nasce MANUAL e este bloco a devolve assim — a conta configurada
  // aqui pode ser a REAL, e deixar HORARIA ligada faria a máquina buscar notas
  // do cliente de hora em hora, para sempre.
  const { dados: cfgAntes } = await api("GET", "/omie/config", null, token);
  aoTerminar.push(() => api("PUT", "/omie/config", {
    modo: cfgAntes?.modo ?? "simulado",
    ativa: cfgAntes?.ativa ?? false,
    agenda_frequencia: cfgAntes?.agenda_frequencia ?? "MANUAL",
    agenda_hora: cfgAntes?.agenda_hora ?? 3,
    agenda_janela_dias: cfgAntes?.agenda_janela_dias ?? null,
  }, token));

  await irPara(p, `${WEB}/integracoes`);
  await new Promise((r) => setTimeout(r, 2000));
  // ⚠️ **Pelo id da seção, não por "o primeiro select com HORARIA".** Desde que
  // o PDV Legal ganhou agenda, há DOIS blocos iguais na mesma tela — e o
  // seletor por conteúdo passou a devolver o de quem estivesse antes no DOM.
  const blocoAgenda = await p.evaluate(() => {
    const sel = document.querySelector("#agenda-omie select");
    return {
      // ⚠️ Pelo texto da página, não por `span.rotulo`: o título do bloco é um
      // `<p class="rotulo">`, e a classe é a mesma dos rótulos de campo.
      temBloco: /buscar notas sozinho/i.test(document.body.innerText),
      valor: sel?.value ?? null,
      opcoes: sel ? [...sel.options].map((o) => o.value) : [],
    };
  });
  checar("a tela oferece a busca automática", blocoAgenda.temBloco, blocoAgenda);
  checar("com as três frequências",
    ["MANUAL", "HORARIA", "DIARIA"].every((f) => blocoAgenda.opcoes.includes(f)),
    blocoAgenda);
  // ⚠️ **Nasce MANUAL.** Cada busca consome cota, e o Omie bloqueia a
  // integração inteira de quem passa do ponto: ligar é decisão de quem paga.
  checar("e começa em manual", blocoAgenda.valor === "MANUAL", blocoAgenda);

  // Escolher "a cada hora" tem de avisar do custo — 24 buscas por dia.
  await p.evaluate(() => {
    const sel = document.querySelector("#agenda-omie select");
    if (!sel) return;
    sel.value = "HORARIA";
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 900));
  checar("a cada hora avisa que consome cota",
    await p.evaluate(() => /bloqueia a integração inteira/i.test(document.body.innerText)));

  // "Uma vez por dia" troca a pergunta: aparece a hora.
  await p.evaluate(() => {
    const sel = document.querySelector("#agenda-omie select");
    if (!sel) return;
    sel.value = "DIARIA";
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 900));
  checar("uma vez por dia pergunta a hora",
    await p.evaluate(() =>
      [...document.querySelectorAll("#agenda-omie span.rotulo")].some((r) =>
        /A que hora/i.test(r.textContent ?? ""))));
  await foto(p, "29-agenda-omie");

  await api("PUT", "/omie/config", {
    modo: cfgAntes?.modo ?? "simulado",
    ativa: cfgAntes?.ativa ?? false,
    agenda_frequencia: cfgAntes?.agenda_frequencia ?? "MANUAL",
    agenda_hora: cfgAntes?.agenda_hora ?? 3,
    agenda_janela_dias: cfgAntes?.agenda_janela_dias ?? null,
  }, token);

  console.log("10z. buscar vendas do PDV sozinho");
  // ⚠️ Mesma devolução do bloco do Omie: a conta do PDV configurada aqui é a
  // REAL, e deixar HORARIA ligada faria a máquina buscar as vendas do cliente
  // de hora em hora — cada busca é uma requisição por dia da janela.
  const { dados: pdvAntes } = await api("GET", "/pdv/config", null, token);
  const reporPdv = () => api("PUT", "/pdv/config", {
    modo: pdvAntes?.modo ?? "simulado",
    ativa: pdvAntes?.ativa ?? false,
    agenda_frequencia: pdvAntes?.agenda_frequencia ?? "MANUAL",
    agenda_hora: pdvAntes?.agenda_hora ?? 4,
    agenda_janela_dias: pdvAntes?.agenda_janela_dias ?? null,
  }, token);
  aoTerminar.push(reporPdv);

  await irPara(p, `${WEB}/integracoes`);
  // ⚠️ **Esperar o BLOCO, não o relógio.** `pdv-legal.tsx` devolve
  // `<Carregando/>` enquanto `/pdv/config` não responde, então o `#agenda-pdv`
  // não existe no DOM — e a checagem acusava a tela de não ter a agenda. O
  // bloco do Omie é outro componente e responde antes, o que fazia a falha
  // parecer específica do PDV. Dormir um tempo fixo e afirmar é supor a
  // precondição; esperar por ela é garanti-la.
  await p.waitForSelector("#agenda-pdv", { timeout: 20000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 400));
  const agendaPdv = await p.evaluate(() => {
    const sel = document.querySelector("#agenda-pdv select");
    return {
      temBloco: /buscar vendas sozinho/i.test(document.body.innerText),
      valor: sel?.value ?? null,
      opcoes: sel ? [...sel.options].map((o) => o.value) : [],
    };
  });
  checar("o PDV também oferece a busca automática", agendaPdv.temBloco, agendaPdv);

  // 🔑 A mão inversa. Até aqui a integração só LIA do PDV; escrever de volta
  // mexe no sistema que a casa usa para vender, então é um interruptor
  // separado do "integração ativa" e nasce DESLIGADO.
  const envioPdv = await p.evaluate(() => {
    const bloco = document.querySelector("#envio-pdv");
    const caixa = bloco?.querySelector('input[type="checkbox"]');
    return { temBloco: !!bloco, ligado: caixa ? caixa.checked : null,
             frase: /Enviar informações ao PDV/.test(bloco?.innerText ?? "") };
  });
  checar("a tela oferece o envio ao PDV", envioPdv.temBloco && envioPdv.frase, envioPdv);
  // ⚠️ **Afirma que a caixinha REFLETE o servidor, não que ela está desligada.**
  // Ela nasce desligada, mas depois de a casa ligar o envio ela fica ligada — e
  // o teste caía acusando de defeito uma decisão do dono. É a mesma correção da
  // checagem do setor BAR: descrever a propriedade, nunca o estado do dia.
  const { dados: cfgEnvio } = await api("GET", "/pdv/config", null, token);
  checar("e a caixinha mostra o que o servidor diz",
    envioPdv.ligado === !!cfgEnvio?.enviar_ao_pdv, [envioPdv.ligado, cfgEnvio?.enviar_ao_pdv]);
  checar("com as três frequências",
    ["MANUAL", "HORARIA", "DIARIA"].every((f) => agendaPdv.opcoes.includes(f)),
    agendaPdv);

  await p.evaluate(() => {
    const sel = document.querySelector("#agenda-pdv select");
    if (!sel) return;
    sel.value = "HORARIA";
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 900));
  // ⚠️ "A cada hora" não parece caro até alguém multiplicar: 24 buscas por dia,
  // e cada uma faz uma requisição por dia da janela.
  checar("a cada hora diz quanto custa",
    await p.evaluate(() => /uma requisição por dia da janela/i.test(document.body.innerText)));

  await p.evaluate(() => {
    const sel = document.querySelector("#agenda-pdv select");
    if (!sel) return;
    sel.value = "DIARIA";
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 900));
  checar("uma vez por dia pergunta a hora",
    await p.evaluate(() =>
      [...document.querySelectorAll("#agenda-pdv span.rotulo")].some((r) =>
        /A que hora/i.test(r.textContent ?? ""))));
  await foto(p, "31-agenda-pdv");
  await reporPdv();

  console.log("10a. ritmo do fechamento: dia, semana ou mês");
  // ⚠️ **A loja volta a MENSAL no fim deste bloco.** O ritmo muda o período em
  // que o painel de CMV e a tela inicial abrem; deixá-lo em SEMANAL faria as
  // suítes de API seguintes apurarem outro recorte e acusarem diferença sem
  // que nada tivesse quebrado. Mesma lição do modo `simulado` do Omie.
  aoTerminar.push(async () => {
    await api("PUT", "/unidades/1/parametros",
      { ciclo_fechamento: "MENSAL", dia_fechamento_cmv: 1, fechamento_dia_semana: 7 }, token);
  });

  // ⚠️ Parte de MENSAL em vez de supor: a base é compartilhada, e uma suíte
  // anterior que estourou no meio pode ter deixado a loja noutro ritmo.
  await api("PUT", "/unidades/1/parametros",
    { ciclo_fechamento: "MENSAL", dia_fechamento_cmv: 1, fechamento_dia_semana: 7 }, token);

  await irPara(p, `${WEB}/lojas`);
  await new Promise((r) => setTimeout(r, 1600));
  // ⚠️ O título está num `.rotulo`, que o CSS põe em maiúsculas — e `innerText`
  // devolve o texto RENDERIZADO, não o que está no JSX. Procurar pela frase
  // como ela foi escrita não acha nada.
  const temRitmo = await p.evaluate(() =>
    /ritmo do fechamento do cmv/i.test(document.body.innerText));
  checar("a tela de Lojas oferece o ritmo do fechamento", temRitmo);

  // No mensal só existe a pergunta do mês: oferecer também o dia da semana
  // seria pedir uma resposta que não muda nada.
  const seletores = () =>
    p.evaluate(() => {
      const rotulos = [...document.querySelectorAll("label")].map((l) =>
        l.textContent?.trim() ?? "");
      return {
        temSemana: rotulos.some((r) => r.startsWith("Dia em que a semana fecha")),
        temMes: rotulos.some((r) => r.startsWith("Dia em que o mês começa")),
        frase: document.body.innerText.match(/Fecha .+/)?.[0] ?? "",
        etiquetas: [...document.querySelectorAll("section .etiqueta, section span")]
          .map((e) => e.textContent?.trim()).filter((t) => /\d{2}\/\d{2}\/\d{4}/.test(t ?? "")),
      };
    });
  const mensal = await seletores();
  checar("no mensal, pergunta o dia de início do mês", mensal.temMes, mensal);
  checar("e NÃO pergunta o dia da semana", !mensal.temSemana, mensal);
  checar("a frase confirma o que foi escolhido",
    /Fecha no fim do mês/.test(mensal.frase), mensal.frase);

  // Trocar para semanal muda a pergunta e a prévia — que vem do servidor, do
  // mesmo código que vai fechar o período de verdade.
  await p.evaluate(() => {
    const sel = [...document.querySelectorAll("select")]
      .find((s) => [...s.options].some((o) => o.value === "SEMANAL"));
    if (!sel) return;
    sel.value = "SEMANAL";
    sel.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 1800));
  const semanal = await seletores();
  checar("no semanal, pergunta o dia em que a semana fecha", semanal.temSemana, semanal);
  checar("e some a pergunta do mês", !semanal.temMes, semanal);
  checar("a prévia diz em que dia fecha",
    /Fecha todo domingo/.test(semanal.frase), semanal.frase);
  checar("e mostra os próximos períodos", semanal.etiquetas.length >= 3, semanal.etiquetas);
  await foto(p, "26-ritmo-semanal");

  // Salvar e conferir que o painel de CMV passou a abrir na SEMANA.
  await p.evaluate(() => {
    [...document.querySelectorAll("button")].find((b) => b.textContent === "Salvar")?.click();
  });
  await new Promise((r) => setTimeout(r, 1500));
  await irPara(p, `${WEB}/cmv`);
  await new Promise((r) => setTimeout(r, 2200));
  const noCmv = await p.evaluate(() => {
    const texto = document.body.innerText;
    const opcoes = [...document.querySelectorAll("select")]
      .flatMap((s) => [...s.options].map((o) => o.textContent?.trim() ?? ""));
    return {
      temSeletor: opcoes.some((o) => /^semana de /.test(o)),
      emCurso: opcoes.some((o) => /em curso/.test(o)),
      botao: [...document.querySelectorAll("button")]
        .map((b) => b.textContent?.trim() ?? "").find((t) => t.startsWith("Fechar")) ?? "",
      texto,
    };
  });
  checar("o painel de CMV oferece as semanas para escolher", noCmv.temSeletor, noCmv.botao);
  checar("e marca qual está em curso", noCmv.emCurso, noCmv.botao);
  // ⚠️ O botão nomeia o período: "Fechar o mês" numa casa que fecha por semana
  // é a tela discordando do que o servidor vai fazer.
  checar("o botão de fechar nomeia o período, não o mês",
    !/mês/.test(noCmv.botao), noCmv.botao);
  await foto(p, "26b-cmv-semanal");

  await api("PUT", "/unidades/1/parametros",
    { ciclo_fechamento: "MENSAL", dia_fechamento_cmv: 1, fechamento_dia_semana: 7 }, token);

  console.log("10b. paginação: o padrão das listas");
  // O rodapé de página é o mesmo em todo grid. Aqui se prova o CONTRATO dele:
  // diz quantos existem, anda, deixa escolher o tamanho e lembra a escolha.
  // ⚠️ GARANTE o que precisa: numa base recém-instalada não há 20 produtos, e o
  // rodapé se esconde de propósito quando não há o que paginar. Sem isto o
  // bloco inteiro morria num seletor que não existe — e a culpa parecia ser da
  // paginação, não da base vazia.
  const marcaPag = String(Date.now()).slice(-5);
  // ⚠️ **Os 25 são SEMPRE deste teste, não "até chegar a 25 na base".** A conta
  // antiga partia do total existente: com a base já passando de 25 produtos —
  // que é o normal depois de qualquer bateria, e o certo depois de uma
  // importação real — o laço não criava nada, e a busca por `${marcaPag}-0`
  // logo abaixo não achava nenhum. O rodapé sumia com a lista vazia e a
  // checagem acusava a paginação por um problema que era do dado. É a mesma
  // lição das suítes de API: cada teste procura os registros DELE.
  const criadosPag = [];
  for (let i = 0; i < 25; i++) {
    const { dados } = await api("POST", "/produtos",
      { nome: `Pag tela ${marcaPag}-${String(i).padStart(2, "0")}`, tipo: "INSUMO",
        um_estoque: "UN" }, token);
    if (dados?.id) criadosPag.push(dados.id);
  }

  await irPara(p, `${WEB}/produtos`);
  await new Promise((r) => setTimeout(r, 1600));

  const lerPaginacao = () =>
    p.evaluate(() => {
      const sel = document.querySelector('select[aria-label="Registros por página"]');
      const t = document.body.innerText;
      return {
        tem: !!sel,
        porPagina: sel ? Number(sel.value) : null,
        rodape: t.match(/(\d+)–(\d+) de ([\d.]+)/)?.[0] ?? null,
        total: Number((t.match(/\d+–\d+ de ([\d.]+)/)?.[1] ?? "0").replace(/\./g, "")),
        linhas: document.querySelectorAll("tbody tr").length,
        primeiro: document.querySelector("tbody tr td")?.textContent?.trim() ?? null,
        proximaLigada: !document.querySelector('button[aria-label="Próxima página"]')?.disabled,
        anteriorDesligada: !!document.querySelector('button[aria-label="Página anterior"]')
          ?.disabled,
      };
    });

  const antes = await lerPaginacao();
  checar("a lista tem o rodapé de página", antes.tem, antes);
  checar("que diz quantos existem, não só quantos vieram",
    antes.total > antes.linhas, antes);
  checar("na primeira página o 'anterior' fica desligado", antes.anteriorDesligada, antes);

  await p.evaluate(() => document.querySelector('button[aria-label="Próxima página"]')?.click());
  await new Promise((r) => setTimeout(r, 1400));
  const segunda = await lerPaginacao();
  checar("a próxima página traz outros registros",
    segunda.primeiro !== antes.primeiro && segunda.primeiro !== null, [antes.primeiro, segunda.primeiro]);
  checar("e o rodapé acompanha", segunda.rodape !== antes.rodape, [antes.rodape, segunda.rodape]);
  checar("o total não muda ao virar a página", segunda.total === antes.total,
    [antes.total, segunda.total]);

  // 20, 50 ou 100 — escolha de quem olha.
  await p.select('select[aria-label="Registros por página"]', "50");
  await new Promise((r) => setTimeout(r, 1600));
  const maior = await lerPaginacao();
  checar("trocar o tamanho traz mais linhas", maior.linhas > antes.linhas,
    [antes.linhas, maior.linhas]);
  checar("e volta para a primeira página", /^1–/.test(maior.rodape ?? ""), maior.rodape);

  // ⚠️ A preferência é lembrada: quem escolheu 50 não quer reescolher a cada
  // visita. Sai da tela e volta.
  await irPara(p, `${WEB}/fornecedores`);
  await new Promise((r) => setTimeout(r, 1200));
  await irPara(p, `${WEB}/produtos`);
  await new Promise((r) => setTimeout(r, 1800));
  const lembrado = await lerPaginacao();
  checar("a escolha de quantos por página é lembrada", lembrado.porPagina === 50,
    lembrado.porPagina);

  // Filtrar volta ao começo: quem está na página 3 e digita uma busca não pode
  // cair numa tela vazia porque o resultado tem uma página só.
  await p.evaluate(() => document.querySelector('button[aria-label="Próxima página"]')?.click());
  await new Promise((r) => setTimeout(r, 1400));
  const campoBuscaPag =
    (await p.$$('input[placeholder="nome, código ou código de barras"]'))[0];
  // ⚠️ Um termo que EXISTE nesta base. "cafe" era chute: numa base recém-limpa
  // não acha nada, a lista fica vazia, o rodapé some — e a checagem acusava a
  // paginação por um problema que era do dado. Os produtos desta fase têm
  // marca própria, e o `-0` pega uma parte deles, não todos.
  await campoBuscaPag.type(`${marcaPag}-0`);
  await new Promise((r) => setTimeout(r, 1800));
  const filtrado = await lerPaginacao();
  checar("filtrar volta para a primeira página",
    filtrado.linhas > 0 && (filtrado.rodape === null || /^1–/.test(filtrado.rodape)), filtrado);
  checar("e o total passa a ser o do filtro", filtrado.total < antes.total || !filtrado.tem,
    [antes.total, filtrado.total]);
  await foto(p, "32-paginacao");
  for (const id of criadosPag) await api("DELETE", `/produtos/${id}`, null, token);

  console.log("10b2. cadastrar em pagina propria: fornecedor e usuario");
  // ⚠️ **Os dois formularios viviam na coluna da direita da lista.** O de
  // fornecedor tinha treze campos espremidos em 360 px; o de usuario, uma lista
  // de papeis que cresce com o sistema, cada um com descricao de duas linhas --
  // e o botao de salvar caia fora da tela. Quem cadastrava marcava caixinha sem
  // ver o que marcava. Mesmo corte de Compras e de Vendas.
  const mCad = Date.now().toString().slice(-5);

  await irPara(p, `${WEB}/fornecedores`);
  await new Promise((r) => setTimeout(r, 1600));
  const listaForn = await textoVisivel(p);
  // ⚠️ A lista nao pode mais ter o formulario dentro: se "Razao social" aparecer
  // aqui, o cartao voltou para a direita.
  checar("a lista de fornecedores nao tem mais o formulario",
    !/Raz[ãa]o social/i.test(listaForn), listaForn.slice(0, 160));
  checar("e o botao leva para a pagina nova", await p.evaluate(() =>
    [...document.querySelectorAll("a")].some(
      (a) => /Novo fornecedor/i.test(a.textContent ?? "") && a.getAttribute("href") === "/fornecedores/novo")));

  await irPara(p, `${WEB}/fornecedores/novo`);
  await new Promise((r) => setTimeout(r, 1400));
  const formForn = await textoVisivel(p);
  checar("a pagina de novo fornecedor abre", /Novo fornecedor/i.test(formForn), formForn.slice(0, 140));
  checar("com os campos separados por assunto",
    /Identifica[çc][ãa]o/i.test(formForn) && /Contato/i.test(formForn) && /Entrega/i.test(formForn),
    formForn.slice(0, 260));
  // ⚠️ O CNPJ e o que liga a nota do Omie ao fornecedor certo -- a tela diz isso.
  checar("e a tela diz para que serve o CNPJ", /casa a nota do Omie/i.test(formForn),
    formForn.slice(0, 300));

  await p.evaluate((nome) => {
    const set = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    const campos = [...document.querySelectorAll("input")];
    if (campos[0]) { set.call(campos[0], nome); campos[0].dispatchEvent(new Event("input", { bubbles: true })); }
  }, `Fornecedor tela ${mCad}`);
  await new Promise((r) => setTimeout(r, 400));
  // ⚠️ Clique por `evaluate`, nao por `p.click` com `waitForNavigation`: a volta
  // para a lista e do CLIENTE (`router.push`), entao a espera por navegacao nunca
  // resolve e trava o protocolo do Chrome -- derrubando a rodada inteira.
  await p.evaluate(() => {
    document.querySelector('button[type="submit"]')?.click();
  });
  await new Promise((r) => setTimeout(r, 2500));
  const { dados: fornCriados } = await api(
    "GET", `/fornecedores?busca=Fornecedor tela ${mCad}`, null, token);
  const meuForn = (fornCriados ?? []).find((f) => f.nome === `Fornecedor tela ${mCad}`);
  checar("cadastrar pela pagina grava o fornecedor", !!meuForn, (fornCriados ?? []).length);
  if (meuForn) {
    aoTerminar.push(() => api("DELETE", `/fornecedores/${meuForn.id}`, null, token));
    // ⚠️ A edicao e a MESMA forma da criacao, para o olho reconhecer.
    await irPara(p, `${WEB}/fornecedores/${meuForn.id}`);
    await new Promise((r) => setTimeout(r, 1600));
    const edicao = await textoVisivel(p);
    checar("e a edicao abre com o nome no titulo",
      edicao.includes(`Fornecedor tela ${mCad}`), edicao.slice(0, 160));
  }

  await irPara(p, `${WEB}/usuarios`);
  await new Promise((r) => setTimeout(r, 1600));
  const listaUsu = await textoVisivel(p);
  checar("a lista de usuarios nao tem mais o formulario",
    !/Nova senha|Pap[ée]is<\/span>/i.test(listaUsu) && !/Criar usu[áa]rio/i.test(listaUsu),
    listaUsu.slice(0, 160));

  await irPara(p, `${WEB}/usuarios/novo`);
  await new Promise((r) => setTimeout(r, 1600));
  const formUsu = await textoVisivel(p);
  checar("a pagina de novo usuario abre", /Novo usu[áa]rio/i.test(formUsu), formUsu.slice(0, 140));
  // ⚠️ Os papeis agora cabem lado a lado, com a descricao inteira a vista.
  checar("com os papeis e suas descricoes a vista",
    /Pap[ée]is/i.test(formUsu) && /Administrador/i.test(formUsu), formUsu.slice(0, 300));
  checar("e dizendo que a senha e provisoria",
    /troca no primeiro acesso/i.test(formUsu), formUsu.slice(0, 300));
  await foto(p, "34-cadastro-em-pagina");

  console.log("10c. a ajuda dentro do sistema");
  // ⚠️ O manual é UM arquivo (`public/ajuda.html`), exibido pela tela e
  // publicado como documento. Duas cópias do mesmo texto divergem no primeiro
  // parágrafo novo — e aí o sistema explica duas coisas diferentes sobre si.
  await irPara(p, `${WEB}/ajuda`);
  await new Promise((r) => setTimeout(r, 3000));
  const ajuda = await p.evaluate(() => {
    const q = document.querySelector("iframe");
    const doc = q?.contentDocument;
    return {
      temQuadro: !!q,
      titulo: doc?.title ?? null,
      secoes: doc ? doc.querySelectorAll("section").length : 0,
      diagramas: doc ? doc.querySelectorAll("svg").length : 0,
      alturaQuadro: q ? Math.round(q.getBoundingClientRect().height) : 0,
      alturaConteudo: doc ? doc.documentElement.scrollHeight : 0,
      // ⚠ A Ajuda saiu do menu LATERAL e vive no menu do usuario, na
      // barra superior — o manual e de quem esta usando, nao um assunto do
      // sistema como estoque ou compras.
      noMenu: true,
    };
  });
  const ajudaNoMenuDoUsuario = await p.evaluate(async () => {
    document.querySelector("#barra-superior button[aria-haspopup='menu']")?.click();
    await new Promise((r) => setTimeout(r, 200));
    const tem = [...document.querySelectorAll("#menu-usuario a")]
      .some((a) => a.getAttribute("href") === "/ajuda");
    document.body.click();
    return tem;
  });
  checar("a Ajuda está no menu do usuário", ajudaNoMenuDoUsuario);
  checar("o manual carrega dentro da tela", ajuda.titulo === "Botané por dentro", ajuda);
  checar("com todos os processos e os dois diagramas",
    ajuda.secoes >= 16 && ajuda.diagramas === 2, ajuda);
  // ⚠️ A seção que explica DE ONDE VEM cada número é o coração do manual: é ela
  // que faz alguém conferir um relatório em vez de aceitar o valor que está lá.
  // Cobrar o texto, e não só a contagem de seções, porque contagem passa mesmo
  // quando o conteúdo virou outra coisa.
  const trilha = await p.evaluate(() => {
    const q = document.querySelector("iframe");
    const d = q?.contentDocument;
    const t = d?.getElementById("trilha")?.innerText ?? "";
    return {
      existe: t.length > 500,
      custoMedio: /ponderad/i.test(t),
      congelado: /congelad/i.test(t),
      resumo: /CMV real ÷ receita|estoque inicial \+ compras/i.test(t),
    };
  });
  checar("o manual explica de onde vem cada número", trilha.existe, trilha);
  checar("com o custo médio ponderado, o custo congelado e a fórmula do CMV",
    trilha.custoMedio && trilha.congelado && trilha.resumo, trilha);
  // Documento com rolagem própria dentro de página que já rola é briga de
  // rolagem: a roda do mouse para no meio e ninguém sabe qual das duas move.
  checar("o quadro cresce até a altura do conteúdo",
    ajuda.alturaConteudo > 2000 && Math.abs(ajuda.alturaQuadro - ajuda.alturaConteudo) < 60,
    ajuda);
  await foto(p, "33-ajuda");

  console.log("10d. a barra superior, o menu do usuario e o rodape");
  await p.goto(`${WEB}/`, { waitUntil: "networkidle0" });
  await p.waitForSelector("#barra-superior");

  // 🔑 Quem entrou fica no canto superior DIREITO, que e onde todo mundo
  // procura. Antes era o pe do menu lateral — no celular, com a gaveta fechada,
  // sair do sistema exigia abrir o menu e rolar ate o fim.
  const barraTopo = await p.evaluate(() => {
    const b = document.querySelector("#barra-superior");
    if (!b) return null;
    const botao = b.querySelector("button[aria-haspopup='menu']");
    const r = botao?.getBoundingClientRect();
    return {
      temBotao: !!botao,
      texto: botao?.innerText ?? "",
      // Do meio da tela para a direita: e a posicao que faz a convencao valer.
      aDireita: r ? r.left > window.innerWidth / 2 : false,
      topo: Math.round(b.getBoundingClientRect().top),
    };
  });
  checar("a barra superior existe e fica no topo", barraTopo && barraTopo.topo === 0, barraTopo);
  checar("o nome de quem entrou vira o controle, no canto direito",
    barraTopo?.temBotao && barraTopo.aDireita, barraTopo);

  // ⚠️ Clique DENTRO da pagina, nao pelo `p.click`. O `p.click` do puppeteer
  // rola o elemento e espera ele ficar estavel, e essa dança estourou o
  // `protocolTimeout` de 60 s nesta barra — derrubando a rodada inteira num
  // ponto que nao tem defeito nenhum. O elemento e um botao simples: mandar o
  // clique de dentro do documento faz a mesma coisa e nao depende de layout.
  await p.evaluate(() =>
    document.querySelector("#barra-superior button[aria-haspopup='menu']")?.click());
  await p.waitForSelector("#menu-usuario");
  const itensDoMenu = await p.evaluate(() =>
    [...document.querySelectorAll("#menu-usuario a, #menu-usuario button")]
      .map((e) => e.innerText.trim().toLowerCase()));
  for (const esperado of ["alertas", "ajuda", "perfil", "alterar senha", "sair"]) {
    checar(`o menu do usuario tem "${esperado}"`,
      itensDoMenu.some((t) => t === esperado), itensDoMenu);
  }
  await foto(p, "35-barra-superior");

  // ⚠️ Fechar clicando FORA: menu que so fecha pelo proprio botao fica preso na
  // tela quando a pessoa desiste dele.
  await p.mouse.click(8, 400);
  await p.waitForFunction(() => !document.querySelector("#menu-usuario"));
  checar("o menu fecha ao clicar fora", true);

  // O Perfil edita o PROPRIO cadastro — nome e telefone, e mais nada: e-mail e
  // identidade de quem entra, papel e loja sao permissao.
  // ⚠️ Clique DENTRO da pagina, nao pelo `p.click`. O `p.click` do puppeteer
  // rola o elemento e espera ele ficar estavel, e essa dança estourou o
  // `protocolTimeout` de 60 s nesta barra — derrubando a rodada inteira num
  // ponto que nao tem defeito nenhum. O elemento e um botao simples: mandar o
  // clique de dentro do documento faz a mesma coisa e nao depende de layout.
  await p.evaluate(() =>
    document.querySelector("#barra-superior button[aria-haspopup='menu']")?.click());
  await p.waitForSelector("#menu-usuario");
  // ⚠️ **A tela do Perfil se alcanca pelo ENDERECO, nao encenando o clique.**
  // Que o item existe e para onde ele aponta ja esta afirmado acima; clicar num
  // link que fecha o proprio menu ao ser clicado so acrescenta uma interacao
  // fragil — e ela derrubou a rodada inteira, esperando por uma navegacao que
  // nao veio, longe de qualquer defeito.
  await irPara(p, `${WEB}/perfil`);
  await p.waitForFunction(() => /Perfil/.test(document.body.innerText));
  const perfilTela = await p.evaluate(() => {
    const campos = [...document.querySelectorAll("label")].map((l) => ({
      rotulo: (l.innerText || "").split("\n")[0].trim(),
      desabilitado: !!l.querySelector("input")?.disabled,
    }));
    return { campos, texto: document.body.innerText };
  });
  // ⚠ Comparacao sem caixa: `.rotulo` tem `text-transform: uppercase`, e o
  // `innerText` do Chrome devolve o que se VE — "NOME", nunca "Nome".
  const rotuloE = (c, r) => c.rotulo.toLowerCase() === r;
  checar("o perfil tem nome e telefone editaveis",
    ["nome", "telefone"].every((r) =>
      perfilTela.campos.some((c) => rotuloE(c, r) && !c.desabilitado)), perfilTela.campos);
  checar("e o e-mail so de leitura",
    perfilTela.campos.some((c) => rotuloE(c, "e-mail") && c.desabilitado), perfilTela.campos);
  await foto(p, "36-perfil");

  // O rodape fixo diz a VERSAO — e ela vem do /saude, ou seja, do que esta NO
  // AR. Uma constante compilada aqui diria o que foi construido, que e outra
  // pergunta.
  await p.waitForFunction(
    () => /v\d+\.\d+\.\d+/.test(document.querySelector("#barra-inferior")?.innerText ?? ""),
    { timeout: 8000 },
  ).catch(() => {});
  const rodapePe = await p.evaluate(() => {
    const f = document.querySelector("#barra-inferior");
    if (!f) return null;
    const r = f.getBoundingClientRect();
    return {
      texto: f.innerText.trim(),
      // Fixo no pe da JANELA, nao no fim do documento.
      noPe: Math.abs(r.bottom - window.innerHeight) < 2,
      aDireita: r.width > 0,
    };
  });
  checar("o rodape fixo mostra a versao", /^v\d+\.\d+\.\d+$/.test(rodapePe?.texto ?? ""), rodapePe);
  checar("e fica preso no pe da janela", rodapePe?.noPe, rodapePe);

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

  // ⚠️ A marca saiu do topo do MENU e foi para a barra superior — no desktop o
  // menu lateral virou só navegacao. A gaveta do celular continua com ela,
  // porque a gaveta cobre a barra.
  const logoNaBarra = await p.evaluate(
    () => !!document.querySelector("#barra-superior img"));
  checar("logo aparece na barra superior", logoNaBarra);

  // Tira a logo de teste: a real é a que o cliente subir.
  await api("DELETE", "/empresa/logo", null, token);
} finally {
  // O que precisa voltar ao lugar mesmo se o roteiro estourar no meio.
  for (const desfazer of aoTerminar) {
    try {
      await desfazer();
    } catch (e) {
      console.log(`  ! não deu para desfazer: ${e}`);
    }
  }
  await navegador.close();
}

console.log(`\n${ok} passaram, ${falhas.length} falharam`);
falhas.forEach((f) => console.log(`  - ${f}`));
console.log(`fotos em ${FOTOS}`);
process.exit(falhas.length ? 1 : 0);
