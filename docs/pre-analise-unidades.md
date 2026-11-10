# Pré-análise de unidades — produtos em rascunho

> Lote 1, feito em 05/10/2026 pelo conector de produção: INSUMOS em rascunho de **BOB…** a **COX…**
> (105 produtos). É sugestão a partir do NOME do produto — nada foi gravado.
> **Fator** = quantas unidades de ESTOQUE vêm em 1 unidade de COMPRA.
> "conferir" = o nome não diz o tamanho da embalagem; o número sai da nota.

## Regras usadas

1. **Ingrediente pesado na cozinha/confeitaria** → estoque em **KG**; compra no pacote; fator = peso do pacote em kg.
2. **Carne e hortifruti a granel** → estoque **KG**, compra **KG**, fator 1.
3. **Verdura vendida por maço ou cabeça** → estoque **UN**, compra **UN** (ou MC), fator 1.
4. **Bebida que se vende/usa inteira** (vinho, cerveja, lata) → estoque **UN**; compra **CX**; fator = unidades na caixa.
5. **Descartável e papelaria** → estoque **UN**; compra **CX/PCT**; fator = quantidade da embalagem.
6. **Líquido usado em dose** → estoque **L**; compra na garrafa/caixa; fator = litros.

## Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 3558 | BOB.PLAST.PICOTADA-40X60 | PC | UN | UN | 1 | bobina = 1 rolo; tipo deveria ser EMBALAGEM |
| 1816 | BROCOLIS | UN | UN | UN | 1 | por cabeça |
| 1307 | CACAU ALCALINO EM PO 1KG | UN | KG | PCT | 1 | |
| 1375 | CACAU EM PO 100% 500 GR SICAO | — | KG | PCT | 0,5 | provável duplicado do 19 |
| 1288 | CACAU EM PO ALCALINO (NAC) PCT 1KG | UN | KG | PCT | 1 | provável duplicado do 1307 |
| 337 | CACAU PO 500G 100% ALCALINO MAVALERIO | UN | KG | PCT | 0,5 | |
| 19 | CACAU PO 500G 100% SICAO | UN | KG | PCT | 0,5 | provável duplicado do 1375; ver também 1064 (lote 9) |
| 588 | CACHAÇA | UN | UN | UN | 1 | garrafa |
| 1920 | CAETANO VICENTINO CABERNET FRANC 6X750 ML | CX | UN | CX | 6 | estoque na garrafa |
| 1606 | CAETANO VICENTINO CABERNET SAUVIGNON:MERLOT 6X750 ML | CX | UN | CX | 6 | existe item de venda PDV separado (2298) — candidato a fusão |
| 1921 | CAETANO VICENTINO MALBEC 6X750 ML | CX | UN | CX | 6 | |
| 1624 | CALENDULA (IMP) PCT 500G | UN | KG | PCT | 0,5 | |
| 1825 | CANELA 6 CM PCT 1KG | UN | KG | PCT | 1 | |
| 1424 | CANELA EM PO PURA COFERPAN 1KG | UN | KG | PCT | 1 | |
| 2025 | CANELA EM PO PURA PREMIUM PCT 500G (CX 24UN) | UN | KG | PCT | 0,5 | segunda embalagem: CX = 12; o nome completo traz "PA PCT 500G": compra por pacote confirmada (regra 20) |
| 309 | CANELA MOIDA PCT 1KG | UN | KG | PCT | 1 | |
| 1211 | CANELA PO PURA 500G NUANCE | — | KG | PCT | 0,5 | |
| 479 | CANUDO PAPEL KRAFT 8MM - 10 X 200 (2000UN P/CX) | CX | UN | CX | 2000 | segunda embalagem: PCT = 200 |
| 1166 | CANUDO VEGETAL 20CM X 8MM - 20 X 100 (2000UN P/CX) | CX | UN | CX | 2000 | segunda embalagem: PCT = 100 |
| 577 | CAPSULA GAS P/CHANTILLY BEST WHIP | — | UN | CX | conferir | caixas de 10 ou 50; ver 1655 (lote 4), caixa de 10 |
| 2043 | CAQUI FUIU | KG | KG | KG | 1 | já está certo |
| 1621 | CARDAMOMO EM SEMENTE PCT 500G | UN | KG | PCT | 0,5 | |
| 1028 | CARMENERE ESTATE (TERRANOBLE) 2022 | — | UN | CX | conferir | provável caixa de 6 |
| 1367 | CARTA ENVELOPE FRASE PCTE 5UNIDADES | UN | UN | PCT | 5 | |
| 1364 | CARTAO 9X9 10UN NATURAL | PCT | UN | PCT | 10 | |
| 1922 | CASA DI NENI TANNAT: ALICANTE BOUSCHET 6X750 ML | UN | UN | CX | 6 | hoje já tem categoria VINHO ESPUMANTE e setor BAR |
| 3442 | CASCA DE LARANJA CRISTALIZADA CESARIN 5 KG | KG | KG | UN | 5 | balde de 5 kg |
| 1277 | CASTANHA DO PARA INTEIRA 1KG | UN | KG | PCT | 1 | |
| 1269 | CASTANHA DO PARA QUEBRADA 1KG | UN | KG | PCT | 1 | |
| 680 | CAST CAJU W1 240 TORRADA PCT 1KG | UN | KG | PCT | 1 | |
| 850 | CAST CAJU W1 240 T/S PCT 1KG | UN | KG | PCT | 1 | |
| 1371 | CAST PARA INTEIRA MEDIA PCT 1KG | UN | KG | PCT | 1 | provável duplicado do 1277 |
| 1313 | CATCHUP 1,033KG HEINZ | UN | KG | UN | 1,033 | |
| 1315 | CATCHUP DOYPACK 1,01KG HELLMANNS | UN | KG | UN | 1,01 | |
| 285 | CATCHUP HEINZ BAG 2,0KG | UN | KG | UN | 2 | |
| 1640 | CATCHUP HEMMER GALAO 3,8KG | KG | KG | GL | 3,8 | |
| 478 | CATCHUP TRAD 1KG HEMMER | UN | KG | UN | 1 | |
| 48 | CEBOLINHA P | — | UN | UN | 1 | maço; provável duplicado do 1487; **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 1487 | CEBOLINHA VERDE | UN | UN | UN | 1 | maço; hortifruti já tratado em 06/10 |
| 1479 | CENOURA | KG | KG | KG | 1 | já está certo; duplicado do 696; hortifruti já tratado em 06/10 |
| 696 | CENOURA KG | KG | KG | KG | 1 | já está certo; **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 1711 | CEREAL MAT NESTLE 120G | UN | UN | UN | 1 | se entrar em receita por peso: KG, fator 0,12 |
| 1734 | CEREJA | — | KG | KG | 1 | |
| 465 | CERV BITBURGER PILSE | — | UN | CX | conferir | unidades por caixa |
| 462 | CERV HOFBRAU ORIGINA | — | UN | CX | conferir | unidades por caixa |
| 1065 | CERVEJA BIERBAUM PILSEN/LAGER 600 ML | — | UN | CX | conferir | provável 12 |
| 1066 | CERVEJA BIERBAUM WEISS 600 ML | — | UN | CX | conferir | provável 12 |
| 1861 | CESTA DE BAMBU ALÇA GAUCHA 50X35CM | UN | UN | UN | 1 | não é insumo: embalagem/utensílio |
| 1300 | CESTA DE CAFÉ | UN | UN | UN | 1 | parece kit de venda, não insumo |
| 1306 | CESTA VIME 1 CRIS. | UN | UN | UN | 1 | embalagem/utensílio |
| 2010 | CHA BAER MATE 0,350L 6UN | — | UN | PCT | 6 | fardo de 6 |
| 489 | CHA BRANCO COM LICHIA E JASMIM LATA 269ML | UN | UN | CX | conferir | latas por caixa |
| 485 | CHA BRANCO COM PESSEGO 1L | UN | UN | UN | 1 | já está certo; bebida pronta de revenda, conta-se a garrafa (revisto em 07/10: antes sugeria L) |
| 635 | CHA BRANCO COM PESSEGO LATA 269ML | UN | UN | CX | conferir | latas por caixa |
| 636 | CHA PRETO COM CRANBERRY E HIBISCO LATA 269ML | UN | UN | CX | conferir | latas por caixa |
| 674 | CHALOSOFIA ATACADO LATA 50G | — | UN | UN | 1 | lata para revenda |
| 904 | CHALOSOFIA FOOD SERVICE 250G | — | KG | PCT | 0,25 | usado em infusão, por peso |
| 1897 | CHAMPIGNON | — | KG | KG | 1 | **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 528 | CHAMP VEUVE CLICQ 750ML | UN | UN | UN | 1 | já está certo |
| 1610 | CHANTILLY REFRIGERATTO FLEISCHMANN 1L | UN | L | UN | 1 | |
| 1010 | CHARDONNAY ESTATE (TERRANOBLE) 2023 | — | UN | CX | conferir | provável caixa de 6 |
| 1600 | CHA VERDE PREMIUM (IMP) PCT 1KG | UN | KG | PCT | 1 | |
| 1774 | CHOC GRANUL HAR 1,01KG | UN | KG | PCT | 1,01 | |
| 1189 | CHOC M.AMARGO NOBRE SICAO GOTAS 2,05KG | UN | KG | PCT | 2,05 | |
| 1391 | CHOCOLATE 70% KG | — | KG | KG | 1 | |
| 729 | CHOCOLATE GOTAS AMARGO 50,7% 2,01 KG CALLEBAUT | — | KG | PCT | 2,01 | |
| 1092 | CHOCOLATE GOTAS AMARGO 70% 1,01 KG SICAO | UN | KG | PCT | 1,01 | provável duplicado do 1243 (lote 9) |
| 752 | CHOCOLATE GOTAS AMARGO 70,5% 2,01 KG CALLEBAUT | UN | KG | PCT | 2,01 | |
| 989 | CHOCOLATE GOTAS BRANCO 2,05 KG SICAO | — | KG | PCT | 2,05 | provável duplicado do 1003 (lote 9) |
| 728 | CHOCOLATE GOTAS BRANCO VELVET 32% 2,01 KG CALLEBAUT | — | KG | PCT | 2,01 | |
| 1093 | CHOCOLATE GOTAS MEIO AMARGO 2,05 KG SICAO | KG | KG | PCT | 2,05 | estoque já certo; falta a compra; mesma família do 1977 (lote 9) |
| 1330 | CHOCOLATE GOTAS RUBY RB2 32,8% 2,5 KG CALLEBAUT | UN | KG | PCT | 2,5 | |
| 1082 | CHUCRUTE GRUETZMACHER 500G | — | KG | UN | 0,5 | |
| 1573 | CIL. DIOXIDO DE CARBONO 9KG | UN | UN | UN | 1 | cilindro; não é insumo de receita; duplicado do 1526 (lote 2) |
| 1801 | CN CREMEIRA | UN | UN | UN | 1 | utensílio, não insumo |
| 827 | COCO 1KG RALADO FINO PURO DIKOKO | — | KG | PCT | 1 | |
| 2100 | COCO FLOCADO SEM ACUCAR (NAC) PCT 1KG | UN | KG | PCT | 1 | |
| 1542 | COCO FLOCOS BRANCO C/ ACUCAR PCT 1KG | UN | KG | PCT | 1 | |
| 1494 | COCO FLOCOS QUEIMADO C/ ACUCAR PCT 1KG | UN | KG | PCT | 1 | |
| 73 | COENTRO | — | UN | UN | 1 | maço; duplicado do 1079; hortifruti já tratado em 06/10 |
| 1079 | COENTRO IRINEU UN | UN | UN | UN | 1 | maço; **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 1719 | COGUMELO | — | KG | KG | 1 | provável duplicado do 1519; **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 1519 | COGUMELO PARIS | — | KG | KG | 1 | hortifruti já tratado em 06/10; absorveu as bandejas (214, 745, 2160, 1719); fatores continuam pendentes |
| 214 | COGUMELO PARIS IN NATURA 1KG (INTEIRO) | UN | KG | UN | 1 | **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 745 | COGUMELO PARIS IN NATURA 300G | UN | KG | BDJ | 0,3 | **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 103 | COGUMELO SHITAKE IN NATURA 1KG (INTEIRO) | UN | KG | UN | 1 | |
| 2160 | COGUMELO SO FRESH 200G | UN | KG | BDJ | 0,2 | **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 899 | COLHER LITTLE COFEE 100UN | — | UN | PCT | 100 | |
| 1250 | COLOMBA PASCAL F. POMBA 500 GR C/50 | — | UN | PCT | 50 | parece forma de papel, 50 por pacote — conferir; ver 1252 (lote 4) |
| 967 | COMINHO MOIDO PCT 1KG | UN | KG | PCT | 1 | |
| 1617 | COND. PAPRICA PICANTE JANDIRA 250G | UN | KG | PCT | 0,25 | ver 1073 e 1317 (lote 7) |
| 1882 | COND. PIMENTA GRAO JANDIRA 1KG | UN | KG | PCT | 1 | |
| 1155 | COPA FATIADA CX30 UNI | — | KG | CX | conferir | frio fatiado vai em KG (regra 19); caixa com 30 envelopes — se forem de 80 g, como o presunto cru 1154, fator 2,4 (revisto em 07/10: antes sugeria UN) |
| 480 | COPO FIBRA DE BAMBU 270ML - 20 X 25 (500UN P/CX) | CX | UN | CX | 500 | segunda embalagem: PCT = 25 |
| 874 | COPO MINI QUADRATTO 40ML 10UN | — | UN | PCT | 10 | |
| 664 | COPO PLASTICO PP 330 ML C/50 UND | UN | UN | PCT | 50 | tampa: 663 (lote 9) |
| 662 | COPO PLASTICO PP 440 ML C/50 UND | UN | UN | PCT | 50 | tampa: 661 (lote 9) |
| 1222 | COSTELA PONTA DESOSSADA KG | KG | KG | KG | 1 | já está certo |
| 1237 | COSTELA PONTA RESFRIADA/COSTELA | KG | KG | KG | 1 | já está certo |
| 1118 | COSTELA RIPINHA CONGELADA/CUBOS | KG | KG | KG | 1 | já está certo |
| 15 | COSTELA SEM OSSO RESFRIADA | KG | KG | KG | 1 | já está certo; duplicado do 492 |
| 492 | COSTELA SEM OSSO RESFRIADA/INTEIRO | KG | KG | KG | 1 | já está certo |
| 1241 | COSTELA SERRADA CONGELADA/4 DEDO CX 10KG | KG | KG | KG | 1 | se a nota vier em caixa: CX = 10 |
| 399 | COUSCOUS MARROQUINO (TIPIAK) CX 500G | UN | KG | CX | 0,5 | |
| 1587 | COUVE FLOR | — | UN | UN | 1 | por cabeça; duplicado do 1984; hortifruti já tratado em 06/10 |
| 1984 | COUVE FLOR UN | UN | UN | UN | 1 | por cabeça; **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 1662 | COUVE MANTEIGA | — | UN | UN | 1 | maço; hortifruti já tratado em 06/10 |
| 1522 | COUVE MINEIRA | — | UN | UN | 1 | maço; provável duplicado do 1662; **fora da lista em 07/10** (absorvido na limpeza do hortifruti) |
| 112 | COUVE MIZUNA (IN) | UN | UN | UN | 1 | maço |
| 59 | COXA E SOBRECOXA SEM OSSO DE FRANGO RESF | KG | KG | KG | 1 | já está certo; ver também 455 (lote 2) e 1948 (lote 3) |
| 705 | COXA E SOB. TEMP PATO CONG CONFITADA 16X0,6KG (9,6KG) | KG | KG | CX | 9,6 | segunda embalagem: PCT = 0,6 |
| 1002 | COXAO DURO RESFRIADA/BIFE | KG | KG | KG | 1 | já está certo |
| 692 | COXAO DURO RESFRIADA/INTEIRO | KG | KG | KG | 1 | já está certo |
| 1975 | COXAO MOLE RESFRIADA/BIFE SEM CAPA | KG | KG | KG | 1 | já está certo |
| 3561 | CAJUN SPICE MIX BOMBAY VD 75 G | UN | KG | UN | 0,075 | **novo**: entrou no cadastro depois de 05/10; tempero em vidro, como os outros Bombay (3560, 3562, 3559) |

### Revisão do lote 1 — 07/10/2026

