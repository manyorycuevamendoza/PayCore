"""Genera los gráficos del informe a partir de los CSV reales de Locust.

No hay ni un número escrito a mano: todo sale de performance/results/. Si una
carrera no existe, su barra no se dibuja, en lugar de inventarla.

Uso:
    ./.venv/bin/python performance/graficos.py
"""

from __future__ import annotations

import csv
import pathlib
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

RAIZ = pathlib.Path(__file__).parent
RESULTADOS = RAIZ / "results"
DESTINO = RAIZ.parent / "docs" / "diagrams"

# Paleta sobria y distinguible también en escala de grises.
COLOR_PESIMISTA = "#0f6d63"
COLOR_SERIALIZABLE = "#b5651d"
COLOR_NEUTRO = "#5a6b78"


# Cuentas que crea performance/seed_perf.py: 50 de carga más la caliente.
# Cada una recibe su saldo con una transferencia desde SYSTEM_FUNDING, así que
# esas no son trabajo de la prueba y se descuentan.
TRANSFERENCIAS_DE_PREPARACION = 51
DURACION_S = 60


@dataclass
class Carrera:
    etiqueta: str
    peticiones: int
    fallos: int
    rps: float
    p50: float
    p95: float
    p99: float
    maximo: float

    confirmadas: int = 0

    @property
    def tasa_fallo(self) -> float:
        return 100.0 * self.fallos / self.peticiones if self.peticiones else 0.0

    @property
    def confirmadas_por_segundo(self) -> float:
        """Transferencias realmente escritas en el ledger, por segundo.

        No es lo mismo que peticiones por segundo. Esta cifra sale de contar
        filas en PostgreSQL al terminar la carrera, no de lo que respondió la
        API. Es la diferencia entre medir el servicio y comprobar el dinero.
        """
        return max(0, self.confirmadas - TRANSFERENCIAS_DE_PREPARACION) / DURACION_S


def _a_float(valor: str) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def leer_confirmadas(directorio: str) -> int:
    """Transferencias completadas según PostgreSQL, no según la API."""
    ruta = RESULTADOS / directorio / "reconciliacion.txt"
    if not ruta.exists():
        return 0
    for linea in ruta.read_text().splitlines():
        campos = [c.strip() for c in linea.split("|")]
        if len(campos) == 6 and campos[0].lstrip("-").isdigit():
            return int(campos[3])
    return 0


def leer(directorio: str, fila: str = "POST /transfers") -> Carrera | None:
    ruta = RESULTADOS / directorio / "locust_stats.csv"
    if not ruta.exists():
        print(f"  (falta {directorio}, se omite)")
        return None
    with ruta.open(newline="") as fichero:
        for registro in csv.DictReader(fichero):
            if registro["Name"] == fila:
                return Carrera(
                    etiqueta=directorio,
                    peticiones=int(registro["Request Count"]),
                    fallos=int(registro["Failure Count"]),
                    rps=_a_float(registro["Requests/s"]),
                    p50=_a_float(registro["50%"]),
                    p95=_a_float(registro["95%"]),
                    p99=_a_float(registro["99%"]),
                    maximo=_a_float(registro["Max Response Time"]),
                    confirmadas=leer_confirmadas(directorio),
                )
    print(f"  (en {directorio} no hay fila '{fila}', se omite)")
    return None


def _estilo(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)


