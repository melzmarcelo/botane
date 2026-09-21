"""Troca `overflow-x-auto` por `grid-rolante` SO onde ele envolve uma tabela.

⚠️ Nem todo `overflow-x-auto` e grid: a cascata do CMV e um SVG, e dar altura
maxima a ela cortaria o desenho. O criterio e o conteudo, nao a classe.
"""
import pathlib
import re

raiz = pathlib.Path("web")
alvos = sorted(list((raiz / "app").rglob("*.tsx")) + list((raiz / "components").rglob("*.tsx")))

trocados, pulados = [], []

for arq in alvos:
    s = arq.read_text(encoding="utf-8")
    if "overflow-x-auto" not in s:
        continue
    linhas = s.split("\n")
    mudou = False
    for i, linha in enumerate(linhas):
        if "overflow-x-auto" not in linha:
            continue
        # Olha as proximas linhas: ha uma <table> logo abaixo, antes de fechar?
        janela = "\n".join(linhas[i:i + 6])
        if "<table" in janela:
            linhas[i] = linha.replace("overflow-x-auto", "grid-rolante")
            mudou = True
            trocados.append(f"{arq.relative_to(raiz)}:{i + 1}")
        else:
            pulados.append(f"{arq.relative_to(raiz)}:{i + 1}  {linha.strip()[:70]}")
    if mudou:
        arq.write_text("\n".join(linhas), encoding="utf-8")

print(f"trocados: {len(trocados)}")
print(f"pulados (nao envolvem tabela): {len(pulados)}")
for x in pulados:
    print("   ", x)
