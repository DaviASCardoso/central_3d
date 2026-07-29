"""Testes do editor: três painéis, geração assíncrona, debounce e estado."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest
from build123d import Box
from PySide6.QtCore import Qt

from central.contrato import Corpo, Param, Produto, Resultado, TipoParam
from central.nucleo import descobrir
from central.ui import tema
from central.ui.editor import DEBOUNCE_EM_MS, PAGINA_ERRO, PAGINA_VIEWPORT, Editor

pytestmark = pytest.mark.ui

REGISTRO = descobrir()
ESPERA = 30_000


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


def abrir(editor: Editor, qtbot, produto: Produto, valores: dict[str, Any] | None = None):
    """Abre um produto e espera a primeira geração terminar."""
    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        editor.abrir(produto, valores)
    return editor


@pytest.fixture
def editor_com_placa(editor, qtbot):
    return abrir(editor, qtbot, REGISTRO.obter("placa_nome"))


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


def test_indicador_comeca_parado(editor) -> None:
    assert not editor.indicador.esta_ativo()


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


def test_abrir_com_valores_iniciais(editor, qtbot) -> None:
    abrir(editor, qtbot, REGISTRO.obter("placa_nome"), {"nome": "Bia", "largura": 120.0})
    assert editor.inspetor.valores()["nome"] == "Bia"
    assert editor.ultima_geracao.dimensoes[0] == pytest.approx(120.0)


def test_a_camera_nao_se_move_ao_editar(editor_com_placa, qtbot) -> None:
    editor = editor_com_placa
    posicao = editor.viewport.posicao_da_camera()
    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        editor.inspetor.campos["largura"].widget.spin.setValue(120.0)
    assert editor.viewport.posicao_da_camera() == pytest.approx(posicao)


def test_trocar_de_produto_reenquadra(editor, qtbot) -> None:
    abrir(editor, qtbot, REGISTRO.obter("placa_nome"))
    posicao = editor.viewport.posicao_da_camera()
    abrir(editor, qtbot, produto_de_dois_corpos())
    assert editor.viewport.posicao_da_camera() != pytest.approx(posicao)


def test_restaurar_padroes_volta_os_campos(editor_com_placa, qtbot) -> None:
    editor = editor_com_placa
    editor.inspetor.campos["nome"].widget.linha.setText("Bia")
    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        editor.restaurar_padroes()
    assert editor.inspetor.valores()["nome"] == "Helena"


# --- debounce ------------------------------------------------------------


def test_edicao_continua_e_debounceada(editor_com_placa, qtbot) -> None:
    """Arrastar um slider deve disparar uma geração só, após o silêncio."""
    editor = editor_com_placa
    geracoes: list[Any] = []
    editor.gerado.connect(geracoes.append)

    slider = editor.inspetor.campos["largura"].widget.spin
    for valor in range(90, 121, 5):
        slider.setValue(float(valor))
        qtbot.wait(20)

    assert editor.debounce_pendente()
    assert geracoes == []

    qtbot.waitUntil(lambda: len(geracoes) == 1, timeout=ESPERA)
    assert editor.ultima_geracao.dimensoes[0] == pytest.approx(120.0)


def test_edicao_discreta_e_imediata(editor_com_placa, qtbot) -> None:
    """Esperar 250 ms depois de um clique num combo pareceria travamento."""
    editor = editor_com_placa
    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        editor.inspetor.campos["fonte"].widget.setCurrentText("Verdana")
    assert not editor.debounce_pendente()


def test_debounce_espera_o_intervalo_declarado(editor_com_placa, qtbot) -> None:
    editor = editor_com_placa
    editor.inspetor.campos["nome"].widget.linha.setText("Ab")
    inicio = time.monotonic()
    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        pass
    decorrido_em_ms = (time.monotonic() - inicio) * 1000
    assert decorrido_em_ms >= DEBOUNCE_EM_MS * 0.8


def test_interface_responde_durante_a_geracao(editor, qtbot) -> None:
    """A geração roda fora da thread da interface; a UI não pode congelar."""
    liberar = threading.Event()
    entrou = threading.Event()

    def gerar_lento(valores: dict[str, Any]):
        entrou.set()
        liberar.wait(timeout=10)
        return Box(valores["lado"], 10, 10)

    produto = Produto(
        id="lento",
        nome="Lento",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(
            Param(
                chave="lado",
                rotulo="Lado",
                tipo=TipoParam.DECIMAL,
                padrao=10.0,
                minimo=1.0,
                maximo=50.0,
            ),
        ),
        gerar=gerar_lento,
    )

    editor.abrir(produto)
    assert entrou.wait(timeout=10)

    # A interface continua atendendo eventos enquanto o worker trabalha.
    qtbot.wait(50)
    editor.inspetor.campos["lado"].widget.spin.setValue(15.0)
    assert editor.inspetor.valores()["lado"] == pytest.approx(15.0)

    liberar.set()
    qtbot.waitUntil(lambda: editor.ultima_geracao is not None, timeout=ESPERA)


# --- estado visível da geração ------------------------------------------


def test_indicador_aparece_durante_a_geracao(editor, qtbot) -> None:
    liberar = threading.Event()
    entrou = threading.Event()

    def gerar_lento(_valores: dict[str, Any]):
        entrou.set()
        liberar.wait(timeout=10)
        return Box(10, 10, 10)

    produto = Produto(
        id="lento2",
        nome="Lento",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(),
        gerar=gerar_lento,
    )

    editor.abrir(produto)
    assert entrou.wait(timeout=10)
    qtbot.waitUntil(lambda: editor.indicador.esta_ativo(), timeout=ESPERA)

    liberar.set()
    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        pass
    assert not editor.indicador.esta_ativo()


def test_a_peca_anterior_nunca_some(editor_com_placa, qtbot) -> None:
    """Nunca a viewport ficando vazia; a peça só esmaece enquanto gera."""
    editor = editor_com_placa
    assert editor.viewport.ator_do_corpo("placa") is not None

    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        editor.inspetor.campos["fonte"].widget.setCurrentText("Tahoma")

    assert editor.viewport.ator_do_corpo("placa") is not None
    assert editor.pilha.currentIndex() == PAGINA_VIEWPORT


def test_opacidade_volta_ao_normal_depois_de_gerar(editor_com_placa, qtbot) -> None:
    from central.ui.viewport import OPACIDADE_NORMAL

    editor = editor_com_placa
    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        editor.inspetor.campos["fonte"].widget.setCurrentText("Georgia")

    opacidade = editor.viewport.ator_do_corpo("placa").GetProperty().GetOpacity()
    assert opacidade == pytest.approx(OPACIDADE_NORMAL)


# --- árvore de corpos ----------------------------------------------------


def test_arvore_lista_um_item_por_corpo(editor, qtbot) -> None:
    abrir(editor, qtbot, produto_de_dois_corpos())
    assert editor.arvore.nomes() == ["base", "tampa"]


def test_desmarcar_corpo_esconde_na_viewport(editor, qtbot) -> None:
    abrir(editor, qtbot, produto_de_dois_corpos())
    editor.arvore.topLevelItem(1).setCheckState(0, Qt.CheckState.Unchecked)
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


def test_status_mostra_a_contagem_de_corpos(editor, qtbot) -> None:
    abrir(editor, qtbot, produto_de_dois_corpos())
    assert "2 corpo(s)" in editor.status.estado.text()


def test_status_mostra_os_avisos_do_produto(editor, qtbot) -> None:
    abrir(editor, qtbot, produto_de_dois_corpos())
    assert "um aviso qualquer" in editor.status.avisos.text()


def test_sem_aviso_o_campo_fica_vazio(editor_com_placa) -> None:
    assert editor_com_placa.status.avisos.text() == ""


def test_aviso_de_compressao_chega_a_barra(editor, qtbot) -> None:
    abrir(
        editor,
        qtbot,
        REGISTRO.obter("placa_nome"),
        {"nome": "Bartolomeu Nascimento", "largura": 60.0},
    )
    assert "comprimido" in editor.status.avisos.text()


# --- erros ---------------------------------------------------------------


def test_valor_invalido_grifa_o_campo_e_nao_troca_a_peca(editor_com_placa, qtbot) -> None:
    editor = editor_com_placa
    anterior = editor.ultima_geracao

    with qtbot.waitSignal(editor.falhou, timeout=ESPERA):
        editor.inspetor.campos["nome"].widget.linha.setText("   ")

    assert editor.ultima_geracao is anterior
    assert editor.pilha.currentIndex() == PAGINA_VIEWPORT
    assert "inválido" in editor.status.estado.text()


def test_falha_de_geracao_mostra_painel_com_traceback(editor, qtbot) -> None:
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
    with qtbot.waitSignal(editor.falhou, timeout=ESPERA):
        editor.abrir(produto)

    assert editor.pilha.currentIndex() == PAGINA_ERRO
    assert "ZeroDivisionError" in editor.painel_de_erro.detalhe.toPlainText()
    assert "Traceback" in editor.painel_de_erro.detalhe.toPlainText()


def test_inspetor_continua_ativo_depois_de_falha(editor, qtbot) -> None:
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
    with qtbot.waitSignal(editor.falhou, timeout=ESPERA):
        editor.abrir(produto)
    assert editor.pilha.currentIndex() == PAGINA_ERRO

    editor.inspetor.campos["x"].widget.setValue(7)
    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        pass

    assert editor.pilha.currentIndex() == PAGINA_VIEWPORT
    assert chamadas[-1] == 7


def test_indicador_para_depois_de_falhar(editor, qtbot) -> None:
    produto = Produto(
        id="estoura",
        nome="Estoura",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(),
        gerar=lambda _v: (_ for _ in ()).throw(RuntimeError("estourou")),
    )
    with qtbot.waitSignal(editor.falhou, timeout=ESPERA):
        editor.abrir(produto)
    assert not editor.indicador.esta_ativo()


def test_traceback_do_painel_e_copiavel(editor, qtbot) -> None:
    produto = Produto(
        id="estoura2",
        nome="Estoura",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(),
        gerar=lambda _v: (_ for _ in ()).throw(RuntimeError("estourou")),
    )
    with qtbot.waitSignal(editor.falhou, timeout=ESPERA):
        editor.abrir(produto)
    assert editor.painel_de_erro.detalhe.isReadOnly()
    assert editor.painel_de_erro.detalhe.textInteractionFlags() != 0


# --- cache ---------------------------------------------------------------


def test_voltar_a_um_valor_ja_gerado_vem_do_cache(editor_com_placa, qtbot) -> None:
    editor = editor_com_placa
    acertos = editor.gerador.cache.estatisticas.acertos

    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        editor.inspetor.campos["fonte"].widget.setCurrentText("Verdana")
    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        editor.inspetor.campos["fonte"].widget.setCurrentText("Arial")

    assert editor.gerador.cache.estatisticas.acertos > acertos


def test_mudar_so_a_cor_nao_regenera_geometria(editor_com_placa, qtbot) -> None:
    editor = editor_com_placa
    acertos = editor.gerador.cache.estatisticas.acertos

    with qtbot.waitSignal(editor.gerado, timeout=ESPERA):
        editor.inspetor.campos["cor"].widget.definir("#FF0000")
        editor.inspetor.campos["cor"].widget.valor_mudou.emit("#FF0000")

    assert editor.gerador.cache.estatisticas.acertos == acertos + 1


# --- peça grande demais --------------------------------------------------


def test_peca_que_excede_o_volume_e_sinalizada(editor, qtbot) -> None:
    produto = Produto(
        id="gigante",
        nome="Gigante",
        versao="1.0.0",
        descricao="",
        categoria="Teste",
        params=(),
        gerar=lambda _v: Box(300, 300, 10),
    )
    abrir(editor, qtbot, produto)

    assert "excede o volume" in editor.status.dimensoes.text()
    ator = editor.viewport.ator_do_corpo("corpo_1")
    vermelho, verde, azul = ator.GetProperty().GetColor()
    assert vermelho > verde and vermelho > azul
