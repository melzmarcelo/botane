# Os módulos do Botané

> O sistema pensado por área de negócio, e não por camada. Serve para responder
> três perguntas que apareciam toda vez: **o que eu leio antes de mexer aqui**,
> **o que eu rodo depois** e **onde isto mora**.

⚠️ **Os módulos são organização, não pastas.** O código continua onde sempre
esteve — `api/routers/`, `api/services/`, `web/app/(app)/`. Mover arquivo para
pasta de módulo mexeria em dezenas de imports e na ordem de declaração de rota
(que já custou um bug neste projeto) sem entregar nada que este documento não
entregue.

🔑 **A memória segue os módulos**, um arquivo por módulo em
[`docs/memoria/`](docs/memoria/). Antes de mexer num módulo, leia o arquivo dele
— é lá que estão os "já tentei assim e quebrou".

| Módulo | Memória | Suítes |
|---|---|---|
| [Cadastros](#cadastros) | `docs/memoria/cadastros.md` | `cadastros`, `pessoas`, `produto_do_omie`, `vinculo`, `conversao`, `acucar_500g`, `utensilios`, `troca_de_unidade`, `openfoodfacts`, `kits` |
| [Produção](#produção) | `docs/memoria/producao.md` | `fichas`, `producao` |
| [Compras](#compras) | `docs/memoria/compras.md` | `notas`, `ean_das_notas` |
| [Custos](#custos) | `docs/memoria/custos.md` | `memoria`, `lotes` |
| [Estoque](#estoque) | `docs/memoria/estoque.md` | `estoque`, `ajustes`, `inventario_filtros`, `transferencias`, `alertas`, `lotes` |
| [Vendas](#vendas) | `docs/memoria/vendas.md` | `vendas`, `consumo_pessoa`, `consumo_periodo`, `pdv_legal` |
| [Administrativo](#administrativo) | `docs/memoria/administrativo.md` | `fundacao`, `sessao`, `senha`, `lojas_do_usuario`, `setor_do_usuario`, `omie`, `agenda_omie`, `agenda_fuso`, `email_prazo` |
| [CMV](#cmv) | `docs/memoria/cmv.md` | `cmv`, `grupos_cmv`, `ciclos`, `relatorios` |
| _(transversal)_ | `docs/memoria/_transversais/` | `paginacao`, `exportacoes` |

---

## Cadastros

Produtos, pessoas e as tabelas de apoio — o que todo o resto referencia.

- **Rotas:** `produtos.py`, `fornecedores.py`, `cadastros.py`
- **Serviços:** `produtos_vinculo.py`, `kits.py`, `precos.py`, `troca_de_unidade.py`, `openfoodfacts.py`
- **Telas:** `produtos/`, `produtos/[id]/`, `produtos/duplicados/`, `produtos/ean-das-notas/`, `fornecedores/`, `cadastros/`
- **Permissões:** `cadastros.produtos`, `cadastros.fornecedores`, `cadastros.categorias`, `cadastros.setores`, `cadastros.locais`, `cadastros.unidades_medida`

⚠️ **"Pessoa" é `fornecedores`**, e a tabela não foi renomeada: desde a migração
055 ela guarda quem compra, quem trabalha e quem consome. `fornecedor = true`
distingue.

⚠️ **A unidade de estoque é o denominador de tudo** — trocá-la converte custo,
mínimo, máximo e as embalagens, e é recusada em produto que já tem razão.

## Produção

- **Rotas:** `fichas.py`, `producao_agenda.py`
- **Serviços:** `producao_agenda.py`, e o custo da ficha vive em `custos.py`
- **Telas:** `fichas/`, `producao/`
- **Permissões:** `fichas.visualizar`, `fichas.editar`, `fichas.homologar`, `fichas.custos`, `producao.agenda`

⚠️ **A ficha é versionada e o custo é congelado no uso** — recalcular depois
faria a produção de ontem mudar de valor sozinha.

## Compras

Notas de entrada: XML, digitação, conciliação e lançamento no razão.

- **Rotas:** `notas.py`
- **Serviços:** `nfe_xml.py`, `ean_das_notas.py`
- **Telas:** `compras/`, `compras/[id]/`, `compras/nova/`
- **Permissões:** `compras.notas`, `compras.conciliar`, `compras.lancar`

⚠️ **A nota só vira estoque no LANÇAMENTO**, não na importação: o XML entra como
documento, e é a conciliação item→produto que decide o que baixa.

## Custos

Tudo que decide quanto uma coisa custa.

- **Serviço central:** `custos.py` — **o único lugar que sabe quanto custa um insumo**
- **Também:** `precos.py`, `memoria_calculo.py`, o ajuste de custo em `ajustes.py`
- **Telas:** o cartão de custo em `produtos/[id]/custo.tsx`, os relatórios de memória

🔑 **A ordem de precedência é a da confiança:** custo médio do razão → último
preço do fornecedor → `produtos.custo_referencia`. O médio é o que a casa pagou;
a referência é o que outro sistema acha.

⚠️ **Custo em `numeric` com 6 casas, jamais float.**

## Estoque

Saldos, movimentos, ajustes, inventário e transferências entre lojas.

- **Rotas:** `estoque.py`, `ajustes.py`, `inventario.py`, `transferencias.py`, `alertas.py`
- **Serviços:** `estoque.py` (**a única porta de escrita no razão**), `ajustes.py`, `inventario_selecao.py`, `transferencias.py`, `alertas.py`
- **Telas:** `estoque/`, `ajustes/`, `inventario/`, `transferencias/`, `rede/`, `alertas/`
- **Permissões:** `estoque.saldos`, `estoque.entradas`, `estoque.saidas`, `estoque.perdas`, `estoque.ajuste`, `estoque.custo`, `estoque.inventario`, `estoque.inventario_criar`, `estoque.transferencias`, `estoque.transferencia_receber`, `estoque.retroativo`

⚠️ **`estoque_movimentos` é append-only.** Correção é estorno, nunca `UPDATE` ou
`DELETE` — e é por isso que trocar a unidade de um produto com razão é recusado.

## Vendas

- **Rotas:** `vendas.py`, `consumo.py`, `pdv.py`
- **Serviços:** `consumo_pessoa.py`, `consumo_periodo.py`, `services/pdv/`
- **Telas:** `vendas/`, `vendas/[id]/`, `vendas/lancar/`, `vendas/por-pessoa/`, `vendas/sem-vinculo/`, `consumo/`, `meu-consumo/`
- **Permissões:** `cmv.painel`, `cmv.relatorios`, `cmv.fechamento`, `consumo.periodos`

⚠️ **"Em aberto" é a venda SEM carimbo de período** (`vendas.id_consumo_periodo`),
nunca uma conta de datas.

⚠️ **Consumo de pessoa exige ciclo ABERTO** (08/09/2026) — venda de balcão, não.

## Administrativo

Empresa, lojas, parâmetros, integrações e usuários.

- **Rotas:** `empresa.py`, `usuarios.py`, `papeis.py`, `autenticacao.py`, `omie.py`, `email_config.py`, `historico.py`, `inicio.py`
- **Serviços:** `services/omie/`, `agenda_integracao.py`, `email.py`, `segredos.py`, `senhas.py`
- **Telas:** `empresa/`, `lojas/`, `usuarios/`, `papeis/`, `integracoes/`, `perfil/`, `auditoria/`, `trocar-senha/`
- **Permissões:** `admin.empresa`, `admin.unidades`, `admin.usuarios`, `admin.papeis`, `admin.integracoes`, `admin.auditoria`, `integracao.omie`, `integracao.pdv`

⚠️ **Credencial de integração é cifrada** (`segredos.py`) e **não se promove por
merge**: `api/.env` está fora do versionamento de propósito.

## CMV

- **Rotas:** `cmv.py`
- **Serviços:** `cmv.py`, `cmv_grupos.py`, `periodos.py`, `relatorios.py`, `memoria_calculo.py`
- **Telas:** `cmv/`
- **Permissões:** `cmv.painel`, `cmv.relatorios`, `cmv.fechamento`, `cmv.grupos`, `cmv.reabrir`

🔑 **`CMV real = estoque inicial + compras − estoque final`**, e o teórico sai da
ficha. A diferença entre os dois é a variância, que é o número que interessa.

---

## Transversal

O que não pertence a um módulo e atravessa todos. Fica em
[`docs/memoria/_transversais/`](docs/memoria/_transversais/).

| | |
|---|---|
| `padroes-de-ui.md` | paginação, modais, avisos, componentes |
| `exportacao-e-relatorios.md` | o catálogo de exportação (CSV/PDF) e seus filtros |
| `infra-e-deploy.md` | migrações, agendador, SMTP, App Platform |
| `geral.md` | lições de teste e o que não caiu em nenhum módulo |

- **Rotas:** `exportacoes.py`  ·  **Tela:** `exportacao/`
- **Serviços:** `exportacao.py`, `exportacao_catalogo.py`, `paginacao.py`

---

## Como usar isto

**Ao corrigir um defeito:** identifique o módulo pela tela ou pela rota, leia
`docs/memoria/<módulo>.md` **antes** de abrir o código, e rode as suítes daquele
módulo depois. A bateria inteira só antes de promover.

**Ao implementar algo novo:** o módulo diz onde a rota, o serviço e a tela devem
nascer, e qual arquivo de memória recebe a decisão no fim. Toda decisão que
custou caro vira entrada lá — é isso que impede o próximo de repetir.

⚠️ **Um recurso que cruza módulos existe e é normal** — a colheita de EAN nasce
em Compras e escreve em Cadastros; o consumo por pessoa é Vendas mas usa Custos.
Nesse caso a decisão vai na memória do módulo **dono da regra**, com um ponteiro
no outro.
