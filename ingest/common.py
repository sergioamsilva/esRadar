"""Definições partilhadas pelo pipeline de ingestão do esRadar."""

from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = RAIZ / "data"
DIR_BRUTO = DIR_DADOS / "raw"
DIR_SAIDA = DIR_DADOS / "out"
DIR_SNAPSHOTS = DIR_DADOS / "snapshots"
DIR_REFERENCIA = RAIZ / "reference"

BASE_DGES = "https://www.dges.gov.pt"
BASE_GUIAS = f"{BASE_DGES}/guias"
BASE_INFOCURSOS = "https://infocursos.medu.pt"

TEMPO_LIMITE = 60
TENTATIVAS = 4
# Um pedido por segundo. O site da DGES é ASP clássico e serve o país inteiro
# na época das colocações — não há justificação para ir mais depressa.
INTERVALO_PEDIDOS = 1.0

_sessao: requests.Session | None = None
_ultimo_pedido = 0.0


def sessao() -> requests.Session:
    global _sessao
    if _sessao is None:
        _sessao = requests.Session()
        _sessao.headers["User-Agent"] = (
            "esRadar/0.1 (arquivo de dados publicos sobre o acesso ao ensino superior)"
        )
    return _sessao


def descarregar(url: str, destino: Path, *, forcar: bool = False) -> bool:
    """Descarrega `url` para `destino`, com cache em disco e rate-limit.

    Devolve True se descarregou, False se o ficheiro já existia (cache).
    O conteúdo é gravado em bruto, byte a byte — a descodificação (as páginas
    ASP da DGES vêm em windows-1252) é problema de quem lê, nunca de quem
    arquiva.
    """
    global _ultimo_pedido
    if destino.exists() and destino.stat().st_size > 0 and not forcar:
        return False
    destino.parent.mkdir(parents=True, exist_ok=True)
    espera = time.monotonic() - _ultimo_pedido
    if espera < INTERVALO_PEDIDOS:
        time.sleep(INTERVALO_PEDIDOS - espera)
    ultima_falha: Exception | None = None
    for tentativa in range(TENTATIVAS):
        try:
            _ultimo_pedido = time.monotonic()
            resp = sessao().get(url, timeout=TEMPO_LIMITE)
            resp.raise_for_status()
            destino.write_bytes(resp.content)
            return True
        except Exception as exc:  # noqa: BLE001 — retry indiscriminado, falha alto no fim
            ultima_falha = exc
            time.sleep(2**tentativa)
    raise RuntimeError(f"falhou o download de {url}: {ultima_falha}")


def ler_html(caminho: Path) -> str:
    """Lê uma página arquivada da DGES. Sempre windows-1252, nunca resp.text."""
    return caminho.read_bytes().decode("windows-1252", errors="replace")


_LIGACAO = {"de", "da", "do", "das", "dos", "e"}


def normalizar(texto: str) -> str:
    """Reduz um nome (curso ou instituição) à sua forma comparável.

    Usado apenas para *semear* o crosswalk — a correspondência final é sempre
    por chave declarada em reference/, curada à mão.
    """
    if not texto:
        return ""
    t = unicodedata.normalize("NFKD", texto)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    for c in ",.;:/\\-–—()'\"":
        t = t.replace(c, " ")
    return " ".join(t.split())


def normalizar_agressivo(texto: str) -> str:
    """Descarta também palavras de ligação. Só para sugerir, nunca para decidir."""
    return " ".join(p for p in normalizar(texto).split() if p not in _LIGACAO)


def garantir_dirs() -> None:
    for d in (DIR_BRUTO, DIR_SAIDA, DIR_SNAPSHOTS, DIR_REFERENCIA):
        d.mkdir(parents=True, exist_ok=True)
