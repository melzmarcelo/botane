import puppeteer from "puppeteer-core";
const CHROME="C:/Program Files/Google/Chrome/Application/chrome.exe";
const WEB="http://127.0.0.1:3100", API="http://127.0.0.1:9200";
const PERFIL = process.argv[2] || "scripts/_chrome-perfil";
const login=await fetch(`${API}/auth/login`,{method:"POST",headers:{"Content-Type":"application/json"},
  body:JSON.stringify({email:"admin@botane.com.br",senha:"botane123"})}).then(r=>r.json());
const cab={"Content-Type":"application/json",Authorization:`Bearer ${login.access_token}`};
const m=String(Date.now()).slice(-5); const criados=[];
for(let i=0;i<25;i++){
  const r=await fetch(`${API}/produtos`,{method:"POST",headers:cab,
    body:JSON.stringify({nome:`Pag tela ${m}-${String(i).padStart(2,"0")}`,tipo:"INSUMO",um_estoque:"UN"})}).then(r=>r.json());
  criados.push(r.id);
}
const nav=await puppeteer.launch({executablePath:CHROME,headless:"new",userDataDir:PERFIL,
  args:["--no-sandbox","--window-size=1440,1000"],defaultViewport:{width:1440,height:1000},protocolTimeout:60000});
const p=await nav.newPage();
await p.goto(`${WEB}/login`,{waitUntil:"networkidle2"});
if (await p.$('input[type="email"]')) {
  await p.type('input[type="email"]',"admin@botane.com.br");
  await p.type('input[type="password"]',"botane123");
  await Promise.all([p.waitForNavigation({waitUntil:"networkidle2"}).catch(()=>{}),p.click('button[type="submit"]')]);
}
await new Promise(r=>setTimeout(r,1500));
const estado=async(rot)=>{
  const e=await p.evaluate(()=>({url:location.pathname+location.search,
    busca:document.querySelector('input[placeholder="nome, código ou código de barras"]')?.value??null,
    linhas:document.querySelectorAll("tbody tr").length,
    guardado:JSON.stringify(Object.fromEntries(Object.entries(localStorage).filter(([k])=>/pag|pp|produt/i.test(k))))}));
  console.log(`  ${rot.padEnd(30)} url=${e.url} busca="${e.busca}" linhas=${e.linhas}`);
  if (rot==="inicio") console.log(`     localStorage: ${e.guardado}`);
  return e;
};
await p.goto(`${WEB}/produtos`,{waitUntil:"networkidle2"});
await new Promise(r=>setTimeout(r,2000)); await estado("inicio");
await p.select('select[aria-label="Registros por página"]',"50").catch(()=>{});
await new Promise(r=>setTimeout(r,1600));
await p.goto(`${WEB}/fornecedores`,{waitUntil:"networkidle2"});
await new Promise(r=>setTimeout(r,1200));
await p.goto(`${WEB}/produtos`,{waitUntil:"networkidle2"});
await new Promise(r=>setTimeout(r,1800)); await estado("voltou de fornecedores");
await p.evaluate(()=>document.querySelector('button[aria-label="Próxima página"]')?.click());
await new Promise(r=>setTimeout(r,1400)); await estado("pagina 2");
const campo=(await p.$$('input[placeholder="nome, código ou código de barras"]'))[0];
await campo.type(`${m}-0`);
await new Promise(r=>setTimeout(r,4000)); await estado("apos digitar");
await nav.close();
for(const id of criados) await fetch(`${API}/produtos/${id}`,{method:"DELETE",headers:cab});
