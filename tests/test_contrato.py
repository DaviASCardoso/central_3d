"""Testes do contrato.

O mais importante deles é o de isolamento: o contrato é a camada da base e não
pode arrastar Qt, VTK nem geometria consigo. Se este teste quebrar, alguém
importou algo pesado em `central.contrato` e um script de linha de comando
passou a pagar segundos de import por nada.
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys

import pytest

from central.contrato import Corpo, Param, Produto, Resultado, TipoParam

PROGRAMA_ISOLAMENTO = """
import sys
import central.contrato  # noqa: F401
pesados = [m for m in ("PySide6", "vtkmodules", "vtk", "build123d", "OCP", "trimesh")
           if m in sys.modules]
print(",".join(pesados))
"""


def test_contrato_nao_importa_dependencias_pesadas() -> None:
    saida = subprocess.run(
        [sys.executable, "-c", PROGRAMA_ISOLAMENTO],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert saida.stdout.strip() == "", f"contrato arrastou: {saida.stdout.strip()}"


def test_tipos_de_param_sao_os_seis_declarados() -> None:
    assert {t.value for t in TipoParam} == {
        "texto",
        "inteiro",
        "decimal",
        "booleano",
        "escolha",
        "cor",
    }


def test_tipo_param_e_string() -> None:
    assert TipoParam.TEXTO == "texto"


def _param_minimo() -> Param:
    return Param(chave="nome", rotulo="Nome", tipo=TipoParam.TEXTO, padrao="Ana")


def test_param_e_imutavel() -> None:
    param = _param_minimo()
    with pytest.raises(dataclasses.FrozenInstanceError):
        param.padrao = "outro"


def test_param_tem_defaults_do_contrato() -> None:
    param = _param_minimo()
    assert param.grupo == "Geral"
    assert param.ordem == 0
    assert param.avancado is False
    assert param.afeta_geometria is True
    assert param.visivel_se is None


def test_param_usa_slots() -> None:
    param = _param_minimo()
    with pytest.raises(AttributeError):
        param.__dict__  # noqa: B018


def _produto_minimo() -> Produto:
    return Produto(
        id="teste",
        nome="Teste",
        versao="1.0.0",
        descricao="Produto de teste.",
        categoria="Teste",
        params=(_param_minimo(),),
        gerar=lambda valores: valores,
    )


def test_produto_e_imutavel() -> None:
    produto = _produto_minimo()
    with pytest.raises(dataclasses.FrozenInstanceError):
        produto.versao = "2.0.0"


def test_produto_tem_defaults_do_contrato() -> None:
    produto = _produto_minimo()
    assert produto.tags == ()
    assert produto.validar is None
    assert produto.orientacao is None
    assert produto.altura_camada_sugerida is None
    assert produto.requer_suporte is False
    assert produto.tempo_estimado_min is None


def test_corpo_tem_cor_padrao_e_e_mutavel() -> None:
    corpo = Corpo(nome="base", forma=object())
    assert corpo.cor == "#8AB4F8"
    assert corpo.filamento is None
    corpo.cor = "#FFFFFF"
    assert corpo.cor == "#FFFFFF"


def test_resultado_nao_compartilha_defaults_mutaveis() -> None:
    primeiro = Resultado(corpos=[])
    segundo = Resultado(corpos=[])
    primeiro.avisos.append("aviso")
    primeiro.metadados["chave"] = "valor"
    assert segundo.avisos == []
    assert segundo.metadados == {}
