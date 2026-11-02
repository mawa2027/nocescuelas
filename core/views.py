from django.shortcuts import render, get_object_or_404, redirect
from .models import Escuela, Incidencia, Derivacion, EstadoConectividad
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.db.models import Count, Q, Avg, F, ExpressionWrapper, DurationField, Case, When, Value, IntegerField, Max
from django.db.models.functions import TruncMonth

from django.core.mail import send_mail
from django.utils.timezone import now
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator

from datetime import timedelta
from .utils import norm, resumen_cortes, tipo_enlace, buscar_ids

import uuid


# ===============================
# LISTA DE ESCUELAS (LIMPIO)
# ===============================
from django.db.models import Q
import unicodedata

def normalizar(texto):
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto.lower())
        if unicodedata.category(c) != 'Mn'
    )
def lista_escuelas_old(request):

    q = request.GET.get("q", "").strip()

    # métricas
    total_escuelas = Escuela.objects.count()

    tickets_activos = Incidencia.objects.exclude(
        estado="CERRADO"
    ).count()

    tickets_abiertos = Incidencia.objects.filter(
        estado="ABIERTO"
    ).count()

    tickets_derivados = Incidencia.objects.filter(
        estado="DERIVADA"
    ).count()

    escuelas = Escuela.objects.all()

    if q:

        escuelas = escuelas.annotate(

            prioridad=Case(

                # CUE exacto
                When(cue__iexact=q, then=Value(1)),

                # nombre escuela
                When(escuelas__icontains=q, then=Value(2)),

                # localidad
                When(localidad__icontains=q, then=Value(3)),

                # departamento
                When(departamento__icontains=q, then=Value(4)),

                # predio
                When(predio__icontains=q, then=Value(5)),

                # predio final
                When(predio_final__icontains=q, then=Value(6)),

                default=Value(10),
                output_field=IntegerField(),
            )

        ).filter(

            Q(cue__icontains=q) |
            Q(escuelas__icontains=q) |
            Q(localidad__icontains=q) |
            Q(departamento__icontains=q) |
            Q(predio__icontains=q) |
            Q(predio_final__icontains=q)

        ).order_by("prioridad", "escuelas")

    # paginación
    paginator = Paginator(escuelas, 20)
    page_number = request.GET.get("page")
    escuelas_page = paginator.get_page(page_number)

    context = {

        "escuelas": escuelas_page,
        "q": q,

        "total_escuelas": total_escuelas,
        "tickets_activos": tickets_activos,
        "tickets_abiertos": tickets_abiertos,
        "tickets_derivados": tickets_derivados,

    }

    return render(request, "core/lista_escuelas.html", context)
