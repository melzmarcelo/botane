"""O que as suítes de fumaça precisam ter antes de testar o que testam.

Base recém-instalada — ou recém-limpa pelo `limpar_dados.py` — não tem local de
estoque nem setor. Sem local, nenhum movimento entra; sem setor, o relatório por
grupo não tem grupo. Supor que existem fazia a suíte quebrar num ponto que não
tem nada a ver com o que ela prova, e escondia o resultado de tudo o mais.

Cada suíte **garante** o que precisa, do mesmo jeito que já cria os próprios
produtos. Rodar contra uma instalação virgem passou a ser parte do contrato.
"""

import sys

# Redirecionar a saída para arquivo troca o console (cp1252 aqui) por uma
# codificação que não tem o sinal de menos tipográfico e outros. A suíte morria
# ao IMPRIMIR o resultado, depois de já ter testado tudo — e o relatório se
# perdia inteiro por causa de um caractere de rótulo.
for _saida in (sys.stdout, sys.stderr):
    try:
        _saida.reconfigure(errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - saída redirecionada
        pass


def garantir_local(chamar, token) -> dict:
    """O local principal, criando um se não houver nenhum.

    Devolve o registro completo (e não o `{id, message}` do POST): quem chama
    costuma precisar de `principal` e `nome` também.
    """
    st, locais = chamar("GET", "/locais", token=token)
    if locais:
        return next((l for l in locais if l["principal"]), locais[0])
    # Sem `principal`: é o servidor que elege o primeiro local da loja, e é esse
    # caminho — o de quem não marca a caixinha — que precisa ser exercitado.
    chamar("POST", "/locais", {"nome": "Estoque seco", "tipo": "SECO"}, token=token)
    st, locais = chamar("GET", "/locais", token=token)
    return next((l for l in locais if l["principal"]), locais[0])


def garantir_locais(chamar, token, quantos: int = 2) -> list[dict]:
    """Pelo menos `quantos` locais — para transferência, que precisa de dois.

    Não manda `principal`: **de propósito**. O helper marcava a caixinha no
    primeiro local, coisa que quem cadastra "Balcão" não faz, e por isso
    nenhuma suíte passava pelo caminho de quem não marca. Quem elege o
    principal é o servidor, no primeiro local da loja.
    """
    st, locais = chamar("GET", "/locais", token=token)
    faltam = quantos - len(locais or [])
    for i in range(faltam):
        chamar("POST", "/locais",
               {"nome": f"Local {len(locais or []) + i + 1}", "tipo": "SECO"},
               token=token)
    st, locais = chamar("GET", "/locais", token=token)
    return locais


def garantir_setores(chamar, token, quantos: int = 2) -> list[dict]:
    """Pelo menos `quantos` setores — o CMV por grupo precisa de mais de um
    para provar que cada grupo fica com o seu."""
    st, setores = chamar("GET", "/setores", token=token)
    existentes = {(s["nome"] or "").lower() for s in (setores or [])}
    # Pula o nome que já está lá: repetir é 409 agora (antes era 500), e o
    # helper ficaria sem criar nada achando que criou.
    padrao = [n for n in ("Cozinha", "Bar", "Confeitaria", "Salão")
              if n.lower() not in existentes]
    for i in range(max(0, quantos - len(setores or []))):
        if i < len(padrao):
            chamar("POST", "/setores", {"nome": padrao[i], "ordem": i}, token=token)
    st, setores = chamar("GET", "/setores", token=token)
    return setores


def garantir_categorias(chamar, token, quantos: int = 2) -> list[dict]:
    """Pelo menos `quantos` categorias — a base nova não traz nenhuma."""
    st, categorias = chamar("GET", "/categorias", token=token)
    existentes = {(c["nome"] or "").lower() for c in (categorias or [])}
    padrao = [n for n in ("Mercearia", "Laticínios", "Hortifrúti", "Bebidas", "Descartáveis",
                          "Carnes", "Padaria", "Limpeza")
              if n.lower() not in existentes]
    for i in range(max(0, quantos - len(categorias or []))):
        if i < len(padrao):
            chamar("POST", "/categorias", {"nome": padrao[i], "tipo": "INSUMO"}, token=token)
    st, categorias = chamar("GET", "/categorias", token=token)
    return categorias


def garantir_fornecedor(chamar, token, nome: str, cnpj: str) -> int:
    """O fornecedor do cenário, reaproveitando o que já existir com aquele CNPJ.

    A busca é pelo **CNPJ**, não pelo nome: o CNPJ é a chave única no banco, e
    procurar por nome já falhou quando o importador simulado do Omie criou um
    fornecedor com o mesmo documento e outro nome — a suíte não achava, tentava
    criar e levava 409.
    """
    digitos = "".join(c for c in cnpj if c.isdigit())
    st, achados = chamar("GET", f"/fornecedores?incluir_inativos=true&busca={digitos}",
                         token=token)
    existente = next(
        (f for f in (achados or [])
         if "".join(c for c in (f.get("cnpj") or "") if c.isdigit()) == digitos),
        None,
    )
    if existente:
        chamar("PUT", f"/fornecedores/{existente['id']}", {"ativo": True}, token=token)
        return existente["id"]

    st, r = chamar("POST", "/fornecedores", {"nome": nome, "cnpj": cnpj}, token=token)
    if r.get("id"):
        return r["id"]
    # 409: alguém criou entre a busca e o POST, ou o CNPJ está com outro nome.
    st, achados = chamar("GET", f"/fornecedores?incluir_inativos=true&busca={digitos}",
                         token=token)
    return (achados or [{}])[0].get("id")


def garantir_cozinha(chamar, token, email: str = "smoke.cozinha@botane.com.br",
                     senha: str = "smoke12345") -> str | None:
    """O usuário de Cozinha das suítes, criado se não existir. Devolve o token dele.

    Várias suítes só REATIVAVAM o usuário quando ele já estava lá. Numa base
    recém-instalada ele não está, o login falhava com 401 e as checagens de
    permissão passavam a comparar 401 com 403 — testando outra coisa.
    """
    st, papeis = chamar("GET", "/papeis", token=token)
    id_cozinha = next((p["id"] for p in (papeis or []) if p["nome"] == "Cozinha"), None)
    if not id_cozinha:
        return None

    st, usuarios = chamar("GET", "/usuarios?incluir_inativos=true", token=token)
    existente = next((u for u in (usuarios or []) if u["email"] == email), None)
    if existente:
        chamar("PUT", f"/usuarios/{existente['id']}",
               {"ativo": True, "senha": senha, "papeis": [{"id_papel": id_cozinha}]}, token=token)
    else:
        chamar("POST", "/usuarios",
               {"nome": "Smoke Cozinha", "email": email, "senha": senha,
                "papeis": [{"id_papel": id_cozinha}]}, token=token)

    st, r = chamar("POST", "/auth/login", {"email": email, "senha": senha})
    return r.get("access_token")
