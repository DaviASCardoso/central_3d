"""Testes da descoberta de produtos."""

from __future__ import annotations

from pathlib import Path

import pytest

from central.nucleo import descobrir
from central.nucleo.erros import ErroDeDescoberta

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def registro_de_teste():
    return descobrir(FIXTURES / "produtos_teste")


def test_produtos_validos_sao_descobertos(registro_de_teste) -> None:
    assert set(registro_de_teste.produtos) == {"cubo_simples", "placa_com_submodulo"}
    assert len(registro_de_teste) == 2


def test_produto_quebrado_vira_falha_com_traceback(registro_de_teste) -> None:
    falha = registro_de_teste.falhas["quebrado_no_import"]
    assert "RuntimeError" in falha.mensagem
    assert "falha proposital" in falha.mensagem
    assert "Traceback" in falha.traceback_completo
    assert "quebrado_no_import" in falha.traceback_completo
    assert falha.caminho.name == "quebrado_no_import"


def test_produto_sem_manifesto_vira_falha_nomeada(registro_de_teste) -> None:
    falha = registro_de_teste.falhas["sem_manifesto"]
    assert "MANIFESTO" in falha.mensagem
    assert falha.id == "sem_manifesto"


def test_manifesto_do_tipo_errado_vira_falha(registro_de_teste) -> None:
    falha = registro_de_teste.falhas["manifesto_do_tipo_errado"]
    assert "deveria ser Produto" in falha.mensagem


def test_pacote_com_sublinhado_e_ignorado_sem_importar(registro_de_teste) -> None:
    assert "_ignorado" not in registro_de_teste.falhas
    assert "_ignorado" not in registro_de_teste.produtos


def test_uma_falha_nao_impede_os_produtos_validos(registro_de_teste) -> None:
    assert len(registro_de_teste.produtos) == 2
    assert len(registro_de_teste.falhas) == 3


def test_import_relativo_dentro_do_produto_funciona(registro_de_teste) -> None:
    produto = registro_de_teste.obter("placa_com_submodulo")
    assert produto.gerar({"nome": "Ana"}) == {"nome": "Ana", "origem": "submodulo"}


def test_manifesto_preserva_os_campos_declarados(registro_de_teste) -> None:
    produto = registro_de_teste.obter("placa_com_submodulo")
    assert produto.nome == "Placa com Submódulo"
    assert produto.versao == "2.1.0"
    assert produto.categoria == "Papelaria"
    assert produto.tags == ("placa",)


def test_obter_id_inexistente_levanta(registro_de_teste) -> None:
    with pytest.raises(KeyError):
        registro_de_teste.obter("nao_existe")


def test_contains_e_categorias(registro_de_teste) -> None:
    assert "cubo_simples" in registro_de_teste
    assert "nao_existe" not in registro_de_teste
    assert registro_de_teste.categorias() == ["Papelaria", "Teste"]


def test_ordenados_agrupa_por_categoria_depois_nome(registro_de_teste) -> None:
    assert [p.id for p in registro_de_teste.ordenados()] == [
        "placa_com_submodulo",
        "cubo_simples",
    ]


def test_id_duplicado_registra_o_primeiro_e_recusa_o_segundo() -> None:
    registro = descobrir(FIXTURES / "produtos_duplicados")
    assert registro.obter("colidido").nome == "Primeiro"
    assert "já usado" in registro.falhas["segundo"].mensagem


def test_diretorio_inexistente_levanta_erro_de_descoberta(tmp_path: Path) -> None:
    with pytest.raises(ErroDeDescoberta, match="inexistente"):
        descobrir(tmp_path / "nao_existe")


def test_diretorio_sem_init_levanta_erro_de_descoberta(tmp_path: Path) -> None:
    (tmp_path / "solto").mkdir()
    with pytest.raises(ErroDeDescoberta, match="__init__"):
        descobrir(tmp_path / "solto")


def test_diretorio_padrao_do_repositorio_e_varrido() -> None:
    registro = descobrir()
    assert registro.diretorio.name == "produtos"
    assert registro.falhas == {}