def lista_escuelas(request):

    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    if estado not in ("OK", "CAIDO", "LENTO", "SIN_DATOS"):
        estado = ""

    total_escuelas = Escuela.objects.count()

    cerrados = ("RESUELTO", "RESUELTA", "CERRADO", "RECHAZADO")
    tickets_activos = Incidencia.objects.exclude(estado__in=cerrados).count()
    tickets_abiertos = Incidencia.objects.filter(estado="ABIERTO").count()
    tickets_derivados = Incidencia.objects.filter(
        estado__in=("DERIVADA", "DERIVADO")
    ).count()

    # Estado de conectividad (lo actualiza la sincronización con Meraki)
    from django.db.models import Max
    from django.utils.timesince import timesince
    por_estado = dict(Escuela.objects.values_list("estado").annotate(n=Count("id")))
    operativas = por_estado.get("OK", 0)
    sin_conexion = por_estado.get("CAIDO", 0)
    lentas = por_estado.get("LENTO", 0)
    sin_datos = por_estado.get("SIN_DATOS", 0)
    ultima_sync = EstadoConectividad.objects.aggregate(m=Max("actualizado"))["m"]

    escuelas = Escuela.objects.select_related("conectividad")

    if estado:
        escuelas = escuelas.filter(estado=estado)

    if q:

        escuelas = escuelas.annotate(

            prioridad=Case(

                When(cue__iexact=q, then=Value(1)),
                When(escuelas__icontains=q, then=Value(2)),
                When(localidad__icontains=q, then=Value(3)),
                When(departamento__icontains=q, then=Value(4)),
                When(predio__icontains=q, then=Value(5)),
                When(predio_final__icontains=q, then=Value(6)),

                default=Value(10),
                output_field=IntegerField(),
            )

        ).filter(

            Q(cue__icontains=q) |
            Q(escuelas__icontains=q) |
            Q(localidad__icontains=q) |
            Q(departamento__icontains=q) |
            Q(predio__icontains=q) |
            Q(predio_final__icontains=q)

        ).order_by("prioridad", "escuelas")

    else:
        escuelas = escuelas.order_by("escuelas")

    # Paginación: 50 escuelas por página
    paginator = Paginator(escuelas, 50)
    pagina = paginator.get_page(request.GET.get("page"))
    pagina.object_list = list(pagina.object_list)

    for e in pagina.object_list:
        c = getattr(e, "conectividad", None)
        e.tipo = tipo_enlace(e.internet)
        e.sin_contacto = (
            timesince(c.ultimo_contacto)
            if c and c.ultimo_contacto and c.estado in ("caida", "inactiva")
            else ""
        )

    actual = pagina.number
    if paginator.num_pages > 1:
        page_range = list(range(max(1, actual - 2),
                                min(paginator.num_pages, actual + 2) + 1))
    else:
        page_range = []

    filtros = [
        ("", "Todas", total_escuelas),
        ("OK", "Operativas", operativas),
        ("CAIDO", "Caídas", sin_conexion),
        ("LENTO", "Lentas", lentas),
        ("SIN_DATOS", "Sin datos", sin_datos),
    ]

    context = {

        "escuelas": pagina,
        "q": q,
        "estado": estado,
        "filtros": filtros,
        "page_range": page_range,
        "total_resultados": paginator.count,

        "total_escuelas": total_escuelas,
        "tickets_activos": tickets_activos,
        "tickets_abiertos": tickets_abiertos,
        "tickets_derivados": tickets_derivados,

        "operativas": operativas,
        "sin_conexion": sin_conexion,
        "lentas": lentas,
        "sin_datos": sin_datos,
        "ultima_sync": ultima_sync,

    }

    return render(request, "core/lista_escuelas.html", context)
def buscar_escuelas(request):

    q = request.GET.get("q", "").strip()

    if not q:
        return JsonResponse([], safe=False)

    q_normal = normalizar(q)

    palabras = q_normal.split()

    filtros = Q()

    for palabra in palabras:
        filtros |= Q(escuelas__icontains=palabra)
        filtros |= Q(localidad__icontains=palabra)
        filtros |= Q(departamento__icontains=palabra)
        filtros |= Q(predio__icontains=palabra)
        filtros |= Q(predio_final__icontains=palabra)
        filtros |= Q(cue__icontains=palabra)

    escuelas = Escuela.objects.filter(filtros).distinct()[:10]

    data = []

    for e in escuelas:
        data.append({
            "id": e.id,
            "nombre": e.escuelas,
            "cue": e.cue,
            "localidad": e.localidad,
            "departamento": e.departamento
        })

    return JsonResponse(data, safe=False)
# ===============================
# LISTA DE TICKETS
# ===============================

def lista_tickets(request):
    estado = request.GET.get("estado")
    mes = request.GET.get("mes")
    q = request.GET.get("q", "").strip()

    incidencias = Incidencia.objects.select_related("escuela").all()

    if estado:
        incidencias = incidencias.filter(estado=estado)

    if mes:
        year, month = mes.split("-")
        incidencias = incidencias.filter(
            fecha__year=year,
            fecha__month=month
        )

    if q:
        incidencias = incidencias.filter(
            Q(ticket__icontains=q) |
            Q(escuela__escuelas__icontains=q) |
            Q(escuela__cue__icontains=q) |
            Q(escuela__localidad__icontains=q) |
            Q(contacto__icontains=q) |
            Q(diagnostico__icontains=q)
        )

    incidencias = incidencias.order_by("-fecha")

    return render(request, "core/lista_tickets.html", {
        "incidencias": incidencias,
        "estado": estado,
        "mes": mes,
        "q": q,
    })


