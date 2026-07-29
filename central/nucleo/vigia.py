"""Recarregamento a quente dos módulos de produto.

O fluxo de trabalho previsto é escrever o produto com o Claude Code em outra
janela e ver o resultado aparecer sem reiniciar. Um observador do `watchdog`
monitora `produtos/` recursivamente e, ao detectar escrita num `.py`, espera
duzentos milissegundos de silêncio para não disparar no meio de uma gravação
parcial. Ver a seção 5 do CENTRAL.md.

Falha de reload nunca derruba o app: o erro é registrado e a versão anterior do
módulo continua ativa.
"""

from __future__ import annotations

import importlib
import sys
import threading
import traceback
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from central.log import obter
from central.nucleo.registro import Registro, descobrir

_log = obter(__name__)

SILENCIO_EM_MS = 200
"""Quanto esperar sem novos eventos antes de recarregar."""

EXTENSAO = ".py"


class _Ouvinte(FileSystemEventHandler):
    """Traduz eventos do watchdog em pedidos de recarregamento."""

    def __init__(self, ao_mudar: Callable[[], None]) -> None:
        """Guarda o gancho a chamar quando um `.py` muda.

        Args:
            ao_mudar: Função sem argumentos, chamada a cada evento relevante.
        """
        super().__init__()
        self._ao_mudar = ao_mudar

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Reage a qualquer evento de arquivo dentro do diretório vigiado."""
        if event.is_directory:
            return
        caminho = Path(str(event.src_path))
        if caminho.suffix != EXTENSAO:
            return
        _log.debug("evento %s em %s", event.event_type, caminho.name)
        self._ao_mudar()


class VigiaDeProdutos(QObject):
    """Observa `produtos/` e reemite o registro quando algo muda.

    Signals:
        registro_mudou: Emitido com o `Registro` recém-descoberto.
        produtos_invalidados: Emitido com a lista de `id` que saíram do cache.
    """

    registro_mudou = Signal(object)
    produtos_invalidados = Signal(list)

    def __init__(
        self,
        diretorio: Path | None = None,
        silencio_em_ms: int = SILENCIO_EM_MS,
        pai: QObject | None = None,
    ) -> None:
        """Cria o vigia, ainda sem observar nada.

        Args:
            diretorio: Diretório de produtos. Por padrão, o do repositório.
            silencio_em_ms: Espera sem eventos antes de recarregar.
            pai: Objeto pai do Qt.
        """
        super().__init__(pai)
        from central.nucleo.registro import DIRETORIO_PADRAO

        self.diretorio = (diretorio or DIRETORIO_PADRAO).resolve()
        self.silencio_em_ms = silencio_em_ms
        self.registro: Registro | None = None

        self._observador: Observer | None = None  # type: ignore[valid-type]
        self._temporizador: threading.Timer | None = None
        self._trava = threading.Lock()
        self._recarregamentos = 0

    # --- ciclo de vida ---------------------------------------------------

    def iniciar(self) -> None:
        """Começa a observar o diretório de produtos."""
        if self._observador is not None:
            return
        self._observador = Observer()
        self._observador.schedule(
            _Ouvinte(self._agendar_recarga), str(self.diretorio), recursive=True
        )
        self._observador.start()
        _log.info("vigiando %s", self.diretorio)

    def encerrar(self, espera_em_s: float = 5.0) -> None:
        """Para de observar e cancela recarregamento pendente.

        Args:
            espera_em_s: Quanto esperar pela thread do observador.
        """
        with self._trava:
            if self._temporizador is not None:
                self._temporizador.cancel()
                self._temporizador = None
        if self._observador is not None:
            self._observador.stop()
            self._observador.join(timeout=espera_em_s)
            self._observador = None

    # --- recarregamento --------------------------------------------------

    def _agendar_recarga(self) -> None:
        """Reinicia a contagem de silêncio a cada evento.

        Uma gravação em duas etapas — escrever e depois truncar, como muitos
        editores fazem — produz dois eventos em poucos milissegundos, e sem
        essa espera o reload aconteceria no meio do arquivo pela metade.
        """
        with self._trava:
            if self._temporizador is not None:
                self._temporizador.cancel()
            self._temporizador = threading.Timer(
                self.silencio_em_ms / 1000.0, self.recarregar
            )
            self._temporizador.daemon = True
            self._temporizador.start()

    def recarregar(self) -> Registro | None:
        """Recarrega os módulos de produto e reemite o registro.

        Falha de reload não derruba nada: o erro vai para o log e a descoberta
        acontece mesmo assim, de modo que o módulo que quebrou aparece como
        falha na biblioteca e os demais continuam válidos.

        Returns:
            O novo registro, ou `None` se nem a descoberta foi possível.
        """
        with self._trava:
            self._temporizador = None

        anteriores = set(self.registro.produtos) if self.registro else set()
        self._recarregar_modulos()

        try:
            novo = descobrir(self.diretorio)
        except Exception:  # noqa: BLE001 -- recarga nunca derruba a Central
            _log.error("falha ao redescobrir produtos:\n%s", traceback.format_exc())
            return None

        self.registro = novo
        self._recarregamentos += 1

        invalidados = sorted(anteriores | set(novo.produtos))
        self.produtos_invalidados.emit(invalidados)
        self.registro_mudou.emit(novo)
        _log.info("recarregamento %d: %d produto(s)", self._recarregamentos, len(novo))
        return novo

    def _recarregar_modulos(self) -> None:
        """Roda `importlib.reload` nos módulos já importados de `produtos/`."""
        prefixo = f"{self.diretorio.name}."
        nomes = [
            nome
            for nome in list(sys.modules)
            if nome == self.diretorio.name or nome.startswith(prefixo)
        ]
        # Submódulos primeiro: recarregar o pacote antes do submódulo faria o
        # `from .geometria import gerar` do __init__ pegar a versão velha.
        for nome in sorted(nomes, key=lambda n: -n.count(".")):
            modulo = sys.modules.get(nome)
            if modulo is None:
                continue
            try:
                importlib.reload(modulo)
            except Exception:  # noqa: BLE001 -- módulo quebrado vira falha, não crash
                _log.warning(
                    "falha ao recarregar %s; a versão anterior continua ativa:\n%s",
                    nome,
                    traceback.format_exc(),
                )

    @property
    def recarregamentos(self) -> int:
        """Quantas recargas já aconteceram, usado nos testes."""
        return self._recarregamentos


def preservar_valores(
    anteriores: dict[str, object], params: tuple
) -> dict[str, object]:
    """Mantém os valores cujas chaves ainda existem no manifesto novo.

    Os que sumiram são descartados, e o inspetor devolve o padrão para eles.
    É assim que editar um produto com o editor aberto não perde o que o
    operador já tinha digitado. Ver a seção 5 do CENTRAL.md.

    Args:
        anteriores: Valores que estavam no inspetor antes da recarga.
        params: Os `Param` do manifesto recém-carregado.

    Returns:
        Apenas os valores cujas chaves sobreviveram.
    """
    chaves = {param.chave for param in params}
    return {chave: valor for chave, valor in anteriores.items() if chave in chaves}
