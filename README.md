# Motor de Inferencia

  1. El usuario escribe reglas y hechos en lenguaje natural (uno por línea).
  2. EXTRACTOR DE ÁTOMOS: cada proposición simple recibe una letra (P, Q, R...).
     Una misma frase escrita igual es siempre el mismo átomo; «no ...» es ¬átomo.
  3. TRADUCTOR: Los conectores del texto se convierten en fórmulas lógicas.
  4. ÁRBOL SEMÁNTICO: Se supone que TODAS las reglas son verdaderas y se
     descompone cada fórmula con su regla de expansión:
         una rama (alfa):  ∧   ¬∨   ¬→   ¬¬
         dos ramas (beta): ∨   →    ↔    ¬∧   ¬↔
  5. Una rama con un átomo y su negación se cierra (✕); las que quedan abiertas
     son los modelos: las condiciones que hacen verdaderas todas las reglas.
     Si todas se cierran, la base de conocimiento es INCONSISTENTE.
