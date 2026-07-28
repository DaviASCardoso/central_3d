"""Catálogo de produtos da Central.

Um pacote por produto, cada um expondo uma variável de módulo `MANIFESTO` do
tipo `central.contrato.Produto`. Pacotes cujo nome começa com sublinhado são
ignorados pela descoberta, que é como `_template` fica fora da biblioteca.

Um módulo de produto importa apenas de `central.contrato` e das bibliotecas de
geometria. Ver `CONTRATO.md` na raiz do repositório.
"""

from __future__ import annotations
