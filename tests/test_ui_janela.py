"""Testes de fumaça da janela principal.

A seção 15 do CENTRAL.md limita a cobertura de interface a isto: a janela
abre, lista o que o núcleo descobriu, e abrir um produto não lança exceção.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from central.nucleo import descobrir
from central.ui import tema
from central.ui.janela import ABA_BIBLIOTECA, ABA_EDITOR, JanelaPrincipal

pytestmark = pytest.mark.ui


@pytest.fixture
def janela(qtbot):
    aplicacao = QApplication.instance()
    assert aplicacao is not None
    tema.aplicar(aplicacao, tema.Esquema.ESCURO)
    widget = JanelaPrincipal(descobrir())
    qtbot.addWidget(widget)
    yield widget
    # A janela segura uma thread de geração e um contexto de OpenGL; soltá-los
    # explicitamente evita que o acúmulo entre testes derrube o processo.
    widget.editor.encerrar()


def test_janela_abre_sem_excecao(janela) -> None:
    assert janela.isEnabled()


def test_titulo_traz_o_nome_e_a_versao(janela) -> None:
    from central import __version__

    assert janela.windowTitle() == f"Central {__version__}"


def test_ha_exatamente_as_abas_da_v1(janela) -> None:
    assert janela.nomes_das_abas() == ["Biblioteca", "Editor"]


def test_lote_e_catalogo_nao_existem_nem_vazios(janela) -> None:
    nomes = janela.nomes_das_abas()
    assert "Lote" not in nomes
    assert "Catálogo" not in nomes


def test_comeca_na_biblioteca(janela) -> None:
    assert janela.aba_atual() == ABA_BIBLIOTECA


def test_troca_de_aba(janela) -> None:
    janela.ir_para(ABA_EDITOR)
    assert janela.aba_atual() == ABA_EDITOR


def test_a_aba_biblioteca_e_a_grade_de_cards(janela) -> None:
    from central.ui.biblioteca import Biblioteca

    assert isinstance(janela.biblioteca, Biblioteca)
    assert janela.biblioteca.quantidade_de_cards() >= 1


def test_escolher_produto_leva_ao_editor(janela) -> None:
    assert janela.aba_atual() == ABA_BIBLIOTECA
    janela.biblioteca.produto_escolhido.emit("placa_nome")
    assert janela.aba_atual() == ABA_EDITOR


def test_barra_de_status_conta_os_produtos(janela) -> None:
    mensagem = janela.statusBar().currentMessage()
    assert str(len(janela.registro)) in mensagem
    assert "catálogo" in mensagem


def test_janela_usa_o_registro_recebido(janela) -> None:
    assert janela.registro is not None
    assert "placa_nome" in janela.registro


def test_mostrar_a_janela_nao_lanca(janela, qtbot) -> None:
    janela.show()
    qtbot.waitExposed(janela)
    assert janela.isVisible()


# --- tema ---------------------------------------------------------------


def test_tema_escuro_e_o_padrao_sem_aplicacao() -> None:
    assert tema.PALETAS[tema.Esquema.ESCURO] is tema.ESCURA


def test_aplicar_devolve_o_esquema_pedido(qapp) -> None:
    assert tema.aplicar(qapp, tema.Esquema.CLARO) is tema.Esquema.CLARO
    assert tema.esquema_atual() is tema.Esquema.CLARO
    assert tema.paleta_atual() is tema.CLARA

    assert tema.aplicar(qapp, tema.Esquema.ESCURO) is tema.Esquema.ESCURO
    assert tema.paleta_atual() is tema.ESCURA


def test_aplicar_troca_a_paleta_da_aplicacao(qapp) -> None:
    from PySide6.QtGui import QPalette

    tema.aplicar(qapp, tema.Esquema.ESCURO)
    cor = qapp.palette().color(QPalette.ColorRole.Window).name().upper()
    assert cor == tema.ESCURA.fundo.upper()


def test_folha_de_estilo_e_aplicada(qapp) -> None:
    tema.aplicar(qapp, tema.Esquema.ESCURO)
    assert "QTabBar::tab:selected" in qapp.styleSheet()


@pytest.mark.parametrize("esquema", list(tema.Esquema))
def test_toda_paleta_tem_as_cores_declaradas(esquema: tema.Esquema) -> None:
    paleta = tema.PALETAS[esquema]
    for campo in paleta.__slots__:
        valor = getattr(paleta, campo)
        assert valor.startswith("#") and len(valor) == 7, f"{campo} = {valor}"
