"""Testes do editor de três painéis com geração síncrona."""

from __future__ import annotations

from typing import Any

import pytest
from build123d import Box

from central.contrato import Corpo, Param, Produto, Resultado, TipoParam
from central.nucleo import descobrir
from central.ui import tema
from central.ui.editor import PAGINA_ERRO, PAGINA_VIEWPORT, Editor

pytestmark = pytest.mark.ui

REGISTRO = descobrir()


@pytest.fixture
def editor(qtbot, qapp):
    tema.aplicar(qapp, tema.Esquema.ESCURO)
    widget = Editor()
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    widget.iniciar()
    yield widget
    widget.encerrar()


@pytest.fixture
def editor_com_placa(editor):
    editor.abrir(REGISTRO.obter("placa_nome"))
    return editor


def produto_de_dois_corpos() -> Produto:
    def gerar(valores: dict[str, Any]) -> Resultado:
        lado = valores["lado"]
        return Resultado(
            corpos=[
                Corpo(nome="base", forma=Box(lado, lado, 5), cor="#8AB4F8"),
                Corpo(nome="tampa", forma=Box(lado, lado, 2), cor="#F28B82"),
            ],
            avisos=["um aviso qualquer"],
        )

    return Produto(
        id="dois",
        nome="Dois Corpos",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(
            Param(
                chave="lado",
                rotulo="Lado",
                tipo=TipoParam.DECIMAL,
                padrao=20.0,
                minimo=5.0,
                maximo=40.0,
            ),
        ),
        gerar=gerar,
    )


# --- estado inicial ------------------------------------------------------


def test_editor_sem_produto_nao_lanca(editor) -> None:
    assert editor.produto is None
    assert editor.inspetor is None
    editor.gerar({})


def test_restaurar_comeca_desabilitado(editor) -> None:
    assert not editor.acao_restaurar.isEnabled()


# --- abertura e geração --------------------------------------------------


def test_abrir_gera_e_exibe(editor_com_placa) -> None:
    editor = editor_com_placa
    assert editor.produto.id == "placa_nome"
    assert editor.ultima_geracao is not None
    assert editor.pilha.currentIndex() == PAGINA_VIEWPORT
    assert editor.viewport.ator_do_corpo("placa") is not None


def test_abrir_habilita_restaurar(editor_com_placa) -> None:
    assert editor_com_placa.acao_restaurar.isEnabled()


def test_abrir_monta_o_inspetor_do_produto(editor_com_placa) -> None:
    chaves = set(editor_com_placa.inspetor.campos)
    assert chaves == {p.chave for p in REGISTRO.obter("placa_nome").params}


def test_abrir_com_valores_iniciais(editor) -> None:
    editor.abrir(REGISTRO.obter("placa_nome"), {"nome": "Bia", "largura": 120.0})
    assert editor.inspetor.valores()["nome"] == "Bia"
    assert editor.ultima_geracao.dimensoes[0] == pytest.approx(120.0)


def test_mudar_parametro_regenera(editor_com_placa, qtbot) -> None:
    editor = editor_com_placa
    antes = editor.ultima_geracao
    with qtbot.waitSignal(editor.gerado):
        editor.inspetor.campos["nome"].widget.linha.setText("Bia")
    assert editor.ultima_geracao is not antes


def test_a_camera_nao_se_move_ao_editar(editor_com_placa) -> None:
    """O comportamento da seção 7 que sustenta o senso de edição contínua."""
    editor = editor_com_placa
    posicao = editor.viewport.posicao_da_camera()
    editor.inspetor.campos["largura"].widget.spin.setValue(120.0)
    assert editor.viewport.posicao_da_camera() == pytest.approx(posicao)


def test_trocar_de_produto_reenquadra(editor) -> None:
    editor.abrir(REGISTRO.obter("placa_nome"))
    posicao = editor.viewport.posicao_da_camera()
    editor.abrir(produto_de_dois_corpos())
    assert editor.viewport.posicao_da_camera() != pytest.approx(posicao)


def test_restaurar_padroes_volta_os_campos(editor_com_placa) -> None:
    editor = editor_com_placa
    editor.inspetor.campos["nome"].widget.linha.setText("Bia")
    editor.restaurar_padroes()
    assert editor.inspetor.valores()["nome"] == "Helena"


# --- árvore de corpos ----------------------------------------------------


def test_arvore_lista_um_item_por_corpo(editor) -> None:
    editor.abrir(produto_de_dois_corpos())
    assert editor.arvore.nomes() == ["base", "tampa"]


