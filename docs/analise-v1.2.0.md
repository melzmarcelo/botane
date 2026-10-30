# Análise do sistema — v1.2.0 (30/10/2026)

🔑 **Pedido do dono (30/10/2026):** *"uma análise detalhada de todo o sistema, inclusive o de
reservas, validando layouts, informações, segurança. Apontando melhorias e possíveis problemas.
Pode implementar o que achar sem perguntar, e ao fim pode promover para a produção. Vamos
iniciar uma nova versão do sistema, a v1.2.0."*

## Como foi feita

| Frente | O que se olhou |
|---|---|
| Erros reais | O registro de erros do AR (`erros_sistema`, pelo conector): 12 registros, todos da API |
| Segurança | Cada uma das 524 rotas da API e a proteção dela (levantamento automático); rotas públicas uma a uma; SQL montado com texto; HTML montado no site; login, recuperação de senha, sessão; cabeçalhos; dependências (`npm audit`, `pip-audit`) |
| Informação | O painel e os alertas do AR; o CMV da semana corrente até a causa |
| Layout | ~70 telas do sistema no celular (390 px) e no computador (1366 px): rolagem horizontal, texto quebrado (`undefined`, `NaN`, `[object Object]`), erros de console e chamadas que falharam; o site do cliente local e o do AR |
| Código | `pyflakes` na API inteira; `tsc` no front |

As ferramentas ficaram no repositório: `web/scripts/varrer-telas.mjs` (todas as telas, celular e
computador, com relatório em `web/scripts/_capturas/relatorio.json`) e `web/scripts/varrer-site.mjs`.

## Corrigido nesta versão

| # | Gravidade | Achado | Correção |
|---|---|---|---|
| 1 | 🔴 Crítica | **Next.js 16.3.8 com falhas conhecidas de execução remota de código sem login** (GHSA-2464-fhr4-w9xw, GHSA-673q-mjm6-r5xr) e negação de serviço (GHSA-p3m5-59mp-jv5r) | Next 16.4.3; `npm audit --omit=dev` zerado |
| 2 | 🔴 Alta | **Pillow 12.3.0 com 39 falhas conhecidas** — é quem abre as imagens enviadas (logo, fotos, Cardápio Vivo) | Pillow 13.0.0; `pip-audit` zerado |
| 3 | 🟠 Alta | **Conexão morta com o banco derrubava pedidos** — no AR, `/saude` em 500 com "SSL SYSCALL error: EOF detected" e, no rollback, "connection already closed" (26/10). O pool entregava ao próximo pedido a conexão que o banco já tinha fechado | `database.py`: keepalive de TCP; `SELECT 1` antes de usar a conexão parada há mais de 30 s; a quebrada sai do pool em vez de voltar; o rollback dela não levanta outro erro por cima. Testado matando a conexão do lado do servidor |
| 4 | 🟠 Alta | **Sem conexão = sair da conta.** Ao abrir o sistema, QUALQUER falha do `/auth/me` apagava a sessão: celular sem sinal, o app aberto offline, a API trocando de contêiner no deploy (os ~4 min da promoção), o banco com a conexão caída (item 3) ou uma navegação que cortava o pedido. A pessoa digitava a senha de novo sem ter feito nada. Achado porque a própria varredura de telas caía no login | `lib/sessao.tsx`: só 401/403 encerram; o resto mostra "Sem conexão com o sistema agora — sua sessão continua aberta", tenta de novo a cada 5 s e abre sozinho. `verificar-sessao-sem-conexao.mjs` (5) na bateria |
| 5 | 🟠 Alta | **A mesma coisa na renovação**: com o acesso vencido, um 500/503 no `/auth/refresh` era lido como sessão recusada | `lib/api.ts`: `renovar` só devolve "acabou" em 401/403; o resto é erro de "tente de novo" |
| 6 | 🟡 Média | **Auditoria mostrava `whatsapps: [object Object]`** no resumo do antes/depois | Lista vira "N itens"; objeto, o JSON curto |
| 7 | 🟡 Média | **CMV negativo sem dizer por quê.** No AR, a semana de 26/10 está em −R$ 5,3 mil (food cost −26,8%): um inventário achou **+R$ 6,7 mil** a mais do que o sistema tinha (saídas antigas sem a entrada). A conta está certa — devolve o consumo contado a mais nas semanas anteriores —, mas a tela só dava as causas possíveis | O aviso do Painel de CMV diz a causa com o número quando são os ajustes de inventário |
| 8 | 🟢 Baixa | **Link do site sem prévia** — compartilhado no WhatsApp/Instagram, aparecia o endereço cru | Tags Open Graph no site (nome, frase, logo) e `GET /publico/marca/logo`, endereço fixo da logo |
| 9 | 🟢 Baixa | **"Esta é a primeira versão."** no rodapé da reserva (quando a casa confirma pelo WhatsApp) — falava do sistema, e o cliente lia como site inacabado | "A reserva é confirmada pelo WhatsApp.", nas três línguas |