def grafico_estrategias() -> None:
    """Pesimista frente a SERIALIZABLE en los dos escenarios de escritura."""
    escenarios = ["caliente", "mixto"]
    nombres = {
        "caliente": "Contención máxima\n(una sola cuenta de origen)",
        "mixto": "Contención baja\n(50 cuentas al azar)",
    }

    datos = {
        (esc, est): leer(f"{esc}-{est}-100u-60s")
        for esc in escenarios
        for est in ("pessimistic", "serializable")
    }
    if any(v is None for v in datos.values()):
        print("  faltan carreras, no se dibuja grafico_estrategias")
        return

    figura, ejes = plt.subplots(1, 4, figsize=(16, 4.4))
    posiciones = range(len(escenarios))
    ancho = 0.36

    paneles = [
        ("Peticiones por segundo\n(lo que responde la API)",
         lambda c: c.rps, "req/s"),
        ("Transferencias confirmadas\npor segundo (contadas en la BD)",
         lambda c: c.confirmadas_por_segundo, "transf/s"),
        ("Latencia p99", lambda c: c.p99, "ms"),
        ("Tasa de fallo", lambda c: c.tasa_fallo, "%"),
    ]

    for ax, (titulo, extraer, unidad) in zip(ejes, paneles, strict=True):
        pes = [extraer(datos[(e, "pessimistic")]) for e in escenarios]
        ser = [extraer(datos[(e, "serializable")]) for e in escenarios]
        b1 = ax.bar([p - ancho / 2 for p in posiciones], pes, ancho,
                    label="pessimistic", color=COLOR_PESIMISTA)
        b2 = ax.bar([p + ancho / 2 for p in posiciones], ser, ancho,
                    label="serializable", color=COLOR_SERIALIZABLE)
        for barras in (b1, b2):
            ax.bar_label(barras, fmt="%.1f", fontsize=8, padding=2)
        ax.set_title(titulo, fontsize=10)
        ax.set_ylabel(unidad, fontsize=9)
        ax.set_xticks(list(posiciones))
        ax.set_xticklabels([nombres[e] for e in escenarios], fontsize=8)
        ax.margins(y=0.18)
        _estilo(ax)

    ejes[0].legend(fontsize=9, frameon=False)
    figura.suptitle(
        "PayCore. Estrategias de concurrencia, 100 usuarios durante 60 s "
        "(POST /transfers)",
        fontsize=12,
    )
    figura.tight_layout()
    figura.savefig(DESTINO / "rendimiento-estrategias.png", dpi=150)
    plt.close(figura)
    print("  rendimiento-estrategias.png")


def grafico_optimizacion() -> None:
    """Antes y después de acotar la sesión al cuerpo del endpoint."""
    antes = leer(
        "antes-de-alinear-el-pool/lectura-pessimistic-100u-60s",
        "GET /accounts/me/balance",
    )
    despues = leer(
        "lectura-pessimistic-100u-60s", "GET /accounts/me/balance"
    )
    if antes is None or despues is None:
        print("  faltan carreras, no se dibuja grafico_optimizacion")
        return

    figura, ejes = plt.subplots(1, 3, figsize=(12, 4))
    paneles = [
        ("Peticiones por segundo", [antes.rps, despues.rps], "req/s", "%.1f"),
        ("Latencia p99", [antes.p99, despues.p99], "ms", "%.0f"),
        ("Tasa de fallo", [antes.tasa_fallo, despues.tasa_fallo], "%", "%.2f"),
    ]

    for ax, (titulo, valores, unidad, formato) in zip(ejes, paneles, strict=True):
        barras = ax.bar(
            ["antes", "después"], valores, 0.5,
            color=[COLOR_NEUTRO, COLOR_PESIMISTA],
        )
        ax.bar_label(barras, fmt=formato, fontsize=9, padding=2)
        ax.set_title(titulo, fontsize=10)
        ax.set_ylabel(unidad, fontsize=9)
        ax.margins(y=0.2)
        _estilo(ax)

    figura.suptitle(
        "PayCore. Efecto de acotar la sesión de base de datos al cuerpo del "
        "endpoint\nCarga idéntica: solo lectura, 100 usuarios durante 60 s "
        "(GET /accounts/me/balance)",
        fontsize=11,
    )
    figura.tight_layout()
    figura.savefig(DESTINO / "rendimiento-optimizacion.png", dpi=150)
    plt.close(figura)
    print("  rendimiento-optimizacion.png")