> Relido com as regras 7 a 26 e conferido contra a lista de hoje (offsets 50 a 149, duas chamadas de leitura).
> Nada foi gravado no sistema.

- **Mudaram de sugestão (3):** CACHAÇA (588) para UN, pela decisão dos destilados; CHA BRANCO COM PESSEGO 1L (485) de L para UN, por ser bebida pronta; COPA FATIADA (1155) de UN para KG, pela regra dos frios fatiados.
- **Saíram da lista (10):** 48, 696, 1897, 1079, 1719, 214, 745, 2160, 1984, 1522 — não aparecem mais entre os insumos ativos; batem com os cadastros absorvidos na limpeza do hortifruti de 06/10. As linhas ficaram na tabela, marcadas.
- **Já tratados no hortifruti (6):** 1487, 1479, 73, 1519, 1587, 1662 — hoje têm categoria e setor.
- **Entrou (1):** CAJUN SPICE MIX (3561), acima.
- **As demais 86 linhas continuam valendo**; onde havia par em outro lote, a observação ganhou a referência.
- Os vinhos do lote (Caetano Vicentino, Casa di Neni, Terranoble, Veuve Clicquot) não são de mesa: ficam em UN, como já estavam.

## Lote 2 — COXAS… a ESPONJA…

> Feito em 07/10/2026 pelo conector de produção: INSUMOS em rascunho de **COXAS…** a **ESPONJA…**
> (77 produtos; `buscar_produtos` tipo INSUMO, offsets 150 a 249). Nada foi gravado.
> A busca vem em ordem alfabética com ATIVO e RASCUNHO misturados; os ativos ficam de fora.
> Próximo lote começa no offset 250.

### Regras acrescentadas

7. **Limpeza e utensílio** (desinfetante, esponja, escova, dispenser) → estoque **UN**, contado por frasco/peça; compra **UN** ou **PCT**. O tipo deveria ser MATERIAL_LIMPEZA ou UTENSILIO.
8. **Pote pequeno com EAN de varejo** (doce de leite 50 g / 450 g) → tratado como revenda: estoque **UN**, compra **CX**. Se entrar em receita por peso: KG, fator = peso do pote.

### Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 455 | COXAS E SOBRECOXAS SEM OSSO DE FRANGO RESF PCT | KG | KG | KG | 1 | já está certo; duplicado do 59 |
| 421 | CRANBERRY DESIDRATADO INTEIRO PCT 1KG | UN | KG | PCT | 1 | |
| 1133 | CRANBERRY FATIADO 1KG | CX | KG | PCT | 1 | o CX de hoje parece engano |
| 27 | CRAVO DA INDIA EM FLOR INTEIRO (NAC) PCT 500G | UN | KG | PCT | 0,5 | |
| 808 | CRAVO MOIDO PCT 1KG | UN | KG | PCT | 1 | |
| 11 | CREAM CHEESE BS 1,2KG CX6UN | UN | KG | BS | 1,2 | o nome completo diz "P/A BS 1,2KG": a venda é por bisnaga; segunda embalagem: CX = 7,2 (corrigido no lote 8) |
| 65 | CREME DE AVELA BALDE 3KG- SC | UN | KG | UN | 3 | balde de 3 kg |
| 1054 | CREME DE LEITE 17 1,03KG PIRACANJUBA | UN | KG | UN | 1,03 | se a ficha usa em volume: L, com o litro na nota |
| 66 | CREME DE PISTACHE CARAVELLA BALDE 3KG- SC | UN | KG | UN | 3 | balde de 3 kg |
| 1867 | CREME LEITE (NATA) 46% GORD BLD 3,5KG | UN | KG | UN | 3,5 | balde de 3,5 kg |
| 1795 | CREMOR TARTATO 50G MIX | UN | KG | UN | 0,05 | |
| 1379 | CRIS. MARGARIDA SORTIDA | — | UN | UN | 1 | parece flor (crisântemo) de decoração, não insumo — conferir se vem em maço ou vaso |
| 938 | CRIS.MARGARIDA VYRON- | — | UN | UN | 1 | idem |
| 935 | CRIS.PINOQUIO ROSA- | — | UN | UN | 1 | idem |
| 1750 | CR LEITE TIROL 200G | UN | KG | UN | 0,2 | caixinha; se a nota vier em caixa fechada, conferir quantas |
| 60 | CUPIM A RESFRIADA | KG | KG | KG | 1 | já está certo; duplicado do 804 |
| 804 | CUPIM RESFRIADA/INTEIRO | KG | KG | KG | 1 | já está certo |
| 3560 | CURCUMA PO BOMBAY MINI PET 200 G | UN | KG | UN | 0,2 | existe ATIVO 965 (ACAFRAO EM PO - CURCUMA 1KG) — candidato a fusão |
| 966 | CURRY MOIDO (C/ 12 ICMS) PCT 1KG | UN | KG | PCT | 1 | |
| 1642 | CX 30X11CM | UN | UN | UN | 1 | caixa de embalagem; tipo deveria ser EMBALAGEM |
| 1177 | CX PANETONE 500GR 18X18X20 C/10 | — | UN | PCT | 10 | embalagem |
| 807 | DAMASCO DOCE TURCO N.2 CX 12,5KG | UN | KG | CX | 12,5 | os cinco damascos N.2 (807, 1282, 1504, 1347, 823) são o mesmo produto em embalagens diferentes — candidatos a fusão |
| 1282 | DAMASCO DOCE TURCO N.2 PCT 1KG | UN | KG | PCT | 1 | |
| 1504 | DAMASCO DOCE TURCO N.2 PCT 5KG | UN | KG | PCT | 5 | |
| 1852 | DAMASCO DOCE TURCO N.4 CX 12,5KG | UN | KG | CX | 12,5 | calibre N.4, não é o mesmo do N.2 |
| 1347 | DAMASCO TURCO N2- 1KG | UN | KG | PCT | 1 | provável duplicado do 1282 |
| 823 | DAMASCO TURCO N 2 DAG FOOD 12.50KG | CX | KG | CX | 12,5 | provável duplicado do 807 |
| 1778 | DESINCRUSTANTE CONCENTRADO MASTERCRUST 5L | UN | UN | UN | 1 | galão; material de limpeza |
| 3638 | DESINF GIRANDO SOL 5L LA | UN | UN | UN | 1 | galão; material de limpeza |
| 1764 | DESMOLDANTE SPRAY ECO CERA DE ABELHA UNTAFACIL 400ML | UN | UN | UN | 1 | já está certo; spray não se dosa |
| 1941 | DESMOLDANTE UX 100 PRODIPANI 600ML | — | UN | UN | 1 | |
| 1526 | DIOXIDO DE CARBONO 9KG ONU 1013 | UN | UN | UN | 1 | cilindro; duplicado do 1573 (lote 1) |
| 986 | DISP P.T INTERF PRETO FUME | UN | UN | UN | 1 | dispenser de papel toalha: utensílio, não insumo |
| 1670 | DISP P.T INTER VELADO | UN | UN | UN | 1 | idem |
| 759 | DOCE DE LEITE 200G | — | UN | CX | conferir | pote de revenda; potes por caixa |
| 515 | DOCE DE LEITE 450G | UN | UN | CX | conferir | pote de revenda; potes por caixa |
| 511 | DOCE DE LEITE 4,6KG - FOOD SERVICE | UN | KG | UN | 4,6 | balde, usado em receita |
| 513 | DOCE DE LEITE 50G | UN | UN | CX | conferir | pote de revenda; potes por caixa |
| 446 | DOCE DE LEITE BALDE | KG | KG | UN | conferir | estoque já certo; peso do balde sai da nota |
| 514 | DOCE DE LEITE C/PISTACHE 450G | UN | UN | CX | conferir | pote de revenda |
| 512 | DOCE DE LEITE C/PISTACHE 50G | UN | UN | CX | conferir | pote de revenda |
| 829 | DOCE DE LEITE DE OVELHA | KG | KG | UN | conferir | estoque já certo; peso do pote sai da nota |
| 1059 | DOCE DE LEITE PURO MU-MU 4,75KG | KG | KG | UN | 4,75 | estoque já certo; falta a compra |
| 389 | DOCE LEITE VACALIM 450G | UN | UN | CX | conferir | pote de revenda; se entrar em receita: KG, fator 0,45 |
| 803 | DORSO PATO S/PESC C/SAMB CONG VG (16KG) | KG | KG | CX | 16 | estoque já certo; falta a compra |
| 833 | DRAGEA DE CASTANHA DE CAJU | KG | KG | KG | 1 | já está certo |
| 834 | DRAGEA DE MACADAMIA | KG | KG | KG | 1 | já está certo |
| 1392 | DRAGEAS DIVERSAS | KG | KG | KG | 1 | já está certo |
| 1657 | ECOBAG LINHO | — | UN | UN | 1 | artigo de venda, não insumo |
| 1171 | EDAMAME EM GRAOS PCT 1KG CONG - 10 X 1 | KG | KG | CX | 10 | segunda embalagem: PCT = 1 |
| 1341 | EDAMAME EM GRÃOS PRÉ COZIDO ***1 KG*** | — | KG | PCT | 1 | provável duplicado do 1171 |
| 283 | EDAMAME EM GRÃOS PRÉ COZIDO 500G | PCT | KG | PCT | 0,5 | |
| 826 | EDAMAME NA VAGEM PREMIUM C/ SAL 500G | PCT | KG | PCT | 0,5 | produto diferente do grão (vem na vagem) |
| 1643 | ELIPSE VERDE E CARAMELO MENOR COSTURA PRETO E CAFÉ | UN | UN | UN | 1 | parece jogo americano/utensílio, não insumo |
| 1017 | EMBALAGEM 1500ML KRAFT \| 100 UNIDADES | CX | UN | CX | 100 | |
| 1570 | EMBALAGEM ANTIGORDURA COM VISOR CENTRAL 42X20-4 - 500 UNIDADES | UN | UN | CX | 500 | |
| 900 | EMBALAGEM KRAFT COM VISOR CENTRAL 28X15-4 - 1000 UNIDADES | UN | UN | CX | 1000 | |
| 921 | EMBALAGEM KRAFT COM VISOR CENTRAL 42X23-4 - 1000 UNIDADES | UN | UN | CX | 1000 | |
| 1569 | EMBALAGEM KRAFT COM VISOR CENTRAL 42X23-9 - 1000 UNIDADES | UN | UN | CX | 1000 | |
| 566 | EMBALAGEM RETANGULAR BP 10 C/100 UND - BIPACK | UN | UN | PCT | 100 | |
| 553 | EMBALAGEM RETANGULAR BP 13 C/100 UND - BIPACK | UN | UN | PCT | 100 | |
| 551 | EMBALAGEM RETANGULAR BP 20 C/100 UND - BIPACK | UN | UN | PCT | 100 | |
| 1097 | EMUSTAB 200G SELECTA | UN | KG | UN | 0,2 | |
| 2179 | ENROLADO SALS UN | UN | UN | UN | 1 | já está certo; salgado pronto, parece revenda |
| 1366 | ENVELOPE AMOR/EUVC C/5-REISA | PCT | UN | PCT | 5 | |
| 1368 | ENVELOPE ANIVERSARIO C/5-REISA | PCT | UN | PCT | 5 | |
| 1926 | ERVA DOCE FUNCHO | — | KG | KG | 1 | supondo a semente (tempero); se for o bulbo fresco: UN por peça — conferir |
| 74 | ERVILHA | KG | KG | KG | 1 | já está certo |
| 2065 | ESCOVA LOLLY LIMPEZA | UN | UN | UN | 1 | material de limpeza |
| 1944 | ESCOVAS PARA LIMPEZA DE CANUDOS | UN | UN | UN | conferir | o código "10CNE" sugere pacote de 10 |
| 1389 | ESPETO DE BAMBU KNOT 9 CM C/50 UND - INOVEN | — | UN | PCT | 50 | |
| 1676 | ESPETO GABOARDI 25CM C 5 | UN | UN | PCT | conferir | "C 5" está truncado: 5 ou 50 |
| 1505 | ESPINAFRE | — | UN | UN | 1 | maço |
| 3641 | ESPONJA ALKLIN ANTIRRISC | UN | UN | UN | 1 | material de limpeza |
| 107 | ESPONJA DUPLA FACE SCOTH BRITE 3M 10UN | UN | UN | PCT | 10 | material de limpeza |
| 1460 | ESPONJA LIMPPANO ANTIAD | UN | UN | UN | 1 | material de limpeza |
| 1759 | ESPONJA MULTIUSO LEVE 4 PAGUE 3 | UN | UN | PCT | 4 | material de limpeza |

## Lote 3 — ESPONJA MULTIUSO SCOTCH… a FOCCACIA…

> Feito em 07/10/2026 pelo conector de produção: INSUMOS em rascunho de **ESPONJA MULTIUSO SCOTCH…**
> a **FOCCACIA…** (77 produtos; offsets 250 a 349). Nada foi gravado.
> Ficaram de fora 17 ATIVOS e 6 ARQUIVADOS (farinhas com lote no nome: 1008, 1085, 1009, 338, 339, 1475).
> Próximo lote começa no offset 350.

### Regras acrescentadas

9. **Fermento fresco em tablete** → estoque **KG**, compra **UN** (o tablete), fator 0,5.
10. **Filme de PVC** → estoque **UN** (o rolo), fator 1; a metragem não se controla.

### Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 1872 | ESPONJA MULTIUSO SCOTCH-BRITE | UN | UN | UN | 1 | já está certo; material de limpeza |
| 2101 | ESPONJA SCOTCH BRITE C 4 | UN | UN | PCT | 4 | material de limpeza |
| 161 | ESPUMANTE BRUT BOSSA N1 | — | UN | CX | conferir | provável caixa de 6 |
| 160 | ESPUMANTE DEMI-SEC BOSSA N2 | — | UN | CX | conferir | provável caixa de 6 |
| 189 | ESPUMANTE DEMI-SEC BOSSA N2 U | — | UN | UN | 1 | "U" = garrafa avulsa (código é EAN); duplicado do 160 |
| 159 | ESPUMANTE MOSCATEL BOSSA N4 | — | UN | CX | conferir | provável caixa de 6 |
| 3111 | ESPUMANTE MOSCATEL ROSE 750ML | UN | UN | UN | 1 | já está certo |
| 190 | ESPUMANTE ROSE BOSSA N3 U | — | UN | UN | 1 | garrafa avulsa (código é EAN) |
| 530 | ESPUMANTE THERA ANIMA BRUT LOTE I - 23 | UN | UN | UN | 1 | já está certo |
| 436 | ESPUMANTE THERA ANIMA ROSE LOTE I 2020 | UN | UN | UN | 1 | já está certo |
| 1018 | ETIQUETA LACRE DE SEGURANCA G KRAFT - 1000 UNIDADES | CX | UN | CX | 1000 | |
| 2081 | ETIQUETA LACRE DE SEGURANCA G PRETA - 1000 UNIDADES | CX | UN | CX | 1000 | |
| 687 | ETIQUETA MX C/1000 | UN | UN | PCT | 1000 | se o controle for por rolo: UN/UN, fator 1 |
| 1849 | EXCELLENCE DARK 70 2 | CX | KG | PCT | conferir | chocolate 70%; o "2" truncado sugere 2 kg |
| 1695 | FAB PO PARA DECORACAO 3GR AZUL ANIZ | UN | UN | UN | 1 | já está certo; potinho de pó, não se pesa |
| 1692 | FAB PO PARA DECORACAO 5GR AZUL TIFFANY | UN | UN | UN | 1 | já está certo; potinho de pó, não se pesa |
| 1599 | FARINHA DE LINHACA DOURADA (NAC) PCT 1KG | UN | KG | PCT | 1 | |
| 932 | FARINHA DE LINHACA MARROM CMI 10KG | — | KG | SC | 10 | |
| 418 | FARINHA DE LINHACA MARROM NAC. 10KG | — | KG | SC | 10 | provável duplicado do 932 |
| 370 | FARINHA DE LINHACA MARROM (NAC) PCT 1KG | UN | KG | PCT | 1 | mesmo produto do 932 em outra embalagem |
| 765 | FARINHA MANDIOCA 1KG FRITZ E FRIDA | UN | KG | PCT | 1 | |
| 1196 | FARINHA MANDIOCA EXTRA FINA 1KG TUPA | — | KG | PCT | 1 | |
| 831 | FARINHA MANDIOCA FINA 1KG TAPOAN | — | KG | PCT | 1 | |
| 1738 | FECHO 10CM 100UN | UN | UN | PCT | 100 | embalagem |
| 1735 | FECHO 10CM 48UN GALA | UN | UN | PCT | 48 | embalagem |
| 766 | FEIJAO BRANCO 1KG URBANO | — | KG | PCT | 1 | |
| 1497 | FEIJAO BRANCO CALDAO 500GR | UN | KG | PCT | 0,5 | |
| 820 | FEIJAO BRANCO PREMIUM T1 500G FRITZ E FR | UN | KG | PCT | 0,5 | |
| 1964 | FEIJAO CALDAO 500G FRAD | UN | KG | PCT | 0,5 | fradinho |
| 2095 | FEIJAO CALDO BOM 250G | UN | KG | PCT | 0,25 | 250 g é incomum para feijão cru — conferir se não é produto pronto |
| 1051 | FEIJAO PRETO PREMIUM T1 1KG FRITZ E FRID | UN | KG | PCT | 1 | os três feijões pretos de 1 kg são candidatos a fusão |
| 830 | FEIJAO PRETO TIPO1 1KG RESERVA | UN | KG | PCT | 1 | |
| 1195 | FEIJAO PRETO TIPO1 1KG URBANO | — | KG | PCT | 1 | |
| 555 | FEIJAO VERMELHO PREMIUM T1 500G FRITZ | UN | KG | PCT | 0,5 | |
| 654 | FERMENTO FRESCO 500GR (MASSA DOCE) | — | KG | UN | 0,5 | tablete |
| 1286 | FERMENTO FRESCO 500GR (MASSA SAL) | UN | KG | UN | 0,5 | tablete |
| 1596 | FERMENTO FRESCO FORNATTA 500GR (MASSA SAL) | UN | KG | UN | 0,5 | provável duplicado do 1286 |
| 1684 | FERMENTO INSTANTANEO MASSA SALGADA FLEISCHMANN 500G | PCT | KG | PCT | 0,5 | |
| 1896 | FERMENTO MADRE DESIDRATADO NATURKRAFT PLATINUM 1 KG | KG | KG | PCT | 1 | estoque já certo; falta a compra |
| 1441 | FERM FRESCO MD 500G MAURIPAN | — | KG | UN | 0,5 | massa doce; provável duplicado do 654 |
| 127 | FERM FRESCO MS 500G MAURIPAN | UN | KG | UN | 0,5 | massa salgada; provável duplicado do 1286 |
| 653 | FERM INST FLEISCH 500GR(DOCE) | UN | KG | PCT | 0,5 | |
| 437 | FERM INST MD 500G MAURIPAN | KG | KG | PCT | 0,5 | estoque já certo; falta a compra |
| 6 | FERM QUIMICO 1KG ADIMIX | UN | KG | PCT | 1 | existe ATIVO 1664 (FERMENTO QUIMICO) — candidato a fusão |
| 3564 | FERM QUIMICO 2KG MAURI | UN | KG | PCT | 2 | idem |
| 982 | FIAMBRE FATIADO FRIOSBLU 100G | UN | KG | PCT | 0,1 | |
| 3280 | FIAMBRE PEDACO FRIOSBLU KG (2 PEDACOS DE 400G CADA) | KG | KG | KG | 1 | já está certo |
| 1190 | FIFTY FIFTY DRINKS - CATARINA MULE - LATA 269ML | — | UN | CX | conferir | latas por caixa |
| 1191 | FIFTY FIFTY DRINKS - TROPICAL - LATA 269ML | — | UN | CX | conferir | latas por caixa |
| 1378 | FILE DE CORVINA KG | KG | KG | KG | 1 | já está certo |
| 1948 | FILE DE COXAS E SOBRECOXAS RESF SC | KG | KG | KG | 1 | já está certo; provável duplicado do 59 e do 455 |
| 1973 | FILE DE LINGUADO 100/200 IQF CONG - 12 KG | KG | KG | CX | 12 | estoque já certo; falta a compra |
| 1899 | FILE DE LINGUADO 200/300 IQF CONG - 12 KG | KG | KG | CX | 12 | calibre diferente do 1973 |
| 1074 | FILE DE LINGUADO FRESCO P KG | KG | KG | KG | 1 | já está certo |
| 1538 | FILE DE PEITO DE FRANGO RESF SC | KG | KG | KG | 1 | já está certo |
| 1342 | FILÉ DE SALMÃO INTEIRO FRESCO KG | KG | KG | KG | 1 | já está certo; provável duplicado do 147 |
| 1529 | FILE DE SALMÃO PARTE DO LOMBO KG | KG | KG | KG | 1 | já está certo |
| 1900 | FILE DE SALMAO PORCAO 250G CONG - 48 X 250 | UN | KG | CX | 12 | segunda embalagem: porção = 0,25; se a ficha usa por porção: UN, CX = 48 |
| 147 | FILE DE SALMAO PREMIUM FRESCO - KG | KG | KG | KG | 1 | já está certo |
| 1799 | FILE DE SOROROCA FRESCO KG | KG | KG | KG | 1 | já está certo |
| 1213 | FILE DE TILAPIA G FRESCA | KG | KG | KG | 1 | já está certo |
| 3247 | FILE DUPLO CONGELADO - SERRADO MEDIA 350GR CX 10KG | KG | KG | KG | 1 | se a nota vier em caixa: CX = 10 |
| 569 | FILME DE PVC 380X300M - DISPAFILM | — | UN | UN | 1 | rolo; os oito filmes de PVC são embalagem e candidatos a fusão por metragem |
| 668 | FILME DE PVC 38 CM X 300 MT C/CORTADOR - BRASPRATICK | UN | UN | UN | 1 | já está certo |
| 1135 | FILME DE PVC 38 CM X 800 MT | UN | UN | UN | 1 | já está certo |
| 1312 | FILME DE PVC 38 CM X 800 MT - LUSAFILM | — | UN | UN | 1 | provável duplicado do 1135 |
| 1757 | FILME PVC 38X1000M | UN | UN | UN | 1 | já está certo |
| 552 | FILME PVC 38X10MM 300M GUARUFILME | UN | UN | UN | 1 | já está certo |
| 451 | FILME PVC 38X9MM 600M ECOFILM | CX | UN | CX | conferir | rolos por caixa |
| 1108 | FILME PVC ESTICAVEL 380X100M SERPA | UN | UN | UN | 1 | já está certo |
| 1967 | FILTRO 3CORAC 30UN | UN | UN | PCT | 30 | |
| 1019 | FILTRO DE PAPEL MELITTA N.4 C/30 UN | — | UN | PCT | 30 | |
| 1544 | FILTRO PAPEL MELITTA N 4 | UN | UN | PCT | conferir | 30 ou 40 por caixinha; provável duplicado do 1019 |
| 1075 | FILTRO PAPEL P/CAFE 103 MELLITA | UN | UN | PCT | conferir | 30 ou 40 por caixinha |
| 547 | FIOR DI LATTE ATAC 2 | KG | KG | UN | conferir | estoque já certo; o "2" truncado sugere peça de 2 kg |
| 291 | FLOR DO TESTO | KG | KG | KG | 1 | o nome não diz o que é — conferir o produto antes de confiar na unidade |
| 1826 | FOCCACIA TOMATE | UN | UN | UN | 1 | já está certo; pão comprado pronto, parece revenda |

## Lote 4 — FOLHA ALUM… a KIT CESTA…

> Feito em 07/10/2026 pelo conector de produção: INSUMOS em rascunho de **FOLHA ALUM…** a
> **KIT CESTA…** (98 produtos; offsets 350 a 449). Nada foi gravado.
> Ficaram de fora 2 ATIVOS (1946, 1328).
> Próximo lote começa no offset 450.

### Regras acrescentadas

11. **Polpa de fruta congelada em sachês de 100 g** ("FRUTA - … 100 GRS") → estoque **KG**, compra **PCT**, fator 1,02 (o pacote de 10 sachês).
12. **Destilado e licor** → estoque **UN** (a garrafa), fator 1; a caixa, quando o nome traz "(12)" ou "(6)", é a segunda embalagem. **Decisão do Marcelo em 07/10/2026** — a primeira versão deste arquivo sugeria L; as 30 linhas (cachaça, gin, licores, rum, steinhäger, tequila, vodca, uísque, os três vermutes e os dois xaropes de bar) foram trocadas. **Óleo usado em dose** continua em **L**, compra **GF**, fator = litros da garrafa.

### Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 1805 | FOLHA ALUM.D5 S/TP 1150ML WYDA 1X100UN | UN | UN | CX | 100 | marmitex de alumínio; embalagem |
| 703 | FORMA 2 11 274 0000 | UN | UN | UN | conferir | o nome não diz o que é nem quantas vêm |
| 689 | FORMA 8799 | UN | UN | UN | conferir | idem |
| 1868 | FORMA COLOMBA C 3 750 G. | UN | UN | PCT | conferir | "C 3" está truncado |
| 1252 | FORMA COLOMBA OVAL OND.DECOR 500G C/50UN | — | UN | PCT | 50 | mesma família do 1250 (lote 1) |
| 1124 | FORMA PANETONE 500G KRAFT DECOR C/100UN | — | UN | PCT | 100 | |
| 1749 | FORMA PANETONE 500GR FIORI 100 UN | — | UN | PCT | 100 | |
| 1744 | FORMA PANETONE BAIXO M-200 | UN | UN | PCT | conferir | formas por pacote |
| 970 | FORMA PARA TORTA PIE 90 COM TAMPA COM 10 UN SULFORMA | UN | UN | PCT | 10 | |
| 101 | FORMAS 6X6X6CM COM TAMPA | UN | UN | PCT | conferir | formas por pacote |
| 1238 | FORSTER MAR.RIESLING KABINETT (E. MULLER) 2022 | — | UN | CX | conferir | provável caixa de 6 |
| 2118 | FRAMBOESA LIOFILIZADA GRA | KG | KG | KG | 1 | já está certo |
| 1666 | FRUTA - ABACAXI 100 GRS - PCT 1,02 KG | — | KG | PCT | 1,02 | polpa em sachês |
| 1796 | FRUTA - AMORA 100 GRS - PCT 1,02 KG | — | KG | PCT | 1,02 | polpa em sachês |
| 777 | FRUTA - AMORA 100 GRS - SABOR DA FRUTA | — | KG | PCT | 1,02 | duplicado do 1796 (mesmo código 1830) |
| 568 | FRUTA AMORA CG PCT1KG CX6KG | KG | KG | PCT | 1 | fruta inteira congelada, não polpa; "P/A PCT 1KG": a venda é por pacote; segunda embalagem: CX = 6 (corrigido no lote 8) |
| 9 | FRUTA FRAMBOESA CG PCT1KG CX6KG | KG | KG | PCT | 1 | fruta inteira congelada; venda por pacote; segunda embalagem: CX = 6 (corrigido no lote 8) |
| 1823 | FRUTA - FRAMBOESA - LA - PCT 1,02 KG | — | KG | PCT | 1,02 | polpa em sachês |
| 781 | FRUTA - FRAMBOESA - LA - PCT 1 KG | — | KG | PCT | 1 | duplicado do 1823 (mesmo código 1153) — conferir se o fator é 1 ou 1,02 |
| 901 | FRUTA - MANGA 100 GRS. - LA - PCT 1,02 KG | — | KG | PCT | 1,02 | polpa em sachês |
| 1797 | FRUTA - MARACUJA COM SEMENTE 100 GRS - PCT 1,02 KG | — | KG | PCT | 1,02 | polpa em sachês |
| 782 | FRUTA - MARACUJA COM SEMENTE 100 GRS - SABOR DA FR | — | KG | PCT | 1,02 | duplicado do 1797 (mesmo código 1816) |
| 1244 | FRUTA - MORANGO 100 GRS | — | KG | PCT | conferir | provável 1,02, como as outras polpas |
| 567 | FRUTA MORANGO CG PCT 1KG CX 10KG | KG | KG | PCT | 1 | fruta inteira congelada; venda por pacote; segunda embalagem: CX = 10 (corrigido no lote 8) |
| 10 | FRUTA MORANGO CG PCT1KG CX6KG | KG | KG | PCT | 1 | mesmo produto do 567 em caixa menor; segunda embalagem: CX = 6 (corrigido no lote 8) |
| 1963 | FRUT CRI LA VIO 150G | UN | KG | UN | 0,15 | frutas cristalizadas |
| 348 | FT WERNER 5X5KG T1 | FD | KG | FD | 25 | farinha de trigo; segunda embalagem: PCT = 5; existe ATIVO 1938 (FARINHA TRIGO) — candidato a fusão |
| 203 | FT WERNER T1 25KG | — | KG | SC | 25 | idem |
| 544 | FUBÁ DE MILHO | CX | KG | PCT | conferir | o CX de hoje parece engano; provável pacote de 1 kg |
| 1289 | G-3530 GARRAFA PET CRISTAL C/TPA 300ML GALVANOTEK | UN | UN | CX | conferir | embalagem; garrafas por caixa |
| 447 | G-695 POTE PARA MOLHOS MILLENIUM 30ML BRANCO C/10 GALVANOTEK | — | UN | PCT | 10 | embalagem |
| 1953 | G-695SF POTE PARA MOLHOS 30ML BRANCO PET C/20 GALVANOTEK | — | UN | PCT | 20 | embalagem |
| 39 | G-73 BANDEJA MULTIUSO IDEAL CRISTAL PET C/10 GALVANOTEK | — | UN | PCT | 10 | embalagem |
| 1131 | GARRAFA 350ML CHA DE HIBISCO COM PESSEGO GASEIFICADO | UN | UN | UN | 1 | já está certo; bebida pronta, parece revenda |
| 1040 | GAS BUTANO REFIL PARA MACARICO | UN | UN | UN | 1 | já está certo; não é insumo de receita |
| 1655 | GAS P/ CHANTILLY ISI 84G C/10 | UN | UN | CX | 10 | mesma família do 577 (lote 1) |
| 187 | GAS REFIL DIOXIDO DE CARBONO REFIL | — | UN | UN | 1 | os três refis de CO2 são candidatos a fusão |
| 1290 | GAS REFIL DIOXIDO DE CARBONO REFIL AZUL | UN | UN | UN | 1 | já está certo |
| 1732 | GAS REFIL DIOXIDO DE CARBONO REFIL TERRA ROSA | UN | UN | UN | 1 | já está certo |
| 784 | GELATINA 510G NEUTRA QUALIMAX | UN | KG | PCT | 0,51 | |
| 951 | GELATINA S/SABOR 1KG NUANCE | UN | KG | PCT | 1 | |
| 1968 | GELATINA S/ SABOR INCOLOR APTI 500G | PCT | KG | PCT | 0,5 | |
| 1044 | GELO FOX 3KG PCT | UN | UN | UN | 1 | saco; se alguma ficha baixar gelo por peso: KG, fator 3 |
| 1521 | GENGIBRE | KG | KG | KG | 1 | já está certo |
| 1625 | GENGIBRE RAIZ PCT 1KG | UN | KG | PCT | 1 | provável duplicado do 1521 |
| 2122 | GERGELIM BRANCO DESCASCADO 1KG SESAMO | — | KG | PCT | 1 | os três gergelins brancos são candidatos a fusão |
| 1495 | GERGELIM BRANCO DESPELICULADO (*) PCT 1KG | UN | KG | PCT | 1 | |
| 1443 | GERGELIM BRANCO DESPELICULADO PCT 1KG | UN | KG | PCT | 1 | |
| 684 | GERGELIM COM CASCA (NAC) PCT 1KG | UN | KG | PCT | 1 | |
| 1724 | GIN BOMBAY SAPPHIRE 750 ML (12/56) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 172 | GIN TANQUERAY 750 ML (12) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 374 | GIRASSOL PEPITA PCT 1KG | UN | KG | PCT | 1 | |
| 584 | GLICOSE MILHO 25KG XAROPE INDEMIL | — | KG | UN | 25 | balde |
| 1957 | GLUCOSE DE MILHO 5KG SICOLA | — | KG | UN | 5 | balde; mesmo produto do 584 em outra embalagem |
| 1705 | GOIABA | KG | KG | KG | 1 | já está certo; já tratado na limpeza do hortifruti (06/10) |
| 691 | GOIABADA CASCAO PREDILECTA 1,01KG F.PACK | UN | KG | UN | 1,01 | |
| 2067 | GOIABADA STELLA DORO | UN | KG | UN | conferir | peso da embalagem sai da nota |
| 1962 | GOIAB PREDILECTA 1 01KG | UN | KG | UN | 1,01 | duplicado do 691 |
| 962 | GOMA XANTANA (IMP) PCT 1KG | UN | KG | PCT | 1 | |
| 434 | GOTAS CHOCOLATE AO LEITE GRANEL (KG) | KG | KG | KG | 1 | já está certo |
| 219 | GOTAS CHOCOLATE BRANCO GRANEL (KG) | KG | KG | KG | 1 | já está certo |
| 3469 | GOUDA FAT 130G PRESIDENT RAV | UN | KG | PCT | 0,13 | |
| 321 | GRAO BICO CONSERVA 2,6KG COOPER FOODS | — | KG | UN | 2,6 | lata; 2,6 é o peso bruto, o drenado é menor |
| 1592 | GRAO DE BICO 400G CALDAO | UN | KG | PCT | 0,4 | |
| 832 | GRAO DE BICO COZ 1KG BURG | — | KG | UN | 1 | cozido — não fundir com o seco |
| 1027 | GRAO DE BICO MIUDO 1KG PQ ALIMENTOS | — | KG | PCT | 1 | seco |
| 1562 | GROWLER 1L PILSEN - STANNIS PILSNER | UN | UN | UN | 1 | já está certo; revenda |
| 3283 | GUANCIALLE 250G | UN | KG | PCT | 0,25 | |
| 5 | GUARD 39,5X39,5 GRAN SENSACAO PERS CX 36X25 - 1/8 | CX | UN | CX | 900 | segunda embalagem: PCT = 25 |
| 1886 | GUARDANAPO 1039036 33X33CM 20UN | UN | UN | PCT | 20 | |
| 879 | GUARDANAPO MILI BISTRO | UN | UN | PCT | conferir | folhas por pacote |
| 1261 | GUARDANAPO PREMIUM 40X40 PERSONALIZADO FOLHA DUPLA C/1.000UN - BOTANE | CX | UN | CX | 1000 | |
| 1230 | GUARD F DUPLA GRAN SE 39,5X39,5CM PRATYC | — | UN | PCT | conferir | provável 25, como o 5 |
| 494 | GUARD F DUPLA GRAN SENS 39,5X39,5CM ROSA | UN | UN | PCT | conferir | provável 25, como o 5 |
| 1669 | GUARD GRAN CHEF 40X39,5 25 FL DUPLA | UN | UN | PCT | 25 | |
| 1541 | GUARD PAP FD ELITE C 50 | UN | UN | PCT | 50 | |
| 456 | HIBISCO FLOR (IMP) PCT 1KG | UN | KG | PCT | 1 | |
| 1691 | HORTELA | — | UN | UN | 1 | maço |
| 673 | ILUMINA-TE .:ATACADO LATA 50G | — | UN | UN | 1 | lata de chá para revenda (como o 674 do lote 1) |
| 497 | ILUMINA-TE .:FOOD SERVICE KG | — | KG | PCT | 1 | chá usado em infusão, por peso |
| 1212 | IMPD - SALMAO EVISCERADO FRESCO 08/10LB PREMIUM | KG | KG | KG | 1 | já está certo |
| 672 | INTIMIDADE .:ATACADO LATA 50G | — | UN | UN | 1 | lata de chá para revenda |
| 903 | INTIMIDADE .:FOOD SERVICE 250G | — | KG | PCT | 0,25 | |
| 496 | INTIMIDADE .:FOOD SERVICE KG | — | KG | PCT | 1 | mesmo chá do 903 em outra embalagem |
| 671 | INTUICAO .:ATACADO LATA 60G | — | UN | UN | 1 | lata de chá para revenda |
| 905 | INTUICAO .:FOOD SERVICE 250G | — | KG | PCT | 0,25 | |
| 495 | INTUICAO .:FOOD SERVICE KG | — | KG | PCT | 1 | mesmo chá do 905 em outra embalagem |
| 1247 | IOG HOLANDES NAT 1 8L | UN | L | UN | 1,8 | balde de 1,8 L, usado em receita |
| 481 | IOGURTE INTEGRAL COM GELEIA DE DAMASCO - 170 GRAMAS | UN | UN | UN | 1 | já está certo; pote de revenda |
| 290 | IOGURTE INTEGRAL COM GELEIA DE MORANGO - 170 GRAMAS | UN | UN | UN | 1 | já está certo; pote de revenda |
| 816 | IOGURTE INTEGRAL COM PREPARADO DE MORANGO - 500 GRAMAS | UN | UN | UN | 1 | já está certo; pote de revenda |
| 1187 | IOGURTE INTEGRAL NATURAL - 170 GRAMAS / (1 FARDO) | UN | UN | FD | conferir | potes por fardo |
| 1397 | IOGURTE NATURAL INTEGRAL VERMONT - 500G | UN | KG | UN | 0,5 | supondo uso em receita; se for vendido no pote: UN, fator 1 |
| 518 | I - OLEO DE GERGELIM PREMIUM 100% PURO TORRADO 1L | UN | L | GF | 1 | |
| 1674 | ISCAS DE FILE MIGNON CONGELADA | KG | KG | KG | 1 | já está certo |
| 1623 | JASMIM FLOR PCT 500G | UN | KG | PCT | 0,5 | |
| 585 | KIT BISNAGA KRAEUTERKAESE + TORRADA | UN | UN | UN | 1 | já está certo; kit de revenda, não insumo |
| 617 | KIT CESTA ONE GRANDE | — | UN | UN | 1 | kit/cesta, não insumo |