# ===============================
# UTILIDAD
# ===============================

def mostrar_bool(v):
    if v is True:
        return "Sí"
    if v is False:
        return "No"
    return "No relevado"


# ===============================
# NUEVO TICKET
# ===============================

def nuevo_ticket(request, id):
    escuela = get_object_or_404(Escuela, id=id)

    def to_bool(v):
        if v == "1":
            return True
        if v == "0":
            return False
        return None

    if request.method == "POST":
        codigo = f"NOC-{uuid.uuid4().hex[:8].upper()}"

        incidencia = Incidencia.objects.create(
            escuela=escuela,
            ticket=codigo,
            estado="ABIERTO",
            fecha=timezone.now(),
            fecha_limite=timezone.now() + timedelta(days=15),
            contacto=request.POST.get("contacto"),
            telefono=request.POST.get("telefono"),
            tiene_energia=to_bool(request.POST.get("tiene_energia")),
            navega=to_bool(request.POST.get("navega")),
            navega_lento=to_bool(request.POST.get("navega_lento")),
            ve_red_estudiante=to_bool(request.POST.get("ve_red_estudiante")),
            ve_red_docente=to_bool(request.POST.get("ve_red_docente")),
            luces_utmc=to_bool(request.POST.get("luces_utmc")),
            luces_switch=to_bool(request.POST.get("luces_switch")),
            luces_modem=to_bool(request.POST.get("luces_modem")),
            observaciones=request.POST.get("observaciones"),
        )

        diagnostico = "No se pudo determinar diagnóstico"

        if incidencia.navega is False:
            if not incidencia.ve_red_estudiante and not incidencia.ve_red_docente:
                diagnostico = "Falla de electrónica interna. Derivar a EDUCAR."
            else:
                diagnostico = "Red visible sin navegación. Posible proveedor."
        elif incidencia.navega_lento:
            diagnostico = "Navegación lenta. Posible saturación o proveedor."
        elif incidencia.navega:
            diagnostico = "Conectividad operativa."

        incidencia.diagnostico = diagnostico
        incidencia.save()

        return redirect("ver_ticket", ticket=incidencia.ticket)

    return render(request, "core/nuevo_ticket.html", {
        "escuela": escuela
    })


# ===============================
# DERIVAR TICKET
# ===============================

ESTADOS_TICKET_MANUALES = ("ABIERTO", "DERIVADA", "EN_PROCESO", "RESUELTO", "RECHAZADO", "CERRADO")
ESTADOS_DERIVACION = ("ENVIADA", "EN_PROCESO", "RESUELTA")

def derivar_ticket(request, ticket):
    """Registra que el operador derivó el reclamo (no envía ningún correo)."""
    incidencia = get_object_or_404(Incidencia, ticket=ticket)

    if request.method == "POST":
        empresa = request.POST.get("empresa")
        if empresa in dict(Derivacion.EMPRESAS):
            Derivacion.objects.create(
                incidencia=incidencia,
                empresa=empresa,
                observaciones=(request.POST.get("observaciones") or "").strip(),
            )
            incidencia.estado = "DERIVADA"
            incidencia.save()

    return redirect("ver_ticket", ticket=incidencia.ticket)


# ===============================
# VER TICKET
# ===============================

