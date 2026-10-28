from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Iterator, Optional, Union

# Importar Tkinter para la aplicación de escritorio
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

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
        self._por_clave: dict[str, str] = {}
        self.atomos: dict[str, str] = {}

    @staticmethod
    def _limpiar(frase: str) -> str:
        t = unicodedata.normalize("NFC", frase).lower().replace("sólo", "solo")
        t = re.sub(r"[¿?¡!\"“”«»().:]", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    def _letra(self, n: int) -> str:
        return LETRAS[n] if n < len(LETRAS) else f"P{n - len(LETRAS) + 1}"

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
        if m := RE_SI_POSPUESTO.search(t):
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
    return [p.strip() for p in re.split(r"[\n;]|\.(?:\s|$)", texto) if p.strip()]


# =============================================================================
#  3. REGLAS DE EXPANSIÓN
# =============================================================================
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
    paso: int = 0
    origen: Optional[int] = None
    regla: str = ""
    cierre: Optional[int] = None

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

    def _siguiente(self) -> Optional[Nodo]:
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
            for hoja in self.hojas_abiertas_bajo(nodo):
                for rama in ramas:
                    self._pegar(hoja, rama, nodo, tipo == "alfa")

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
#  5. ANÁLISIS Y REPORTE
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
    for fr in frases:
        formulas.append(tr.traducir(fr))
    return Resultado(frases, formulas, tr.atomos, Arbol(formulas))


def texto_atomos(res: Resultado) -> list[str]:
    return [f"  {l} = {t}" for l, t in res.atomos.items()]


def texto_formulas(res: Resultado) -> list[str]:
    return [f"  R{i}: {mostrar(f):<22} ←  {fr}"
            for i, (fr, f) in enumerate(zip(res.frases, res.formulas), 1)]


def texto_reporte(res: Resultado) -> list[str]:
    hojas = res.arbol.hojas()
    abiertas = res.arbol.ramas_abiertas()
    out = [f"Ramas: {len(hojas)}  (✕ cerradas: {len(hojas) - len(abiertas)}, "
           f"◯ abiertas: {len(abiertas)})", ""]
    if not abiertas:
        out.append("RESULTADO: todas las ramas se cierran → la base de conocimiento es INCONSISTENTE.")
        return out
    out.append("RESULTADO: la base de conocimiento es CONSISTENTE.")
    out.append("Todas las reglas son verdaderas al mismo tiempo cuando:")
    for i, h in enumerate(abiertas, 1):
        m = res.arbol.modelo(h)
        out.append("")
        out.append(f"  Modelo {i}:")
        for letra, texto in res.atomos.items():
            if letra in m:
                out.append(f"     {letra} = {'V' if m[letra] else 'F'}    «{texto}» "
                           f"{'es verdadero' if m[letra] else 'es falso'}")
            else:
                out.append(f"     {letra} = V o F (indistinto)    «{texto}»")
    return out


def reporte_completo(res: Resultado) -> str:
    bloques = ["=== ÁTOMOS ===", *texto_atomos(res), "",
               "=== REGLAS COMO FÓRMULAS ===", *texto_formulas(res), "",
               "=== REPORTE ===", *texto_reporte(res)]
    return "\n".join(bloques)


# =============================================================================
#  6. DISTRIBUCIÓN DEL ÁRBOL PARA DIBUJAR
# =============================================================================
def disponer(arbol: Arbol) -> tuple[dict[int, tuple[float, int]], int, int]:
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
#  7. INTERFAZ GRÁFICA DE ESCRITORIO (Tkinter)
# =============================================================================
EJEMPLO = ("Si es de día, entonces voy a trabajar\n"
           "Si llueve, entonces no voy a trabajar\n"
           "Es de día")


def lanzar_gui() -> None:
    class App(tk.Tk):
        ANCHO_CHAR, ALTO_CAJA, SEP_NIVEL, MARGEN = 7, 65, 100, 30

        def __init__(self) -> None:
            super().__init__()
            self.title("Simulador de Tableros Semánticos · Visual Studio")
            self.geometry("1150x800")
            self.resultado: Optional[Resultado] = None
            self._construir_ui()
            # Cargar ejemplo por defecto al iniciar
            self.entrada.insert("1.0", EJEMPLO)
            self.analizar()

        def _construir_ui(self) -> None:
            marco = ttk.Frame(self, padding=10)
            marco.pack(fill="both", expand=True)

            ttk.Label(marco, text="Escribe tus reglas o hechos en español (uno por línea o separados por punto):",
                      font=("TkDefaultFont", 10, "bold")).pack(anchor="w")
            
            self.entrada = scrolledtext.ScrolledText(marco, height=6, font=("TkDefaultFont", 11))
            self.entrada.pack(fill="x", pady=(4, 8))

            botones = ttk.Frame(marco)
            botones.pack(fill="x", pady=(0, 8))
            
            ttk.Button(botones, text="Analizar y Dibujar", command=self.analizar).pack(side="left", padx=(0, 6))
            ttk.Button(botones, text="Limpiar / Nueva Frase", command=self.limpiar).pack(side="left", padx=(0, 6))
            ttk.Button(botones, text="Cargar Ejemplo", command=self.cargar_ejemplo).pack(side="left", padx=(0, 6))
            
            self.estado = ttk.Label(botones, text="", font=("TkDefaultFont", 10, "bold"))
            self.estado.pack(side="right")

            self.pestañas = ttk.Notebook(marco)
            self.pestañas.pack(fill="both", expand=True)

            # Pestaña 1: Árbol Visual Interactivo
            tab_arbol = ttk.Frame(self.pestañas)
            self.pestañas.add(tab_arbol, text="1. Árbol Semántico (Gráfico)")
            self.lienzo = tk.Canvas(tab_arbol, bg="white", highlightthickness=0)
            sy = ttk.Scrollbar(tab_arbol, orient="vertical", command=self.lienzo.yview)
            sx = ttk.Scrollbar(tab_arbol, orient="horizontal", command=self.lienzo.xview)
            self.lienzo.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
            sy.pack(side="right", fill="y")
            sx.pack(side="bottom", fill="x")
            self.lienzo.pack(fill="both", expand=True)
            
            # Permitir arrastrar el lienzo con el mouse
            self.lienzo.bind("<ButtonPress-1>", lambda e: self.lienzo.scan_mark(e.x, e.y))
            self.lienzo.bind("<B1-Motion>", lambda e: self.lienzo.scan_dragto(e.x, e.y, gain=1))

            # Pestaña 2: Reporte detallado en texto
            self.txt_reporte = self._pestaña_texto("2. Reporte y Modelos Detallados")

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

        def cargar_ejemplo(self) -> None:
            self.entrada.delete("1.0", "end")
            self.entrada.insert("1.0", EJEMPLO)
            self.analizar()

        def limpiar(self) -> None:
            self.entrada.delete("1.0", "end")
            self.lienzo.delete("all")
            self._poner(self.txt_reporte, ["Escribe tus reglas arriba y presiona 'Analizar y Dibujar'."])
            self.estado.configure(text="")

        def analizar(self) -> None:
            texto = self.entrada.get("1.0", "end")
            try:
                self.resultado = analizar(texto)
            except ErrorFrase as e:
                messagebox.showerror("Error de interpretación", str(e))
                return
            
            r = self.resultado
            self._poner(self.txt_reporte, [reporte_completo(r)])
            self.dibujar_arbol(r.arbol)
            
            if r.consistente:
                self.estado.configure(text="Base CONSISTENTE ✓", foreground="#2e7d32")
            else:
                self.estado.configure(text="Base INCONSISTENTE ✕", foreground="#c62828")
            
            self.pestañas.select(0)

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

        def dibujar_arbol(self, arbol: Arbol) -> None:
            c = self.lienzo
            c.delete("all")
            pos, columnas, niveles = disponer(arbol)
            nodos = {n.ident: n for n in arbol.recorrido()}
            cajas = {i: self._lineas_caja(n) for i, n in nodos.items()}
            
            ancho_col = max(len(l) for ls, _, _ in cajas.values() for l in ls) * self.ANCHO_CHAR + 30
            ancho_col = max(ancho_col, 180)

            def centro(i: int) -> tuple[float, float]:
                x, nivel = pos[i]
                return (self.MARGEN + (x + 0.5) * ancho_col,
                        self.MARGEN + nivel * self.SEP_NIVEL + self.ALTO_CAJA / 2)

            # Dibujar líneas (aristas)
            for i, n in nodos.items():
                x0, y0 = centro(i)
                for h in n.hijos:
                    x1, y1 = centro(h.ident)
                    c.create_line(x0, y0 + self.ALTO_CAJA / 2 - 5,
                                  x1, y1 - self.ALTO_CAJA / 2 + 5, fill="#555", width=1.8)

            # Dibujar cajas de nodos
            for i, (lineas, relleno, borde) in cajas.items():
                x, y = centro(i)
                ancho = max(len(l) for l in lineas) * self.ANCHO_CHAR + 16
                alto = 18 * len(lineas) + 12
                c.create_rectangle(x - ancho / 2, y - alto / 2, x + ancho / 2, y + alto / 2,
                                   fill=relleno, outline=borde, width=2)
                c.create_text(x, y, text="\n".join(lineas), justify="center",
                              font=("TkDefaultFont", 10, "bold"))

            c.configure(scrollregion=(0, 0, columnas * ancho_col + 2 * self.MARGEN,
                                     niveles * self.SEP_NIVEL + 2 * self.MARGEN))

    App().mainloop()


def main() -> int:
    ap = argparse.ArgumentParser(description="Simulador de Tableros Semánticos")
    ap.add_argument("--cli", action="store_true", help="Ejecutar en modo consola de texto")
    args = ap.parse_args()

    if args.cli:
        print("Modo consola activo. Escribe tus reglas (Enter vacío para terminar):")
        lineas = []
        while True:
            try:
                l = input(f"  Regla {len(lineas) + 1}> ")
            except EOFError:
                break
            if not l.strip():
                break
            lineas.append(l)
        try:
            print(reporte_completo(analizar("\n".join(lineas))))
        except ErrorFrase as e:
            print(f"Error: {e}")
            return 1
        return 0

    # Por defecto abre la aplicación gráfica de escritorio
    try:
        lanzar_gui()
    except Exception as e:
        print(f"No se pudo abrir la interfaz gráfica: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())