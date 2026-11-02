import re
import time
import unicodedata
from datetime import timedelta
from django.utils import timezone
from .models import CambioDisponibilidad

MICRO_MIN = 15                    # cortes de menos de 15 min = micro cortes
HORA_INICIO, HORA_FIN = 7, 19     # horario escolar (hora local), lunes a viernes
RUIDO_BUSQUEDA = {"n", "nro", "nr", "num", "numero"}
_cache_indice = {"hasta": 0, "datos": []}

def norm(v):
    v = str(v or "").strip()
    return v[:-2] if v.endswith(".0") else v


def tipo_enlace(valor):
    """Agrupa las variantes del campo Escuela.internet en una categoría."""
    v = (unicodedata.normalize("NFKD", str(valor or ""))
         .encode("ascii", "ignore").decode().lower().strip())
    if v in ("", "nan", "nd", "none"):
        return "Sin dato"
    if "motoriz" in v:
        return "Starlink Motorizada"
    if "mini" in v:
        return "Starlink Mini SPS" if "sps" in v else "Starlink Mini"
    if "starlink" in v:
        return "Starlink"
    if "standar" in v:
        m = re.search(r"v\s?(\d)", v)
        return f"Standard V{m.group(1)}" if m else "Standard"
    primera = v.split()[0]
    if primera in ("fo", "re", "cm"):
        return primera.upper()
    return "Otro"


def resumen_cortes(dias=7):
    """Por predio: cortes, micro cortes, caídas largas, cortes en horario
    escolar, minutos sin servicio y fecha del último corte."""
    ahora = timezone.now()
    desde = ahora - timedelta(days=dias)
    res = {}

    def reg(p):
        return res.setdefault(p, {"cortes": 0, "micro": 0, "largos": 0,
                                  "escolares": 0, "minutos": 0.0, "ultimo": None})

    def cerrar(p, inicio, fin):
        r = reg(p)
        dur = (fin - inicio).total_seconds() / 60
        r["cortes"] += 1
        r["minutos"] += dur
        r["micro" if dur < MICRO_MIN else "largos"] += 1
        loc = timezone.localtime(inicio)
        if loc.weekday() < 5 and HORA_INICIO <= loc.hour < HORA_FIN:
            r["escolares"] += 1
        if r["ultimo"] is None or inicio > r["ultimo"]:
            r["ultimo"] = inicio

    por_serial = {}
    for c in CambioDisponibilidad.objects.filter(ts__gte=desde).order_by("ts"):
        por_serial.setdefault(c.serial, []).append(c)

    for evs in por_serial.values():
        inicio = None
        for c in evs:
            if c.estado_nuevo == "offline":
                if inicio is None:
                    inicio = c.ts
            elif inicio is not None:
                cerrar(c.predio, inicio, c.ts)
                inicio = None
            elif c.estado_anterior == "offline":
                # el corte había empezado antes de la ventana: solo suma minutos
                reg(c.predio)["minutos"] += (c.ts - desde).total_seconds() / 60
        if inicio is not None:                      # sigue caído ahora
            cerrar(evs[-1].predio, inicio, ahora)
    return res
def tokens_busqueda(texto):
    """Texto -> lista de palabras en minúscula y sin acentos.
    Unifica N°, Nº, N.º, Nro y separa letras de números (N3 -> 3)."""
    t = re.sub(r"[º°ª˚]", " ", str(texto or "").lower())
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", t)
    return [p for p in re.findall(r"[a-z0-9]+", t) if p not in RUIDO_BUSQUEDA]


def _indice():
    """Escuelas ya normalizadas. Se recalcula cada 5 minutos."""
    if time.time() > _cache_indice["hasta"]:
        from .models import Escuela
        datos = []
        for id_, cue, nombre, loc, dpto, predio, pfinal, unif in Escuela.objects.values_list(
                "id", "cue", "escuelas", "localidad", "departamento",
                "predio", "predio_final", "unificar"):
            datos.append((
                id_,
                nombre or "",
                tokens_busqueda(nombre),
                tokens_busqueda(f"{loc} {dpto}"),
                tokens_busqueda(f"{norm(cue)} {norm(predio)} {norm(pfinal)} {norm(unif)}"),
            ))
        _cache_indice["datos"] = datos
        _cache_indice["hasta"] = time.time() + 300
    return _cache_indice["datos"]


def _coincide(tok, palabras):
    if tok.isdigit() and len(tok) < 4:
        return tok in palabras                          # número corto: palabra exacta
    return any(p.startswith(tok) for p in palabras)     # texto o número largo: comienzo


def buscar_ids(q, estado=""):
    """IDs de las escuelas que cumplen la búsqueda, de más a menos relevante.
    Devuelve None si lo escrito no tiene palabras útiles."""
    toks = tokens_busqueda(q)
    if not toks:
        return None
    frase = f" {' '.join(toks)} "
    validos = None
    if estado:
        from .models import Escuela
        validos = set(Escuela.objects.filter(estado=estado).values_list("id", flat=True))

    res = []
    for id_, nombre, n, l, c in _indice():
        if validos is not None and id_ not in validos:
            continue
        puntos = 0
        for t in toks:
            if _coincide(t, n):
                puntos += 10
            elif _coincide(t, c):
                puntos += 6
            elif _coincide(t, l):
                puntos += 3
            else:
                break
        else:
            if frase in f" {' '.join(n)} ":
                puntos += 30                      # las palabras juntas y en orden
            if len(toks) == 1 and toks[0] in c:
                puntos += 100                     # CUE o predio exacto
            res.append((-puntos, nombre, id_))
    res.sort()
    return [r[2] for r in res]
