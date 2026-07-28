"""Testes da linha de comando."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from central.cli import (
    CODIGO_ERRO,
    CODIGO_OK,
    CODIGO_VALORES_INVALIDOS,
    principal,
)

PROGRAMA_ISOLAMENTO = """
import sys
import central.cli
central.cli.principal(["listar"])
pesados = [m for m in ("PySide6", "vtkmodules", "vtk") if m in sys.modules]
print("PESADOS:" + ",".join(pesados))
"""


# --- listar --------------------------------------------------------------


def test_listar_mostra_a_placa(capsys) -> None:
    assert principal(["listar"]) == CODIGO_OK
    saida = capsys.readouterr().out
    assert "placa_nome" in saida
    assert "Placa com Nome" in saida
    assert "Papelaria" in saida


def test_listar_detalhado_mostra_os_parametros(capsys) -> None:
    assert principal(["listar", "--detalhado"]) == CODIGO_OK
    saida = capsys.readouterr().out
    assert "--nome" in saida
    assert "--altura-texto" in saida
    assert "mm" in saida


def test_listar_nao_lista_falhas_quando_nao_ha(capsys) -> None:
    principal(["listar"])
    assert "com falha" not in capsys.readouterr().out


# --- gerar ---------------------------------------------------------------


def test_gerar_escreve_o_3mf(tmp_path: Path, capsys) -> None:
    codigo = principal(
        ["gerar", "placa_nome", "--nome", "Helena", "--saida", str(tmp_path)]
    )
    assert codigo == CODIGO_OK
    arquivo = tmp_path / "placa_nome.3mf"
    assert arquivo.is_file()
    assert arquivo.stat().st_size > 0
    assert str(arquivo) in capsys.readouterr().out


def test_gerar_relata_dimensoes_e_triangulos(tmp_path: Path, capsys) -> None:
    principal(["gerar", "placa_nome", "--saida", str(tmp_path)])
    saida = capsys.readouterr().out
    assert "1 corpo(s)" in saida
    assert "triângulos" in saida
    assert "80.0 × 25.0" in saida


def test_gerar_em_stl(tmp_path: Path) -> None:
    codigo = principal(
        ["gerar", "placa_nome", "--saida", str(tmp_path), "--formato", "stl"]
    )
    assert codigo == CODIGO_OK
    assert (tmp_path / "placa_nome.stl").is_file()


def test_nome_do_arquivo_pode_ser_escolhido(tmp_path: Path) -> None:
    principal(
        [
            "gerar",
            "placa_nome",
            "--saida",
            str(tmp_path),
            "--nome-do-arquivo",
            "helena_mesa",
        ]
    )
    assert (tmp_path / "helena_mesa.3mf").is_file()


def test_parametros_do_produto_chegam_a_geometria(tmp_path: Path, capsys) -> None:
    principal(
        [
            "gerar",
            "placa_nome",
            "--largura",
            "120",
            "--profundidade",
            "40",
            "--saida",
            str(tmp_path),
        ]
    )
    assert "120.0 × 40.0" in capsys.readouterr().out


def test_valor_fora_da_faixa_sai_com_codigo_2(tmp_path: Path, capsys) -> None:
    codigo = principal(
        ["gerar", "placa_nome", "--relevo", "99", "--saida", str(tmp_path)]
    )
    assert codigo == CODIGO_VALORES_INVALIDOS
    erro = capsys.readouterr().err
    assert "relevo" in erro
    assert "máximo" in erro


def test_validacao_cruzada_tambem_sai_com_codigo_2(tmp_path: Path, capsys) -> None:
    codigo = principal(
        ["gerar", "placa_nome", "--nome", "   ", "--saida", str(tmp_path)]
    )
    assert codigo == CODIGO_VALORES_INVALIDOS
    assert "não pode ser vazio" in capsys.readouterr().err


def test_produto_inexistente_sai_com_codigo_1(capsys) -> None:
    assert principal(["gerar", "nao_existe"]) == CODIGO_ERRO
    erro = capsys.readouterr().err
    assert "não existe" in erro
    assert "placa_nome" in erro


def test_aviso_do_produto_vai_para_stderr(tmp_path: Path, capsys) -> None:
    principal(
        [
            "gerar",
            "placa_nome",
            "--nome",
            "Bartolomeu Nascimento",
            "--largura",
            "60",
            "--saida",
            str(tmp_path),
        ]
    )
    assert "comprimido" in capsys.readouterr().err


def test_nome_nao_e_sequestrado_por_nome_do_arquivo(tmp_path: Path) -> None:
    """O argparse abrevia opção longa, e `--nome` casaria com `--nome-do-arquivo`.

    Sem `allow_abbrev=False`, o valor do parâmetro do produto ia parar no nome
    do arquivo e o texto gravado na peça voltava ao padrão — tudo em silêncio.
    """
    principal(["gerar", "placa_nome", "--nome", "Helena", "--saida", str(tmp_path)])
    assert (tmp_path / "placa_nome.3mf").is_file()
    assert not (tmp_path / "Helena.3mf").exists()


def test_parametro_desconhecido_e_recusado(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        principal(["gerar", "placa_nome", "--cor-do-cabelo", "ruivo"])


def test_saida_e_criada_quando_nao_existe(tmp_path: Path) -> None:
    destino = tmp_path / "nova" / "pasta"
    assert principal(["gerar", "placa_nome", "--saida", str(destino)]) == CODIGO_OK
    assert (destino / "placa_nome.3mf").is_file()


# --- isolamento e empacotamento -----------------------------------------


def test_cli_nao_importa_qt_nem_vtk() -> None:
    """A linha de comando prova que a camada de valor não depende de interface."""
    saida = subprocess.run(
        [sys.executable, "-c", PROGRAMA_ISOLAMENTO],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    linha = next(
        linha for linha in saida.stdout.splitlines() if linha.startswith("PESADOS:")
    )
    assert linha == "PESADOS:", f"a CLI arrastou: {linha}"


def test_entry_point_esta_instalado(tmp_path: Path) -> None:
    execucao = subprocess.run(
        ["central-cli", "gerar", "placa_nome", "--saida", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert execucao.returncode == CODIGO_OK, execucao.stderr
    assert (tmp_path / "placa_nome.3mf").is_file()
