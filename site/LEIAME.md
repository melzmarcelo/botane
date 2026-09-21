# O site do cliente — `reserva.botanedeliecafe.com.br`

> Esboço, 21/09/2026. **Pedido do dono:** *"agora vamos criar o site para o
> cliente, onde o front será separado... Os itens serão: Reserva, Catálogos
> cadastrados e ativos, Entre em Contato (onde vai abrir o whatsapp para enviar
> mensagem para o número cadastrado para a empresa). Montar assim e depois vamos
> melhorando."*

É o **terceiro artefato** da casa, ao lado de `api/` e `web/`:

| | quem usa | onde mora |
|---|---|---|
| `web/` | a equipe | `sistema.botanedeliecafe.com.br` |
| `site/` | **o cliente** | `reserva.botanedeliecafe.com.br` |
| `api/` | os dois | `sistema.botanedeliecafe.com.br/api` |

## As três portas

```
      ╭──────────────────────────────╮
      │   capa oliva · "Aberto agora"│
      │          ( Botané )          │   ← o medalhão, 92px
      ╰──────────────────────────────╯
            Botané Deli e Café
          Ter · Qua · Qui · Sex · Sáb

   🗓️  Reservar uma mesa            ›   (destaque)
   📖  Catálogo de Encomendas       ›   → abre o PDF
   💬  Entre em contato             ›   → abre o WhatsApp
```

## A cara: o protótipo, linha a linha

🔑 **Pedido do dono (21/09/2026):** *"deixa mais próximo ao protótipo que foi proposto em
`apresentacao/reservas-prototipo.html`, utilizando a logo cadastrada, os catálogos colocar
tudo na página inicial, no estilo apresentado, e ao clicar no botão, abrir o catálogo."*

A capa de 128px com os dois gradientes radiais sobre o oliva, o **medalhão redondo de 92px**
descendo 34px por cima dela, a tarja de estado no canto, e a lista de `.item` com ícone à
esquerda e subtítulo embaixo. As fontes são as de lá — **Fraunces** nos títulos, **Karla** no
corpo, **DM Mono** nas miudezas.

🔑 **Os catálogos são ITENS DA PÁGINA INICIAL**, um por cardápio, e clicar **abre o PDF**.
Antes era uma tela separada com uma lista dentro; o protótipo já os mostrava no hub.

⚠️ **A logo cadastrada vira o medalhão.** Sem ela, ele desenha o nome da casa, como o
protótipo — inventar uma imagem seria pior, o cliente veria a marca de outra pessoa. Sobe em
Administração ▸ Empresa.

⚠️ **A capa NÃO usa `empresa.cor_primaria`, e isso foi medido na tela.** A cor cadastrada é um
verde vivo que o sistema interno usa como acento sobre fundo claro; chapada numa capa de 128px
ela briga com o medalhão escuro e afasta o site justamente do protótipo, que é terroso.

## Por que um `index.html` e não um app

🔑 **São três telas que leem a API.** Um arquivo que abre direto carrega mais
rápido no celular de quem está na rua do que qualquer bundle, publica como site
estático (mais barato que um componente Node no App Platform) e não tem build
para quebrar numa promoção.

⚠️ **Isto é uma decisão de hoje, não para sempre.** No dia em que o site ganhar
login do cliente, "minhas reservas" e histórico, vale o app — e aí a troca é de
hospedagem e de arquivo, não de backend: a API já está pronta e é a mesma.

## Como rodar aqui

```powershell
cd site
python -m http.server 3200
```

E abrir <http://127.0.0.1:3200>.

⚠️ **Não abra o `index.html` com duplo clique.** Por `file://` a origem é `null`,
o CORS barra tudo e a tela fica bonita e vazia — sem cardápio, sem horário e sem
o WhatsApp da casa. Tem de ser servido por HTTP.

⚠️ **A porta 3200 está na lista do CORS** (`api/.env`, `CORS_ORIGINS`). Mudando a
porta, mude lá também — senão o navegador bloqueia e não explica na tela.

## O que ele lê

Tudo vem de `/publico/{loja}/...`, o único router da casa sem permissão:

| rota | para quê |
|---|---|
| `/publico/1/casa` | nome, endereço, telefone e o **WhatsApp** do botão de contato |
| `/publico/1/catalogos` | os cardápios `ATIVO`, dentro do período **e com PDF** |
| `/publico/1/horarios?dia=…&pessoas=…` | os horários com mesa, pela mesma regra da agenda |

🔑 **A loja sai do `<html data-loja="1">`.** No dia em que houver duas casas com
reserva, cada uma publica o seu com o número dela — sem tocar no código.

## O que já faz, e o que ainda não

- ✅ **Cardápios** — cada um é um item da página inicial, e clicar abre o PDF.
- ✅ **Entre em contato** — abre a conversa no WhatsApp com mensagem pronta.
  🔑 `wa.me` é **só um link**: não exige WhatsApp Business API, provedor nem
  modelo aprovado. O esboço de reservas deixou o WhatsApp "para depois" pensando
  no envio automático de confirmação — *abrir* a conversa custa isto.
  ⚠️ **Sem número cadastrado o site DIZ isso**, em vez de mostrar um botão que não
  leva a lugar nenhum. Sai de Administração ▸ Empresa ▸ WhatsApp, e o servidor
  limpa a máscara: o cadastro aceita "(47) 99910-5033" e o `wa.me` só aceita
  dígitos.
- 🟡 **Reserva** — mostra os horários que a casa tem livres, de verdade, pela
  mesma regra da agenda do balcão. **Ainda não grava**: ao escolher o horário, o
  site monta a mensagem pronta para o WhatsApp.
  ⚠️ **A tela não promete o que não faz.** Dizer "reservado" faria o cliente
  aparecer na porta sem mesa.

## O que falta para a reserva fechar sozinha

1. **Identificar quem reserva** — o esboço já decidiu: `fornecedores` é a tabela
   de pessoas, e a chave é o telefone.
2. **Conter abuso.** Esta é a diferença entre ler e gravar: uma rota pública que
   CRIA registro precisa de limite por telefone e por origem, senão o salão
   amanhece lotado de reservas que ninguém fez.
3. **A trava de concorrência já existe** (`_travar_o_dia`, por loja e dia): duas
   pessoas reservando o mesmo horário ao mesmo tempo é o caso que define a
   arquitetura, e ele está resolvido desde a migração 070.

## Para publicar

1. Um componente de **site estático** no App Platform, servindo esta pasta, com
   o domínio `reserva.botanedeliecafe.com.br`.
2. ⚠️ **Acrescentar esse domínio a `CORS_ORIGINS`** da API, no painel. Sem isso o
   site sobe, abre e não carrega nada — e o navegador não diz por quê na tela.
   É a volta do CORS que o esboço previu ao escolher front separado: hoje `web` e
   `api` dividem o domínio e o problema não existe.
3. `deploy_on_push: false` vale aqui também — a promoção é um ato consciente.
