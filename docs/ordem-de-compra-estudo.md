# Ordem de Compra — estudo

🔑 **Pedido do dono (23/11/2026):** *"Inicia um estudo para adicionarmos Ordem de Compra no
botane. Onde o usuario adiciona itens que precisam ser comprar, informa a quantidade e um
observação opcional. E conforme estes pedidos vão sendo compras estes podem ir saindo da lista
e entram em outra como comprado."*

Estado: **etapa 1 construída em 23/11/2026** (1.3.16, migração 158), com as quatro recomendações
da seção 8, e **etapa 2 em 24/11/2026** (1.3.18): sugestões do mínimo na própria tela, atalhos no
painel e nos alertas, e só produtos comprados (produzido e kit ficam fora, pedido do dono). O
"selo já na lista" ficou dentro da janela de sugestões, não no painel. O que foi decidido está em
`docs/memoria/compras.md`; as etapas 3 a 5 seguem por fazer.
Abaixo, o estudo como foi escrito, com um ajuste: `voltar` recebe uma lista de ids
(`POST /ordens-compra/voltar`), para o "desfazer" de uma compra em lote ser uma operação só.

Estado original: **análise, nada construído.** O módulo Compras hoje começa quando a nota chega.
Este estudo cobre o que vem antes dela: alguém percebe que falta, alguém compra.

---

## 1. A ideia em uma frase

Uma **lista viva por loja**, com duas abas: **A comprar** e **Comprados**. Cada linha anda
sozinha, sem esperar as outras.

```
  alguém pede            quem compra marca            a nota chega (já existe)
 ┌────────────┐         ┌────────────┐              ┌──────────────────────┐
 │ A COMPRAR  │ ──────▶ │  COMPRADO  │ ┄┄┄┄┄┄┄┄┄┄▶  │ conferir → lançar    │
 └────────────┘         └────────────┘  (etapa 4)   │ (só aqui vira estoque)│
       │  ▲                   │                     └──────────────────────┘
       │  └── voltar à lista ─┘
       ▼
   CANCELADO
```

### O que ela NÃO é

- 🔑 **Comprado não é recebido, e não mexe no estoque.** Só a nota lançada entra no razão
  (regras 1 e 3 do `CLAUDE.md`). Marcar "comprado" é um aviso entre pessoas. Por isso errar aqui
  é barato e desfazer é um clique.
- **Não decide custo.** O preço de verdade vem da nota, e `custos.py` continua sendo o único
  lugar que sabe quanto custa um insumo.
- **Não é "Pedidos".** Esse nome já é do cardápio (`pedidos`, `pedidos.ver`). No código e na
  tela o termo é sempre **ordem de compra**, para ninguém procurar no lugar errado.

## 2. O que o Botané já tem e a Ordem de Compra aproveita

| Já existe | Onde | Uso aqui |
|---|---|---|
| Quem está abaixo do mínimo, quanto falta, consumo por dia, cobertura em dias, fornecedor preferido, e se a ação é **comprar ou produzir** | `painel_estoque.py` | Botão "pôr na lista" (etapa 2) |
| Alerta "Abaixo do estoque mínimo", que já se descreve como *"a base da lista de compras"* | `alertas.py`, `alertas/page.tsx` | Mesmo botão |
| Unidades de compra com fator (CX de 12 = 12) | `produto_unidades` | Pedir em CX, FD, KG |
| De quem se compra, código, embalagem, último preço, preferencial | `produto_fornecedor` | Sugerir fornecedor e agrupar |
| WhatsApp, prazo, dias de entrega e pedido mínimo do fornecedor | `fornecedores` | Mandar o pedido (etapa 3) |
| Assistente no WhatsApp com prévia e botão Confirmar | `assistente_acoes.py` | "Acabou a farinha" (etapa 5) |

O `MAPEAMENTO.md` já previa na fase 2 *"cotação, pedido de compra, conferência de recebimento"*.
Este estudo entrega a primeira parte disso, sem cotação.

## 3. Como funciona na tela

Nova entrada no menu **Compras ▸ Ordem de compra** (`/compras/ordens`).

```
┌ Ordem de compra ──────────────────────────────────── Matriz ┐
│ [ A comprar (12) ]   [ Comprados ]                           │
│                                                              │
│ Produto [ farinha de trigo…  ]  Qtd [ 2 ] [ FD ▾ ]           │
│ Observação [ opcional                     ]      [Adicionar] │
│ ──────────────────────────────────────────────────────────── │
│ ☐ Farinha de trigo    2 FD   "a de sempre"   Ana · hoje 09:10│
│ ☐ Leite integral     12 L                    Beto · ontem    │
│ ☐ Guardanapo (fora do cadastro)  3 PCT       Ana · ontem     │
│ ──────────────────────────────────────────────────────────── │
│ 2 selecionados                        [ Marcar como comprado ]│
└──────────────────────────────────────────────────────────────┘
```