def ver_ticket(request, ticket):
    incidencia = get_object_or_404(Incidencia, ticket=ticket)

    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "cerrar_ticket":
            incidencia.estado = "RESUELTO"
            incidencia.save()

        elif accion == "cambiar_estado":
            nuevo = request.POST.get("estado")
            if nuevo in ESTADOS_TICKET_MANUALES:
                incidencia.estado = nuevo
                incidencia.save()

        elif accion == "estado_derivacion":
            did = str(request.POST.get("derivacion_id", ""))
            d = incidencia.derivaciones.filter(id=did).first() if did.isdigit() else None
            nuevo = request.POST.get("estado")
            if d and nuevo in ESTADOS_DERIVACION:
                d.estado = nuevo
                nota = (request.POST.get("observaciones") or "").strip()
                if nota:
                    marca = timezone.localtime().strftime("%d/%m %H:%M")
                    d.observaciones = (d.observaciones + "\n" if d.observaciones else "") + f"[{marca}] {nota}"
                d.save()

        return redirect("ver_ticket", ticket=incidencia.ticket)

    derivaciones = incidencia.derivaciones.order_by("-fecha")
    return render(request, "core/ver_ticket.html", {
        "incidencia": incidencia,
        "derivacion": incidencia.derivaciones.order_by("id").first(),
        "derivaciones": derivaciones,
        "estados_ticket": [(v, l) for v, l in Incidencia.ESTADOS
                           if v in ESTADOS_TICKET_MANUALES],
    })
# ===============================
# DETALLE ESCUELA
# ===============================

@never_cache
def detalle_escuela(request, id):
    escuela = get_object_or_404(Escuela, id=id)
    incidencias = Incidencia.objects.filter(escuela=escuela).order_by("-fecha")

    return render(request, "core/detalle_escuela.html", {
        "escuela": escuela,
        "incidencias": incidencias,
    })


# ===============================
# CONSULTAR TICKET
# ===============================

def consultar_ticket(request):

    if request.method == "POST":

        q = request.POST.get("ticket", "").strip().upper()

        incidencia = Incidencia.objects.filter(
            Q(ticket__icontains=q) | Q(ticket__iendswith=q)
        ).first()

        if incidencia:
            return redirect("ver_ticket", ticket=incidencia.ticket)

        return render(request, "core/consultar_ticket.html", {
            "error": "Ticket no encontrado"
        })

    return render(request, "core/consultar_ticket.html")
def save(self, *args, **kwargs):

    if not self.ticket:
        self.ticket = f"NOC-{uuid.uuid4().hex[:8].upper()}"

    if self.estado in ["RESUELTO", "CERRADO"] and not self.fecha_cierre:
        self.fecha_cierre = timezone.now()

    if self.estado in ["ABIERTO", "DERIVADA", "EN_PROCESO", "RECHAZADO"]:
        self.fecha_cierre = None

    super().save(*args, **kwargs)



def dashboard_noc(request):
    hoy = now()

    stats = Incidencia.objects.aggregate(
        total=Count("id"),

        abiertas=Count(
            "id",
            filter=Q(estado__in=["ABIERTO","DERIVADA","EN_PROCESO"])
        ),

        derivadas=Count(
            "id",
            filter=Q(estado="DERIVADA")
        ),

        en_proceso=Count(
            "id",
            filter=Q(estado="EN_PROCESO")
        ),

        resueltos=Count(
            "id",
            filter=Q(estado="RESUELTO")
        ),

        rechazados=Count(
            "id",
            filter=Q(estado="RECHAZADO")
        ),

        cerrados=Count(
            "id",
            filter=Q(estado="CERRADO")
        ),

        vencidas=Count(
            "id",
            filter=Q(
                estado__in=["ABIERTO","DERIVADA","EN_PROCESO"],
                fecha_limite__lt=hoy
            )
        ),
    )

    # SLA
    incidencias_resueltas = Incidencia.objects.filter(
        estado="CERRADO",
        fecha_cierre__isnull=False
    ).annotate(
        duracion=ExpressionWrapper(
            F("fecha_cierre") - F("fecha"),
            output_field=DurationField()
        )
    )

    sla_promedio = incidencias_resueltas.aggregate(
        promedio=Avg("duracion")
    )["promedio"]

    sla_dias = round(sla_promedio.total_seconds() / 86400, 2) if sla_promedio else 0


    # Tickets por mes
    tickets_por_mes = (
        Incidencia.objects
        .annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(total=Count("id"))
        .order_by("mes")
    )

    labels = [item["mes"].strftime("%m/%Y") for item in tickets_por_mes]
    data = [item["total"] for item in tickets_por_mes]


    # Top escuelas
    top_escuelas = (
        Incidencia.objects
        .values("escuela__escuelas")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )


    context = {
        **stats,
        "labels": labels,
        "data": data,
        "sla": sla_dias,
        "top_escuelas": top_escuelas,
        "alerta_abiertas": stats["abiertas"] > 50,
        "sla_critico": sla_dias > 5,
    }

    return render(request, "core/dashboard_noc.html", context)
    
