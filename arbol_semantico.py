from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Iterator, Optional, Union

sys.setrecursionlimit(20000)

# =============================================================================
#  1. FÓRMULAS
# =============================================================================
Y, O, IMP, IFF = "∧", "∨", "→", "↔"


@dataclass(frozen=True)
class Atom:
    nombre: str


@dataclass(frozen=True)
class Neg:
    sub: "Formula"


@dataclass(frozen=True)
class Bin:
    op: str
    izq: "Formula"
    der: "Formula"


Formula = Union[Atom, Neg, Bin]


def es_literal(f: Formula) -> bool:
    return isinstance(f, Atom) or (isinstance(f, Neg) and isinstance(f.sub, Atom))


def complementaria(lit: Formula) -> Formula:
    return lit.sub if isinstance(lit, Neg) else Neg(lit)


def mostrar(f: Formula) -> str:
    """Fórmula → texto, con paréntesis solo donde hacen falta."""
    if isinstance(f, Atom):
        return f.nombre
    if isinstance(f, Neg):
        interior = mostrar(f.sub)
        return "¬" + (interior if isinstance(f.sub, (Atom, Neg)) else f"({interior})")

    def lado(h: Formula) -> str:
        s = mostrar(h)
        if isinstance(h, Bin) and not (h.op == f.op and f.op in (Y, O)):
            return f"({s})"
        return s

    return f"{lado(f.izq)} {f.op} {lado(f.der)}"


# =============================================================================
#  2. LENGUAJE NATURAL → ÁTOMOS Y FÓRMULAS
# =============================================================================
class ErrorFrase(ValueError):
    """Frase que el traductor no logra interpretar."""


LETRAS = list("PQRSTUVWXYZABCDEFGHIJKLMNO")


def _sin_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


RE_IFF = re.compile(r",?\s+si y solo si\s+")
RE_NEG_TOTAL = re.compile(
    r"^(?:no es (?:verdad|cierto) que|es (?:falso|mentira) que|"
    r"no ocurre que|no es el caso que)\s+(.+)$")
RE_ENTONCES = re.compile(r",?\s+entonces\s+")
RE_SOLO_SI = re.compile(r",?\s+solo si\s+")
RE_SI_POSPUESTO = re.compile(r",?\s+si\s+")
RE_DISYUNCION = re.compile(r",?\s+(?:o|u)\s+")
RE_CONJUNCION = re.compile(r",?\s+(?:y|e|pero)\s+")
RE_PREFIJO_ATOMO = re.compile(r"^(?:es verdad que|es cierto que|ocurre que)\s+")