## Lote 5 — KITDEGUSTACAO… a MARZAROTTO…

> Feito em 07/10/2026 pelo conector de produção: INSUMOS em rascunho de **KITDEGUSTACAO…** a
> **MARZAROTTO…** (91 produtos; offsets 450 a 549). Nada foi gravado.
> Ficaram de fora 9 ATIVOS (leites, limões, MANTEIGA SEM SAL).
> "hortifruti já tratado" = cadastro que ficou da limpeza de 06/10 (tem categoria e setor); aparece só para constar.
> Próximo lote começa no offset 550.

### Regras acrescentadas

13. **Licor** segue a regra 12: estoque **UN** (a garrafa); o número entre parênteses no nome é a caixa.
14. **Embutido e congelado "PCT x KG CX y KG P/A PCT x KG"** → estoque **KG**, compra **PCT**, fator = peso do pacote; a caixa é a segunda embalagem. (Corrigido no lote 8: o "P/A" no fim do nome diz a unidade em que o fornecedor vende.)

### Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 1766 | KITDEGUSTACAO-CACHACACHOC | KG | UN | UN | 1 | kit de degustação; o KG de hoje parece engano; não é insumo |
| 1518 | KIWI IMPORTADO | KG | KG | KG | 1 | já está certo |
| 2860 | KOMBUCHA ABACAXI E HORTELA 310ML | UN | UN | UN | 1 | já está certo; bebida de revenda; se a nota vier em caixa, conferir quantas |
| 315 | KOMBUCHA DE ABACAXI E HORTELÃ 300 ML | UN | UN | UN | 1 | já está certo; provável duplicado do 2860 |
| 314 | KOMBUCHA DE MORANGO E HIBISCO 300 ML | UN | UN | UN | 1 | já está certo |
| 2861 | KOMBUCHA FRUTAS VERMELHAS 310ML | UN | UN | UN | 1 | já está certo |
| 2024 | KOMBUCHA MORANGO E HIBISCO 400ML | UN | UN | UN | 1 | já está certo; tamanho diferente do 314 |
| 313 | KOMBUCHA SABOR MAÇÃ COM CANELA | UN | UN | UN | 1 | já está certo |
| 312 | KOMBUCHA SABOR RED BLEND | UN | UN | UN | 1 | já está certo |
| 2862 | KOMBUCHA UVA 310ML | UN | UN | UN | 1 | já está certo |
| 375 | LACRE TERMOENCOLHIVEL 74MM - POTES (PCT C/ 50) | CX | UN | PCT | 50 | embalagem |
| 145 | LARANJA BAHIA | KG | KG | KG | 1 | hortifruti já tratado |
| 307 | LARANJA FATIAS DESIDRATADA PCT 500G | UN | KG | PCT | 0,5 | |
| 49 | LARANJA PERA | KG | KG | KG | 1 | hortifruti já tratado |
| 731 | LASANHA BOLON 600G S | — | UN | UN | 1 | prato pronto congelado; parece revenda |
| 730 | LASANHA CAMARAO 400G | — | UN | UN | 1 | prato pronto congelado; parece revenda |
| 655 | LEBERKASE PEDACO FRIOSBLU KG | KG | KG | KG | 1 | já está certo |
| 1319 | LICOR 43 (ORIGINAL) (PACK C/ COPO BALON CARAJILLO) 700 ML (6) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 6 |
| 1647 | LICOR COINTREAU FRANCES 700 ML (12) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 1635 | LICOR DE DOCE DE LEITE DE OVELHA 250ML | UN | UN | UN | 1 | já está certo; parece revenda; se entrar em drinque: L, fator 0,25 |
| 1303 | LICOR FINO DE CAFE - 700ML - KAFFEE LIKOR | UN | UN | UN | 1 | garrafa |
| 1646 | LICOR FINO DE FLOR DE SABUGUEIRO 700 ML | — | UN | UN | 1 | garrafa |
| 1301 | LICOR FINO DE ROSAS 700 ML | — | UN | UN | 1 | garrafa |
| 1645 | LICOR FINO DE TANGERINA 700 ML | — | UN | UN | 1 | garrafa |
| 1648 | LICOR FRANGELICO 700 ML (12) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 648 | LICOR STOCK 720ML CR CAS | UN | UN | UN | 1 | garrafa; creme de cassis |
| 771 | LICOR STOCK CURACAU FINO (TRIPLE SEC) 720 ML (6) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 6 |
| 565 | LIMPA CHAPA E GRILL DESINCRUSTANTE PROFISSIONAL DEOLINE 5 LTS | UN | UN | UN | 1 | já está certo; material de limpeza |
| 1407 | LIMPA CHAPA E GRILL S/ENXAQUE 750 ML - DEOLINE | — | UN | UN | 1 | material de limpeza |
| 3419 | LIMP VEJA 30 DESC 2UN L | UN | UN | UN | conferir | embalagem promocional; "2UN" pode ser pacote com 2 |
| 1746 | LIMP VEJA 400ML BANH CLO | UN | UN | UN | 1 | já está certo; material de limpeza |
| 1741 | LIMP VEJA 500ML BANHEIRO | UN | UN | UN | 1 | já está certo; material de limpeza |
| 2026 | LING CALABRESA DEF PCT1,5KG CX12KG | KG | KG | PCT | 1,5 | estoque já certo; "P/A PCT 1,5KG": a venda é por pacote; segunda embalagem: CX = 12 (corrigido no lote 8) |
| 1972 | LING CALABRESA FAT CG PCT1KG CX8KG | KG | KG | PCT | 1 | estoque já certo; venda por pacote; segunda embalagem: CX = 8 (corrigido no lote 8) |
| 1965 | LING CALABRESA JCW 1KG F | UN | KG | PCT | 1 | |
| 1349 | LING SUINA CG PCT 5KG CX20KG | KG | KG | PCT | 5 | estoque já certo; venda por pacote; segunda embalagem: CX = 20 (corrigido no lote 8) |
| 526 | LINGUA CONGELADA | KG | KG | KG | 1 | já está certo |
| 581 | LINGUICA BLUMENAU MOIDA DESCHAMPS KG PCT | KG | KG | KG | 1 | já está certo |
| 749 | LINGUICA SUINA CG FRIOSBLU 600G | KG | KG | PCT | 0,6 | estoque já certo; falta a compra |
| 1558 | LINGUICA WESTPHALIA | KG | KG | KG | 1 | já está certo |
| 896 | LINHACA DOURADA 1KG | UN | KG | PCT | 1 | |
| 1446 | LINHACA DOURADA SEMENTE (NAC) PCT 1KG | UN | KG | PCT | 1 | provável duplicado do 896 |
| 150 | LOMBO CANADENSE FATIADO FRIOSBLU 100G | UN | KG | PCT | 0,1 | |
| 1509 | LOMBO CANADENSE INTEIRO FRIOSBLU KG (4 PC INTEIRAS) | KG | KG | KG | 1 | já está certo |
| 1344 | LOMBO DE ATUM FRESCO- KG | KG | KG | KG | 1 | já está certo |
| 1571 | LOMBO DEFUMADO INTEIRO FRIOSBLU KG (4 PC INTEIRAS) | KG | KG | KG | 1 | já está certo |
| 349 | LOMBO DE PIRARUCU KG | KG | KG | KG | 1 | já está certo |
| 342 | LOMBO SUINO FATIADO KG | KG | KG | KG | 1 | já está certo |
| 1554 | LTE UHT TIROL INT 1L | — | L | UN | 1 | existe ATIVO 2155 (LEITE INTEGRAL CAIXINHA) — candidato a fusão; se a nota vier em caixa: CX = 12 |
| 1408 | LUVA DE LATEX P/LIMPEZA AMARELA G C/2 UND | — | UN | UN | 1 | a unidade é o par |
| 1350 | LUVA DE LATEX P/LIMPEZA AMARELA M C/2 UND - TALGE | — | UN | UN | 1 | a unidade é o par |
| 1889 | LUVA LATEX PARA LIMPEZA G | UN | UN | UN | 1 | já está certo; provável duplicado do 1408 |
| 1892 | LUVA LATEX PARA LIMPEZA M | UN | UN | UN | 1 | já está certo; provável duplicado do 1350 |
| 857 | LUVA NITRILICA PRETA P SEM PO C/100 UND - TALGE | — | UN | CX | 100 | se o controle for por caixa: UN/UN, fator 1 |
| 1508 | MACA ARGENTINA VERDE | KG | KG | KG | 1 | já está certo |
| 1639 | MACA ARGENTINA VERMELHA | KG | KG | KG | 1 | já está certo |
| 1454 | MACA CHA FATIAS PCT 500G | UN | KG | PCT | 0,5 | maçã desidratada para chá |
| 1481 | MACA FUJI | KG | KG | KG | 1 | hortifruti já tratado |
| 977 | MAC ANTICO MOLINO 500G 6 | UN | KG | PCT | 0,5 | macarrão; o "6" final pode ser o formato ou a caixa — conferir |
| 1049 | MACA PINK LADY KG | KG | KG | KG | 1 | já está certo |
| 2075 | MAC BARILLA ITA 500G N 3 | UN | KG | PCT | 0,5 | |
| 388 | MAC ITA BARILLA 500G LIN | UN | KG | PCT | 0,5 | linguine |
| 441 | MAC ITA BARILLA 500G SPA | UN | KG | PCT | 0,5 | spaghetti |
| 1078 | MAC KARUI 200G ORIENTAL | UN | KG | PCT | 0,2 | |
| 1983 | MAC NISSIN YAKISSOBA 500 | UN | KG | PCT | 0,5 | |
| 393 | MAIONESE BD 3KG HELLMANNS | — | KG | UN | 3 | balde; as cinco maioneses são candidatas a fusão |
| 818 | MAIONESE DOYPACK 1KG HELLMANNS | UN | KG | UN | 1 | |
| 1536 | MAIONESE HELLMANNS BAG 1,6KG | UN | KG | UN | 1,6 | |
| 1457 | MAIONESE HEMMER 930G | UN | KG | UN | 0,93 | |
| 1603 | MAION HELLMANNS 500G C2 | UN | KG | UN | 0,5 | |
| 1125 | MALTE 500G AROMA IREKS | — | KG | PCT | 0,5 | |
| 1484 | MAMAO FORMOSA | KG | KG | KG | 1 | hortifruti já tratado |
| 700 | MAMAO PAPAIA | KG | KG | KG | 1 | hortifruti já tratado; fator do código que vem por unidade continua pendente |
| 1517 | MANGA | KG | KG | KG | 1 | hortifruti já tratado |
| 2117 | MANGA CONF 47X27 DESCART 50UN COFERPAN | — | UN | PCT | 50 | manga de confeiteiro |
| 1228 | MANGA CONF 50X30 DESCART 50UN COFERPAN | — | UN | PCT | 50 | manga de confeiteiro |
| 2099 | MANGA DESCARTAVEL GRANDE 50X28CM C/50 | PCT | UN | PCT | 50 | provável duplicado do 1228 |
| 67 | MANJERICAO | UN | UN | UN | 1 | hortifruti já tratado |
| 2144 | MANJERICAO VERDE ITALIANO - ERVA AROMATICA, TEMPERO - 1UN | UN | UN | UN | 1 | já está certo; pelo código é muda em vaso; provável duplicado do 67 |
| 3468 | MANTEIGA C/SAL MOTTE 250G PRESIDENT IMP | UN | KG | UN | 0,25 | |
| 1329 | MANTEIGA MYCRYO DE CACAU 550 GR CALLEBAUT | UN | KG | UN | 0,55 | |
| 3439 | MANTEIGA S/SAL CX 5 KG PRESIDENT TEU | CX | KG | CX | 5 | existe ATIVO 25 (MANTEIGA SEM SAL) — candidato a fusão |
| 220 | MANTEIGA TOURAGE | — | KG | UN | conferir | placa de 1 ou 2 kg |
| 1753 | MANTEIGA TOURAGE PLACA 1KG 30X31 | — | KG | UN | 1 | provável duplicado do 220 |
| 1336 | MANT PRESIDENT S S 200G | UN | KG | UN | 0,2 | existe ATIVO 25 (MANTEIGA SEM SAL) — candidato a fusão |
| 68 | MARACUJA | KG | KG | KG | 1 | hortifruti já tratado |
| 805 | MARG COAMO 80% L S/SAL ZERO TRANS 14,5KG | UN | KG | CX | 14,5 | |
| 192 | MARRECO RECHEADO TEMP CONG VG 6X3,0KG (18KG) | KG | KG | CX | 18 | estoque já certo; segunda embalagem: peça = 3 |
| 1918 | MARZAROTTO ESPUMANTE MOSCATEL 750 ML | UN | UN | UN | 1 | já está certo |
| 1919 | MARZAROTTO GRAN RESERVA TANNAT 750 ML | UN | UN | UN | 1 | já está certo |
| 3044 | MARZAROTTO PLENO BLEND 2022 750 ML | UN | UN | UN | 1 | já está certo |