def buscar_escuelas(request):

    q = request.GET.get("q", "").strip()

    if not q:
        return JsonResponse([], safe=False)

    escuelas = Escuela.objects.filter(
        Q(escuelas__icontains=q) |
        Q(localidad__icontains=q) |
        Q(cue__icontains=q)
    )[:10]

    data = []

    for e in escuelas:
        data.append({
            "cue": e.cue,
            "nombre": e.escuelas,
            "localidad": e.localidad
        })

    return JsonResponse(data, safe=False)
    return render(request, "core/dashboard_noc.html", context)

def _entero(valor, defecto):
    return int(valor) if str(valor).isdigit() else defecto




def escuelas_inestables(request):
    dias = min(_entero(request.GET.get("dias"), 7), 13)
    minimo = _entero(request.GET.get("min"), 3)
    tipo = request.GET.get("tipo", "")
    escolar = request.GET.get("horario") == "escolar"

    por_predio = {}
    for e in Escuela.objects.all():
        for campo in (e.predio, e.predio_final, e.unificar):
            k = norm(campo)
            if k and e not in por_predio.setdefault(k, []):
                por_predio[k].append(e)

    filas, tipos = [], set()
    for p, r in resumen_cortes(dias).items():
        escuelas = por_predio.get(p, [])
        tipos_p = sorted({tipo_enlace(e.internet) for e in escuelas}) or ["Sin escuela"]
        tipos.update(tipos_p)
        n = r["escolares"] if escolar else r["cortes"]
        if n < minimo or (tipo and tipo not in tipos_p):
            continue
        filas.append({"predio": p, "escuelas": escuelas,
                      "tipo": ", ".join(tipos_p), "n": n, **r})
    filas.sort(key=lambda f: f["n"], reverse=True)
    return render(request, "core/inestables.html", {
        "filas": filas, "dias": dias, "minimo": minimo,
        "tipo": tipo, "tipos": sorted(tipos), "escolar": escolar})

ESTADOS_ABIERTOS = ("ABIERTO", "DERIVADO", "DERIVADA", "EN_PROCESO")


def caidas_meraki(request):
    from django.db.models import Max
    filtro = request.GET.get("estado")
    if filtro in ("caida", "degradada", "inactiva"):
        estados = [filtro]
    else:
        estados = ["caida", "degradada"]

    items = list(EstadoConectividad.objects.filter(estado__in=estados)
                 .select_related("escuela").order_by("desde"))
    con_ticket = set(Incidencia.objects.filter(
        estado__in=ESTADOS_ABIERTOS,
        escuela_id__in=[i.escuela_id for i in items],
    ).values_list("escuela_id", flat=True))
    for i in items:
        i.tipo = tipo_enlace(i.escuela.internet)
        i.con_ticket = i.escuela_id in con_ticket

    cuenta = {e: EstadoConectividad.objects.filter(estado=e).count()
              for e in ("caida", "degradada", "inactiva")}
    ultima = EstadoConectividad.objects.aggregate(m=Max("actualizado"))["m"]
    limite = timedelta(hours=72 if timezone.localtime().weekday() in (0, 5, 6) else 30)
    return render(request, "core/caidas_meraki.html", {
        "items": items,
        "cuenta": cuenta,
        "filtro": filtro,
        "ultima_sync": ultima,
        "sync_vieja": not ultima or timezone.now() - ultima > limite,
    })
