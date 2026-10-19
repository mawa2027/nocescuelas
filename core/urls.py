from django.urls import path
from . import views

urlpatterns = [
    path("escuelas/", views.lista_escuelas, name="lista_escuelas"),
    path("escuelas/<int:id>/", views.detalle_escuela, name="detalle_escuela"),
    path("escuelas/<int:id>/nuevo-ticket/", views.nuevo_ticket, name="nuevo_ticket"),
    path("buscar-escuelas/", views.buscar_escuelas, name="buscar_escuelas"),
    # 👇 ESPECÍFICAS PRIMERO
    path("ticket/consultar/", views.consultar_ticket, name="consultar_ticket"),
    path("ticket/<str:ticket>/derivar/", views.derivar_ticket, name="derivar_ticket"),

    # 👇 GENÉRICA SIEMPRE AL FINAL
    path("ticket/<str:ticket>/", views.ver_ticket, name="ver_ticket"),

    path("tickets/", views.lista_tickets, name="lista_tickets"),
    path("dashboard/", views.dashboard_noc, name="dashboard_noc"),
    
    ]
