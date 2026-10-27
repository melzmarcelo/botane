"""Ler uma planilha do Excel (.xlsx) sem biblioteca: o arquivo é um ZIP com XML dentro.

🔑 **Por que não `openpyxl`**: seria uma dependência a mais no servidor (presa, auditada
e atualizada — ver `requirements.txt`) para ler texto de células. O formato é aberto e a
biblioteca padrão lê ZIP e XML; o que se perde é fórmula e formatação, que a importação
não usa. A célula de fórmula traz o último VALOR calculado, que é o que interessa.

⚠️ **Data vem como NÚMERO** (dias desde 30/12/1899) quando a célula é de data — quem lê a
coluna converte com `data_do_excel`. Texto "15/03/2022" também é aceito lá.
⚠️ **Arquivo hostil**: ZIP que descompacta para gigabytes e XML com DTD (a "bomba de
entidades") são recusados antes de ler.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta
from xml.etree import ElementTree as ET

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
# O que a planilha pode ocupar DESCOMPACTADA. A da casa tem 40 KB; 60 MB é folga larga
# e ainda barra o ZIP que vira gigabytes.
MAXIMO_DESCOMPACTADO = 60 * 1024 * 1024


class XlsxInvalido(ValueError):
    """Não é um .xlsx que dê para ler — a frase vai para a tela."""


def e_xlsx(conteudo: bytes) -> bool:
    return conteudo[:2] == b"PK"


def _xml(z: zipfile.ZipFile, nome: str) -> ET.Element:
    bruto = z.read(nome)
    # ⚠️ Planilha de verdade não declara DTD; quem declara está tentando a bomba de
    # entidades. Recusa antes de o parser expandir qualquer coisa.
    if b"<!DOCTYPE" in bruto[:2048].upper() or b"<!ENTITY" in bruto.upper():
        raise XlsxInvalido("A planilha tem uma estrutura que não é aceita.")
    return ET.fromstring(bruto)


def _coluna(ref: str) -> int:
    letras = re.match(r"[A-Z]+", ref or "A")
    n = 0
    for c in letras.group() if letras else "A":
        n = n * 26 + ord(c) - 64
    return n - 1


def ler(conteudo: bytes) -> list[tuple[str, list[list[str]]]]:
    """As abas, na ordem do arquivo: `[(nome da aba, [[célula, ...], ...]), ...]`.

    Células como TEXTO, sem espaço sobrando; vazia é "". As linhas mantêm a posição das
    colunas (a célula vazia no meio continua ocupando o lugar dela).
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as e:
        raise XlsxInvalido("O arquivo não é uma planilha do Excel (.xlsx) válida.") from e
    if sum(i.file_size for i in z.infolist()) > MAXIMO_DESCOMPACTADO:
        raise XlsxInvalido("A planilha é grande demais para importar.")
    nomes = set(z.namelist())
    if "xl/workbook.xml" not in nomes:
        raise XlsxInvalido("O arquivo não é uma planilha do Excel (.xlsx) válida.")

    compartilhados: list[str] = []
    if "xl/sharedStrings.xml" in nomes:
        for si in _xml(z, "xl/sharedStrings.xml").findall(f"{_NS}si"):
            compartilhados.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))

    alvos = {r.get("Id"): r.get("Target")
             for r in _xml(z, "xl/_rels/workbook.xml.rels")}
    abas: list[tuple[str, list[list[str]]]] = []
    folhas = _xml(z, "xl/workbook.xml").find(f"{_NS}sheets")
    for folha in (folhas if folhas is not None else []):
        alvo = alvos.get(folha.get(f"{_REL}id")) or ""
        caminho = alvo.lstrip("/") if alvo.startswith("/") else f"xl/{alvo}"
        if caminho not in nomes:
            continue
        linhas: list[list[str]] = []
        for row in _xml(z, caminho).iter(f"{_NS}row"):
            celulas: dict[int, str] = {}
            for c in row.findall(f"{_NS}c"):
                tipo, v = c.get("t"), c.find(f"{_NS}v")
                if tipo == "s" and v is not None and v.text is not None:
                    i = int(v.text)
                    texto = compartilhados[i] if i < len(compartilhados) else ""
                elif tipo == "inlineStr":
                    texto = "".join(t.text or "" for t in c.iter(f"{_NS}t"))
                else:
                    texto = v.text if v is not None and v.text is not None else ""
                celulas[_coluna(c.get("r") or "")] = texto.strip()
            if celulas:
                linhas.append([celulas.get(i, "") for i in range(max(celulas) + 1)])
            else:
                linhas.append([])
        abas.append((folha.get("name") or "", linhas))
    return abas


def data_do_excel(texto: str | None) -> date | None:
    """"45123" (número de série do Excel), "15/03/2022", "15/03/22" ou "2022-03-15".

    ⚠️ Levanta `ValueError` com a frase para a tela quando não é data — célula de data
    com texto qualquer não vira "sem data" calada.
    """
    t = (texto or "").strip()
    if not t:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", t):
        n = float(t)
        # O Excel conta de 30/12/1899 (o bug do 29/02/1900 já está dentro desse início).
        if 1 <= n < 2958466:
            return date(1899, 12, 30) + timedelta(days=int(n))
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", t)
    if m:
        d, mes, a = int(m[1]), int(m[2]), int(m[3])
        return date(a + 2000 if a < 100 else a, mes, d)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})( .*)?", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    raise ValueError(f"“{t}” não é uma data (use 15/03/2022)")
