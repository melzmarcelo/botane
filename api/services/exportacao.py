"""Exportação em CSV que o Excel brasileiro abre com dois cliques.

Três detalhes decidem se o arquivo abre certo ou vira uma coluna só de lixo:

1. **Separador `;`** — é o que o Excel em pt-BR espera; a vírgula ele usa como
   decimal.
2. **BOM no começo** — sem ele o Excel lê UTF-8 como Latin-1 e o "ç" vira "Ã§".
3. **Número com vírgula decimal** e sem separador de milhar, senão o Excel
   trata como texto e nenhuma soma funciona.
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal

BOM = "﻿"


def _valor(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, (Decimal, float, int)) and not isinstance(v, bool):
        # Vírgula decimal, sem milhar: é o que o Excel pt-BR soma.
        return f"{v}".replace(".", ",")
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y %H:%M")
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y")
    return str(v)


def csv_de(linhas: list[dict], colunas: list[tuple[str, str]],
           titulo: str | None = None, resumo: list[tuple[str, object]] | None = None) -> str:
    """`colunas` = [(chave_no_dict, "Cabeçalho na planilha"), ...]."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n",
                          quoting=csv.QUOTE_MINIMAL)

    if titulo:
        escritor.writerow([titulo])
        escritor.writerow([f"Botané Deli e Café — gerado em "
                           f"{datetime.now().strftime('%d/%m/%Y %H:%M')}"])
        escritor.writerow([])
    if resumo:
        for rotulo, valor in resumo:
            escritor.writerow([rotulo, _valor(valor)])
        escritor.writerow([])

    escritor.writerow([cab for _chave, cab in colunas])
    for linha in linhas:
        escritor.writerow([_valor(linha.get(chave)) for chave, _cab in colunas])

    return BOM + saida.getvalue()


def nome_arquivo(base: str, inicio: date | None = None, fim: date | None = None) -> str:
    pedaco = ""
    if inicio and fim:
        pedaco = f"-{inicio.strftime('%Y%m%d')}-a-{fim.strftime('%Y%m%d')}"
    elif inicio:
        pedaco = f"-{inicio.strftime('%Y%m%d')}"
    return f"botane-{base}{pedaco}-{date.today().strftime('%Y%m%d')}.csv"