## Verificado e em ordem

- **Toda rota protegida.** 430 exigem permissão; 45 exigem login e conferem a permissão por dentro
  quando gravam ou exportam (`estoque/saidas`, `exportar/*`); as 49 públicas são as esperadas
  (site, cardápio da mesa, webhook, login, OAuth/MCP, `/saude`, `/arquivos`).
- **Sem injeção de SQL**: todo trecho montado com texto (`ORDER BY {ordem}`, `{coluna}`) usa valor
  fixo do próprio código, nunca o que veio da requisição.
- **Site sem injeção de HTML**: o que vem da API passa por `esc()` antes do `innerHTML`; as telas
  (React) não usam `dangerouslySetInnerHTML`.
- **Login**: trava por tentativas (gravada fora da transação que recusa), sessão rotativa com graça
  de 30 s só para rotação (o logout vale na hora). **Esqueci a senha**: resposta igual para e-mail
  existente ou não, limite por hora.
- **Rotas públicas por telefone** (reserva, "Suas reservas", fidelidade): dica mascarada do nome,
  limite de tentativas por origem com a origem guardada em hash; o "basta o telefone" é decisão do
  dono de 24/09/2026, com a consequência registrada.
- **Pedidos da mesa** com limite por sessão; **chamar o garçom** com um chamado aberto por mesa e
  tipo; **webhook do WhatsApp** só com a assinatura do app.
- **Cabeçalhos** de segurança nos dois lados (HSTS, moldura só do próprio site, `nosniff`,
  `Referrer-Policy`, `Permissions-Policy`); `/arquivos` com `nosniff`, PDF isolado e
  redimensionamento em larguras fixas com cache.
- **Layout**: nenhuma tela com rolagem horizontal no celular nem no computador; nenhum
  `undefined`/`NaN` na tela (só o `[object Object]` da auditoria, corrigido).
- **Código**: `pyflakes` sem nome indefinido; `tsc` limpo.

## Recomendações (não implementadas — e por quê)

### Dados da operação (é trabalho da casa, não do código)
- **55 produtos com saldo negativo** e **2.158 saídas com custo provisório**: é a origem dos CMVs
  estranhos. Cada negativo é uma entrada que faltou (nota não lançada, produção não apontada) ou
  uma contagem. Atacar pelos de maior valor (Estoque ▸ situação "negativo").
- **427 produtos de produção própria sem ficha homologada** e **254 rascunhos já em uso**: sem
  ficha não há custo teórico (cobertura de ficha está em 35%); sem cadastro completo, o estoque
  não converte unidades.
- **Semana de 19 a 25/10 ainda aberta** e **meta de food cost não definida** (o painel fica sem
  referência).
- **17 notas abertas**, 2 paradas por item sem produto e 2 conciliadas sem lançar (R$ 862,06).

### Segurança, com custo maior que o benefício hoje
- **CSP que restringe script** pediria nonce em cada página do Next; a CSP atual fecha moldura,
  `<base>`, plugin e formulário. Fica para quando houver motivo (por exemplo, conteúdo de terceiros
  na tela).
- **Sessão em `localStorage`**: um XSS levaria o token. Mitigado por não haver HTML injetado
  (verificado acima); mover para cookie `HttpOnly` exige refazer o fluxo de sessão do front e do
  conector.
- **3 falhas "altas" em dependências de DESENVOLVIMENTO** (ferramentas de teste) — não sobem para
  o ar.

### Limpeza
- 18 importações sem uso na API (`pyflakes`). Nenhuma muda comportamento.
