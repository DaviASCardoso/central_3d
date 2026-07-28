"""Pacote com sublinhado no nome: a descoberta deve pulá-lo sem tentar importar.

Se a descoberta tentasse importar este pacote, a exceção abaixo apareceria como
uma falha no registro — que é exatamente o que o teste verifica não acontecer.
"""

from __future__ import annotations

raise RuntimeError("este pacote jamais deveria ser importado")
