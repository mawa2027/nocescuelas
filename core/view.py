from django.shortcuts import render, get_object_or_404,redirect
from .models import Escuela, Incidencia
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
from django.core.mail import send_mail


def lista_escuelas(request):
    q = request.GET.get("q", "").strip()

    escuelas = Escuela.objects.all()

    if q:
        escuelas = escuelas.filter(
            Q(cue__icontains=q) |
            Q(escuelas__icontains=q) |
            Q(localidad__icontains=q) |
            Q(departamento__icontains=q) |
            Q(predio__icontains=q) |
            Q(predio_final__icontains=q)
        )

    return render(request, "core/lista_escuelas.html", {
        "escuelas": escuelas,
        "q": q
    })


def escuela_detalle_diagnostico(request, id):
    escuela = get_object_or_404(Escuela, id=id)

    if request.method == "POST":

        def to_bool(v):
            if v == "1":
                return True
            if v == "0":
                return False
            return None

        incidencia = Incidencia.objects.create(
            escuela=escuela,
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
        )

        # ======================
        # DIAGNÓSTICO NOC REAL
        # ======================

        diagnostico = "No se pudo determinar diagnóstico"

        if incidencia.navega is False:
            if incidencia.ve_red_estudiante is False and incidencia.ve_red_docente is False:
                diagnostico = "Falla de electrónica interna. Derivar a EDUCAR."
            elif incidencia.ve_red_estudiante or incidencia.ve_red_docente:
                diagnostico = "Red visible sin navegación. Posible proveedor de internet."

        elif incidencia.navega_lento:
            diagnostico = "Navegación lenta. Posible saturación o proveedor."

        elif incidencia.navega:
            diagnostico = "Conectividad operativa."

        incidencia.diagnostico = diagnostico
        incidencia.save()

        # 👉 ACÁ ESTÁ LA CLAVE
        return redirect("ver_incidencia", ticket=incidencia.ticket)

    # ======================
    # GET → mostrar formulario
    # ======================
    return render(request, "core/escuela_diagnostico.html", {
        "escuela": escuela
    })
def ver_incidencia(request, ticket):
    incidencia = get_object_or_404(Incidencia, ticket=ticket)

    return render(request, "core/ver_incidencia.html", {
        "incidencia": incidencia
    })
def consultar_ticket(request):
    if request.method == "POST":
        ticket = request.POST.get("ticket").strip().upper()
        return redirect("ver_ticket", ticket=ticket)

    return render(request, "core/consultar_ticket.html")
def ver_ticket(request, ticket):
    incidencia = get_object_or_404(Incidencia, ticket=ticket)

    return render(request, "core/ver_ticket.html", {
        "incidencia": incidencia
    })

def derivar_ticket(request, ticket):
    incidencia = get_object_or_404(Incidencia, ticket=ticket)

    empresa = "PROVEEDOR"  # luego lo automatizamos

    Derivacion.objects.create(
        incidencia=incidencia,
        empresa=empresa
    )

    # cambiar estado
    incidencia.estado = "DERIVADA"
    incidencia.save()

    # enviar mail
    send_mail(
        subject=f"Ticket {incidencia.ticket}",
        message=f"""
Ticket: {incidencia.ticket}
Escuela: {incidencia.escuela}
Diagnóstico: {incidencia.diagnostico}

Favor verificar y responder este correo.
""",
        from_email="noc@tudominio.gob.ar",
        recipient_list=["proveedor@empresa.com"],
        fail_silently=False
    )

    return redirect("ver_ticket", ticket=incidencia.ticket)
def detalle_escuela(request, id):
    escuela = get_object_or_404(Escuela, id=id)

    incidencias = escuela.incidencias.order_by("-fecha")

    return render(request, "core/detalle_escuela.html", {
        "escuela": escuela,
        "incidencias": incidencias
    })
def consultar_ticket(request):
    if request.method == "POST":
        ticket = request.POST.get("ticket", "").strip().upper()
        return redirect("ver_ticket", ticket=ticket)

    return render(request, "core/consultar_ticket.html")