def test_desmarcar_corpo_esconde_na_viewport(editor) -> None:
    editor.abrir(produto_de_dois_corpos())
    item = editor.arvore.topLevelItem(1)
    from PySide6.QtCore import Qt

    item.setCheckState(0, Qt.CheckState.Unchecked)
    assert editor.viewport.ator_do_corpo("tampa").GetVisibility() == 0
    assert editor.viewport.ator_do_corpo("base").GetVisibility() == 1


def test_arvore_e_recolhivel(editor_com_placa) -> None:
    editor = editor_com_placa
    assert editor.arvore.isVisible()
    editor.alternar_arvore()
    assert not editor.arvore.isVisible()


# --- barra de status -----------------------------------------------------


def test_status_mostra_as_dimensoes(editor_com_placa) -> None:
    texto = editor_com_placa.status.dimensoes.text()
    assert "80.0 × 25.0" in texto
    assert "mm" in texto


def test_status_mostra_a_contagem_de_corpos(editor) -> None:
    editor.abrir(produto_de_dois_corpos())
    assert "2 corpo(s)" in editor.status.estado.text()


def test_status_mostra_os_avisos_do_produto(editor) -> None:
    editor.abrir(produto_de_dois_corpos())
    assert "um aviso qualquer" in editor.status.avisos.text()


def test_sem_aviso_o_campo_fica_vazio(editor_com_placa) -> None:
    assert editor_com_placa.status.avisos.text() == ""


def test_aviso_de_compressao_chega_a_barra(editor) -> None:
    editor.abrir(
        REGISTRO.obter("placa_nome"),
        {"nome": "Bartolomeu Nascimento", "largura": 60.0},
    )
    assert "comprimido" in editor.status.avisos.text()


# --- erros ---------------------------------------------------------------


def test_valor_invalido_grifa_o_campo_e_nao_troca_a_peca(editor_com_placa) -> None:
    editor = editor_com_placa
    anterior = editor.ultima_geracao

    editor.inspetor.campos["nome"].widget.linha.setText("   ")

    assert editor.ultima_geracao is anterior
    assert editor.pilha.currentIndex() == PAGINA_VIEWPORT
    assert "inválido" in editor.status.estado.text()


def test_falha_de_geracao_mostra_painel_com_traceback(editor) -> None:
    def gerar(_valores: dict[str, Any]):
        raise ZeroDivisionError("division by zero")

    produto = Produto(
        id="quebrado",
        nome="Quebrado",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(Param(chave="x", rotulo="X", tipo=TipoParam.INTEIRO, padrao=1),),
        gerar=gerar,
    )
    editor.abrir(produto)

    assert editor.pilha.currentIndex() == PAGINA_ERRO
    assert "ZeroDivisionError" in editor.painel_de_erro.detalhe.toPlainText()
    assert "Traceback" in editor.painel_de_erro.detalhe.toPlainText()


def test_inspetor_continua_ativo_depois_de_falha(editor) -> None:
    """O operador precisa poder corrigir o valor sem reabrir o produto."""
    chamadas: list[int] = []

    def gerar(valores: dict[str, Any]):
        chamadas.append(valores["x"])
        if valores["x"] < 5:
            raise ValueError("x pequeno demais")
        return Box(10, 10, 10)

    produto = Produto(
        id="condicional",
        nome="Condicional",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(
            Param(chave="x", rotulo="X", tipo=TipoParam.INTEIRO, padrao=1, minimo=0, maximo=9),
        ),
        gerar=gerar,
    )
    editor.abrir(produto)
    assert editor.pilha.currentIndex() == PAGINA_ERRO

    editor.inspetor.campos["x"].widget.setValue(7)
    assert editor.pilha.currentIndex() == PAGINA_VIEWPORT
    assert chamadas[-1] == 7


def test_traceback_do_painel_e_copiavel(editor) -> None:
    def gerar(_valores: dict[str, Any]):
        raise RuntimeError("estourou")

    produto = Produto(
        id="estoura",
        nome="Estoura",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(),
        gerar=gerar,
    )
    editor.abrir(produto)
    assert editor.painel_de_erro.detalhe.isReadOnly()
    assert editor.painel_de_erro.detalhe.textInteractionFlags() != 0


# --- peça grande demais --------------------------------------------------


def test_peca_que_excede_o_volume_e_sinalizada(editor) -> None:
    produto = Produto(
        id="gigante",
        nome="Gigante",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(),
        gerar=lambda _v: Box(300, 300, 10),
    )
    editor.abrir(produto)

    assert "excede o volume" in editor.status.dimensoes.text()
    ator = editor.viewport.ator_do_corpo("corpo_1")
    vermelho, verde, azul = ator.GetProperty().GetColor()
    assert vermelho > verde and vermelho > azul