- **Adicionar** em três campos, com Enter, e o foco volta ao produto. Quem lembra de cinco
  coisas lança as cinco sem abrir janela.
- **Marcar comprado** por linha ou em várias de uma vez. A linha sai da aba e aparece um
  "desfazer" na hora.
- **Comprados:** filtro por período, quem comprou e fornecedor. Dali se pode **voltar à lista**.
- **Celular é o caso principal:** quem marca está no mercado ou no fornecedor. Lista em cartões,
  com alvo de toque de 44 px (`docs/ux-estudo.md`).
- **Imprimir** a lista, seguindo o padrão da casa (PDF em aba, nunca "Baixar"). Observação e
  quantidade entram no relatório na mesma entrega.

## 4. Os casos que decidem o desenho

1. **Comprou só parte.** Pediram 10, havia 6. A linha se divide: 6 vão para Comprados e 4
   continuam em A comprar, ligadas por `id_item_origem`. Sem isso, ou o resto some, ou alguém
   precisa redigitar.
2. **Duas pessoas pedem o mesmo.** Ao adicionar, a tela avisa *"já tem 5 L pedidos por Ana"* e
   oferece **somar** ou **manter separado**. Avisa, não bloqueia: pode ser para outro uso, e a
   observação diz qual.
3. **Duas pessoas compram o mesmo.** Marcar lê a linha com `FOR UPDATE`. Quem chega depois recebe
   409 *"Beto já marcou às 10:42"*, em vez de um segundo "comprado" calado.
4. **Item fora do cadastro.** O funcionário não vai parar para cadastrar guardanapo. A linha
   aceita texto livre, e como não entra no estoque, isso não suja nada.
5. **Produto produzido pela casa.** Molho da cozinha não se compra. A busca avisa e aponta para a
   agenda de produção, a mesma separação que os alertas já fazem.
6. **Produto inativo ou fundido.** Inativo não é oferecido na busca. Se uma fusão absorver um
   produto com linha aberta, a linha passa para o sobrevivente (ver seção 6).

## 5. Modelo de dados (rascunho, migração 158)

Uma tabela só. Cada linha é um item, sem cabeçalho de documento, porque o pedido descreve itens
que saem um a um. Se a casa quiser um documento para o fornecedor, ele é gerado a partir das
linhas (etapa 3).

```sql
CREATE TABLE IF NOT EXISTS ordem_compra_itens (
    id              bigserial PRIMARY KEY,
    id_unidade      integer NOT NULL REFERENCES unidades(id),
    id_produto      integer REFERENCES produtos(id),      -- nulo = fora do cadastro
    descricao_livre varchar(160),
    quantidade      numeric(18,4) NOT NULL CHECK (quantidade > 0),
    um              varchar(6) NOT NULL REFERENCES unidades_medida(sigla),
    observacao      varchar(300),
    status          varchar(12) NOT NULL DEFAULT 'A_COMPRAR'
                    CHECK (status IN ('A_COMPRAR', 'COMPRADO', 'CANCELADO')),
    id_item_origem  bigint REFERENCES ordem_compra_itens(id),  -- compra parcial
    id_fornecedor   integer REFERENCES fornecedores(id),       -- opcional, ao comprar
    criado_em       timestamptz NOT NULL DEFAULT now(),
    criado_por      integer NOT NULL REFERENCES usuarios(id),
    comprado_em     timestamptz,
    comprado_por    integer REFERENCES usuarios(id),
    cancelado_em    timestamptz,
    cancelado_por   integer REFERENCES usuarios(id),
    CONSTRAINT ck_ordem_item_identificado CHECK (
        id_produto IS NOT NULL OR length(trim(coalesce(descricao_livre, ''))) > 0
    )
);
CREATE INDEX IF NOT EXISTS ix_ordem_a_comprar
    ON ordem_compra_itens (id_unidade, criado_em) WHERE status = 'A_COMPRAR';
CREATE INDEX IF NOT EXISTS ix_ordem_comprados
    ON ordem_compra_itens (id_unidade, comprado_em DESC) WHERE status = 'COMPRADO';
CREATE INDEX IF NOT EXISTS ix_ordem_produto ON ordem_compra_itens (id_produto);
```

**Permissões** (regra 4), duas chaves novas no grupo Compras:

| Chave | Permite | Para quem |
|---|---|---|
| `compras.ordem_solicitar` | Ver a lista, adicionar, editar e cancelar o **próprio** pedido | Toda a equipe |
| `compras.ordem_comprar` | Marcar comprado, voltar à lista, editar e cancelar **qualquer** linha | Quem compra |

**Rotas** (`routers/ordens_compra.py`, `services/ordens_compra.py`, `models/ordens_compra.py`):

```
GET    /ordens-compra?status=&de=&ate=&fornecedor=   lista paginada, da loja do seletor
POST   /ordens-compra                                adiciona
PUT    /ordens-compra/{id}                           corrige (só A_COMPRAR)
POST   /ordens-compra/comprar                        [{id, quantidade?, id_fornecedor?}]
POST   /ordens-compra/{id}/voltar                    volta à lista
POST   /ordens-compra/{id}/cancelar                  cancela
```

Sem `DELETE`: cancelar preserva quem pediu o quê, e as ações passam pela auditoria.

## 6. Armadilhas já conhecidas neste código

- ⚠️ **Fusão de produtos.** Tabela nova com `id_produto` precisa entrar em `_REAPONTAVEIS`, senão
  a linha aberta fica presa a um cadastro arquivado. É o mesmo tipo de falha da memória de
  Compras (10/09/2026).
- ⚠️ **Troca de unidade do produto.** `troca_de_unidade.py` converte mínimo, máximo e embalagens.
  Linha aberta guarda `um` própria e precisa ser tratada ou conferida ali.
- ⚠️ **Ligar à nota pelo ITEM quebraria.** A correção da nota manual (`routers/notas.py`) e a
  atualização vinda do Omie (`importador.atualizar_nota`) **apagam e reinserem** os `nota_itens`,
  então uma FK para o item perderia o vínculo a cada uma delas. Na etapa 4, o vínculo é com
  `id_nota` + produto.
- ⚠️ **"Abaixo do mínimo" pode não mostrar tudo.** A consulta parte de `estoque_saldos`, então
  produto com mínimo e **sem nenhuma linha de saldo** na loja não aparece, justamente o que
  mais falta. Conferir antes da etapa 2.
- ⚠️ **O mínimo é do produto, não da loja** (`produtos.estoque_minimo`). Com a segunda loja, a
  sugestão de quantidade usaria o mesmo número para as duas.
- ⚠️ **A sugestão precisa converter a unidade.** O painel calcula `faltam` em unidade de estoque;
  a compra é em CX ou FD. Arredondar **para cima** pela embalagem do `produto_unidades`.

## 7. Ordem de construção

| Etapa | Entrega | Resolve |
|---|---|---|
| **1. A lista** | Tabela, permissões, rotas, tela com as duas abas, compra parcial, imprimir, testes | **Todo o pedido do dono** |
| 2. Ligada ao estoque | "Pôr na lista" no painel e nos alertas, com quantidade sugerida; selo "já na lista" | Ninguém precisa lembrar |
| 3. Por fornecedor | Agrupar A comprar por fornecedor, aviso de pedido mínimo e dia de entrega, imprimir e mandar por WhatsApp | O pedido sai pronto |
| 4. Ligada à nota | Na conferência, mostrar "isto estava comprado" e fechar o ciclo como recebido | Comprado que nunca chegou |
| 5. Assistente | "Põe 2 fardos de farinha na lista" pelo WhatsApp e pelo conector, com confirmação | Pedir sem abrir o sistema |

A etapa 1 sozinha já é usável e não toca em estoque, custo, nota nem CMV, o que a torna uma
entrega de baixo risco. A migração só cria tabela e permissões, sem reescrever dado.

**Cobertura da etapa 1:** `smoke_ordens_compra.py` (ciclo, parcial, dupla marcação, permissões,
isolamento entre lojas, fusão e prova de que o saldo não muda) e `verificar-ordens-compra.mjs`
(fluxo na tela, inclusive em largura de celular).

## 8. O que o dono precisa decidir

| # | Pergunta | Recomendação |
|---|---|---|
| 1 | Lista contínua de itens, ou documento numerado (OC 123) com vários itens? | **Lista contínua.** É o que o pedido descreve; o documento pode nascer na etapa 3 |
| 2 | Aceita item fora do cadastro? | **Sim**, em texto livre |
| 3 | Toda a equipe pode pedir? Quem marca como comprado? | **Todos pedem; só quem tem a chave marca** |
| 4 | Ao marcar comprado, pede algo além? (fornecedor, valor) | **Fornecedor opcional, sem valor.** O valor certo vem da nota |

Compra parcial, aviso de repetido e "voltar à lista" entram na etapa 1 como descritos, salvo se o
dono preferir diferente.
