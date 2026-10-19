from django.shortcuts import render, get_object_or_404, redirect
from .models import Escuela, Incidencia, Derivacion

from django.http import JsonResponse
from django.db.models import Count, Q, Avg, F, ExpressionWrapper, DurationField, Case, When, Value, IntegerField
from django.db.models.functions import TruncMonth

from django.core.mail import send_mail
from django.utils.timezone import now
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.core.paginator import Paginator

from datetime import timedelta
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

    context = {

        "escuelas": escuelas,
        "q": q,

        "total_escuelas": total_escuelas,
        "tickets_activos": tickets_activos,
        "tickets_abiertos": tickets_abiertos,
        "tickets_derivados": tickets_derivados,

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

def derivar_ticket(request, ticket):
    incidencia = get_object_or_404(Incidencia, ticket=ticket)

    if request.method == "POST":
        empresa = request.POST.get("empresa")

        derivacion = Derivacion.objects.create(
            incidencia=incidencia,
            empresa=empresa
        )

        incidencia.estado = "DERIVADA"
        incidencia.save()

        escuela = incidencia.escuela

        mensaje = f"""
TICKET NOC: {incidencia.ticket}
ESTADO: DERIVADO
FECHA: {derivacion.fecha.strftime('%d/%m/%Y %H:%M')}

ESCUELA
-------------------------
Nombre: {escuela.escuelas}
CUE: {escuela.cue}
Localidad: {escuela.localidad}
Departamento: {escuela.departamento}
Predio: {escuela.predio_final or escuela.predio or 'No informado'}

CONTACTO
-------------------------
Contacto: {incidencia.contacto}
Teléfono: {incidencia.telefono}

DIAGNÓSTICO NOC
-------------------------
{incidencia.diagnostico}

OBSERVACIONES
-------------------------
{incidencia.observaciones or 'Sin observaciones'}
"""

        send_mail(
            subject=f"[NOC] Ticket {incidencia.ticket} - {empresa}",
            message=mensaje,
            from_email="angelwcortes@gmail.com",
            recipient_list=["angelwcortes@gmail.com"],
            fail_silently=False
        )

        return redirect("ver_ticket", ticket=incidencia.ticket)

    return redirect("ver_ticket", ticket=incidencia.ticket)


# ===============================
# VER TICKET
# ===============================

def ver_ticket(request, ticket):
    incidencia = get_object_or_404(Incidencia, ticket=ticket)
    derivacion = Derivacion.objects.filter(incidencia=incidencia).first()

    if request.method == "POST" and request.POST.get("accion") == "cerrar_ticket":
        incidencia.estado = "RESUELTA"
        incidencia.fecha_resolucion = timezone.now()
        incidencia.save()
        return redirect("ver_ticket", ticket=incidencia.ticket)

    return render(request, "core/ver_ticket.html", {
        "incidencia": incidencia,
        "derivacion": derivacion
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
