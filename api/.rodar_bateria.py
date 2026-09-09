import glob, os, subprocess, sys, time
suites = sorted(glob.glob("tests/smoke_*.py"))
inicio = time.time()
total_ok = total_falha = 0
quebrados = []
for s in suites:
    r = subprocess.run([sys.executable, s], capture_output=True, text=True,
                       errors="replace", cwd=".")
    ultima = [l for l in (r.stdout or "").splitlines() if "passaram," in l]
    linha = ultima[-1] if ultima else "(sem resumo)"
    marca = "OK " if r.returncode == 0 else "FALHOU"
    print(f"{marca} {os.path.basename(s):38} {linha}")
    if ultima:
        n = ultima[-1].split()
        total_ok += int(n[0]); total_falha += int(n[2])
    if r.returncode != 0:
        quebrados.append(s)
        for l in (r.stdout or "").splitlines():
            if "FALHA" in l:
                print("      ", l.strip())
        if not ultima:
            print("      ", (r.stderr or "")[-600:])
print(f"\n{len(suites)-len(quebrados)}/{len(suites)} suites, "
      f"{total_ok} checagens ok, {total_falha} falharam, "
      f"{time.time()-inicio:.0f}s")
raise SystemExit(1 if quebrados else 0)
