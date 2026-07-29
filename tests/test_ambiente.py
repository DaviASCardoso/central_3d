"""Verifica que o ambiente instalado corresponde ao declarado no pyproject."""

from __future__ import annotations

import importlib.metadata as metadados
import re
import sys
import tomllib
from pathlib import Path

import pytest

import central

FIXACAO = re.compile(r"^(?P<nome>[A-Za-z0-9._-]+)==(?P<versao>[0-9][0-9A-Za-z.+-]*)$")


def _dependencias_fixadas(raiz: Path) -> dict[str, str]:
    """Lê do pyproject.toml as dependências fixadas com `==`."""
    conteudo = (raiz / "pyproject.toml").read_text(encoding="utf-8")
    dados = tomllib.loads(conteudo)
    fixadas: dict[str, str] = {}
    for requisito in dados["project"]["dependencies"]:
        casamento = FIXACAO.match(requisito.strip())
        if casamento is not None:
            fixadas[casamento["nome"]] = casamento["versao"]
    return fixadas


def test_versao_do_pacote() -> None:
    assert central.__version__ == "0.1.0"


def test_python_e_3_12() -> None:
    assert sys.version_info[:2] == (3, 12)


def test_ha_dependencias_fixadas(raiz_do_projeto: Path) -> None:
    fixadas = _dependencias_fixadas(raiz_do_projeto)
    assert set(fixadas) == {
        "build123d",
        "cadquery-ocp-novtk",
        "lib3mf",
        "numpy",
        "PySide6",
        "trimesh",
        "vtk",
        "watchdog",
    }


def test_versoes_instaladas_batem_com_as_fixadas(raiz_do_projeto: Path) -> None:
    fixadas = _dependencias_fixadas(raiz_do_projeto)
    divergentes = {
        nome: (esperada, metadados.version(nome))
        for nome, esperada in fixadas.items()
        if metadados.version(nome) != esperada
    }
    assert not divergentes, f"versões divergentes: {divergentes}"


@pytest.mark.parametrize(
    "modulo",
    ["build123d", "lib3mf", "numpy", "PySide6", "trimesh", "vtkmodules"],
)
def test_dependencias_pesadas_importam(modulo: str) -> None:
    __import__(modulo)


def test_configurar_logging_e_idempotente() -> None:
    import logging

    from central import log

    log.configurar()
    quantidade = len(logging.getLogger().handlers)
    log.configurar()
    assert len(logging.getLogger().handlers) == quantidade
