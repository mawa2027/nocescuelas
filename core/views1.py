from django.shortcuts import render, get_object_or_404, redirect
from .models import Escuela, Incidencia, Derivacion
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from django.core.mail import send_mail
from django.utils.timezone import now
from django.db.models import Count
from django.views.decorators.cache import never_cache
import uuid
import re
import unicodedata


def lista_escuelas(request):
    q = request.GET.get("q", "").strip()  # ← CORREGIDO: las comillas estaban mal

    escuelas = Escuela.objects.all()

    if q:
        # Normalizar la búsqueda (quitar acentos y caracteres especiales)
        q_normalized = ''.join(
            c for c in unicodedata.normalize('NFD', q.lower())
            if unicodedata.category(c) != 'Mn'
        )
        
        # Dividir en palabras
        palabras = q_normalized.split()
        
        # Crear filtros combinados
        filtros = Q()
        
        for palabra in palabras:
            # Buscar en campos principales
            campo_filtros = (
                Q(cue__icontains=palabra) |
                Q(escuelas__icontains=palabra) |
                Q(localidad__icontains=palabra) |
                Q(departamento__icontains=palabra) |
                Q(predio__icontains=palabra) |
                Q(predio_final__icontains=palabra) |
                Q(nivel__icontains=palabra)
            )
            
            # Si la palabra es un número, buscar coincidencias con números en el nombre
            if palabra.isdigit():
                campo_filtros |= Q(escuelas__icontains=f" {palabra} ")  # Número solo
                campo_filtros |= Q(escuelas__icontains=f"º{palabra}")   # 3º, 4º, etc
                campo_filtros |= Q(escuelas__icontains=f" Nº{palabra}") # Nº3
                campo_filtros |= Q(escuelas__icontains=f" {palabra}º")  # 3º
                campo_filtros |= Q(cue__icontains=palabra)  # Buscar en CUE también
            
            filtros |= campo_filtros
        
        # Búsqueda especial para términos como "tecnica" que pueden estar abreviados
        terminos_comunes = {
            'tecnica': ['tec', 'tecnica', 'técnica', 'tecnico', 'técnico'],
            'escuela': ['esc', 'escuela'],
            'nro': ['nº', 'no', 'numero', 'número', 'nro'],
        }
        
        # Agregar variantes de palabras comunes
        for palabra in palabras:
            for clave, variantes in terminos_comunes.items():
                if palabra in variantes or any(v in palabra for v in variantes):
                    for variante in variantes:
                        filtros |= Q(escuelas__icontains=variante)
                    break
        
        escuelas = escuelas.filter(filtros).distinct()
        
        # Ordenar resultados (los que empiezan con la búsqueda primero)
        escuelas = sorted(escuelas, key=lambda e: (
            not e.escuelas.lower().startswith(q.lower()),
            e.escuelas
        ))

    return render(request, "core/lista_escuelas.html", {
        "escuelas": escuelas,
        "q": q
    })


def lista_tickets(request):
    estado = request.GET.get("estado")
    mes = request.GET.get("mes")
    q = request.GET.get("q", "").strip()

    incidencias = Incidencia.objects.select_related("escuela").all()

    # filtro por estado
    if estado:
        incidencias = incidencias.filter(estado=estado)

    # filtro por mes (YYYY-MM)
    if mes:
        year, month = mes.split("-")
        incidencias = incidencias.filter(
            fecha__year=year,
            fecha__month=month
        )

    # búsqueda libre mejorada
    if q:
        q_normalized = ''.join(
            c for c in unicodedata.normalize('NFD', q.lower())
            if unicodedata.category(c) != 'Mn'
        )
        
        palabras = q_normalized.split()
        filtros = Q()
        
        for palabra in palabras:
            filtros |= Q(ticket__icontains=palabra)
            filtros |= Q(escuela__escuelas__icontains=palabra)
            filtros |= Q(escuela__cue__icontains=palabra)
            filtros |= Q(escuela__localidad__icontains=palabra)
            filtros |= Q(contacto__icontains=palabra)
            filtros |= Q(diagnostico__icontains=palabra)
            
            if palabra.isdigit():
                filtros |= Q(ticket__icontains=palabra)
                filtros |= Q(escuela__cue__icontains=palabra)
        
        incidencias = incidencias.filter(filtros).distinct()

    incidencias = incidencias.order_by("-fecha")

    return render(request, "core/lista_tickets.html", {
        "incidencias": incidencias,
        "estado": estado,
        "mes": mes,
        "q": q,
    })


def mostrar_bool(v):
    if v is True:
        return "Sí"
    if v is False:
        return "No"
    return "No relevado"


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

        # diagnóstico automático (igual que el otro flujo)
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

DETALLE TÉCNICO
-------------------------
Tiene energía: {mostrar_bool(incidencia.tiene_energia)}
Navega: {mostrar_bool(incidencia.navega)}
Navega lento: {mostrar_bool(incidencia.navega_lento)}
Ve red estudiante: {mostrar_bool(incidencia.ve_red_estudiante)}
Ve red docente: {mostrar_bool(incidencia.ve_red_docente)}
Luces UTMc: {mostrar_bool(incidencia.luces_utmc)}
Luces Switch: {mostrar_bool(incidencia.luces_switch)}
Luces Módem: {mostrar_bool(incidencia.luces_modem)}
"""
        send_mail(
            subject=f"[NOC] Ticket {incidencia.ticket} - {empresa}",
            message=mensaje,
            from_email="angelwcortes@gmail.com",
            recipient_list=["angelwcortes@gmail.com"],  # luego lo automatizamos
            fail_silently=False
        )

        return redirect("ver_ticket", ticket=incidencia.ticket)

    return redirect("ver_ticket", ticket=incidencia.ticket)


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


@never_cache
def detalle_escuela(request, id):
    escuela = get_object_or_404(Escuela, id=id)
    incidencias = Incidencia.objects.filter(escuela=escuela).order_by("-fecha")
    return render(request, "core/detalle_escuela.html", {
        "escuela": escuela,
        "incidencias": incidencias,
    })


def consultar_ticket(request):
    if request.method == "POST":
        ticket = request.POST.get("ticket", "").strip().upper()
        return redirect("ver_ticket", ticket=ticket)
    return render(request, "core/consultar_ticket.html")


def dashboard_noc(request):
    hoy = now().date()
    total = Incidencia.objects.count()
    abiertas = Incidencia.objects.filter(estado="ABIERTO").count()
    derivadas = Incidencia.objects.filter(estado="DERIVADA").count()
    vencidas = Incidencia.objects.filter(
        estado="ABIERTO",
        fecha_limite__lt=hoy
    ).count()
    ultimos_tickets = Incidencia.objects.select_related("escuela") \
        .order_by("-fecha")[:10]
    return render(request, "core/dashboard_noc.html", {
        "total": total,
        "abiertas": abiertas,
        "derivadas": derivadas,
        "vencidas": vencidas,
        "ultimos_tickets": ultimos_tickets,
    })
