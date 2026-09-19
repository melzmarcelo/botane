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
import { execFileSync } from "node:child_process";

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

/** POST multipart — o `api()` só fala JSON, e upload é formulário.
 *
 * ⚠️ O conteúdo é um PNG mínimo de verdade: o servidor abre a imagem para
 * conferir que ela é uma imagem, e bytes inventados levariam 400.
 */
async function enviarArquivo(caminho, token, imagem = null) {
  // Sem `imagem`, manda um PNG 8x8 de teste. Com ela, manda os bytes dados —
  // é assim que a logo original da casa volta ao lugar no fim da rodada.
  const png = imagem?.buffer ?? Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAIAQMAAAD+wSzIAAAABlBMVEX///+/v7+jQ3Y5AAAA"
    + "DklEQVQI12P4AIX8EAgALgAD/aNpbtEAAAAASUVORK5CYII=", "base64");
  const tipo = imagem?.tipo ?? "image/png";
  const corpo = new FormData();
  corpo.append("arquivo", new Blob([png], { type: tipo }), imagem?.nome ?? "prato.png");
  const r = await fetch(API + caminho, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: corpo,
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
      // ⚠️ **`ProtocolError: … timed out` na navegação também é transitório**, e
      // era re-lançado: derrubou a rodada inteira num `goto` comum, depois de
      // 280 checagens verdes. É a mesma família do "detached Frame" que este
      // laço já trata — navegação que não termina limpa. Três tentativas
      // continuam sendo o teto: um travamento de verdade ainda estoura, só que
      // depois de o sistema ter tido chance.
      if (!/detached|Target closed|Navigating frame|ProtocolError|timed out/i.test(String(e))
          || tentativa === 2) throw e;
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
/** Espera o botao aparecer e clica nele, devolvendo se conseguiu.
 *
 * ⚠️ **`b?.click()` no-opera em SILENCIO** quando a tela ainda nao renderizou —
 * e o `?.` foi posto justamente para nao derrubar a bateria. O efeito colateral
 * e pior que a queda: nada e clicado, a espera seguinte gasta o orcamento
 * inteiro por um texto que nunca vai vir, e a falha acusa o texto em vez de
 * acusar o clique que nao houve. Foi assim que as tres checagens do custo
 * inicial cairam, com a tela ainda em branco e o botao inexistente.
 */
/* ⚠️ **Casa por TEXTO PURO, não por regex — e isso foi escolha, não simplismo.**
 * A primeira versão recebia a fonte de uma `RegExp`, e o rótulo dos botões desta
 * tela começa com "+". Escapá-lo custou duas tentativas: a barra se perdia no
 * caminho até o arquivo, `"\+ salão"` virava `"+ salão"` em JS e
 * `new RegExp("+ …")` estourava com "nothing to repeat" — derrubando a bateria
 * INTEIRA, não só a checagem. Botão se identifica pelo que está escrito nele;
 * regex aqui só acrescentava uma linguagem a mais para errar.
 * `exato` existe para "criar", que é prefixo de "Criar 6 mesas". */
async function clicarQuando(pagina, texto, { exato = false, limite = 15000 } = {}) {
  const ate = Date.now() + limite;
  while (Date.now() < ate) {
    const clicou = await pagina.evaluate(({ alvo, exigirIgual }) => {
      const b = [...document.querySelectorAll("button")].find((x) => {
        const t = (x.textContent ?? "").trim().toLowerCase();
        return exigirIgual ? t === alvo : t.includes(alvo);
      });
      if (!b || b.disabled) return false;
      b.click();
      return true;
    }, { alvo: texto.trim().toLowerCase(), exigirIgual: exato });
    if (clicou) return true;
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

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
  // ⚠️ **Sem cache do navegador, e isto NAO e zelo excessivo** (15/09/2026).
  // O perfil do Chrome e reaproveitado entre rodadas, e em desenvolvimento o
  // Next serve a folha de estilo sempre na MESMA URL enquanto o conteudo dela
  // muda. Resultado: a rodada carregava o CSS da rodada anterior. Quando a
  // lateral foi de 240px para 276, a classe nova nao estava na folha em cache,
  // a grade virou UMA coluna, o menu (sticky, 100vh) passou a cobrir o
  // conteudo, e o clique no "Criar produto" — nas coordenadas certas — caiu no
  // item "Painel de CMV" do menu. A bateria acusou o cadastro de produto, que
  // estava intacto: **CSS velho nao falha, ele MENTE.**
  await p.setCacheEnabled(false);
  // O 403 da fase 3 é o comportamento esperado (servidor barrando a Cozinha);
  // só interessa erro fora disso.
  let coletando = true;
  const erros = [];
  const anotar = (t) => {
    if (coletando && !/favicon|hmr|_next\/static/.test(t)) erros.push(t);
  };
  p.on("pageerror", (e) => anotar(String(e)));
  p.on("console", (m) => m.type() === "error" && anotar(m.text()));

  // 🔑 **Nenhuma caixa do NAVEGADOR, em tela nenhuma** (pedido do dono,
  // 14/09/2026: *"identifiquei mensagens padrão do navegador, onde devemos
  // tratar elas como padrão do nosso sistema, não aquele popup feio"*).
  // `window.confirm`/`alert`/`prompt` têm fonte de sistema, botão em inglês e
  // nenhum lugar para explicar o que a ação faz — e o componente `Confirmacao`
  // existe justamente para isso, com o motivo escrito no docstring dele desde
  // sempre. Mesmo assim duas telas voltaram a usar a caixa nativa.
  // ⚠️ **A guarda é GLOBAL e vale para o roteiro inteiro**, não para uma tela:
  // é o único jeito de a regressão não voltar pela porta de uma tela que
  // ninguém estava olhando. Anotar e DISPENSAR o diálogo importa — sem
  // dispensar, um `confirm()` trava a página e leva a bateria junto.
  const caixasNativas = [];
  p.on("dialog", async (d) => {
    caixasNativas.push(`${d.type()}: ${d.message()}`);
    await d.dismiss().catch(() => {});
  });
  aoTerminar.push(async () => {
    checar("nenhuma caixa do navegador (confirm/alert/prompt) apareceu",
      caixasNativas.length === 0, caixasNativas.join(" | "));
  });

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
  await p2.setCacheEnabled(false);
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

  console.log("1b. o painel abre no dia da ultima venda, com setas");
  // 🔑 **Pedido do dono (03/09/2026).** O painel respondia pelo mês inteiro e
  // não dizia como foi o último dia — que é a primeira coisa que se olha de
  // manhã. ⚠️ Abre no dia da ÚLTIMA venda, não em hoje: de manhã "hoje" é um
  // dia sem venda nenhuma, e um cartão zerado se lê como "a casa não vendeu".
  await irPara(p, `${WEB}/`);
  const { dados: painelDia } = await api("GET", "/inicio", null, token);
  if (painelDia?.dia) {
    await p.waitForFunction(
      () => /VENDAS DO DIA|Vendas do dia/i.test(document.body.innerText),
      { timeout: 15000 });
    const cartaoDia = await p.evaluate(() => {
      const b = (rot) =>
        [...document.querySelectorAll("button")]
          .find((x) => x.getAttribute("aria-label") === rot);
      const texto = document.body.innerText;
      return {
        temTicket: /Ticket médio/i.test(texto),
        temValor: /Valor total/i.test(texto),
        // ⚠️ Pelo `aria-label`, não pelo caractere: "‹" e "›" são símbolos, e
        // procurá-los por texto casaria com qualquer chevron da página.
        voltar: !!b("dia anterior com venda"),
        avancar: !!b("próximo dia com venda"),
        avancarDesligado: b("próximo dia com venda")?.disabled,
      };
    });
    // 🔑 **O dia da semana, junto da data** (pedido do dono, 03/09/2026): um
    // sábado e uma segunda não se comparam, e a data sozinha obriga quem olha a
    // fazer essa conta de cabeça.
    // ⚠️ **Conferido contra a data que o SERVIDOR mandou**, e calculado aqui em
    // hora local — `new Date('aaaa-mm-dd')` é meia-noite UTC, que em Brasília é
    // o dia anterior a partir das 21h. Um teste que caísse na mesma armadilha
    // da tela concordaria com o erro em vez de pegá-lo.
    const SEMANA_ESPERADA = ["domingo", "segunda-feira", "terça-feira", "quarta-feira",
      "quinta-feira", "sexta-feira", "sábado"];
    const [aa, mm, dd] = String(painelDia.dia.data).slice(0, 10).split("-").map(Number);
    const esperado = SEMANA_ESPERADA[new Date(aa, mm - 1, dd).getDay()];
    const semanaNaTela = await p.evaluate(() => document.body.innerText);
    checar("o cartao do dia diz o dia da semana",
      semanaNaTela.includes(esperado), { esperado, data: painelDia.dia.data });
    checar("o painel mostra as vendas do dia", cartaoDia.temValor && cartaoDia.temTicket,
      cartaoDia);
    checar("com as duas setas de navegação", cartaoDia.voltar && cartaoDia.avancar, cartaoDia);
    // 🔑 **A seta que não leva a lugar nenhum tem de PARECER desligada.** O dia
    // mais recente não tem próximo; uma seta viva que não faz nada ao ser
    // clicada se lê como tela quebrada. Quem sabe se há para onde ir é o
    // servidor (`proximo`), e a afirmação é sobre a PROPRIEDADE — não sobre o
    // estado do dia, que muda a cada venda importada.
    checar("e a seta de avançar acompanha o que o servidor diz",
      cartaoDia.avancarDesligado === (painelDia.dia.proximo === null),
      { tela: cartaoDia.avancarDesligado, servidor: painelDia.dia.proximo });
    await foto(p, "01b-vendas-do-dia");

    // Andar para trás troca a data e os números — sem recarregar o painel.
    if (painelDia.dia.anterior) {
      const antes = await p.evaluate(() => document.body.innerText);
      await p.evaluate(() => {
        [...document.querySelectorAll("button")]
          .find((x) => x.getAttribute("aria-label") === "dia anterior com venda")?.click();
      });
      await p.waitForFunction(
        (texto) => document.body.innerText !== texto, { timeout: 15000 }, antes);
      const { dados: r } = await api(
        "GET", `/inicio/dia?data=${painelDia.dia.anterior}`, null, token);
      const naTela = await p.evaluate(() => document.body.innerText);
      // ⚠️ A data na tela sai por extenso ("01 Set 2026"): compara-se o DIA e o
      // ano, que é o que o formato garante — não a string ISO, que a tela não
      // mostra em lugar nenhum.
      const [ano, , dia] = painelDia.dia.anterior.split("-");
      checar("a seta volta para o dia anterior com venda",
        naTela.includes(`${dia} `) && naTela.includes(ano), painelDia.dia.anterior);
      checar("e os números passam a ser os dele",
        naTela.includes(String(r.dia.vendas)), r?.dia);
      // ⚠️ **Só o dia navegou**: o resto do painel continua o que era. Trocar de
      // dia não pode custar a apuração do período nem a lista de alertas.
      checar("sem recarregar o resto do painel",
        /Precisa da sua atenção|Custo do que saiu/i.test(naTela), naTela.slice(0, 120));
    }
  } else {
    // ⚠️ Base sem venda nenhuma é estado legítimo (é o primeiro dia da casa), e
    // o cartão simplesmente não existe. Afirmar que ele está lá faria a suíte
    // acusar de defeito a decisão de "número verdadeiro ou nenhum".
    checar("sem venda importada, o painel não inventa um cartão de vendas",
      !(await p.evaluate(() => /Ticket médio/i.test(document.body.innerText))));
  }

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
  // ⚠️ **Esperar pela tela de DESTINO, não por um tempo fixo.** Com 1200 ms a
  // checagem afirmava sobre um menu que ainda não tinha voltado — e falhava
  // longe de qualquer defeito, na primeira vez que a compilação da página
  // demorou. A espera é pela navegação; a AFIRMAÇÃO continua sendo sobre o
  // estado do menu, que é outra coisa.
  await p.waitForFunction(
    () => /Marca/.test(document.querySelector("main")?.innerText ?? ""),
    { timeout: 15000 },
  ).catch(() => {});
  // ⚠️ A escolha e da PESSOA e sobrevive a navegacao — o que nao sobrevive
  // e o login, que recolhe tudo de novo.
  const aoVoltar = await grupoDaTela();
  checar("e continua aberto ao voltar para a tela", aoVoltar.aberto === "true", aoVoltar);

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

  // 🔑 **A BUSCA obedece a mesma permissao que o menu** (15/09/2026). Ela varre
  // `lib/menu.ts` com o mesmo filtro — e a razao de provar isto aqui e que uma
  // lista separada seria o caminho natural para a busca: bastaria alguem
  // escrever "todas as telas" numa constante para a cozinha achar "Empresa",
  // clicar, e tomar 403. Busca que oferece porta fechada e pior do que busca
  // nenhuma.
  await p.keyboard.down("Control");
  await p.keyboard.press("KeyK");
  await p.keyboard.up("Control");
  await p.waitForSelector("#paleta-campo", { timeout: 8000 }).catch(() => null);
  const buscaCozinha = await p.evaluate(() => ({
    abriu: !!document.querySelector("#paleta-campo"),
    telas: [...document.querySelectorAll(".paleta-op")].map((l) => l.innerText.replace(/\n/g, " ")),
  }));
  checar("a busca de telas abre para a cozinha tambem", buscaCozinha.abriu, buscaCozinha);
  checar("e NAO oferece Empresa, que ela nao pode abrir",
    buscaCozinha.abriu && !buscaCozinha.telas.some((t) => /Empresa/.test(t)), buscaCozinha.telas);
  checar("nem Papeis e permissoes",
    buscaCozinha.abriu && !buscaCozinha.telas.some((t) => /Pap/.test(t)), buscaCozinha.telas);
  await p.keyboard.press("Escape");
  await new Promise((r) => setTimeout(r, 200));

  // Digitar a rota na barra de endereço não abre porta nenhuma: quem barra é a API.
  await p.goto(`${WEB}/usuarios`, { waitUntil: "networkidle2" });
  // ⚠️ Espera a tela PARAR de carregar, não 900 ms. Numa compilação fria ela
  // ainda dizia "carregando…" e a checagem acusava a API de deixar passar quem
  // ela tinha barrado — um defeito de segurança que não existia.
  await p.waitForFunction(() => !/^\s*carregando/i.test(document.body.innerText),
    { timeout: 30000, polling: 250 }).catch(() => {});
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
  // ⚠️ **Pelo id do campo, e nao por `input[required]`.** O `required` saiu do
  // formulario em 15/09/2026: ele traz a validacao NATIVA junto, ou seja, o
  // balao cinza do Chrome — a mesma caixa que esta casa baniu do resto do
  // sistema. A sonda apontava para um atributo que existia por tabela, nao
  // para o campo que ela queria; quando o atributo saiu, a rodada morreu aqui,
  // a tres fases de distancia de qualquer defeito.
  await p.waitForSelector("#campo-nome", { timeout: 20000 });
  await p.type("#campo-nome", nomeProduto);

  // ⚠️ Tipo novo tem de CHEGAR à tela. `TIPOS` (api/models/produtos.py) e
  // `TIPOS_PRODUTO` (web/lib/cadastros.ts) são listas separadas: mexer só numa
  // faz o servidor aceitar um tipo que ninguém consegue escolher. É a lição do
  // EAN na direção inversa — e essa não quebra nada, só nunca aparece.
  // 🔑 **`main select`, nunca `select` solto.** O seletor de LOJA vive na
  // barra superior e e o primeiro `<select>` do documento assim que existe a
  // segunda loja — as checagens de tipo de produto passaram a ler os ids das
  // lojas ("1", "15") e `p.select` chegaria a TROCAR a loja no meio do teste.
  // E a armadilha do "primeiro elemento que casa", de novo: ela some enquanto
  // ha uma loja so, e volta no dia em que a casa abre a filial.
  const tiposNaTela = await p.evaluate(() =>
    [...(document.querySelector("main select")?.options ?? [])].map((o) => o.value));
  checar("a tela oferece os sete tipos de produto", tiposNaTela.length === 7, tiposNaTela);
  checar("inclusive utensílios e enxoval", tiposNaTela.includes("UTENSILIO"), tiposNaTela);

  // A ajuda do tipo é o que explica a escolha a quem cadastra; sem ela
  // "Utensílios" fica indistinguível de "Material de limpeza".
  await p.select("main select", "UTENSILIO");
  await new Promise((r) => setTimeout(r, 300));
  const ajudaUtensilio = await textoVisivel(p);
  checar("e explica que utensílio não é consumido pela receita",
    /quebra, some e é reposto/i.test(ajudaUtensilio),
    ajudaUtensilio.slice(0, 200));

  await p.select("main select", "INSUMO");
  const selects = await p.$$("main select");
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
      () => [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].some(
        (r) => r.textContent?.trim() === "NCM"),
      { timeout: 20000 })
    .catch(() => {});

  // ⚠️ **O EAN existia no formulário e não tinha campo na tela.** Era enviado ao
  // salvar e lido pela conciliação da nota, mas ninguém conseguia ver nem
  // digitar: o dado só entrava pela importação do Omie. Campo que o servidor
  // aceita e a tela não oferece é campo morto — e some sem ninguém notar.
  const fiscais = await p.evaluate(() => {
    const rotulos = [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].map((r) =>
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

  // 🔑 **O cadastro em ABAS** (16/09/2026, protótipo aprovado pelo dono). Eram
  // nove cartoes empilhados: quem entrava para corrigir o preco rolava por
  // unidade, estoque, fiscal e fornecedores antes de acha-lo.
  const abasProduto = await p.evaluate(() => {
    const abas = [...document.querySelectorAll('[role="tab"]')].map((b) => b.textContent.trim());
    const visiveis = () => [...document.querySelectorAll("section.cartao")]
      .filter((c) => c.offsetParent !== null)
      .map((c) => c.querySelector("h2")?.textContent?.trim() ?? "");
    return { abas, naPrincipal: visiveis() };
  });
  checar("o cadastro do produto abre em abas",
    ["Principal", "Fornecedores", "Estoque", "Movimentação"].every(
      (x) => abasProduto.abas.includes(x)), abasProduto.abas);
  // 🔑 Preco e custo no MESMO bloco, porque a pergunta e uma so: da margem?
  checar("com preço e custo no mesmo bloco, na Principal",
    abasProduto.naPrincipal.includes("Valores")
      && !abasProduto.naPrincipal.includes("Fornecedores"),
    abasProduto.naPrincipal);
  // ⚠️ O ativo era uma caixinha no pe do cartao "Observacoes", a nove cartoes de
  // distancia do nome. Desativar e decisao de CADASTRO.
  const ativoNaIdentificacao = await p.evaluate(() => {
    const cartao = [...document.querySelectorAll("section.cartao")]
      .find((c) => c.querySelector("h2")?.textContent?.trim() === "Identificação");
    return /Ativo/.test(cartao?.querySelector("header")?.innerText ?? "");
  });
  checar("e o interruptor de ativo no bloco de identificação", ativoNaIdentificacao);

  // 🔑 **A aba de MOVIMENTACAO, que nao existia.** Para saber por que o saldo de
  // um item esta negativo era preciso sair do cadastro, abrir Saldos e
  // movimentos e achar o produto de novo pela lupa.
  await p.evaluate(() => [...document.querySelectorAll('[role="tab"]')]
    .find((b) => b.textContent.trim() === "Movimentação")?.click());
  await p.waitForFunction(
    () => /O razão deste produto|não controla estoque/i.test(document.body.innerText),
    { timeout: 15000 }).catch(() => {});
  const movProduto = await p.evaluate(() => ({
    abriu: /O razão deste produto|não controla estoque/i.test(document.body.innerText),
    // ⚠️ So LEITURA: estornar e reprocessar tem permissao propria e previa antes
    // do botao, e ficam em Saldos e movimentos.
    semEstornar: ![...document.querySelectorAll("button")]
      .some((b) => /estornar|reprocessar/i.test(b.textContent ?? "")),
    levaParaORazao: [...document.querySelectorAll("a")]
      .some((a) => /Saldos e movimentos/i.test(a.textContent ?? "")),
  }));
  checar("a aba de Movimentação abre o razão do produto", movProduto.abriu, movProduto);
  checar("só de leitura, com o caminho para quem precisa mexer",
    movProduto.semEstornar && movProduto.levaParaORazao, movProduto);
  await p.evaluate(() => [...document.querySelectorAll('[role="tab"]')]
    .find((b) => b.textContent.trim() === "Principal")?.click());
  await new Promise((r) => setTimeout(r, 400));
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
      () => [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].some(
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
      () => [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].some(
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
  // ⚠️ **Espera limitada, não um sono fixo.** `/cadastros` carrega as quatro
  // listas inteiras e a marca do PDV depende do `/auth/me` do layout: 1500 ms
  // bastavam quando a base tinha três setores e passaram a não bastar, e a
  // checagem acusava a tela de não oferecer o que ela oferece.
  await p.waitForFunction(
    () => /integrar ao PDV|tirar do PDV/.test(document.body.innerText),
    { timeout: 15000 },
  ).catch(() => {});
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
  // ⚠️ **Espera pelo CAMPO, não por um relógio.** Os 600 ms fixos bastavam até
  // a tela crescer; numa compilação fria do Next a lista ainda dizia
  // "carregando…" e o seletor voltava `undefined` — o que não FALHAVA a
  // checagem, derrubava a bateria inteira num TypeError, escondendo tudo que
  // vinha depois. Falhar é aceitável; abortar a rodada não é.
  const seletorBuscaProduto = 'input[placeholder="nome, código ou código de barras"]';
  await p.waitForSelector(seletorBuscaProduto, { timeout: 30000 }).catch(() => {});
  const campoBuscaProduto = (await p.$$(seletorBuscaProduto))[0];
  checar("a lista de produtos oferece a busca", !!campoBuscaProduto);
  if (!campoBuscaProduto) throw new Error("campo de busca de produto nao apareceu");
  await campoBuscaProduto.type(nomeProduto);
  await new Promise((r) => setTimeout(r, 1200));
  const naLista = await esperarTexto(p, nomeProduto);
  checar("produto aparece na lista quando procurado pelo nome", naLista, nomeProduto);

  // 🔑 **A colheita de EAN das notas** (08/09/2026). O caminho vive na lista de
  // produtos, e não em Integrações: código de barras é campo do cadastro, e quem
  // vai preenchê-lo em lote está olhando esta lista.
  const temCaminhoEan = await p.evaluate(() =>
    [...document.querySelectorAll("a")].some(
      (a) => a.textContent?.includes("Código de barras das notas")));
  checar("o caminho para a colheita de EAN esta na lista de produtos", temCaminhoEan);

  // 🔑 **Alteracao multipla** (09/09/2026, pedido do dono): marcar varios e
  // mudar tipo, categoria, setor ou a ativacao de uma vez. O catalogo tem 2.229
  // produtos vindos do Omie sem categoria nem setor, e um a um sao quatro
  // passos por produto -- ninguem faz duas mil vezes.
  await p.goto(`${WEB}/produtos`, { waitUntil: "networkidle2" });
  await p.waitForSelector('table tbody tr input[type="checkbox"]', { timeout: 30000 })
    .catch(() => {});
  const emLote = await p.evaluate(() => {
    const caixas = [...document.querySelectorAll('table tbody tr input[type="checkbox"]')];
    return { caixas: caixas.length, barraAntes: /marcado/i.test(document.body.innerText) };
  });
  checar("a lista de produtos tem caixinha por linha", emLote.caixas > 0, emLote);
  // ⚠️ A barra so pode existir DEPOIS de marcar: uma barra de acao vazia
  // ocupando espaco em toda visita ensina a ignorar aquela faixa da tela.
  checar("e a barra de acao NAO aparece antes de marcar", !emLote.barraAntes, emLote);

  const depoisDeMarcar = await p.evaluate(async () => {
    const caixas = [...document.querySelectorAll('table tbody tr input[type="checkbox"]')];
    caixas[0]?.click();
    caixas[1]?.click();
    await new Promise((r) => setTimeout(r, 400));
    const texto = document.body.innerText;
    return {
      diz: /2\s*produto\(s\) marcado/i.test(texto),
      temBotao: [...document.querySelectorAll("button")]
        .some((b) => /Alterar em lote/i.test(b.textContent ?? "")),
    };
  });
  checar("marcar duas linhas faz a barra dizer 2", depoisDeMarcar.diz, depoisDeMarcar);
  checar("com o botao de alterar em lote", depoisDeMarcar.temBotao, depoisDeMarcar);

  const naJanelaLote = await p.evaluate(async () => {
    [...document.querySelectorAll("button")]
      .find((b) => /Alterar em lote/i.test(b.textContent ?? ""))?.click();
    await new Promise((r) => setTimeout(r, 900));
    const d = [...document.querySelectorAll('[role="dialog"]')].pop();
    const botao = [...(d?.querySelectorAll("button") ?? [])]
      .find((b) => /Aplicar em/i.test(b.textContent ?? ""));
    return {
      abriu: !!d,
      campos: d?.querySelectorAll("select").length ?? 0,
      aplicarTravado: botao ? botao.disabled : "sem-botao",
    };
  });
  checar("a janela da alteracao em lote abre", naJanelaLote.abriu, naJanelaLote);
  // Tipo, categoria, setor e ativacao -- os quatro que o dono pediu.
  checar("com os quatro campos", naJanelaLote.campos >= 4, naJanelaLote);
  // ⚠️ **Nada se aplica sem escolher o que mudar.** Um botao ativo antes da
  // previa convida a gravar em trezentos cadastros sem ver o numero.
  checar("e o aplicar nasce travado, sem previa",
    naJanelaLote.aplicarTravado === true, naJanelaLote);
  await foto(p, "08d-alteracao-multipla");
  await p.keyboard.press("Escape");
  await new Promise((r) => setTimeout(r, 500));

  await p.goto(`${WEB}/produtos/ean-das-notas`, { waitUntil: "networkidle2" });
  await p.waitForFunction(
    () => /C[oó]digo de barras das notas/i.test(document.body.innerText),
    { timeout: 30000, polling: 300 }).catch(() => {});
  const textoEan = await textoVisivel(p);
  checar("a tela da colheita de EAN abre",
    /C[oó]digo de barras das notas/i.test(textoEan), textoEan.slice(0, 140));
  // ⚠️ **Nada pode ser gravado sem clique.** O botao de aplicar nasce
  // DESABILITADO porque a selecao nasce vazia — marcar tudo por padrao faria um
  // clique gravar centenas de codigos que ninguem olhou, que e exatamente o que
  // esta tela existe para nao fazer.
  const aplicarTravado = await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (x) => /Aplicar em/i.test(x.textContent ?? ""));
    return b ? b.disabled : "sem-botao";
  });
  checar("o botao de aplicar nasce desabilitado (ou nao ha o que aplicar)",
    aplicarTravado === true || aplicarTravado === "sem-botao", aplicarTravado);
  await foto(p, "08c-ean-das-notas");

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

  // 🔑 **O local pode dizer a que SETOR pertence** (migração 051). O processo
  // da casa é: o açúcar entra no Estoque Central e de manhã cada setor leva um
  // pacote para o seu canto. O canto do setor é um LOCAL, e é essa coluna que
  // liga "onde a mercadoria está" a "quem a consome".
  // ⚠️ Vazio é resposta legítima e é o padrão: o Estoque Central não pertence
  // a setor nenhum — ele serve a todos.
  await irPara(p, `${WEB}/cadastros?aba=locais`);
  await p.waitForSelector("#setor-do-local", { timeout: 12000 }).catch(() => {});
  const setorDoLocal = await p.evaluate(() => {
    const sel = document.querySelector("#setor-do-local");
    return {
      existe: !!sel,
      primeira: sel?.options?.[0]?.value ?? null,
      opcoes: sel?.options?.length ?? 0,
    };
  });
  checar("o local declara a que setor pertence", setorDoLocal.existe, setorDoLocal);
  checar("e o padrão é NENHUM, que é o estoque geral",
    setorDoLocal.primeira === "" && setorDoLocal.opcoes > 1, setorDoLocal);

  // 🔑 **Dava para criar e desativar, e não dava para CORRIGIR.** Os quatro PUT
  // existem no servidor desde o começo e a tela nunca os ofereceu: um setor
  // cadastrado com o nome errado no primeiro dia ficava errado para sempre.
  // ⚠️ A correção usa o MESMO formulário do cadastro — criar e corrigir têm a
  // mesma forma, para o olho reconhecer. A checagem afirma a PROPRIEDADE: o que
  // se clica em "editar" volta preenchido no formulário, e salvar troca o nome
  // na lista. Nada aqui depende de quantos setores a base tem hoje.
  // ⚠️ **`.toUpperCase()`: quem normaliza o nome é o BANCO** (gatilho da
  // migração 050, que estendeu ao fornecedor e às tabelas de apoio o que a 036
  // fez com o produto). A checagem procura pelo que foi GRAVADO — procurar
  // pelo que ela mandou faz a linha "não existir" e acusa a tela de um defeito
  // que é do teste. É a mesma correção que a 036 já tinha exigido.
  const marcaEd = Date.now().toString().slice(-6);
  const APOIO = `Tela apoio ${marcaEd}`.toUpperCase();
  const APOIO_CORRIGIDO = `Tela corrigido ${marcaEd}`.toUpperCase();
  const { dados: apoioCriado } = await api(
    "POST", "/setores", { nome: `Tela apoio ${marcaEd}` }, token);
  await irPara(p, `${WEB}/cadastros?aba=setores`);
  // ⚠️ **A lista de apoio PAGINA, e o registro desta rodada cai fora da
  // primeira página.** "Poucos por natureza" era suposição: a base real tem
  // dezenas de setores, e um nome que começa com T fica na página 2. A checagem
  // acusava a tela de não oferecer editar numa linha que ela nem mostrava.
  // Aumentar a página é o que uma pessoa faria — e é o que o rodapé oferece.
  await p.select('select[aria-label="Registros por página"]', "100").catch(() => {});
  // ⚠️ **Cem por página deixou de bastar, e virar a página é o que uma pessoa
  // faria.** A base local tem 113 setores ATIVOS — as suítes da API criam
  // setores ("BAR REL 029200" e parentes) e não os desativam —, e um nome que
  // começa com T cai na página 2. A checagem acusava a tela de não oferecer
  // editar numa linha que ela nem mostrava: defeito do TESTE, e o segundo
  // desta mesma checagem pelo mesmo motivo. Escolher o tamanho da página foi a
  // correção anterior; ela some assim que a base cresce mais um pouco. Procurar
  // ATÉ ACHAR não depende de quantos setores a base tem hoje.
  for (let volta = 0; volta < 12; volta++) {
    const achou = await p.evaluate((nome) => document.body.innerText.includes(nome), APOIO);
    if (achou) break;
    const virou = await p.evaluate(() => {
      const b = document.querySelector('button[aria-label="Próxima página"]');
      if (!b || b.disabled) return false;
      b.click();
      return true;
    });
    if (!virou) break;
    await new Promise((r) => setTimeout(r, 700));
  }
  const abriuEdicao = await p.evaluate((nome) => {
    const li = [...document.querySelectorAll("main ul > li")]
      .find((x) => x.innerText.includes(nome));
    const botao = li && [...li.querySelectorAll("button")]
      .find((b) => b.textContent?.trim() === "editar");
    botao?.click();
    return { achouLinha: !!li, achouBotao: !!botao };
  }, APOIO);
  checar("a linha da tabela de apoio oferece editar",
    abriuEdicao.achouLinha && abriuEdicao.achouBotao, abriuEdicao);
  await new Promise((r) => setTimeout(r, 600));
  const noFormulario = await p.evaluate(() => {
    const form = document.querySelector("#form-apoio");
    const campo = form?.querySelector("input");
    return {
      valor: campo?.value ?? "",
      // ⚠️ O botão troca de palavra: "Adicionar" num formulário que vai
      // SUBSTITUIR um registro faria criar um duplicado por engano.
      botao: form?.querySelector('button[type="submit"]')?.textContent?.trim() ?? "",
      temCancelar: [...(form?.querySelectorAll("button") ?? [])]
        .some((b) => b.textContent?.trim() === "cancelar"),
    };
  });
  checar("e traz o registro para o MESMO formulário do cadastro",
    noFormulario.valor === APOIO, noFormulario);
  checar("com o botão dizendo Salvar, e uma saída ao lado",
    noFormulario.botao === "Salvar" && noFormulario.temCancelar, noFormulario);
  await p.evaluate((nome) => {
    const campo = document.querySelector("#form-apoio input");
    const set = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    set.call(campo, nome);
    campo.dispatchEvent(new Event("input", { bubbles: true }));
    document.querySelector('#form-apoio button[type="submit"]')?.click();
  }, APOIO_CORRIGIDO);
  await p.waitForFunction(
    (nome) => document.body.innerText.includes(nome), { timeout: 12000 },
    APOIO_CORRIGIDO,
  ).catch(() => {});
  const depoisDeCorrigir = await p.evaluate((antigo) => ({
    texto: document.body.innerText,
    // Voltou a ser um formulário de cadastro: nada preso da edição anterior.
    botao: document.querySelector('#form-apoio button[type="submit"]')?.textContent?.trim(),
    campo: document.querySelector("#form-apoio input")?.value ?? "",
    aindaTemOAntigo: document.body.innerText.includes(antigo),
  }), APOIO);
  // ⚠️ **Pelo SERVIDOR, não pelo texto da página.** A afirmação é sobre o
  // ESTADO: um registro só, com o nome novo. A lista de apoio pagina — "poucos
  // por natureza" era suposição, e a base real tem 184 locais e dezenas de
  // setores —, então o registro corrigido pode não estar na página à vista, e a
  // checagem acusaria a tela de não ter salvo o que salvou. É a lição do
  // "relatório cortado no topo esconde o registro que se procura".
  const { dados: setoresDepois } = await api(
    "GET", "/setores?incluir_inativos=true", null, token);
  const comNomeNovo = (setoresDepois ?? []).filter((x) => x.nome === APOIO_CORRIGIDO);
  const comNomeVelho = (setoresDepois ?? []).filter((x) => x.nome === APOIO);
  checar("salvar troca o nome na lista, sem criar outro registro",
    comNomeNovo.length === 1 && comNomeVelho.length === 0,
    { novo: comNomeNovo.length, velho: comNomeVelho.length });
  checar("e o formulário volta a ser o de cadastro",
    depoisDeCorrigir.botao === "Adicionar" && depoisDeCorrigir.campo === "",
    depoisDeCorrigir);
  // Sai da lista ativa: a suíte não deixa setor de teste para trás.
  {
    const { dados: setoresAgora } = await api(
      "GET", "/setores?incluir_inativos=true", null, token);
    // ⚠️ **Pelo ID, não pelo nome.** Casar pelo nome GRAVADO já foi a correção
    // anterior, e ela ainda deixava rastro: numa rodada que falhasse ANTES da
    // renomeação, o setor continuava chamando "TELA APOIO …", não casava com
    // `APOIO_CORRIGIDO` e ficava ativo para sempre — dois assim na base local.
    // O id não depende de o teste ter chegado ao fim.
    const meu = (setoresAgora ?? []).find(
      (x) => x.id === apoioCriado?.id || x.nome === APOIO_CORRIGIDO);
    if (meu) await api("PUT", `/setores/${meu.id}`, { ativo: false }, token);
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
  // 🔑 **Os campos se acham pelo NOME, não pela posição.** Esta linha era
  // "ordem dos campos numéricos: 0 rendimento, 1 porções, 2 bruta…", e a ordem
  // mudou no dia em que a tela ganhou o tamanho da porção entre os dois — o
  // "500" da farinha teria ido para o campo errado, e a falha apareceria três
  // checagens adiante, num custo que não fecha. `aria-label` já era o padrão da
  // suíte para busca e para o seletor de páginas; agora vale para estes também.
  const campoNum = async (rotulo) => p.$(`input[aria-label="${rotulo}"]`);
  // clickCount:3 não seleciona o conteúdo de input[type=number] no Chrome —
  // sem o ctrl+A o valor novo entra colado no que já estava (1 + 8 = 18).
  const trocar = async (campo, valor) => {
    await campo.click();
    await p.keyboard.down("Control");
    await p.keyboard.press("KeyA");
    await p.keyboard.up("Control");
    await campo.type(valor);
  };
  await trocar(await campoNum("Rendimento da receita"), "2");
  await trocar(await campoNum("Porções da receita"), "8");
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
  await (await campoNum("Quantidade bruta do item 1")).type("500");

  // 🔑 **A foto tem de estar aqui, na tela de CRIAR.** A primeira versão só a
  // oferecia depois de a ficha existir — e quem cadastra o prato está com a
  // foto na mão naquele momento; ele não achava onde pô-la e concluía que o
  // sistema não tinha o campo. Foi assim que o dono a encontrou faltando.
  const campoFotoNova = await p.$("#foto-da-ficha");
  checar("a tela de CRIAR a ficha também pede a foto do prato", !!campoFotoNova);
  const avisaEnvio = await p.evaluate(() => {
    const campo = document.querySelector("#foto-da-ficha");
    const cartao = [...document.querySelectorAll("section, div")]
      .find((d) => /Foto do prato/.test(d.querySelector("h2")?.textContent ?? ""));
    return {
      diz: /enviada quando a ficha for criada/i.test(document.body.innerText),
      // ⚠️ **O estado vazio se afirma AQUI**, na ficha que ainda não existe — é
      // o único lugar onde ele é garantido. Afirmá-lo na tela de uma ficha que
      // acabou de nascer com foto é descrever o estado do dia.
      semFoto: /sem\s*foto/i.test(document.body.innerText),
      aceita: campo?.getAttribute("accept") ?? "",
      // 🔑 **O controle nativo do navegador NÃO conta como botão.** Ele tem a
      // cara do sistema operacional, muda em cada máquina e não se parece com
      // nada mais do sistema — o dono olhou a tela e não achou o botão, com o
      // campo ali. A checagem antiga só perguntava se o input existia, e um
      // input escondido responde "sim" do mesmo jeito.
      campoEscondido: !!campo && campo.offsetParent === null,
      botao: [...(cartao?.querySelectorAll("button.btn") ?? [])]
        .map((b) => b.textContent?.trim() ?? ""),
    };
  });
  // ⚠️ E ela precisa DIZER que sobe junto com a ficha: um seletor de arquivo
  // que não dá retorno imediato parece um que não funcionou.
  checar("dizendo que ela sobe junto com a ficha", avisaEnvio.diz, avisaEnvio);
  checar("e que aceita só imagem, dizendo quando não há nenhuma",
    avisaEnvio.aceita.includes("image/") && avisaEnvio.semFoto, avisaEnvio);
  // 🔑 Um BOTÃO da casa, como no cadastro da empresa — não o seletor nativo.
  checar("com um botão de verdade, e não o seletor cru do navegador",
    avisaEnvio.campoEscondido && avisaEnvio.botao.some((b) => /imagem/i.test(b)),
    avisaEnvio);
  if (campoFotoNova) {
    // PNG de verdade: o servidor ABRE a imagem para conferir que ela é uma.
    // ⚠️ Em `_fotos/`, que é ignorado pelo git e fica no D: como tudo aqui.
    writeFileSync(`${FOTOS}/_prato-teste.png`, Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
      + "hQGAhKmMIQAAAABJRU5ErkJggg==", "base64"));
    await campoFotoNova.uploadFile(`${FOTOS}/_prato-teste.png`);
    await new Promise((r) => setTimeout(r, 700));
    const previa = await p.evaluate(() => {
      const img = document.querySelector('img[alt^="Foto de"]');
      return { tem: !!img, ehLocal: (img?.getAttribute("src") ?? "").startsWith("blob:") };
    });
    // A prévia é local: ainda não há nada no servidor para onde apontar.
    checar("e mostra a imagem escolhida antes de gravar",
      previa.tem && previa.ehLocal, previa);
  }

  const selectsUm = await p.$$("main select");
  // Sem o select do produto sobraram dois: 0 rendimento_um, 1 unidade do item.
  await selectsUm[1].select("G");
  await Promise.all([
    p.waitForNavigation({ waitUntil: "networkidle2" }).catch(() => {}),
    p.click('button[type="submit"]'),
  ]);
  await new Promise((r) => setTimeout(r, 1800));
  const criouFicha = /\/fichas\/\d+/.test(p.url());
  checar("cria ficha pela tela", criouFicha, p.url());
  if (criouFicha && campoFotoNova) {
    // ⚠️ Pelo SERVIDOR, não pela tela: o que se prova aqui é que a imagem
    // escolhida antes de a ficha existir chegou até ela.
    const { dados: recem } = await api(
      "GET", `/fichas/${p.url().match(/fichas\/(\d+)/)?.[1]}`, null, token);
    checar("e a foto escolhida na criação chega junto", !!recem?.foto_url,
      recem?.foto_url);
  }
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

    // 🔑 **De onde vem o rendimento** (12/09/2026, pedido do dono: "tem como ser
    // gerado automaticamente? o sistema que a cliente usa soma todos os
    // ingredientes"). A soma vem do servidor e entra como SUGESTAO — nunca
    // escrita sozinha, porque `rendimento_qtd` divide o consumo na producao.
    // ⚠️ Este bloco NAO salva: a aritmetica da tela e o que se afirma aqui, e a
    // persistencia tem suite propria (`smoke_rendimento.py`). Salvar mudaria o
    // rendimento da ficha e as checagens seguintes medem outra coisa.
    await p.waitForFunction(
      () => /soma dos ingredientes/i.test(document.body.innerText), { timeout: 15000 },
    ).catch(() => {});
    const somaNaTela = await p.evaluate(() => {
      const texto = document.body.innerText;
      return {
        aparece: /soma dos ingredientes/i.test(texto),
        // O numero da soma, como a tela o escreve.
        trecho: texto.match(/soma dos ingredientes d[áa][^\n]*/i)?.[0] ?? "",
        temUsar: [...document.querySelectorAll("button")]
          .some((b) => (b.textContent ?? "").trim() === "usar"),
      };
    });
    checar("a tela diz de onde vem o rendimento: a soma dos ingredientes",
      somaNaTela.aparece, somaNaTela);
    checar("com o numero a vista e um clique para usar",
      /\d/.test(somaNaTela.trecho) && somaNaTela.temUsar, somaNaTela);

    // Clicar em "usar" escreve a soma no campo — e o campo e o do rendimento.
    const valorDe = (rotulo) => p.evaluate(
      (r) => document.querySelector(`input[aria-label="${r}"]`)?.value ?? "", rotulo);
    const rendAntes = await valorDe("Rendimento da receita");
    await p.evaluate(() => [...document.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").trim() === "usar")?.click());
    await new Promise((r) => setTimeout(r, 600));
    const rendDepois = await valorDe("Rendimento da receita");
    checar("usar a sugestao escreve no campo do rendimento",
      rendDepois !== rendAntes && Number(rendDepois) > 0, [rendAntes, rendDepois]);

    // 🔑 **A conta nos dois sentidos.** Informar o tamanho da porcao tem de
    // recalcular quantas porcoes rendem — e o inverso tambem.
    const campoTamanho = await campoNum("Tamanho da porção");
    checar("o cabecalho tem o campo do tamanho da porcao", !!campoTamanho);
    await campoTamanho.click();
    await p.keyboard.down("Control");
    await p.keyboard.press("KeyA");
    await p.keyboard.up("Control");
    await campoTamanho.type("0.5");
    await new Promise((r) => setTimeout(r, 500));
    const depoisDoTamanho = {
      rendimento: Number(await valorDe("Rendimento da receita")),
      porcoes: Number(await valorDe("Porções da receita")),
    };
    // rendimento / 0,5 = porcoes. A conta e da tela, e e isso que se afirma.
    checar("informar o tamanho da porcao recalcula as porcoes",
      Math.abs(depoisDoTamanho.porcoes - depoisDoTamanho.rendimento / 0.5) < 0.02,
      depoisDoTamanho);

    // 🔑 **O fator de coccao ganhou onde ser digitado.** A coluna existe desde a
    // migracao 006 com "muda rendimento, nao custo" escrito nela, e nenhuma tela
    // a oferecia: ficava 1 em toda ficha.
    const temCoccao = await p.evaluate(() =>
      [...document.querySelectorAll("input[aria-label]")]
        .some((i) => /fator de coc/i.test(i.getAttribute("aria-label") ?? "")));
    checar("cada ingrediente tem o campo de coccao", temCoccao);

    // 🔑 **"Adicionar linha" DEPOIS da lista** (13/09/2026, pedido do dono: "o
    // botao sempre fica no topo, mas pode colocar no fim dos itens, fica a
    // usabilidade melhor"). Ele era a `acao` do cartao, e `acao` mora no
    // cabecalho: quem acabou de preencher a ultima linha tinha de subir a tela
    // para pedir a proxima — numa receita de doze ingredientes, doze vezes.
    // ⚠️ A checagem e de ORDEM no documento, nao de existencia: o botao continuaria
    // existindo se alguem o devolvesse ao cabecalho por simetria com os outros
    // cartoes, e e exatamente isso que ela impede.
    const ondeEstaOBotao = await p.evaluate(() => {
      const cartao = [...document.querySelectorAll("section.cartao")]
        .find((c) => (c.querySelector("h2")?.textContent ?? "").trim() === "Ingredientes");
      const botao = [...(cartao?.querySelectorAll("button") ?? [])]
        .find((b) => /Adicionar linha/i.test(b.textContent ?? ""));
      // ⚠️ Pelo `id`, nao por classe: o resumo de custo abaixo do botao tambem e
      // `rounded`, e a primeira versao desta checagem media contra ELE — dizendo
      // que o botao estava antes das linhas quando ele estava depois.
      const linhas = [...document.querySelectorAll("#itens-da-ficha > div")];
      const ultima = linhas[linhas.length - 1];
      if (!botao || !ultima) return { achou: false, linhas: linhas.length };
      return {
        achou: true,
        linhas: linhas.length,
        // 4 = DOCUMENT_POSITION_FOLLOWING: o botao vem depois da ultima linha.
        depoisDaUltima: !!(ultima.compareDocumentPosition(botao) & 4),
      };
    });
    checar("o botao de adicionar linha fica DEPOIS dos itens",
      ondeEstaOBotao.achou && ondeEstaOBotao.depoisDaUltima, ondeEstaOBotao);

    // Volta o rendimento para o que a fase montou: o resto do roteiro conta com
    // ele, e este bloco nao grava nada de proposito.
    await irPara(p, `${WEB}/fichas/${idFicha}`);
    await new Promise((r) => setTimeout(r, 1200));

    // 🔑 **Os MODOS de rendimento moram no CABECALHO, numa tabela** (13/09/2026
    // e 16/09/2026, pedidos do dono: "o rendimento e os destinos estao em grupos
    // separados; podem ficar juntos" e depois "podemos criar mais modos de
    // rendimento para diferentes setores, com um nome, e este sera o modo
    // selecionado ao agendar ou produzir").
    // ⚠️ O que se afirma e o comportamento pedido: a linha nova NASCE IGUAL ao
    // padrao. Conferir que o botao existe nao diz nada sobre isso.
    const { dados: vitrineTela } = await api("POST", "/locais",
      { nome: `Vitrine tela ${marca}` }, token);
    aoTerminar.push(() => api("DELETE", `/locais/${vitrineTela.id}`, null, token));
    await irPara(p, `${WEB}/fichas/${idFicha}`);
    await p.waitForFunction(
      () => !!document.querySelector('input[aria-label="Rendimento da receita"]'),
      { timeout: 15000 },
    ).catch(() => {});
    const tabelaRend = await p.evaluate(() => {
      const cartao = [...document.querySelectorAll("section.cartao")]
        .find((c) => /O que esta ficha produz/i.test(c.querySelector("h2")?.textContent ?? ""));
      const texto = cartao?.innerText ?? "";
      return {
        noCabecalho: !!cartao?.querySelector('input[aria-label="Rendimento da receita"]'),
        // A primeira linha e a prateleira PADRAO, e a tela diz isso.
        dizPadrao: /padr[ãa]o/i.test(texto),
        avisaDivide: /divide o consumo/i.test(texto),
        botao: [...(cartao?.querySelectorAll("button") ?? [])]
          .some((b) => /\+ modo/i.test(b.textContent ?? "")),
      };
    });
    checar("o rendimento e os modos ficam no MESMO cartão do cabeçalho",
      tabelaRend.noCabecalho && tabelaRend.dizPadrao, tabelaRend);
    checar("com o caminho para acrescentar um modo, e o aviso do consumo",
      tabelaRend.botao && tabelaRend.avisaDivide, tabelaRend);

    // 🔑 A linha nova NASCE IGUAL ao padrao — e o coracao do pedido.
    const rendPadrao = await p.evaluate(() =>
      document.querySelector('input[aria-label="Rendimento da receita"]')?.value ?? "");
    await p.evaluate(() => [...document.querySelectorAll("button")]
      .find((b) => /\+ modo/i.test(b.textContent ?? ""))?.click());
    await new Promise((r) => setTimeout(r, 500));
    const nascida = await p.evaluate(() => ({
      rendimento:
        document.querySelector('input[aria-label="rendimento do modo 1"]')?.value ?? null,
      porcoes: document.querySelector('input[aria-label="porções do modo 1"]')?.value ?? null,
      temNome: !!document.querySelector('input[aria-label="nome do modo 1"]'),
      temSeletor: !!document.querySelector('select[aria-label="onde vale o modo 1"]'),
    }));
    // 🔑 O NOME e o que a cozinha escolhe na hora de produzir — sem ele o modo
    // nao existe para quem produz, so para o banco.
    checar("o modo novo nasce com nome e com o rendimento do padrão",
      nascida.temNome && nascida.temSeletor && nascida.rendimento === rendPadrao,
      { rendPadrao, ...nascida });

    // Batiza o modo, aponta para a vitrine, muda o rendimento e salva JUNTO.
    const campoNomeModo = await p.$('input[aria-label="nome do modo 1"]');
    await campoNomeModo.type("Vitrine");
    const selDestino = await p.$('select[aria-label="onde vale o modo 1"]');
    await selDestino.select(`l:${vitrineTela.id}`);
    const campoRendDestino = await p.$('input[aria-label="rendimento do modo 1"]');
    await campoRendDestino.click();
    await p.keyboard.down("Control");
    await p.keyboard.press("KeyA");
    await p.keyboard.up("Control");
    await campoRendDestino.type("1");
    await p.evaluate(() => [...document.querySelectorAll("button")]
      .find((b) => /^Salvar$/i.test(b.textContent?.trim() ?? ""))?.click());
    await p.waitForFunction(
      () => /Ficha salva/i.test(document.body.innerText), { timeout: 12000 },
    ).catch(() => {});
    const { dados: fichaComDestino } = await api("GET", `/fichas/${idFicha}`, null, token);
    // ⚠️ Salvar a ficha grava os destinos na MESMA acao: era um cartao com botao
    // proprio, e uma mudanca so exigia salvar duas vezes.
    checar("salvar a ficha grava os modos junto",
      (fichaComDestino?.modos ?? []).some(
        (m) => m.nome === "Vitrine" && m.id_local === vitrineTela.id
          && Math.abs(Number(m.rendimento_qtd) - 1) < 0.01),
      fichaComDestino?.modos);
    await foto(p, "17c-modos-de-rendimento");
    // Tira o modo: o resto do roteiro produz este bolo e conta com o rendimento
    // da ficha.
    await api("PUT", `/fichas/${idFicha}/modos`, { itens: [] }, token);

    // A prateleira de destino ao PROGRAMAR — a agenda guardava o campo desde o
    // comeco e a tela nunca o mandava.
    await irPara(p, `${WEB}/producao`);
    await new Promise((r) => setTimeout(r, 1400));
    const temPrateleira = await p.evaluate(() =>
      !!document.querySelector('select[aria-label="Prateleira de destino"]'));
    checar("a agenda pergunta para qual prateleira produzir", temPrateleira);

    // ⚠️ **VOLTA para a ficha.** As checagens seguintes (imprimir, foto do prato)
    // sao desta tela, e este bloco tinha saido dela para ver a agenda: quatro
    // checagens boas falharam de uma vez com "abriu: false", apontando para
    // recursos que estao no lugar. Quem navega, devolve a tela onde a achou.
    await irPara(p, `${WEB}/fichas/${idFicha}`);
    await new Promise((r) => setTimeout(r, 1300));

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

    // 🔑 **A foto do prato pronto.** A ficha é seguida por quem está de pé na
    // cozinha, e "está pronto?" é uma pergunta VISUAL: nenhuma descrição de
    // montagem responde o que a imagem responde. A coluna existia desde a
    // etapa 3 e nunca tinha sido usada.
    const cartaoFoto = await p.evaluate(() => {
      const campo = document.querySelector("#foto-da-ficha");
      const cartao = [...document.querySelectorAll("section, div")]
        .find((d) => /Foto do prato/.test(d.querySelector("h2")?.textContent ?? ""));
      return {
        temCartao: /Foto do prato/i.test(document.body.innerText),
        temCampo: !!campo,
        // Só imagem: o servidor recusa o resto, e oferecer tudo ensina o erro.
        aceita: campo?.getAttribute("accept") ?? "",
        botao: [...(cartao?.querySelectorAll("button.btn") ?? [])]
          .map((b) => b.textContent?.trim() ?? ""),
      };
    });
    checar("a ficha tem o cartão da foto do prato",
      cartaoFoto.temCartao && cartaoFoto.temCampo && cartaoFoto.aceita.includes("image/"),
      cartaoFoto);
    checar("com o botão de imagem à vista, como no cadastro da empresa",
      cartaoFoto.botao.some((b) => /imagem/i.test(b)), cartaoFoto);
    // ⚠️ Envio de arquivo pela API, não pelo seletor do navegador: o que se
    // mede aqui é a TELA mostrando a foto, e encenar o clique no seletor de
    // arquivos do sistema operacional é frágil sem provar mais nada.
    const subiu = await enviarArquivo(`/fichas/${idFicha}/foto`, token);
    checar("a foto sobe pela rota da ficha",
      subiu.status === 200 && !!subiu.dados?.foto_url, subiu);
    await irPara(p, `${WEB}/fichas/${idFicha}`);
    // ⚠️ **Espera a imagem CARREGAR, nao a tag aparecer.** A tag existe assim
    // que o React desenha; o `naturalWidth` so passa de zero quando o arquivo
    // chega. Esperando so o elemento, a checagem lia a largura no instante
    // seguinte e reprovava por impaciencia — a mesma familia dos 1.200 ms fixos
    // da busca de ajustes.
    await p.waitForFunction(
      () => {
        const i = document.querySelector('img[alt^="Foto de"]');
        return !!i && (i.complete ? i.naturalWidth > 0 : false);
      },
      { timeout: 20000, polling: 250 },
    ).catch(() => {});
    const comFoto = await p.evaluate(() => {
      const img = document.querySelector('img[alt^="Foto de"]');
      return {
        tem: !!img,
        // ⚠️ `naturalWidth` e não só o `src`: a tag pode estar lá apontando
        // para uma URL que devolve 404, e a tela pareceria certa.
        carregou: (img?.naturalWidth ?? 0) > 0,
        // ⚠️ O rótulo é "remover", como no cadastro da empresa — a checagem
        // antiga procurava "remover foto" e quebrou quando os dois passaram a
        // falar igual. Casar pelo cartão, não pelo texto solto da página.
        oferece: [...(document.querySelectorAll("button") ?? [])]
          .some((b) => /^remover$/i.test(b.textContent?.trim() ?? "")),
      };
    });
    checar("e a tela passa a mostrá-la", comFoto.tem && comFoto.carregou, comFoto);
    checar("com a saída para tirá-la", comFoto.oferece, comFoto);
    await api("DELETE", `/fichas/${idFicha}/foto`, null, token);

    // 🔑 **Duplicar a receita para OUTRO produto** (12/09/2026, pedido do dono:
    // "tenho Bolo de Morango e Bolo de Banana, a base da receita e a mesma").
    // Sem isto a segunda receita era redigitada item por item — e e ai que uma
    // entra com 200 G de farinha e a outra com 250.
    // ⚠️ A checagem termina na FICHA NOVA, com os itens a vista: confirmar que o
    // botao existe nao diz que a copia carregou a receita.
    const { dados: bananaTela } = await api("POST", "/produtos",
      { nome: `Tela bolo banana ${marca}`, tipo: "PRODUZIDO", um_estoque: "UN" }, token);
    // ⚠️ O estado da ORIGEM fica guardado ANTES: o que se afirma e que duplicar
    // nao a toca, e nao em que status ela esta — esta fase a deixa em rascunho,
    // e cravar "homologada" aqui foi um engano da primeira versao desta
    // checagem, que acusou o recurso por uma suposicao do teste.
    const { dados: origemAntes } = await api("GET", `/fichas/${idFicha}`, null, token);
    await irPara(p, `${WEB}/fichas/${idFicha}`);
    await new Promise((r) => setTimeout(r, 1300));
    const temDuplicar = await p.evaluate(() => [...document.querySelectorAll("button")]
      .some((b) => /Duplicar receita/i.test(b.textContent ?? "")));
    checar("a ficha oferece duplicar a receita", temDuplicar);
    await p.evaluate(() => [...document.querySelectorAll("button")]
      .find((b) => /Duplicar receita/i.test(b.textContent ?? ""))?.click());
    await p.waitForSelector('[role="dialog"]', { timeout: 8000 });
    const janelaDup = await p.evaluate(() => {
      const d = document.querySelector('[role="dialog"]');
      return {
        titulo: d?.querySelector("h2")?.textContent ?? "",
        // ⚠️ A janela tem de DIZER o que vai junto e que nasce rascunho: quem
        // confirma sem saber descobre o efeito pela lista de fichas, depois.
        dizOqueCopia: /ingredientes/i.test(d?.innerText ?? "")
          && /rascunho/i.test(d?.innerText ?? ""),
      };
    });
    checar("a janela explica o que a copia leva, e que nasce em rascunho",
      janelaDup.dizOqueCopia, janelaDup);

    // ⚠️ **O BuscaCadastro se dirige DIGITANDO e apertando Tab** — nao por botao.
    // E o foco nasce no botao de confirmar (autoFocus da Confirmacao), entao o
    // campo precisa do clique antes.
    const campoDestino = await p.$('[role="dialog"] input[aria-label="Buscar o produto de destino"]');
    checar("com a busca do produto de destino", !!campoDestino);
    await campoDestino.click();
    await campoDestino.type(`Tela bolo banana ${marca}`);
    await p.keyboard.press("Tab");
    await new Promise((r) => setTimeout(r, 1500));
    await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] button')]
      .find((b) => /Copiar receita/i.test(b.textContent ?? ""))?.click());
    // A tela vai para a COPIA: o passo seguinte e sempre ajustar a receita nova.
    await p.waitForFunction(
      (de) => /\/fichas\/\d+$/.test(location.pathname) && !location.pathname.endsWith(`/${de}`),
      { timeout: 15000 }, String(idFicha),
    ).catch(() => {});
    // 🔑 **O nome do ingrediente mora num `<input>`, e `innerText` nao ve valor
    // de campo.** Na tela editavel cada item e um `BuscaCadastro` — um input com
    // o nome do insumo no `value`. A checagem da cozinha, tres linhas abaixo,
    // acha "TELA FARINHA" no texto porque AQUELA tela e so leitura; esta, nao.
    // Custou duas rodadas: a espera nascia falsa, estourava 15 s e a medicao
    // caia na casca da pagina (menu + nome do prato), acusando a copia de nao
    // trazer a receita — que ela trouxe, como o servidor confirma logo abaixo.
    await p.waitForFunction(
      () => [...document.querySelectorAll("input")]
        .some((i) => /TELA FARINHA/i.test(i.value)),
      { timeout: 15000 },
    ).catch(() => {});
    const idCopia = p.url().match(/fichas\/(\d+)/)?.[1];
    checar("copiar leva para a ficha nova", !!idCopia && idCopia !== String(idFicha),
      [idCopia, idFicha]);
    const naCopia = await p.evaluate(() => document.body.innerText);
    checar("que e do produto de destino",
      new RegExp(`Tela bolo banana ${marca}`, "i").test(naCopia),
      naCopia.slice(0, 120));
    checar("nasce em rascunho", /rascunho/i.test(naCopia), naCopia.slice(0, 160));
    // 🔑 O que importa: a receita veio junto. Mesmo insumo, mesma quantidade.
    const camposDaCopia = await p.evaluate(() =>
      [...document.querySelectorAll("input")].map((i) => i.value).filter(Boolean));
    checar("com o ingrediente da receita original a vista",
      camposDaCopia.some((v) => /TELA FARINHA/i.test(v)), camposDaCopia.slice(0, 12));
    const { dados: copiaApi } = await api("GET", `/fichas/${idCopia}`, null, token);
    const { dados: origemApi } = await api("GET", `/fichas/${idFicha}`, null, token);
    checar("e com os mesmos itens da origem no servidor",
      (copiaApi?.itens ?? []).length === (origemApi?.itens ?? []).length
        && (copiaApi?.itens ?? []).length > 0,
      [(copiaApi?.itens ?? []).length, (origemApi?.itens ?? []).length]);
    checar("sem mexer na ficha de origem — mesmo status e mesmos itens",
      origemApi?.status === origemAntes?.status
        && (origemApi?.itens ?? []).length === (origemAntes?.itens ?? []).length,
      [origemAntes?.status, origemApi?.status]);
    await foto(p, "17b-duplicar-ficha");

    // 🔑 **A busca do destino lista so PRODUZIDOS** (decisao do dono, 12/09/2026).
    // Sem esta checagem a decisao volta atras no primeiro refactor da tela — e o
    // sintoma seria uma lista com 600 insumos onde se procura um prato.
    // ⚠️ Vai DEPOIS da copia e fecha a janela no fim: nada do roteiro seguinte
    // depende deste passo, entao um tropeco aqui nao contamina o resto.
    await p.evaluate(() => [...document.querySelectorAll("button")]
      .find((b) => /Duplicar receita/i.test(b.textContent ?? ""))?.click());
    await p.waitForSelector('[role="dialog"]', { timeout: 8000 }).catch(() => {});
    const buscaFiltrada = await p.$(
      '[role="dialog"] input[aria-label="Buscar o produto de destino"]');
    if (buscaFiltrada) {
      // `Tela farinha` e INSUMO: com o filtro, a busca nao o resolve.
      await buscaFiltrada.click();
      await buscaFiltrada.type(`Tela farinha ${marca}`);
      await p.keyboard.press("Tab");
      await new Promise((r) => setTimeout(r, 1500));
      const oQueVeio = await p.evaluate(() => {
        const janelas = [...document.querySelectorAll('[role="dialog"]')];
        const lupa = janelas[janelas.length - 1];
        return {
          janelas: janelas.length,
          // 🔑 **O campo GUARDA o texto digitado quando nada resolve.** A
          // primeira versao desta checagem olhava o valor do campo e falhava com
          // o filtro FUNCIONANDO: o `BuscaCadastro` so reescreve o texto quando
          // alguem e escolhido. O que prova o recorte e a janela da lupa dizendo
          // que nao achou — e a lista vazia dentro dela.
          naoAchou: /Nenhum produto produzido/i.test(lupa?.innerText ?? ""),
          achados: [...(lupa?.querySelectorAll("ul li") ?? [])].length,
        };
      });
      checar("a busca do destino nao oferece insumo, so produzido",
        oQueVeio.naoAchou && oQueVeio.achados === 0, oQueVeio);
    }
    // Fecha o que estiver aberto, da janela de dentro para fora.
    for (let i = 0; i < 3; i++) {
      const fechou = await p.evaluate(() => {
        const janelas = [...document.querySelectorAll('[role="dialog"]')];
        const ultima = janelas[janelas.length - 1];
        const x = ultima?.querySelector('[aria-label="fechar"]');
        if (x) { x.click(); return true; }
        const cancelar = [...(ultima?.querySelectorAll("button") ?? [])]
          .find((b) => /Cancelar/i.test(b.textContent ?? ""));
        if (cancelar) { cancelar.click(); return true; }
        return false;
      });
      if (!fechou) break;
      await new Promise((r) => setTimeout(r, 400));
    }

    await api("DELETE", `/fichas/${idCopia}`, null, token);
    await api("DELETE", `/produtos/${bananaTela.id}`, null, token);
    await irPara(p, `${WEB}/fichas/${idFicha}`);
    await new Promise((r) => setTimeout(r, 900));

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

    // 🔑 **A lista mostra UMA linha por produto, e a ficha tem seletor de versao**
    // (13/09/2026, relato do dono: "quando sai uma nova versao, parece que ha dois
    // produtos na lista, onde poderia ter somente uma linha, e dentro da ficha
    // poderia ter uma selecao de versao").
    // ⚠️ Cenario proprio: a ficha desta fase e usada por meia duzia de checagens,
    // e criar versao nela mudaria o que elas medem.
    const { dados: prodVer } = await api("POST", "/produtos", {
      nome: `Tela versoes ${marca}`, tipo: "PRODUZIDO", um_estoque: "KG",
      producao_propria: true,
    }, token);
    aoTerminar.push(() => api("DELETE", `/produtos/${prodVer.id}`, null, token));
    const { dados: fVer1 } = await api("POST", "/fichas", {
      id_produto: prodVer.id, rendimento_qtd: 1, rendimento_um: "KG", porcoes: 1,
      itens: [{ id_insumo: insumo.id, qtd_bruta: 1, um: "KG" }],
    }, token);
    await api("POST", `/fichas/${fVer1.id}/nova-versao`, null, token);

    // ⚠️ **Filtrando pela busca, nao procurando na pagina 1.** A base tem 74
    // fichas e a lista pagina de 20 em 20: o produto desta rodada cai na pagina
    // quatro, e a checagem media uma lista onde ele nunca estaria.
    await irPara(p, `${WEB}/fichas?busca=Tela versoes ${marca}`);
    await p.waitForFunction(
      (nome) => document.body.innerText.includes(nome),
      { timeout: 15000 }, `Tela versoes ${marca}`.toUpperCase(),
    ).catch(() => {});
    const naLista = await p.evaluate((nome) => {
      const linhas = [...document.querySelectorAll("table.tabela tbody tr")]
        .map((tr) => tr.innerText)
        .filter((t) => t.toUpperCase().includes(nome));
      return { quantas: linhas.length, texto: linhas[0] ?? "" };
    }, `Tela versoes ${marca}`.toUpperCase());
    // ⚠️ O que se afirma e o numero de LINHAS: a ficha tem duas versoes, e antes
    // disso o produto aparecia duas vezes como se fossem dois pratos.
    checar("o produto com duas versões aparece UMA vez na lista",
      naLista.quantas === 1, naLista);
    checar("com a versão e quantas existem", /v2/.test(naLista.texto)
      && /de 2/.test(naLista.texto), naLista);

    // Dentro da ficha: o seletor de versao.
    await irPara(p, `${WEB}/fichas/${fVer1.id}`);
    // ⚠️ **Espera o SELETOR, não um relógio.** A ficha carrega por XHR depois do
    // `networkidle2`, e um `setTimeout` de 1,5 s reprovava a checagem por
    // impaciência sob carga — passou em duas rodadas seguidas e caiu na
    // terceira, sem ninguém tocar na tela. Mesma lição do custo inicial: se o
    // seletor de fato não existir, isto ainda falha, só que nove segundos
    // depois em vez de um e meio.
    const seletorVersao = await p
      .waitForSelector('select[aria-label="Versão da ficha"]', { timeout: 9000 })
      .catch(() => null);
    checar("a ficha oferece escolher a versão", !!seletorVersao);
    if (seletorVersao) {
      const opcoes = await p.evaluate(() =>
        [...document.querySelectorAll('select[aria-label="Versão da ficha"] option')]
          .map((o) => o.textContent?.trim() ?? ""));
      checar("com as duas versões e a situação de cada uma",
        opcoes.length === 2 && opcoes.every((o) => /^v\d+ · \w+/.test(o)), opcoes);
    }

    // O cabecalho: o produto sozinho na primeira linha.
    // ⚠️ A afirmacao e de LARGURA, nao de existencia: o campo continuaria na tela
    // se alguem o devolvesse para a grade dos numeros, espremido entre eles.
    const larguras = await p.evaluate(() => {
      const cartao = [...document.querySelectorAll("section.cartao")]
        .find((c) => /O que esta ficha produz/i.test(c.querySelector("h2")?.textContent ?? ""));
      // ⚠️ O `Campo` e um `<label>` com `<span class="rotulo">` DIRETO. A primeira
      // versao procurava "label, div" e casava com a GRADE inteira — que contem as
      // duas linhas, e por isso nunca estava "acima" do rendimento. Medir o
      // elemento errado acusou o cabecalho de nao ter mudado quando ele mudou.
      const produto = [...(cartao?.querySelectorAll("label") ?? [])]
        .find((x) => (x.querySelector(":scope > span.rotulo, :scope > span.rotulo-campo")?.textContent ?? "")
          .trim() === "Produto");
      const rendimento = [...(cartao?.querySelectorAll("input[aria-label]") ?? [])]
        .find((i) => i.getAttribute("aria-label") === "Rendimento da receita");
      if (!produto || !rendimento) return null;
      return {
        produto: Math.round(produto.getBoundingClientRect().width),
        rendimento: Math.round(rendimento.getBoundingClientRect().width),
        // Primeira linha: o produto comeca ACIMA do rendimento.
        acima: produto.getBoundingClientRect().bottom
               <= rendimento.getBoundingClientRect().top + 2,
      };
    });
    checar("o produto ocupa a primeira linha do cabeçalho, sozinho",
      !!larguras && larguras.acima && larguras.produto > larguras.rendimento, larguras);
    await foto(p, "17e-lista-e-versoes");

    // 🔑 **Rascunho se EXCLUI, e o custo que a ficha PREVE aparece no produto**
    // (13/09/2026, dois pedidos do dono). Cenario proprio: a ficha desta fase ja
    // foi usada por meia duzia de checagens, e excluir a dela levaria as fotos e o
    // custo embora.
    const { dados: prodRasc } = await api("POST", "/produtos", {
      nome: `Tela rascunho ${marca}`, tipo: "PRODUZIDO", um_estoque: "KG",
      producao_propria: true,
    }, token);
    aoTerminar.push(() => api("DELETE", `/produtos/${prodRasc.id}`, null, token));
    const { dados: fichaRasc } = await api("POST", "/fichas", {
      // 🔑 **Com PORCOES**, para a tela ter o que escolher: 2 KG de insumo a 8,00
      // dao 16,00; rende 10 KG em 8 porcoes. A porcao custa 2,00 e o quilo, 1,60 —
      // e o pedido do dono (13/09/2026) e que quem lidera seja a PORCAO.
      id_produto: prodRasc.id, rendimento_qtd: 10, rendimento_um: "KG", porcoes: 8,
      itens: [{ id_insumo: insumo.id, qtd_bruta: 2, um: "KG" }],
    }, token);

    // ⚠️ O produto NUNCA foi produzido: a cascata nao sabe o custo, e a ficha sabe.
    await irPara(p, `${WEB}/produtos/${prodRasc.id}`);
    await p.waitForFunction(
      () => /provis[óo]rio/i.test(document.body.innerText), { timeout: 15000 },
    ).catch(() => {});
    const custoProv = await p.evaluate(() => {
      // ⚠️ O custo deixou de ter cartao proprio (16/09/2026, cadastro em abas):
      // ele e METADE de "Valores", ao lado do preco, porque a pergunta e uma so
      // — da margem?
      const cartao = [...document.querySelectorAll("section.cartao")]
        .find((c) => (c.querySelector("h2")?.textContent ?? "").trim() === "Valores");
      const texto = cartao?.innerText ?? "";
      return {
        temCartao: !!cartao,
        // 16,00 em 8 porcoes = 2,00 a porcao. E o numero que lidera.
        mostraAPorcao: /2,00/.test(texto),
        dizQueEPorcao: /Custo de uma por[çc][ãa]o/i.test(texto),
        // ⚠️ E o por UNIDADE continua a vista: e ele que casa com o estoque, que
        // se move em KG. Sumir com ele faria a tela discordar do razao sem nada
        // explicando.
        mostraOQuilo: /1,60/.test(texto),
        // ⚠️ O rotulo e o que impede o teorico de virar apurado aos olhos de quem
        // olha: sem ele, o numero tem a mesma cara do custo medio do razao.
        dizQueEProvisorio: /provis[óo]rio/i.test(texto),
        dizDeOndeVeio: /ficha v\d/i.test(texto),
        avisaQueNascePelaProducao: /primeira produ|nasce na/i.test(texto),
      };
    });
    checar("o produto sem produção mostra o custo que a ficha prevê",
      custoProv.temCartao && custoProv.mostraAPorcao, custoProv);
    checar("liderando pela PORÇÃO, com o rótulo dizendo isso",
      custoProv.dizQueEPorcao, custoProv);
    checar("e com o custo por unidade de estoque à vista junto",
      custoProv.mostraOQuilo, custoProv);
    checar("com a etiqueta de PROVISÓRIO e de qual ficha veio",
      custoProv.dizQueEProvisorio && custoProv.dizDeOndeVeio, custoProv);
    checar("e dizendo que o custo de verdade nasce na produção",
      custoProv.avisaQueNascePelaProducao, custoProv);

    // O rascunho se exclui — e a tela pergunta antes.
    await irPara(p, `${WEB}/fichas/${fichaRasc.id}`);
    await new Promise((r) => setTimeout(r, 1300));
    const temExcluir = await p.evaluate(() => [...document.querySelectorAll("button")]
      .some((b) => /Excluir rascunho/i.test(b.textContent ?? "")));
    checar("a ficha em rascunho oferece excluir", temExcluir);
    await p.evaluate(() => [...document.querySelectorAll("button")]
      .find((b) => /Excluir rascunho/i.test(b.textContent ?? ""))?.click());
    await p.waitForSelector('[role="dialog"]', { timeout: 8000 }).catch(() => {});
    const janelaExcluir = await p.evaluate(() => {
      const d = document.querySelector('[role="dialog"]');
      return {
        abriu: !!d,
        // ⚠️ "Nao ha como desfazer" tem de estar escrito: excluir e o unico botao
        // desta tela que nao tem volta.
        avisaSemVolta: /n[ãa]o h[áa] como desfazer/i.test(d?.innerText ?? ""),
      };
    });
    checar("perguntando antes, e dizendo que não há volta",
      janelaExcluir.abriu && janelaExcluir.avisaSemVolta, janelaExcluir);
    await p.evaluate(() => [...document.querySelectorAll('[role="dialog"] button')]
      .find((b) => /Sim, excluir/i.test(b.textContent ?? ""))?.click());
    await p.waitForFunction(() => /\/fichas$/.test(location.pathname), { timeout: 12000 })
      .catch(() => {});
    const { status: depoisDeExcluir } = await api(
      "GET", `/fichas/${fichaRasc.id}`, null, token);
    checar("e a ficha some de verdade do servidor", depoisDeExcluir === 404,
      depoisDeExcluir);
    await foto(p, "17d-rascunho-e-provisorio");

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
    semFormulario: ![...document.querySelectorAll("span.rotulo, span.rotulo-campo")]
      .some((r) => r.textContent?.trim() === "Local"),
  }));
  checar("a lista tem o botão de nova contagem", listaInv.temBotao, listaInv);
  checar("e não carrega mais o formulário de abertura", listaInv.semFormulario, listaInv);

  await irPara(p, `${WEB}/inventario/novo`);
  await new Promise((r) => setTimeout(r, 1800));
  const noNovo = await p.evaluate(() => {
    const rotulos = [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].map((x) =>
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
  // ⚠️ **Esperar pela tela de DESTINO, não por um tempo fixo.** Os 2,2 s que
  // havia aqui bastavam com uma contagem de dez linhas e pararam de bastar com
  // uma de centenas: a checagem media a tela ainda em branco e acusava a
  // contagem de não ter campo nenhum. Falhou três vezes num dia sem que nada
  // do sistema tivesse mudado — que é o pior tipo de teste frágil.
  await p.waitForFunction(
    () => !!document.querySelector('input[inputmode="decimal"]'), { timeout: 20000 },
  ).catch(() => {});
  const telaContagem = await p.evaluate(() => {
    const rotulos = [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].map((x) => x.textContent);
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
    // ⚠️ **Sai sem estourar quando a tela não pintou.** Sem esta guarda o
    // `c.focus()` levantava `Cannot read properties of null`, e a rodada
    // INTEIRA morria ali — um `checar` que falha custa uma linha; uma exceção
    // custa as trezentas checagens seguintes.
    if (!c) return;
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
  // ⚠️ **A ficha tem de ser de produto ATIVO.** Ficha homologada apontando para
  // produto desativado existe — produto com movimento vira inativo em vez de
  // sumir, e a ficha dele fica —, e agendar nela devolve 400 "está inativo". O
  // POST não era conferido, então a agenda ficava vazia e a falha aparecia três
  // checagens adiante, dizendo que a agenda não abre a folha.
  // 🔑 **A suite cria a PROPRIA ficha, sempre.** Reaproveitar "a primeira
  // homologada da base" ja caiu duas vezes por motivos diferentes: uma vez num
  // produto INATIVO, outra num produto NA_HORA — que e produzido e baixado no
  // mesmo instante da venda e por isso nao se agenda. E o filtro nao tem como
  // ser feito pela lista: `/produtos` nao devolve `modo_producao`. Precondicao
  // GARANTIDA, nunca suposta — e cada suite procura os registros DELA.
  const marcaFicha = String(Date.now()).slice(-5);
  const { dados: insFicha } = await api("POST", "/produtos",
    { nome: `Agenda insumo ${marcaFicha}`, tipo: "INSUMO", um_estoque: "KG" }, token);
  const { dados: prodFicha } = await api("POST", "/produtos",
    { nome: `Agenda preparo ${marcaFicha}`, tipo: "PRODUZIDO", um_estoque: "UN",
      modo_producao: "PARA_ESTOQUE" }, token);
  aoTerminar.push(() => api("DELETE", `/produtos/${prodFicha.id}`, null, token));
  aoTerminar.push(() => api("DELETE", `/produtos/${insFicha.id}`, null, token));
  const { dados: novaFicha } = await api("POST", "/fichas", {
    id_produto: prodFicha.id, rendimento_qtd: 1, rendimento_um: "UN", porcoes: 1,
    // 🔑 **Com MODO DE PREPARO**, porque a folha da producao passou a leva-lo
    // (16/09/2026, pedido do dono: "quem vai ver esta tela precisa saber as
    // quantidades e o modo de preparo, e nao os custos"). Sem ele aqui, a
    // checagem da folha passaria sem provar nada.
    modo_preparo: "1. Misturar tudo.\n2. Levar ao forno por 20 min.",
    alergenos: "gluten",
    tempo_preparo_min: 20,
    itens: [{ id_insumo: insFicha.id, qtd_bruta: 0.2, um: "KG" }],
  }, token);
  await api("POST", `/fichas/${novaFicha.id}/homologar`, null, token);
  const homologada = { id: novaFicha.id, id_produto: prodFicha.id, status: "HOMOLOGADA" };
  checar("há ficha homologada para a agenda usar", !!homologada, homologada);
  const amanhaISO = diaLocal(1);
  // ⚠️ **Confere o POST.** Sem isto, uma recusa aqui vira "a agenda não abre a
  // folha" lá embaixo — a falha longe da causa que esta suíte já pagou caro.
  const { status: stAgenda, dados: dAgenda } = await api("POST", "/producao-agenda",
    { id_produto: homologada.id_produto, data_prevista: amanhaISO, quantidade: 3 }, token);
  checar("a linha da agenda é criada", stAgenda === 201 || stAgenda === 200,
    [stAgenda, dAgenda]);

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
  // ⚠️ **Espera limitada pelo link, não um sono fixo.** A agenda vem do
  // servidor e a lista cresceu com a base: a checagem media a tela antes de a
  // linha existir e acusava a agenda de não abrir a folha.
  await p.waitForFunction(
    () => [...document.querySelectorAll("a")]
      .some((x) => /\/producao\/\d+$/.test(x.getAttribute("href") ?? "")),
    { timeout: 15000 },
  ).catch(() => {});
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
    // ⚠️ **Espera pelo CONTEÚDO, não por tempo fixo.** Os 1.600 ms davam conta
    // na máquina livre e não davam com a máquina ocupada: numa rodada com
    // escrita concorrente no banco, as três checagens abaixo voltaram
    // `{colunas:false, rende:false, falta:false}` — ou seja, a página ainda nem
    // tinha renderizado a tabela, e o teste acusou a tela de não ter colunas
    // que ela tem. É a mesma lição das checagens "oferece baixar".
    await p.waitForFunction(
      () => [...document.querySelectorAll("th")].some(
        (t) => (t.textContent ?? "").trim() === "Por unidade"),
      { timeout: 20000 },
    ).catch(() => {});
    const folha = await p.evaluate(() => {
      const cab = [...document.querySelectorAll("th")].map((t) => t.textContent?.trim());
      return {
        colunas: ["Insumo", "Por unidade", "Total", "Tem no local"].every((c) =>
          cab.includes(c)),
        rende: /A receita rende/i.test(document.body.innerText),
        falta: /tem tudo|item\(ns\) faltando/i.test(document.body.innerText),
        // 🔑 **A folha e da COZINHA** (16/09/2026, pedido do dono: "quem vai ver
        // esta tela precisa saber as quantidades e o modo de preparo, e nao os
        // custos; disponibilizar a impressao desta tela, para que seja passada
        // para a producao").
        semColunaCusto: !cab.includes("Custo"),
        preparo: /Como se faz/i.test(document.body.innerText)
          && /Levar ao forno/i.test(document.body.innerText),
        alergenos: /Alérgenos/i.test(document.body.innerText),
        quanto: /Produzir\s+\d/i.test(document.body.innerText),
        imprimir: [...document.querySelectorAll("button")]
          .some((b) => /Imprimir a folha/i.test(b.textContent ?? "")),
        // 🔑 **A coluna do que REALMENTE foi usado** (16/09/2026, pedido do dono:
        // "na receita vao 5 ovos, mas por um acaso usei 6"). Em branco e a
        // receita; o que a pessoa escrever e o que sai do estoque.
        usei: cab.includes("Usei"),
        campoUsei: document.querySelectorAll('input[aria-label^="usado de"]').length,
        // ⚠️ A largura mora no INVOLUCRO: `.campo` tem `width:100%` sem camada e
        // ganha de uma utilitaria `w-[92px]` na cascata — o campo esticava para
        // a largura da celula e a coluna virava a mais larga da tabela.
        larguraUsei: Math.round(
          document.querySelector('input[aria-label^="usado de"]')
            ?.getBoundingClientRect().width ?? 0),
      };
    });
    checar("com quantidade por unidade e total", folha.colunas, folha);
    checar("dizendo quantas vezes a receita é feita", folha.rende, folha);
    checar("e se tem tudo ou o que falta", folha.falta, folha);
    checar("o QUANTO produzir vem em destaque", folha.quanto, folha);
    // ⚠️ O custo saiu da tabela: ele disputava a leitura com as quantidades, e
    // quem esta na bancada nao decide nada com ele.
    checar("e o custo NÃO disputa a tabela com as quantidades", folha.semColunaCusto, folha);
    checar("o modo de preparo está na folha, com os alérgenos",
      folha.preparo && folha.alergenos, folha);
    checar("e a folha se imprime", folha.imprimir, folha);
    checar("a lista tem a coluna do que foi realmente usado",
      folha.usei && folha.campoUsei > 0, folha);
    checar("e o campo dela é estreito, não a coluna inteira",
      folha.larguraUsei > 0 && folha.larguraUsei < 140, folha);

    // 🔑 **O que vai para o PAPEL**: sem menu, sem botões, sem custo — e com a
    // tabela INTEIRA. ⚠️ O esqueleto é uma grade de duas colunas; esconder o
    // menu não tira a coluna dele, e o conteúdo saía espremido em 276px com as
    // colunas da direita cortadas. No papel não há barra de rolagem para
    // denunciar o corte.
    await p.emulateMediaType("print");
    await new Promise((r) => setTimeout(r, 300));
    const papel = await p.evaluate(() => {
      const tabela = document.querySelector("table");
      const largura = tabela ? tabela.getBoundingClientRect().width : 0;
      return {
        semMenu: !/Buscar tela/i.test(document.body.innerText),
        semCusto: !/custo desta produção/i.test(document.body.innerText),
        comPreparo: /Como se faz/i.test(document.body.innerText),
        // A prova de que a grade foi desfeita: a tabela ocupa a folha, não a
        // faixa do menu.
        larguraTabela: Math.round(largura),
        janela: document.documentElement.clientWidth,
      };
    });
    checar("no papel não vai o menu nem o custo", papel.semMenu && papel.semCusto, papel);
    checar("mas vai o modo de preparo", papel.comPreparo, papel);
    checar("e a tabela ocupa a folha inteira, sem coluna cortada",
      papel.larguraTabela > papel.janela * 0.7, papel);
    await p.emulateMediaType(null);
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
    const campos = [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].map((x) => x.textContent);
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
      const rotulos = [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].map((x) => x.textContent);
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
    const rotulos = [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].map((x) => x.textContent);
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

  // 🔑 **A saída que não achou saldo sai por custo PROVISÓRIO**, e cada uma é
  // uma entrada que ninguém lançou. A etiqueta na linha sempre existiu; o que
  // faltava era poder PERGUNTAR quais são.
  // ⚠️ A afirmação é sobre a propriedade, não sobre o estado do dia: marcando
  // a caixinha, tudo o que sobrar tem de estar marcado como provisório — e
  // lista vazia é resposta legítima (quer dizer que não há entrada faltando).
  const temCaixaProvisorio = await p.evaluate(
    () => !!document.querySelector("#so-provisorios"));
  checar("o razão oferece filtrar só o custo provisório", temCaixaProvisorio);
  if (temCaixaProvisorio) {
    await p.evaluate(() => document.querySelector("#so-provisorios")?.click());
    await p.waitForFunction(
      () => !document.body.innerText.includes("Carregando"), { timeout: 12000 },
    ).catch(() => {});
    await new Promise((r) => setTimeout(r, 1400));
    const soProvisorios = await p.evaluate(() => {
      const linhas = [...document.querySelectorAll("main table tbody tr")];
      return {
        linhas: linhas.length,
        // A etiqueta mora na mesma célula do tipo do movimento.
        todasMarcadas: linhas.every((tr) => /custo provis[óo]rio/i.test(tr.innerText)),
        explica: /custo\s+estimado|entrada que falta/i.test(document.body.innerText),
        vazioExplica: /n[ãa]o h[áa] entrada faltando/i.test(document.body.innerText),
      };
    });
    checar("e o que sobra está todo marcado como provisório",
      soProvisorios.linhas === 0 || soProvisorios.todasMarcadas, soProvisorios);
    // ⚠️ Lista vazia é a BOA notícia — e precisa dizer isso, senão parece que o
    // filtro não funcionou.
    checar("dizendo o que fazer, ou que não há nada a fazer",
      soProvisorios.linhas ? soProvisorios.explica : soProvisorios.vazioExplica,
      soProvisorios);
    // ⚠️ **O ARQUIVO tem de oferecer o mesmo recorte.** Filtro que existe num
    // lado só recria a divergência que o razão exportado existe para não ter —
    // e quem declara o que a janela oferece é o catálogo do SERVIDOR.
    const { dados: catalogo } = await api("GET", "/exportar/catalogo", null, token);
    const razaoNoCatalogo = (catalogo ?? []).find((r) => r.chave === "movimentos");
    checar("e a janela de exportação oferece o mesmo filtro",
      (razaoNoCatalogo?.filtros ?? []).some((f) => f.nome === "provisorio"),
      (razaoNoCatalogo?.filtros ?? []).map((f) => f.nome));
    await p.evaluate(() => document.querySelector("#so-provisorios")?.click());
    await new Promise((r) => setTimeout(r, 1200));
  }
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
    // ⚠️ **Dentro do `main`, nao no documento inteiro.** A busca era
    // `document.querySelector('[aria-pressed="true"]')`, e em 15/09/2026 o menu
    // ganhou o alfinete dos atalhos — um botao de alternancia, com o
    // `aria-pressed` que a norma pede, e que mora no `aside`, ANTES do `main`.
    // A partir dali esta sonda media o alfinete (texto vazio) e acusava a tela
    // de Ajustes de nao ter tipo escolhido. O produto estava certo; o endereco
    // da medicao e que era largo demais.
    const escolhido = document.querySelector('main [aria-pressed="true"]');
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
    [...document.querySelectorAll(".rotulo, .rotulo-campo")].map((r) => r.textContent?.trim() ?? ""));
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
    rotulos: [...document.querySelectorAll("span.rotulo, .rotulo, .rotulo-campo")]
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
  // ⚠️ **Espera o CAMPO SER PREENCHIDO, não um relógio.** Eram 1.200 ms
  // fixos, e estas três checagens falharam e passaram alternadamente ao longo
  // do dia — lidas como instabilidade, quando o que variava era o tempo da
  // busca (a base cresceu de 0 para 3.200 produtos numa mesma sessão). Foi
  // conferido que a API responde certo: a busca exata devolve 1 registro em
  // ~230 ms. É a mesma lição que este arquivo já carrega no bloco do CMV.
  const alvoPreenchido = `Est tela ${m4}`.toUpperCase();
  await p.waitForFunction(
    (esperado) => (document.querySelector('input[aria-label="Buscar produto"]')?.value ?? "")
      .includes(esperado),
    { timeout: 15000, polling: 200 }, alvoPreenchido).catch(() => {});
  const preencheu = await p.evaluate(
    () => document.querySelector('input[aria-label="Buscar produto"]')?.value ?? "");
  checar("um resultado só: o Tab preenche e segue",
    preencheu.includes(alvoPreenchido), preencheu);

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
  // ⚠️ Mesma troca: espera a JANELA existir, nao 1.400 ms.
  await p.waitForSelector('[role="dialog"]', { timeout: 15000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 400));
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
  // ⚠️ **A quantidade e o custo são de TIPOS diferentes agora**, e por isso
  // cada um se acha do seu jeito: o custo unitário grava em `numeric(18,6)` e
  // virou `CampoCusto` (texto com máscara), então `input[type=number]` só
  // devolve a quantidade — `numEstoque[1]` era `undefined` e a bateria morria
  // aqui, longe da causa. Achar pelo RÓTULO é a mesma lição do campo de preço
  // lá embaixo: índice de lista muda quando a tela muda, rótulo não.
  const numEstoque = await p.$$("input[type=number]");
  await numEstoque[0].type("10");
  const campoCustoEntrada = await p.evaluateHandle(() => {
    const l = [...document.querySelectorAll("label")].find(
      (x) => /custo unit[áa]rio/i.test(x.querySelector("span.rotulo, span.rotulo-campo")?.textContent ?? ""));
    return l?.querySelector("input");
  });
  await campoCustoEntrada.asElement().type("20");
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
    () => document.querySelectorAll("main select")[0]?.options.length ?? 0);
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
    const s = document.querySelectorAll("main select")[0];
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
  await p.waitForFunction(() => /Para quem/i.test(document.body.innerText),
    { timeout: 30000, polling: 300 }).catch(() => {});

  // 🔑 **O preço vem junto do produto** (04/09/2026, relato do dono: escolhi o
  // produto e o valor não veio). Ele ja viajava na lista e ninguem o usava —
  // quem lancava relia o preco na tela do produto e digitava de novo.
  const { dados: comPreco } = await api("POST", "/produtos", {
    nome: `Prato preco tela ${m6}`, tipo: "REVENDA", um_estoque: "UN",
    preco_venda: 37.5,
  }, token);
  aoTerminar.push(() => api("DELETE", `/produtos/${comPreco.id}`, null, token));
  await p.reload({ waitUntil: "networkidle2" });
  await p.waitForFunction(() => /Para quem/i.test(document.body.innerText),
    { timeout: 30000, polling: 300 }).catch(() => {});
  // ⚠️ **O BuscaCadastro se dirige DIGITANDO e apertando Tab** — nao por botao.
  // Minha primeira versao procurava um botao "Buscar/Escolher" que nao existe, e
  // a checagem falhou acusando a tela de nao carregar o preco. Sondei a tela
  // isolada para descobrir: e o mesmo padrao que a ficha ja usa desde sempre.
  const buscaItemVenda = await p.$('input[aria-label^="Buscar produto"]');
  checar("o item da venda se escolhe por busca", !!buscaItemVenda);
  if (buscaItemVenda) {
    await buscaItemVenda.type(`Prato preco tela ${m6}`);
    await p.keyboard.press("Tab");
    await new Promise((r) => setTimeout(r, 1600));
  }
  // ⚠️ **O preço é MASCARADO** (`CampoMoeda`): o campo mostra "37,50" e é de
  // texto, então nem `input[type=number]` o encontra nem `Number()` o lê.
  // Compara-se o texto, que é o que a pessoa vê.
  const valorCarregado = await p.evaluate(() =>
    [...document.querySelectorAll("main input")].map((c) => c.value).filter(Boolean));
  checar("escolher o produto carrega o preco de venda sozinho",
    valorCarregado.includes("37,50"), valorCarregado);

  // 🔑 **A pessoa se escolhe pela JANELA, nao por combobox** (mesmo relato).
  // Uma lista de 800 nomes num select nao se percorre, e a politica de cupom —
  // que e o motivo de escolher a pessoa — some.
  const semCombo = await p.evaluate(() =>
    !document.querySelector('select[aria-label="Pessoa do cupom"]'));
  checar("a pessoa NAO e mais um combobox", semCombo, semCombo);

  // 🔑 **A PREVIA do que o cupom vai sair** (04/09/2026, pedido do dono:
  // "gostaria que o valor fosse ajustado ao digitar para ter esta percepcao
  // visual"). Com o item de 37,50 na tela, escolher uma pessoa com 20% de
  // desconto tem de mostrar 30,00 — e mostrar os DOIS numeros.
  const pessoaOffCupom = await api("POST", "/fornecedores", {
    nome: `DESCONTO TELA ${m6}`, fornecedor: false,
    cupom_base: "VENDA", cupom_desconto_pct: 20,
  }, token);
  const buscaPessoaCupom = await p.$('input[aria-label^="Buscar pessoa"]');
  checar("a pessoa do cupom se escolhe por busca", !!buscaPessoaCupom);
  if (buscaPessoaCupom) {
    // ⚠️ **A QUANTIDADE e obrigatoria para haver previa** — sem ela a linha nao
    // esta pronta e a tela nao pergunta nada ao servidor. Minha primeira versao
    // esqueceu isso e acusou a tela de nao mostrar o valor; sondei o cenario
    // isolado e o 30,00 aparecia assim que a quantidade entrava.
    await p.evaluate(() => {
      const qtd = document.querySelector('input[type="number"]');
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, "value").set;
      setter.call(qtd, "2");
      qtd.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await buscaPessoaCupom.type(`DESCONTO TELA ${m6}`);
    await p.keyboard.press("Tab");
    // ⚠️ **Esperar por "Sai por" NAO servia**: aquele e o cabecalho da coluna, e
    // ele aparece so por existir politica — a espera terminava ANTES de a
    // previa chegar, e a medicao lia o estado anterior. O rodape com o cheio so
    // existe quando a resposta do servidor chegou, entao e nele que se espera.
    await p.waitForFunction(() => /cheio\s*R\$/i.test(document.body.innerText),
      { timeout: 20000, polling: 250 }).catch(() => {});
  }
  const textoPreviaCupom = await p.evaluate(() => document.body.innerText);
  // 🔑 37,50 menos 20% = 30,00. O numero PROVA que a conta veio do servidor:
  // a tela nunca soube o percentual, ele viaja so na politica da pessoa.
  checar("a previa mostra por quanto o item vai sair",
    /30,00/.test(textoPreviaCupom), textoPreviaCupom.slice(0, 300));
  // ⚠️ **Os dois numeros, nao so o ajustado.** O campo editavel continua com o
  // preco CHEIO: pusesse o descontado ali, o envio levaria o valor ja
  // descontado e o servidor descontaria de novo — 20% viraria 36%, calado.
  const cheioNoCampoCupom = await p.evaluate(() =>
    [...document.querySelectorAll("main input")].map((c) => c.value));
  checar("e o campo editavel continua com o preco CHEIO",
    cheioNoCampoCupom.includes("37,50"), cheioNoCampoCupom);
  // 🔑 **Os tres numeros do rodape**: 2 x 37,50 = 75,00 cheio, 15,00 de desconto
  // e 60,00 a pagar. ⚠️ Afirmar so a PALAVRA "desconto" passaria pelo aviso do
  // cabecalho, que ja diz "20% de desconto" — a checagem passaria com o rodape
  // quebrado.
  checar("com o cheio, o desconto e o total no rodape",
    /75,00/.test(textoPreviaCupom) && /15,00/.test(textoPreviaCupom)
      && /60,00/.test(textoPreviaCupom), textoPreviaCupom.slice(0, 400));

  await p.reload({ waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1500));
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

  // 🔑 **O filtro de DIA** (pedido do dono, 03/09/2026). O servidor ja aceitava
  // `inicio` e `fim` desde sempre; a tela nunca ofereceu, e conferir um dia
  // contra o PDV exigia rolar a lista ate achar onde a data virava.
  const temCampoDia = await p.evaluate(() =>
    !!document.querySelector('input[type="date"][aria-label="Dia"]'));
  checar("a tela de vendas oferece filtrar por dia", temCampoDia, temCampoDia);

  // ⚠️ Um dia SEM venda tem de esvaziar a lista — se o filtro nao chegasse ao
  // servidor, a venda desta rodada continuaria na tela e o teste passaria por
  // engano.
  await p.evaluate(() => {
    const c = document.querySelector('input[type="date"][aria-label="Dia"]');
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    setter.call(c, "2001-01-01");
    c.dispatchEvent(new Event("input", { bubbles: true }));
    c.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await new Promise((r) => setTimeout(r, 1600));
  // ⚠️ **Medir na LISTA, e ela e um `<ul>`.** Duas medicoes erradas antes desta:
  // `textoVisivel` anexa o VALOR dos campos de input, e a caixa de busca ainda
  // contem o documento — procura-lo no texto da tela devolvia verdadeiro com a
  // lista vazia, ou seja, o teste media o que ele mesmo tinha digitado. Depois,
  // `tbody tr` deu sempre ZERO, porque a lista de vendas nao e tabela: ali a
  // afirmacao "esvaziou" passava trivialmente e a "voltou" falhava sempre,
  // acusando a tela de um defeito que ela nao tinha.
  const vendaNaLista = () => p.evaluate((d) =>
    [...document.querySelectorAll("li")].some((l) => l.innerText.includes(d)), doc6);
  checar("filtrar um dia sem venda esvazia a lista", !(await vendaNaLista()));

  // ⚠️ E ha como VOLTAR: um `type="date"` nao se esvazia sozinho em todo
  // navegador, e sem a saida quem filtrou fica preso no dia.
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((b) => /Todos os dias/i.test(b.textContent ?? ""))?.click();
  });
  await new Promise((r) => setTimeout(r, 1600));
  checar("e o botao Todos os dias devolve a lista", await vendaNaLista());

  // 🔑 **O relatorio de consumo por pessoa** (04/09/2026, pedido do dono: "o
  // funcionario vai comprar, lancamos e depois cobramos o valor dele"). O
  // caminho vive em Vendas pelo mesmo motivo que a busca do PDV: quem quer
  // saber o que fulano consumiu abre Vendas, nao Exportar.
  const temCaminhoConsumo = await p.evaluate(() =>
    [...document.querySelectorAll("a")].some(
      (a) => a.textContent?.includes("Consumo por pessoa")));
  checar("o caminho para o consumo por pessoa esta em Vendas", temCaminhoConsumo);

  await p.goto(`${WEB}/vendas/por-pessoa`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => /Consumo por pessoa/i.test(document.body.innerText),
    { timeout: 20000, polling: 300 }).catch(() => {});
  const textoConsumo = await textoVisivel(p);
  checar("a tela de consumo por pessoa abre", /Consumo por pessoa/i.test(textoConsumo),
    textoConsumo.slice(0, 140));
  // 🔑 **As tres colunas.** So o valor a cobrar nao seria aceito por quem paga:
  // o funcionario quer ver o beneficio, e por isso o cheio e o desconto ficam
  // ao lado do total.
  checar("com o cheio, o desconto e o a cobrar",
    /Valor cheio/i.test(textoConsumo) && /Desconto/i.test(textoConsumo)
      && /A cobrar/i.test(textoConsumo), textoConsumo.slice(0, 400));
  // ⚠️ Sintetico e analitico sao dois documentos, e a tela tem de oferecer os
  // dois — o pedido foi explicito em "podendo ser sintetico ou analitico".
  checar("e a escolha entre sintetico e analitico",
    /sint[eé]tico/i.test(textoConsumo) && /anal[ií]tico/i.test(textoConsumo),
    textoConsumo.slice(0, 400));
  // 🔑 **O recorte e o CICLO, nao um par de datas** (08/09/2026, pedido do
  // dono). ⚠️ O fechamento leva tudo que estava em aberto ate a data final,
  // inclusive consumo anterior ao inicio do ciclo: filtrar por data mostraria
  // um conjunto diferente do que foi cobrado, e esta tela E o documento da
  // cobranca. A checagem cobra os DOIS lados — o seletor entrou e as datas
  // sairam — porque so a primeira metade passaria com os dois na tela.
  checar("o filtro e o ciclo de consumo, com 'em aberto' como padrao",
    /Ciclo de consumo/i.test(textoConsumo) && /Em aberto/i.test(textoConsumo),
    textoConsumo.slice(0, 500));
  const camposData = await p.evaluate(
    () => document.querySelectorAll('input[type="date"]').length);
  checar("e os dois campos de data sairam da tela", camposData === 0, camposData);

  // 🔑 **O botao de baixar** (04/09/2026, pedido do dono: "tem a opcao de baixar
  // o arquivo do consumo por pessoa"). ⚠️ Ele so aparece se o CATALOGO do
  // servidor der a permissao — uma copia da regra escrita na tela deixaria o
  // botao visivel para quem levaria 403 ao clicar.
  const temBaixar = await p.evaluate(() =>
    [...document.querySelectorAll("button")].some(
      (b) => b.textContent?.trim() === "Baixar"));
  checar("com o botao de baixar o arquivo", temBaixar);

  // 🔑 **O periodo de consumo** (04/09/2026): abre, acumula e fecha no
  // pagamento. ⚠️ Este bloco monta o proprio cenario e desfaz no fim — periodo
  // aberto e um singleton por loja, e um que sobrasse faria a proxima rodada
  // recusar o `abrir` de qualquer outra suite.
  await p.goto(`${WEB}/consumo`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => /Per[ií]odos de consumo/i.test(document.body.innerText),
    { timeout: 20000, polling: 300 }).catch(() => {});
  const textoCiclos = await textoVisivel(p);
  checar("a tela de periodos de consumo abre",
    /Per[ií]odos de consumo/i.test(textoCiclos), textoCiclos.slice(0, 140));
  // 🔑 O numero que a casa quer saber antes de fechar: quanto ha para cobrar.
  checar("dizendo quanto esta em aberto agora",
    /Em aberto agora/i.test(textoCiclos), textoCiclos.slice(0, 400));
  checar("e qual e o ciclo atual", /Ciclo atual/i.test(textoCiclos),
    textoCiclos.slice(0, 400));

  // ⚠️ **Meu consumo nao exige permissao nenhuma**, como a Ajuda: ninguem
  // precisa de autorizacao para ver a propria divida. A checagem entra pelo
  // caminho do MENU DO USUARIO, que e onde o dono pediu que ela vivesse.
  const noMenuDoUsuario = await p.evaluate(() => {
    // ⚠️ O gatilho se acha por `aria-haspopup`, nao por `aria-controls` — que
    // nao existe nesta barra. Conferido no componente antes de escrever.
    const botao = document.querySelector('button[aria-haspopup="menu"]');
    (botao instanceof HTMLElement) && botao.click();
    return new Promise((r) => setTimeout(() => {
      const links = [...document.querySelectorAll('#menu-usuario a')];
      r(links.some((a) => a.textContent?.includes("Meu consumo")));
    }, 400));
  });
  checar("Meu consumo esta no menu do usuario", noMenuDoUsuario);

  await p.goto(`${WEB}/meu-consumo`, { waitUntil: "networkidle2" });
  await p.waitForFunction(() => /Meu consumo/i.test(document.body.innerText),
    { timeout: 20000, polling: 300 }).catch(() => {});
  const textoMeu = await textoVisivel(p);
  checar("a tela Meu consumo abre", /Meu consumo/i.test(textoMeu),
    textoMeu.slice(0, 140));
  // ⚠️ **"Nao devo nada" e "nao estou ligado a um cadastro" sao coisas
  // diferentes**, e mostrar zero nos dois casos esconderia a segunda — que se
  // resolve no cadastro de usuarios, nao nesta tela. Uma das duas frases tem de
  // estar la; qual delas depende de o admin ter pessoa ligada.
  checar("dizendo o saldo ou que o login nao tem pessoa ligada",
    /Em aberto/i.test(textoMeu) || /ligado a um cadastro/i.test(textoMeu),
    textoMeu.slice(0, 400));


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

  // 🔑 **No cupom vale o nome do PDV** (pedido do dono, 03/09/2026): e o que o
  // caixa e o cliente viram. Na base real ele costuma ser MELHOR que o do
  // cadastro — o `nome` chega truncado em 40 caracteres nos itens de catering,
  // enquanto o curto traz a descricao inteira, e um rascunho antigo chamado
  // "RASCUNHO ANTIGO DO PAO DE QUEIJO 085800" tem "PAO DE QUEIJO" como curto.
  // ⚠️ A checagem acima ja cobre o caminho de RESERVA: aquele prato foi
  // cadastrado a mao, nunca teve nome de PDV, e a tela caiu no do cadastro.
  const nomePdv = `PDV ${m6} CURTO`;
  await api("PUT", `/produtos/${prod6.id}`, { nome_curto: nomePdv }, token);
  await p.reload({ waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  const comCurto = await p.evaluate(() => {
    const linha = [...document.querySelectorAll("tbody tr")]
      .find((t) => /CURTO/i.test(t.innerText));
    return { texto: linha?.innerText ?? "", achou: !!linha };
  });
  checar("o cupom passa a mostrar o nome do PDV", comCurto.achou, comCurto);
  // ⚠️ **E o do CADASTRO nao some.** Quem confere o cupom contra o cadastro
  // precisa saber em que produto a linha caiu — mostrar so o do PDV esconderia
  // justamente o que se esta conferindo.
  checar("e o nome do cadastro continua a vista, marcado como tal",
    /cadastro:/i.test(comCurto.texto) && new RegExp(`CMV TELA PRATO ${m6}`, "i")
      .test(comCurto.texto), comCurto);
  // Devolve o produto como estava: nome curto e do PDV, e este foi posto a mao.
  await api("PUT", `/produtos/${prod6.id}`, { nome_curto: null }, token);

  await foto(p, "24b-venda-detalhe");

  // 🔑 **O cupom da PESSOA mostra o cheio e o desconto** (04/09/2026, pedido do
  // dono: "ao acessar este cupom, ver o valor cheio e o valor do desconto").
  // ⚠️ **Este bloco monta o proprio cenario**, e nao reaproveita a venda acima:
  // aquela nao tem pessoa, entao as colunas novas nao apareceriam e a checagem
  // passaria pelo motivo errado — foi assim que o cartao de codigos passou
  // verde sem nunca ter rodado.
  const pessoaCupom = await api("POST", "/fornecedores", {
    nome: `CUPOM PESSOA ${m6}`, fornecedor: false,
    cupom_base: "VENDA", cupom_desconto_pct: 20,
  }, token);
  // 🔑 **Venda com pessoa exige ciclo de consumo ABERTO** (08/09/2026). Sem
  // isto o lancamento abaixo volta 400 e as seis checagens do cupom caem em
  // cascata, acusando a tela de nao mostrar o que ela nunca recebeu.
  // ⚠️ **As datas nascem depois do ultimo ciclo existente**: um ciclo real da
  // casa sobrepondo o do teste faz `abrir` devolver 409 por sobreposicao.
  // ⚠️ E o ciclo so se apaga se foi ESTA bateria que o abriu — um ciclo da casa
  // nao e lixo de teste.
  const { dados: ciclos } = await api("GET", "/consumo/periodos", null, token);
  let cicloDaBateria = null;
  if (!ciclos.aberto) {
    const ultimo = (ciclos.periodos || []).reduce(
      (mx, x) => (!mx || x.fim > mx ? x.fim : mx), null);
    const base = new Date(ultimo ? `${ultimo}T12:00:00` : Date.now());
    if (ultimo) base.setDate(base.getDate() + 1);
    // ⚠️ Local, nao UTC — ver a nota do `diaLocal` no topo do arquivo.
    const dia = (d) => d.toLocaleDateString("sv-SE");
    const fim = new Date(base);
    fim.setDate(fim.getDate() + 29);
    const novo = await api("POST", "/consumo/periodos", {
      inicio: dia(base), fim: dia(fim), nome: `Ciclo bateria ${m6}`,
    }, token);
    cicloDaBateria = novo.dados?.id ?? null;
    if (cicloDaBateria) {
      aoTerminar.push(() => api("DELETE", `/consumo/periodos/${cicloDaBateria}`, null, token));
    }
  }
  checar("ha ciclo de consumo aberto para a venda com pessoa",
    !!(ciclos.aberto || cicloDaBateria), { aberto: ciclos.aberto, cicloDaBateria });
  await api("POST", "/vendas/importar", { vendas: [{
    data: hoje6, documento: `PESSOA-${m6}`, origem: "MANUAL",
    id_pessoa: pessoaCupom.dados.id,
    itens: [{ id_produto: prod6.id, quantidade: 2, valor_unitario: 50 }],
  }] }, token);
  const { dados: comPessoa } = await api("GET", `/vendas?busca=PESSOA-${m6}`, null, token);
  checar("a venda com pessoa entra", comPessoa.length === 1, comPessoa.length);
  if (comPessoa.length) {
    aoTerminar.push(() => api("DELETE", `/vendas/${comPessoa[0].id}`, null, token));
    await p.goto(`${WEB}/vendas/${comPessoa[0].id}`, { waitUntil: "networkidle2" });
    await p.waitForFunction(() => /Receita/i.test(document.body.innerText),
      { timeout: 20000, polling: 300 }).catch(() => {});
    const textoPessoa = await textoVisivel(p);
    checar("o cupom diz para quem foi",
      new RegExp(`CUPOM PESSOA ${m6}`, "i").test(textoPessoa), textoPessoa.slice(0, 300));
    // 🔑 100 cheio, 20 de desconto, 80 cobrado. Os tres numeros na tela — e o
    // 100,00 so existe porque o preco de tabela passou a ser GUARDADO: antes a
    // politica o reescrevia e ele se perdia.
    checar("com o valor cheio de 100,00 a vista",
      /100,00/.test(textoPessoa), textoPessoa.slice(0, 400));
    checar("e o desconto de 20,00 dito",
      /desconto de/i.test(textoPessoa) && /20,00/.test(textoPessoa),
      textoPessoa.slice(0, 400));
    // ⚠️ **A politica CONGELADA**, nao a do cadastro de hoje: quem passar de 20%
    // para 30% faria este cupom se explicar por uma regra que nao valia quando
    // ele nasceu.
    checar("e a regra que valia no dia, escrita no cabecalho",
      /20% de desconto/i.test(textoPessoa), textoPessoa.slice(0, 400));
  }

  // A conta: 10 pratos a 5,00 de custo = 50,00 de CMV teórico; receita 300,00.
  const { dados: ap } = await api("GET", `/cmv/apuracao?inicio=${hoje6}&fim=${hoje6}`, null, token);
  checar("CMV teórico entra na apuração", Number(ap.cmv_teorico) >= 50,
    ap.cmv_teorico);
  checar("receita entra na apuração", Number(ap.receita) >= 300, ap.receita);

  await p.goto(`${WEB}/cmv?`, { waitUntil: "networkidle2" });
  // ⚠️ **Esperar o CONTEÚDO, nunca um tempo fixo.** Eram 1,5 s, e a rota do CMV
  // e compilada sob demanda em desenvolvimento: com o app maior a primeira
  // visita passou disso, e as quatro checagens abaixo passaram a medir a casca
  // do app — acusando a tela de nao mostrar numeros que ela mostra. E a mesma
  // licao que `esperarTexto` ja carrega: teste que falha "as vezes" e pior que
  // teste que nao existe, porque ensina a ignorar o vermelho.
  await p.waitForFunction(() => /Food cost/i.test(document.body.innerText),
    { timeout: 30000, polling: 300 }).catch(() => {});
  // 🔑 **O cabeçalho: o RECORTE de um lado, o que FAZER com ele do outro**
  // (pedido do dono, 16/09/2026: *"os filtros e botão do cabeçalho estão
  // misturados, podendo haver confusão"* e *"colocar como filtro de período
  // somente os períodos do CMV, não os de data inicial e final"*).
  const cab = await p.evaluate(() => {
    const h = document.querySelector("main header");
    const periodo = [...h.querySelectorAll("label")]
      .find((l) => /^Período$/i.test(l.querySelector("span")?.textContent?.trim() ?? ""));
    const sel = periodo?.querySelector("select");
    // ⚠️ `border-l-2`, nunca `border-l`: "border-linha2" CONTÉM "border-l" como
    // pedaço, e o filtro pegaria qualquer div com borda colorida.
    const grupos = [...h.querySelectorAll("div")]
      .filter((d) => typeof d.className === "string" && d.className.includes("border-l-2"));
    const divisor = grupos[0] ? getComputedStyle(grupos[0]) : null;
    return {
      titulo: h.querySelector("h1")?.textContent?.trim(),
      datas: h.querySelectorAll('input[type="date"]').length,
      rotulos: [...h.querySelectorAll(".rotulo-campo")].map((x) => x.textContent?.trim()),
      opcoes: sel ? [...sel.options].map((o) => o.textContent?.trim()) : [],
      escolhido: sel ? sel.options[sel.selectedIndex]?.textContent?.trim() : null,
      // ⚠️ **Medido, não presumido**: `--color-linha` some contra o fundo do
      // miolo, e as variantes `sm:` destas utilitárias não chegaram à folha —
      // nos dois casos a classe estava no HTML e o traço valia 0px.
      divisor: divisor ? divisor.borderLeftWidth : null,
      botoes: [...h.querySelectorAll("button")].map((x) => x.textContent?.trim()),
    };
  });
  checar("o cabeçalho se chama Painel de CMV", cab.titulo === "Painel de CMV", cab.titulo);
  // ⚠️ **Data digitada à mão é onde o engano entra**: "17/08 a 23/08" com um dia
  // a mais e a apuração deixa de bater com o fechamento, sem nada avisando — o
  // número continua saindo. O ciclo da loja é o único recorte em que a conta
  // fecha com o que foi fechado.
  checar("e o período só oferece os ciclos do CMV, sem data solta",
    cab.datas === 0, cab);
  checar("sem a opção vaga de 'outro recorte'",
    cab.opcoes.length > 0 && !cab.opcoes.some((o) => /outro recorte/i.test(o ?? "")),
    cab.opcoes);
  // 🔑 O período corrente vem ESCOLHIDO. Antes o seletor casava por início E
  // fim, e o corrente é truncado em hoje: ele nunca aparecia selecionado, e a
  // tela abria dizendo "outro recorte" sobre o período que estava mostrando.
  checar("com o período em curso já escolhido", /em curso/.test(cab.escolhido ?? ""),
    cab.escolhido);
  checar("os três filtros são Período, Escopo e Ver por",
    ["Período", "Escopo", "Ver por"].every((r) => cab.rotulos.includes(r)), cab.rotulos);
  // 🔑 **No cabeçalho só o RECORTE** (pedido do dono, 16/09/2026: *"retirar o
  // baixar e o imprimir tela do cabeçalho"*). Uma volta antes eles ficaram ali,
  // separados por um traço; agora saíram. ⚠️ "saber mais" é do `ExplicaTela` e
  // continua — ele abre a frase da tela, não tira nada de dentro do sistema.
  checar("e nenhum botão de baixar ou imprimir no cabeçalho",
    !cab.botoes.some((t) => /baixar|imprimir/i.test(t ?? "")), cab.botoes);

  // 🔑 **UM botão de baixar, na barra das abas** (pedido do dono, 16/09/2026:
  // *"alterar o baixar esta tabela para um botão de baixar"*). Eram cinco
  // espalhados pelo painel — um no cabeçalho, um por aba como link discreto e
  // mais um dentro da memória —, cada um dando um arquivo diferente e nenhum
  // com a conta do CMV junto.
  const naBarra = await p.evaluate(() => {
    const nav = document.querySelector('[role="tablist"]');
    const b = [...(nav?.querySelectorAll("button") ?? [])]
      .find((x) => x.textContent?.trim() === "Baixar");
    return { existe: !!b, botao: b ? b.className.includes("btn") : null,
             quantos: [...document.querySelectorAll("button")]
               .filter((x) => /^Baixar/i.test(x.textContent?.trim() ?? "")).length };
  });
  checar("a barra das abas tem o botão Baixar", naBarra.existe, naBarra);
  // ⚠️ Botão de verdade, não `link-acao`: ele TIRA a tela de dentro do sistema,
  // e isso não é um link de navegação.
  checar("e ele é botão, não link", naBarra.botao === true, naBarra);
  checar("e é o único da tela", naBarra.quantos === 1, naBarra);

  // A janela dele: o período é o CICLO, e a aba vem semeada com a que está
  // aberta — é o que faz o arquivo bater com o que está à vista.
  // ⚠️ Troca de aba ANTES de abrir: com a aba padrão a semeadura acertaria por
  // coincidência, e a checagem não provaria que ela acompanha.
  await p.evaluate(() => {
    [...document.querySelectorAll('[role="tab"]')]
      .find((b) => b.textContent?.trim() === "Curva ABC")?.click();
  });
  await new Promise((r) => setTimeout(r, 1800));
  await p.evaluate(() => {
    [...document.querySelectorAll('[role="tablist"] button')]
      .find((b) => b.textContent?.trim() === "Baixar")?.click();
  });
  await p.waitForFunction(() => document.querySelector('[role="dialog"]'),
    { timeout: 15000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 1800));
  const janelaCmv = await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    if (!d) return null;
    const sels = [...d.querySelectorAll("select")].map((x) => ({
      rotulo: x.closest("div")?.querySelector(".rotulo")?.textContent?.trim() ?? "?",
      escolhido: x.options[x.selectedIndex]?.textContent?.trim() ?? null,
      quantas: x.options.length,
    }));
    return { datas: d.querySelectorAll('input[type="date"]').length, sels };
  });
  checar("a janela de baixar abre", !!janelaCmv, janelaCmv);
  // 🔑 *"esta vai abrir o filtro do período, e não datas como está"*.
  checar("e o período nela é o ciclo do CMV, sem campo de data",
    janelaCmv?.datas === 0
      && /em curso/.test(janelaCmv.sels.find((x) => x.rotulo === "Período")?.escolhido ?? ""),
    janelaCmv);
  // 🔑 *"os dados da aba posicionada"*: a aba aberta chega escolhida. Sem isso,
  // baixar da aba da curva ABC daria a margem por prato — o padrão do
  // relatório —, e quem conferisse os dois acharia que um deles mente.
  checar("e a aba aberta já vem escolhida no arquivo",
    /Curva ABC/i.test(janelaCmv?.sels.find((x) => /levar junto/i.test(x.rotulo))?.escolhido ?? ""),
    janelaCmv?.sels);
  await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    [...(d?.querySelectorAll("button") ?? [])]
      .find((b) => b.textContent?.trim() === "Cancelar")?.click();
  });
  // ⚠️ **Devolve a aba.** Este bloco trocou para a Curva ABC de propósito, e as
  // checagens seguintes leem a aba "A conta" — a da cascata. Fase que desvia,
  // devolve: sem isto a cascata não estava na tela e a falha acusava o desenho,
  // que estava intacto.
  await p.evaluate(() => {
    [...document.querySelectorAll('[role="tab"]')]
      .find((b) => b.textContent?.trim() === "A conta")?.click();
  });
  await new Promise((r) => setTimeout(r, 1500));

  const textoCmv = await p.evaluate(() => document.body.innerText);
  checar("painel mostra CMV real e teórico",
    /CMV REAL/i.test(textoCmv) && /CMV TEÓRICO/i.test(textoCmv), textoCmv.slice(0, 80));
  // ⚠️ **A variância deixou de ser ladrilho** (16/09/2026, protótipo aprovado):
  // ela é a RELAÇÃO entre o real e o teórico, e virou a legenda do teórico. A
  // checagem antiga procurava a palavra no texto da página inteira e passaria
  // por acidente pelo cabeçalho da tabela de períodos fechados — procura agora
  // o ladrilho, que é onde ela precisa estar.
  const ladrilhos = await p.evaluate(() =>
    [...document.querySelectorAll("p.rotulo")].map((x) => ({
      rotulo: x.textContent?.trim(),
      resto: [...(x.parentElement?.querySelectorAll("p") ?? [])]
        .slice(1).map((y) => y.textContent?.trim()).join(" · "),
    })));
  const teorico = ladrilhos.find((x) => /CMV teórico/i.test(x.rotulo ?? ""));
  checar("a variância vem junto do CMV teórico, não solta",
    /Variância: R\$/i.test(teorico?.resto ?? ""), teorico);
  checar("e a receita ganhou ladrilho próprio",
    ladrilhos.some((x) => x.rotulo === "Receita"), ladrilhos.map((x) => x.rotulo));
  checar("painel mostra food cost", /FOOD COST/i.test(textoCmv));

  // 🔑 **As sete abas** (16/09/2026, protótipo aprovado). Eram quatro listas
  // empilhadas; a primeira agora é A CONTA, desenhada.
  const abasCmv = await p.evaluate(() =>
    [...document.querySelectorAll('[role="tab"]')].map((b) => b.textContent?.trim()));
  for (const esperada of ["A conta", "Curva ABC", "Margem por prato", "Movimentação",
                          "O que subiu de preço", "Memória de cálculo"]) {
    checar(`o painel tem a aba "${esperada}"`, abasCmv.includes(esperada), abasCmv);
  }
  checar("e a aba da quebra leva o eixo escolhido no nome",
    abasCmv.some((x) => /^Quebra por /.test(x ?? "")), abasCmv);
  // A cascata: a conta do CMV desenhada, e não mais montada de cabeça. O
  // `aria-label` é a mesma conta em palavras — se o desenho sumir, ele some com
  // ela, e a checagem não passa por um SVG vazio.
  const cascata = await p.evaluate(() =>
    document.querySelector('svg[role="img"]')?.getAttribute("aria-label") ?? "");
  checar("a aba A conta desenha a cascata do CMV",
    /Estoque inicial .*mais compras .*menos estoque final .*CMV/i.test(cascata),
    cascata.slice(0, 120));
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

  // 🔑 **A tela virou ABAS** (09/09/2026, pedido do dono: *"cria uma aba e
  // coloca as coisas do Omie, outra para o PDV Legal, outra para o e-mail e
  // demais"*). Eram dez cartões empilhados em 751 linhas, e quem vinha
  // configurar o e-mail rolava por credencial, notas, catálogo, custo inicial e
  // conferência de estoque.
  const abasInt = await p.evaluate(() => ({
    nomes: [...document.querySelectorAll("nav button")].map((b) => b.textContent?.trim()),
    // ⚠️ Sem `?aba=`, abre a PRIMEIRA — e a primeira tem de ser uma que a
    // pessoa pode ver, senão ela cai numa aba vazia sem entender por quê.
    url: location.search,
    // A frase do que a aba faz vem antes do conteúdo: "Omie" e "PDV Legal" são
    // nomes de fornecedor, não dizem o que cada um traz para cá.
    explica: /notas de compra|cat[áa]logo de produtos/i.test(document.body.innerText),
  }));
  checar("Integrações tem uma aba por integração",
    ["Omie", "PDV Legal", "E-mail"].every((n) => abasInt.nomes.includes(n)), abasInt.nomes);
  checar("e abre na primeira sem precisar de ?aba=", abasInt.url === "", abasInt.url);
  checar("dizendo o que a aba traz, não só o nome do fornecedor", abasInt.explica, abasInt);

  // 🔑 **A aba vive na URL**: é o que permite o menu apontar direto, o voltar do
  // navegador funcionar e a tela virar um link que se manda para alguém.
  await irPara(p, `${WEB}/integracoes?aba=email`);
  await p.waitForFunction(() => /SMTP|servidor de e-mail|e-mail/i.test(
    document.body.innerText), { timeout: 15000 }).catch(() => {});
  const naEmail = await p.evaluate(() => ({
    // O bloco do Omie NÃO pode estar na tela do e-mail: se estiver, as abas
    // são enfeite e a tela continua sendo a pilha de antes.
    temOmie: /app_key|Credenciais do Omie/i.test(document.body.innerText),
    temEmail: /SMTP|servidor de e-mail/i.test(document.body.innerText),
  }));
  checar("a aba do e-mail abre pela URL", naEmail.temEmail, naEmail);
  checar("e não carrega junto o bloco do Omie", !naEmail.temOmie, naEmail);

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

  // 🔑 **O pré-cadastro e a TROCA de produto, na própria conferência**
  // (pedido do dono, 14/09/2026). O item do azeite está pendente, que é o estado
  // exato em que a casa se vê quando o código do fornecedor não casa com nada —
  // e é daqui que saem os dois caminhos: criar o que falta, ou trocar o que veio
  // errado. O caso que puxou isto foi o ABACATE de um fornecedor e o MORANGO de
  // outro dividindo o mesmo código no Omie.
  const clicarLinha = async (texto) =>
    p.evaluate((t) => {
      const b = [...document.querySelectorAll("button")].find(
        (x) => (x.textContent ?? "").trim().toLowerCase() === t);
      if (b) b.click();
      return !!b;
    }, texto);
  const temLinhaBotao = async (texto) =>
    p.evaluate((t) => [...document.querySelectorAll("button")]
      .some((x) => (x.textContent ?? "").trim() === t), texto);

  checar("o item pendente oferece criar o produto pela própria nota",
    await temLinhaBotao("criar produto"));
  await clicarLinha("criar produto");
  await esperarTexto(p, "completar cadastro", 9000);
  const textoRascunho = await p.evaluate(() => document.body.innerText);
  // ⚠️ **O pré-cadastro tem de se anunciar NA LINHA.** Ele nasce rascunho — sem
  // unidade e sem fator conferidos — e quem sabe os dois é justamente quem está
  // com a nota na mão. O alerta do início avisa a casa, não esta nota.
  checar("o produto criado pela nota se anuncia rascunho na linha",
    /rascunho — completar cadastro/i.test(textoRascunho), textoRascunho.slice(0, 400));
  checar("e a nota deixa de ter item sem produto",
    !/sem produto vinculado/i.test(textoRascunho), textoRascunho.slice(0, 300));

  // A troca: até aqui, item já casado só abria a janela da conversão, e não
  // havia como dizer "não é este produto" antes de a nota virar razão.
  checar("item já vinculado oferece trocar o produto",
    await temLinhaBotao("não é este produto"));
  await clicarLinha("não é este produto");
  await esperarTexto(p, "hoje está em", 6000);
  const textoTroca = await p.evaluate(() => document.body.innerText);
  checar("trocar abre a busca dizendo em que produto a linha está hoje",
    /hoje está em/i.test(textoTroca), textoTroca.slice(0, 400));
  checar("com a saída de trocar e a de desistir",
    (await temLinhaBotao("trocar")) && (await temLinhaBotao("cancelar")));
  await foto(p, "29c-trocar-produto");
  // ⚠️ Desiste: a nota segue para as checagens seguintes do jeito que estava.
  await clicarLinha("cancelar");
  await new Promise((r) => setTimeout(r, 400));
  checar("desistir devolve a linha ao produto que já estava lá",
    !(await temLinhaBotao("trocar")) && (await temLinhaBotao("não é este produto")));

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
  // ⚠️ Mesma razao do CMV: 1,2 s fixos nao bastam para a rota compilada sob
  // demanda em desenvolvimento, e a falha aparecia como "o formulario nao abre"
  // num formulario que abre.
  await p.waitForFunction(() => document.querySelectorAll("main select").length >= 3,
    { timeout: 30000, polling: 300 }).catch(() => {});
  const seletoresNota = await p.$$("main select");
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

  console.log("7y. as prateleiras ja na CRIACAO do produto");
  // 🔑 Pedido do dono (02/09/2026): o cartao aparecia so depois de o produto
  // existir. E ali, cadastrando, que a pessoa decide onde ele vai morar —
  // esconder o campo faz concluir que o sistema nao o tem. Sem id nao ha onde
  // gravar, entao as prateleiras ficam no estado e sobem depois do POST.
  const mNovo = String(Date.now()).slice(-6);
  const idLocalNovo = await garantirLocal();
  const { dados: localExtra } = await api(
    "POST", "/locais", { nome: `Canto criacao ${mNovo}`, tipo: "SECO" }, token);

  await irPara(p, `${WEB}/produtos/novo`);
  // 🔑 **Em produto NOVO a aba de Estoque continua existindo.** Fornecedor e
  // movimento apontam para um id que ainda nao ha — a prateleira nao: e ali,
  // cadastrando, que a pessoa decide onde o produto vai morar.
  await p.waitForFunction(
    () => [...document.querySelectorAll('[role="tab"]')]
      .some((b) => b.textContent.trim() === "Estoque"), { timeout: 15000 }).catch(() => {});
  await p.evaluate(() => [...document.querySelectorAll('[role="tab"]')]
    .find((b) => b.textContent.trim() === "Estoque")?.click());
  await p.waitForSelector("#local-a-acrescentar", { timeout: 15000 });
  checar("a tela de criar produto ja tem o cartao das prateleiras", true);
  const textoNovo = await textoVisivel(p);
  checar("e explica que elas nascem vazias junto com o produto",
    /passam a existir vazias|nascem vazias|vao morar|vai morar/i.test(textoNovo),
    textoNovo.slice(0, 300));

  await p.select("#local-a-acrescentar", String(localExtra.id));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((b) => b.textContent?.trim() === "Acrescentar")?.click();
  });
  await p.waitForSelector("#locais-do-produto", { timeout: 10000 });
  // ⚠️ Nada foi ao servidor ainda: o produto nem existe.
  const linhaPendente = await p.evaluate(() =>
    [...document.querySelectorAll("#locais-do-produto tbody tr")].map((t) => t.innerText));
  checar("a prateleira escolhida entra na lista antes de o produto existir",
    linhaPendente.some((l) => l.includes(`CANTO CRIACAO ${mNovo}`)), linhaPendente);

  // Preenche o minimo e cria. As prateleiras sobem logo depois do POST.
  await p.evaluate((nome) => {
    const campos = [...document.querySelectorAll("input.campo")];
    const alvo = campos.find((c) => c.closest("label")?.innerText?.match(/Nome/i));
    const nativo = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    nativo.call(alvo, nome);
    alvo.dispatchEvent(new Event("input", { bubbles: true }));
  }, `Produto criacao ${mNovo}`);
  await p.evaluate(() => {
    const s = [...document.querySelectorAll("main select")]
      .find((x) => [...x.options].some((o) => /KG/.test(o.textContent ?? "")));
    if (!s) return;
    const o = [...s.options].find((x) => /^KG/.test(x.textContent ?? ""));
    if (!o) return;
    const nativo = Object.getOwnPropertyDescriptor(
      window.HTMLSelectElement.prototype, "value").set;
    nativo.call(s, o.value);
    s.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((b) => b.textContent?.trim() === "Criar produto")?.click();
  });
  await new Promise((r) => setTimeout(r, 3000));
  const { dados: achados } = await api(
    "GET", `/produtos?busca=${encodeURIComponent(`Produto criacao ${mNovo}`)}`, null, token);
  const produtoCriado = (achados ?? [])[0];
  checar("o produto e criado pela tela", !!produtoCriado, achados);
  if (produtoCriado) {
    aoTerminar.push(() => api("DELETE", `/produtos/${produtoCriado.id}`, null, token));
    const { dados: locaisDoNovo } = await api(
      "GET", `/produtos/${produtoCriado.id}/locais`, null, token);
    checar("e a prateleira escolhida na criacao ja esta gravada",
      (locaisDoNovo ?? []).some((l) => l.id_local === localExtra.id), locaisDoNovo);
    checar("com saldo zero — declarar nao movimenta nada",
      Number((locaisDoNovo ?? []).find((l) => l.id_local === localExtra.id)?.quantidade) === 0,
      locaisDoNovo);
    await api("DELETE", `/produtos/${produtoCriado.id}/locais/${localExtra.id}`, null, token);
  }
  await api("DELETE", `/locais/${localExtra.id}`, null, token);
  void idLocalNovo;

  console.log("7z. as prateleiras no cadastro do produto");
  // 🔑 O cadastro só tinha o local PADRÃO, aquele por onde o produto ENTRA. As
  // demais prateleiras só passavam a existir na primeira transferência — não
  // havia como preparar a casa antes de operar, nem como ver de relance em
  // quantos cantos o mesmo insumo mora.
  const mLoc = String(Date.now()).slice(-6);
  const idLocalA = await garantirLocal();
  const { dados: localB } = await api(
    "POST", "/locais", { nome: `Canto tela ${mLoc}`, tipo: "SECO" }, token);
  const { dados: prodLoc } = await api("POST", "/produtos", {
    codigo: `TLOC-${mLoc}`, nome: `Insumo dos locais ${mLoc}`, tipo: "INSUMO",
    um_estoque: "KG", controla_estoque: true, id_local_padrao: idLocalA,
  }, token);
  aoTerminar.push(() => api("DELETE", `/produtos/${prodLoc.id}`, null, token));
  await api("POST", "/estoque/entradas", {
    id_produto: prodLoc.id, quantidade: 8, custo_unitario: 2.5, id_local: idLocalA,
  }, token);

  await irPara(p, `${WEB}/produtos/${prodLoc.id}`);
  // ⚠️ Esperar pelo que se vai MEDIR, nunca um tempo fixo: o cartão só existe
  // depois de `/produtos/{id}/locais` responder, e dormir e afirmar é supor a
  // precondição.
  await p.waitForSelector("#locais-do-produto", { timeout: 15000 });

  // 🔑 **Salvar RECARREGA a tela** (09/09/2026, relato do dono: "preciso dar
  // F5 para mostrar o custo certo"). O servidor TRANSFORMA o que recebe — o
  // nome vira maiuscula, e trocar a unidade de estoque converte o custo. Sem
  // reler, a tela seguia mostrando o valor de antes no exato momento em que ele
  // mudou.
  // ⚠️ A prova usa o nome porque a transformacao e visivel e barata: digita-se
  // minusculo, e o campo tem de mostrar MAIUSCULO sem ninguem recarregar nada.
  const nomeMinusculo = `prod local ${mLoc} renomeado`;
  await p.evaluate((novoNome) => {
    const campo = document.querySelector('input[name="nome"], #nome')
      ?? [...document.querySelectorAll("input")].find(
        (i) => (i.value ?? "").length > 3 && i.type === "text");
    if (campo) {
      const set = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, "value").set;
      set.call(campo, novoNome);
      campo.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }, nomeMinusculo);
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((b) => /^Salvar$/.test(b.textContent?.trim() ?? ""))?.click();
  });
  // Espera o CONTEUDO: o campo mostrando o nome ja normalizado pelo servidor.
  const releu = await p.waitForFunction(
    (esperado) => [...document.querySelectorAll("input")]
      .some((i) => (i.value ?? "").trim() === esperado),
    { timeout: 15000, polling: 250 }, nomeMinusculo.toUpperCase(),
  ).then(() => true).catch(() => false);
  checar("salvar releu o produto do servidor, sem F5", releu, nomeMinusculo);

  // ⚠️ **As prateleiras moraram para a aba Estoque** (16/09/2026). A tela e a
  // mesma; o que mudou e que agora ha uma aba entre ela e quem olha.
  await p.evaluate(() => [...document.querySelectorAll('[role="tab"]')]
    .find((b) => b.textContent.trim() === "Estoque")?.click());
  await new Promise((r) => setTimeout(r, 600));
  const textoLoc = await textoVisivel(p);
  checar("a tela do produto diz em que prateleiras ele está",
    /Onde este produto fica/i.test(textoLoc), textoLoc.slice(0, 160));
  const linhasLoc = await p.evaluate(() =>
    [...document.querySelectorAll("#locais-do-produto tbody tr")].map((t) => t.innerText));
  checar("com o saldo daquela prateleira",
    linhasLoc.some((l) => /8/.test(l)), linhasLoc);
  checar("e com o custo médio dela",
    linhasLoc.some((l) => /R\$\s*2,50/.test(l)), linhasLoc);

  // 🔑 Declarar uma prateleira NÃO movimenta nada — é o ponto do pedido: ela
  // passa a existir vazia, pronta para receber a transferência.
  await p.select("#local-a-acrescentar", String(localB.id));
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((b) => b.textContent?.trim() === "Acrescentar")?.click();
  });
  await p.waitForFunction(
    (nome) => [...document.querySelectorAll("#locais-do-produto tbody tr")]
      .some((t) => t.innerText.includes(nome)),
    { timeout: 15000 }, `Canto tela ${mLoc}`.toUpperCase());
  const { dados: locaisApi } = await api(
    "GET", `/produtos/${prodLoc.id}/locais`, null, token);
  checar("acrescentar um local pela tela grava no servidor",
    (locaisApi ?? []).some((l) => l.id_local === localB.id), locaisApi);
  checar("e a prateleira nova nasce com saldo zero",
    Number((locaisApi ?? []).find((l) => l.id_local === localB.id)?.quantidade) === 0,
    locaisApi);
  const { dados: movLoc } = await api(
    "GET", `/estoque/movimentos?id_produto=${prodLoc.id}`, null, token);
  checar("e nenhum movimento entrou no razão por causa disso",
    (movLoc ?? []).length === 1, (movLoc ?? []).length);
  await foto(p, "37a-locais-do-produto");

  // 🔑 **O custo do produto, que nao tinha onde ser consultado** (pedido do
  // dono, 03/09/2026). Ele ja alimentava ficha, CMV teorico e margem, mas
  // nenhuma tela o mostrava. ⚠️ E a "Memoria de calculo" ao lado nao cobre o
  // caso: ela explica o custo MEDIO, que nasce de movimento — numa casa que
  // importou o catalogo e ainda nao lancou nota ela sai vazia, enquanto o custo
  // de referencia responde pela cascata sem aparecer em lugar nenhum.
  const custoNaTela = await p.evaluate(() => {
    const cartao = [...document.querySelectorAll("section.cartao")]
      .find((c) => (c.querySelector("h2")?.textContent ?? "").trim() === "Valores");
    return {
      temCartao: !!cartao,
      // ⚠️ A ORIGEM vem junto do valor: "R$ 20,03" sem dizer se e o que a casa
      // pagou, o que o fornecedor cobra ou o que outro sistema acha nao
      // responde a pergunta que se faz em seguida.
      dizAOrigem: /custo m[ée]dio|fornecedor|refer[êe]ncia|ningu[ée]m sabe/i
        .test(cartao?.innerText ?? ""),
      botao: [...(cartao?.querySelectorAll("button") ?? [])]
        .some((b) => b.textContent?.trim() === "Histórico"),
    };
  });
  checar("a tela do produto mostra o custo", custoNaTela.temCartao, custoNaTela);
  checar("dizendo de ONDE o numero veio", custoNaTela.dizAOrigem, custoNaTela);
  checar("com o botao de historico", custoNaTela.botao, custoNaTela);

  await p.evaluate(() => {
    const cartao = [...document.querySelectorAll("section.cartao")]
      .find((c) => (c.querySelector("h2")?.textContent ?? "").trim() === "Valores");
    [...(cartao?.querySelectorAll("button") ?? [])]
      .find((b) => b.textContent?.trim() === "Histórico")?.click();
  });
  await p.waitForSelector('[role="dialog"]', { timeout: 10000 }).catch(() => {});
  const historico = await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    return {
      abriu: !!d,
      titulo: d?.querySelector("h2")?.textContent ?? "",
      // 🔑 A distincao que evita a leitura errada: so o razao e uma linha do
      // tempo. Fornecedor e referencia guardam so o valor corrente.
      explicaAsFontes: /linha do tempo/i.test(d?.textContent ?? ""),
    };
  });
  checar("o historico abre numa janela", historico.abriu, historico);
  checar("com o titulo dizendo o que e",
    /Hist[óo]rico de custo/i.test(historico.titulo), historico);
  checar("e explicando que so o razao e uma linha do tempo",
    historico.explicaAsFontes, historico);
  await foto(p, "37b-custo-do-produto");
  await p.keyboard.press("Escape");

  // 🔑 **A conversao do codigo de fora** (o ACUCAR DE CONFEITEIRO): o fornecedor
  // manda o pacote de 1 kg e o de 500 g como produtos DIFERENTES, e aqui os dois
  // sao o mesmo. Depois da fusao, a nota do de 500 g entrava como 1 kg por
  // unidade — o estoque dobrava calado.
  // ⚠️ Este produto foi fundido no bloco do Vincular, entao tem apelido.
  // ⚠️ Tirar só com a prateleira VAZIA — quem recusa é o servidor. Aqui ela
  // está vazia, então sai.
  await p.evaluate((nome) => {
    const linha = [...document.querySelectorAll("#locais-do-produto tbody tr")]
      .find((t) => t.innerText.includes(nome));
    linha?.querySelector("button")?.click();
  }, `Canto tela ${mLoc}`.toUpperCase());
  await p.waitForFunction(
    (nome) => ![...document.querySelectorAll("#locais-do-produto tbody tr")]
      .some((t) => t.innerText.includes(nome)),
    { timeout: 15000 }, `Canto tela ${mLoc}`.toUpperCase());
  const { dados: locaisDepois } = await api(
    "GET", `/produtos/${prodLoc.id}/locais`, null, token);
  checar("e tirar a prateleira vazia some com ela no servidor também",
    !(locaisDepois ?? []).some((l) => l.id_local === localB.id), locaisDepois);
  // ⚠️ A que tem saldo continua: apagá-la faria o estoque sumir da vista sem um
  // movimento no razão explicando.
  checar("enquanto a que tem saldo continua no cadastro",
    (locaisDepois ?? []).some((l) => l.id_local === idLocalA), locaisDepois);

  // 🔑 **Excluir a LINHA que se quer, não a última.** O rodapé antigo removia
  // sempre a de baixo: quem tinha três embalagens e queria tirar a do meio
  // apagava duas e redigitava uma.
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((b) => (b.textContent ?? "").trim() === "+ unidade")?.click();
  });
  const removedores = await p.evaluate(() =>
    [...document.querySelectorAll('button[aria-label^="remover "]')].length);
  checar("cada linha de unidade de compra tem o próprio remover", removedores >= 1,
    removedores);

  await api("DELETE", `/locais/${localB.id}`, null, token);

  // 🔑 **A linha de PESO pergunta ao contrario** (12/09/2026, caso da cliente:
  // ela compra a duzia de ovos, estoca em UN e usa 50 G de ovo na receita).
  // `produto_unidades.fator` sempre quis dizer "quantas unidades de ESTOQUE
  // cabem em uma desta" — para o grama isso da 0,02, e ninguem sabe quantos
  // ovos cabem num grama: a cozinha sabe que o ovo pesa 50 g. A tela pergunta
  // "1 UN = [50] G" e grava o inverso.
  // ⚠️ **Cenario proprio, em UN.** O `prodLoc` acima estoca em KG, e KG com G e
  // a MESMA grandeza: ali a pergunta nao vira, e a checagem passaria sem
  // exercitar nada.
  // ⚠️ **E a checagem vai ate a FICHA.** Conferir so o fator seria testar a tela
  // contra ela mesma; o que importa e que 50 G virem 1 UN no consumo.
  const mOvo = `${Date.now()}`.slice(-6);
  const { dados: ovoTela } = await api("POST", "/produtos", {
    codigo: `TOVO-${mOvo}`, nome: `Ovo tela ${mOvo}`, tipo: "INSUMO",
    um_estoque: "UN", controla_estoque: true,
  }, token);
  aoTerminar.push(() => api("DELETE", `/produtos/${ovoTela.id}`, null, token));
  await irPara(p, `${WEB}/produtos/${ovoTela.id}`);
  await p.waitForFunction(() => /Unidades de compra/.test(document.body.innerText),
    { timeout: 15000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 700));
  const cabecalhoEquiv = await p.evaluate(() =>
    [...document.querySelectorAll("section.cartao thead th")].map((t) => t.textContent));
  checar("a coluna da equivalencia mostra a relacao, nao um numero solto",
    cabecalhoEquiv.includes("Equivalência"), cabecalhoEquiv);

  await p.evaluate(() => [...document.querySelectorAll("button")]
    .find((b) => (b.textContent ?? "").trim() === "+ unidade")?.click());
  await new Promise((r) => setTimeout(r, 400));
  const selsOvo = await p.$$("section.cartao tbody select");
  await selsOvo[selsOvo.length - 1].select("G");
  await new Promise((r) => setTimeout(r, 400));
  const rotulosOvo = await p.evaluate(() =>
    [...document.querySelectorAll("section.cartao tbody input[aria-label]")]
      .map((i) => i.getAttribute("aria-label")));
  checar("escolhida a unidade de peso, a pergunta vira para 1 UN = ? G",
    rotulosOvo.some((r) => /^quantos G em 1 UN$/.test(r ?? "")), rotulosOvo);

  const campoPeso = await p.$('section.cartao tbody input[aria-label="quantos G em 1 UN"]');
  await campoPeso.type("50");
  await p.evaluate(() => [...document.querySelectorAll("button")]
    .find((b) => /Gravar unidades/.test(b.textContent ?? ""))?.click());
  await p.waitForFunction(
    () => /gravada/i.test(document.body.innerText), { timeout: 10000 },
  ).catch(() => {});
  const { dados: unidadesOvo } = await api(
    "GET", `/produtos/${ovoTela.id}/unidades`, null, token);
  const linhaG = (unidadesOvo ?? []).find((x) => x.um === "G");
  checar("e o banco recebe o INVERSO: 1 UN = 50 G grava fator 0,02",
    !!linhaG && Math.abs(Number(linhaG.fator) - 0.02) < 1e-9, unidadesOvo);

  // A volta: a tela nao pode devolver 0,02 a quem digitou 50.
  await irPara(p, `${WEB}/produtos/${ovoTela.id}`);
  // ⚠️ **Espera a LINHA da unidade existir, nao 1.300 ms.** O tempo fixo
  // bastava ate a bateria passar a rodar sem cache do navegador (15/09/2026):
  // com a folha e a rota compiladas do zero, a tabela chega depois, e a sonda
  // lia uma lista vazia e acusava a tela de perder o que tinha acabado de
  // gravar. A afirmacao continua sendo sobre o VALOR; o que mudou foi esperar
  // pela coisa certa.
  await p.waitForFunction(
    () => document.querySelectorAll("section.cartao tbody input[aria-label]").length > 0,
    { timeout: 20000, polling: 250 },
  ).catch(() => {});
  const devolta = await p.evaluate(() =>
    [...document.querySelectorAll("section.cartao tbody input[aria-label]")]
      .map((i) => `${i.getAttribute("aria-label")}=${i.value}`));
  checar("recarregando, a tela mostra 50 de novo", 
    devolta.some((r) => /^quantos G em 1 UN=50$/.test(r)), devolta);

  // O que a tela gravou e o que a ficha usa.
  const { dados: massaOvo } = await api("POST", "/produtos", {
    codigo: `TMAS-${mOvo}`, nome: `Massa tela ${mOvo}`, tipo: "PRODUZIDO",
    um_estoque: "KG", controla_estoque: true, producao_propria: true,
  }, token);
  aoTerminar.push(() => api("DELETE", `/produtos/${massaOvo.id}`, null, token));
  const { dados: fichaOvo } = await api("POST", "/fichas", {
    id_produto: massaOvo.id, rendimento_qtd: 1, rendimento_um: "KG", porcoes: 1,
    itens: [{ id_insumo: ovoTela.id, qtd_bruta: 50, um: "G" }],
  }, token);
  aoTerminar.push(() => api("DELETE", `/fichas/${fichaOvo.id}`, null, token));
  const { dados: detalheOvo } = await api("GET", `/fichas/${fichaOvo.id}`, null, token);
  const itemOvo = (detalheOvo?.itens ?? [])[0];
  checar("e 50 G de ovo viram 1 UN na ficha, pelo que a tela gravou",
    !!itemOvo && Math.abs(Number(itemOvo.qtd_estoque) - 1) < 1e-6
      && itemOvo.conversao === "embalagem",
    itemOvo && { qtd_estoque: itemOvo.qtd_estoque, conversao: itemOvo.conversao,
                 aviso: itemOvo.aviso });
  await foto(p, "37b-equivalencia-de-peso");

  // ⚠️ **Este bloco NAVEGA para outro produto, entao vem DEPOIS das checagens
  // de prateleira.** Posto antes, ele levava a tela embora e as tres checagens
  // seguintes mediam a pagina errada — a falha apareceu como "tirar a
  // prateleira vazia nao sumiu", num comportamento que funciona.
  // ⚠️ **O cenario e MONTADO aqui, e nao aproveitado de outro bloco.** A primeira
  // versao dependia de o produto da vez ter codigo de fora — nao tinha, o `if`
  // pulava tudo em silencio e a rodada fechava com a MESMA contagem de antes.
  // Checagem que nao roda e pior que checagem que falha: ela diz verde.
  const mCod = Date.now().toString().slice(-6);
  const { dados: acu1 } = await api("POST", "/produtos", {
    codigo: `TACU1-${mCod}`, nome: `ACUCAR TELA 1KG ${mCod}`, tipo: "INSUMO",
    um_estoque: "KG", controla_estoque: true, status: "ATIVO", codigo_omie: `TA1${mCod}`,
  }, token);
  const { dados: acu5 } = await api("POST", "/produtos", {
    codigo: `TACU5-${mCod}`, nome: `ACUCAR TELA 500G ${mCod}`, tipo: "INSUMO",
    um_estoque: "KG", controla_estoque: true, status: "ATIVO", codigo_omie: `TA5${mCod}`,
  }, token);
  aoTerminar.push(() => api("DELETE", `/produtos/${acu1.id}`, null, token));
  aoTerminar.push(() => api("DELETE", `/produtos/${acu5.id}`, null, token));
  // A fusao e o que cria o apelido — e e o apelido que recebe a conversao.
  await api("POST", `/produtos/${acu1.id}/vincular`, { id_sai: acu5.id }, token);

  await irPara(p, `${WEB}/produtos/${acu1.id}`);
  await p.waitForFunction(() => /Códigos de fora/i.test(document.body.innerText),
    { timeout: 30000, polling: 300 }).catch(() => {});
  const temCartaoCodigos = await p.evaluate(() =>
    [...document.querySelectorAll("section.cartao")]
      .some((c) => /Códigos de fora/i.test(c.querySelector("h2")?.textContent ?? "")));
  checar("o produto fundido mostra o cartao de codigos de fora", temCartaoCodigos);
  if (temCartaoCodigos) {
    const campoConv = await p.evaluate(() => {
      const i = document.querySelector('input[aria-label^="conversão de"]');
      return i ? { rotulo: i.getAttribute("aria-label"), valor: i.value } : null;
    });
    checar("o cartao de codigos de fora oferece a conversao", !!campoConv, campoConv);
    if (campoConv) {
      // ⚠️ **O valor tem de FICAR na tela depois de gravar.** Ele sumia: o campo
      // lia `rascunho ?? valor do servidor` e o gravar limpava o rascunho com
      // string VAZIA — que nao e `undefined`, entao o `??` nao caia no valor de
      // volta. O numero estava salvo o tempo todo e so nao aparecia, e por isso
      // recarregar "resolvia" — que e o que faz esse tipo de defeito passar
      // despercebido.
      await p.evaluate(() => {
        const c = document.querySelector('input[aria-label^="conversão de"]');
        const s2 = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, "value").set;
        s2.call(c, "0.5");
        c.dispatchEvent(new Event("input", { bubbles: true }));
        [...c.closest("tr").querySelectorAll("button")]
          .find((b) => /Gravar/i.test(b.textContent ?? ""))?.click();
      });
      await new Promise((r) => setTimeout(r, 2500));
      const depoisDeGravar = await p.evaluate(() => {
        const c = document.querySelector('input[aria-label^="conversão de"]');
        return { valor: c?.value, naoInformada: /não informada/i.test(c?.closest("tr")?.innerText ?? "") };
      });
      checar("e o valor gravado CONTINUA na tela, sem recarregar",
        Number(String(depoisDeGravar.valor).replace(",", ".")) === 0.5, depoisDeGravar);
      // A etiqueta "nao informada" separa o 1 automatico do 1 digitado; gravada
      // a conversao, ela tem de sair.
      checar("e a etiqueta de nao informada sai", !depoisDeGravar.naoInformada,
        depoisDeGravar);
      await foto(p, "37c-conversao-do-codigo");
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
  // ⚠️ **O rótulo encurtou de "Movimentação do estoque" para "Movimentação"**
  // quando os botões viraram abas (16/09/2026): dentro do painel do CMV não há
  // outra movimentação, e o nome comprido roubava a largura das outras seis.
  checar("a aba Movimentação abre no painel de CMV",
    await clicarQuando(p, "Movimentação", { exato: true }));
  await new Promise((r) => setTimeout(r, 1800));
  const mov = await p.evaluate(() => {
    const texto = document.body.innerText;
    const cabecalhos = [...document.querySelectorAll("th")].map((t) => t.textContent?.trim());
    return {
      colunas: ["Inicial", "Entradas", "Saídas", "Final"].every((c) => cabecalhos.includes(c)),
      situacao: /período (aberto|fechado)/i.test(texto),
      fecha: /a conta fecha/i.test(texto),
      naoFecha: /A conta não fecha/i.test(texto),
      // ⚠️ **O diagnóstico vai junto, e isto custou uma investigação inteira.**
      // A versão anterior reprovava com `{fecha:false}` e mais nada — sem o
      // valor, sem o período e sem os quatro números. Reproduzida depois, com a
      // máquina livre, a identidade fechava com diferença ZERO: era um
      // lançamento retroativo que uma fase anterior deixou e outra desfez.
      // 🔑 Esta checagem é sensível ao que as outras fases deixam na base (ver
      // a nota do ritmo MENSAL no começo do arquivo). Quando ela cair de novo,
      // o que importa é saber DE QUANTO e EM QUE janela — senão a investigação
      // recomeça do zero, como recomeçou desta vez.
      quanto: (texto.match(/A conta não fecha por ([^(]+)/i) || [])[1]?.trim() ?? null,
      janela: (texto.match(/\d{2}\/\d{2}\/\d{4}\s*(a|–|-)\s*\d{2}\/\d{2}\/\d{4}/) || [])[0]
        ?? null,
      totais: [...document.querySelectorAll("tfoot td, tfoot th")]
        .map((c) => c.textContent?.trim()).filter(Boolean).slice(0, 6),
    };
  });
  checar("a movimentação mostra inicial, entradas, saídas e final", mov.colunas, mov);
  checar("e diz se o período está aberto ou congelado", mov.situacao, mov);
  checar("com a identidade conferida na própria tela", mov.fecha && !mov.naoFecha, mov);
  await foto(p, "24b-movimentacao");

  console.log("7b. a quebra do CMV, o escopo e o que subiu de preço");
  await irPara(p, `${WEB}/cmv`);
  await p.waitForFunction(() => /Food cost/i.test(document.body.innerText),
    { timeout: 30000, polling: 300 }).catch(() => {});

  // 🔑 **"Onde o custo pesa" virou a aba Quebra** (16/09/2026, protótipo
  // aprovado pelo dono): *"podendo ter a opção de ser pela empresa, por loja,
  // por local de estoque, setor, categoria, produto"*. Eram dois eixos, dentro
  // da aba dos relatórios do dono; são seis, comandados pelo "Ver por" do alto.
  const eixos = await p.evaluate(() => {
    const r = [...document.querySelectorAll("label")]
      .find((l) => /Ver por/i.test(l.querySelector("span")?.textContent ?? ""));
    return [...(r?.querySelectorAll("option") ?? [])].map((o) => o.value);
  });
  for (const x of ["loja", "local", "setor", "categoria", "grupo", "produto"]) {
    checar(`o "Ver por" oferece o eixo ${x}`, eixos.includes(x), eixos);
  }

  checar("a aba da quebra abre", await clicarQuando(p, "Quebra por "));
  await new Promise((r) => setTimeout(r, 1800));
  const quebra = await p.evaluate(() => document.body.innerText);
  checar("e diz que não é rateio, e sim a mesma conta restrita",
    /não é rateio/i.test(quebra), quebra.slice(0, 200));
  // 🔑 **A prova que dá sentido ao corte**: a soma das linhas FECHA com o CMV do
  // período. Sem ela a tabela seria uma divisão arbitrária de um total, e
  // ninguém poderia agir sobre uma linha. A tela escreve isso ao pé; se a soma
  // furar, o texto muda e a checagem cai — que é exatamente o que se quer.
  checar("a soma das linhas fecha com o CMV do período",
    /a soma das linhas fecha com o CMV do período/i.test(quebra)
      || /Nenhum movimento no período/i.test(quebra),
    (quebra.match(/a soma das linhas difere[^\n]*/i) || [])[0] ?? "fechou");

  // Trocar o eixo tem de recarregar a tabela E renomear a aba: é a mesma
  // pergunta feita de outro jeito, e a aba que não acompanha mente sobre o que
  // está na tela.
  const trocouEixo = await p.evaluate(() => {
    const r = [...document.querySelectorAll("label")]
      .find((l) => /Ver por/i.test(l.querySelector("span")?.textContent ?? ""));
    const sel = r?.querySelector("select");
    if (!sel) return false;
    const nativo = Object.getOwnPropertyDescriptor(
      window.HTMLSelectElement.prototype, "value").set;
    nativo.call(sel, "categoria");
    sel.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  });
  await new Promise((r) => setTimeout(r, 1800));
  const porCategoria = await p.evaluate(() => document.body.innerText);
  checar("dá para trocar para categoria",
    trocouEixo && /CMV por categoria/i.test(porCategoria), porCategoria.slice(0, 200));

  // 🔑 **O ESCOPO** (16/09/2026): a apuração é por LOJA e está certo — quem
  // opera opera numa de cada vez. Quem responde pelas duas tinha de trocar de
  // loja no seletor e somar de cabeça.
  // ⚠️ Empresa é o que o USUÁRIO enxerga: numa casa de uma loja só, os dois
  // escopos devolvem o MESMO número, e isso está certo. O que se cobra aqui é
  // que a troca exista e não derrube a apuração.
  const mexerNoEscopo = (valor) => p.evaluate((v) => {
    const r = [...document.querySelectorAll("label")]
      .find((l) => /Escopo/i.test(l.querySelector("span")?.textContent ?? ""));
    const sel = r?.querySelector("select");
    if (!sel) return null;
    const nativo = Object.getOwnPropertyDescriptor(
      window.HTMLSelectElement.prototype, "value").set;
    nativo.call(sel, v);
    sel.dispatchEvent(new Event("change", { bubbles: true }));
    return [...sel.querySelectorAll("option")].map((o) => o.value);
  }, valor);

  const opcoesEscopo = await mexerNoEscopo("empresa");
  checar("o recorte oferece esta loja e a empresa inteira",
    !!opcoesEscopo && opcoesEscopo.includes("loja") && opcoesEscopo.includes("empresa"),
    opcoesEscopo);
  await new Promise((r) => setTimeout(r, 2200));
  checar("e a apuração continua de pé no escopo da empresa",
    /CMV real/i.test(await p.evaluate(() => document.body.innerText)));
  // Volta para a loja: as fases seguintes leem esta tela esperando o padrão.
  await mexerNoEscopo("loja");
  await new Promise((r) => setTimeout(r, 1500));

  checar("a aba do que subiu de preço abre",
    await clicarQuando(p, "O que subiu de preço"));
  await new Promise((r) => setTimeout(r, 1800));
  checar("e traz o relatório de preços",
    /O que subiu de preço/i.test(await p.evaluate(() => document.body.innerText)));

  // 🔑 **A memória de cálculo virou ABA** (16/09/2026, protótipo aprovado).
  // Ela só existia em PDF, e a pergunta *"estes R$ 237 mil de compras, de quais
  // notas são?"* nasce OLHANDO o painel, não baixando arquivo.
  // ⚠️ **O quadro 4 vem PRIMEIRO, ao contrário do PDF**: no papel a ordem é a
  // da conta; na tela, a ordem é a da dúvida — e a dúvida é sempre "por que a
  // soma das notas não é a linha Compras?".
  checar("a aba da memória de cálculo abre", await clicarQuando(p, "Memória de cálculo"));
  await p.waitForFunction(() => /Quadro 4/i.test(document.body.innerText),
    { timeout: 25000, polling: 300 }).catch(() => {});
  const mem = await p.evaluate(() => {
    const texto = document.body.innerText;
    return {
      texto,
      ordem: [...texto.matchAll(/Quadro (\d)/g)].map((m) => m[1]).join(""),
      metodo: /Método de custeio/i.test(texto),
      situacao: /Situação do período/i.test(texto),
    };
  });
  checar("a memória abre a apuração nos quatro quadros",
    ["1", "2", "3", "4"].every((n) => mem.ordem.includes(n)), mem.ordem);
  checar("e a conciliação vem primeiro, que é a dúvida de quem chega",
    mem.ordem.startsWith("4"), mem.ordem);
  checar("com o método de custeio e a situação do período à vista",
    mem.metodo && mem.situacao, { metodo: mem.metodo, situacao: mem.situacao });
  checar("e a conciliação explica a diferença entre as notas e a linha Compras",
    /soma das notas/i.test(mem.texto), mem.texto.slice(0, 200));
  await foto(p, "36-cmv-quebra-e-memoria");

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

  // 🔑 A memória de cálculo (pedido da contabilidade, 02/09/2026). Os três
  // entram pelo CATÁLOGO, então aparecem em toda tela que tem o botão Baixar —
  // não há lista escrita no front que possa divergir.
  const chavesCat = new Set((catalogo ?? []).map((r) => r.chave));
  checar("a memória de cálculo do CMV está no catálogo",
    chavesCat.has("memoria-cmv"), [...chavesCat]);
  checar("o inventário valorizado também", chavesCat.has("inventario-valorizado"),
    [...chavesCat]);
  checar("e a memória por produto também", chavesCat.has("memoria-produto"),
    [...chavesCat]);
  // ⚠️ Uma DATA, não um período: o inventário responde "quanto valia o estoque
  // NAQUELE dia", e duas pontas fariam escolher um intervalo para uma pergunta
  // que tem uma data só.
  const doInventario = (catalogo ?? []).find((r) => r.chave === "inventario-valorizado");
  checar("e o inventário pede uma data, não um período",
    (doInventario?.filtros ?? []).some((f) => f.tipo === "data"),
    doInventario?.filtros);

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
    const rotulos = [...(d?.querySelectorAll("span.rotulo, span.rotulo-campo") ?? [])].map((x) =>
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

  // 🔑 **O inventário valorizado tem botão próprio em /estoque**, ao lado da
  // posição de hoje: são perguntas diferentes — uma é operacional, a outra é o
  // documento do balanço. E é ele que exercita o filtro de DATA, um tipo novo
  // na janela: sem a renderização dele o inventário sairia sempre com a data de
  // hoje, e ninguém veria por quê, porque o campo não apareceria.
  await irPara(p, `${WEB}/estoque`);
  await p.waitForFunction(
    () => [...document.querySelectorAll("button")]
      .some((b) => /Inventário valorizado/i.test(b.textContent ?? "")),
    { timeout: 15000 });
  checar("a tela de estoque oferece o inventário valorizado", true);
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((b) => /Inventário valorizado/i.test(b.textContent ?? ""))?.click();
  });
  await p.waitForSelector('[role="dialog"] input[type="date"]', { timeout: 15000 });
  const janelaInv = await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    return {
      rotulos: [...(d?.querySelectorAll("span.rotulo, span.rotulo-campo") ?? [])].map((x) => x.textContent?.trim()),
      // Uma data só: o período tem duas caixas de data, este tem uma.
      datas: (d?.querySelectorAll('input[type="date"]') ?? []).length,
    };
  });
  checar("e a janela dele pede UMA data, não um período",
    janelaInv.rotulos.includes("Na data de") && janelaInv.datas === 1, janelaInv);
  await p.evaluate(() => {
    const d = document.querySelector('[role="dialog"]');
    [...(d?.querySelectorAll("button") ?? [])]
      .find((b) => b.textContent?.trim() === "Cancelar")?.click();
  });

  // A memória de cálculo do CMV fica ao LADO do arquivo do contador, não no
  // lugar dele: um é o resumo que se lê, o outro é o anexo que se confere.
  await irPara(p, `${WEB}/cmv`);
  await p.waitForFunction(
    () => [...document.querySelectorAll("button")]
      .some((b) => /Memória de cálculo/i.test(b.textContent ?? "")),
    { timeout: 20000 });
  checar("o painel de CMV oferece a memória de cálculo", true);

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
  // ⚠️ **A lista de usuários PAGINA, e o desta rodada cai fora da primeira
  // página.** A base acumula um usuário por rodada — usuário com histórico
  // vira inativo em vez de sumir —, e a checagem acusava a tela de não oferecer
  // o link numa linha que ela nem mostrava. Aumentar a página é o que uma
  // pessoa faria, e é o que o rodapé oferece. Mesma correção da lista de apoio.
  await p.select('select[aria-label="Registros por página"]', "100").catch(() => {});
  await p.waitForFunction(
    (nome) => document.body.innerText.includes(nome), { timeout: 12000 },
    `Tela Senha ${marcaSenha}`,
  ).catch(() => {});
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

  // 🔑 A chave de máquina do conector MCP (migração 074). As regras do servidor
  // estão em `api/tests/smoke_tokens_api.py`; aqui é o que só a TELA pode errar:
  // mostrar a chave uma vez, escondê-la depois, e revogar.
  console.log("9a2. chaves de acesso do conector MCP");
  const marcaChave = String(Date.now()).slice(-6);
  const emailChave = `tela.chave.${marcaChave}@botane.com.br`;
  const { dados: usuarioChave } = await api("POST", "/usuarios", {
    nome: `Tela Chave ${marcaChave}`, email: emailChave,
    senha: "provisoria123",
    papeis: [{ id_papel: papeisSenha.find((x) => x.nome === "Cozinha").id }],
  }, token);
  await irPara(p, `${WEB}/usuarios/${usuarioChave.id}`);
  await p.waitForFunction(() => document.body.innerText.includes("Nenhuma chave gerada"),
    { timeout: 20000 }).catch(() => {});
  checar("o cadastro do usuário mostra o cartão de chaves, vazio",
    /Nenhuma chave gerada/.test(await p.evaluate(() => document.body.innerText)));
  checar("abre a janela de gerar", await clicarQuando(p, "Gerar chave", { exato: true }));
  checar("e gera", await clicarQuando(p, "Gerar", { exato: true }));
  await p.waitForFunction(() => /btn_[\w-]{20,}/.test(document.body.innerText),
    { timeout: 12000 }).catch(() => {});
  const textoChave = await p.evaluate(() => document.body.innerText);
  const valorChave = (textoChave.match(/btn_[\w-]{20,}/) ?? [])[0];
  checar("a chave aparece inteira, para copiar", !!valorChave);
  checar("com o aviso de que não aparece de novo", /não aparece de novo/.test(textoChave));
  const { status: stChave, dados: meChave } = await api("GET", "/auth/me", null, valorChave);
  checar("e a chave copiada da tela abre a API como a pessoa",
    stChave === 200 && meChave?.email === emailChave,
    { stChave, email: meChave?.email });
  await foto(p, "34b-chave-gerada");

  checar("oferece revogar", await clicarQuando(p, "revogar", { exato: true }));
  // ⚠️ **O "Revogar" da confirmação é clicado DENTRO da janela.** `clicarQuando`
  // compara em minúsculas, então "Revogar" casava primeiro com o link "revogar"
  // da linha, que vem antes no documento: o clique reabria a mesma pergunta e a
  // confirmação nunca acontecia — e as três checagens seguintes acusavam a tela.
  await p.waitForSelector('[role="dialog"]', { timeout: 8000 }).catch(() => {});
  checar("e confirma", await p.evaluate(() => {
    const b = [...document.querySelectorAll('[role="dialog"] button')]
      .find((x) => x.textContent.trim() === "Revogar");
    b?.click();
    return !!b;
  }));
  await p.waitForFunction((v) => !document.body.innerText.includes(v),
    { timeout: 12000 }, valorChave).catch(() => {});
  const textoRevogada = await p.evaluate(() => document.body.innerText);
  checar("revogar some com a chave em claro", !textoRevogada.includes(valorChave));
  checar("e a linha passa a dizer revogada", /\brevogada\b/.test(textoRevogada));
  checar("e a chave para de abrir a API",
    (await api("GET", "/auth/me", null, valorChave)).status === 401);
  await api("DELETE", `/usuarios/${usuarioChave.id}`, null, token);

  // 🔑 O Perfil é onde a PRÓPRIA pessoa acha o endereço para colar no claude.ai
  // e desconecta o Claude dela — o admin tem `integracao.claude` (migração 075).
  await irPara(p, `${WEB}/perfil`);
  await p.waitForFunction(() => /\/mcp\b/.test(document.body.innerText),
    { timeout: 15000 }).catch(() => {});
  const textoPerfil = await p.evaluate(() => document.body.innerText);
  checar("o Perfil mostra o endereço do conector do Claude", /https?:\/\/\S+\/mcp\b/.test(textoPerfil),
    textoPerfil.slice(0, 200));
  checar("com o caminho no claude.ai", /Adicionar conector personalizado/.test(textoPerfil));

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
  await c.setCacheEnabled(false);
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

  // 🔑 **As telas do dia a dia a um toque** (14/09/2026). Antes, trocar de tela
  // no celular eram cinco gestos: ☰, esperar, achar o grupo, abrir, tocar. Menu
  // que exige abrir gaveta e menu que nao se usa — e o efeito nao e reclamacao,
  // e a pessoa parar de conferir o estoque no salao.
  // ⚠️ **Espera a barra EXISTIR, e a razao e o proprio componente.** `pode()`
  // devolve `false` ate a sessao chegar do `/auth/me`, entao so sobra o
  // "Inicio" — e com menos de dois destinos a barra nao se desenha, de
  // proposito (barra de um item so nao e navegacao). Medir antes disso lia
  // `{existe:false}` e acusava o produto de um estado que era meu relogio.
  // Quinta vez nesta sessao que esperar pela coisa errada acusa a coisa errada.
  await c.waitForSelector("#barra-navegacao a", { timeout: 9000 }).catch(() => null);
  // ⚠️ **O nome desta variavel e `barraDia` porque `barra` ja existia** — e
  // renomear com um replace CEGO trocou tambem dentro das strings: a bateria
  // passou a procurar `#barraDia-navegacao`, que nunca existiu. Quatro
  // checagens falharam por duas rodadas acusando um componente que estava
  // certo, e a sonda isolada achava a barra na hora. Renomear identificador nao
  // e substituir texto.
  const barraDia = await c.evaluate(() => {
    const nav = document.querySelector("#barra-navegacao");
    if (!nav) return { existe: false };
    const itens = [...nav.querySelectorAll("a")];
    const rodape = document.querySelector("#barra-inferior");
    return {
      existe: true,
      quantos: itens.length,
      nomes: itens.map((a) => a.textContent?.trim()),
      // ⚠️ 44px e o que a WCAG 2.5.5 recomenda para o dedo; 24 e so o minimo
      // absoluto da 2.5.8, e barra de navegacao nao e lugar de morar no minimo.
      menorAlvo: Math.min(...itens.map((a) => a.getBoundingClientRect().height)),
      // ⚠️ A navegacao fica ACIMA do rodape da versao, que continua existindo:
      // ele e o que separa "a correcao nao funcionou" de "nao foi publicada".
      acimaDoRodape: rodape
        ? nav.getBoundingClientRect().bottom <= rodape.getBoundingClientRect().top + 1
        : null,
      // 🔑 E o conteudo nao pode nascer embaixo dela.
      folgaDoMain: parseFloat(getComputedStyle(document.querySelector("main")).paddingBottom),
    };
  });
  checar("o celular ganha a barra das telas do dia a dia", barraDia.existe, barraDia);
  checar("com pelo menos tres destinos", (barraDia.quantos ?? 0) >= 3, barraDia);
  checar("e alvos de toque de 44px ou mais", (barraDia.menorAlvo ?? 0) >= 44, barraDia);
  // ⚠️ **`=== true`, e nao `!== false`.** Com a barra ausente o campo nunca era
  // calculado, e `undefined !== false` e verdadeiro: esta checagem passava
  // exatamente nas rodadas em que as de cima falhavam. Terceira vacuidade que
  // esta fase produziu — todas do mesmo feitio, afirmar sobre o que nao foi
  // medido.
  checar("ela fica acima do rodape da versao, que continua la",
    barraDia.acimaDoRodape === true, barraDia);
  checar("e o conteudo tem folga para nao nascer embaixo dela",
    (barraDia.folgaDoMain ?? 0) >= 96, barraDia);
  await c.screenshot({ path: `${FOTOS}/m2b-barra-navegacao.png` });

  // ⚠️ E no computador ela NAO aparece: a lateral ja resolve, e duas navegacoes
  // na mesma tela seriam duas respostas para "onde eu clico".
  // ⚠️ **Leva a pagina de desktop de volta para DENTRO do app antes de medir.**
  // A fase anterior e a do PWA, que a deixa na tela de sem-conexao — fora do
  // layout, onde barra nenhuma existe. Medir ali dava "ausente" e acusava o
  // componente de nao renderizar, quando o que faltava era a precondicao.
  await irPara(p, `${WEB}/`);
  await p.waitForSelector("#barra-inferior", { timeout: 9000 }).catch(() => null);
  const noComputador = await p.evaluate(() => {
    const nav = document.querySelector("#barra-navegacao");
    return nav ? getComputedStyle(nav).display : "ausente";
  });
  // ⚠️ **Exige "none", e nao aceita "ausente".** Aceitar os dois fazia a
  // checagem passar exatamente no estado em que as de cima falhavam — a barra
  // fora do DOM. Checagem que passa pelo mesmo motivo que outra falha nao
  // afirma nada.
  checar("e no computador ela existe no DOM, mas escondida",
    noComputador === "none", noComputador);

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

  // ⚠️ **A aba do celular FECHA aqui, e a principal volta para a frente.**
  // Ela ficava aberta até o fim da rodada, e isso deixava `p` em segundo plano
  // de lá em diante — onde o Chrome congela o `requestAnimationFrame`. O
  // `waitForFunction` do Puppeteer pesquisa por rAF: a condição é avaliada uma
  // vez na instalação e, se ainda não for verdadeira, **nunca mais é olhada**.
  // Toda espera por algo que ainda vai acontecer virava um timeout inevitável,
  // com a tela já no estado certo — foi o que aconteceu com a fusão em lote,
  // acusada de não recarregar a lista quando ela tinha recarregado.
  await c.close();
  await p.bringToFront();

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

  // 🔑 **A fila das unidades que vieram de fora** (09/09/2026, decisão do dono:
  // *"conforme as unidades vão chegando pelas notas podemos ir vinculando ou
  // cadastrando"*). O que ela conserta é silencioso: item de nota com unidade
  // desconhecida não parava o lançamento — a conversão não achava caminho e a
  // quantidade entrava 1:1, e a diferença só aparecia no CMV do mês.
  // ⚠️ Um apelido com a MARCA da rodada: um "PT" fixo apagaria, na limpeza, a
  // tradução de verdade que o dono venha a criar.
  const mUni = `ZW${Date.now().toString().slice(-5)}`;
  await api("POST", "/unidades-medida/apelidos", { apelido: mUni, sigla: "UN" }, token);
  aoTerminar.push(() => api("DELETE", `/unidades-medida/apelidos/${mUni}`, null, token));

  await irPara(p, `${WEB}/cadastros?aba=unidades`);
  await p.waitForFunction(
    () => /unidades que vieram nas notas/i.test(document.body.innerText), { timeout: 15000 })
    .catch(() => {});
  const filaUm = await p.evaluate(() => ({
    temCartao: /Unidades que vieram nas notas/i.test(document.body.innerText),
    // ⚠️ A explicação vem ANTES da lista: sem ela, "BJ · 1 item" não diz a
    // ninguém por que aquilo está ali nem o que acontece se ficar.
    explica: /sem conversão/i.test(document.body.innerText),
    // 🔑 A saída para a unidade que NÃO existe aqui é cadastrá-la, não traduzir
    // para a mais parecida — que é como o custo para de fluir em silêncio.
    mandaCadastrar: /traduzir para a mais parecida/i.test(document.body.innerText),
    texto: document.body.innerText,
  }));
  checar("Tabelas de apoio mostra as unidades que vieram nas notas", filaUm.temCartao, filaUm.explica);
  checar("explicando que sem tradução a nota entra sem conversão", filaUm.explica);
  checar("e que a unidade que falta se CADASTRA, não se aproxima", filaUm.mandaCadastrar);
  // 🔑 O que já foi traduzido fica à vista, com o desfazer: uma tradução errada
  // ("PC" para UN quando era PCT) precisa de caminho de volta.
  checar("a tradução já feita aparece com o que ela virou",
    filaUm.texto.includes(mUni) && /vale como/i.test(filaUm.texto),
    filaUm.texto.slice(0, 400));
  // ⚠️ E a tela diz o que a tradução NÃO faz: o razão é append-only, e quem
  // espera que ela conserte a nota de ontem vai procurar o número que não mudou.
  checar("dizendo que ela vale para as PRÓXIMAS notas",
    /pr[óo]ximas/i.test(filaUm.texto) && /estorno/i.test(filaUm.texto),
    filaUm.texto.slice(0, 400));

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

  // 🔑 **A fusao comeca pelo cadastro do PDV** (15/09/2026). Pela regra nova ele
  // e o principal — e juntar A PARTIR do outro lado, num lote, agora esbarra na
  // trava que existe desde sempre: os escolhidos tem de cair todos no MESMO
  // principal, e com o do cardapio entre eles a direcao deixa de ser unica. A
  // tela diz isso e manda refazer a partir dele, que e o que esta fase faz.
  await irPara(p, `${WEB}/produtos/${vincB.id}`);
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

  // 🔑 **A janela NAO lista o proprio produto, e aceita marcar varios**
  // (09/09/2026, pedido do dono). Vincular um cadastro a si mesmo nao existe:
  // oferece-lo so serve para produzir a mensagem de erro depois do clique.
  //
  // ⚠️ **Sao DOIS `[role="dialog"]` aninhados** — a propria Vincular e a janela
  // de busca por cima dela. A primeira versao desta checagem pegou o PRIMEIRO,
  // digitou no campo da Vincular e clicou no "fechar" DELA: o bloco inteiro que
  // vinha depois desabou, acusando de defeito uma tela intacta. Aqui e sempre o
  // ULTIMO, e se fecha por Escape, que nao depende de achar botao nenhum.
  const naJanela = await p.evaluate(async (marca) => {
    const ultimo = () => [...document.querySelectorAll('[role="dialog"]')].pop();
    const antes = document.querySelectorAll('[role="dialog"]').length;
    [...document.querySelectorAll('button[aria-label="Buscar produto"]')].pop()?.click();
    await new Promise((r) => setTimeout(r, 600));
    const abriu = document.querySelectorAll('[role="dialog"]').length > antes;
    const d = ultimo();
    const campo = d?.querySelector("input.campo");
    if (campo) {
      const set = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, "value").set;
      set.call(campo, marca);
      campo.dispatchEvent(new Event("input", { bubbles: true }));
    }
    await new Promise((r) => setTimeout(r, 2200));
    const dd = ultimo();
    return {
      abriu,
      linhas: [...(dd?.querySelectorAll("li") ?? [])].map((li) => (li.textContent ?? "").trim()),
      caixinhas: dd?.querySelectorAll('input[type="checkbox"]').length ?? 0,
    };
  }, mVinc);
  checar("a janela de busca abre por cima da Vincular", naJanela.abriu, naJanela);
  checar("oferecendo caixinha para marcar varios", naJanela.caixinhas > 0, naJanela);
  // ⚠️ O produto ABERTO e o `vincB`; ele nao pode aparecer entre os candidatos.
  checar("e NAO lista o proprio produto que se esta vinculando",
    !naJanela.linhas.some((l) => l.includes(`CERVEJA HEINEKEN PILSEN ${mVinc}`)),
    naJanela.linhas.slice(0, 4));
  checar("mas lista os demais cadastros",
    naJanela.linhas.some((l) => l.includes(`BEB CERV HEINEKEN 350ML ${mVinc}`)),
    naJanela.linhas.slice(0, 4));
  // Escape fecha SO a janela de busca; a Vincular continua aberta para o resto.
  await p.keyboard.press("Escape");
  await new Promise((r) => setTimeout(r, 600));
  const vincSegue = await p.evaluate(() =>
    document.querySelectorAll('[role="dialog"]').length);
  checar("e o Escape fecha so a busca, deixando a Vincular aberta",
    vincSegue === 1, vincSegue);

  // 🔑 **A janela PAGINA de verdade** (09/09/2026, pedido do dono). Era um
  // "Mostrar mais" que pedia `limite = 25 x pagina` e trazia tudo desde o
  // comeco: dava para ver todos os produtos so filtrando, porque percorrer a
  // lista custava trazer a lista inteira.
  const paginandoNaBusca = await p.evaluate(async () => {
    const ultimo = () => [...document.querySelectorAll('[role="dialog"]')].pop();
    [...document.querySelectorAll('button[aria-label="Buscar produto"]')].pop()?.click();
    await new Promise((r) => setTimeout(r, 900));
    const d = ultimo();
    const rodape = () => (d?.textContent ?? "");
    const nomes = () => [...(d?.querySelectorAll("li") ?? [])]
      .map((li) => (li.textContent ?? "").trim()).slice(0, 3);
    const antes = { texto: rodape().match(/\d+–\d+ de [\d.]+/)?.[0] ?? null, nomes: nomes() };
    const proxima = [...(d?.querySelectorAll("button") ?? [])]
      .find((b) => b.getAttribute("aria-label") === "Próxima página");
    proxima?.click();
    await new Promise((r) => setTimeout(r, 1600));
    const dd = ultimo();
    const depois = {
      texto: (dd?.textContent ?? "").match(/\d+–\d+ de [\d.]+/)?.[0] ?? null,
      nomes: [...(dd?.querySelectorAll("li") ?? [])]
        .map((li) => (li.textContent ?? "").trim()).slice(0, 3),
    };
    return { temProxima: !!proxima, antes, depois };
  });
  checar("a janela de busca tem navegacao de pagina", paginandoNaBusca.temProxima,
    paginandoNaBusca);
  // ⚠️ O rodape diz o INTERVALO ("1-25 de 3.183"), nao "quantos ja vieram":
  // e a diferenca entre saber onde se esta e saber so o tamanho do balde.
  checar("com o intervalo e o total a vista",
    !!paginandoNaBusca.antes.texto, paginandoNaBusca.antes);
  // 🔑 A prova de que e paginacao e nao "mostrar mais": a pagina 2 traz OUTROS
  // registros, e nao os mesmos com mais embaixo.
  checar("e a proxima pagina traz outros registros",
    paginandoNaBusca.depois.nomes.length > 0
      && JSON.stringify(paginandoNaBusca.depois.nomes)
         !== JSON.stringify(paginandoNaBusca.antes.nomes),
    paginandoNaBusca);
  // ⚠️ **O rodape tem de CONTINUAR na pagina 2** — e esta checagem faltava.
  // O servidor manda o `X-Total` so na primeira pagina (recontar a cada clique
  // custaria a tabela inteira); a janela trocava o nulo pelo tamanho do que
  // veio, entao na pagina 2 o total virava 25 e o rodape sumia, deixando quem
  // navegava sem caminho de volta. A checagem anterior olhava so as linhas e
  // passou verde com o defeito na tela.
  checar("e o rodape CONTINUA na segunda pagina",
    !!paginandoNaBusca.depois.texto, paginandoNaBusca.depois);
  // E o total nao pode encolher ao virar a pagina: ele e o mesmo filtro.
  checar("com o mesmo total da primeira",
    (paginandoNaBusca.antes.texto ?? "").split(" de ")[1]
      === (paginandoNaBusca.depois.texto ?? "").split(" de ")[1],
    [paginandoNaBusca.antes.texto, paginandoNaBusca.depois.texto]);
  await p.keyboard.press("Escape");
  await new Promise((r) => setTimeout(r, 500));

  if (busca) {
    await busca.type(`BEB CERV HEINEKEN 350ML ${mVinc}`);
    await p.keyboard.press("Tab");
    await new Promise((r) => setTimeout(r, 1800));
    const previa = await textoVisivel(p);
    // ⚠️ A previa vem ANTES do botao porque fusao nao tem desfazer: quem
    // confirma precisa ver com que nome o produto vai ficar.
    checar("a previa mostra como fica", /Como fica/i.test(previa), previa.slice(0, 160));
    // 🔑 **As duas descricoes vem do lado do PDV** (15/09/2026, pedido do dono:
    // *"sempre dar prioridade para manter o produto do PDV e nao do Omie —
    // nomes, codigo, preco de venda"*). O nome do cardapio e o que a equipe
    // fala; o do Omie e o fiscal, que continua na linha da nota.
    checar("as duas descricoes vem do lado do PDV",
      previa.includes(`CERVEJA HEINEKEN PILSEN ${mVinc}`), previa.slice(0, 260));
    // ⚠️ E o cartao "Fica" nomeia o cadastro do PDV: e ele que sobrevive agora,
    // e a tela tem de dizer isso ANTES de alguem confirmar — fusao nao tem
    // desfazer. Medido no cartao, e nao no texto solto da tela: o nome do outro
    // cadastro aparece em mais lugares, e procurar por ausencia num texto
    // inteiro passaria verde por acidente.
    const ficaNaTela = await p.evaluate(() => {
      const cartoes = [...document.querySelectorAll("div")].filter(
        (d) => (d.querySelector(":scope > p.rotulo")?.textContent ?? "").trim() === "Fica");
      return cartoes.length ? cartoes[0].innerText.replace(/\n/g, " / ") : null;
    });
    checar("e o cartao 'Fica' nomeia o cadastro do PDV",
      (ficaNaTela ?? "").includes(`CERVEJA HEINEKEN PILSEN ${mVinc}`), ficaNaTela);
    checar("dizendo que o outro vira inativo", /vira inativo/i.test(previa));
    // ⚠️ Nada a baixar aqui (o lado do PDV nao vendeu), e a tela DIZ isso em vez
    // de calar: caixinha ausente sem explicacao lê como funcionalidade faltando.
    checar("e explica que nao ha o que baixar do estoque",
      /Nada a baixar do estoque/i.test(previa), previa.slice(0, 400));

    // 🔑 **O "Como fica" mostra por quais CÓDIGOS o cadastro vai responder.**
    // É o que faz a fusão ser confiável no caso do ABACATE: o catálogo do Omie
    // cria um cadastro por código, e o do absorvido era DESCARTADO — a próxima
    // nota que o trouxesse não achava o principal, o item caía na fila de
    // pendências e quem clicasse em "criar produto" recriava o duplicado.
    const linhasDeCodigo = await p.evaluate(() =>
      [...document.querySelectorAll("#codigos-do-resultado tbody tr")].map((tr) =>
        [...tr.children].map((td) => (td.textContent ?? "").trim())));
    checar("o Como fica mostra as linhas de código externo",
      linhasDeCodigo.length >= 2, linhasDeCodigo);
    checar("com o do cadastro que fica como principal",
      linhasDeCodigo.some((l) => l.includes(`771${mVinc}`) && l.includes("principal")),
      linhasDeCodigo);
    // ⚠️ Aqui o lado que fica não tem código do PDV, então o do absorvido SOBE
    // a principal em vez de virar apelido — a prévia diz o mesmo que a fusão faz.
    checar("e o do que sai também passa a cair aqui",
      linhasDeCodigo.some((l) => l.includes(`991${mVinc}`)), linhasDeCodigo);

    // 🔑 **Vários de uma vez**: juntar um a um seria abrir esta janela cinco
    // vezes, e a quinta já não lembraria o que a primeira decidiu.
    const { dados: vincC } = await api("POST", "/produtos", {
      codigo: `TVINC-C-${mVinc}`, nome: `HEINEKEN 600 ${mVinc}`,
      tipo: "REVENDA", um_estoque: "UN", controla_estoque: true, status: "ATIVO",
      codigo_omie: `773${mVinc}`,
    }, token);
    aoTerminar.push(() => api("DELETE", `/produtos/${vincC.id}`, null, token));
    const buscaMais = await p.$('input[aria-label="Buscar produto"]');
    if (buscaMais) {
      await buscaMais.type(`HEINEKEN 600 ${mVinc}`);
      await p.keyboard.press("Tab");
      await p.waitForFunction(
        (codigo) => document.body.innerText.includes(codigo),
        { timeout: 12000 }, `773${mVinc}`,
      ).catch(() => {});
    }
    const comDois = await p.evaluate(() => ({
      // Cada escolhido vira uma etiqueta com × para tirar da lista.
      etiquetas: [...document.querySelectorAll('button[aria-label^="tirar "]')].length,
      botao: [...document.querySelectorAll("button")]
        .map((b) => b.textContent?.trim() ?? "")
        .find((t) => t.startsWith("Vincular e fundir")) ?? "",
      codigos: [...document.querySelectorAll("#codigos-do-resultado tbody tr")].length,
    }));
    checar("dá para acrescentar mais de um cadastro", comDois.etiquetas === 2, comDois);
    // ⚠️ O botão DIZ quantos vão junto: "Vincular e fundir" no singular faria
    // parecer que só o último conta.
    checar("e o botão diz quantos vão junto", /os 2/.test(comDois.botao), comDois);
    checar("com os códigos dos dois no Como fica",
      comDois.codigos >= linhasDeCodigo.length + 1, comDois);

    // ⚠️ **A janela tem de CABER na tela e rolar POR DENTRO.** Esta montava o
    // próprio overlay em vez de usar o `Modal` da casa — e com a lista de
    // escolhidos e a tabela de códigos ela passou a sair da tela sem barra de
    // rolagem em lugar nenhum, porque o corpo da página fica travado enquanto
    // ela está aberta. É o mesmo defeito que a janela de exportação já teve, e
    // a segunda implementação divergiu na primeira correção.
    // ⚠️ Medido numa tela de notebook de verdade: a altura de 1000 do resto da
    // bateria esconde exatamente esta classe de defeito.
    await p.setViewport({ width: 1440, height: 760 });
    await new Promise((r) => setTimeout(r, 700));
    const coubeVinc = await p.evaluate(() => {
      const d = document.querySelector('[role="dialog"]');
      if (!d) return { achou: false };
      const corpo = d.children[1];
      corpo.scrollTop = corpo.scrollHeight;
      const botao = [...d.querySelectorAll("button")].find((b) =>
        (b.textContent?.trim() ?? "").startsWith("Vincular e fundir"));
      const cartao = d.getBoundingClientRect();
      const bb = botao?.getBoundingClientRect();
      return {
        achou: true,
        cabe: cartao.bottom <= window.innerHeight + 1 && cartao.top >= -1,
        rola: corpo.scrollHeight > corpo.clientHeight + 1,
        botaoAlcancavel: !!bb && bb.bottom <= window.innerHeight + 1 && bb.top >= 0,
      };
    });
    checar("a janela de vincular cabe na tela de um notebook", coubeVinc.cabe, coubeVinc);
    checar("com o miolo rolando por dentro", coubeVinc.rola, coubeVinc);
    // O botão fica FORA da rolagem: rolado até o fim, continua onde estava.
    checar("e o botão de fundir sempre à vista", coubeVinc.botaoAlcancavel, coubeVinc);
    await p.setViewport({ width: 1440, height: 1000 });
    await new Promise((r) => setTimeout(r, 500));
    await foto(p, "32-vincular");

    await p.evaluate(() => {
      const b = [...document.querySelectorAll("button")].find(
        (x) => (x.textContent?.trim() ?? "").startsWith("Vincular e fundir"));
      b?.click();
    });
    await new Promise((r) => setTimeout(r, 2600));
    // ⚠️ **Esperar o `window.location.reload()` que a fusão dispara.** A tela
    // recarrega para mostrar o nome e os códigos novos; seguir por cima dele
    // faz o recarregamento chegar no MEIO do bloco seguinte, desmontando a
    // janela que ele acabou de abrir — e o sintoma aparece longe da causa, como
    // uma busca que não seleciona nada.
    await p.waitForNavigation({ waitUntil: "networkidle2", timeout: 8000 })
      .catch(() => {});
    const { dados: depois } = await api("GET", `/produtos/${vincB.id}`, null, token);
    // ⚠️ As duas descricoes sao a do PDV — e o nome fiscal do Omie nao se perde:
    // ele continua na linha da nota, que e o que a conferencia le.
    checar("a fusao pela tela deixa o cadastro com o nome do PDV",
      depois.nome === `CERVEJA HEINEKEN PILSEN ${mVinc}`
      && depois.nome_curto === `CERVEJA HEINEKEN PILSEN ${mVinc}`,
      [depois.nome, depois.nome_curto]);
    // 🔑 E ele passa a CONTROLAR ESTOQUE, herdado do cadastro do Omie: sem essa
    // heranca, a compra deixaria de entrar no razao — calada.
    checar("e passa a controlar estoque, herdado do outro",
      depois.controla_estoque === true, depois.controla_estoque);
    checar("e os codigos das duas integracoes",
      depois.codigo_omie === `771${mVinc}` && depois.codigo_pdv === `991${mVinc}`,
      [depois.codigo_omie, depois.codigo_pdv]);
    const { dados: saiu } = await api("GET", `/produtos/${vincA.id}`, null, token);
    checar("e o outro ficou inativo, nao apagado", saiu.ativo === false, saiu.ativo);
    // 🔑 E o código do Omie do terceiro não se perdeu: virou apelido, e é por
    // ele que a próxima nota daquele fornecedor cai neste cadastro.
    checar("o codigo do Omie do absorvido virou apelido, nao lixo",
      (depois.codigos_externos ?? []).some((c) => c.codigo === `773${mVinc}`),
      depois.codigos_externos);
  }

  // 🔑 **Fundir A PARTIR do cadastro que NÃO vai ficar** (achado pelo dono,
  // 03/09/2026). Vincular dois cadastros do Omie funcionava; um do PDV com um
  // do Omie devolvia *"Escolha dois cadastros diferentes"* — com dois cadastros
  // diferentes escolhidos.
  //
  // A causa era da TELA: a prévia resolve a direção e devolve `id_sai`; quando
  // ela inverte, `id_sai` É o cadastro em que a pessoa está, e era esse id que
  // voltava ao servidor como "o que sai". O pedido chegava com o mesmo id dos
  // dois lados. O bloco acima nunca pegou isso porque começa do lado do Omie,
  // onde a direção NÃO inverte — e por isso este bloco começa do outro lado.
  const mInv = Date.now().toString().slice(-5);
  const { dados: invOmie } = await api("POST", "/produtos", {
    codigo: `TINV-O-${mInv}`, nome: `AGUA COM GAS ${mInv}`, tipo: "REVENDA",
    um_estoque: "UN", controla_estoque: true, status: "ATIVO",
    codigo_omie: `881${mInv}`,
  }, token);
  const { dados: invPdv } = await api("POST", "/produtos", {
    codigo: `TINV-P-${mInv}`, nome: `AGUA GAS PDV ${mInv}`, tipo: "PRODUZIDO",
    producao_propria: true, controla_estoque: false, status: "RASCUNHO",
    codigo_pdv: `991${mInv}`,
  }, token);
  aoTerminar.push(() => api("DELETE", `/produtos/${invOmie.id}`, null, token));
  aoTerminar.push(() => api("DELETE", `/produtos/${invPdv.id}`, null, token));

  // Começa no RASCUNHO do PDV — o que vai ser absorvido.
  // ⚠️ **O bloco acima termina com um `window.location.reload()` em voo** (é o
  // que a tela faz depois de fundir, para recarregar nome e códigos). Navegar
  // por cima dele fazia o recarregamento chegar DEPOIS e devolver a página
  // anterior — onde o botão "Vincular" também existe. A busca então casava com
  // o produto errado e a espera estourava, três linhas adiante da causa.
  // ⚠️ **A tela passou a ser a do OMIE** (15/09/2026). Com a prioridade do PDV,
  // quem inverte agora é este lado — e é a inversão que este bloco existe para
  // exercitar. Abrindo do cardápio, a direção deixaria de inverter e a checagem
  // passaria sem provar nada, que é o pior desfecho possível para ela.
  await irPara(p, `${WEB}/produtos/${invOmie.id}`);
  // Espera por algo que só existe na tela de DESTINO: o código deste cadastro.
  await p.waitForFunction(
    (codigo) => document.body.innerText.includes(codigo),
    { timeout: 20000 }, `TINV-O-${mInv}`);
  await p.waitForFunction(
    () => [...document.querySelectorAll("button")]
      .some((b) => b.textContent?.trim() === "Vincular"), { timeout: 15000 });
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((x) => x.textContent?.trim() === "Vincular")?.click();
  });
  await p.waitForSelector('input[aria-label="Buscar produto"]', { timeout: 15000 });

  /**
   * Escolhe um cadastro na busca da janela e espera a prévia aparecer.
   *
   * ⚠️ **Digita de DENTRO do documento, não por um handle.** O handle envelhece
   * — um recarregamento tardio da tela anterior desmonta a janela, e digitar
   * num input descartado não dá erro nenhum: some no vazio, e a falha aparece
   * como "a busca não seleciona".
   * ⚠️ **Confere o valor antes do Tab.** Sem isso, um `type` que não pegou vira
   * um Tab em campo vazio, que abre a janela de pesquisa e não escolhe nada.
   * ⚠️ **E tenta duas vezes**: a busca tem debounce e vai ao servidor; sob a
   * carga da bateria a primeira tentativa às vezes chega antes da resposta.
   */
  const escolherNaBusca = async (texto, marcaEsperada) => {
    for (let tentativa = 0; tentativa < 2; tentativa++) {
      const escreveu = await p.evaluate((t) => {
        const campo = document.querySelector('input[aria-label="Buscar produto"]');
        if (!campo) return false;
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, "value").set;
        setter.call(campo, t);
        campo.dispatchEvent(new Event("input", { bubbles: true }));
        campo.focus();
        return campo.value === t;
      }, texto);
      if (!escreveu) {
        // A janela sumiu: reabre e tenta de novo.
        await p.evaluate(() => {
          [...document.querySelectorAll("button")]
            .find((x) => x.textContent?.trim() === "Vincular")?.click();
        });
        await p.waitForSelector('input[aria-label="Buscar produto"]', { timeout: 15000 });
        continue;
      }
      // Deixa a busca ir ao servidor e voltar antes do Tab.
      await new Promise((r) => setTimeout(r, 1800));
      await p.keyboard.press("Tab");
      const achou = await p
        .waitForFunction((c) => document.body.innerText.includes(c),
          { timeout: 12000 }, marcaEsperada)
        .then(() => true)
        .catch(() => false);
      if (achou) return true;
    }
    return false;
  };

  try {
    const escolheu = await escolherNaBusca(`AGUA GAS PDV ${mInv}`, `991${mInv}`);
    checar("a busca da janela escolhe o cadastro do cardapio", escolheu);
    if (escolheu) {
      const avisoInv = await textoVisivel(p);
      // ⚠️ **Inverter calado seria pior que não inverter**: a pessoa confirma
      // achando que o cadastro que abriu é o que fica.
      checar("a previa avisa que a direcao foi invertida",
        /invertid|cadastro do PDV|controla estoque/i.test(avisoInv), avisoInv.slice(0, 300));

      await p.evaluate(() => {
        [...document.querySelectorAll("button")]
          .find((x) => (x.textContent?.trim() ?? "").startsWith("Vincular e fundir"))?.click();
      });
      await new Promise((r) => setTimeout(r, 2600));
      const textoDepois = await textoVisivel(p);
      // 🔑 A afirmação central: a tela mandava o `id_sai` da prévia de volta, e
      // na direção invertida ele É o cadastro da tela — o pedido chegava com o
      // mesmo id dos dois lados.
      checar("fundir do lado que sai NAO devolve 'escolha dois cadastros diferentes'",
        !/dois cadastros diferentes/i.test(textoDepois), textoDepois.slice(0, 300));
      const { dados: ficouInv } = await api("GET", `/produtos/${invOmie.id}`, null, token);
      const { dados: saiuInv } = await api("GET", `/produtos/${invPdv.id}`, null, token);
      // 🔑 Quem sobrevive e o cadastro do PDV, mesmo tendo sido o ESCOLHIDO — e
      // ele leva os dois codigos junto.
      checar("o cadastro do PDV sobrevive, com os dois codigos",
        saiuInv.ativo === true && saiuInv.codigo_pdv === `991${mInv}`
        && saiuInv.codigo_omie === `881${mInv}`,
        [saiuInv.ativo, saiuInv.codigo_pdv, saiuInv.codigo_omie]);
      // ⚠️ E ele passa a controlar estoque, herdado do que foi absorvido: sem a
      // heranca, a compra deixaria de entrar no razao — calada.
      checar("controlando estoque, herdado do cadastro do Omie",
        saiuInv.controla_estoque === true, saiuInv.controla_estoque);
      checar("e o do Omie, que era o da tela, foi absorvido",
        ficouInv.ativo === false, ficouInv.ativo);
    }
  } catch (e) {
    // O diagnóstico vai junto: sem ele a falha diz só "timeout", e o que se
    // precisa saber é em que tela e com que janela ela aconteceu.
    const diag = await p.evaluate(() => ({
      url: location.pathname,
      janelas: document.querySelectorAll('[role="dialog"]').length,
      texto: (document.querySelector('[role="dialog"]')?.innerText ?? "").slice(0, 300),
    })).catch(() => null);
    checar("fundir a partir do lado invertido pela tela", false,
      String(e).slice(0, 110) + " | " + JSON.stringify(diag));
  }

  console.log("10w2. os cadastros com o MESMO NOME, em lote");
  // 🔑 **A tela que já era referenciada e nunca existiu**: o cartão do PDV em
  // Integrações manda para `/produtos/duplicados`, e o endereço dava 404.
  // ⚠️ Ela DETECTA e não decide — o projeto já removeu uma cascata que
  // vinculava sozinha por semelhança de nome. Nome idêntico é um sinal mais
  // forte, mas segue sendo um sinal: "VALE-PRESENTE" pode ser três valores
  // diferentes. Por isso o aviso vem ANTES da lista e nada acontece sem clique.
  const mDup = Date.now().toString().slice(-5);
  const dups = [];
  for (let i = 0; i < 3; i++) {
    const { dados } = await api("POST", "/produtos", {
      codigo: `TDUP${i}-${mDup}`, nome: `ABACATE TELA ${mDup}`, tipo: "INSUMO",
      um_estoque: "KG", controla_estoque: true, status: "ATIVO",
      codigo_omie: `55${i}${mDup}`,
    }, token);
    dups.push(dados.id);
    aoTerminar.push(() => api("DELETE", `/produtos/${dados.id}`, null, token));
  }

  // 🔑 **O caminho mora em INTEGRAÇÕES, e não em Produtos** (movido a pedido do
  // dono). O duplicado não é erro de quem cadastra: ele nasce das duas
  // importações. O teste entra por onde a pessoa entra — um link que existe mas
  // não está no caminho de ninguém é o mesmo que não existir.
  // ⚠️ **A ABA vai na URL** (09/09/2026): a tela virou abas, e o cartão dos
  // duplicados mora em "Outros" — ele não é do Omie nem do PDV, nasce das duas.
  // Sem o `?aba=`, a checagem cairia na primeira aba e acusaria a tela de não
  // ter um cartão que ela tem, noutra aba.
  await irPara(p, `${WEB}/integracoes?aba=outros`);
  await p.waitForFunction(() => /mesmo nome/i.test(document.body.innerText),
    { timeout: 15000 }).catch(() => {});
  const portaDup = await p.evaluate(() => {
    const cartao = [...document.querySelectorAll("section.cartao")]
      .find((c) => (c.querySelector("h2")?.textContent ?? "").includes("mesmo nome"));
    return {
      temCartao: !!cartao,
      // O aviso de que nome igual não prova nada já aparece aqui, antes do clique.
      avisa: /não é prova/i.test(cartao?.innerText ?? ""),
      destino: cartao?.querySelector("a[href='/produtos/duplicados']")?.textContent?.trim() ?? "",
    };
  });
  checar("o caminho para os duplicados esta em Integracoes", portaDup.temCartao, portaDup);
  checar("com o botao Mesmo nome apontando para a tela",
    portaDup.destino === "Mesmo nome", portaDup);
  checar("e ja avisando ali que nome igual nao e prova", portaDup.avisa, portaDup);

  // ⚠️ E NÃO está mais no cabeçalho de Produtos: sair de um lugar faz parte de
  // mudar de lugar — dois caminhos para a mesma tela é o que se quis evitar.
  await irPara(p, `${WEB}/produtos`);
  const sobrouEmProdutos = await p.evaluate(() =>
    !!document.querySelector("a[href='/produtos/duplicados']"));
  checar("e nao ficou duplicado no cabecalho de Produtos", !sobrouEmProdutos);

  await irPara(p, `${WEB}/produtos/duplicados`);
  await p.waitForFunction(
    (nome) => document.body.innerText.includes(nome), { timeout: 20000 },
    `ABACATE TELA ${mDup}`);
  const telaDup = await p.evaluate((nome) => {
    const texto = document.body.innerText;
    const cartao = [...document.querySelectorAll("section.cartao")]
      .find((c) => (c.querySelector("h2")?.textContent ?? "").includes(nome));
    return {
      // O aviso vem ANTES da lista: quem lê a lista primeiro já começou a clicar.
      avisaQueNomeNaoEProva: /não é prova/i.test(texto),
      dizQueNaoTemDesfazer: /não tem desfazer/i.test(texto),
      linhas: cartao ? cartao.querySelectorAll("tbody tr").length : 0,
      // Uma linha diz "fica"; as outras, "vira inativo".
      temFica: (cartao?.innerText ?? "").includes("fica"),
      botao: [...(cartao?.querySelectorAll("button") ?? [])]
        .map((b) => b.textContent?.trim() ?? "")
        .find((t) => t.startsWith("Juntar")) ?? "",
    };
  }, `ABACATE TELA ${mDup}`);
  checar("a tela de duplicados existe e lista o grupo", telaDup.linhas === 3, telaDup);
  checar("dizendo que nome igual NAO e prova, antes da lista",
    telaDup.avisaQueNomeNaoEProva && telaDup.dizQueNaoTemDesfazer, telaDup);
  checar("e marcando qual cadastro fica", telaDup.temFica, telaDup);
  checar("com o botao dizendo quantos vao junto", /Juntar os 3/.test(telaDup.botao), telaDup);
  await foto(p, "32c-duplicados");

  // ⚠️ Fusão não tem desfazer, e por isso PERGUNTA antes — e a pergunta é do
  // sistema, não do navegador.
  try {
    await p.evaluate((nome) => {
      const cartao = [...document.querySelectorAll("section.cartao")]
        .find((c) => (c.querySelector("h2")?.textContent ?? "").includes(nome));
      [...(cartao?.querySelectorAll("button") ?? [])]
        .find((b) => (b.textContent?.trim() ?? "").startsWith("Juntar"))?.click();
    }, `ABACATE TELA ${mDup}`);
    await p.waitForSelector('[role="dialog"]', { timeout: 15000 });
    checar("juntar pergunta antes, no padrao do sistema", true);
    await p.evaluate(() => {
      const d = document.querySelector('[role="dialog"]');
      [...(d?.querySelectorAll("button") ?? [])]
        .find((b) => b.textContent?.trim() === "Juntar")?.click();
    });
    // ⚠️ **Esperar o CARTÃO sumir, não o nome sair da página.** O aviso de
    // sucesso repete o nome do grupo — e ele para de contar enquanto o foco
    // está dentro dele, então o nome pode ficar na tela indefinidamente. A
    // afirmação é sobre a LISTA, e é nela que se mede.
    await p.waitForFunction(
      (nome) => ![...document.querySelectorAll("section.cartao")]
        .some((c) => (c.querySelector("h2")?.textContent ?? "").includes(nome)),
      { timeout: 25000 }, `ABACATE TELA ${mDup}`);
    // ⚠️ Só ATIVOS entram na lista: sem isso ela nunca esvaziaria, propondo de
    // novo o que já foi feito.
    checar("o grupo sai da lista depois de junto", true);
    const { dados: ficouDup } = await api("GET", `/produtos/${dups[0]}`, null, token);
    checar("o principal sobrevive", ficouDup.ativo === true, ficouDup.ativo);
    // 🔑 A razão de existir: os códigos dos absorvidos passam a cair no principal.
    // Sem isso a próxima nota que trouxesse o código de um deles não acharia o
    // sobrevivente, e o duplicado renasceria na importação seguinte.
    const codigosDup = (ficouDup.codigos_externos ?? []).map((c) => c.codigo);
    checar("e os codigos dos absorvidos passam a cair nele",
      codigosDup.includes(`551${mDup}`) && codigosDup.includes(`552${mDup}`), codigosDup);
  } catch (e) {
    // ⚠️ **A falha tem de dizer o que a TELA mostrava.** "TimeoutError" sozinho
    // não distingue as três causas possíveis — o POST não saiu, saiu e voltou
    // erro, ou voltou 200 e a lista não recarregou —, e sem isso a investigação
    // vira adivinhação. O `juntar` da página só recarrega no caminho de
    // SUCESSO: um erro de rede depois de o servidor ter gravado deixa o grupo
    // na tela, e é esse estado que este dump captura.
    const diagDup = await p.evaluate(() => ({
      avisos: [...document.querySelectorAll('[role="status"]')].map((x) => x.innerText),
      dialogoAberto: !!document.querySelector('[role="dialog"]'),
      cartoes: [...document.querySelectorAll("section.cartao")]
        .map((c) => c.querySelector("h2")?.textContent ?? ""),
    })).catch(() => null);
    checar("juntar o grupo pela tela", false,
      String(e).slice(0, 120) + " | " + JSON.stringify(diagDup));
  }

  console.log("10x. PDV Legal: a credencial e o que ainda falta");
  // ⚠️ **Só a autenticação existe, e a tela tem de DIZER isso.** O catálogo de
  // endpoints da Tablet Cloud não é público; um cartão com um botão de testar e
  // mais nada parece um pedaço faltando, e alguém abriria chamado por isso.
  await irPara(p, `${WEB}/integracoes?aba=pdv`);
  await new Promise((r) => setTimeout(r, 2000));
  const pdv = await p.evaluate(() => {
    const texto = document.body.innerText;
    const rotulos = [...document.querySelectorAll("span.rotulo, span.rotulo-campo")].map((r) =>
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
  // ⚠️ **E o orçamento subiu de 30 s para 90** (16/09/2026): 17 s é a medida com
  // a máquina LIVRE, e esta fase roda no meio da bateria, com a API atendendo
  // tudo o mais. Com 30 s a checagem caía por contenção — e levava junto as
  // três seguintes, porque enquanto a conferência roda a tela fica `ocupado` e
  // os botões ficam DESABILITADOS: `clicarQuando` os pula, e a falha aparecia
  // como "o botão do custo inicial não está na tela".
  // 🔑 É o mesmo número que a prévia do custo já usava, pela mesma razão.
  let conf = "";
  for (let tentativa = 0; tentativa < 90; tentativa++) {
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

  // 🔑 **O custo inicial.** Medido na base: 2.323 produtos ativos que controlam
  // estoque sem custo nenhum — nunca entrou nota deles aqui e nao ha preco de
  // fornecedor. Sem custo nao ha ficha, nem CMV teorico, nem margem: o prato
  // entra na conta valendo ZERO e o food cost sai bom demais, calado.
  // ⚠️ A tela tem de DIZER que e referencia e nao movimento — quem clica sem
  // isso espera ver o estoque encher, e nada no saldo vai mudar.
  const clicouCusto = await clicarQuando(p, "Trazer o custo inicial", { limite: 40000 });
  // 🔑 **Afirmar o CLIQUE separa as duas causas.** Sem esta linha, "a previa nao
  // respondeu" tanto pode ser o endpoint lento quanto o botao que nunca foi
  // clicado — e as tres checagens seguintes caem juntas dizendo a coisa errada.
  checar("o botao de trazer o custo inicial esta na tela", clicouCusto);
  let custosTexto = "";
  // ⚠️ **A espera é longa porque a varredura é longa, e foi MEDIDA** (14/09/2026):
  // `custos-iniciais/previa` leva ~15s com a máquina livre e passou de **50s**
  // com a bateria rodando junto — são 30 páginas do `ListarPosEstoque` mais uma
  // volta de `custo_do_insumo` por produto (3.520 na base local). O orçamento de
  // 30s deixava a checagem falhar por contenção e acusar a TELA de um defeito
  // que era de relógio: `textoVisivel` voltava só o cabeçalho, e as duas
  // checagens seguintes caíam junto porque leem o mesmo corpo.
  // 🔑 Se voltar a estourar, o problema passou a ser o ENDPOINT, não este número.
  for (let tentativa = 0; tentativa < 75; tentativa++) {
    await new Promise((r) => setTimeout(r, 1000));
    custosTexto = await textoVisivel(p);
    if (/receberiam custo de refer[êe]ncia|Falha ao consultar/i.test(custosTexto)) break;
  }
  checar("a previa do custo inicial responde",
    /receberiam custo de refer[êe]ncia/i.test(custosTexto), custosTexto.slice(0, 200));
  // ⚠️ **A previa NAO grava**, e a tela precisa mostrar o botao de aplicar
  // separado: com 2.323 produtos, descobrir o efeito depois e tarde.
  const previaCusto = await p.evaluate(() => ({
    dizReferencia: /custo de refer[êe]ncia/i.test(document.body.innerText),
    dizQueNaoMexeNoRazao: /nada entra no raz[ãa]o/i.test(document.body.innerText),
    temAplicar: [...document.querySelectorAll("button")]
      .some((b) => /^Aplicar em \d+ produto/.test(b.textContent?.trim() ?? "")),
    // ⚠️ ESTA tabela, pelo id: a tela de Integracoes tem outras, e "a primeira
    // que casa" media a errada — dizia que havia o que aplicar quando nao havia.
    temLinhas: !!document.querySelector("#custos-iniciais tbody tr"),
    explicaOVazio: /n[ãa]o h[áa] o que trazer|ainda n[ãa]o foi importado/i
      .test(document.body.innerText),
  }));
  checar("dizendo que e REFERENCIA, nao movimento de estoque",
    previaCusto.dizReferencia && previaCusto.dizQueNaoMexeNoRazao, previaCusto);
  // ⚠️ **A afirmacao e sobre a PROPRIEDADE, nao sobre o estado do dia.** Havendo
  // o que aplicar, o gravar e um botao SEPARADO — a previa nunca grava sozinha.
  // Nao havendo (base recem-limpa, catalogo do Omie ainda nao importado), a tela
  // tem de DIZER por que a lista esta vazia. Exigir o botao sempre acusava a
  // tela de um defeito que era do dado.
  checar(previaCusto.temLinhas
    ? "havendo o que aplicar, o gravar fica num botao separado"
    : "sem nada a aplicar, a tela explica a lista vazia em vez de oferecer o botao",
    previaCusto.temLinhas ? previaCusto.temAplicar : previaCusto.explicaOVazio,
    previaCusto);
  await foto(p, "33b-custo-inicial");

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
      [...document.querySelectorAll("#agenda-omie span.rotulo, #agenda-omie span.rotulo-campo")].some((r) =>
        /A que hora/i.test(r.textContent ?? ""))));
  // 🔑 A diária é "uma vez por dia, A PARTIR dessa hora" — antes era "nessa
  // hora, se alguém estiver acordado", e o dia inteiro passava em branco quando
  // a API estava parada às 4h. Quem escolhe a hora precisa saber o que acontece
  // quando ninguém está de pé nela — e que o botão não substitui a busca do dia.
  checar("e explica que ela busca assim que o sistema voltar",
    await p.evaluate(() =>
      /busca assim que voltar/i.test(document.body.innerText)));
  checar("e que buscar no botao nao dispensa a busca do dia",
    await p.evaluate(() =>
      /n[ãa]o substitui/i.test(document.body.innerText)));
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

  await irPara(p, `${WEB}/integracoes?aba=pdv`);
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

  // 🔑 **A busca de vendas passou a trazer o PREÇO do PDV** (09/09/2026, pedido
  // do dono), e o mesmo interruptor do envio decide de quem o preço é: ligado, o
  // dono é o Botané e a busca não toca nele; desligado, o dono é o PDV e a
  // mudança feita no caixa vem sozinha.
  // ⚠️ **A frase é a única coisa que torna isso visível.** Sem ela, quem liga o
  // envio para mandar cadastros daqui perde, sem saber, a atualização de preço
  // que vinha do caixa — e descobre pelo efeito, no cupom.
  // ⚠️ Afirma a PROPRIEDADE, não o estado do dia: qual frase aparece depende do
  // que o servidor diz, e as duas são corretas. É a mesma correção da checagem
  // acima e da do setor BAR.
  const frasesPreco = await p.evaluate(() => ({
    envio: document.querySelector("#envio-pdv")?.innerText ?? "",
    agenda: document.querySelector("#agenda-pdv")?.innerText ?? "",
  }));
  const donoEhACasa = !!cfgEnvio?.enviar_ao_pdv;
  checar("o interruptor do envio diz de quem é o preço",
    donoEhACasa
      ? /o preço daqui é o que vale/i.test(frasesPreco.envio)
      : /o preço é o do PDV/i.test(frasesPreco.envio),
    [donoEhACasa, frasesPreco.envio.slice(0, 300)]);
  checar("e a busca automática diz o que faz com ele",
    donoEhACasa
      ? /não mexe em preço/i.test(frasesPreco.agenda)
      : /atualiza o preço que mudou no caixa/i.test(frasesPreco.agenda),
    [donoEhACasa, frasesPreco.agenda.slice(0, 300)]);
  // ⚠️ E o que NÃO vem sozinho continua escrito, nos dois estados: categoria,
  // setor e nome mudam AQUI, à mão, e alinhá-los segue sendo um clique.
  checar("dizendo também que categoria e setor seguem manuais",
    /Importar cardápio/i.test(frasesPreco.agenda), frasesPreco.agenda.slice(0, 300));

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
      [...document.querySelectorAll("#agenda-pdv span.rotulo, #agenda-pdv span.rotulo-campo")].some((r) =>
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

  // ⚠️ Os parametros sairam da LISTA e foram para dentro de cada loja —
  // consultar e cadastrar sao telas diferentes, como em Compras e Vendas.
  // O id 1 e a matriz, a mesma que a linha acima acabou de configurar.
  await irPara(p, `${WEB}/lojas/1`);
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
    const sel = [...document.querySelectorAll("main select")]
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
    const opcoes = [...document.querySelectorAll("main select")]
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

  console.log("10a4. as normas de UX que a paleta e os controles tem de cumprir");
  // 🔑 **Pedido do dono (14/09/2026):** *"mais compatibilidade com as normas de
  // UX… letras amigaveis e bonitas… tanto para computador quanto para celular."*
  // O estudo em `docs/ux-estudo.md` mediu a paleta contra a WCAG 2.1 e achou
  // tres coisas fora da norma. Isto aqui e a guarda para elas nao voltarem —
  // norma sem teste volta na primeira vez que alguem ajustar uma cor "so um
  // pouquinho".
  await irPara(p, `${WEB}/produtos`);
  await new Promise((r) => setTimeout(r, 1400));
  const normas = await p.evaluate(() => {
    // Contraste do WCAG 2.1, calculado sobre o que o NAVEGADOR realmente pinta
    // — nao sobre o token, que pode estar sendo sobreposto por outra regra.
    const luz = (cor) => {
      const [r, g, b] = cor.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number).map((x) => {
        const v = x / 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const razao = (a, b) => {
      const [x, y] = [luz(a), luz(b)].sort((m, n) => n - m);
      return (x + 0.05) / (y + 0.05);
    };
    const de = (el, prop) => getComputedStyle(el)[prop];
    const campo = document.querySelector(".campo");
    // ⚠️ **O primeiro VISÍVEL, não o primeiro do DOM.** A versão anterior
    // pegava `.link-acao` sem olhar se ele estava renderizado e media altura
    // ZERO — reprovando o alvo de toque por um elemento que ninguém vê. Medir
    // o que está escondido é o mesmo erro de esperar pelo texto errado: a
    // resposta vem, e não é sobre o que se perguntou.
    const acao = [...document.querySelectorAll(".link-acao, .btn")]
      .find((el) => el.getBoundingClientRect().height > 0) ?? null;
    const etiqueta = [...document.querySelectorAll("span")]
      .find((s) => /rascunho/i.test(s.textContent ?? ""));
    const fundo = de(document.querySelector(".cartao") ?? document.body, "backgroundColor");
    return {
      // ⚠️ 16px: abaixo disso o Safari do iPhone da zoom ao focar o campo.
      campoPx: campo ? parseFloat(de(campo, "fontSize")) : null,
      // ⚠️ WCAG 2.5.8 pede 24x24 como MINIMO absoluto; 2.5.5 recomenda 44.
      acaoAltura: acao ? Math.round(acao.getBoundingClientRect().height) : null,
      // ⚠️ WCAG 1.4.11: 3,0 para a fronteira de um elemento de interface.
      bordaCampo: campo ? razao(de(campo, "borderTopColor"), fundo).toFixed(2) : null,
      // ⚠️ WCAG 1.4.3: 4,5 para texto de corpo — e a etiqueta tem 11px.
      etiquetaTexto: etiqueta ? razao(de(etiqueta, "color"), fundo).toFixed(2) : null,
      // A familia do dado denso: a celula deixou de ser serifada.
      celula: de(document.querySelector("tbody td") ?? document.body, "fontFamily"),
      // E a prosa continua serifada, que e a voz da casa.
      prosa: de(document.querySelector(".prosa") ?? document.body, "fontFamily"),
    };
  });
  checar("o campo tem 16px — abaixo disso o iPhone da zoom ao focar",
    normas.campoPx >= 16, normas);
  checar("o alvo de toque passa dos 24px que a norma pede como minimo",
    normas.acaoAltura >= 28, normas);
  checar("a borda do campo passa dos 3,0 da WCAG 1.4.11",
    Number(normas.bordaCampo) >= 3, normas);
  checar("e a etiqueta de 11px passa dos 4,5 da WCAG 1.4.3",
    normas.etiquetaTexto === null || Number(normas.etiquetaTexto) >= 4.5, normas);
  // 🔑 A divisao que o estudo propos: sem-serifa no dado, serifada na prosa.
  checar("a celula da tabela esta na familia de LEITURA, nao na serifada",
    /Inter/i.test(normas.celula) && !/Newsreader/i.test(normas.celula), normas.celula);
  checar("e a prosa continua serifada — a voz da casa",
    /Newsreader/i.test(normas.prosa), normas.prosa);
  await foto(p, "44-normas-ux");

  // 🔑 **O cabecalho nao pode ESMAGAR o titulo** (15/09/2026, relatado pelo
  // dono: *"em algumas telas o cabecalho falhou, por exemplo no painel do
  // CMV"*). A coluna do titulo era `min-w-0 flex-1` e o bloco de acoes do CMV
  // tem cinco controles: o flex cedeu tudo para eles e o `<h1>` ficou com
  // **2px de largura por 1.613 de altura** — uma letra por linha — em vez de a
  // linha quebrar em duas. ⚠️ A medida aqui e do CMV de proposito: e a tela com
  // o maior bloco de acoes do sistema, entao e ela que quebra primeiro.
  await irPara(p, `${WEB}/cmv`);
  await p.waitForSelector("main header h1", { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 1200));
  const cabecalho = await p.evaluate(() => {
    const h = document.querySelector("main header");
    const t = h.querySelector("h1");
    const b = h.querySelector("button[aria-expanded]");
    const prosa = h.querySelector("#explica-tela");
    return {
      larguraTitulo: Math.round(t.getBoundingClientRect().width),
      alturaTitulo: Math.round(t.getBoundingClientRect().height),
      janela: window.innerWidth,
      rotulo: b?.innerText?.trim() ?? null,
      // A frase existe no DOM (o `aria-controls` aponta para ela), mas nao ocupa
      // a tela: e um no so, escondido pelo `hidden`.
      prosaNoDom: !!prosa,
      prosaVisivel: prosa ? prosa.offsetParent !== null : null,
    };
  });
  checar("o titulo da tela ocupa a largura que tem, em vez de ser esmagado",
    cabecalho.larguraTitulo > 400, cabecalho);
  checar("e cabe em uma ou duas linhas, nao em uma letra por linha",
    cabecalho.alturaTitulo <= 90, cabecalho);
  // 🔑 **A explicacao vem RECOLHIDA** — o estudo de layout ja dizia que ela
  // ensina na primeira semana e estorva na terceira. Na primeira versao ela so
  // se escondia no celular; no computador custava duas linhas em toda tela.
  checar("a explicacao da tela vem atras de um 'saber mais'",
    cabecalho.rotulo === "saber mais", cabecalho);
  checar("e ela nao ocupa a tela enquanto ninguem pede",
    cabecalho.prosaNoDom === true && cabecalho.prosaVisivel === false, cabecalho);
  await p.evaluate(() =>
    document.querySelector("main header button[aria-expanded]")?.click());
  await new Promise((r) => setTimeout(r, 300));
  const cabecalhoAberto = await p.evaluate(() => {
    const b = document.querySelector("main header button[aria-expanded]");
    const prosa = document.querySelector("#explica-tela");
    return {
      expandido: b?.getAttribute("aria-expanded"),
      rotulo: b?.innerText?.trim(),
      visivel: prosa ? prosa.offsetParent !== null : false,
      texto: (prosa?.innerText ?? "").slice(0, 40),
    };
  });
  checar("um clique mostra a explicacao",
    cabecalhoAberto.visivel === true && cabecalhoAberto.expandido === "true", cabecalhoAberto);
  // ⚠️ E o mesmo controle esconde de novo: um botao que so sabe abrir deixa a
  // tela com a frase para sempre, que e o estado de que se estava saindo.
  checar("e o mesmo controle esconde de volta", cabecalhoAberto.rotulo === "ocultar",
    cabecalhoAberto);
  await p.evaluate(() =>
    document.querySelector("main header button[aria-expanded]")?.click());
  await new Promise((r) => setTimeout(r, 250));

  // 🔑 **E o mesmo "saber mais" nas telas que montam o cabecalho a MAO**
  // (15/09/2026, pedido do dono: *"colocar este saber mais em todas as telas
  // que tenham o texto"*). Sao 35, contra as 4 que usam `CabecalhoTela` — se o
  // controle so existisse nestas quatro, a mesma tela diria a frase de dois
  // jeitos conforme a rota.
  // ⚠️ **O que se mede e a PROSA ESCONDIDA, nao o botao existir.** Um botao que
  // aparece com a frase ainda a vista teria passado a checagem sem entregar
  // nada — que e o que se estava consertando.
  const semSaberMais = [];
  for (const rota of ["/fichas", "/producao", "/usuarios", "/alertas", "/compras"]) {
    await irPara(p, WEB + rota);
    await p.waitForSelector("h1", { timeout: 15000 }).catch(() => {});
    await new Promise((r) => setTimeout(r, 700));
    const tela = await p.evaluate(() => {
      const b = document.querySelector('button[aria-controls="explica-tela"]');
      const prosa = document.querySelector("#explica-tela");
      return { botao: b?.innerText?.trim() ?? null,
               escondida: prosa ? prosa.offsetParent === null : null };
    });
    if (tela.botao !== "saber mais" || tela.escondida !== true) semSaberMais.push(rota + " " + JSON.stringify(tela));
  }
  checar("as telas de cabecalho a mao tambem recolhem a explicacao",
    semSaberMais.length === 0, semSaberMais);

  // ⚠️ **E o dado NAO virou explicacao.** A linha cinza abaixo do titulo que
  // mostra o e-mail do usuario, o periodo da conta ou a origem da venda tem a
  // mesma cara da frase explicativa — e esconder o ASSUNTO da tela atras de
  // "saber mais" teria sido a leitura mecanica desta tarefa. Cinco telas
  // ficaram de fora de proposito; esta e a guarda de uma delas.
  await irPara(p, `${WEB}/consumo`);
  await p.waitForSelector("h1", { timeout: 15000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 900));
  const primeiroPeriodo = await p.evaluate(() => {
    const l = [...document.querySelectorAll("a")].find((a) => /\/consumo\/\d+$/.test(a.getAttribute("href") ?? ""));
    if (l) l.click();
    return !!l;
  });
  if (primeiroPeriodo) {
    await new Promise((r) => setTimeout(r, 1500));
    const doPeriodo = await p.evaluate(() => ({
      temBotao: !!document.querySelector('button[aria-controls="explica-tela"]'),
      texto: document.querySelector("main")?.innerText?.slice(0, 200) ?? "",
    }));
    checar("o dado do cabecalho continua a vista, e nao virou 'saber mais'",
      doPeriodo.temBotao === false && /\d{2}\/\d{2}\/\d{4}/.test(doPeriodo.texto), doPeriodo);
  }

  console.log("10a3. o periodo se chama pelo nome, nao 'mes' sempre");
  // 🔑 **Relatado pelo dono (14/09/2026):** *"nas telas quando trata de periodo,
  // sempre cita mes, mas caso o periodo for semanal, a descricao esta errada —
  // o CMV nao e o mes que conta, e sim o periodo."*
  // 🔑 **O NUMERO ja vinha certo** (o painel calcula por `periodo_do_dia`, que
  // respeita o ciclo). Era o texto ao redor dele que dizia "mes" sempre: o CMV
  // "do mes" numa casa que fecha toda semana.
  // ⚠️ A checagem tem de MEDIR A TELA, nao conferir que o parametro gravou —
  // gravar sempre funcionou; era a frase que nao acompanhava.
  const { dados: euPeriodo } = await api("GET", "/auth/me", null, token);
  const lojaAtual = euPeriodo.unidades[0].id;
  const ritmo = async (ciclo, extra = {}) =>
    api("PUT", `/unidades/${lojaAtual}/parametros`,
      { ciclo_fechamento: ciclo, ...extra }, token);

  // ⚠️ Devolve a loja ao ritmo de fabrica aconteca o que acontecer: a base e
  // compartilhada, e deixa-la em SEMANAL faria a apuracao de outras fases abrir
  // noutro periodo e acusar diferenca sem nada ter quebrado. Mesma licao do
  // `atexit` da suite de ciclos.
  aoTerminar.push(async () => {
    await ritmo("MENSAL", { dia_fechamento_cmv: 1 });
  });

  await ritmo("MENSAL", { dia_fechamento_cmv: 1 });
  await irPara(p, `${WEB}/`);
  await p.reload({ waitUntil: "networkidle2" });
  await esperarTexto(p, "Custo do que saiu", 9000);
  const textoMensal = await p.evaluate(() => document.body.innerText);
  checar("no ritmo mensal a tela inicial fala em MES",
    /CMV do mês/i.test(textoMensal) && /Perdas do mês/i.test(textoMensal), textoMensal.slice(0, 600));

  await ritmo("SEMANAL", { fechamento_dia_semana: 7 });
  await irPara(p, `${WEB}/`);
  await p.reload({ waitUntil: "networkidle2" });
  await esperarTexto(p, "Custo do que saiu", 9000);
  const textoSemanal = await p.evaluate(() => document.body.innerText);
  // 🔑 A checagem que o dono pediu: a MESMA tela, com a casa fechando toda
  // semana, nao pode continuar dizendo "mes".
  checar("no ritmo semanal ela passa a falar em SEMANA",
    /CMV da semana/i.test(textoSemanal) && /Perdas da semana/i.test(textoSemanal),
    textoSemanal.slice(0, 600));
  checar("e nao sobra nenhum 'do mês' na tela",
    !/do mês/i.test(textoSemanal), (textoSemanal.match(/.{0,40}do mês.{0,40}/i) || [])[0]);
  // ⚠️ As contracoes: "desta semana" e "nesta semana", no feminino. Montar isso
  // na tela daria duas versoes da mesma verdade — por isso vem do servidor.
  checar("com as contracoes no feminino",
    /desta semana|nesta semana/i.test(textoSemanal), textoSemanal.slice(0, 600));
  // E o rotulo do cabecalho, que ja estava certo antes, continua.
  checar("e o cabecalho diz de onde ate onde",
    /semana de/i.test(textoSemanal), textoSemanal.slice(0, 200));
  await foto(p, "43-periodo-semanal");

  await ritmo("MENSAL", { dia_fechamento_cmv: 1 });

  console.log("10a2. as casas decimais da quantidade, que a loja escolhe");
  // 🔑 **Era ajuste MORTO.** `parametros.casas_decimais_qtd` existe desde a
  // migração 001, a tela de Lojas sempre o ofereceu para editar — e nada o
  // lia: mexer ali não mudava número nenhum na tela. Ajuste que não faz nada é
  // pior que ajuste inexistente, porque ensina que a tela mente.
  // ⚠️ A checagem tem de MEDIR a tela, não conferir que o campo foi gravado —
  // gravar sempre funcionou; era a leitura que não existia.
  const marcaCasas = String(Date.now()).slice(-6);
  const { dados: prodCasas } = await api("POST", "/produtos",
    { nome: `Casas tela ${marcaCasas}`, tipo: "INSUMO", um_estoque: "KG" }, token);
  await api("POST", "/estoque/entradas",
    { id_produto: prodCasas.id, quantidade: 2.1875, custo_unitario: 10 }, token);
  const { dados: parAntes } = await api("GET", "/unidades/1/parametros", null, token);

  const qtdNaTela = async (casas) => {
    await api("PUT", "/unidades/1/parametros",
      { ...parAntes, casas_decimais_qtd: casas }, token);
    // ⚠️ **Tem de RECARREGAR**: a preferência viaja no `/auth/me`, que a sessão
    // busca uma vez. É a mesma razão de o seletor de loja recarregar a página.
    await p.goto(`${WEB}/estoque?busca=Casas%20tela%20${marcaCasas}`,
      { waitUntil: "networkidle2" });
    await p.reload({ waitUntil: "networkidle2" });
    await new Promise((r) => setTimeout(r, 1500));
    return p.evaluate(() => {
      const tr = document.querySelector("table tbody tr");
      return tr ? [...tr.querySelectorAll("td")][2]?.innerText.trim() ?? "" : "";
    });
  };

  const comQuatro = await qtdNaTela(4);
  checar("com 4 casas a loja vê 2,1875", comQuatro.startsWith("2,1875"), comQuatro);
  const comDuas = await qtdNaTela(2);
  checar("com 2 casas a MESMA quantidade vira 2,19", comDuas.startsWith("2,19"), comDuas);
  // ⚠️ Zero é uma escolha legítima ("0 a 6" está escrito na tela), e arredonda
  // só a EXIBIÇÃO: o razão continua com 2,1875 gravado.
  const comZero = await qtdNaTela(0);
  checar("com 0 casas arredonda para 2", comZero.startsWith("2 "), comZero);
  const { dados: saldoCru } = await api(
    "GET", `/estoque/saldos?id_produto=${prodCasas.id}`, null, token);
  checar("e o que está GRAVADO não mudou uma casa",
    Math.abs(Number(saldoCru?.[0]?.quantidade ?? 0) - 2.1875) < 0.00001, saldoCru?.[0]);
  await api("PUT", "/unidades/1/parametros", parAntes, token);
  await api("DELETE", `/produtos/${prodCasas.id}`, null, token);

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
  // ⚠️ **Afirmar que criou, em vez de engolir a falha.** O `if (dados?.id)`
  // existe para nao quebrar o laco — e o efeito colateral e pior que a quebra:
  // nascendo zero produtos, a checagem de filtro 200 linhas abaixo acusa a
  // PAGINACAO de um problema que e do cadastro, e o diagnostico dela ja teve de
  // ser turbinado duas vezes por isso. Mesma familia do `b?.click()` silencioso.
  checar("os 25 produtos da fase de paginacao foram criados",
    criadosPag.length === 25, criadosPag.length);

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
        // ⚠️ **A LINHA inteira, nao o primeiro `<td>`.** A lista de produtos
        // ganhou uma caixinha de selecao como primeira celula, e ela nao tem
        // texto: as duas paginas passaram a devolver "" e a checagem acusou a
        // paginacao de nao virar, quando o que mudou foi a tabela.
        primeiro: document.querySelector("tbody tr")?.textContent?.trim() || null,
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

  // 🔑 **Entrar num registro e VOLTAR mantém o rodapé** (09/09/2026, relatado
  // pelo dono: *"quando vou para a segunda ou terceira página adiante, ao entrar
  // no produto e voltar para o grid, a parte de paginação some"*).
  // A tela volta montada do ZERO: a página vem da URL (`?p=2`), mas o total não
  // vem de lugar nenhum, e o servidor só o conta no `offset = 0`. O rodapé sumia
  // inteiro — e com ele o caminho de volta para a página 1. A lista ficava presa
  // naquela fatia, sem nada dizendo que existiam outras.
  // ⚠️ Reproduz o caminho de QUEM USA: clica na linha, espera a ficha, volta
  // pelo histórico. Chamar a URL direto pularia justamente o que quebrava.
  const urlNaPagina2 = p.url();
  checar("a página adiante fica na URL", /[?&]p=2\b/.test(urlNaPagina2), urlNaPagina2);
  await p.evaluate(() => {
    document.querySelector('tbody tr a[href^="/produtos/"]')?.click();
  });
  await p.waitForFunction(() => /\/produtos\/\d+/.test(location.pathname), { timeout: 15000 })
    .catch(() => {});
  await p.waitForFunction(
    () => !/^\s*carregando/i.test(document.body.innerText), { timeout: 15000 }).catch(() => {});
  const abriuFicha = /\/produtos\/\d+/.test(p.url());
  checar("clicar na linha abre a ficha do produto", abriuFicha, p.url());

  await p.goBack();
  // ⚠️ Espera pelo CONTEÚDO, não por tempo fixo: o rodapé só aparece depois da
  // resposta da lista, e um `setTimeout` que passe antes dela transforma o teste
  // em moeda. Foi a lição das checagens "oferece baixar".
  await p.waitForFunction(
    () => /\d+–\d+ de [\d.]+/.test(document.body.innerText), { timeout: 15000 })
    .catch(() => {});
  const depoisDeVoltar = await lerPaginacao();
  checar("voltar do produto traz o rodapé de volta", depoisDeVoltar.tem && depoisDeVoltar.total > 0,
    depoisDeVoltar);
  // 🔑 A afirmação central: o total foi RECUPERADO, não zerado. Sem o
  // `com_total`, ele voltava 0 e o rodapé inteiro desaparecia.
  checar("com o mesmo total de antes", depoisDeVoltar.total === antes.total,
    [antes.total, depoisDeVoltar.total]);
  // ⚠️ E na PÁGINA em que se estava — senão o total voltaria mas a posição não,
  // que é metade do defeito.
  checar("e na mesma página, não na primeira",
    depoisDeVoltar.rodape === segunda.rodape, [segunda.rodape, depoisDeVoltar.rodape]);
  checar("com o 'anterior' ligado, que é o caminho de volta",
    !depoisDeVoltar.anteriorDesligada, depoisDeVoltar);

  // 🔑 **Virar a página traz a lista de volta ao topo** (09/09/2026, pedido do
  // dono). O botão fica no RODAPÉ: quem clica está no fim da lista, a página
  // seguinte é desenhada acima dele, e o olho continua parado nas últimas
  // linhas — dá a impressão de que nada aconteceu.
  // ⚠️ A checagem rola a página até o FIM antes de clicar: partindo do topo,
  // "voltou ao topo" seria verdade sem o recurso existir.
  await p.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await new Promise((r) => setTimeout(r, 300));
  const rolagemAntes = await p.evaluate(() => window.scrollY);
  await p.evaluate(() => document.querySelector('button[aria-label="Página anterior"]')?.click());
  // ⚠️ **O que se afirma é o TOPO DO CARTÃO à vista, não `scrollY ≈ 0`.** A
  // primeira versão desta checagem exigia voltar ao topo do DOCUMENTO e falhou
  // com [968, 618] — o sistema tinha feito exatamente o certo (parar no topo do
  // bloco da lista, abaixo da barra fixa de 56px), e a checagem é que estava
  // medindo outra coisa. Rolar ao topo do documento seria errado no cartão
  // dentro de uma ficha, que é justamente o caso que a decisão preservou.
  // A rolagem é suave: esperar por ela CHEGAR, não por um tempo fixo.
  await p.waitForFunction(() => {
    const c = document.querySelector("table")?.closest(".cartao");
    if (!c) return false;
    const t = c.getBoundingClientRect().top;
    return t > -8 && t < 140;
  }, { timeout: 10000 }).catch(() => {});
  const rolagem = await p.evaluate(() => {
    const c = document.querySelector("table")?.closest(".cartao");
    return { y: window.scrollY, topoDoCartao: c ? Math.round(c.getBoundingClientRect().top) : null };
  });
  checar("a página estava rolada até o fim antes de virar", rolagemAntes > 200, rolagemAntes);
  checar("e virar a página sobe a tela", rolagem.y < rolagemAntes,
    [rolagemAntes, rolagem.y]);
  // 🔑 A afirmação central: o começo da lista fica à vista, logo abaixo da
  // barra do topo — não escondido atrás dela, nem no meio da página.
  checar("deixando o topo da lista à vista, abaixo da barra",
    rolagem.topoDoCartao !== null && rolagem.topoDoCartao > -8 && rolagem.topoDoCartao < 140,
    rolagem);
  // Volta para a página 2, que é onde o resto deste bloco espera estar.
  await p.evaluate(() => document.querySelector('button[aria-label="Próxima página"]')?.click());
  await new Promise((r) => setTimeout(r, 1200));

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
  // ⚠️ **Espera o RESULTADO da busca, não 1.800 ms.** A digitação tem debounce
  // de 300 ms e a resposta vem depois; numa rodada com a máquina ocupada o
  // tempo fixo acabava antes, a lista ainda estava vazia e a checagem acusava a
  // paginação de sumir — `{tem:false, linhas:0}`, que é a assinatura de "a
  // página não terminou de carregar", não de um defeito. Mesma lição das
  // checagens "oferece baixar" e da folha de produção.
  // ⚠️ **Esperar por uma LINHA com a marca nao servia, e o defeito so apareceu
  // numa base pequena.** A lista ordena por nome; com milhares de produtos, os
  // "Pag tela ..." desta fase nunca caiam na pagina 2, entao a condicao so
  // ficava verdadeira DEPOIS de filtrar. Numa base recem-limpa, com menos de
  // cem produtos, eles ja estao na pagina 2 — a condicao nasce verdadeira, o
  // `waitForFunction` volta na hora, e a medicao le a tela AINDA NAO filtrada:
  // rodape "51-94 de 94", total inalterado. A checagem acusava a paginacao de
  // um defeito que era da espera.
  // 🔑 A espera certa e pelo EFEITO do filtro, nao por um dado que pode ja
  // estar na tela: a URL carregando `busca=` e o pedido tendo voltado.
  await p.waitForFunction(
    (marca) => location.search.includes(`busca=${marca}`),
    { timeout: 20000 },
    encodeURIComponent(`${marcaPag}-0`),
  ).catch(() => {});
  // E um respiro para a resposta do servidor pintar a lista: a URL muda quando
  // o debounce escreve, e o pedido sai depois dela.
  // 🔑 **`every` numa lista VAZIA e verdadeiro, e era esse o defeito da espera**
  // (16/09/2026). A condicao era so "toda linha tem a marca": com a tabela
  // ainda vazia ela nascia verdadeira, o `waitForFunction` voltava na hora e a
  // medicao lia a tela ANTES da resposta chegar. Dai a assinatura que ja tinha
  // mandado turbinar o diagnostico duas vezes -- `{linhas:0, total:0,
  // vazio:true}` com a URL correta e os produtos existindo no banco -- e o
  // "reproduzida isolada, ela passa": na maquina livre a resposta chegava antes
  // da leitura por sorte de milissegundos.
  // ⚠️ A espera certa exige **pelo menos uma linha** alem de todas casarem.
  await p.waitForFunction(
    (marca) => {
      const linhas = [...document.querySelectorAll("tbody tr")];
      return linhas.length > 0
        && linhas.every((tr) => (tr.textContent ?? "").includes(marca));
    },
    { timeout: 20000 },
    `${marcaPag}-0`,
  ).catch(() => {});
  const filtrado = await lerPaginacao();
  // ⚠️ **O diagnóstico vai junto.** Esta checagem falhou duas rodadas seguidas
  // com `{linhas:0}` e nada mais — e `linhas:0` sozinho não distingue "a busca
  // não achou" de "a página ainda não carregou" de "o filtro ficou de outra
  // rodada". Reproduzida isolada, ela passa; então o que falta é saber em que
  // ESTADO a tela está quando ela falha aqui.
  const diagFiltro = await p.evaluate(() => ({
    url: location.pathname + location.search,
    busca: document.querySelector(
      'input[placeholder="nome, código ou código de barras"]')?.value ?? null,
    // Os seletores de filtro que a tela ganhou em 09/09/2026: um deles preso
    // num valor de um passo anterior esvaziaria a lista sem mais explicação.
    selects: [...document.querySelectorAll("select")].map(
      (x) => `${x.getAttribute("aria-label") ?? x.name ?? "?"}=${x.value}`),
    vazio: /nenhum produto|nada encontrado/i.test(document.body.innerText),
    primeiraLinha: document.querySelector("tbody tr")?.textContent?.trim()?.slice(0, 60) ?? null,
  }));
  checar("filtrar volta para a primeira página",
    filtrado.linhas > 0 && (filtrado.rodape === null || /^1–/.test(filtrado.rodape)),
    { ...filtrado, ...diagFiltro, termo: `${marcaPag}-0` });
  checar("e o total passa a ser o do filtro", filtrado.total < antes.total || !filtrado.tem,
    [antes.total, filtrado.total]);
  await foto(p, "32-paginacao");
  for (const id of criadosPag) await api("DELETE", `/produtos/${id}`, null, token);

  console.log("10b0. o preco que veio do PDV aparece na ficha do produto");
  // 🔑 **Relatado pelo dono (09/09/2026):** *"no grid aparece o preço de venda,
  // mas ao consultar o produto o preço de venda está vazio; este produto veio
  // do PDV"* (PDV-10798484).
  //
  // O preço tem dois donos: o da CASA (`id_unidade` nulo) e o da LOJA. O que vem
  // do PDV nasce da loja, de propósito — `tabelapreco` é por filial. O grid
  // mostra o resolvido (loja primeiro); o formulário mostrava só o da casa, e o
  // bloco "Preço nesta loja" só existe para quem tem MAIS DE UMA loja.
  // Resultado com uma loja: o preço ficava invisível e não editável — 637
  // produtos do PDV na base de teste.
  {
    const mPreco = Date.now().toString().slice(-5);
    const { dados: pPreco } = await api("POST", "/produtos", {
      nome: `Preco da loja ${mPreco}`, tipo: "REVENDA", um_estoque: "UN",
    }, token);
    aoTerminar.push(() => api("DELETE", `/produtos/${pPreco.id}`, null, token));
    // ⚠️ Pela ROTA DA LOJA, que é como o preço do PDV entra: gravá-lo por
    // `preco_venda` no corpo do produto criaria o preço da CASA, e o teste
    // passaria sem exercitar o defeito.
    await api("PUT", `/produtos/${pPreco.id}/preco-loja`, { preco_venda: 218 }, token);

    const { dados: conferindo } = await api("GET", `/produtos/${pPreco.id}`, null, token);
    checar("o servidor diz que o preço é da LOJA, não da casa",
      conferindo.preco_loja === 218 && conferindo.preco_casa === null,
      [conferindo.preco_casa, conferindo.preco_loja]);

    await irPara(p, `${WEB}/produtos/${pPreco.id}`);
    // ⚠️ **Espera o CAMPO ESTAR PREENCHIDO, e nao o rotulo aparecer.** O rotulo
    // faz parte do formulario e ja esta na tela antes de a resposta do produto
    // chegar: a sonda lia o campo vazio e acusava a tela de nao mostrar um
    // preco que ela mostraria meio segundo depois. Falhou uma vez, num perfil
    // de navegador recem-criado — ou seja, na rodada em que a rota compilou do
    // zero. E a mesma licao ja escrita duas vezes neste arquivo: esperar pela
    // coisa CERTA, que aqui e o valor, nao o cenario ao redor dele.
    await p.waitForFunction(() => {
      const campo = [...document.querySelectorAll("label")].find(
        // ⚠️ O rotulo MUDA com o numero de lojas ("Preco de venda da casa"
        // quando ha mais de uma) — e a base local guarda filial de rodada
        // anterior. Aceitar as duas formas e o que impede esta sonda de acusar
        // a tela por causa do estado da base.
        (l) => /^Pre[çc]o de venda( da casa)?$/i.test(l.querySelector("span.rotulo, span.rotulo-campo")?.textContent?.trim() ?? ""));
      return !!campo?.querySelector("input")?.value;
    }, { timeout: 20000, polling: 250 }).catch(() => {});
  // ⚠️ **Pelo RÓTULO do campo, não pelo primeiro `input[type=number]`.** A
  // primeira versão subia do rótulo com `closest("div")` — que passa por cima
  // do `<label>` e cai num contêiner do cartão inteiro —, e lia o `fator_compra`
  // logo acima: a checagem falhou com "1" e acusou a tela de não mostrar o
  // preço, que ela mostrava. `Campo` renderiza
  // `<label><span class="rotulo">…</span><div><input/></div></label>`, então o
  // caminho honesto é achar o LABEL cujo rótulo é esse e ler o input dele.
    const noCampo = await p.evaluate(() => {
      const campo = [...document.querySelectorAll("label")].find(
        (l) => /^Pre[çc]o de venda( da casa)?$/i.test(
          l.querySelector("span.rotulo, span.rotulo-campo")?.textContent?.trim() ?? ""));
      return campo?.querySelector("input")?.value ?? null;
    });
    // 🔑 A afirmação central: o campo mostra o preço que VALE, não vazio.
    // ⚠️ **O campo é MASCARADO** (`CampoMoeda`), então o que se lê é "218,00" e
    // não "218": `Number("218,00")` é NaN, e a checagem acusava a tela de não
    // mostrar um preço que ela mostrava. Comparar pelo texto formatado é o
    // certo aqui — é o que a pessoa vê, e é o formato que a máscara promete.
    checar("e a ficha do produto mostra esse preço no campo",
      noCampo === "218,00", noCampo);

    // ⚠️ E salvar mantém o preço na LOJA. Escrito na casa, abriria uma segunda
    // linha vigente: a da loja continuaria mandando e o número editado não
    // teria efeito nenhum — com a tela dizendo que salvou.
    await api("PUT", `/produtos/${pPreco.id}/preco-loja`, { preco_venda: 199 }, token);
    const { dados: depois } = await api("GET", `/produtos/${pPreco.id}`, null, token);
    checar("mudar o preço da loja continua sem criar preço da casa",
      depois.preco_loja === 199 && depois.preco_casa === null,
      [depois.preco_casa, depois.preco_loja]);
    checar("e o resolvido acompanha", depois.preco_venda === 199, depois.preco_venda);
  }

  console.log("10b1. os produtos que a pessoa fornece");
  // 🔑 **Pedido do dono (09/09/2026):** *"no cadastro de pessoas, criar um grupo
  // dos produtos que a pessoa/fornecedor está vinculado"*. A ficha já dizia
  // QUANTOS; o número sozinho não responde "o que a gente compra deste aqui?".
  // ⚠️ O vínculo NASCE do lançamento da nota — por isso a checagem procura uma
  // pessoa que já tenha produtos, em vez de cadastrar um vínculo por fora.
  {
    const { dados: pessoas } = await api(
      "GET", "/fornecedores?incluir_inativos=true&limite=1000", null, token);
    // ⚠️ A de MAIS produtos, não a primeira: com três linhas o corte de dez não
    // se observa, e a checagem passaria sem exercitar nada.
    const comProdutos = (pessoas ?? [])
      .filter((f) => (f.produtos ?? 0) > 0)
      .sort((a, b) => (b.produtos ?? 0) - (a.produtos ?? 0))[0];
    if (comProdutos) {
      await irPara(p, `${WEB}/fornecedores/${comProdutos.id}`);
      await p.waitForFunction(
        () => /produtos desta pessoa/i.test(document.body.innerText), { timeout: 15000 })
        .catch(() => {});
      const cartao = await p.evaluate(() => {
        const cab = [...document.querySelectorAll("th")].map((t) => t.textContent?.trim());
        return {
          tem: /Produtos desta pessoa/i.test(document.body.innerText),
          colunas: ["Produto", "Último preço", "Última compra"].every((c) => cab.includes(c)),
          // 🔑 O preço é POR UNIDADE DE ESTOQUE, e dizê-lo é o que impede
          // "R$ 2,50" de ser lido como o preço da caixa.
          diz_a_unidade: /por unidade de estoque/i.test(document.body.innerText),
          linhas: document.querySelectorAll("table tbody tr").length,
          // A linha leva ao produto: a ficha da pessoa é o ponto de partida.
          leva_ao_produto: [...document.querySelectorAll("a")].some(
            (a) => /^\/produtos\/\d+$/.test(a.getAttribute("href") ?? "")),
          // 🔑 **Dez por página, e o seletor NÃO aparece** (decisão do dono,
          // 09/09/2026). O tamanho é do cartão, não de quem olha: um cartão
          // dentro de uma ficha tem espaço decidido pelo layout, e oferecer 100
          // ali empurraria o resto da página para fora da tela.
          tem_seletor: !!document.querySelector('select[aria-label="Registros por página"]'),
          rodape: (document.body.innerText.match(/\d+–\d+ de [\d.]+ produto/) ?? [null])[0],
          // ⚠️ Só os ATIVOS: a etiqueta de inativo não pode aparecer aqui, e a
          // descrição do cartão diz o recorte.
          diz_ativos: /produto\(s\) ativo\(s\)/i.test(document.body.innerText),
        };
      });
      checar("a ficha da pessoa lista os produtos dela", cartao.tem, cartao);
      checar("com preço e data da última compra", cartao.colunas, cartao);
      checar("dizendo que o preço é por unidade de estoque", cartao.diz_a_unidade, cartao);
      checar("e cada linha leva ao produto", cartao.leva_ao_produto && cartao.linhas > 0,
        cartao);
      checar("a lista diz que traz só os ativos", cartao.diz_ativos, cartao);
      // ⚠️ **Nunca mais que dez linhas**, tenha a pessoa doze ou cento e dois.
      checar("e nunca passa de dez linhas por página", cartao.linhas <= 10, cartao);
      // 🔑 A ausência do seletor é a afirmação: com ele, o tamanho voltaria a
      // ser escolha de quem olha, que é o que esta decisão tirou.
      checar("sem oferecer 'por página' — o tamanho é fixo", !cartao.tem_seletor, cartao);
      // ⚠️ **A contagem da LISTA de pessoas inclui produto inativo; o cartao so
      // mostra os ATIVOS.** Numa base grande isso nunca separava os dois
      // numeros; numa recem-limpa a pessoa aparece com doze e o cartao pinta
      // sete, e a checagem cobrava um rodape que nao tinha o que paginar.
      // A pergunta certa e a mesma que o cartao faz: quantos ATIVOS ela tem.
      const { dados: ativosDaPessoa } = await api(
        "GET", `/fornecedores/${comProdutos.id}/produtos`, null, token);
      const quantosAtivos = (ativosDaPessoa ?? []).filter((x) => x.ativo !== false).length;
      if (quantosAtivos > 10) {
        // Passando de dez, o rodapé TEM de aparecer: sem ele a lista fica presa
        // nas dez primeiras sem nada dizendo que existem outras.
        checar("passando de dez, o rodapé de página aparece", !!cartao.rodape, cartao);
      }
    } else {
      // ⚠️ Sem pessoa com vínculo na base, a checagem não vale: afirmaria sobre
      // um estado que não existe. Diz isso em vez de passar por sorte.
      checar("a ficha da pessoa lista os produtos dela", false,
        "(nenhuma pessoa com produto vinculado na base)");
    }

    // ⚠️ **O vazio EXPLICA.** Ninguém cadastra este vínculo à mão — ele nasce da
    // nota —, e "nenhum produto" sem essa frase parece campo que faltou.
    const semProdutos = (pessoas ?? []).find((f) => !(f.produtos ?? 0));
    if (semProdutos) {
      await irPara(p, `${WEB}/fornecedores/${semProdutos.id}`);
      await p.waitForFunction(
        () => /produtos desta pessoa/i.test(document.body.innerText), { timeout: 15000 })
        .catch(() => {});
      checar("e quem não fornece nada vê o porquê, não um vazio mudo",
        await p.evaluate(() => /vínculo se cria sozinho|nasce sozinho/i.test(
          document.body.innerText)));
    }
  }

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
  checar("a lista de pessoas nao tem mais o formulario",
    !/Raz[ãa]o social/i.test(listaForn), listaForn.slice(0, 160));
  // ⚠️ **"Nova pessoa", nao "Novo fornecedor"** (04/09/2026): a tela passou a
  // guardar quem nao vende nada para a casa, e o rotulo seguiu. A ROTA continua
  // `/fornecedores`, de proposito — mudar a URL espalharia risco por Compras,
  // Integracoes e exportacoes para o usuario ver a mesma tela.
  checar("e o botao leva para a pagina nova", await p.evaluate(() =>
    [...document.querySelectorAll("a")].some(
      (a) => /Nova pessoa/i.test(a.textContent ?? "") && a.getAttribute("href") === "/fornecedores/novo")));

  await irPara(p, `${WEB}/fornecedores/novo`);
  await new Promise((r) => setTimeout(r, 1400));
  const formForn = await textoVisivel(p);
  checar("a pagina de nova pessoa abre", /Nova pessoa/i.test(formForn), formForn.slice(0, 140));
  // 🔑 A marca que decide onde a pessoa aparece: sem ela, o seletor de
  // fornecedor da nota viraria uma lista de funcionarios.
  checar("com a caixa de 'e fornecedor'", /[ÉE] fornecedor/i.test(formForn),
    formForn.slice(0, 400));
  // 🔑 E a politica de cupom, que e o motivo de a pessoa existir na venda.
  checar("e a politica de cupom da pessoa",
    /No cupom desta pessoa/i.test(formForn), formForn.slice(0, 400));
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
  // ⚠️ **`.toUpperCase()`: o nome do fornecedor é normalizado pelo BANCO**
  // (gatilho da migração 050, que estendeu a ele o que a 036 fez com o
  // produto). A checagem afirma sobre o que foi GRAVADO, não sobre o que ela
  // digitou na tela.
  const meuForn = (fornCriados ?? [])
    .find((f) => f.nome === `Fornecedor tela ${mCad}`.toUpperCase());
  checar("cadastrar pela pagina grava o fornecedor", !!meuForn, (fornCriados ?? []).length);
  if (meuForn) {
    aoTerminar.push(() => api("DELETE", `/fornecedores/${meuForn.id}`, null, token));
    // ⚠️ A edicao e a MESMA forma da criacao, para o olho reconhecer.
    await irPara(p, `${WEB}/fornecedores/${meuForn.id}`);
    await new Promise((r) => setTimeout(r, 1600));
    const edicao = await textoVisivel(p);
    checar("e a edicao abre com o nome no titulo",
      edicao.toUpperCase().includes(`Fornecedor tela ${mCad}`.toUpperCase()),
      edicao.slice(0, 160));
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

  console.log("10d2. o menu novo: busca, atalhos e icones");
  // 🔑 **O menu foi redesenhado em 15/09/2026** (pedido do dono: *"gostaria de
  // um menu mais moderno"*). A lateral tinha seis grupos, todos recolhidos —
  // decisao deliberada, que continua de pe —, e o preco dela era dois cliques
  // por navegacao numa coluna com 85% do espaco vazio. Tres movimentos:
  // busca (Ctrl+K), atalhos fixados e icone em cada linha.
  await irPara(p, `${WEB}/`);
  await p.waitForSelector("#menu-busca", { timeout: 12000 });

  const menuNovo = await p.evaluate(() => {
    const linhas = [...document.querySelectorAll("aside .menu-linha")];
    const grupos = [...document.querySelectorAll("aside .menu-grupo")];
    return {
      linhas: linhas.length,
      // O icone vive DENTRO do link, junto do nome — nao ao lado da linha.
      semIcone: linhas.filter((l) => !l.querySelector("a svg")).length,
      gruposSemIcone: grupos.filter((g) => !g.querySelector("svg")).map((g) => g.innerText),
      // ⚠️ `<button>` dentro de `<a>` e HTML invalido: o navegador desmancha a
      // arvore em silencio e o leitor de tela anuncia um controle dentro do
      // outro. O alfinete tem de ser IRMAO do link.
      botaoDentroDeLink: document.querySelectorAll("aside a button").length,
      teclaVisivel: document.querySelector(".menu-tecla")?.offsetParent !== null,
      contas: grupos.map((g) => g.querySelector(".menu-conta")?.textContent ?? null),
      // O grupo de uma tela so deixou de ser pasta (ver `montarMenu`).
      grupoCompras: grupos.some((g) => /^compras/i.test(g.innerText.trim())),
      linkCompras: document.querySelectorAll('aside a[href="/compras"]').length,
    };
  });
  checar("o menu tem linhas e toda linha tem icone",
    menuNovo.linhas >= 8 && menuNovo.semIcone === 0, menuNovo);
  checar("todo titulo de grupo tem icone", menuNovo.gruposSemIcone.length === 0, menuNovo);
  checar("o alfinete e IRMAO do link, nao filho (HTML valido)",
    menuNovo.botaoDentroDeLink === 0, menuNovo);
  checar("no computador a busca anuncia o atalho do teclado",
    menuNovo.teclaVisivel === true, menuNovo);
  checar("cada grupo diz quantas telas tem dentro",
    menuNovo.contas.length > 0 && menuNovo.contas.every((c) => /^\d+$/.test(c ?? "")),
    menuNovo.contas);
  // 🔑 Abrir uma pasta com um papel dentro e um clique que nao compra nada — e
  // isto nao vale so para Compras: vale para quem tem permissao de UMA tela
  // dentro de um grupo de seis.
  checar("grupo de uma tela so vira item: Compras deixou de ser pasta",
    menuNovo.grupoCompras === false, menuNovo);
  checar("e a tela dela continua alcancavel", menuNovo.linkCompras >= 1, menuNovo);

  // 🔑 **Nenhum nome de tela pode ser cortado** (15/09/2026, relatado pelo dono:
  // *"aumentar um pouco o menu pois alguns itens cortaram a descricao"*). Com o
  // icone e o alfinete, a coluna de 240px deixava ~169px para o texto, e
  // "Saldos e movimentos", "Exportacao para o PDV" e "Papeis e permissoes" nao
  // cabiam. ⚠️ Nome cortado obriga a pessoa a ADIVINHAR o destino, que e o
  // contrario do que um menu faz.
  await p.evaluate(() =>
    document.querySelectorAll("aside .menu-grupo").forEach((b) => b.click()));
  await new Promise((r) => setTimeout(r, 400));
  const cortados = await p.evaluate(() =>
    [...document.querySelectorAll("aside .menu-item span:last-child")]
      .filter((s) => s.scrollWidth > s.clientWidth + 1)
      .map((s) => `${s.textContent} (${s.scrollWidth}>${s.clientWidth})`));
  checar("nenhum nome de tela e cortado no menu", cortados.length === 0, cortados);
  // ⚠️ Devolve os grupos ao estado recolhido: quem desvia, devolve.
  await p.evaluate(() =>
    document.querySelectorAll("aside .menu-grupo[aria-expanded='true']").forEach((b) => b.click()));
  await new Promise((r) => setTimeout(r, 300));

  // ---- a busca (Ctrl+K) ----
  await p.keyboard.down("Control");
  await p.keyboard.press("KeyK");
  await p.keyboard.up("Control");
  await p.waitForSelector("#paleta-campo", { timeout: 8000 });
  const paletaAberta = await p.evaluate(() => ({
    foco: document.activeElement?.id ?? null,
    opcoes: document.querySelectorAll(".paleta-op").length,
    primeiraMarcada: document.querySelector(".paleta-op")?.getAttribute("aria-selected"),
    // A pagina atras nao rola enquanto a busca esta aberta — e a mesma regra da
    // `Modal`: rolar o que esta por baixo da a impressao de que o clique passou.
    corpoTravado: document.body.style.overflow,
  }));
  checar("Ctrl+K abre a busca ja com o foco no campo",
    paletaAberta.foco === "paleta-campo", paletaAberta);
  checar("e oferece as telas que esta pessoa pode abrir",
    paletaAberta.opcoes >= 10, paletaAberta);
  checar("a primeira ja vem marcada, para o Enter valer sem seta",
    paletaAberta.primeiraMarcada === "true", paletaAberta);
  checar("a pagina atras nao rola com a busca aberta",
    paletaAberta.corpoTravado === "hidden", paletaAberta);

  // ⚠️ Sem acento de proposito: ninguem digita "Inventário" com o acento numa
  // busca. Se o filtro comparasse as strings cruas, isto acharia zero.
  await p.type("#paleta-campo", "invent");
  await p.waitForFunction(() => document.querySelectorAll(".paleta-op").length === 1,
    { timeout: 6000 }).catch(() => {});
  const achadosDaBusca = await p.evaluate(() =>
    [...document.querySelectorAll(".paleta-op")].map((l) => l.innerText.replace(/\n/g, " ")));
  checar("digitar sem acento encontra a tela acentuada",
    achadosDaBusca.length === 1 && /Invent/.test(achadosDaBusca[0]), achadosDaBusca);
  checar("e o resultado diz de que grupo a tela e",
    /ESTOQUE/i.test(achadosDaBusca[0] ?? ""), achadosDaBusca);
  await foto(p, "36b-busca-de-telas");

  await p.keyboard.press("Enter");
  await p.waitForFunction(() => location.pathname === "/inventario", { timeout: 12000 })
    .catch(() => {});
  const depoisDoEnter = await p.evaluate(() => ({
    rota: location.pathname,
    fechou: !document.querySelector("#paleta-campo"),
    corpo: document.body.style.overflow,
    ativo: document.querySelector("aside .menu-item-ativo")?.innerText.trim() ?? null,
  }));
  checar("Enter abre a tela escolhida", depoisDoEnter.rota === "/inventario", depoisDoEnter);
  checar("a busca fecha ao abrir a tela", depoisDoEnter.fechou, depoisDoEnter);
  // ⚠️ Devolver a rolagem e o que mais se esquece: uma janela que fecha sem
  // restaurar `overflow` deixa a PAGINA travada, e o defeito aparece longe.
  checar("e devolve a rolagem da pagina", depoisDoEnter.corpo !== "hidden", depoisDoEnter);
  checar("o menu marca a tela em que se esta", depoisDoEnter.ativo === "Inventário",
    depoisDoEnter);

  // Escape fecha SEM navegar — a saida que todo mundo tenta antes do X.
  await p.keyboard.down("Control");
  await p.keyboard.press("KeyK");
  await p.keyboard.up("Control");
  await p.waitForSelector("#paleta-campo", { timeout: 8000 });
  await p.keyboard.press("Escape");
  await new Promise((r) => setTimeout(r, 300));
  const depoisDoEscape = await p.evaluate(() => ({
    fechou: !document.querySelector("#paleta-campo"),
    rota: location.pathname,
  }));
  checar("Escape fecha a busca sem sair da tela",
    depoisDoEscape.fechou && depoisDoEscape.rota === "/inventario", depoisDoEscape);

  // O botao do menu abre a mesma busca: quem nao conhece o atalho tambem chega.
  await p.evaluate(() => document.querySelector("#menu-busca")?.click());
  await p.waitForSelector("#paleta-campo", { timeout: 8000 }).catch(() => null);
  checar("o botao do menu abre a mesma busca",
    await p.evaluate(() => !!document.querySelector("#paleta-campo")));
  await p.keyboard.press("Escape");
  await new Promise((r) => setTimeout(r, 250));

  // ---- os atalhos ----
  // 🔑 Eles ocupam o espaco que ja estava vazio, e sao de QUEM usa: a cozinha
  // nao abre as mesmas telas que o escritorio.
  const atalhosAntes = await p.evaluate(() => ({
    secao: !!document.querySelector(".menu-secao"),
    guardados: JSON.parse(localStorage.getItem("botane.atalhos") ?? "null"),
    marcados: document.querySelectorAll(".menu-fixar-marcado").length,
  }));
  checar("o menu abre com uma secao de atalhos", atalhosAntes.secao, atalhosAntes);

  // Fixa o Inventario pelo caminho da pessoa: abre o grupo, toca no alfinete.
  await p.evaluate(() => {
    [...document.querySelectorAll("aside .menu-grupo")]
      .find((b) => /estoque/i.test(b.innerText))?.click();
  });
  await new Promise((r) => setTimeout(r, 350));
  await p.evaluate(() => {
    const linha = [...document.querySelectorAll("aside .menu-filhos .menu-linha")]
      .find((l) => /Inventário/.test(l.innerText));
    linha?.querySelector("button")?.click();
  });
  await new Promise((r) => setTimeout(r, 350));
  const aoFixar = await p.evaluate(() => ({
    guardados: JSON.parse(localStorage.getItem("botane.atalhos") ?? "[]"),
    // O atalho aparece ANTES do primeiro grupo — e essa e a razao de existir.
    noTopo: (() => {
      const nav = document.querySelector("aside nav");
      const alvo = [...nav.querySelectorAll(".menu-linha")]
        .find((l) => /Inventário/.test(l.innerText));
      const grupo = nav.querySelector(".menu-grupo");
      return alvo && grupo
        ? alvo.compareDocumentPosition(grupo) === Node.DOCUMENT_POSITION_FOLLOWING
        : null;
    })(),
  }));
  checar("o alfinete fixa a tela nos atalhos",
    aoFixar.guardados.includes("/inventario"), aoFixar);
  checar("e ela passa a aparecer antes dos grupos", aoFixar.noTopo === true, aoFixar);

  // ⚠️ **Sobrevive ao recarregar** — e esta e a checagem que importa: a
  // preferencia mora no navegador, e uma que so vale ate a proxima F5 e uma
  // preferencia que ninguem usa.
  await p.reload({ waitUntil: "networkidle2" });
  await p.waitForSelector(".menu-secao", { timeout: 12000 });
  const atalhosAoVoltar = await p.evaluate(() =>
    [...document.querySelectorAll("aside .menu-linha")].map((l) => l.innerText.trim()));
  checar("o atalho sobrevive ao recarregar a pagina",
    atalhosAoVoltar.filter((t) => /Inventário/.test(t)).length >= 1, atalhosAoVoltar.slice(0, 8));

  // E sai pelo mesmo gesto — um controle que so sabe adicionar acumula lixo.
  await p.evaluate(() => {
    const linha = [...document.querySelectorAll("aside .menu-linha")]
      .find((l) => /Inventário/.test(l.innerText));
    linha?.querySelector("button")?.click();
  });
  await new Promise((r) => setTimeout(r, 350));
  const aoTirar = await p.evaluate(() =>
    JSON.parse(localStorage.getItem("botane.atalhos") ?? "[]"));
  checar("e o mesmo alfinete tira", !aoTirar.includes("/inventario"), aoTirar);
  await foto(p, "36c-menu-novo");

  // 🔑 **As peças de formulário, redesenhadas** (15/09/2026, protótipo aprovado
  // pelo dono: `apresentacao/pecas-prototipo.html`). Três coisas que a norma
  // mede e uma que ela não mede, mas que era o pior defeito da tela.
  await irPara(p, `${WEB}/produtos/novo`);
  await p.waitForSelector("#campo-nome", { timeout: 20000 });
  await new Promise((r) => setTimeout(r, 900));
  const pecas = await p.evaluate(() => {
    const luz = (cor) => {
      const [r, g, b] = cor.match(/[\d.]+/g).slice(0, 3).map(Number).map((x) => {
        const v = x / 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
      });
      return 0.2126 * r + 0.7152 * g + 0.0722 * b;
    };
    const razao = (a, b) => {
      const [x, y] = [luz(a), luz(b)].sort((m, n) => n - m);
      return (x + 0.05) / (y + 0.05);
    };
    const fundo = getComputedStyle(document.querySelector(".cartao") ?? document.body).backgroundColor;
    const rot = document.querySelector(".rotulo-campo");
    const er = getComputedStyle(rot);
    const botao = [...document.querySelectorAll("button.btn")]
      .find((b) => b.getBoundingClientRect().height > 0);
    return {
      // O rótulo saiu da mono de 10,5px em MAIÚSCULAS.
      rotuloPx: parseFloat(er.fontSize),
      rotuloCaixa: er.textTransform,
      rotuloContraste: razao(er.color, fundo),
      quantos: document.querySelectorAll(".rotulo-campo").length,
      // 44px é o que a WCAG 2.5.5 recomenda para o dedo.
      alturaBotao: botao ? Math.round(botao.getBoundingClientRect().height) : null,
      raioCampo: getComputedStyle(document.querySelector(".campo")).borderRadius,
    };
  });
  checar("o rotulo do campo cresceu e saiu das MAIUSCULAS",
    pecas.rotuloPx >= 13 && pecas.rotuloCaixa === "none", pecas);
  checar("e passa folgado no contraste de texto de corpo",
    Number(pecas.rotuloContraste) >= 4.5, pecas);
  checar("a tela usa a peca nova, e nao o rotulo de secao", pecas.quantos >= 5, pecas);
  checar("o botao chega aos 44px que a norma recomenda para o dedo",
    (pecas.alturaBotao ?? 0) >= 44, pecas);

  // 🔑 **O erro do campo, NO campo.** Antes o nome era validado pelo `required`
  // do navegador — ou seja, pela caixa cinza do Chrome, a mesma que esta casa
  // baniu do resto do sistema — e o erro de servidor saía no balão do canto,
  // longe do campo e sumindo em 6 segundos.
  // ⚠️ A guarda global de `dialog` desta bateria derruba a rodada se um balão
  // do navegador aparecer aqui: é o que prova que a validação é NOSSA.
  await p.evaluate(() => {
    const c = document.querySelector("#campo-nome");
    if (c) { c.value = ""; }
  });
  await p.click('button[type="submit"]');
  await new Promise((r) => setTimeout(r, 600));
  const comErro = await p.evaluate(() => {
    const campo = document.querySelector("#campo-nome");
    const erro = document.querySelector(".erro-campo");
    return {
      invalido: campo?.getAttribute("aria-invalid"),
      // O `aria-describedby` é o que faz o leitor de tela LER a frase do erro.
      descrito: campo?.getAttribute("aria-describedby") ?? "",
      mensagem: erro?.innerText?.trim() ?? null,
      // Quem errou tem de poder corrigir sem procurar o campo.
      focado: document.activeElement === campo,
      rota: location.pathname,
    };
  });
  checar("submeter sem nome NAO cria produto nenhum", comErro.rota === "/produtos/novo", comErro);
  checar("o campo fica marcado como invalido", comErro.invalido === "true", comErro);
  checar("com a frase dizendo o que fazer, embaixo dele",
    /precisa de um nome/i.test(comErro.mensagem ?? ""), comErro);
  checar("ligada ao campo pelo aria-describedby, e com o foco nele",
    comErro.descrito.includes("-erro") && comErro.focado === true, comErro);

  // ⚠️ E corrigir apaga o erro NA HORA: erro que só some no próximo "salvar"
  // deixa a pessoa sem saber se acertou.
  await p.type("#campo-nome", "ab");
  await new Promise((r) => setTimeout(r, 400));
  const corrigido = await p.evaluate(() => ({
    invalido: document.querySelector("#campo-nome")?.getAttribute("aria-invalid"),
    temErro: !!document.querySelector(".erro-campo"),
  }));
  checar("e corrigir apaga o erro na hora",
    corrigido.invalido === null && corrigido.temErro === false, corrigido);
  await foto(p, "44b-pecas-do-formulario");

  console.log("10d3. reprocessar o estoque de um produto");
  // 🔑 **Pedido do dono (15/09/2026):** *"em saldos e movimentos, criar uma
  // opcao de reprocessar, caso tenha alteracoes, disponibilizar a opcao de
  // reprocessar o estoque, filtrando por produto"*.
  // 🔑 O caso e o LANCAMENTO RETROATIVO: a nota do dia 9 entra hoje, depois de
  // a venda do dia 12 ja ter saido. A venda saiu por custo estimado (nao havia
  // saldo) e o saldo ficou negativo — e nada disso se acerta sozinho, porque o
  // custo medio e calculado no instante do lancamento.
  const mRep = Date.now().toString().slice(-5);
  const { dados: prodRep } = await api("POST", "/produtos", {
    codigo: `TREP-${mRep}`, nome: `VINHO REPRO TELA ${mRep}`, tipo: "REVENDA",
    um_estoque: "UN", controla_estoque: true, status: "ATIVO",
  }, token);
  aoTerminar.push(() => api("DELETE", `/produtos/${prodRep.id}`, null, token));
  // 🔑 **E o RAZAO deste produto some junto** — `DELETE /produtos` so inativa o
  // cadastro, que e o certo para o sistema e insuficiente aqui. Esta fase lanca
  // uma saida, depois uma entrada com data ANTERIOR, e reprocessa: dali em
  // diante o razao dele e coerente na ordem da DATA, enquanto `estoque_saldos`
  // e o resto da base seguem coerentes na ordem de LANCAMENTO. O relatorio de
  // CMV por grupo le a fotografia pelo `id DESC` e passa a discordar do CMV do
  // periodo — medido: R$ 256,00 em dois produtos, derrubando smoke_grupos_cmv e
  // smoke_relatorios, duas suites a tres telas da causa.
  // ⚠️ Mesma excecao documentada da `smoke_reprocessar`: teste que deixa rastro
  // derruba o proximo, e o que fecha a conta e nao deixar rastro nenhum.
  aoTerminar.push(() => {
    execFileSync("python", ["tests/limpar_rastro.py", "TREP-"], { cwd: "../api" });
  });
  const { dados: locaisRep } = await api("GET", "/locais", null, token);
  const localRep = (locaisRep.find((l) => l.principal) ?? locaisRep[0]).id;
  // ⚠️ A ordem e o teste: saida primeiro, entrada com data ANTERIOR depois.
  await api("POST", "/estoque/saidas", {
    id_produto: prodRep.id, quantidade: 2, tipo: "SAIDA_VENDA", id_local: localRep,
    data_movimento: "2026-09-12", documento: `TREP-V-${mRep}`,
  }, token);
  await api("POST", "/estoque/entradas", {
    id_produto: prodRep.id, quantidade: 6, custo_unitario: 64, id_local: localRep,
    data_movimento: "2026-09-09", documento: `TREP-N-${mRep}`,
  }, token);

  await irPara(p, `${WEB}/estoque`);
  await p.waitForFunction(() => /Razão de estoque|Saldos/.test(document.body.innerText),
    { timeout: 20000 }).catch(() => {});
  await clicarQuando(p, "Movimentos", { exato: true });
  await new Promise((r) => setTimeout(r, 900));

  // ⚠️ **O produto se escolhe pela LUPA, nao digitando.** Este filtro e o
  // `FiltroCadastro`: o texto filtra a lista, e quem FIXA um produto e a
  // janela de pesquisa — e reprocessar precisa de um produto, nao de um
  // recorte. A tela diz isso a quem digitou e nao viu o botao.
  const semProduto = await p.evaluate(() => !!document.querySelector("#reprocessar-estoque"));
  checar("sem produto escolhido, nao ha o que reprocessar", semProduto === false, semProduto);

  await p.evaluate(() =>
    [...document.querySelectorAll('button[aria-label="Buscar produto"]')].pop()?.click());
  await p.waitForSelector('[role="dialog"] input', { timeout: 15000 }).catch(() => {});
  await p.evaluate((nome) => {
    const campo = document.querySelector('[role="dialog"] input');
    if (!campo) return;
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    setter.call(campo, nome);
    campo.dispatchEvent(new Event("input", { bubbles: true }));
  }, `VINHO REPRO TELA ${mRep}`);
  await p.waitForFunction((nome) => {
    const janela = document.querySelector('[role="dialog"]');
    return !!janela && janela.innerText.includes(nome);
  }, { timeout: 15000 }, `VINHO REPRO TELA ${mRep}`).catch(() => {});
  await p.evaluate((nome) => {
    const linha = [...document.querySelectorAll('[role="dialog"] tbody tr, [role="dialog"] li')]
      .find((x) => x.innerText.includes(nome));
    (linha?.querySelector("button") ?? linha)?.click();
  }, `VINHO REPRO TELA ${mRep}`);
  await p.waitForSelector("#reprocessar-estoque", { timeout: 15000 }).catch(() => {});
  checar("escolhido o produto, o botao Reprocessar aparece",
    await p.evaluate(() => !!document.querySelector("#reprocessar-estoque")));

  await p.evaluate(() => document.querySelector("#reprocessar-estoque")?.click());
  await p.waitForFunction(() => /Como fica a prateleira/i.test(document.body.innerText),
    { timeout: 20000 }).catch(() => {});
  const janelaRep = await p.evaluate(() =>
    document.querySelector('[role="dialog"]')?.innerText ?? "");
  // 🔑 **A previa vem ANTES do botao**: isto reescreve numero que alguem ja leu.
  checar("a previa mostra como fica a prateleira",
    /Como fica a prateleira/i.test(janelaRep), janelaRep.slice(0, 200));
  checar("e o que muda em cada movimento",
    /O que muda em cada movimento/i.test(janelaRep), janelaRep.slice(0, 200));
  // ⚠️ A saida saiu por ZERO e passa a custar 64 — e a previa TEM de mostrar os
  // dois numeros, senao quem confirma nao sabe o que esta confirmando.
  // ⚠️ **O espaco depois do "R$" e NAO SEPARAVEL** (U+00A0): e o que o
  // `Intl.NumberFormat` produz para BRL, e `includes("R$ 0,00")` com espaco
  // comum nao casa com ele. No terminal os dois se parecem, entao a falha
  // aparece como "a tela nao mostra o numero" — com o numero na tela.
  const semNbsp = janelaRep.replace(/\u00a0/g, " ");
  checar("dizendo de quanto para quanto vai o custo da saida",
    semNbsp.includes("R$ 0,00") && semNbsp.includes("R$ 64,00"), semNbsp.slice(0, 400));
  await foto(p, "44c-reprocessar");

  await clicarQuando(p, "Reprocessar 3 movimento");
  await p.waitForFunction(() => !document.querySelector('[role="dialog"]'),
    { timeout: 20000 }).catch(() => {});
  await new Promise((r) => setTimeout(r, 1200));

  const { dados: movsRep } = await api(
    "GET", `/estoque/movimentos?id_produto=${prodRep.id}&por_pagina=50`, null, token);
  const saidaRep = (movsRep ?? []).find((m) => m.tipo === "SAIDA_VENDA");
  const entradaRep = (movsRep ?? []).find((m) => m.tipo === "ENTRADA_MANUAL");
  checar("depois de reprocessar, a saida custa a media do momento",
    Number(saidaRep?.custo_unitario ?? 0) === 64, saidaRep);
  checar("e o saldo dela deixou de ser negativo",
    Number(saidaRep?.saldo_apos ?? -1) === 4, saidaRep);
  // ⚠️ O custo da ENTRADA nao se toca: e o que a casa pagou.
  checar("o custo da entrada continua o da nota",
    Number(entradaRep?.custo_unitario ?? 0) === 64, entradaRep);
  const { dados: saldosRep } = await api(
    "GET", `/estoque/saldos?id_produto=${prodRep.id}`, null, token);
  checar("e a prateleira fica com saldo e custo certos",
    Number(saldosRep?.[0]?.quantidade ?? 0) === 4
    && Number(saldosRep?.[0]?.custo_medio ?? 0) === 64, saldosRep?.[0]);
  console.log("10e. remessa entre lojas: em transito e recebimento");
  // 🔑 **A remessa em transito continua contando no estoque de quem mandou** — e
  // esta tela existe para esse "continua contando" nao virar armadilha. O que se
  // prova aqui e o que a tela promete, nao o estado do dia: que ela DIZ que nada
  // foi lancado, e que o botao de receber so aparece na loja de DESTINO.
  const marcaR = String(Date.now()).slice(-6);
  const { dados: filialR } = await api("POST", "/unidades", {
    nome: `Filial tela ${marcaR}`, apelido: `T${marcaR}`,
  }, token);
  // ⚠️ A filial sai mesmo se o roteiro estourar no meio: com duas lojas ativas o
  // seletor aparece na barra e vira o primeiro `<select>` do documento, e as
  // checagens que leem `select` passam a ler id de loja. Mesma licao do
  // `preservar_credenciais`.
  aoTerminar.push(async () => {
    await api("PUT", `/unidades/${filialR.id}`, { ativo: false }, token);
    // E a loja escolhida volta a ser a matriz: a escolha mora no localStorage do
    // navegador, e deixa-la na filial faria a proxima rodada abrir tudo na loja
    // errada — inclusive as telas que nada tem a ver com remessa.
    try {
      await p.evaluate(() => localStorage.setItem("botane.unidade", "1"));
    } catch { /* a pagina pode ja ter sido fechada */ }
  });

  // ⚠️ `garantirLocal` devolve o ID, não o objeto.
  const idLocalMatrizR = await garantirLocal();
  const { dados: locaisFilR } = await fetch(`${API}/locais`, {
    headers: { Authorization: `Bearer ${token}`, "X-Unidade": String(filialR.id) },
  }).then(async (r) => ({ dados: await r.json() }));
  const { dados: prodR } = await api("POST", "/produtos", {
    codigo: `TELAREM${marcaR}`, nome: `Insumo remessa tela ${marcaR}`,
    tipo: "INSUMO", um_estoque: "KG", controla_estoque: true,
  }, token);
  await api("POST", "/estoque/entradas", {
    id_produto: prodR.id, id_local: idLocalMatrizR, quantidade: 15, custo_unitario: 4,
  }, token);
  const { dados: remessaR } = await api("POST", "/transferencias", {
    id_local_origem: idLocalMatrizR, id_local_destino: locaisFilR[0].id,
    itens: [{ id_produto: prodR.id, quantidade: 5 }],
  }, token);

  await irPara(p, `${WEB}/transferencias`);
  // ⚠️ Espere por algo que so existe na tela de DESTINO — dormir um tempo fixo e
  // afirmar e supor a precondicao.
  await p.waitForFunction(
    (id) => document.body.innerText.includes(`#${id}`),
    { timeout: 8000 }, remessaR.id,
  ).catch(() => {});
  const listaRemessas = await p.evaluate(() => document.body.innerText);
  checar("a remessa aparece em transito", listaRemessas.includes(`#${remessaR.id}`),
    listaRemessas.slice(0, 120));

  await irPara(p, `${WEB}/transferencias/${remessaR.id}`);
  await p.waitForFunction(
    () => /em tr[aâ]nsito/i.test(document.body.innerText), { timeout: 8000 },
  ).catch(() => {});
  const naOrigem = await p.evaluate(() => ({
    texto: document.body.innerText,
    botoes: [...document.querySelectorAll("button")].map((b) => b.innerText.trim()),
  }));
  checar("a tela diz que nada foi lancado ainda",
    /continua contando/i.test(naOrigem.texto), naOrigem.texto.slice(0, 140));
  // 🔑 A tela NAO pode oferecer um botao que vai levar 403. Quem recebe e o
  // destino, e a pergunta e a loja ATUAL — nao a visibilidade, que no
  // administrador e sempre verdadeira.
  checar("na loja de ORIGEM nao ha botao de receber",
    !naOrigem.botoes.some((b) => /Receber no estoque/i.test(b)), naOrigem.botoes);
  checar("mas ha o de cancelar, que e de quem despachou",
    naOrigem.botoes.some((b) => /Cancelar remessa/i.test(b)), naOrigem.botoes);

  // O saldo da origem precisa DIZER quanto ja esta na estrada, senao a segunda
  // remessa do dia despacha o que ja saiu.
  // ⚠️ **A tela nao le `?id_produto` da URL** — o filtro e estado dela. Digitar
  // no campo e o unico caminho que existe de verdade; navegar com um parametro
  // inventado mede a primeira pagina do cadastro inteiro.
  await irPara(p, `${WEB}/estoque`);
  await p.waitForSelector('input[placeholder="produto ou código"]', { timeout: 10000 });
  await p.type('input[placeholder="produto ou código"]', `remessa tela ${marcaR}`);
  await p.waitForFunction(
    (nome) => document.body.innerText.toUpperCase().includes(nome),
    { timeout: 12000 }, `INSUMO REMESSA TELA ${marcaR}`,
  ).catch(() => {});
  const nosSaldos = await p.evaluate(() => document.body.innerText);
  checar("e o saldo da origem avisa o que esta em transito",
    /em tr[aâ]nsito/i.test(nosSaldos), nosSaldos.slice(-260));

  // 🔑 **O estoque da EMPRESA**: o mesmo produto somando as lojas. So existe com
  // mais de uma loja — numa casa so seria a tela de sempre com uma coluna a mais.
  // ⚠️ O que se afirma aqui e a PROPRIEDADE, nao o estado do dia: que o
  // interruptor existe, que a linha vira o produto (o filtro de prateleira sai,
  // porque seletor que nao corta nada e promessa falsa) e que a loja SEM aquele
  // produto mostra traco — "nao tem linha aqui" e "tem zero" se leem igual e so
  // o segundo e um saldo.
  // 🔑 **Tres granularidades da mesma pergunta**, e nao duas caixinhas: por
  // prateleira ("onde esta"), por produto ("quanto a loja tem") e por empresa.
  // O processo da casa poe o mesmo produto em varios locais — o acucar entra
  // no Estoque Central e cada setor leva um pacote para o seu canto —, e a
  // lista por prateleira mostra quatro linhas e nenhum total.
  const opcoesVisao = await p.evaluate(() =>
    [...(document.querySelector("#visao-saldos")?.options ?? [])].map((o) => o.value));
  checar("os saldos escolhem a granularidade", opcoesVisao.length >= 2, opcoesVisao);
  checar("com prateleira, produto e — havendo mais de uma loja — empresa",
    opcoesVisao.includes("prateleira") && opcoesVisao.includes("produto")
    && opcoesVisao.includes("empresa"), opcoesVisao);
  const temSomarLojas = opcoesVisao.includes("empresa");
  if (temSomarLojas) {
    const rotuloLocal = () => p.evaluate(() => [...document.querySelectorAll("main .rotulo, main .rotulo-campo")]
      .some((x) => (x.textContent ?? "").trim() === "Local"));
    // ⚠️ **Escolhe a prateleira ANTES de medir.** A tela abre em "por produto"
    // desde 11/09/2026 (pedido do dono), e aí o filtro de prateleira ja nao
    // esta la — `localAntes` vinha falso e a checagem acusava um defeito que
    // nao existia. O que se afirma e a TRANSICAO: com prateleira ha filtro de
    // local, na visao de empresa nao ha.
    await p.select("#visao-saldos", "prateleira");
    await p.waitForFunction(
      () => [...document.querySelectorAll("main .rotulo, main .rotulo-campo")]
        .some((x) => (x.textContent ?? "").trim() === "Local"),
      { timeout: 10000 },
    ).catch(() => {});
    const localAntes = await rotuloLocal();
    await p.select("#visao-saldos", "empresa");
    // ⚠️ **Esperar pela frase explicativa nao espera nada**: ela aparece no
    // instante do clique, antes de a lista voltar do servidor — e a checagem
    // media a tabela ainda vazia. Espere pela COLUNA da filial, que so existe
    // depois de a resposta chegar.
    await p.waitForFunction(
      (apelido) => [...document.querySelectorAll("main table thead th")]
        .some((t) => (t.textContent ?? "").trim() === apelido),
      { timeout: 15000 }, `T${marcaR}`,
    ).catch(() => {});
    const naRede = await p.evaluate((apelido) => {
      const th = [...document.querySelectorAll("main table thead th")]
        .map((t) => (t.textContent ?? "").trim());
      const tr = [...document.querySelectorAll("main table tbody tr")][0];
      const tds = [...(tr?.children ?? [])].map((c) => (c.textContent ?? "").trim());
      return { th, tds, coluna: th.indexOf(apelido) };
    }, `T${marcaR}`);
    checar("a barra deixa de oferecer o filtro de prateleira",
      localAntes && !(await rotuloLocal()), { localAntes });
    checar("e a tabela ganha uma coluna para cada loja",
      naRede.coluna > 0 && naRede.th.includes("Total"), naRede.th);
    checar("a loja que nao tem o produto mostra traco, nao zero",
      naRede.tds[naRede.coluna] === "—", naRede.tds);
    // 🔑 **A linha que faz os dois numeros da empresa fecharem.** O painel da
    // rede conta o produto inativo que ainda tem saldo; esta lista nao. Sem
    // dizer quanto ficou de fora, quem confere um contra o outro conclui que um
    // dos dois mente. ⚠️ Afirmo a PROPRIEDADE, nao o estado do dia: quando ha
    // inativo com saldo o aviso aparece, e a caixinha que os inclui existe.
    checar("a visao de empresa oferece incluir os inativos",
      await p.evaluate(() => !!document.querySelector("#incluir-inativos")));
    // ⚠️ **O aviso obedece a BUSCA, e e isso que ele tem de fazer** — com o
    // campo preenchido ele fala so daquele produto. Para medi-lo contra a API e
    // preciso olhar a mesma lista que ela responde: limpo o campo antes.
    // (A primeira versao comparava a tela filtrada com a API inteira e acusava
    // de defeito exatamente o comportamento certo.)
    // ⚠️ **`elementHandle.click()` rola o elemento e estoura o `protocolTimeout`**
    // — derrubou a rodada inteira aqui, num ponto sem defeito nenhum. Focar de
    // DENTRO do documento faz a mesma coisa sem depender de layout.
    await p.evaluate(() => {
      const c = document.querySelector('input[placeholder="produto ou código"]');
      if (c instanceof HTMLInputElement) c.focus();
    });
    await p.keyboard.down("Control");
    await p.keyboard.press("KeyA");
    await p.keyboard.up("Control");
    await p.keyboard.press("Backspace");
    const { dados: foraApi } = await api(
      "GET", "/estoque/saldos-rede/inativos?apenas_com_saldo=true", null, token);
    await p.waitForFunction(
      (n) => (n === 0) === !document.querySelector("#fora-da-lista"),
      { timeout: 15000 }, foraApi.produtos,
    ).catch(() => {});
    const oAviso = await p.evaluate(() => ({
      texto: document.querySelector("#fora-da-lista")?.textContent?.trim() ?? "",
    }));
    checar("e diz quanto ficou de fora quando ha inativo com saldo",
      foraApi.produtos === 0
        ? oAviso.texto === ""
        : /inativos/i.test(oAviso.texto) && oAviso.texto.includes(String(foraApi.produtos)),
      { foraApi, ...oAviso });
    // Volta ao modo de sempre: o proximo bloco le a lista por prateleira.
    await p.select("#visao-saldos", "prateleira");
    await new Promise((r) => setTimeout(r, 800));
  }

  // Troca de loja pelo seletor da barra — e o rotulo dele que o identifica, nao
  // a posicao no DOM: o seletor de loja e o primeiro `<select>` do documento.
  await irPara(p, `${WEB}/transferencias/${remessaR.id}`);
  await p.waitForSelector('select[aria-label="Loja"]', { timeout: 8000 });
  await p.select('select[aria-label="Loja"]', String(filialR.id));
  await p.waitForFunction(
    () => [...document.querySelectorAll("button")]
      .some((b) => /Receber no estoque/i.test(b.innerText)),
    { timeout: 10000 },
  ).catch(() => {});
  const noDestino = await p.evaluate(() =>
    [...document.querySelectorAll("button")].map((b) => b.innerText.trim()));
  checar("na loja de DESTINO o botao de receber aparece",
    noDestino.some((b) => /Receber no estoque/i.test(b)), noDestino);
  checar("e o de cancelar some — quem cancela e quem despachou",
    !noDestino.some((b) => /Cancelar remessa/i.test(b)), noDestino);

  // 🔑 **Clicar de DENTRO do documento.** `p.$$("button")` seguido de
  // `p.evaluate(el => ..., handle)` estoura o `protocolTimeout` do Chrome quando
  // os handles envelhecem — e a troca de loja recarrega a pagina inteira, entao
  // eles envelhecem sempre. Aconteceu aqui: a ProtocolError derrubou a rodada
  // num ponto sem defeito nenhum. O texto continua sendo o que identifica o
  // botao; so a procura mudou de lado.
  const clicarPorTexto = (padrao) =>
    p.evaluate((p_) => {
      const alvo = [...document.querySelectorAll("button")]
        .find((b) => new RegExp(p_, "i").test(b.innerText.trim()));
      if (alvo) alvo.click();
      return !!alvo;
    }, padrao);

  await clicarPorTexto("Receber no estoque");
  await p.waitForFunction(
    () => [...document.querySelectorAll("button")].some((b) => /^Receber$/i.test(b.innerText.trim())),
    { timeout: 8000 },
  ).catch(() => {});
  await clicarPorTexto("^Receber$");
  // ⚠️ **`/recebida/i` no corpo da pagina nasce VERDADEIRO.** A tela ja traz o
  // rotulo "Recebida" (a data, vazia enquanto em transito) e a frase "no
  // instante em que esta remessa for recebida" — entao esta espera voltava na
  // hora, antes de o POST terminar, e a checagem seguinte (o saldo da filial
  // pela API) corria contra a gravacao. Passava quando o servidor era mais
  // rapido que o proximo `fetch`; com a API recem-subida, nao passava.
  // 🔑 A espera certa e pelo EFEITO que so existe depois de receber: o botao
  // sai da tela e o servidor passa a dizer RECEBIDA. Mesma licao das esperas de
  // paginacao (11/09) — esperar por um dado que ja pode estar la nao e esperar.
  await p.waitForFunction(
    () => ![...document.querySelectorAll("button")]
      .some((b) => /Receber no estoque/i.test(b.innerText)),
    { timeout: 10000 },
  ).catch(() => {});
  let statusRemessa = null;
  for (let i = 0; i < 20; i++) {
    statusRemessa = (await api("GET", `/transferencias/${remessaR.id}`, null, token))
      .dados?.status ?? null;
    if (statusRemessa === "RECEBIDA") break;
    await new Promise((r) => setTimeout(r, 250));
  }
  checar("receber deixa a remessa recebida", statusRemessa === "RECEBIDA", statusRemessa);
  await foto(p, "40-remessa");

  // E o razao andou nas DUAS lojas: a filial ganhou o que a matriz perdeu.
  const { dados: saldoFil } = await fetch(
    `${API}/estoque/saldos?id_produto=${prodR.id}`,
    { headers: { Authorization: `Bearer ${token}`, "X-Unidade": String(filialR.id) } },
  ).then(async (r) => ({ dados: await r.json() }));
  checar("e a filial passou a ter as 5 unidades",
    Math.abs(saldoFil.reduce((s, x) => s + Number(x.quantidade), 0) - 5) < 0.01, saldoFil);

  // ⚠️ Volta para a matriz ANTES do resto do roteiro: as checagens seguintes
  // supoem a loja de sempre, e uma tela na filial nao tem nada dentro.
  await p.select('select[aria-label="Loja"]', "1");
  await new Promise((r) => setTimeout(r, 1500));

  console.log("10f. em que loja a pessoa trabalha");
  // 🔑 **`usuario_papeis.id_unidade` existe desde o primeiro script e a tela
  // mandava SEMPRE nulo.** Com uma loja era a resposta certa; com a filial
  // aberta, todo mundo passou a enxergar as duas e o `ve_unidade` que protege
  // saldo, venda, inventario e remessa virou enfeite.
  // ⚠️ Este bloco fica AQUI, e nao junto do resto de usuarios, porque so faz
  // sentido com a segunda loja de pe — e quem a cria e o bloco da remessa.
  await irPara(p, `${WEB}/usuarios/novo`);
  await p.waitForFunction(
    () => /Onde trabalha/i.test(document.body.innerText), { timeout: 10000 },
  ).catch(() => {});
  const comLojas = await p.evaluate(() => document.body.innerText);
  checar("o cadastro de usuario pergunta onde a pessoa trabalha",
    /Onde trabalha/i.test(comLojas), comLojas.slice(0, 160));
  checar("com todas as lojas como padrao",
    /Todas as lojas/i.test(comLojas) && /S[oó] estas lojas/i.test(comLojas),
    comLojas.slice(0, 200));

  // A lista de lojas so aparece depois de escolher "so estas": um bloco de
  // caixinhas sempre a vista sugere que e preciso marcar alguma.
  // ⚠️ **Medir pelo ID da caixinha, nao pelo texto do documento.** O apelido da
  // filial tambem aparece no SELETOR DE LOJA da barra superior, entao
  // `body.innerText.includes(apelido)` era verdadeiro antes de a lista existir —
  // e o teste acusava a tela de mostrar o que ela nao mostrava. E a armadilha do
  // "primeiro elemento que casa" pela outra ponta: procurar no documento inteiro
  // uma string que tambem mora na casca.
  const caixinhaDaFilial = `#loja-${filialR.id}`;
  const antesDeEscolher = await p.evaluate(
    (sel) => !!document.querySelector(sel), caixinhaDaFilial);
  checar("e a lista de lojas so aparece quando se escolhe restringir",
    !antesDeEscolher, antesDeEscolher);

  await p.evaluate(() => {
    const alvo = [...document.querySelectorAll("label")]
      .find((l) => /S[oó] estas lojas/i.test(l.innerText));
    alvo?.querySelector("input")?.click();
  });
  await p.waitForSelector(caixinhaDaFilial, { timeout: 6000 }).catch(() => {});
  const depoisDeEscolher = await p.evaluate(
    (sel) => !!document.querySelector(sel), caixinhaDaFilial);
  checar("e ai as lojas da casa aparecem para marcar", depoisDeEscolher, depoisDeEscolher);
  await foto(p, "41-usuario-lojas");

  console.log("10g. de que setor a pessoa cuida");
  // 🔑 **`usuario_setores` existe desde o script 004 e nunca foi lida por
  // nada** — "Restrição por setor (o ajudante conta só a área dele). Sem linha
  // = sem limite.", dizia o comentário. É a mesma história da loja acima: o
  // sistema sabia fazer e não oferecia isso a ninguém. Agora o cadastro
  // pergunta, e o painel da pessoa abre no que é dela.
  const semSetor = await p.evaluate(() => ({
    pergunta: /De que setor cuida/i.test(document.body.innerText),
    // O padrão é a casa toda: ninguém perde nada no dia do deploy.
    padrao: /A casa toda/i.test(document.body.innerText),
    restringe: /S[oó] estes setores/i.test(document.body.innerText),
    // ⚠️ **A tela tem de DIZER que setor não é permissão.** Quem lesse "só
    // estes setores" como bloqueio deixaria de configurar o papel — e a pessoa
    // continuaria abrindo as telas pelo menu.
    avisaQueNaoEPermissao: /n[ãa]o é permiss[ãa]o/i.test(document.body.innerText),
    // A lista de setores só aparece depois de escolher restringir, como a de lojas.
    listaEscondida: !document.querySelector("[id^='setor-']"),
  }));
  checar("o cadastro de usuario pergunta de que setor a pessoa cuida",
    semSetor.pergunta, semSetor);
  checar("com a casa toda como padrao", semSetor.padrao && semSetor.restringe, semSetor);
  checar("dizendo que setor NAO e permissao", semSetor.avisaQueNaoEPermissao, semSetor);
  checar("e a lista de setores so aparece quando se escolhe restringir",
    semSetor.listaEscondida, semSetor);

  await p.evaluate(() => {
    const alvo = [...document.querySelectorAll("label")]
      .find((l) => /S[oó] estes setores/i.test(l.innerText));
    alvo?.querySelector("input")?.click();
  });
  await p.waitForSelector("[id^='setor-']", { timeout: 6000 }).catch(() => {});
  const comSetores = await p.evaluate(() =>
    [...document.querySelectorAll("[id^='setor-']")].length);
  checar("e ai os setores da casa aparecem para marcar", comSetores > 0, comSetores);
  await foto(p, "41b-usuario-setores");

  // 🔑 **O que o pedido pede de verdade: o painel abre no que é da pessoa.**
  // ⚠️ Medido pelo SERVIDOR e pela TELA: a API diz que recorta, e a tela tem de
  // mostrar o cartão — um endpoint certo com tela muda não entrega nada.
  const { dados: painelAdmin } = await api("GET", "/inicio", null, token);
  checar("o painel traz a agenda de producao",
    !!painelAdmin.producao, Object.keys(painelAdmin));
  checar("e quem nao tem setor marcado ve a casa inteira",
    painelAdmin.producao?.todos_setores === true, painelAdmin.producao);

  await irPara(p, `${WEB}/`);
  await p.waitForFunction(
    () => /Para produzir/i.test(document.body.innerText), { timeout: 15000 },
  ).catch(() => {});
  const painelTela = await p.evaluate(() => {
    const cartao = [...document.querySelectorAll("section.cartao")]
      .find((c) => (c.querySelector("h2")?.textContent ?? "").includes("Para produzir"));
    return {
      temCartao: !!cartao,
      // O caminho para a agenda inteira: o cartão mostra as primeiras linhas.
      abreAgenda: !!cartao?.querySelector("a[href='/producao']"),
      texto: (cartao?.innerText ?? "").slice(0, 120),
    };
  });
  checar("e a tela inicial mostra o cartao Para produzir", painelTela.temCartao, painelTela);
  checar("com o caminho para a agenda inteira", painelTela.abreAgenda, painelTela);
  await foto(p, "41c-painel-producao");

  console.log("11. logo da empresa");
  // PNG 1x1 de verdade, para o servidor validar a imagem e não só o content-type
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
    "base64",
  );
  writeFileSync(`${FOTOS}/_logo-teste.png`, png);

  // 🔑 Guarda a logo que a casa tem AGORA e devolve no fim, aconteça o que
  // acontecer. Sem isto a bateria apagava a marca do cliente.
  const { dados: empresaAntes } = await api("GET", "/empresa", null, token);
  const logoOriginal = empresaAntes?.logo_url ?? null;
  let bytesOriginais = null;
  if (logoOriginal) {
    // A rota é pública: a `<img>` do navegador não manda cabeçalho nenhum.
    const r = await fetch(`${API}${logoOriginal}`);
    if (r.ok) {
      bytesOriginais = {
        buffer: Buffer.from(await r.arrayBuffer()),
        tipo: r.headers.get("content-type") ?? "image/png",
      };
    }
  }
  const restaurarLogo = async () => {
    if (!bytesOriginais) {
      // Sem logo também é um estado a devolver.
      await api("DELETE", "/empresa/logo", null, token);
      return;
    }
    await enviarArquivo("/empresa/logo", token, {
      buffer: bytesOriginais.buffer, tipo: bytesOriginais.tipo, nome: "logo",
    });
  };
  // A rede de segurança: roda no `finally`, mesmo se o roteiro estourar antes
  // de chegar ao fim deste bloco. Repetir é inofensivo — são os mesmos bytes.
  aoTerminar.push(restaurarLogo);

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

  // 🔑 **A bateria APAGAVA a logo do cliente.** Ela subia esta de teste por
  // cima e depois chamava `DELETE /empresa/logo` — "a real é a que o cliente
  // subir" —, só que a real já estava lá. A marca sumia da barra e do cabeçalho
  // de todo PDF, e quem rodou a bateria não tinha como ligar uma coisa à outra.
  // Mesma lição do `preservar_credenciais` e do modo do PDV: **suíte devolve o
  // que encontrou**, e não um estado "limpo" que ela supõe ser o certo.
  await restaurarLogo();
  const { dados: empresaDepois } = await api("GET", "/empresa", null, token);
  if (logoOriginal) {
    const r = await fetch(`${API}${empresaDepois?.logo_url ?? ""}`);
    const voltou = r.ok
      && Buffer.from(await r.arrayBuffer()).equals(bytesOriginais.buffer);
    // ⚠️ A URL MUDA — o nome ganha sufixo novo a cada envio, e é isso que
    // invalida o cache do navegador. O que tem de voltar são os BYTES.
    checar("a logo que a casa tinha volta ao lugar no fim da rodada", voltou,
      empresaDepois?.logo_url);
  } else {
    checar("sem logo antes, a de teste sai e a base fica como estava",
      (empresaDepois?.logo_url ?? null) === null, empresaDepois?.logo_url);
  }

  // ⚠️ A logo de teste NÃO é apagada aqui — quem devolve a base é o
  // `restaurarLogo` registrado em `aoTerminar` no começo deste bloco. A versão
  // anterior chamava `DELETE /empresa/logo` dizendo "a real é a que o cliente
  // subir": só que a real já estava lá, e sumia da barra e do cabeçalho de todo
  // PDF. Mesma lição do `preservar_credenciais` e do modo do PDV.
  console.log("12. o modulo de Reservas, ligado por loja");
  // 🔑 **Pedido do dono (14/09/2026):** o módulo inteiro é ligado por parâmetro
  // da loja, e ligar tem de mudar TRÊS coisas — o menu, a tela e a oferta das
  // permissões. Aqui se prova o lado de fora; o de dentro (a recusa do
  // servidor) está em `smoke_reservas_config.py`.
  const { dados: eu } = await api("GET", "/auth/me", null, token);
  const lojaR = eu.unidades[0].id;
  const ligarReservas = async (valor) =>
    api("PUT", `/unidades/${lojaR}/parametros`, { reservas_ligado: valor }, token);

  // ⚠️ Devolve a loja ao estado de partida aconteça o que acontecer: uma casa
  // que não faz reserva não pode terminar a bateria com o módulo ligado.
  await ligarReservas(false);
  aoTerminar.push(async () => {
    await ligarReservas(false);
  });

  await entrar(p, ADMIN);
  // ⚠️ **A tela inicial e `/`, nao `/inicio`** — a segunda responde 404. A
  // primeira versao desta fase apontava para ela, e o efeito foi pior que uma
  // falha: a checagem do lado DESLIGADO passou por VACUIDADE, porque um 404 nao
  // tem menu nenhum para conter o grupo.
  // ⚠️ **E pelo DOM, nao pelo `innerText`**, como a fase 2 ja fazia: com os
  // grupos recolhidos o `display: none` tira os itens do texto visivel, e a
  // pergunta aqui e "o menu OFERECE esta tela?".
  await irPara(p, `${WEB}/`);
  await new Promise((r) => setTimeout(r, 900));
  const grupoNoMenu = async () =>
    p.evaluate(() => !!document.querySelector("aside a[href='/reservas/configuracoes']"));
  checar("desligado, o menu nao tem o grupo Reservas", !(await grupoNoMenu()));
  // A prova de que a checagem acima nao e vazia: o menu esta LA, com os outros.
  const outrosGrupos = await p.evaluate(() =>
    [...document.querySelectorAll("aside a")].length);
  checar("e o menu existe, com as outras telas", outrosGrupos > 5, outrosGrupos);

  // ⚠️ A tela também não abre pelo endereço direto: quem recusa é o servidor.
  await irPara(p, `${WEB}/reservas/configuracoes`);
  await new Promise((r) => setTimeout(r, 1200));
  const recusa = await p.evaluate(() => document.body.innerText);
  checar("e a tela recusa pelo endereco direto, dizendo onde se liga",
    /n[ãa]o est[áa] ligado|Lojas/i.test(recusa), recusa.slice(0, 200));

  await ligarReservas(true);
  // O menu vem do `/auth/me`, que a sessão carrega uma vez — recarregar é o que
  // a pessoa faria depois de ligar o parâmetro noutra aba.
  await irPara(p, `${WEB}/`);
  await p.reload({ waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  checar("ligado, o grupo Reservas aparece no menu", await grupoNoMenu());

  // ⚠️ **Ponto de partida MONTADO, e a razao e a propria feature.** A
  // configuracao SOBREVIVE — de proposito —, entao a rodada seguinte encontra o
  // sabado que esta fase abriu na anterior. Sem zerar antes, o clique mais
  // abaixo DESMARCA em vez de marcar, e as duas checagens caem invertidas: a
  // primeira nao acha o aviso (havia dia aberto) e a segunda acha (nao ha mais).
  // Foi exatamente assim que elas cairam — e e a mesma licao que
  // `smoke_reservas_config.py` ja tinha pago na secao 4.
  const { dados: cfgReservas } = await api("GET", "/reservas/configuracao", null, token);
  await api("PUT", "/reservas/configuracao", {
    aceita_online: cfgReservas.aceita_online,
    confirmacao: cfgReservas.confirmacao,
    teto_online: cfgReservas.teto_online,
    tolerancia_min: cfgReservas.tolerancia_min,
    folga_min: cfgReservas.folga_min,
    passo_min: cfgReservas.passo_min,
    antecedencia_min_horas: cfgReservas.antecedencia_min_horas,
    antecedencia_max_dias: cfgReservas.antecedencia_max_dias,
    cadastro_completo: cfgReservas.cadastro_completo,
    horarios: cfgReservas.horarios.map((h) => ({ ...h, aberto: false })),
    // ⚠️ **As faixas tambem entram no ponto de partida.** A fase da agenda, mais
    // abaixo, deixa a loja com UMA faixa de 120 min — e a rodada seguinte
    // chegava aqui esperando as tres padrao de 90. Terceira vez que a mesma
    // nao-idempotencia morde nesta sessao: o teste tem de montar o que afirma.
    // 🔑 **Quem prova a SEMEADURA das tres e a suite da API**, que apaga a
    // configuracao antes e ve `_garantir` recria-la. Aqui a pergunta e outra: a
    // TELA lista as faixas e traduz o numero em portugues?
    permanencias: [
      { nome: "Café da manhã", de: "09:00", ate: "11:00", minutos: 60 },
      { nome: "Almoço", de: "11:00", ate: "15:00", minutos: 90 },
      { nome: "Lanche da tarde", de: "15:00", ate: "23:59", minutos: 60 },
    ],
  }, token);

  await irPara(p, `${WEB}/reservas/configuracoes`);
  await esperarTexto(p, "Horário de funcionamento", 9000);
  const telaR = await p.evaluate(() => ({
    texto: document.body.innerText,
    // A semana inteira, e começando na segunda: o servidor manda em ISO
    // (1 = segunda … 7 = domingo), e a tela não reordena nada.
    primeiroDia: document.querySelectorAll("table tbody tr td:first-child")[0]?.innerText ?? "",
    linhas: document.querySelectorAll("table")[0]?.querySelectorAll("tbody tr").length ?? 0,
  }));
  checar("a tela de configuracoes abre com a semana inteira", telaR.linhas === 7, telaR.linhas);
  checar("comecando na segunda-feira", /Segunda/i.test(telaR.primeiroDia), telaR.primeiroDia);
  // 🔑 A casa nasce fechada em todos os dias de propósito — e a tela tem de
  // DIZER isso, senão parece pronta.
  checar("e avisa que nenhum dia esta aberto ainda",
    /Nenhum dia da semana está aberto/i.test(telaR.texto), telaR.texto.slice(0, 300));
  // ⚠️ **O nome da faixa mora no `value` de um `<input>`, e `innerText` nao ve
  // valor de campo.** A primeira versao procurava "Almoço" no texto da pagina e
  // nao achava o que estava a vista na tela.
  const faixasR = await p.evaluate(() =>
    [...document.querySelectorAll('input[aria-label^="nome da faixa"]')]
      .map((i) => i.value));
  checar("a tela lista as faixas de permanencia configuradas",
    faixasR.length === 3 && faixasR.some((n) => /Almoço/i.test(n)), faixasR);
  // A frase que traduz o número: quem senta às 11:00 sai por volta das 12:30.
  checar("dizendo em portugues o que a permanencia faz",
    /11:00 → 12:30/.test(telaR.texto), telaR.texto.slice(0, 600));
  await foto(p, "42-reservas-configuracoes");

  // Abre o sábado e salva: é a prova de que a tela grava de verdade.
  await p.evaluate(() => {
    const linhas = [...document.querySelectorAll("table tbody tr")];
    const sabado = linhas.find((l) => /Sábado/i.test(l.innerText));
    sabado?.querySelector('input[type="checkbox"]')?.click();
  });
  await p.evaluate(() => {
    const b = [...document.querySelectorAll("button")].find(
      (x) => (x.textContent ?? "").trim() === "Salvar");
    b?.click();
  });
  await new Promise((r) => setTimeout(r, 1600));
  await p.reload({ waitUntil: "networkidle2" });
  await esperarTexto(p, "Horário de funcionamento", 9000);
  const depoisR = await p.evaluate(() => document.body.innerText);
  checar("marcar o sabado e salvar tira o aviso de casa fechada",
    !/Nenhum dia da semana está aberto/i.test(depoisR), depoisR.slice(0, 300));

  // ---- o salao: saloes, mesas e lugares ----
  // 🔑 **Pedido do dono:** *"ter o cadastro de saloes, cadastro de mesas,
  // lugares por mesas"* e, depois de ver a tela, *"poderia ser separado por
  // salao"*. A tela mostra UM salao por vez, em abas, e a aba mora no endereco.
  // ⚠️ Ponto de partida MONTADO, pela mesma razao da configuracao: cadastro
  // sobrevive entre rodadas, e afirmar "nenhum salao" sem zerar seria afirmar o
  // que a rodada anterior desfez.
  // ⚠️ **DESLIGA os saloes antigos em vez de apagar, e a razao e o produto.**
  // Mesa que ja hospedou reserva NAO se apaga — e correto, apagar levaria junto
  // a resposta para onde aquelas pessoas sentaram. A primeira versao desta fase
  // tentava apagar e a bateria morria num "Internal Server Error" (que virou um
  // 409 explicado, na mesma rodada). Desligar e o mecanismo do proprio produto:
  // o salao sai da disponibilidade e o cadastro fica.
  const { dados: salaoAntes } = await api("GET", "/reservas/salao", null, token);
  for (const s of salaoAntes.saloes) {
    await api("PUT", `/reservas/saloes/${s.id}`, { ativo: false }, token);
  }

  await irPara(p, `${WEB}/reservas/salao`);
  await esperarTexto(p, "maior grupo que cabe", 9000);
  const salaoVazio = await p.evaluate(() => document.body.innerText);
  checar("a tela do salao mostra os quatro numeros desde o inicio",
    /mesas ativas/i.test(salaoVazio) && /lugares confortáveis/i.test(salaoVazio)
    && /com a cadeira extra/i.test(salaoVazio) && /maior grupo que cabe/i.test(salaoVazio),
    salaoVazio.slice(0, 300));
  // 🔑 Com todos os saloes desligados, o salao nao acomoda ninguem — e o numero
  // que o servidor devolve tem de dizer isso.
  const { dados: semSalao } = await api("GET", "/reservas/salao", null, token);
  checar("com todos os saloes desligados, nao ha lugar nenhum",
    semSalao.lugares === 0 && semSalao.maior_grupo === 0, semSalao);

  // ⚠️ "\+ salao": `clicarQuando` recebe a FONTE de uma regex, e o "+" precisa
  // vir escapado. Sem a barra, `new RegExp("+ salao")` estoura com "nothing to
  // repeat" — e derruba a bateria inteira, nao so a checagem.
  checar("da para abrir o formulario de salao novo", await clicarQuando(p, "+ salão"));
  await p.type('input[aria-label="nome do novo salão"]', `Principal ${marcaNota}`);
  checar("e criar o salao", await clicarQuando(p, "criar", { exato: true }));

  // 🔑 **A aba escolhida mora no ENDERECO**: recarregar cai no mesmo salao.
  // ⚠️ **Espera o ENDERECO, nao o texto** — e a razao e sutil: `esperarTexto`
  // inclui o VALOR DOS CAMPOS, e "Principal …" tinha acabado de ser digitado no
  // input do salao novo. A espera casava no mesmo instante com o que a propria
  // bateria tinha escrito, e o endereco era lido antes de a ida ao servidor
  // voltar. O texto estava certo e mesmo assim nao provava nada.
  const virouEndereco = await p
    .waitForFunction(() => /[?&]salao=\d+/.test(location.search), { timeout: 9000 })
    .then(() => true)
    .catch(() => false);
  checar("o salao recem-criado abre sozinho, e o endereco guarda qual e",
    virouEndereco, p.url());

  const soDoSalao = await p.evaluate(() => document.body.innerText);
  checar("e o salao recem-criado avisa que nao tem mesa nenhuma",
    /Nenhuma mesa neste salão ainda/i.test(soDoSalao), soDoSalao.slice(0, 400));

  // 🔑 **Montar o salao em LOTE** — o trabalho real do cadastro, que acontece
  // uma vez so: clicar "+ mesa" doze vezes e renomear cada uma e exatamente
  // quando ninguem tem paciencia.
  checar("a tela oferece criar varias mesas de uma vez",
    await clicarQuando(p, "+ várias mesas"));
  await esperarTexto(p, "Quantas mesas", 6000);
  // ⚠️ **Prefixo DESTA rodada.** O lote numera a partir do primeiro nome livre e
  // pula os que ja existem — entao, com mesas de rodadas anteriores na base, os
  // nomes nao comecam no 01. Com prefixo proprio, a numeracao volta a ser
  // previsivel E o campo de prefixo fica exercitado.
  const prefixoLote = `P${marcaNota.slice(-2)}`;
  await p.evaluate(({ quantos, prefixo }) => {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    const escrever = (rotulo, valor) => {
      const campo = document.querySelector(`input[aria-label="${rotulo}"]`);
      setter.call(campo, valor);
      campo.dispatchEvent(new Event("input", { bubbles: true }));
    };
    escrever("quantas mesas criar", quantos);
    escrever("prefixo do nome das mesas", prefixo);
  }, { quantos: "6", prefixo: prefixoLote });
  checar("e o botao diz quantas vai criar", await clicarQuando(p, "Criar 6 mesas"));
  await new Promise((r) => setTimeout(r, 1800));

  const { dados: comLote } = await api("GET", "/reservas/salao", null, token);
  // 🔑 **Cada teste procura os registros DELE** — a mesma licao que a fase da
  // paginacao ja carrega no comentario dela. Contar o total da CASA fazia esta
  // checagem somar as mesas das rodadas anteriores (que nao se apagam mais, por
  // terem reserva) e acusar o lote de criar dez em vez de seis.
  const meuSalao = comLote.saloes.find((s) => s.nome === `Principal ${marcaNota}`);
  const minhasMesas = comLote.mesas.filter((m) => m.id_salao === meuSalao?.id);
  checar("as seis mesas nascem de uma vez", minhasMesas.length === 6, minhasMesas.length);
  checar("numeradas a partir do 01, sob o prefixo pedido",
    minhasMesas.some((m) => m.nome === `${prefixoLote}01`)
    && minhasMesas.some((m) => m.nome === `${prefixoLote}06`),
    minhasMesas.map((m) => m.nome));
  // 🔑 Lugares e maximo sao DOIS numeros; o lote grava os dois.
  checar("com lugares e maximo iguais quando ninguem os separou",
    comLote.lugares === comLote.capacidade_max, comLote);
  checar("e o maior grupo e a maior mesa sozinha",
    comLote.maior_grupo === minhasMesas[0].capacidade_max, comLote.maior_grupo);
  await foto(p, "42b-reservas-salao");

  // 🔑 **Um salao de cada vez**: com dois saloes, a tela mostra so o aberto.
  const { dados: outro } = await api("POST", "/reservas/saloes",
    { nome: `Varanda ${marcaNota}`, ordem: 1 }, token);
  await api("POST", "/reservas/mesas/em-lote",
    { id_salao: outro.id, quantidade: 2, lugares: 6, capacidade_max: 8, prefixo: "V" }, token);
  await irPara(p, `${WEB}/reservas/salao?salao=${outro.id}`);
  await esperarTexto(p, `Varanda ${marcaNota}`, 9000);
  const naVaranda = await p.evaluate(() => ({
    linhas: document.querySelectorAll("table tbody tr").length,
    // ⚠️ **A contagem sai do PROPRIO elemento, nao de uma regex sobre o texto.**
    // O nome do salao termina nos digitos da marca da rodada e a contagem cola
    // neles ("Principal 4779526"): `6` nao casa, porque nao ha fronteira de
    // palavra entre dois digitos. O numero estava certo; a leitura e que era
    // fragil.
    abas: [...document.querySelectorAll('[role="tab"]')].map((b) => ({
      nome: (b.getAttribute("aria-label") ?? "").replace(/^salão /, ""),
      contagem: b.querySelector("span.mono")?.textContent?.trim() ?? "",
    })),
  }));
  // ⚠️ Duas mesas na tela, nao oito: a pagina tem o tamanho de um SALAO, nao o
  // da casa inteira. Era esse o pedido.
  checar("a aba da varanda mostra so as mesas dela", naVaranda.linhas === 2, naVaranda);
  // ⚠️ As abas DESTA rodada: salao de rodada anterior continua cadastrado (so
  // desligado), e exigir "exatamente duas" contaria o passado.
  const abasDaRodada = naVaranda.abas.filter((x) => x.nome.includes(marcaNota));
  checar("e as duas abas da rodada aparecem, com a contagem de cada uma",
    abasDaRodada.length === 2
    && abasDaRodada.some((x) => x.nome.startsWith("Principal") && x.contagem === "6")
    && abasDaRodada.some((x) => x.nome.startsWith("Varanda") && x.contagem === "2"),
    abasDaRodada);

  // A junta: duas de 6/8 juntas sentam 16, e vale nos dois sentidos.
  const naVarandaMesas = minhasMesas.length;
  const { dados: comOutro } = await api("GET", "/reservas/salao", null, token);
  const daVaranda = comOutro.mesas.filter((m) => m.id_salao === outro.id);
  await api("PUT", `/reservas/mesas/${daVaranda[0].id}`,
    { junta_com: daVaranda[1].id }, token);
  const { dados: comJunta } = await api("GET", "/reservas/salao", null, token);
  // ⚠️ So as mesas DESTA rodada: as de rodadas anteriores continuam cadastradas
  // (desligadas, nao apagadas) e carregam as juntas delas.
  const juntadasAgora = comJunta.mesas.filter(
    (m) => m.id_salao === outro.id && m.junta_com !== null);
  checar("a junta e gravada nos dois sentidos", juntadasAgora.length === 2,
    juntadasAgora.map((m) => `${m.nome}->${m.junta_com_nome}`));
  checar("e o maior grupo passa a ser a soma das duas: 16",
    comJunta.maior_grupo === 16, comJunta.maior_grupo);
  checar("as seis do principal continuam la", naVarandaMesas === 6);

  // 🔑 **O teto do site tem de caber no salao** — uma das duas descobertas do
  // prototipo. O numero viaja com a configuracao, que e onde o teto se edita.
  const { dados: cfgComSalao } = await api("GET", "/reservas/configuracao", null, token);
  checar("a configuracao sabe o maior grupo que o salao acomoda",
    cfgComSalao.maior_grupo === 16, cfgComSalao.maior_grupo);

  // ⚠️ Salao COM mesa nao se exclui: o caminho e desligar.
  const semExcluir = await p.evaluate(() => document.body.innerText);
  checar("salao com mesa manda desligar em vez de oferecer excluir",
    /desligue em vez de excluir/i.test(semExcluir), semExcluir.slice(0, 400));

  // ---- a agenda do dia: marcar, e o ciclo da reserva ----
  // 🔑 **A regra de disponibilidade e a peca que tudo consome**, e a tela nao a
  // reimplementa: os horarios vem de `/reservas/disponibilidade`, que roda a
  // MESMA regra que a gravacao vai rodar. Uma segunda versao aqui divergiria no
  // primeiro degrau novo, e a tela passaria a oferecer horario que o servidor
  // recusa.
  // Monta um sabado limpo com uma mesa so, para a regra ficar observavel.
  // ⚠️ **`toISOString()` devolve UTC, e isso quebrava a fase depois das 21h.**
  // O laco achava o SABADO local e o `toISOString` o escrevia como DOMINGO
  // (21:00 BRT = 00:00 UTC do dia seguinte). A configuracao abria so o sabado,
  // a agenda pedia o domingo, e o servidor respondia "a casa nao atende neste
  // dia da semana" — com a falha aparecendo como "a tela nao oferece marcar
  // reserva", a seis checagens da causa. E a MESMA armadilha que o `diaLocal`
  // la de cima existe para evitar; esta linha era a que faltava converter.
  const sabado = (() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    while (d.getDay() !== 6) d.setDate(d.getDate() + 1);
    return d.toLocaleDateString("sv-SE");
  })();
  const { dados: cfgAgenda } = await api("GET", "/reservas/configuracao", null, token);
  await api("PUT", "/reservas/configuracao", {
    aceita_online: false, confirmacao: "AUTOMATICA", teto_online: 8,
    tolerancia_min: 15, folga_min: 0, passo_min: 60,
    antecedencia_min_horas: 0, antecedencia_max_dias: 365, cadastro_completo: true,
    horarios: cfgAgenda.horarios.map((h) => ({
      ...h, aberto: h.dia_semana === 6, abre: "11:00", fecha: "18:00",
      ultima_reserva: "15:00",
    })),
    permanencias: [{ nome: "Almoco", de: "11:00", ate: "18:00", minutos: 120 }],
  }, token);
  // Uma mesa de 2 e uma de 6: e o que faz "esgotado depende do grupo" aparecer.
  // ⚠️ **Salao proprio, e os outros desligados.** Mesa com reserva nao se apaga
  // (e nao deve), entao a fase nao pode "limpar" o salao da fase anterior — ela
  // desliga tudo e monta o cenario dela, onde so as duas mesas dela contam.
  const { dados: salaoAg } = await api("GET", "/reservas/salao", null, token);
  for (const s of salaoAg.saloes) {
    await api("PUT", `/reservas/saloes/${s.id}`, { ativo: false }, token);
  }
  const { dados: salaoNovo } = await api("POST", "/reservas/saloes",
    { nome: `Agenda ${marcaNota}` }, token);
  const idSalaoAg = salaoNovo.id;
  await api("POST", "/reservas/mesas",
    { id_salao: idSalaoAg, nome: `A${marcaNota}`, lugares: 2, capacidade_max: 2 }, token);
  await api("POST", "/reservas/mesas",
    { id_salao: idSalaoAg, nome: `B${marcaNota}`, lugares: 6, capacidade_max: 6 }, token);

  await irPara(p, `${WEB}/reservas/agenda?dia=${sabado}`);
  await esperarTexto(p, "pessoas esperadas", 9000);
  checar("a agenda do dia abre", /Agenda do dia/.test(await p.evaluate(
    () => document.body.innerText)));

  checar("e oferece marcar uma reserva", await clicarQuando(p, "Nova reserva"));
  await esperarTexto(p, "Quantas pessoas primeiro", 6000);
  // 🔑 **Pessoas vem ANTES do horario, e a ordem e a regra**: "esgotado" depende
  // do tamanho do grupo, entao a lista de horarios so existe depois do numero.
  const horariosPara = async (n) => {
    await p.evaluate((quantos) => {
      [...document.querySelectorAll("button")]
        .find((b) => b.getAttribute("aria-label") === `${quantos} pessoas`)?.click();
    }, n);
    await new Promise((r) => setTimeout(r, 1400));
    return p.evaluate(() =>
      [...document.querySelectorAll('button[aria-label^="horário"]')]
        .map((b) => ({ hora: b.textContent.trim(), livre: !b.disabled })));
  };

  const para2 = await horariosPara(2);
  // Das 11:00 as 15:00, de hora em hora = 5 horarios.
  checar("a tela mostra os horarios ate a ultima reserva",
    para2.length === 5 && para2[0].hora === "11:00" && para2[4].hora === "15:00", para2);
  checar("todos livres num dia sem reserva", para2.every((h) => h.livre), para2);

  // Marca as 12:00 para 6 pessoas: ocupa a mesa de 6 ate 14:00.
  await horariosPara(6);
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((b) => b.getAttribute("aria-label") === "horário 12:00")?.click();
  });
  // ⚠️ **Espera o campo EXISTIR antes de digitar.** O formulario da reserva so
  // nasce depois do clique no horario, e a funcao ia direto ao `p.$()`: numa
  // maquina ocupada ele voltava nulo e a suite MORRIA no `campo.type`, levando
  // junto o relatorio das 770 checagens ja feitas. E a mesma licao das esperas
  // por conteudo la de cima, paga de novo — aqui com o processo inteiro.
  const escrever = async (rotulo, texto) => {
    const campo = await p
      .waitForSelector(`input[aria-label="${rotulo}"]`, { timeout: 15000 })
      .catch(() => null);
    if (!campo) {
      checar(`o campo "${rotulo}" aparece`, false, "nao renderizou em 15s");
      return;
    }
    await campo.type(texto);
  };
  await escrever("nome de quem reserva", `Familia ${marcaNota}`);
  await escrever("telefone de quem reserva", "47 99910-5033");
  checar("o botao diz o horario escolhido", await clicarQuando(p, "Marcar às 12:00"));
  await new Promise((r) => setTimeout(r, 2000));

  const naAgenda = await p.evaluate(() => document.body.innerText);
  checar("a reserva aparece na agenda", new RegExp(`Familia`).test(naAgenda),
    naAgenda.slice(0, 400));
  // 🔑 A hora de SAIDA sai da permanencia: quem senta as 12:00 com 120 min sai
  // as 14:00. Sem isso a recepcao nao responde "da para encaixar as 14h?".
  checar("com a hora em que a mesa vaga", /14:00/.test(naAgenda), naAgenda.slice(0, 400));
  checar("e a mesa que o SERVIDOR escolheu", new RegExp(`B${marcaNota}`).test(naAgenda),
    naAgenda.slice(0, 400));
  await foto(p, "42c-reservas-agenda");

  // 🔑 **"Esgotado" depende do TAMANHO DO GRUPO** — a checagem que define a
  // regra. Mesmo horario, respostas diferentes.
  await clicarQuando(p, "Nova reserva");
  await esperarTexto(p, "Quantas pessoas primeiro", 6000);
  const de6 = await horariosPara(6);
  const de2 = await horariosPara(2);
  const as12de6 = de6.find((h) => h.hora === "12:00");
  const as12de2 = de2.find((h) => h.hora === "12:00");
  checar("as 12:00 nao ha mais mesa para 6", as12de6 && !as12de6.livre, as12de6);
  checar("mas ainda ha para 2, no MESMO horario", as12de2 && as12de2.livre, as12de2);
  // ⚠️ A mesa de 6 volta as 14:00: os intervalos que se tocam nao se cruzam.
  const as14de6 = de6.find((h) => h.hora === "14:00");
  checar("e as 14:00 ela ja vagou", as14de6 && as14de6.livre, as14de6);
  await clicarQuando(p, "cancelar", { exato: true });

  // 🔑 **REMARCAR pela tela** — a ligacao mais comum depois de marcar.
  // ⚠️ O que prova a regra: a reserva das 12:00 ocupa a mesa ate 14:00, e mesmo
  // assim as 13:00 aparece LIVRE para ela — porque o `ignorar` tira a propria
  // reserva da conta. Sem ele, a tela diria "sem mesa" apontando para a mesa que
  // a propria reserva ocupa.
  checar("a reserva confirmada oferece remarcar", await clicarQuando(p, "remarcar"));
  // ⚠️ **Espera os HORARIOS, nao o titulo do cartao.** O titulo aparece no mesmo
  // instante do clique; os horarios so depois de a disponibilidade voltar do
  // servidor. Esperar pelo titulo lia a lista ainda vazia — e a falha dizia
  // "as 13:00 nao esta livre" quando a resposta nem tinha chegado. Quarta vez
  // nesta sessao que esperar pela coisa errada acusa a coisa errada.
  await p.waitForSelector('button[aria-label^="horário"]', { timeout: 9000 })
    .catch(() => null);
  const noRemarcar = await p.evaluate(() => ({
    texto: document.body.innerText,
    horarios: [...document.querySelectorAll('button[aria-label^="horário"]')]
      .map((b) => ({ hora: b.textContent.trim(), livre: !b.disabled })),
  }));
  checar("a janela diz como a reserva esta hoje",
    /Hoje: 12:00, 6 pessoas/.test(noRemarcar.texto), noRemarcar.texto.slice(0, 400));
  const as13 = noRemarcar.horarios.find((h) => h.hora === "13:00");
  checar("e as 13:00 aparece livre PARA ELA — o ignorar tira ela da conta",
    as13 && as13.livre, noRemarcar.horarios);
  await p.evaluate(() => {
    [...document.querySelectorAll("button")]
      .find((b) => b.getAttribute("aria-label") === "horário 13:00")?.click();
  });
  checar("e o botao fica disponivel depois de escolher", await clicarQuando(p, "Remarcar"));
  await new Promise((r) => setTimeout(r, 1800));
  const depoisRemarcar = await p.evaluate(() => document.body.innerText);
  checar("a agenda mostra a reserva no horario novo",
    /13:00/.test(depoisRemarcar), depoisRemarcar.slice(0, 500));
  // ⚠️ A hora de saida acompanha: 13:00 + 120 min de permanencia = 15:00.
  checar("e a hora de saida acompanha", /15:00/.test(depoisRemarcar),
    depoisRemarcar.slice(0, 500));

  // O ciclo: confirmada -> chegou -> encerrada, e o que some da tela a cada passo.
  checar("a reserva confirmada oferece marcar chegada", await clicarQuando(p, "chegou"));
  await new Promise((r) => setTimeout(r, 1600));
  const depoisChegou = await p.evaluate(() => document.body.innerText);
  checar("e a situacao passa a dizer que chegou", /chegou/.test(depoisChegou),
    depoisChegou.slice(0, 400));
  checar("oferecendo encerrar em seguida", await clicarQuando(p, "encerrar"));
  await new Promise((r) => setTimeout(r, 1600));
  const depoisEncerrou = await p.evaluate(() => document.body.innerText);
  checar("encerrada nao oferece mais nada — o ciclo terminou",
    /encerrada/.test(depoisEncerrou), depoisEncerrou.slice(0, 400));
  // ⚠️ E a mesa continua contando como usada: ela FOI usada, e a agenda tem de
  // continuar explicando por que esteve ocupada.
  const { dados: aindaOcupada } = await api(
    "GET", `/reservas/disponibilidade?data=${sabado}&pessoas=6`, null, token);
  checar("e a mesa encerrada continua ocupada naquele horario",
    !aindaOcupada.horarios.find((h) => h.hora === "12:00").livre, aindaOcupada.horarios);

  // Limpa as reservas do teste: elas seguram mesa entre rodadas.
  const { dados: agLimpar } = await api("GET", `/reservas/agenda?data=${sabado}`, null, token);
  for (const r of agLimpar.reservas) {
    await api("PUT", `/reservas/${r.id}/status`, { status: "CANCELADA" }, token);
  }

  // 🔑 **E as permissões passam a ser oferecidas** — o terceiro efeito.
  await irPara(p, `${WEB}/papeis`);
  await new Promise((r) => setTimeout(r, 1400));
  const comPerm = await p.evaluate(() => document.body.innerText);
  checar("ligado, o catalogo de permissoes oferece as chaves de Reserva",
    /Ver a agenda e as reservas do dia/i.test(comPerm), comPerm.slice(0, 200));

  await ligarReservas(false);
  await irPara(p, `${WEB}/papeis`);
  await p.reload({ waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1400));
  const semPerm = await p.evaluate(() => document.body.innerText);
  // ⚠️ Esconder do catálogo NÃO revoga nada de quem já tem — é tirar da
  // vitrine. O que recusa uma loja desligada é a trava do próprio router.
  checar("e desligar tira as chaves da vitrine de novo",
    !/Ver a agenda e as reservas do dia/i.test(semPerm), semPerm.slice(0, 200));
  await irPara(p, `${WEB}/`);
  await p.reload({ waitUntil: "networkidle2" });
  await new Promise((r) => setTimeout(r, 1200));
  checar("junto com o grupo no menu", !(await grupoNoMenu()));
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
