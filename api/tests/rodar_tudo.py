"""A bateria inteira da API numa passada só, com um resumo no fim.

    python tests/rodar_tudo.py          (da pasta `api`, com a API de pé na 9200)

🔑 **Existe porque a lista das suítes vivia na cabeça de quem rodava.** São 41
arquivos `smoke_*.py`, e chamar um por um é onde se esquece justamente o que a
mudança do dia tocou. Aqui a lista é o `glob`: suíte nova entra sozinha, sem
ninguém precisar lembrar de acrescentá-la em lugar nenhum.

⚠️ **Uma de cada vez, nunca em paralelo.** As suítes escrevem na MESMA base
local — criam produto, lançam nota, mexem no razão — e duas ao mesmo tempo
disputam saldo e código. A falha que isso produz não parece concorrência:
parece um bug de estoque, e já custou meia tarde.

⚠️ **A saída de quem passou é RESUMIDA de propósito.** Quarenta e uma suítes
imprimindo mil e novecentas linhas de "ok" enterram as três que interessam. De
quem falha, sai toda linha de FALHA — e, quando nem resumo houve (a suíte morreu
antes), o fim do `stderr`, que é onde está a exceção.

⚠️ Algumas suítes não imprimem a linha "N passaram": elas não entram na conta de
checagens, mas o código de saída delas conta igual para o veredito.
"""

import glob
import os
import subprocess
import sys
import time

suites = sorted(glob.glob("tests/smoke_*.py"))
if not suites:
    print("Nenhuma suíte encontrada — rode a partir da pasta `api`.")
    raise SystemExit(2)

inicio = time.time()
total_ok = total_falha = 0
quebrados = []

for caminho in suites:
    r = subprocess.run([sys.executable, caminho], capture_output=True, text=True,
                       errors="replace", cwd=".")
    resumo = [ln for ln in (r.stdout or "").splitlines() if "passaram," in ln]
    marca = "OK " if r.returncode == 0 else "FALHOU"
    print(f"{marca} {os.path.basename(caminho):38} {resumo[-1] if resumo else '(sem resumo)'}")
    if resumo:
        n = resumo[-1].split()
        total_ok += int(n[0])
        total_falha += int(n[2])
    if r.returncode != 0:
        quebrados.append(caminho)
        for ln in (r.stdout or "").splitlines():
            if "FALHA" in ln:
                print("      ", ln.strip())
        if not resumo:
            print("      ", (r.stderr or "")[-800:])

print(f"\n{len(suites) - len(quebrados)}/{len(suites)} suítes, {total_ok} checagens ok, "
      f"{total_falha} falharam, {time.time() - inicio:.0f}s")
raise SystemExit(1 if quebrados else 0)