## Lote 6 — MARZAROTTO PLENO MERLOT… a OVINHOS…

> Feito em 07/10/2026 pelo conector de produção: INSUMOS em rascunho de **MARZAROTTO PLENO MERLOT…**
> a **OVINHOS…** (95 produtos; offsets 550 a 649). Nada foi gravado.
> Ficaram de fora 5 ATIVOS (897, 142, 778, 1080, 1463).
> Próximo lote começa no offset 650.

### Regras acrescentadas

15. **Molho líquido de cozinha** (shoyu, inglês) → estoque **L**; compra na garrafa ou galão; fator = litros.
16. **Molho de mesa em frasco pequeno** (Tabasco 60 ml) → estoque **UN**: o frasco vai inteiro para o salão, não se dosa.
17. **Condimento pastoso** (mostarda, molho de tomate, missô, mel, melado) → estoque **KG**; fator = peso da embalagem.
18. **Conserva em lata** (milho) → estoque **KG** pelo peso do rótulo; o peso drenado é menor, e a ficha precisa usar a mesma base.

### Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 1565 | MARZAROTTO PLENO MERLOT 750 ML | UN | UN | UN | 1 | já está certo |
| 3060 | MARZAROTTO PLENO PEVERELLA 750 ML | — | UN | UN | 1 | |
| 3062 | MARZAROTTO PLENO ROSE BLUSH 750 ML | UN | UN | UN | 1 | já está certo |
| 1423 | MASCARA DUPLA EM TNT C/ELASTICO C/100 UND | UN | UN | CX | 100 | descartável, não insumo de receita |
| 493 | MASCARPONE BONFIORE LATTERIA | KG | KG | UN | conferir | estoque já certo; peso do pote sai da nota |
| 463 | MASSA FILOTEA TAGLIA | — | KG | PCT | conferir | nome truncado (tagliatelle); provável 0,25 |
| 168 | MASSA GRANO DURO ESPAGUETE N5 500G BARIL | UN | KG | PCT | 0,5 | provável duplicado do 441 (lote 5) |
| 1339 | MASSA P/ GUIOZA TAICHI 20 F | PCT | UN | PCT | 20 | conta-se a folha |
| 2112 | MASSA PRONTA TUPA 1KG | UN | KG | PCT | 1 | |
| 322 | MASSA TALHARIM NINHO SEMOLA 500G ROSANE | UN | KG | PCT | 0,5 | |
| 2135 | MATCHA CULINARIO 500G | UN | KG | PCT | 0,5 | |
| 1466 | MATCHA EM PO SOLUVEL PESO:1 KG | UN | KG | PCT | 1 | solúvel, não é o mesmo do 2135 |
| 837 | MATIZ ROSE 2021 RA U | — | UN | UN | 1 | vinho; garrafa avulsa |
| 210 | MEIO PEITO SEM OSSO SEM PELE DE FRANGO RESF SC | KG | KG | KG | 1 | já está certo; provável duplicado do 1538 (lote 3) |
| 633 | MELADO DE CANA DACOLONIA POTE 500G | KG | KG | UN | 0,5 | estoque já certo; falta a compra |
| 1276 | MELADO DE CANA POTE 500G MINAMEL | UN | KG | UN | 0,5 | provável duplicado do 633 |
| 734 | MELANCIA BABY KG | KG | KG | KG | 1 | já está certo |
| 1618 | MELAO AMARELO | KG | KG | KG | 1 | já está certo |
| 1047 | MELAO ESPANHOL KG | KG | KG | KG | 1 | já está certo |
| 428 | MEL DE ABELHA 1 KG | — | KG | UN | 1 | |
| 847 | MEL DE ABELHA SILVESTRE PT 1KG | UN | KG | UN | 1 | provável duplicado do 428 |
| 3562 | MERKEN BOMBAY POUCH 30 G | UN | KG | UN | 0,03 | tempero |
| 226 | MIGNON SUINO KG | KG | KG | KG | 1 | já está certo |
| 1769 | MILHO 1,7KG BONARE LATA 1,7KG | UN | KG | UN | 1,7 | lata grande |
| 870 | MILHO TORRADO SABOR MOSTARDA E MEL PCT 1,001KG | UN | KG | PCT | 1,001 | petisco |
| 2106 | MILHO VDE TRADELLI 170G | UN | KG | UN | 0,17 | as quatro latas de 170 g são candidatas a fusão |
| 1726 | MILHO VERDE | — | UN | UN | 1 | supondo espiga in natura; se for lata: KG, fator 0,17 — conferir |
| 1052 | MILHO VERDE 170G BONARE | — | KG | UN | 0,17 | |
| 2003 | MILHO VERDE ETTI 170G SA | UN | KG | UN | 0,17 | |
| 1377 | MILHO VERDE SH 170G BONARE | UN | KG | UN | 0,17 | |
| 1256 | MINI SCHNEKE | UN | UN | UN | 1 | já está certo; produto pronto, não insumo |
| 439 | MISSO MASSA SOJA 1KG SAKURA | — | KG | UN | 1 | |
| 964 | MISSO ORIENTAL (MASSA DE SOJA) PCT 500G | UN | KG | PCT | 0,5 | mesmo produto do 439 em outra embalagem |
| 1609 | MIST. CAKE NEUTRO BAKELS 2KG | PCT | KG | PCT | 2 | |
| 472 | MIX DE VEGETAIS ROOT | — | KG | PCT | conferir | peso do pacote sai da nota |
| 1309 | MOELA COPACOL 1KG BAND | UN | KG | BDJ | 1 | provável duplicado do 1807 |
| 1807 | MOELA DE FRANGO RESF SC | KG | KG | KG | 1 | já está certo |
| 458 | MOIDA DE PRIMEIRA | KG | KG | KG | 1 | já está certo |
| 225 | MOIDA PARA BURGUER C/ COSTELA KG | KG | KG | KG | 1 | já está certo |
| 3635 | MOIDA P BURGUER 50GR 7CM 500GR | UN | UN | PCT | 10 | disco de 50 g, pacote de 500 g; se a ficha usa por peso: KG, fator 0,5 |
| 429 | MOLHO DE PIMENTA TABASCO 60ML VERMELHO | — | UN | UN | 1 | os oito Tabascos se resumem a quatro sabores — candidatos a fusão |
| 1588 | MOLHO INGLES DAJUDA 900ML PET | UN | L | UN | 0,9 | |
| 1404 | MOLHO INGLES PET 1,01L RUAH | — | L | UN | 1,01 | |
| 855 | MOLHO PIMENTA ORIGINAL VD 60ML TABASCO | — | UN | UN | 1 | |
| 856 | MOLHO PIMENTA VERDE SUAVE VD60ML TABASCO | — | UN | UN | 1 | |
| 1654 | MOLHO PIM TABASCO 60ML | UN | UN | UN | 1 | já está certo |
| 1458 | MOLHO RUAH 1 01ML SHOYO | UN | L | UN | 1,01 | shoyu; o "ML" do nome é litro |
| 1496 | MOLHO SHOYU GALAO 3,1L KAMPAI TRAD. | UN | L | GL | 3,1 | |
| 2882 | MOLHO SHOYU KAMPAI TRAD.GALAO 5L | L | L | GL | 5 | estoque já certo; falta a compra |
| 532 | MOLHO SHOYU SUAVE 1L CEREJA | — | L | UN | 1 | |
| 1930 | MOLHO SHOYU SUAVE 5L CEREJA | L | L | GL | 5 | estoque já certo; falta a compra |
| 448 | MOLHO TABASCO CHIPOT | — | UN | UN | 1 | |
| 464 | MOLHO TABASCO SRIRAC | — | UN | UN | 1 | |
| 470 | MOLHO TABASCO TRADIC | — | UN | UN | 1 | |
| 450 | MOLHO TABASCO VERDE | — | UN | UN | 1 | |
| 1053 | MOLHO TOMATE PASSATA 1,02KG POMAROLA | UN | KG | UN | 1,02 | |
| 1297 | MOLHO TOMATE TRAD 1,06KG POMAROLA | — | KG | UN | 1,06 | |
| 1436 | MOL SHOY MITS 900ML | UN | L | UN | 0,9 | shoyu |
| 1476 | MORANGO DESIDRATADO GLACEADO PCT 500G | UN | KG | PCT | 0,5 | |
| 1449 | MORTADELA MADONNA PIMENTA GRAO, FOOD SERVICE, FRACIONADO | KG | KG | KG | 1 | já está certo |
| 1396 | MORTADELA MADONNA PISTACHE, FOOD SERVICE, PECA | KG | KG | KG | 1 | já está certo |
| 2102 | MORTADELA SEARA 180G FAT | UN | KG | PCT | 0,18 | |
| 3114 | MORT BOLOGNA OURO FAT 200G 4UN CX20UN | UN | KG | PCT | 0,8 | pacote com 4 bandejas de 200 g; segunda embalagem: CX = 4 |
| 524 | MORT DEF SOLTIS FAT 200G 3UN CX21UN | UN | KG | PCT | 0,6 | pacote com 3 bandejas de 200 g; segunda embalagem: CX = 4,2 |
| 476 | MOSTARDA AMARELA 1KG HEMMER | UN | KG | UN | 1 | as cinco mostardas amarelas são candidatas a fusão |
| 767 | MOSTARDA AMARELA 3,6KG HEMMER | KG | KG | GL | 3,6 | estoque já certo; falta a compra |
| 1393 | MOSTARDA AMARELA BAG 2KG HEINZ | UN | KG | UN | 2 | |
| 981 | MOSTARDA AMARELA DOYPACK 1,01KG HELLMANN | UN | KG | UN | 1,01 | |
| 286 | MOSTARDA AMARELA HEINZ BAG 2,0KG | UN | KG | UN | 2 | duplicado do 1393 |
| 1284 | MOSTARDA DIJON VIDRO 200G BEAUFOR | UN | KG | UN | 0,2 | |
| 2054 | MOSTARDA EM GRAO 250G MON CHEF | — | KG | UN | 0,25 | |
| 2138 | MOSTARDA FRANCESA BEAUFOR ANCIENNE BALDE 1,001KG | UN | KG | UN | 1,001 | |
| 1459 | MOSTARDA MAILLE D 215G | UN | KG | UN | 0,215 | dijon |
| 1556 | MOSTARDA MAILLE DIJO | — | KG | UN | conferir | provável 0,215; duplicado do 1459 |
| 221 | MOSTARDA VERDE ORIENTAL (IN) | UN | UN | UN | 1 | já está certo; é a folha in natura (maço), não o condimento |
| 1634 | MUSCULO TRASEIRO RESFRIADA/CUBOS | KG | KG | KG | 1 | já está certo |
| 1142 | MUSCULO TRASEIRO RESFRIADA/INTEIRO | KG | KG | KG | 1 | já está certo |
| 670 | NAMASTE CHAI .:ATACADO LATA 60G | — | UN | UN | 1 | lata de chá para revenda |
| 961 | NAMASTE CHAI .:FOOD SERVICE 250G | — | KG | PCT | 0,25 | |
| 498 | NAMASTE CHAI .:FOOD SERVICE 500G | — | KG | PCT | 0,5 | mesmo chá do 961 em outra embalagem |
| 365 | NECTARINA KG | KG | KG | KG | 1 | já está certo |
| 521 | NECTAR PIONEIRA 2 8L | UN | L | GL | 2,8 | néctar de fruta; o nome não diz o sabor |
| 522 | NECTAR PIONEIRA 5L LAR | UN | L | GL | 5 | néctar de laranja |
| 548 | NODINO ATACADO 2 | KG | KG | UN | conferir | estoque já certo; o "2" truncado sugere 2 kg (como o FIOR DI LATTE 547) |
| 1167 | NOZES MARIPOSA EXTRA CX 10KG | UN | KG | CX | 10 | |
| 352 | NOZES-PECA METADES 1 KG | UN | KG | PCT | 1 | |
| 848 | NOZES PECAN GRANULADA PCT 1KG | UN | KG | PCT | 1 | |
| 930 | NOZES PECAN INTEIRA PCT 1KG | UN | KG | PCT | 1 | provável duplicado do 352 |
| 1425 | NOZES PECAN QUEBRADA (PEDACOS) PCT 1KG | UN | KG | PCT | 1 | |
| 1134 | NOZ PECAN TRITURADA 1KG | KG | KG | PCT | 1 | estoque já certo; provável duplicado do 848 |
| 517 | ÓLEO DE GERGELIM TORRADO COMUM TAICHI 1L | — | L | GF | 1 | provável duplicado do 518 (lote 4) |
| 1728 | OLEO DE OLIVA EXTRA VIRGEM - LUGLIO - PET 5LT | UN | L | GL | 5 | existe ATIVO 324 (AZEITE DE OLIVA 5L) — candidato a fusão |
| 675 | OSSOBUCO CONGELADO/SERRADO | KG | KG | KG | 1 | já está certo |
| 742 | OSSOBUCO RESFRIADA/SERRADO | KG | KG | KG | 1 | já está certo |
| 502 | OVINHOS CROCANTES COLORIDOS 100 GR | UN | KG | PCT | 0,1 | confeito; se for vendido no pacote: UN |

## Lote 7 — OVO GEMA… a POLVILHO DOCE 500G…

> Feito em 07/10/2026 pelo conector de produção: INSUMOS em rascunho de **OVO GEMA…** a
> **POLVILHO DOCE 500G…** (87 produtos; offsets 650 a 749). Nada foi gravado.
> Ficaram de fora 3 ATIVOS (589, 1905, 881) e 10 ARQUIVADOS (papéis toalha e papéis higiênicos).
> Próximo lote começa no offset 750.

### Regra acrescentada

19. **Frios fatiados "200G nUN CXmUN"** → estoque **KG**, compra **PCT**, fator = n × 0,2; a caixa é a segunda embalagem.

### Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 3446 | OVO GEMA NETTO PASTEUR 1KG | UN | KG | UN | 1 | gema pasteurizada |
| 1127 | PACOTE DE PAPEL BRANCO 3 KG C/500 UND | — | UN | PCT | 500 | saco de papel; embalagem |
| 1138 | PACOTE DE PAPEL LANCHE VIP 14X40 C/500 UND | — | UN | PCT | 500 | embalagem |
| 1358 | PALHA CELULOSE NATURAL 450G-SC GRANDE | — | UN | UN | 1 | enchimento de cesta; embalagem |
| 1729 | PALHA MADEIRA | UN | UN | UN | 1 | já está certo; embalagem |
| 1264 | PALITO EM BAMBU P/ PETI 12,5 CM C/20UN | UN | UN | PCT | 20 | |
| 1706 | PANETONE DE CHOCOLATE | UN | UN | UN | 1 | já está certo; produto pronto, não insumo |
| 1175 | PANETTONE PISTACHE | UN | UN | UN | 1 | já está certo; produto pronto, não insumo |
| 1174 | PANETTONE TRADICIONAL | UN | UN | UN | 1 | já está certo; produto pronto, não insumo |
| 3448 | PAO BOTANE | UN | UN | UN | 1 | já está certo; parece produção própria, não insumo comprado |
| 3449 | PAO DE GRAOS | UN | UN | UN | 1 | já está certo; idem |
| 1903 | PAO DE NOZES BOTANE | UN | UN | UN | 1 | já está certo; idem |
| 1672 | PAO FRANCES KG | KG | KG | KG | 1 | já está certo |
| 1026 | PAO TIPO TORTILHA RAP10 297G TRADICIONAL | — | UN | PCT | conferir | conta-se a tortilha; quantas por pacote sai do rótulo |
| 1334 | PAO TORTILHA WB 270G WR | UN | UN | PCT | conferir | idem |
| 1966 | PAO TORTILLA VITAL 290G | UN | UN | PCT | conferir | idem; as três tortilhas são candidatas a fusão |
| 871 | PAPEL MANTEIGA 30X40 | UN | UN | PCT | conferir | folhas por pacote |
| 972 | PAPEL MANTEIGA 50X70 400UN | FD | UN | PCT | 400 | |
| 358 | PAPEL MANTEIGA 50X70CM C/400 UND | KG | UN | PCT | 400 | o KG de hoje é engano; duplicado do 972 |
| 1130 | PAPRICA DEF 500G MON CHEF | — | KG | PCT | 0,5 | |
| 747 | PAPRICA DEFUMADA (C/ 12 ICMS) PCT 1,010KG | UN | KG | PCT | 1,01 | mesmo produto do 1130 em outra embalagem |
| 968 | PAPRICA DOCE (C/ 12 ICMS) PCT 1,010KG | UN | KG | PCT | 1,01 | |
| 1317 | PAPRICA PICANTE 500G MON CHEF | — | KG | PCT | 0,5 | |
| 1073 | PAPRICA PICANTE (C/ 12 ICMS) PCT 1,010KG | UN | KG | PCT | 1,01 | mesmo produto do 1317 e do 1617 (lote 1) |
| 1555 | PASSATA RUSTICA MEMB | — | KG | UN | conferir | peso da embalagem sai da nota |
| 2059 | PASSATA SACCIALI 1 5KG | UN | KG | UN | 1,5 | |
| 424 | PASTA DE AMENDOIM 1KG | UN | KG | UN | 1 | |
| 1574 | PASTA DE AMENDOIM (ANDREIA) PT 1,001KG | UN | KG | UN | 1,001 | provável duplicado do 424 |
| 426 | PASTA DE PISTACHE 1KG | KG | KG | UN | 1 | estoque já certo; falta a compra |
| 3444 | PASTA FRESCA PASINI -1KG | — | KG | PCT | 1 | pelo código (PASPAS1) é a farinha Pasini para massa fresca, não a massa |
| 157 | PASTILHAS GRANEL PARA CAPUCCINO | KG | KG | KG | 1 | já está certo |
| 849 | PASTILHAS GRANEL PARA CHOCOLATE QUENTE | KG | KG | KG | 1 | já está certo |
| 1226 | PASTRAMI, FOOD SERVICE, PECA, VPP | KG | KG | KG | 1 | já está certo |
| 1428 | PATE DE FIGADO DE PATO TIPO MOUSSE DE FOIE DE CANARD 95G | UN | UN | UN | 1 | já está certo; pote de revenda |
| 1429 | PATE DE OVAS DE TAINHA TIPO TARAMA 85G | UN | UN | UN | 1 | já está certo; pote de revenda |
| 1427 | PATE DE PATO TIPO RILLETTES DE CANARD 100G | UN | UN | UN | 1 | já está certo; pote de revenda |
| 770 | PATINHO RESFRIADA/MOIDO | KG | KG | KG | 1 | já está certo |
| 505 | PEITO PERU FAT SOLTIS 200G 3UN CX21UN | UN | KG | PCT | 0,6 | pacote com 3 bandejas de 200 g; segunda embalagem: CX = 4,2 |
| 1253 | PEITO SEM OSSO RESFRIADA/INTEIRO | KG | KG | KG | 1 | já está certo; pelo código (P0044) é peito bovino |
| 1050 | PEPINO | KG | KG | KG | 1 | hortifruti já tratado |
| 768 | PEPINO CONS VD 300G HEMMER | — | KG | UN | 0,3 | conserva; peso do rótulo |
| 144 | PEPINO JAPONES | KG | KG | KG | 1 | já está certo |
| 372 | PEPITA DE ABOBORA NATURAL PREMIUM AA PCT 1KG | UN | KG | PCT | 1 | |
| 605 | PEPITA DE GIRASSOL 1KG | UN | KG | PCT | 1 | provável duplicado do 374 (lote 4) |
| 417 | PEPITA DE GIRASSOL GENERAL 25KG (TR2) | — | KG | SC | 25 | mesmo produto do 605 em saco |
| 1528 | PERA | KG | KG | KG | 1 | hortifruti já tratado |
| 1622 | PERA METADES SECA PCT 500G | UN | KG | PCT | 0,5 | |
| 1914 | PERNIL SUINO RESFRIADO KG | KG | KG | KG | 1 | já está certo |
| 1873 | PESSEGO | KG | KG | KG | 1 | hortifruti já tratado |
| 30 | PF-10 BANDEJA RETANGULAR (C/100) - PACKFORM | CX | UN | PCT | 100 | embalagem |
| 31 | PF-13 BANDEJA RETANGULAR (C/100) - PACKFORM | CX | UN | PCT | 100 | embalagem |
| 32 | PF-18 BANDEJA RETANGULAR (C/100) - PACKFORM | CX | UN | PCT | 100 | embalagem |
| 3642 | PH F DUPLA MILI 30M C 32 | UN | UN | FD | 32 | papel higiênico; conta-se o rolo; material de limpeza |
| 1725 | PICANHA RESFRIADA/A | KG | KG | KG | 1 | já está certo |
| 746 | PIMENTA CAYENA EM PO PCT 1,010KG | UN | KG | PCT | 1,01 | |
| 2064 | PIMENTA (KG) | KG | KG | KG | 1 | já está certo; o nome não diz qual pimenta |
| 1498 | PIMENTAO AMARELO | KG | KG | KG | 1 | hortifruti já tratado |
| 2008 | PIMENTÃO COLORIDO | KG | KG | KG | 1 | já está certo |
| 136 | PIMENTAO VERDE | KG | KG | KG | 1 | hortifruti já tratado |
| 72 | PIMENTAO VERMELHO | KG | KG | KG | 1 | hortifruti já tratado |
| 869 | PIMENTA PRETA DO REINO GRAO PCT 1KG | UN | KG | PCT | 1 | as três pimentas-do-reino em grão são candidatas a fusão |
| 2883 | PIMENTA PRETA GRAO 500G MON CHEF | G | KG | PCT | 0,5 | hoje em G; o padrão combinado é KG |
| 531 | PIMENTA REINO PRETA GRAO 500G NUANCE | — | KG | PCT | 0,5 | |
| 2058 | PINHAO KG | KG | KG | KG | 1 | já está certo |
| 2057 | PIPOCA CALDAO 400G | UN | KG | PCT | 0,4 | |
| 125 | PISTACHE CRU SEM CASCA PCT 1KG | UN | KG | PCT | 1 | |
| 1755 | PITAYA | UN | UN | UN | 1 | hortifruti já tratado |
| 1221 | PODDI REFRIGERANTE LARANJA CITRUS 300ML | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 1220 | PODDI REFRIGERANTE UVA CREAM 300ML | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 1699 | PO DECO 5G AZUL CEU MAGO | UN | UN | UN | 1 | já está certo; potinho de pó, não se pesa |
| 1694 | PO DECORACAO 5G VERDE SEREIA MAGO | UN | UN | UN | 1 | já está certo |
| 944 | PO DECORACAO 8G OURO MAGO | UN | UN | UN | 1 | já está certo |
| 379 | POD KOMBUCHA ABACAXI E HORTELA 310 ML | UN | UN | UN | 1 | já está certo; provável duplicado do 2860 (lote 5) |
| 377 | POD KOMBUCHA FRUTAS VERMELHAS 310 ML | UN | UN | UN | 1 | já está certo; provável duplicado do 2861 (lote 5) |
| 85 | POD KOMBUCHA LIMAO E GENGIBRE 400ML | UN | UN | UN | 1 | já está certo |
| 1219 | POD KOMBUCHA MARACUJA E HIBISCO 400ML | UN | UN | UN | 1 | já está certo |
| 99 | POD KOMBUCHA MORANGO E HIBISCO 400ML | UN | UN | UN | 1 | já está certo; provável duplicado do 2024 (lote 5) |
| 380 | POD KOMBUCHA TANGERINA 310 ML | UN | UN | UN | 1 | já está certo |
| 378 | POD KOMBUCHA UVA 310 ML | UN | UN | UN | 1 | já está certo; provável duplicado do 2862 (lote 5) |
| 86 | POD KOMBUCHA UVA 400ML | UN | UN | UN | 1 | já está certo |
| 1218 | POD SMART DRINKS CALM 269ML | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 1217 | POD SMART DRINKS ENERGY 269ML | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 1216 | POD SMART DRINKS FOCUS 269ML | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 669 | POLENTA 500G SINHA | — | KG | PCT | 0,5 | existe ATIVO 881 (POLENTINA) — candidato a fusão |
| 1116 | POLVILHO AZEDO 500G FRITZ E FRIDA | UN | KG | PCT | 0,5 | |
| 305 | POLVILHO AZEDO PCT 1KG | UN | KG | PCT | 1 | mesmo produto do 1116 em outra embalagem |
| 1115 | POLVILHO DOCE 500G FRITZ E FRIDA | UN | KG | PCT | 0,5 | |

## Lote 8 — POLVILHO DOCE (FECULA)… a SACO CONF…

> Feito em 07/10/2026 pelo conector de produção: INSUMOS em rascunho de **POLVILHO DOCE (FECULA)…**
> a **SACO CONF…** (98 produtos; offsets 750 a 849). Nada foi gravado.
> Ficaram de fora 2 ARQUIVADOS (181, 182).
> Próximo lote começa no offset 850.

### Regras acrescentadas

20. **"P/A …" no fim do nome** (fornecedor de frios e laticínios) diz a unidade em que ele vende: essa é a unidade de compra. A caixa que aparece antes é só a segunda embalagem. Sete linhas dos lotes 2, 4 e 5 foram corrigidas por isso.
21. **Queijo em peça de peso variável ("PC+-xKG")** → estoque **KG**, compra **KG**, fator 1: a nota vem com o peso real. Conferir na `previa_de_fusao` (`um_omie`) antes de gravar.
22. **Queijo pequeno com peso no nome e código próprio do produtor** (125 g, 150 g) → tratado como revenda, em **UN**.

### Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 306 | POLVILHO DOCE (FECULA DE MANDIOCA) PCT 1KG | UN | KG | PCT | 1 | mesmo produto do 1115 (lote 7) em outra embalagem |
| 449 | POPCORN MICRO YOKI M | — | UN | UN | 1 | pipoca de micro-ondas |
| 2105 | POP CORN YOKI MANT 100G | UN | UN | UN | 1 | já está certo; provável duplicado do 449 |
| 1071 | POTE BELEM 240 ML (CAIXA C/ 24) - METALICAS - ROSE GOLD | CX | UN | CX | 24 | pote de vidro; embalagem |
| 2888 | POTE DE VIDRO BELEM 240 ML (CAIXA C/ 24) - METALICAS - PRETA | CX | UN | CX | 24 | embalagem |
| 1843 | POTE DE VIDRO BERLIN 596 ML (CAIXA C/ 30) - METALICAS - PRETA | CX | UN | CX | 30 | embalagem |
| 1539 | POTE DE VIDRO MINI BELEM 150 ML (CAIXA C/ 24) - METALICAS - ROSE GOLD | CX | UN | CX | 24 | embalagem |
| 2020 | POTES BRANCOS 500ML 268/255 | — | UN | CX | conferir | potes por caixa |
| 1225 | PRESUNTO BRASEADO MAXIMUS, FOOD SERVICE, PECA, VPP | KG | KG | KG | 1 | já está certo |
| 1154 | PRESUNTO CRU FATIADO 30 UNI 80G GRN | KG | KG | CX | 2,4 | estoque já certo; caixa com 30 envelopes de 80 g |
| 98 | PRESUNTO CRU FATIADO 500G CX 4KG | KG | KG | CX | 4 | estoque já certo; segunda embalagem: PCT = 0,5 |
| 590 | PRESUNTO CRU FATIADO 500G CX 4KG GRN | KG | KG | CX | 4 | provável duplicado do 98 |
| 929 | PRESUNTO FAT 180G 4UN CX16UN P/A PCT 4UN | UN | KG | PCT | 0,72 | pacote com 4 bandejas de 180 g; segunda embalagem: CX = 2,88 |
| 94 | PRESUNTO FAT SOLTIS 200G 3UN CX21UN P/A PCT 3UN | UN | KG | PCT | 0,6 | pacote com 3 bandejas de 200 g; segunda embalagem: CX = 4,2 |
| 381 | PRIMOSALE ATACADO | KG | KG | KG | 1 | já está certo |
| 545 | PRIMOSALE ATACADO 2 | KG | KG | UN | conferir | estoque já certo; o "2" sugere peça de 2 kg; provável duplicado do 381 |
| 906 | PSYLLIUM COMERCIAL SC 10KG | UN | KG | SC | 10 | |
| 373 | PSYLLIUM PREMIUM PCT 1KG | UN | KG | PCT | 1 | |
| 2094 | PUR TOM PASSATA STA 680G | UN | KG | UN | 0,68 | |
| 2085 | QJ A TAL DA CHICA PC | KG | KG | KG | 1 | já está certo |
| 311 | QJO BOM DESTINO 160G BOL | UN | KG | UN | 0,16 | supondo uso em receita; se for vendido inteiro: UN, fator 1 |
| 1442 | QJO BRIE PC+-1,2KG CX+-2,4KG A PC +-1,2KG | KG | KG | KG | 1 | já está certo; peso variável; os três bries são candidatos a fusão |
| 791 | QJO BRIE PC+-1KG CX+-2KG A PC +-1KG | KG | KG | KG | 1 | já está certo; peso variável |
| 1898 | QJO BRIE PC+-1KG CX+-3KG A PC +-1KG | KG | KG | KG | 1 | já está certo; peso variável |
| 1970 | QJO COALHO PC+-2KG CX+-25KG A PC +-2KG | KG | KG | KG | 1 | já está certo; peso variável |
| 22 | QJO GORGONZOLA (AZUL) PC+-3KG CX+-6KG A PC +-3KG | KG | KG | KG | 1 | já está certo; os quatro gorgonzolas são candidatos a fusão |
| 1170 | QJO GORGONZOLA PC+-3,3KG CX+-6,6KG A PC +-3,3KG | KG | KG | KG | 1 | já está certo; peso variável |
| 1421 | QJO GORGONZOLA PC+-3KG CX+-3KG CX +-3KG | KG | KG | KG | 1 | já está certo; peso variável |
| 1234 | QJO GORGONZOLA PC+-3KG CX+-6KG A PC +-3KG | KG | KG | KG | 1 | já está certo; peso variável |
| 739 | QJO MUSSARELA BUF PC+-3,75KG CX+-22KG A PC +-3,75KG | KG | KG | KG | 1 | já está certo; búfala, não fundir com a mussarela comum |
| 3115 | QJO MUSSARELA FAT 150G 4UN CX28UN P/A PCT 4UN | UN | KG | PCT | 0,6 | pacote com 4 bandejas de 150 g; segunda embalagem: CX = 4,2 |
| 740 | QJO MUSSARELA FAT ITF 1KG CX21KG P/A PC 1KG | KG | KG | PC | 1 | estoque já certo; segunda embalagem: CX = 21 |
| 868 | QJO MUSSARELA FAT ITF 1KG CX24KG P/A PC 1KG | KG | KG | PC | 1 | estoque já certo; segunda embalagem: CX = 24; provável duplicado do 740 |
| 357 | QJO MUSSARELA FAT ITF 2KG FD24KG P/A PC 2KG | KG | KG | PC | 2 | estoque já certo; segunda embalagem: FD = 24 |
| 97 | QJO MUSSARELA FAT ITF 4KG CX24KG P/A PC 4KG | KG | KG | PC | 4 | estoque já certo; segunda embalagem: CX = 24 |
| 12 | QJO MUSSARELA PC+-4KG CX+-24KG A PC +-4KG | KG | KG | KG | 1 | já está certo; peça inteira, peso variável |
| 1128 | QJO MUSSARELA PC+-4KG CX+-24KG A PCT +-4KG | KG | KG | KG | 1 | já está certo; provável duplicado do 12 |
| 1119 | QJO MUSS BUF BOLA G 50G BLD1KG CX4BLD PA BLD 1KG | UN | KG | BLD | 1 | balde de 1 kg; segunda embalagem: CX = 4 |
| 1098 | QJO MUSS BUF BOLA M 23G BLD1KG CX4BLD PA BLD 1KG | UN | KG | BLD | 1 | balde de 1 kg; segunda embalagem: CX = 4 |
| 1055 | QJO MUSS BUF BOLA P 10G BLD1KG CX4BLD PA BLD 1KG | UN | KG | BLD | 1 | balde de 1 kg; segunda embalagem: CX = 4 |
| 1455 | QJO MUSS BUF BOLA P 10G POT500G FD2UN P FD 2UN | UN | KG | FD | 1 | fardo com 2 potes de 500 g; mesmo produto do 1055 |
| 2104 | QJO MUSS CASA QUEIJO 300 | UN | KG | UN | 0,3 | |
| 1014 | QJO PARMESAO FAIXA AZUL PC+-7,5KG PC +-7,5KG | KG | KG | KG | 1 | já está certo; os quatro parmesões são candidatos a fusão |
| 287 | QJO PARMESAO PC+-5KG CX+-22KG A PC +-5KG | KG | KG | KG | 1 | já está certo; peso variável |
| 1096 | QJO PARMESAO PC+-6KG CX+-10KG A PCT +-6KG | KG | KG | KG | 1 | já está certo; peso variável |
| 21 | QJO PARMESAO PC+-7,5KG PC +-7,5KG | KG | KG | KG | 1 | já está certo; peso variável |
| 995 | QJO QUARK LAC LELO 280G | UN | KG | UN | 0,28 | |
| 1775 | QUEIJO BRIE CRUZILIA KG | KG | KG | KG | 1 | já está certo |
| 292 | QUEIJO DOS MENDES | KG | KG | KG | 1 | já está certo |
| 18 | QUEIJO FAMILIA SUDBRACK GRANDE | KG | KG | KG | 1 | já está certo |
| 757 | QUEIJO FETA DE LEITE DE CABRA | KG | KG | KG | 1 | já está certo |
| 1201 | QUEIJO GORGONZOLA QUATA | KG | KG | KG | 1 | já está certo |
| 756 | QUEIJO MAASDAM | KG | KG | KG | 1 | já está certo |
| 422 | QUEIJO MORRO AZUL 125G | UN | UN | UN | 1 | já está certo; peça de revenda; se entrar em receita: KG, fator 0,125 |
| 1439 | QUEIJO MUSSARELA CASTELENSE 4 KG | KG | KG | KG | 1 | já está certo; peça de cerca de 4 kg |
| 16 | QUEIJO MUSS. DE BUFALA CEREJINHA (BALDE) | UN | KG | BLD | conferir | provável balde de 1 kg; mesmo produto do 1055 |
| 440 | QUEIJO POMERODE 150G | UN | UN | UN | 1 | já está certo; peça de revenda |
| 17 | QUEIJO POMERODE KG | KG | KG | KG | 1 | já está certo |
| 1335 | QUEIJO QUATA KG PECA TP | KG | KG | KG | 1 | já está certo |
| 1 | QUEIJO TIPO BRIE SANDUICHE VERMONT EM KG | KG | KG | KG | 1 | já está certo |
| 293 | QUEIJO TIPO BRIE VERMONT EM KG REDONDO (G) | KG | KG | KG | 1 | já está certo |
| 755 | QUEIJO TOMME CAPRA DE LEITE DE CABRA | KG | KG | KG | 1 | já está certo |
| 760 | QUEIJO VALE DO TESTO GRANDE - 3M | KG | KG | KG | 1 | já está certo |
| 1143 | QUEIJO VALE DO TESTO PEQ - 12M | KG | KG | KG | 1 | já está certo; maturação diferente, não fundir |
| 1144 | QUEIJO VALE DO TESTO PEQ - 3M | KG | KG | KG | 1 | já está certo |
| 185 | QUINOA BRANCA COZ 1KG BURG | — | KG | UN | 1 | cozida — não fundir com a seca |
| 397 | QUINOA BRANCA GRAO COMERCIAL (NAC) PCT 1KG | UN | KG | PCT | 1 | seca |
| 132 | RADITE | UN | UN | UN | 1 | hortifruti já tratado |
| 71 | RADITE ROXO | UN | UN | UN | 1 | hortifruti já tratado |
| 2033 | REFIL GÁS BUTANO | UN | UN | UN | 1 | já está certo; os três refis duplicam o 1040 (lote 4) |
| 838 | REFIL GAS BUTANO MODELO 6019 | UN | UN | UN | 1 | já está certo |
| 1576 | REFIL GAS BUTANO P/ MACARICO MODELO 6019 | UN | UN | UN | 1 | já está certo |
| 892 | REFIL SAB CENTURY ESP 600ML ANTISSEPTICA | UN | UN | UN | 1 | já está certo; material de limpeza |
| 891 | REFIL SAB CENTURY ESPUMA 600ML ERVA DOCE | UN | UN | UN | 1 | já está certo; material de limpeza |
| 924 | REFIL SAB ESPUMA 700ML ERVA DOCE | UN | UN | UN | 1 | já está certo; material de limpeza |
| 925 | REFIL SAB ESPUMA 700ML TRICLOSAN | UN | UN | UN | 1 | já está certo; material de limpeza |
| 2089 | REFR COCA COLA 2L | UN | UN | UN | 1 | já está certo |
| 2087 | REFRIG ANTAR 2L | UN | UN | UN | 1 | já está certo |
| 1884 | REFRI ORGANICO COLA LT 350ML WEWI | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 318 | REFRI ORGANICO COLA VD 255ML WEWI | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 1947 | REFRI ORGANICO GUARANA 350ML WEWI | — | UN | UN | 1 | bebida de revenda |
| 81 | REFRI ORGANICO GUARANA VD 255ML WEWI | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 82 | REFRI ORGANICO LARANJA VD 255ML WEWI | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 2125 | REPOLHO | UN | UN | UN | 1 | hortifruti já tratado |
| 1516 | REPOLHO ROXO | UN | UN | UN | 1 | já está certo; por cabeça |
| 2153 | REQ CREM CATUPIRY 400G | UN | KG | UN | 0,4 | |
| 2050 | REQUEIJ CREM TIROL 400G | UN | KG | UN | 0,4 | provável duplicado do 2153 |
| 546 | RICOTA ATAC 2 | KG | KG | UN | conferir | estoque já certo; o "2" sugere peça de 2 kg; provável duplicado do 382 |
| 382 | RICOTA ATACADO | KG | KG | KG | 1 | já está certo |
| 353 | RICOTA CREMOSA FRESCA DE BUFALA FAZLATI 250 GR | KG | KG | UN | 0,25 | estoque já certo; falta a compra |
| 516 | ROLO MASS PREP TORTA 8241-CX C/24X1 | CX | UN | CX | 24 | o nome não deixa claro se é massa pronta ou utensílio — conferir |
| 1878 | ROMA | — | KG | KG | 1 | romã; se vier por unidade: UN — conferir |
| 139 | RUCULA | UN | UN | UN | 1 | hortifruti já tratado |
| 898 | RUCULA BABY LEAF (IN) | UN | UN | UN | 1 | já está certo |
| 647 | RUM MALIBU 750ML | — | UN | UN | 1 | garrafa |
| 724 | SABONETE REFIL ANTISSEPTICO VERDESAN 800 ML | UN | UN | UN | 1 | já está certo; material de limpeza |
| 1916 | SACO ADESIVADO BOPP S/ FURO 100 UN 14X20+3 | UN | UN | PCT | 100 | embalagem |
| 1636 | SACO CONF DESC 26X47CM C/50 (MAGO) | UN | UN | PCT | 50 | manga de confeiteiro, como as do lote 5 |

## Lote 9 — SACO DE PAPEL KRAFT… a TOMILHO

> Feito em 07/10/2026 pelo conector de produção: INSUMOS em rascunho de **SACO DE PAPEL KRAFT…**
> a **TOMILHO** (92 produtos; offsets 850 a 949). Nada foi gravado.
> Ficaram de fora 1 ATIVO (83, SAL REFINADO) e 7 ARQUIVADOS (sacos de lixo).
> Próximo lote começa no offset 950 e é o último (o total é 1.016).

### Regra acrescentada

23. **Saco para vácuo (nylon-poli)** → fica em **KG**: o fornecedor vende por peso e o cadastro já está assim. Contar por saco exigiria saber quantos vêm no quilo de cada medida.

### Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 162 | SACO DE PAPEL KRAFT 1KG LISO (PACOTE C/ 500) - DUMAR | UN | UN | PCT | 500 | embalagem |
| 468 | SACO FREEZER DOVER R | — | UN | UN | 1 | rolo; nome truncado |
| 1773 | SACO INC. 15X20CM RIZZO 100UN | — | UN | PCT | 100 | embalagem |
| 1186 | SACO INC.25X37CM 100UN RIZZO | UN | UN | PCT | 100 | embalagem |
| 1278 | SACO INC. 30X45CM RIZZO 100UN | UN | UN | PCT | 100 | embalagem |
| 2196 | SACO INC.50X70CM RIZZO 25UN | UN | UN | PCT | 25 | embalagem |
| 2195 | SACO INC. 80X90CM RIZZO 25UN | UN | UN | PCT | 25 | embalagem |
| 491 | SACO KRAFT - 20,0 X 11,5 X 36,0 CM - SKDP-001 - BOTANE | UN | UN | CX | conferir | sacola personalizada; quantas por caixa sai da nota |
| 1081 | SACO KRAFT - 29,0 X 17,0 X 38,0 CM - SKDP-004 - BOTANE | UN | UN | CX | conferir | idem |
| 562 | SACO KRAFT C/VISOR 160X240X90MM C10 | UN | UN | PCT | 10 | embalagem |
| 3640 | SACO LIXO DOVER ROLL 30L | UN | UN | UN | 1 | já está certo; rolo; material de limpeza |
| 38 | SACO NYLONPOLI 15X20 VACUO | KG | KG | KG | 1 | já está certo; vendido por peso |
| 579 | SACO NYLONPOLI 18X25 VACUO | KG | KG | KG | 1 | já está certo; vendido por peso |
| 37 | SACO NYLONPOLI 20X30 VACUO | KG | KG | KG | 1 | já está certo; vendido por peso |
| 223 | SACO NYLONPOLI 25X35 VACUO | KG | KG | KG | 1 | já está certo; vendido por peso |
| 1087 | SACO PLASTICO - 3946 | UN | UN | PCT | conferir | o nome não diz medida nem quantidade |
| 1915 | SACOS ADESIVADOS TRANSPARENTES BOPP 8X25 100UND | — | UN | PCT | 100 | embalagem |
| 1280 | SACO TRANSP.ADESIV.15X21 100UN GALA | UN | UN | PCT | 100 | embalagem |
| 1401 | SACO TRANSP.ADESIV.15X30 100UN GALA | UN | UN | PCT | 100 | embalagem |
| 1771 | SACO TRANSP.ADESIV.25X37 100UN GALA | UN | UN | PCT | 100 | embalagem |
| 1281 | SACO TRANSP.ADESIV.30X48 100UN GALA | UN | UN | PCT | 100 | embalagem |
| 596 | SALAME ITALIANO FAT PCT 1KG CX10KG P/A PC 1KG | KG | KG | PC | 1 | estoque já certo; segunda embalagem: CX = 10 |
| 997 | SALG DORITOS 120G QJO | UN | UN | UN | 1 | já está certo; se entrar em receita por peso: KG, fator 0,12 |
| 1025 | SALG DORITOS 32G QUEIJO NACHO | — | UN | UN | 1 | |
| 2092 | SALG MILHO DORITOS 257G | UN | UN | UN | 1 | já está certo |
| 550 | SAL GROSSO 1KG FRITZ E FRIDA | — | KG | PCT | 1 | |
| 1653 | SAL MAR REF SOSAL 1KG | UN | KG | PCT | 1 | existe ATIVO 83 (SAL REFINADO) — candidato a fusão |
| 3636 | SAL MAR SOSAL GRSO 1KG | UN | KG | PCT | 1 | sal grosso; provável duplicado do 550 |
| 1907 | SALSA EM PO - 500G | UN | KG | PCT | 0,5 | |
| 1663 | SALSAO | — | UN | UN | 1 | por maço |
| 2055 | SALSICHA CG PCT 3KG CX12KG P/A PCT 3KG | KG | KG | PCT | 3 | estoque já certo; segunda embalagem: CX = 12 |
| 1703 | SALSINHA | UN | UN | UN | 1 | hortifruti já tratado; fator do código que vem em kg continua pendente |
| 1626 | SALVIA FOLHAS (NAC) PCT 500G | UN | KG | PCT | 0,5 | folha seca |
| 1403 | SAQUE MIRIN 500ML KENKO | UN | L | GF | 0,5 | |
| 1448 | SAUVIGNON BLANC ESTATE (TERRANOBLE) 2024 U | — | UN | UN | 1 | garrafa avulsa (código é EAN) |
| 578 | SAUVIGNON BLANC (LAS MORAS) 2023 | — | UN | CX | conferir | provável caixa de 6 |
| 384 | SCAMORZA DEFUMADA ATACADO | KG | KG | KG | 1 | já está certo |
| 416 | SEMENTE DE ABOBORA S/C AA BAOQING 25KG | — | KG | SC | 25 | |
| 933 | SEMENTE DE ABOBORA S/C AA NONGAN 25KG | — | KG | SC | 25 | provável duplicado do 416 |
| 606 | SEMENTE DE ABOBORA S/C NATURAL AA 1KG | UN | KG | PCT | 1 | mesmo produto do 372 (lote 7) |
| 371 | SEMENTE DE CHIA PREMIUM (*) PCT 1KG | UN | KG | PCT | 1 | |
| 398 | SEMENTE DE CHIA PREMIUM PCT 1KG | UN | KG | PCT | 1 | duplicado do 371 |
| 1665 | SE- SACOLA NYLON 300 | — | UN | UN | conferir | o nome não diz se "300" é quantidade |
| 1163 | SHIMAYA KATSUO DASHI 1KG | UN | KG | PCT | 1 | |
| 3007 | SHISO | CX | UN | UN | 1 | folha em caixinha; a unidade é a caixinha, como o ATIVO 897 (MINI FOLHAS MICROVERDE) |
| 1064 | SICAO CACAU EM PO 100% 500G | G | KG | PCT | 0,5 | hoje em G; provável duplicado do 19 e do 1375 (lote 1) |
| 3025 | SICAO CACAU EM PO PRETO 100% 500G | UN | KG | PCT | 0,5 | cacau black, não fundir com o 1064 |
| 1243 | SICAO CHOCO AMARGO 70% GOTAS 1,01KG | UN | KG | PCT | 1,01 | provável duplicado do 1092 (lote 1) |
| 990 | SICAO CHOCOLATE AO LEITE GOTAS 2,05KG | — | KG | PCT | 2,05 | |
| 1952 | SICAO CHOCOLATE BRANCO 2,1KG | — | KG | PCT | 2,1 | |
| 1003 | SICAO CHOCOLATE BRANCO GOTAS 2,05KG | KG | KG | PCT | 2,05 | estoque já certo; provável duplicado do 989 (lote 1) |
| 1977 | SICAO CHOCO MEIO AMARGO 2,1KG | — | KG | PCT | 2,1 | mesma família do 1093 e do 1189 (lote 1) |
| 519 | SOJA VERDE PRECOZIDA E CONGELAD EM GRAOS PCT 250G | UN | KG | PCT | 0,25 | é edamame; ver os do lote 2 |
| 3006 | SORREL | CX | UN | UN | 1 | folha em caixinha; a unidade é a caixinha |
| 171 | STEINHAEGER DOBLE W 900 ML (12) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 93 | ST PIERRE AGUA TONICA - LATA 6X270ML | — | UN | PCT | 6 | conta-se a lata |
| 1015 | STRACCIATELLA ATAC 2 | KG | KG | UN | conferir | estoque já certo; o "2" sugere pote de 2 kg; provável duplicado do 383 |
| 383 | STRACCIATELLA ATACADO | KG | KG | KG | 1 | já está certo |
| 488 | SUCO DE UVA INTEGRAL 1L | UN | UN | UN | 1 | já está certo; garrafa de revenda; se for servido em copo: L, fator 1 |
| 487 | SUCO DE UVA INTEGRAL 250ML | UN | UN | UN | 1 | já está certo; garrafa de revenda |
| 1031 | SUCO DE UVA INTEGRAL 300ML - TORRE DI LUNA | UN | UN | UN | 1 | já está certo; garrafa de revenda |
| 886 | SUCO SUQ 2 8L LAR INTEG | UN | L | GL | 2,8 | suco de laranja; ver os néctares 521 e 522 (lote 6) |
| 1806 | SUPER LIGA NEUTRA 100G DUAS RODAS | UN | KG | UN | 0,1 | |
| 1061 | TAMARAS S/C 1KG | UN | KG | PCT | 1 | as seis tâmaras são o mesmo produto — candidatas a fusão |
| 645 | TAMARAS S/C 5KG | CX | KG | CX | 5 | |
| 821 | TAMARAS S/C ROYAL PALM 5KG | CX | KG | CX | 5 | |
| 310 | TAMARAS SECA SEM CAROCO CX 5KG | UN | KG | CX | 5 | |
| 457 | TAMARAS SECA SEM CAROCO (PALM STAR) CX 5KG | UN | KG | CX | 5 | |
| 1141 | TAMARAS SECA SEM CAROCO PCT 1KG | UN | KG | PCT | 1 | |
| 1960 | TAMPA 90MM CAPPUCINO POLPA VEGETAL - 20 X 50 (1000UN. P/CX) | CX | UN | CX | 1000 | segunda embalagem: PCT = 50 |
| 663 | TAMPA PLASTICA C/FURO TPF-301 C/50 UND - ALTACOPPO | UN | UN | PCT | 50 | par do copo 664 (lote 1) |
| 661 | TAMPA PLASTICA C/FURO TPF-451 C/50 UND - ALTACOPPO | UN | UN | PCT | 50 | par do copo 662 (lote 1) |
| 1293 | TAMPA PP BANDEJA RETANGULAR DE FIBRA VEGETAL CR - 6 X 50 (300UN. P/CX) | CX | UN | CX | 300 | segunda embalagem: PCT = 50 |
| 1520 | TANGERINA | KG | KG | KG | 1 | hortifruti já tratado |
| 824 | TATU RESFRIADA/INTEIRO | KG | KG | KG | 1 | já está certo |
| 2159 | TEMPERO EM PO 5 ESPECIARIAS - FIVE SPICE | UN | KG | UN | conferir | peso do frasco sai da nota |
| 2097 | TEMP PAPRICA DEF 250G NUANCE | — | KG | PCT | 0,25 | páprica defumada; ver 1130 e 747 (lote 7) |
| 772 | TEQUILA JOSE CUERVO SILVER 750 ML (12) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 3559 | THAI RED CURRY BOMBAY VD 60 G | UN | KG | UN | 0,06 | |
| 1354 | TIRA DE ACETATO TRANSPARENTE 12CM X 2KG | UN | UN | UN | 1 | já está certo; rolo de 2 kg, conta-se o rolo |
| 1714 | TOMATE | KG | KG | KG | 1 | hortifruti já tratado |
| 137 | TOMATE CEREJA | KG | KG | KG | 1 | hortifruti já tratado; fatores das bandejas continuam pendentes |
| 366 | TOMATE GRAPE | UN | UN | UN | 1 | hortifruti já tratado; fatores das embalagens continuam pendentes |
| 391 | TOMATE ITALIANO | KG | KG | KG | 1 | hortifruti já tratado; fator do código que vem em caixa continua pendente |
| 1991 | TOMATE PELADO 2,5KG FRITZ E FRIDA | KG | KG | UN | 2,5 | estoque já certo; as sete latas de tomate pelado são candidatas a fusão |
| 1162 | TOMATE PELADO 2,5KG MASTROIANI | UN | KG | UN | 2,5 | |
| 1751 | TOMATE PELADO 2,5KG SACCIALI | UN | KG | UN | 2,5 | |
| 741 | TOMATE PELADO LATA 2,55KG OPERA | — | KG | UN | 2,55 | |
| 89 | TOMATE PELADO LATA 2,5KG OLE | UN | KG | UN | 2,5 | |
| 554 | TOMATE PELADO LATA 2,5KG OPERA I | — | KG | UN | 2,5 | |
| 1567 | TOMATE PELADO PREDILECTA 1,5KG | UN | KG | UN | 1,5 | |
| 3637 | TOMILHO | UN | UN | UN | 1 | já está certo; maço |

