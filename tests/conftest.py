"""Fixtures compartilhadas pela suíte de testes."""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def raiz_do_projeto() -> Path:
    """Diretório raiz do repositório, resolvido a partir deste arquivo."""
    return RAIZ
