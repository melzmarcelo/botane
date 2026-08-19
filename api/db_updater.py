"""Aplica os .sql de db_scripts em ordem, uma vez cada, por checksum.

Mesmo mecanismo dos outros sistemas da casa: script alterado reroda — por isso
**todo script precisa ser idempotente** — e o retry em passes resolve dependência
entre scripts sem exigir ordenação manual perfeita.
"""

import hashlib
import os

from config import SCRIPTS_DIR
from database import get_cursor


def run_migrations() -> None:
    with get_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                script_name VARCHAR(255) PRIMARY KEY,
                checksum    VARCHAR(64),
                applied_at  TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )

    if not os.path.isdir(SCRIPTS_DIR):
        print(f"[db_updater] pasta de scripts nao encontrada: {SCRIPTS_DIR}")
        return

    arquivos = sorted(f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".sql"))

    pendentes: list[tuple[str, str, str]] = []
    for nome in arquivos:
        with open(os.path.join(SCRIPTS_DIR, nome), "r", encoding="utf-8") as f:
            sql = f.read()
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        with get_cursor() as cur:
            cur.execute(
                "SELECT checksum FROM schema_migrations WHERE script_name = %s", (nome,)
            )
            row = cur.fetchone()
        if not (row and row["checksum"] == checksum):
            pendentes.append((nome, sql, checksum))

    if not pendentes:
        print(f"[db_updater] {len(arquivos)} script(s), nada pendente")
        return

    while pendentes:
        falharam: list[tuple[str, str, str]] = []
        erros: dict[str, str] = {}
        avancou = False

        for nome, sql, checksum in pendentes:
            try:
                with get_cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        """
                        INSERT INTO schema_migrations (script_name, checksum)
                        VALUES (%s, %s)
                        ON CONFLICT (script_name)
                        DO UPDATE SET checksum = EXCLUDED.checksum, applied_at = NOW()
                        """,
                        (nome, checksum),
                    )
                print(f"[db_updater] aplicado: {nome}")
                avancou = True
            except Exception as e:  # noqa: BLE001
                falharam.append((nome, sql, checksum))
                erros[nome] = str(e).strip().splitlines()[0]

        if not avancou:
            for nome, msg in erros.items():
                print(f"[db_updater] ERRO em {nome}: {msg}")
            raise RuntimeError(
                f"migracoes travadas: {', '.join(erros)} — nenhum script avancou neste passe"
            )
        pendentes = falharam