## Lote 10 — TOM PELADO… a ZERO CAL… (último)

> Feito em 07/10/2026 pelo conector de produção: INSUMOS em rascunho de **TOM PELADO…** a
> **ZERO CAL…** (65 produtos; offsets 950 a 1015). Nada foi gravado.
> Ficou de fora 1 ATIVO (1814, VINAGRE HEINIG ARROZ).
> **Fim da lista**: os 1.016 INSUMOS foram percorridos. Total analisado nos dez lotes: 785 rascunhos.
> De A até BIT… (offsets 0 a 49) não há rascunho: as 50 linhas são de cadastros ATIVOS. Os offsets 50 a 149
> são a faixa do lote 1 e não foram relidos nesta rodada.

### Regras acrescentadas

24. **Vinagre** → estoque **L**, compra **GF**, fator = litros da garrafa.
25. **Vinho de mesa é de cozinha** → estoque **L**, compra na garrafa/garrafão, fator = litros. **Todos os outros vinhos** → estoque **UN**, a garrafa. **Decisão do Marcelo em 07/10/2026.** São de mesa os que trazem "MESA" no nome e os de garrafão, PET ou 1,5 L (Girola, Vailatti, Sinuelo, Campo Largo, Garibaldi): 11 linhas no lote 10. MOSCATO ALLEANZA (186) é de cozinha e CABERNET SAUVIG (769) fica em UN, ambos confirmados por ele.
26. **Vodca, uísque, vermute e xarope de bar** seguem a regra 12: **UN**, a garrafa. Vermutes e xaropes confirmados pelo Marcelo em 07/10/2026.

### Tabela

| Id | Produto | Hoje | Estoque | Compra | Fator | Observação |
|---|---|---|---|---|---|---|
| 1464 | TOM PELADO TOSCANA 2 5KG | UN | KG | UN | 2,5 | lata; soma-se às sete do lote 9 |
| 1437 | TOM PEL STA TAVOL 2 55KG | UN | KG | UN | 2,55 | lata; idem |
| 104 | TOUCA TELADA PRETA C/ELASTICO C/10 UND. | UN | UN | PCT | 10 | descartável, não insumo de receita |
| 1683 | TRUFA DE CHOCOLATE AMARGO MONALISA CALLEBAUT C/504UN | CX | UN | CX | 504 | casquinha de trufa; conta-se a peça |
| 2890 | U.EMB. DE ALUM. RED. C/TAMPA PLASTICA 19X3CM (PCT C/50UN.) - 600ML | UN | UN | PCT | 50 | embalagem |
| 149 | UNTA FACIL CERA DE ABELHA SPRAY 600ML | UN | UN | UN | 1 | já está certo; ver o 1764 (lote 2), de 400 ml |
| 1180 | UVA PASSA CLARA PCT 1KG | UN | KG | PCT | 1 | |
| 1181 | UVA PASSA ESCURA ARGENTINA PCT 1KG | UN | KG | PCT | 1 | as três passas escuras são candidatas a fusão |
| 1680 | UVA PASSA ESCURA COMERCIAL PCT 1KG | UN | KG | PCT | 1 | |
| 1132 | UVA PASSAS PRETA S/S 1KG | UN | KG | PCT | 1 | |
| 1507 | UVA THOMPSON | KG | KG | KG | 1 | hortifruti já tratado; fator da bandeja de 500 g continua pendente |
| 1534 | UVA VITORIA | — | KG | KG | 1 | |
| 3639 | VASSOURA CONDOR MADRI CC | UN | UN | UN | 1 | já está certo; utensílio de limpeza |
| 1723 | VERMOUTH MARTINI ROSSO 750 ML (12/64) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 1302 | VERMUTE ROSSO SCHLUCK 700 ML | — | UN | UN | 1 | garrafa |
| 2002 | VH CHI CAMIN CHILE 750ML | UN | UN | UN | 1 | garrafa; chileno (EAN 780), não é vinho de mesa |
| 1844 | VH GIROLA BCO SC 4 5L | UN | L | GL | 4,5 | vinho de mesa em garrafão: cozinha |
| 2060 | VH GIROLA TT SV 750ML | UN | L | GF | 0,75 | vinho de mesa (Girola tinto suave): cozinha |
| 1202 | VH MESA V TRENTO 750ML | UN | L | GF | 0,75 | vinho de mesa: cozinha |
| 1434 | VH VAILATTI MESA 750ML | UN | L | GF | 0,75 | vinho de mesa: cozinha |
| 1904 | VH V SUL BCO SCO 750ML | UN | UN | UN | 1 | garrafa; chileno (EAN 780), não é vinho de mesa |
| 452 | VINAGRE BALSAMICO 500ML MASTROIANI | — | L | GF | 0,5 | existe ATIVO 1628 (ACETO BALSAMICO TAVOLA 1L) — candidato a fusão |
| 1209 | VINAGRE CASTELO 750ML AR | UN | L | GF | 0,75 | de arroz; existe ATIVO 1814 (VINAGRE HEINIG ARROZ), que está em UN |
| 1830 | VINAGRE CASTELO 750ML VH | UN | L | GF | 0,75 | de vinho |
| 1690 | VINAGRE GALO 750ML VH TT | UN | L | GF | 0,75 | de vinho tinto |
| 1456 | VINAGRE HEINIG 750ML MAC | UN | L | GF | 0,75 | de maçã |
| 998 | VINAGRE HEINIG 900ML ALC | UN | L | GF | 0,9 | de álcool |
| 1208 | VINAGRE KARUI 750ML ARR | UN | L | GF | 0,75 | de arroz |
| 325 | VINAGRE MACA GF 750ML FRITZ E FRIDA | UN | L | GF | 0,75 | de maçã; provável duplicado do 1456 |
| 1291 | VINAGRE VINHO BRANCO PET 750ML HEINIG | — | L | GF | 0,75 | |
| 1394 | VINAGRE VINHO TINTO PET 750ML HEINIG | — | L | GF | 0,75 | provável duplicado do 1690 |
| 1982 | VINHO BRANCO ANIMA THERA CHARDONNAY 2025 | UN | UN | UN | 1 | já está certo; vinho de carta |
| 84 | VINHO BRANCO SECO 6X1,5L GARIBALDI | GF | L | GF | 1,5 | vinho de mesa em garrafa de 1,5 L: cozinha; segunda embalagem: CX = 9 (6 garrafas) |
| 186 | VINHO BRANCO SECO MOSCATO 750ML ALLEANZA | UN | L | GF | 0,75 | vinho de cozinha (confirmado em 07/10/2026) |
| 477 | VINHO BRANCO SECO PET 4L VAILATTI | UN | L | GL | 4 | vinho de mesa em PET de 4 L: cozinha |
| 1129 | VINHO BRANCO SECO VD 750ML SINUELO | — | L | GF | 0,75 | vinho de mesa (Sinuelo): cozinha |
| 435 | VINHO BRANCO THERA SAUVIGNON BLANC 2022 | UN | UN | UN | 1 | já está certo; vinho de carta |
| 1535 | VINHO CAMPO LARGO BCO SECO 750ML | UN | L | GF | 0,75 | vinho de mesa (Campo Largo): cozinha |
| 758 | VINHO DE MESA TINTO DEMI SECO 750ML SINU | UN | L | GF | 0,75 | vinho de mesa: cozinha |
| 1578 | VINHO LORENA LARANJA SECO TLTP 750ML | — | UN | UN | 1 | vinho de carta |
| 1192 | VINHO ROSE AUDREY 1,5 L JOVEM - UN | UN | UN | UN | 1 | já está certo; vinho de carta |
| 1156 | VINHO ROSE LA JOVEM - CX | CX | UN | CX | conferir | vinho de carta; garrafas por caixa (provável 6) |
| 815 | VINHO ROSE TERROIR XXVII- CX | CX | UN | CX | conferir | vinho de carta; garrafas por caixa (provável 6) |
| 769 | VINHO TINTO SECO CABERNET SAUVIG 750ML | UN | UN | UN | 1 | garrafa; cabernet sauvignon, não é de cozinha (confirmado em 07/10/2026) |
| 780 | VINHO TINTO THERA MADAI 2022 | UN | UN | UN | 1 | já está certo; vinho de carta |
| 1959 | VINHO TTO SUAVE MESA 750ML SINUELO | UN | L | GF | 0,75 | vinho de mesa: cozinha |
| 3694 | VITRINE REFRIGERADA RETA MILANO VSRRM-MA-1,21 | UN | — | — | — | é equipamento (imobilizado), não insumo: não deveria estar no estoque |
| 176 | VODKA ABSOLUT 1000 ML - REGULAR (12/60) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 173 | VODKA ABSOLUT (FLAVORS) CITRON 750 ML (12/65) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 773 | VODKA (BAG-IN-BOX) VIBE 5000 ML (KALVELAGE) (2/176) | UN | UN | UN | 1 | a unidade é o bag de 5 L; se a nota vier em caixa: CX = 2 |
| 175 | VODKA GREY GOOSE 750 ML (6/112) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 6 |
| 775 | VODKA SKYY 750 ML (12) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 1419 | VODKA SKYY 980 ML (12) | UN | UN | UN | 1 | garrafa de 980 ml; em UN não se funde com a de 750 ml (775); se a nota vier em caixa: CX = 12 |
| 174 | VODKA SMIRNOFF 998 ML (12) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 12 |
| 1173 | WEISSKAESE FRACIONADO | KG | KG | KG | 1 | já está certo |
| 1327 | WERMUTE DRY 700 ML | — | UN | UN | 1 | garrafa |
| 1961 | WHEY PROT ITALAC 250ML | UN | UN | UN | 1 | já está certo; bebida de revenda |
| 1607 | WHIP TOPPING BASE RICHS 907G (03517) | UN | KG | UN | 0,907 | |
| 1376 | WHISK WHITE HORSE 1L | UN | UN | UN | 1 | garrafa |
| 1649 | WHISKY WILD TURKEY 101 700 ML (BOURBON) (6) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 6 |
| 676 | WHISKY WILD TURKEY 700ML | UN | UN | UN | 1 | garrafa; conferir se é o 101 (duplicado do 1649) ou o comum |
| 165 | X ALFACE AMERICANA CORACAO BLUMENAU 180G | — | UN | UN | 1 | pacote higienizado; o ATIVO 1205 (ALFACE AMERICANA) está em G |
| 988 | XAROPE CRANBERRY 700ML TEISSEIRE | — | UN | UN | 1 | garrafa |
| 170 | XAROPE MONIN CRANBERRY 700 ML (6) | UN | UN | UN | 1 | garrafa; se a nota vier em caixa: CX = 6 |
| 474 | ZERO CAL STEVIA LIQ | — | UN | UN | 1 | frasco de adoçante; como o ATIVO 627 (ADOCANTE 200ML), em UN |
