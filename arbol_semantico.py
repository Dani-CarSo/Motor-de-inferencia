import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, ttk

from motor_inferencia import Nodo, Parser, Tableau, fstr, hojas, es_lit

CONECTORES = {"a": "Atómica", "n": "Negación", "and": "Conjunción",
              "or": "Disyunción", "imp": "Condicional", "iff": "Bicondicional"}
AZUL, ROJO, VERDE, GRIS = "#4b5fd6", "#c62828", "#1b8a4b", "#777777"


def ocurrencias(f, dentro=False, acc=None):
    """Lista (letra, nº de negaciones directas, dentro_de_negación_mayor) en orden de aparición."""
    acc = [] if acc is None else acc
    if f[0] == "a":
        acc.append((f[1], 0, dentro))
    elif f[0] == "n":
        k, g = 0, f
        while g[0] == "n":
            k, g = k + 1, g[1]
        if g[0] == "a":
            acc.append((g[1], k, dentro))
        else:
            ocurrencias(g, True, acc)
    else:
        ocurrencias(f[1], dentro, acc)
        ocurrencias(f[2], dentro, acc)
    return acc


def estado(letra, k):
    if k == 0:
        return "afirmada"
    if k % 2 == 1:
        return f"NEGADA ({'¬' * k}{letra})" if k == 1 else f"NEGADA, {k} negaciones ({'¬' * k}{letra})"
    return f"doble negación ({'¬' * k}{letra}), equivale a afirmada"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Motor de inferencia · Árboles semánticos")
        self.geometry("1320x780")
        self.minsize(960, 600)
        self.textos, self.reglas, self.P = [], [], Parser()
        self.raiz, self.escala = None, 1.0
        self._interfaz()

    # ------------------------------------------------------------ interfaz
    def _interfaz(self):
        panel = ttk.PanedWindow(self, orient="horizontal")
        panel.pack(fill="both", expand=True)
        izq, der = ttk.Frame(panel, padding=8), ttk.Frame(panel)
        panel.add(izq, weight=0)
        panel.add(der, weight=1)

        ttk.Label(izq, text="Escribe reglas y hechos en español (uno por línea):",
                  font=("Helvetica", 10, "bold")).pack(anchor="w")
        self.entrada = tk.Text(izq, height=5, width=48, wrap="word", font=("Helvetica", 11))
        self.entrada.pack(fill="x", pady=4)
        self.entrada.bind("<Control-Return>", lambda e: (self.agregar(), "break")[1])
        fila = ttk.Frame(izq)
        fila.pack(fill="x")
        ttk.Button(fila, text="➕ Agregar (Ctrl+Enter)", command=self.agregar).pack(side="left")
        ttk.Button(fila, text="Limpiar todo", command=self.limpiar).pack(side="left", padx=6)

        ttk.Label(izq, text="Reglas y fórmulas", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.tr = ttk.Treeview(izq, columns=("id", "conector", "formula", "texto"), show="headings", height=7)
        for c, t, w in (("id", "ID", 34), ("conector", "Conector", 88), ("formula", "Fórmula", 110), ("texto", "Texto original", 170)):
            self.tr.heading(c, text=t)
            self.tr.column(c, width=w, anchor="w")
        self.tr.pack(fill="x")
        ttk.Button(izq, text="Quitar regla seleccionada", command=self.quitar).pack(anchor="w", pady=3)

        ttk.Label(izq, text="Tabla de átomos", font=("Helvetica", 10, "bold")).pack(anchor="w", pady=(6, 0))
        self.ta = ttk.Treeview(izq, columns=("l", "s"), show="headings", height=5)
        self.ta.heading("l", text="Letra")
        self.ta.heading("s", text="Significado")
        self.ta.column("l", width=50)
        self.ta.column("s", width=340)
        self.ta.pack(fill="x")

        ttk.Button(izq, text="🌳  Construir grafo (árbol semántico)",
                   command=self.construir).pack(fill="x", pady=10, ipady=6)
        self.res = tk.Text(izq, height=9, wrap="word", state="disabled", font=("Helvetica", 10))
        self.res.tag_configure("ok", foreground=VERDE)
        self.res.tag_configure("mal", foreground=ROJO)
        self.res.tag_configure("b", font=("Helvetica", 10, "bold"))
        self.res.pack(fill="both", expand=True)

        self.nb = ttk.Notebook(der)
        self.nb.pack(fill="both", expand=True)
        tab_grafo, tab_an = ttk.Frame(self.nb), ttk.Frame(self.nb)
        self.nb.add(tab_grafo, text="🌳 Grafo")
        self.nb.add(tab_an, text="📋 Análisis de cada regla")
        self.an = tk.Text(tab_an, wrap="word", state="disabled", font=("Helvetica", 11), padx=10, pady=8)
        san = ttk.Scrollbar(tab_an, command=self.an.yview)
        self.an.configure(yscrollcommand=san.set)
        san.pack(side="right", fill="y")
        self.an.pack(fill="both", expand=True)
        self.an.tag_configure("t", font=("Helvetica", 12, "bold"), foreground=AZUL, spacing1=10)
        self.an.tag_configure("neg", foreground=ROJO, font=("Helvetica", 11, "bold"))
        self.an.tag_configure("afi", foreground=VERDE, font=("Helvetica", 11, "bold"))
        self.an.tag_configure("g", foreground=GRIS)
        self.an.tag_configure("av", foreground="#b26a00", font=("Helvetica", 11, "bold"))
        barra = ttk.Frame(tab_grafo, padding=4)
        barra.pack(fill="x")
        for t, f in (("🔍+", 1.2), ("🔍−", 1 / 1.2)):
            ttk.Button(barra, text=t, width=5, command=lambda f=f: self.zoom(f)).pack(side="left")
        ttk.Button(barra, text="100%", width=5, command=lambda: self.zoom(None)).pack(side="left", padx=2)
        tk.Label(barra, text="  ▭ fórmula", fg=AZUL).pack(side="left")
        tk.Label(barra, text="  ✕ rama cerrada", fg=ROJO).pack(side="left")
        tk.Label(barra, text="  ○ rama abierta", fg=VERDE).pack(side="left")
        tk.Label(barra, text="  ✓ ya desarrollada   (arrastra para mover)", fg=GRIS).pack(side="left")

        marco = ttk.Frame(tab_grafo)
        marco.pack(fill="both", expand=True)
        self.lienzo = tk.Canvas(marco, bg="white", highlightthickness=0)
        sy = ttk.Scrollbar(marco, orient="vertical", command=self.lienzo.yview)
        sx = ttk.Scrollbar(marco, orient="horizontal", command=self.lienzo.xview)
        self.lienzo.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")
        self.lienzo.pack(fill="both", expand=True)
        self.lienzo.bind("<ButtonPress-1>", lambda e: self.lienzo.scan_mark(e.x, e.y))
        self.lienzo.bind("<B1-Motion>", lambda e: self.lienzo.scan_dragto(e.x, e.y, gain=1))
        self.lienzo.bind("<MouseWheel>", lambda e: self.lienzo.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.lienzo.bind("<Button-4>", lambda e: self.lienzo.yview_scroll(-1, "units"))
        self.lienzo.bind("<Button-5>", lambda e: self.lienzo.yview_scroll(1, "units"))
        self.mensaje("Escribe tus reglas arriba y pulsa «Agregar».")

    # ------------------------------------------------------------ base de conocimiento
    def reconstruir(self, textos):
        P = Parser()
        reglas = [(t, P.parse(t)) for t in textos]
        self.textos, self.reglas, self.P = list(textos), reglas, P
        self.tr.delete(*self.tr.get_children())
        for i, (t, f) in enumerate(reglas, 1):
            self.tr.insert("", "end", values=(f"R{i}", CONECTORES[f[0]], fstr(f), t))
        self.ta.delete(*self.ta.get_children())
        for letra, txt in P.atomos:
            self.ta.insert("", "end", values=(letra, txt))
        self.raiz = None
        self.lienzo.delete("all")
        self.actualizar_analisis()

    def actualizar_analisis(self):
        w = self.an
        w.configure(state="normal")
        w.delete("1.0", "end")
        if not self.reglas:
            w.insert("end", "Aún no hay reglas. Escríbelas a la izquierda y pulsa «Agregar».", "g")
        occ = [ocurrencias(f) for _, f in self.reglas]
        textos = dict(self.P.atomos)
        for i, (t, f) in enumerate(self.reglas):
            w.insert("end", f"R{i + 1} · {CONECTORES[f[0]]} · {fstr(f)}\n", "t")
            w.insert("end", f"Texto original: {t}\n", "g")
            idem = [j + 1 for j, (_, g) in enumerate(self.reglas) if j != i and g == f]
            if idem:
                w.insert("end", "⚠ ATENCIÓN: la fórmula es IDÉNTICA a la regla " +
                         ", ".join(f"R{j}" for j in idem) + "\n", "av")
            for n, (letra, k, dentro) in enumerate(occ[i], 1):
                w.insert("end", f"  P{n}: «{textos[letra]}» → {letra}  ")
                w.insert("end", estado(letra, k) + "\n", "afi" if k % 2 == 0 else "neg")
                if dentro:
                    w.insert("end", "      (está dentro de una negación sobre una fórmula compuesta)\n", "g")
                otras = []
                for j, lista in enumerate(occ):
                    if j == i:
                        continue
                    for (l2, k2, _) in lista:
                        if l2 == letra:
                            igual = (k2 % 2) == (k % 2)
                            otras.append((j + 1, igual, k2))
                            break
                if not otras:
                    w.insert("end", "      · aparece solo en esta regla\n", "g")
                for j, igual, k2 in otras:
                    if igual:
                        w.insert("end", f"      = igual a la proposición de R{j} ({estado(letra, k2)})\n", "g")
                    else:
                        w.insert("end", f"      ~ mismo enunciado que en R{j}, pero con NEGACIÓN OPUESTA ({estado(letra, k2)})\n", "av")
        w.configure(state="disabled")

    def agregar(self):
        lineas = [l.strip() for l in self.entrada.get("1.0", "end").splitlines() if l.strip()]
        if not lineas:
            return
        anteriores = list(self.textos)
        try:
            self.reconstruir(anteriores + lineas)
        except Exception as err:
            self.reconstruir(anteriores)
            messagebox.showerror("No pude interpretar el texto", str(err))
            return
        self.entrada.delete("1.0", "end")
        n = len(anteriores)
        info = [f"R{n + i}: {fstr(self.reglas[n + i - 1][1])}" for i in range(1, len(lineas) + 1)]
        self.mensaje("Agregadas:\n" + "\n".join(info))
        self.nb.select(1)

    def quitar(self):
        sel = self.tr.selection()
        if not sel:
            return
        i = self.tr.index(sel[0])
        self.reconstruir(self.textos[:i] + self.textos[i + 1:])
        self.mensaje(f"Regla R{i + 1} eliminada; se renumeraron átomos y reglas.")

    def limpiar(self):
        self.reconstruir([])
        self.mensaje("Base de conocimiento vacía.")

    def mensaje(self, txt, tag=None):
        self.res.configure(state="normal")
        self.res.delete("1.0", "end")
        self.res.insert("end", txt, tag or ())
        self.res.configure(state="disabled")

    # ------------------------------------------------------------ árbol semántico
    def construir(self):
        if not self.reglas:
            messagebox.showinfo("Sin reglas", "Primero agrega al menos una regla o hecho.")
            return
        T, raiz, pend, lits = Tableau(), Nodo(), [], {}
        for i, (_, f) in enumerate(self.reglas, 1):
            T.agregar(raiz, f, f"R{i}", pend, lits)
        T.correr(raiz, pend, lits)
        self.raiz, self.escala = raiz, 1.0
        self.nb.select(0)
        self.update_idletasks()
        self.dibujar()
        self.resultado(raiz)

    def resultado(self, raiz):
        hs = hojas(raiz)
        abiertas = [h for h in hs if h.abierta is not None]
        self.res.configure(state="normal")
        self.res.delete("1.0", "end")
        self.res.insert("end", f"Ramas cerradas: {len(hs) - len(abiertas)} · abiertas: {len(abiertas)}\n\n", "b")
        if not abiertas:
            self.res.insert("end", "Todas las ramas se cierran: la base de conocimiento es "
                                   "INSATISFACIBLE (inconsistente).", "mal")
        else:
            self.res.insert("end", "Base satisfacible. Condiciones en que todas las reglas se cumplen:\n", "ok")
            for h in abiertas:
                asign, libres = [], []
                for letra, _ in self.P.atomos:
                    if letra in h.abierta:
                        asign.append(f"{letra} = V")
                    elif "¬" + letra in h.abierta:
                        asign.append(f"{letra} = F")
                    else:
                        libres.append(letra)
                extra = f"   ({', '.join(libres)}: cualquier valor)" if libres else ""
                self.res.insert("end", f"  ({', '.join(asign)}){extra}\n", "b")
        self.res.configure(state="disabled")

    def zoom(self, f):
        self.escala = 1.0 if f is None else max(0.4, min(2.5, self.escala * f))
        if self.raiz:
            self.dibujar()

    # ------------------------------------------------------------ dibujo del grafo
    def texto(self, e):
        return f"{e['id']}. {fstr(e['f'])}{'  ✓' if e['ap'] else ''}   [{e['src']}]"

    def medir(self, n):
        s = self.escala
        n.anchos = [self.fuente.measure(self.texto(e)) + int(28 * s) for e in n.items]
        n.marca = None
        if n.cerrada:
            n.marca = (n.motivo.split(" (")[0], "c")
        elif n.abierta is not None:
            n.marca = ("○  rama abierta", "o")
        mw = self.fuente.measure(n.marca[0]) + int(28 * s) if n.marca else 0
        n.propio = max(n.anchos + [mw])
        for k in n.hijos:
            self.medir(k)
        hijos = sum(k.total for k in n.hijos) + self.sep * max(0, len(n.hijos) - 1)
        n.total = max(n.propio, hijos)

    def dibujar(self):
        s = self.escala
        self.fuente = tkfont.Font(family="Helvetica", size=max(6, int(11 * s)))
        self.alto, self.hueco, self.sep = int(34 * s), int(26 * s), int(24 * s)
        self.lienzo.delete("all")
        self.medir(self.raiz)
        self._nodo(self.raiz, self.raiz.total / 2 + 40, 30, None)
        x0, y0, x1, y1 = self.lienzo.bbox("all")
        self.lienzo.configure(scrollregion=(x0 - 30, y0 - 30, x1 + 30, y1 + 30))
        self.lienzo.xview_moveto(0)
        self.lienzo.yview_moveto(0)

    def _flecha(self, a, b):
        self.lienzo.create_line(a[0], a[1], b[0], b[1], arrow="last", fill=GRIS, width=2)

    def _caja(self, cx, y, w, txt, relleno, borde, color):
        self.lienzo.create_rectangle(cx - w / 2, y, cx + w / 2, y + self.alto,
                                     fill=relleno, outline=borde, width=2)
        self.lienzo.create_text(cx, y + self.alto / 2, text=txt, font=self.fuente, fill=color)

    def _nodo(self, n, cx, y, desde):
        previo = desde
        for e, w in zip(n.items, n.anchos):
            if previo:
                self._flecha(previo, (cx, y))
            lit = es_lit(e["f"])
            self._caja(cx, y, w, self.texto(e), "#ffffff" if lit else "#eef2ff", AZUL, "#111111")
            previo = (cx, y + self.alto)
            y += self.alto + self.hueco
        if n.marca:
            txt, tipo = n.marca
            w = self.fuente.measure(txt) + int(28 * self.escala)
            self._flecha(previo, (cx, y))
            if tipo == "c":
                self._caja(cx, y, w, txt, "#fde8e6", ROJO, ROJO)
            else:
                self._caja(cx, y, w, txt, "#e3f4ea", VERDE, VERDE)
            return
        total = sum(k.total for k in n.hijos) + self.sep * (len(n.hijos) - 1)
        x = cx - total / 2
        for k in n.hijos:
            self._nodo(k, x + k.total / 2, y, previo)
            x += k.total + self.sep


if __name__ == "__main__":
    App().mainloop()