class Traductor:
    """Extrae los átomos y convierte cada frase en una fórmula."""

    def __init__(self) -> None:
        self._por_clave: dict[str, str] = {}   # frase normalizada → letra
        self.atomos: dict[str, str] = {}       # letra → frase original

    # -- preparación del texto -------------------------------------------------
    @staticmethod
    def _limpiar(frase: str) -> str:
        t = unicodedata.normalize("NFC", frase).lower().replace("sólo", "solo")
        t = re.sub(r"[¿?¡!\"“”«»().:]", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    def _letra(self, n: int) -> str:
        return LETRAS[n] if n < len(LETRAS) else f"P{n - len(LETRAS) + 1}"

    # -- átomos ---------------------------------------------------------------
    def _atomo(self, t: str) -> Atom:
        t = RE_PREFIJO_ATOMO.sub("", t)
        t = re.sub(r"\s+", " ", t.replace(",", " ")).strip()
        if not t:
            raise ErrorFrase("hay una proposición vacía")
        clave = _sin_acentos(t)
        if clave not in self._por_clave:
            letra = self._letra(len(self._por_clave))
            self._por_clave[clave] = letra
            self.atomos[letra] = t
        return Atom(self._por_clave[clave])

    # -- conectores (de menor a mayor precedencia) ------------------------------
    @staticmethod
    def _plegar(op: str, trozos: list, f) -> Formula:
        res = f(trozos[0])
        for t in trozos[1:]:
            res = Bin(op, res, f(t))
        return res

    def _formula(self, t: str) -> Formula:
        t = t.strip(" ,")
        if not t:
            raise ErrorFrase("falta una proposición")

        if m := RE_IFF.search(t):
            return Bin(IFF, self._formula(t[:m.start()]), self._formula(t[m.end():]))

        if m := RE_NEG_TOTAL.match(t):
            return Neg(self._formula(m.group(1)))

        if t.startswith("si "):
            cuerpo = t[3:]
            if m := RE_ENTONCES.search(cuerpo):
                ante, cons = cuerpo[:m.start()], cuerpo[m.end():]
            elif "," in cuerpo:
                ante, _, cons = cuerpo.partition(",")
            else:
                raise ErrorFrase(f"«{t}»: falta «entonces»")
            return Bin(IMP, self._formula(ante), self._formula(cons))

        if m := RE_SOLO_SI.search(t):
            return Bin(IMP, self._formula(t[:m.start()]), self._formula(t[m.end():]))

        if m := RE_SI_POSPUESTO.search(t):          # «A si B»  =  B → A
            return Bin(IMP, self._formula(t[m.end():]), self._formula(t[:m.start()]))

        trozos = RE_DISYUNCION.split(t)
        if len(trozos) > 1:
            return self._plegar(O, trozos, self._formula)

        trozos = RE_CONJUNCION.split(t)
        if len(trozos) > 1:
            return self._plegar(Y, trozos, self._formula)

        if t.startswith("no "):
            return Neg(self._formula(t[3:]))

        return self._atomo(t)

    def traducir(self, frase: str) -> Formula:
        return self._formula(self._limpiar(frase))


def separar_frases(texto: str) -> list[str]:
    """Una regla por línea; también se separa por punto o punto y coma."""
    return [p.strip() for p in re.split(r"[\n;]|\.(?:\s|$)", texto) if p.strip()]


# =============================================================================
#  3. REGLAS DE EXPANSIÓN (tabla de la clase)
# =============================================================================
# cada entrada: (tipo, función(a, b) → lista de ramas; cada rama = lista de fórmulas)
_DIRECTAS = {
    Y:   ("alfa", lambda a, b: [[a, b]]),
    O:   ("beta", lambda a, b: [[a], [b]]),
    IMP: ("beta", lambda a, b: [[Neg(a)], [b]]),
    IFF: ("beta", lambda a, b: [[a, b], [Neg(a), Neg(b)]]),
}
_NEGADAS = {
    Y:   ("beta", lambda a, b: [[Neg(a)], [Neg(b)]]),
    O:   ("alfa", lambda a, b: [[Neg(a), Neg(b)]]),
    IMP: ("alfa", lambda a, b: [[a, Neg(b)]]),
    IFF: ("beta", lambda a, b: [[a, Neg(b)], [Neg(a), b]]),
}


def expandir(f: Formula) -> tuple[str, list[list[Formula]]]:
    if isinstance(f, Bin):
        tipo, regla = _DIRECTAS[f.op]
        return tipo, regla(f.izq, f.der)
    if isinstance(f, Neg):
        g = f.sub
        if isinstance(g, Neg):
            return "alfa", [[g.sub]]
        if isinstance(g, Bin):
            tipo, regla = _NEGADAS[g.op]
            return tipo, regla(g.izq, g.der)
    raise ValueError(f"fórmula no expandible: {mostrar(f)}")


def nombre_regla(f: Formula) -> str:
    if isinstance(f, Neg):
        return "¬" + (f.sub.op if isinstance(f.sub, Bin) else "¬")
    return f.op


# =============================================================================
#  4. ÁRBOL SEMÁNTICO
# =============================================================================
@dataclass(eq=False)
class Nodo:
    ident: int
    formula: Formula
    etiqueta: str = ""
    padre: Optional["Nodo"] = None
    hijos: list["Nodo"] = field(default_factory=list)
    paso: int = 0                    # paso en que se expandió (0 = sin expandir)
    origen: Optional[int] = None     # nodo del que proviene
    regla: str = ""
    cierre: Optional[int] = None     # nodo con el que se contradice

    @property
    def cerrado(self) -> bool:
        return self.cierre is not None


class Arbol:
    def __init__(self, formulas: list[Formula]) -> None:
        self._n = 0
        self.pasos = 0
        self.raiz: Nodo = None  # type: ignore[assignment]
        self.omitidas: list[str] = []
        ultimo = None
        for i, f in enumerate(formulas, 1):
            ultimo = self._agregar(ultimo, f, etiqueta=f"R{i}")
            if ultimo.cerrado:
                self.omitidas = [f"R{j}" for j in range(i + 1, len(formulas) + 1)]
                break
        self._desarrollar()

    # -- estructura ----------------------------------------------------------------
    def _agregar(self, padre, f, etiqueta="", origen=None, regla="") -> Nodo:
        self._n += 1
        nodo = Nodo(self._n, f, etiqueta, padre, origen=origen, regla=regla)
        if padre is None:
            self.raiz = nodo
        else:
            padre.hijos.append(nodo)
        if es_literal(f):
            opuesta = complementaria(f)
            for a in self.camino(padre):
                if a.formula == opuesta:
                    nodo.cierre = a.ident
                    break
        return nodo

    @staticmethod
    def camino(nodo: Optional[Nodo]) -> list[Nodo]:
        res = []
        while nodo is not None:
            res.append(nodo)
            nodo = nodo.padre
        return res[::-1]

    def recorrido(self) -> Iterator[Nodo]:
        pila = [self.raiz]
        while pila:
            n = pila.pop()
            yield n
            pila.extend(reversed(n.hijos))

    def hojas(self) -> list[Nodo]:
        return [n for n in self.recorrido() if not n.hijos]

    def ramas_abiertas(self) -> list[Nodo]:
        return [h for h in self.hojas() if not h.cerrado]

    @staticmethod
    def hojas_abiertas_bajo(nodo: Nodo) -> list[Nodo]:
        res, pila = [], [nodo]
        while pila:
            n = pila.pop()
            if n.hijos:
                pila.extend(reversed(n.hijos))
            elif not n.cerrado:
                res.append(n)
        return res

    # -- construcción -------------------------------------------------------------
    def _siguiente(self) -> Optional[Nodo]:
        """Fórmula pendiente: primero las de una sola rama, luego las que bifurcan."""
        beta = None
        for n in self.recorrido():
            if n.paso or es_literal(n.formula) or not self.hojas_abiertas_bajo(n):
                continue
            if expandir(n.formula)[0] == "alfa":
                return n
            if beta is None:
                beta = n
        return beta

    def _pegar(self, hoja, formulas, origen: Nodo, sin_repetir: bool) -> None:
        actual = hoja
        presentes = {a.formula for a in self.camino(hoja)} if sin_repetir else set()
        for f in formulas:
            if f in presentes:
                continue
            actual = self._agregar(actual, f, origen=origen.ident,
                                   regla=nombre_regla(origen.formula))
            presentes.add(f)
            if actual.cerrado:
                break

    def _desarrollar(self) -> None:
        while (nodo := self._siguiente()) is not None:
            tipo, ramas = expandir(nodo.formula)
            self.pasos += 1
            nodo.paso = self.pasos
            for hoja in self.hojas_abiertas_bajo(nodo):   # en TODAS las ramas de abajo
                for rama in ramas:
                    self._pegar(hoja, rama, nodo, tipo == "alfa")

    # -- resultados -----------------------------------------------------------------
    def modelo(self, hoja: Nodo) -> dict[str, bool]:
        m: dict[str, bool] = {}
        for n in self.camino(hoja):
            f = n.formula
            if isinstance(f, Atom):
                m[f.nombre] = True
            elif isinstance(f, Neg) and isinstance(f.sub, Atom):
                m[f.sub.nombre] = False
        return m


# =============================================================================
#  5. ANÁLISIS COMPLETO Y REPORTE
# =============================================================================
@dataclass
class Resultado:
    frases: list[str]
    formulas: list[Formula]
    atomos: dict[str, str]
    arbol: Arbol

    @property
    def consistente(self) -> bool:
        return bool(self.arbol.ramas_abiertas())


def analizar(texto: str) -> Resultado:
    frases = separar_frases(texto)
    if not frases:
        raise ErrorFrase("No se escribió ninguna regla.")
    tr = Traductor()
    formulas = []
    for i, fr in enumerate(frases, 1):
        try:
            formulas.append(tr.traducir(fr))
        except ErrorFrase as e:
            raise ErrorFrase(f"Regla {i} («{fr}»): {e}") from None
    return Resultado(frases, formulas, tr.atomos, Arbol(formulas))


def texto_atomos(res: Resultado) -> list[str]:
    return [f"  {l} = {t}" for l, t in res.atomos.items()]


def texto_formulas(res: Resultado) -> list[str]:
    return [f"  R{i}: {mostrar(f):<22} ←  {fr}"
            for i, (fr, f) in enumerate(zip(res.frases, res.formulas), 1)]


def _etiqueta_nodo(n: Nodo) -> str:
    s = f"[{n.ident}] " + (f"{n.etiqueta}: " if n.etiqueta else "") + mostrar(n.formula)
    if n.paso:
        s += f" ✓{n.paso}"
    if n.origen:
        s += f"   ← [{n.origen}] {n.regla}"
    if n.cerrado:
        s += f"   ✕ contradice [{n.cierre}]"
    elif not n.hijos:
        s += "   ◯ abierta"
    return s


def texto_arbol(res: Resultado) -> list[str]:
    salida: list[str] = []

    def rec(n: Nodo, prefijo: str, es_ultimo: bool, es_raiz: bool) -> None:
        marca = "" if es_raiz else ("└─ " if es_ultimo else "├─ ")
        salida.append(prefijo + marca + _etiqueta_nodo(n))
        sig = prefijo if es_raiz else prefijo + ("   " if es_ultimo else "│  ")
        for i, h in enumerate(n.hijos):
            # un solo hijo: se queda en la misma columna (rama sin bifurcar)
            if len(n.hijos) == 1:
                rec(h, sig, True, False)
            else:
                rec(h, sig, i == len(n.hijos) - 1, False)

    rec(res.arbol.raiz, "  ", True, True)
    if res.arbol.omitidas:
        salida.append(f"  (el tronco se cerró antes: no se usaron {', '.join(res.arbol.omitidas)})")
    return salida


def texto_reporte(res: Resultado) -> list[str]:
    hojas = res.arbol.hojas()
    abiertas = res.arbol.ramas_abiertas()
    out = [f"Ramas: {len(hojas)}  (✕ cerradas: {len(hojas) - len(abiertas)}, "
           f"◯ abiertas: {len(abiertas)})", ""]
    if not abiertas:
        out.append("RESULTADO: todas las ramas se cierran → la base de conocimiento es "
                   "INCONSISTENTE.")
        out.append("No existe ninguna situación en la que todas las reglas sean verdaderas.")
        return out
    out.append("RESULTADO: la base de conocimiento es CONSISTENTE.")
    out.append("Todas las reglas son verdaderas al mismo tiempo cuando:")
    for i, h in enumerate(abiertas, 1):
        m = res.arbol.modelo(h)
        out.append("")
        out.append(f"  Modelo {i}:")
        for letra, texto in res.atomos.items():
            if letra in m:
                out.append(f"     {letra} = {'V' if m[letra] else 'F'}   «{texto}» "
                           f"{'es verdadero' if m[letra] else 'es falso'}")
            else:
                out.append(f"     {letra} = V o F (indistinto)   «{texto}»")
    return out


def reporte_completo(res: Resultado) -> str:
    bloques = ["=== ÁTOMOS ===", *texto_atomos(res), "",
               "=== REGLAS COMO FÓRMULAS ===", *texto_formulas(res), "",
               "=== ÁRBOL SEMÁNTICO (todas las reglas se suponen verdaderas) ===",
               *texto_arbol(res), "",
               "=== REPORTE ===", *texto_reporte(res)]
    return "\n".join(bloques)


# =============================================================================
#  6. DISTRIBUCIÓN DEL ÁRBOL PARA DIBUJARLO
# =============================================================================
def disponer(arbol: Arbol) -> tuple[dict[int, tuple[float, int]], int, int]:
    """Devuelve ({ident: (columna, nivel)}, nº de columnas, nº de niveles)."""
    pos: dict[int, tuple[float, int]] = {}
    siguiente = [0]

    def rec(n: Nodo, nivel: int) -> float:
        if not n.hijos:
            x = float(siguiente[0])
            siguiente[0] += 1
        else:
            xs = [rec(h, nivel + 1) for h in n.hijos]
            x = (xs[0] + xs[-1]) / 2
        pos[n.ident] = (x, nivel)
        return x

    rec(arbol.raiz, 0)
    niveles = max(nivel for _, nivel in pos.values()) + 1
    return pos, siguiente[0], niveles


# =============================================================================
#  7. INTERFAZ GRÁFICA (Tkinter)
# =============================================================================
EJEMPLO = ("Si es de día, entonces voy a trabajar\n"
           "Si llueve, entonces no voy a trabajar\n"
           "Es de día")


def lanzar_gui(texto_inicial: str = "") -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    class App(tk.Tk):
        ANCHO_CHAR, ALTO_CAJA, SEP_NIVEL, MARGEN = 7, 58, 90, 24

        def __init__(self) -> None:
            super().__init__()
            self.title("Sistema experto · Árboles semánticos")
            self.geometry("1100x760")
            self.minsize(800, 520)
            self.resultado: Optional[Resultado] = None
            self._construir_ui()
            if texto_inicial:
                self.entrada.insert("1.0", texto_inicial)
                self.analizar()

        # -- interfaz ------------------------------------------------------------
        def _construir_ui(self) -> None:
            marco = ttk.Frame(self, padding=8)
            marco.pack(fill="both", expand=True)

            ttk.Label(marco, text="Reglas y hechos en español (uno por línea):",
                      font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
            self.entrada = scrolledtext.ScrolledText(marco, height=7, font=("TkDefaultFont", 11))
            self.entrada.pack(fill="x", pady=(2, 6))

            botones = ttk.Frame(marco)
            botones.pack(fill="x", pady=(0, 6))
            for texto, cmd in (("Analizar", self.analizar), ("Cargar ejemplo", self.cargar_ejemplo),
                               ("Abrir archivo…", self.abrir), ("Limpiar", self.limpiar),
                               ("Guardar reporte…", self.guardar)):
                ttk.Button(botones, text=texto, command=cmd).pack(side="left", padx=(0, 6))
            self.estado = ttk.Label(botones, text="", foreground="#555")
            self.estado.pack(side="right")

            self.pestañas = ttk.Notebook(marco)
            self.pestañas.pack(fill="both", expand=True)

            self.txt_atomos = self._pestaña_texto("1. Átomos y fórmulas")
            tab_arbol = ttk.Frame(self.pestañas)
            self.pestañas.add(tab_arbol, text="2. Árbol semántico")
            self.lienzo = tk.Canvas(tab_arbol, bg="white", highlightthickness=0)
            sy = ttk.Scrollbar(tab_arbol, orient="vertical", command=self.lienzo.yview)
            sx = ttk.Scrollbar(tab_arbol, orient="horizontal", command=self.lienzo.xview)
            self.lienzo.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
            sy.pack(side="right", fill="y")
            sx.pack(side="bottom", fill="x")
            self.lienzo.pack(fill="both", expand=True)
            self.lienzo.bind("<ButtonPress-1>", lambda e: self.lienzo.scan_mark(e.x, e.y))
            self.lienzo.bind("<B1-Motion>", lambda e: self.lienzo.scan_dragto(e.x, e.y, gain=1))
            self.txt_reporte = self._pestaña_texto("3. Reporte")

        def _pestaña_texto(self, titulo: str) -> scrolledtext.ScrolledText:
            f = ttk.Frame(self.pestañas)
            self.pestañas.add(f, text=titulo)
            t = scrolledtext.ScrolledText(f, font=("Courier", 11), wrap="none")
            t.pack(fill="both", expand=True)
            return t

        @staticmethod
        def _poner(widget, lineas) -> None:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", "\n".join(lineas))
            widget.configure(state="disabled")

        # -- acciones -------------------------------------------------------------
        def cargar_ejemplo(self) -> None:
            self.limpiar()
            self.entrada.insert("1.0", EJEMPLO)
            self.analizar()

        def limpiar(self) -> None:
            self.entrada.delete("1.0", "end")

        def abrir(self) -> None:
            ruta = filedialog.askopenfilename(filetypes=[("Texto", "*.txt"), ("Todos", "*.*")])
            if ruta:
                with open(ruta, encoding="utf-8") as fh:
                    self.limpiar()
                    self.entrada.insert("1.0", fh.read())
                self.analizar()

        def guardar(self) -> None:
            if not self.resultado:
                messagebox.showinfo("Reporte", "Primero analiza unas reglas.")
                return
            ruta = filedialog.asksaveasfilename(defaultextension=".txt",
                                                filetypes=[("Texto", "*.txt")])
            if ruta:
                with open(ruta, "w", encoding="utf-8") as fh:
                    fh.write(reporte_completo(self.resultado))

        def analizar(self) -> None:
            try:
                self.resultado = analizar(self.entrada.get("1.0", "end"))
            except ErrorFrase as e:
                messagebox.showerror("No pude interpretar el texto", str(e))
                return
            r = self.resultado
            self._poner(self.txt_atomos, ["ÁTOMOS", *texto_atomos(r), "",
                                          "REGLAS COMO FÓRMULAS", *texto_formulas(r)])
            self._poner(self.txt_reporte, texto_reporte(r))
            self.dibujar(r.arbol)
            self.estado.configure(text="Consistente ✓" if r.consistente else "Inconsistente ✕",
                                  foreground="#2e7d32" if r.consistente else "#c62828")
            self.pestañas.select(1)

        # -- dibujo ----------------------------------------------------------------
        def _lineas_caja(self, n: Nodo) -> tuple[list[str], str, str]:
            l1 = f"[{n.ident}] " + (f"{n.etiqueta}: " if n.etiqueta else "") + mostrar(n.formula)
            if n.paso:
                l1 += f"  ✓{n.paso}"
            lineas = [l1]
            if n.origen:
                lineas.append(f"← [{n.origen}] {n.regla}")
            if n.cerrado:
                lineas.append(f"✕ contradice [{n.cierre}]")
                return lineas, "#fde2e2", "#c62828"
            if not n.hijos:
                lineas.append("◯ ABIERTA")
                return lineas, "#dff5e1", "#2e7d32"
            return lineas, "#ffffff", "#777777"

        def dibujar(self, arbol: Arbol) -> None:
            c = self.lienzo
            c.delete("all")
            pos, columnas, niveles = disponer(arbol)
            nodos = {n.ident: n for n in arbol.recorrido()}
            cajas = {i: self._lineas_caja(n) for i, n in nodos.items()}
            ancho_col = max(len(l) for ls, _, _ in cajas.values() for l in ls) \
                * self.ANCHO_CHAR + 30
            ancho_col = max(ancho_col, 170)

            def centro(i: int) -> tuple[float, float]:
                x, nivel = pos[i]
                return (self.MARGEN + (x + 0.5) * ancho_col,
                        self.MARGEN + nivel * self.SEP_NIVEL + self.ALTO_CAJA / 2)

            for i, n in nodos.items():                       # aristas
                x0, y0 = centro(i)
                for h in n.hijos:
                    x1, y1 = centro(h.ident)
                    c.create_line(x0, y0 + self.ALTO_CAJA / 2 - 10,
                                  x1, y1 - self.ALTO_CAJA / 2 + 10, fill="#666", width=1.4)

            for i, (lineas, relleno, borde) in cajas.items():  # nodos
                x, y = centro(i)
                ancho = max(len(l) for l in lineas) * self.ANCHO_CHAR + 18
                alto = 18 * len(lineas) + 10
                c.create_rectangle(x - ancho / 2, y - alto / 2, x + ancho / 2, y + alto / 2,
                                   fill=relleno, outline=borde, width=2)
                c.create_text(x, y, text="\n".join(lineas), justify="center",
                              font=("TkDefaultFont", 10))

            c.configure(scrollregion=(0, 0, columnas * ancho_col + 2 * self.MARGEN,
                                      niveles * self.SEP_NIVEL + 2 * self.MARGEN))

    App().mainloop()


# =============================================================================
#  8. PUNTO DE ENTRADA
# =============================================================================
def leer_consola() -> str:
    print("Escribe una regla o hecho por línea (línea vacía para terminar).")
    lineas = []
    while True:
        try:
            l = input(f"  Regla {len(lineas) + 1}> ")
        except EOFError:
            break
        if not l.strip():
            break
        lineas.append(l)
    return "\n".join(lineas)


def main() -> int:
    ap = argparse.ArgumentParser(description="Sistema experto: reglas en español → árbol semántico")
    ap.add_argument("-a", "--archivo", help="archivo de texto con las reglas")
    ap.add_argument("--demo", action="store_true", help="usa el ejemplo de la clase")
    ap.add_argument("--cli", action="store_true", help="modo consola (sin ventana)")
    args = ap.parse_args()

    texto = ""
    if args.demo:
        texto = EJEMPLO
    elif args.archivo:
        with open(args.archivo, encoding="utf-8") as fh:
            texto = fh.read()

    if not args.cli:
        try:
            lanzar_gui(texto)
            return 0
        except Exception as e:  # sin tkinter o sin pantalla
            print(f"(no se pudo abrir la ventana: {e}; uso el modo consola)\n")

    if not texto:
        texto = leer_consola()
    try:
        print(reporte_completo(analizar(texto)))
    except ErrorFrase as e:
        print(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())