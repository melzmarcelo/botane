# Catálogo simples com abertura e cartões, e a aba Pré-visualização — estudo (30/10/2026)

🔑 **Pedido do dono (30/10/2026):** *"quando o catálogo é somente um catálogo, eu gostaria de ter
uma imagem e mensagem de abertura assim como adicionar cartões, mas sem vídeo; isto seria
habilitado somente se ele fosse um Cardápio Vivo. Sendo assim, caso o catálogo seja somente um
catálogo, este pode esconder as opções que só têm no Cardápio Vivo. E gostaria que no cadastro de
catálogos tivesse uma aba pré-visualização, onde podemos ver como este será exibido online, com as
funcionalidades de teste."*

## Decisões (aprovadas: "pode seguir com as recomendações")

| # | Pergunta | Decisão |
|---|---|---|
| 1 | Abertura no catálogo simples | **Bloco de capa** no topo da página do cardápio no site (imagem com a mensagem por cima), que rola junto — não tela cheia. |
| 2 | Destaque (★) e esgotado | **Valem também no site**: esgotado não pode ser pedido em lugar nenhum. |
| 3 | Cartões no catálogo simples | Foto, título e texto, **sem vídeo**, entre os pratos no mesmo lugar do feed. Mesmos dados (`catalogo_cartoes`). |
| 4 | O que é só do Cardápio Vivo | Escondido no catálogo simples: vídeo (prato, seção, cartão), horário de exibição da seção, objetivo, margem, A/B e atenção. Aviso curto apontando a Publicação. |
| 5 | Pré-visualização | Aba nova em todo catálogo de produtos: o que vai ao ar (feed se Vivo; site se simples), mesmo em rascunho ou fora do período, celular/computador, e **modo teste**: carrinho, cesta e "enviar" que o servidor confere e responde o total **sem gravar pedido**. |

## Ordem

1. Servidor: o cardápio público do site traz a abertura, os cartões (sem vídeo), destaque e
   esgotado; prévia com login para qualquer situação; envio de pedido em modo teste (confere e
   não grava). Suítes.
2. Site (`site/index.html` + cópia): capa, cartões, ★ e esgotado; modo prévia/teste.
3. Cadastro: esconder o que é só do Vivo; aba Pré-visualização. Bateria do navegador.
