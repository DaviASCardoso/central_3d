"""Inspetor de parâmetros, gerado inteiramente a partir da declaração.

O mapeamento de tipo para widget é fixo e não é configurável por produto,
porque consistência vale mais que expressividade aqui. Ver a seção 11 do
CENTRAL.md.

Nenhuma regra de negócio mora neste módulo: ele lê `Param`, monta widget, e
emite o dicionário de valores. Quem valida é o núcleo; o inspetor apenas
recebe os erros de volta e grifa o campo culpado.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal, SignalInstance
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from central.contrato import Param, Produto, TipoParam
from central.log import obter
from central.ui import tema

_log = obter(__name__)

GRUPO_AVANCADO = "Avançado"
PASSOS_DO_SLIDER = 1000
"""Resolução do slider quando o parâmetro decimal não declara `passo`."""
DURACAO_DA_ANIMACAO = 120
"""Milissegundos da transição de visibilidade condicional."""
MAXIMO_DE_BOTOES_SEGMENTADOS = 3
"""Acima disso, `ESCOLHA` vira combo em vez de botões."""


class CampoDeCor(QPushButton):
    """Botão que abre o seletor de cor nativo e guarda o hexadecimal."""

    valor_mudou = Signal(str)

    def __init__(self, inicial: str, pai: QWidget | None = None) -> None:
        """Monta o botão já pintado com a cor inicial.

        Args:
            inicial: Cor hexadecimal inicial.
            pai: Widget pai.
        """
        super().__init__(pai)
        self._valor = inicial
        self.clicked.connect(self._escolher)
        self._repintar()

    def _escolher(self) -> None:
        """Abre o seletor nativo e adota a cor escolhida."""
        escolhida = QColorDialog.getColor(QColor(self._valor), self, "Cor de exibição")
        if escolhida.isValid():
            self.definir(escolhida.name().upper())
            self.valor_mudou.emit(self._valor)

    def definir(self, valor: str) -> None:
        """Adota uma cor sem abrir o seletor.

        Args:
            valor: Cor hexadecimal.
        """
        self._valor = valor
        self._repintar()

    def valor(self) -> str:
        """Devolve a cor atual em hexadecimal."""
        return self._valor

    def _repintar(self) -> None:
        """Reflete a cor no próprio botão."""
        self.setText(self._valor)
        contraste = "#000000" if QColor(self._valor).lightnessF() > 0.6 else "#FFFFFF"
        self.setStyleSheet(
            f"background: {self._valor}; color: {contraste}; "
            f"border: 1px solid {tema.paleta_atual().borda}; "
            f"border-radius: {tema.RAIO}px; padding: 4px 12px;"
        )


class DecimalComSlider(QWidget):
    """Slider acoplado a um spinbox, para decimal com mínimo e máximo.

    Só o slider impede digitar um valor preciso, e só o spinbox impede
    explorar. Os dois juntos resolvem os dois casos.
    """

    valor_mudou = Signal(float)

    def __init__(self, param: Param, pai: QWidget | None = None) -> None:
        """Monta o par slider e spinbox a partir da declaração.

        Args:
            param: O parâmetro, que precisa ter `minimo` e `maximo`.
            pai: Widget pai.
        """
        super().__init__(pai)
        self._minimo = float(param.minimo)  # type: ignore[arg-type]
        self._maximo = float(param.maximo)  # type: ignore[arg-type]
        self._passo = float(param.passo) if param.passo else None

        self.spin = QDoubleSpinBox()
        self.spin.setRange(self._minimo, self._maximo)
        self.spin.setDecimals(_casas_decimais(param))
        if self._passo:
            self.spin.setSingleStep(self._passo)
        if param.unidade:
            self.spin.setSuffix(f" {param.unidade}")
        self.spin.setValue(float(param.padrao))

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self._quantidade_de_passos())
        self.slider.setValue(self._para_slider(float(param.padrao)))

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(tema.ESPACAMENTO)
        disposicao.addWidget(self.slider, 1)
        disposicao.addWidget(self.spin)

        self.slider.valueChanged.connect(self._do_slider)
        self.spin.valueChanged.connect(self._do_spin)
        self._emitindo = False

    def _quantidade_de_passos(self) -> int:
        if self._passo:
            return max(1, round((self._maximo - self._minimo) / self._passo))
        return PASSOS_DO_SLIDER

    def _para_slider(self, valor: float) -> int:
        fracao = (valor - self._minimo) / (self._maximo - self._minimo)
        return round(fracao * self._quantidade_de_passos())

    def _do_slider_para_valor(self, posicao: int) -> float:
        fracao = posicao / self._quantidade_de_passos()
        return self._minimo + fracao * (self._maximo - self._minimo)

    def _do_slider(self, posicao: int) -> None:
        if self._emitindo:
            return
        self._emitindo = True
        self.spin.setValue(self._do_slider_para_valor(posicao))
        self._emitindo = False
        self.valor_mudou.emit(self.spin.value())

    def _do_spin(self, valor: float) -> None:
        if self._emitindo:
            return
        self._emitindo = True
        self.slider.setValue(self._para_slider(valor))
        self._emitindo = False
        self.valor_mudou.emit(valor)

    def valor(self) -> float:
        """Devolve o valor atual."""
        return self.spin.value()

    def definir(self, valor: float) -> None:
        """Ajusta os dois controles sem emitir sinal.

        Args:
            valor: O novo valor.
        """
        self._emitindo = True
        self.spin.setValue(valor)
        self.slider.setValue(self._para_slider(valor))
        self._emitindo = False


class BotoesSegmentados(QWidget):
    """Grupo de botões exclusivos, para `ESCOLHA` com poucas opções."""

    valor_mudou = Signal(str)

    def __init__(self, opcoes: tuple[str, ...], inicial: str, pai: QWidget | None = None) -> None:
        """Monta um botão por opção.

        Args:
            opcoes: As opções declaradas.
            inicial: A opção marcada de início.
            pai: Widget pai.
        """
        super().__init__(pai)
        self._grupo = QButtonGroup(self)
        self._grupo.setExclusive(True)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(tema.ESPACAMENTO // 2)

        for indice, opcao in enumerate(opcoes):
            botao = QPushButton(opcao)
            botao.setCheckable(True)
            botao.setChecked(opcao == inicial)
            self._grupo.addButton(botao, indice)
            disposicao.addWidget(botao)

        self._opcoes = opcoes
        self._grupo.idClicked.connect(
            lambda indice: self.valor_mudou.emit(self._opcoes[indice])
        )

    def valor(self) -> str:
        """Devolve a opção marcada."""
        marcado = self._grupo.checkedId()
        return self._opcoes[marcado] if marcado >= 0 else self._opcoes[0]

    def definir(self, valor: str) -> None:
        """Marca uma opção sem emitir sinal.

        Args:
            valor: A opção a marcar.
        """
        if valor not in self._opcoes:
            return
        self._grupo.button(self._opcoes.index(valor)).setChecked(True)


class CampoDeTexto(QWidget):
    """Campo de linha, com contador de caracteres quando há `max_len`."""

    valor_mudou = Signal(str)

    def __init__(self, param: Param, pai: QWidget | None = None) -> None:
        """Monta o campo e, se couber, o contador.

        Args:
            param: O parâmetro declarado.
            pai: Widget pai.
        """
        super().__init__(pai)
        self._max_len = param.max_len

        self.linha = QLineEdit(str(param.padrao))
        if param.max_len is not None:
            self.linha.setMaxLength(param.max_len)

        disposicao = QHBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.setSpacing(tema.ESPACAMENTO)
        disposicao.addWidget(self.linha, 1)

        self.contador: QLabel | None = None
        if param.max_len is not None:
            self.contador = QLabel()
            self.contador.setStyleSheet(f"color: {tema.paleta_atual().texto_fraco};")
            disposicao.addWidget(self.contador)
            self._atualizar_contador(self.linha.text())

        self.linha.textChanged.connect(self._mudou)

    def _mudou(self, texto: str) -> None:
        self._atualizar_contador(texto)
        self.valor_mudou.emit(texto)

    def _atualizar_contador(self, texto: str) -> None:
        if self.contador is not None:
            self.contador.setText(f"{len(texto)}/{self._max_len}")

    def valor(self) -> str:
        """Devolve o texto atual."""
        return self.linha.text()

    def definir(self, valor: str) -> None:
        """Ajusta o texto sem emitir sinal.

        Args:
            valor: O novo texto.
        """
        self.linha.blockSignals(True)
        self.linha.setText(valor)
        self.linha.blockSignals(False)
        self._atualizar_contador(valor)


def _casas_decimais(param: Param) -> int:
    """Deduz quantas casas decimais o spinbox precisa mostrar."""
    if not param.passo:
        return 2
    texto = f"{param.passo:.10f}".rstrip("0")
    if "." not in texto:
        return 0
    return min(4, len(texto.split(".")[1]))


class Campo:
    """Um parâmetro montado: rótulo, widget de edição e estado de erro."""

    def __init__(self, param: Param, widget: QWidget, rotulo: QLabel) -> None:
        """Guarda as três partes de uma linha do inspetor.

        Args:
            param: A declaração de origem.
            widget: O controle de edição.
            rotulo: O rótulo à esquerda.
        """
        self.param = param
        self.widget = widget
        self.rotulo = rotulo
        self._animacao: QPropertyAnimation | None = None
        self._estilo_normal = ""

    def valor(self) -> Any:
        """Lê o valor corrente do widget."""
        alvo = self.widget
        if isinstance(alvo, (CampoDeTexto, DecimalComSlider, BotoesSegmentados, CampoDeCor)):
            return alvo.valor()
        if isinstance(alvo, QComboBox):
            return alvo.currentText()
        if isinstance(alvo, QCheckBox):
            return alvo.isChecked()
        if isinstance(alvo, (QSpinBox, QDoubleSpinBox)):
            return alvo.value()
        raise TypeError(f"widget não reconhecido: {type(alvo).__name__}")

    def definir(self, valor: Any) -> None:
        """Escreve um valor no widget sem emitir sinal de mudança.

        Args:
            valor: O valor a exibir.
        """
        alvo = self.widget
        if isinstance(alvo, (CampoDeTexto, DecimalComSlider, BotoesSegmentados, CampoDeCor)):
            alvo.definir(valor)
            return
        alvo.blockSignals(True)
        if isinstance(alvo, QComboBox):
            alvo.setCurrentText(valor)
        elif isinstance(alvo, QCheckBox):
            alvo.setChecked(bool(valor))
        elif isinstance(alvo, (QSpinBox, QDoubleSpinBox)):
            alvo.setValue(valor)
        alvo.blockSignals(False)

    def grifar(self, mensagens: list[str]) -> None:
        """Marca ou desmarca o campo como culpado por um erro de validação.

        Args:
            mensagens: Erros da validação; lista vazia limpa o grifo.
        """
        paleta = tema.paleta_atual()
        if mensagens:
            self.rotulo.setStyleSheet(f"color: {paleta.erro};")
            self.widget.setStyleSheet(f"border: 1px solid {paleta.erro};")
            self.widget.setToolTip("\n".join(mensagens))
        else:
            self.rotulo.setStyleSheet("")
            self.widget.setStyleSheet(self._estilo_normal)
            self.widget.setToolTip(self.param.ajuda or "")

    def definir_visivel(self, visivel: bool, animar: bool = True) -> None:
        """Mostra ou esconde o campo, com transição curta.

        Um campo escondido mantém seu valor e continua sendo passado a `gerar`.

        Args:
            visivel: Se o campo deve aparecer.
            animar: Se a troca deve ser animada.
        """
        if visivel == self.widget.isVisibleTo(self.widget.parentWidget()):
            return

        self.rotulo.setVisible(visivel)
        self.widget.setVisible(visivel)

        if not animar:
            return

        efeito = QPropertyAnimation(self.widget, b"windowOpacity", self.widget)
        efeito.setDuration(DURACAO_DA_ANIMACAO)
        efeito.setStartValue(0.0 if visivel else 1.0)
        efeito.setEndValue(1.0 if visivel else 0.0)
        efeito.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._animacao = efeito


def montar_widget(param: Param) -> QWidget:
    """Cria o widget de edição de um parâmetro.

    O mapeamento é fixo, conforme a seção 11: texto vira campo de linha com
    contador quando há `max_len`; decimal com mínimo e máximo vira slider
    acoplado a spinbox; decimal sem limites vira só spinbox; inteiro vira
    spinbox; booleano vira switch; escolha vira combo, ou botões segmentados
    com até três opções; cor vira botão que abre o seletor nativo.

    Args:
        param: A declaração do parâmetro.

    Returns:
        O widget correspondente, já com o valor padrão.

    Raises:
        ValueError: Se o tipo do parâmetro não tem mapeamento.
    """
    if param.tipo is TipoParam.TEXTO:
        return CampoDeTexto(param)

    if param.tipo is TipoParam.INTEIRO:
        spin = QSpinBox()
        spin.setRange(
            int(param.minimo) if param.minimo is not None else -1_000_000,
            int(param.maximo) if param.maximo is not None else 1_000_000,
        )
        if param.passo:
            spin.setSingleStep(int(param.passo))
        if param.unidade:
            spin.setSuffix(f" {param.unidade}")
        spin.setValue(int(param.padrao))
        return spin

    if param.tipo is TipoParam.DECIMAL:
        if param.minimo is not None and param.maximo is not None:
            return DecimalComSlider(param)
        spin_decimal = QDoubleSpinBox()
        spin_decimal.setRange(
            param.minimo if param.minimo is not None else -1e9,
            param.maximo if param.maximo is not None else 1e9,
        )
        spin_decimal.setDecimals(_casas_decimais(param))
        if param.passo:
            spin_decimal.setSingleStep(param.passo)
        if param.unidade:
            spin_decimal.setSuffix(f" {param.unidade}")
        spin_decimal.setValue(float(param.padrao))
        return spin_decimal

    if param.tipo is TipoParam.BOOLEANO:
        caixa = QCheckBox()
        caixa.setChecked(bool(param.padrao))
        return caixa

    if param.tipo is TipoParam.ESCOLHA:
        opcoes = param.opcoes or ()
        if 0 < len(opcoes) <= MAXIMO_DE_BOTOES_SEGMENTADOS:
            return BotoesSegmentados(opcoes, str(param.padrao))
        combo = QComboBox()
        combo.addItems(opcoes)
        combo.setCurrentText(str(param.padrao))
        return combo

    if param.tipo is TipoParam.COR:
        return CampoDeCor(str(param.padrao))

    raise ValueError(f"tipo de parâmetro sem mapeamento: {param.tipo}")


def _sinal_de_mudanca(widget: QWidget) -> SignalInstance:
    """Devolve o sinal que cada tipo de widget emite ao mudar de valor."""
    if isinstance(widget, (CampoDeTexto, DecimalComSlider, BotoesSegmentados, CampoDeCor)):
        return widget.valor_mudou
    if isinstance(widget, QComboBox):
        return widget.currentTextChanged
    if isinstance(widget, QCheckBox):
        return widget.toggled
    if isinstance(widget, (QSpinBox, QDoubleSpinBox)):
        return widget.valueChanged
    raise TypeError(f"widget sem sinal de mudança: {type(widget).__name__}")


class SecaoColapsavel(QWidget):
    """Grupo que se abre e fecha, usado pela seção Avançado."""

    def __init__(self, titulo: str, pai: QWidget | None = None) -> None:
        """Monta a seção fechada.

        Args:
            titulo: Texto do cabeçalho.
            pai: Widget pai.
        """
        super().__init__(pai)
        self.botao = QToolButton()
        self.botao.setText(titulo)
        self.botao.setCheckable(True)
        self.botao.setChecked(False)
        self.botao.setArrowType(Qt.ArrowType.RightArrow)
        self.botao.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.botao.setStyleSheet("border: none;")

        self.conteudo = QWidget()
        self.conteudo.setVisible(False)
        self.formulario = QFormLayout(self.conteudo)
        self.formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        disposicao = QVBoxLayout(self)
        disposicao.setContentsMargins(0, 0, 0, 0)
        disposicao.addWidget(self.botao)
        disposicao.addWidget(self.conteudo)

        self.botao.toggled.connect(self._alternar)

    def _alternar(self, aberto: bool) -> None:
        self.conteudo.setVisible(aberto)
        self.botao.setArrowType(
            Qt.ArrowType.DownArrow if aberto else Qt.ArrowType.RightArrow
        )

    def esta_aberta(self) -> bool:
        """Diz se a seção está expandida."""
        return self.botao.isChecked()

    def abrir(self) -> None:
        """Expande a seção."""
        self.botao.setChecked(True)


class Inspetor(QScrollArea):
    """O painel direito do editor, montado a partir de `Produto.params`."""

    valores_mudaram = Signal(dict)
    campo_editado = Signal(str, dict)

    def __init__(self, produto: Produto, pai: QWidget | None = None) -> None:
        """Monta um campo por parâmetro, agrupado como o manifesto declara.

        Args:
            produto: O manifesto cujos parâmetros serão editados.
            pai: Widget pai.
        """
        super().__init__(pai)
        self.produto = produto
        self.campos: dict[str, Campo] = {}

        self.setWidgetResizable(True)
        raiz = QWidget()
        self._disposicao = QVBoxLayout(raiz)
        self._disposicao.setContentsMargins(
            tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2, tema.ESPACAMENTO * 2
        )
        self._disposicao.setSpacing(tema.ESPACAMENTO * 2)

        self._montar_grupos()
        self._disposicao.addStretch(1)
        self.setWidget(raiz)

        self._reavaliar_visibilidade(animar=False)

    def _montar_grupos(self) -> None:
        """Cria uma caixa por grupo declarado, e a seção Avançado ao final."""
        normais = [p for p in self.produto.params if not p.avancado]
        avancados = [p for p in self.produto.params if p.avancado]

        for nome_do_grupo in _ordem_dos_grupos(normais):
            caixa = QGroupBox(nome_do_grupo)
            formulario = QFormLayout(caixa)
            formulario.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            formulario.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
            )
            for param in _do_grupo(normais, nome_do_grupo):
                self._acrescentar(formulario, param)
            self._disposicao.addWidget(caixa)

        if avancados:
            self.secao_avancada = SecaoColapsavel(GRUPO_AVANCADO)
            for param in sorted(avancados, key=lambda p: (p.grupo, p.ordem)):
                self._acrescentar(self.secao_avancada.formulario, param)
            self._disposicao.addWidget(self.secao_avancada)
        else:
            self.secao_avancada = None

    def _acrescentar(self, formulario: QFormLayout, param: Param) -> None:
        """Monta uma linha do formulário para um parâmetro."""
        widget = montar_widget(param)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        if param.ajuda:
            widget.setToolTip(param.ajuda)

        rotulo = QLabel(param.rotulo)
        if param.ajuda:
            rotulo.setToolTip(param.ajuda)

        formulario.addRow(rotulo, widget)
        campo = Campo(param, widget, rotulo)
        self.campos[param.chave] = campo

        _sinal_de_mudanca(widget).connect(
            lambda *_, chave=param.chave: self._mudou(chave)
        )

    def _mudou(self, chave: str) -> None:
        """Reage a uma edição: reavalia visibilidade e emite os valores.

        `campo_editado` sai junto de `valores_mudaram` e diz qual campo mexeu,
        para que o editor decida entre atualizar na hora ou aguardar o
        debounce. Quem só quer os valores continua ouvindo `valores_mudaram`.

        Args:
            chave: A chave do parâmetro que o operador acabou de editar.
        """
        self._reavaliar_visibilidade()
        valores = self.valores()
        self.campo_editado.emit(chave, valores)
        self.valores_mudaram.emit(valores)

    def _reavaliar_visibilidade(self, animar: bool = True) -> None:
        """Aplica `visivel_se` de todos os campos com os valores correntes."""
        valores = self.valores()
        for campo in self.campos.values():
            if campo.param.visivel_se is None:
                continue
            campo.definir_visivel(bool(campo.param.visivel_se(valores)), animar=animar)

    def valores(self) -> dict[str, Any]:
        """Devolve os valores de todos os campos.

        Campos escondidos por `visivel_se` continuam presentes, porque o
        contrato diz que eles mantêm o valor e seguem sendo passados a `gerar`.

        Returns:
            Os valores indexados pela chave do parâmetro.
        """
        return {chave: campo.valor() for chave, campo in self.campos.items()}

    def definir_valores(self, valores: dict[str, Any]) -> None:
        """Escreve valores nos campos sem disparar geração.

        Chaves que o produto não declara são ignoradas, e parâmetros ausentes
        do dicionário voltam ao padrão. É assim que o recarregamento a quente
        preserva o que ainda existe.

        Args:
            valores: Valores a exibir.
        """
        for chave, campo in self.campos.items():
            campo.definir(valores.get(chave, campo.param.padrao))
        self._reavaliar_visibilidade(animar=False)

    def restaurar_padroes(self) -> None:
        """Devolve todos os campos ao valor declarado como padrão."""
        self.definir_valores({p.chave: p.padrao for p in self.produto.params})
        self.valores_mudaram.emit(self.valores())

    def grifar_erros(self, erros: dict[str, list[str]]) -> None:
        """Marca os campos culpados por erros de validação.

        Args:
            erros: Mensagens indexadas pela chave, como o núcleo devolve.
        """
        for chave, campo in self.campos.items():
            campo.grifar(erros.get(chave, []))

    def campos_visiveis(self) -> list[str]:
        """Devolve as chaves dos campos atualmente visíveis."""
        return [
            chave
            for chave, campo in self.campos.items()
            if campo.widget.isVisibleTo(self)
        ]


def _ordem_dos_grupos(params: list[Param]) -> list[str]:
    """Devolve os nomes de grupo na ordem de primeira aparição."""
    vistos: list[str] = []
    for param in params:
        if param.grupo not in vistos:
            vistos.append(param.grupo)
    return vistos


def _do_grupo(params: list[Param], grupo: str) -> list[Param]:
    """Devolve os parâmetros de um grupo, ordenados por `ordem`."""
    return sorted((p for p in params if p.grupo == grupo), key=lambda p: p.ordem)