def grafico_serie_temporal() -> None:
    """Evolución durante la carrera, para ver si el sistema se estabiliza."""
    carreras = [
        ("caliente-pessimistic-100u-60s", "pessimistic", COLOR_PESIMISTA),
        ("caliente-serializable-100u-60s", "serializable", COLOR_SERIALIZABLE),
    ]

    figura, (ax_rps, ax_lat) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    dibujado = False

    for directorio, etiqueta, color in carreras:
        ruta = RESULTADOS / directorio / "locust_stats_history.csv"
        if not ruta.exists():
            continue
        segundos: list[float] = []
        rps: list[float] = []
        p95: list[float] = []
        inicio: float | None = None
        with ruta.open(newline="") as fichero:
            for fila in csv.DictReader(fichero):
                if fila["Name"] != "Aggregated":
                    continue
                marca = _a_float(fila["Timestamp"])
                if inicio is None:
                    inicio = marca
                segundos.append(marca - inicio)
                rps.append(_a_float(fila["Requests/s"]))
                p95.append(_a_float(fila["95%"]))
        if not segundos:
            continue
        ax_rps.plot(segundos, rps, label=etiqueta, color=color, linewidth=1.8)
        ax_lat.plot(segundos, p95, label=etiqueta, color=color, linewidth=1.8)
        dibujado = True

    if not dibujado:
        print("  sin historial, no se dibuja grafico_serie_temporal")
        plt.close(figura)
        return

    ax_rps.set_ylabel("peticiones/s", fontsize=9)
    ax_rps.set_title(
        "Escenario de contención máxima: evolución durante la carrera",
        fontsize=12,
    )
    ax_rps.legend(fontsize=9, frameon=False)
    ax_lat.set_ylabel("p95 (ms)", fontsize=9)
    ax_lat.set_xlabel("segundos desde el inicio", fontsize=9)
    for ax in (ax_rps, ax_lat):
        _estilo(ax)

    figura.tight_layout()
    figura.savefig(DESTINO / "rendimiento-serie-temporal.png", dpi=150)
    plt.close(figura)
    print("  rendimiento-serie-temporal.png")


def tabla_markdown() -> str:
    """Tabla de resultados lista para pegar, generada desde los CSV."""
    filas = [
        ("Solo lectura", "lectura-pessimistic-100u-60s", "GET /accounts/me/balance", "pessimistic"),
        ("Contención baja", "mixto-pessimistic-100u-60s", "POST /transfers", "pessimistic"),
        ("Contención baja", "mixto-serializable-100u-60s", "POST /transfers", "serializable"),
        ("Contención máxima", "caliente-pessimistic-100u-60s", "POST /transfers", "pessimistic"),
        ("Contención máxima", "caliente-serializable-100u-60s", "POST /transfers", "serializable"),
    ]
    lineas = [
        "| Escenario | Estrategia | Peticiones | req/s | transf. confirmadas/s | p50 | p95 | p99 | Máx. | Fallos |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for nombre, directorio, fila, estrategia in filas:
        carrera = leer(directorio, fila)
        if carrera is None:
            continue
        confirmadas = (
            "n/a"
            if fila != "POST /transfers"
            else f"{carrera.confirmadas_por_segundo:.1f}"
        )
        lineas.append(
            f"| {nombre} | `{estrategia}` | {carrera.peticiones} | "
            f"{carrera.rps:.1f} | {confirmadas} | "
            f"{carrera.p50:.0f} ms | {carrera.p95:.0f} ms | "
            f"{carrera.p99:.0f} ms | {carrera.maximo:.0f} ms | "
            f"{carrera.tasa_fallo:.2f} % |"
        )
    return "\n".join(lineas)


def main() -> int:
    DESTINO.mkdir(parents=True, exist_ok=True)
    print("Gráficos generados en docs/diagrams/:")
    grafico_estrategias()
    grafico_optimizacion()
    grafico_serie_temporal()
    print("\nTabla de resultados (generada desde los CSV):\n")
    print(tabla_markdown())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