def lista_escuelas(request):

    q = request.GET.get("q", "").strip()
    estado = request.GET.get("estado", "")
    if estado not in ("OK", "CAIDO", "LENTO", "SIN_DATOS"):
        estado = ""

    total_escuelas = Escuela.objects.count()

    cerrados = ("RESUELTO", "RESUELTA", "CERRADO", "RECHAZADO")
    tickets_activos = Incidencia.objects.exclude(estado__in=cerrados).count()
    tickets_abiertos = Incidencia.objects.filter(estado="ABIERTO").count()
    tickets_derivados = Incidencia.objects.filter(
        estado__in=("DERIVADA", "DERIVADO")
    ).count()

    from django.db.models import Max
    from django.utils.timesince import timesince
    por_estado = dict(Escuela.objects.values_list("estado").annotate(n=Count("id")))
    operativas = por_estado.get("OK", 0)
    sin_conexion = por_estado.get("CAIDO", 0)
    lentas = por_estado.get("LENTO", 0)
    sin_datos = por_estado.get("SIN_DATOS", 0)
    ultima_sync = EstadoConectividad.objects.aggregate(m=Max("actualizado"))["m"]

    ids = buscar_ids(q, estado) if q else None

    if ids is not None:
        paginator = Paginator(ids, 50)
        pagina = paginator.get_page(request.GET.get("page"))
        objs = Escuela.objects.select_related("conectividad").in_bulk(list(pagina.object_list))
        pagina.object_list = [objs[i] for i in pagina.object_list if i in objs]
    else:
        escuelas = Escuela.objects.select_related("conectividad")
        if estado:
            escuelas = escuelas.filter(estado=estado)
        paginator = Paginator(escuelas.order_by("escuelas"), 50)
        pagina = paginator.get_page(request.GET.get("page"))
        pagina.object_list = list(pagina.object_list)

    for e in pagina.object_list:
        c = getattr(e, "conectividad", None)
        e.tipo = tipo_enlace(e.internet)
        e.sin_contacto = (
            timesince(c.ultimo_contacto)
            if c and c.ultimo_contacto and c.estado in ("caida", "inactiva")
            else ""
        )

    actual = pagina.number
    if paginator.num_pages > 1:
        page_range = list(range(max(1, actual - 2),
                                min(paginator.num_pages, actual + 2) + 1))
    else:
        page_range = []

    filtros = [
        ("", "Todas", total_escuelas),
        ("OK", "Operativas", operativas),
        ("CAIDO", "Caídas", sin_conexion),
        ("LENTO", "Lentas", lentas),
        ("SIN_DATOS", "Sin datos", sin_datos),
    ]

    context = {
        "escuelas": pagina,
        "q": q,
        "estado": estado,
        "filtros": filtros,
        "page_range": page_range,
        "total_resultados": paginator.count,
        "total_escuelas": total_escuelas,
        "tickets_activos": tickets_activos,
        "tickets_abiertos": tickets_abiertos,
        "tickets_derivados": tickets_derivados,
        "operativas": operativas,
        "sin_conexion": sin_conexion,
        "lentas": lentas,
        "sin_datos": sin_datos,
        "ultima_sync": ultima_sync,
    }

    return render(request, "core/lista_escuelas.html", context)


def buscar_escuelas(request):
    """Sugerencias del desplegable de búsqueda."""
    q = request.GET.get("q", "").strip()
    ids = buscar_ids(q) if len(q) >= 2 else None
    if not ids:
        return JsonResponse([], safe=False)
    ids = ids[:8]
    objs = Escuela.objects.in_bulk(ids)
    data = [{"nombre": objs[i].escuelas, "cue": objs[i].cue, "localidad": objs[i].localidad}
            for i in ids if i in objs]
    return JsonResponse(data, safe=False)
