from django.urls import path
from . import views

urlpatterns = [
    path("escuelas/", views.lista_escuelas, name="lista_escuelas"),

    # UNA sola pantalla: ver + diagnosticar
    path(
        "escuelas/<int:id>/",
        views.escuela_detalle_diagnostico,
        name="escuela_detalle"
    ),
    path(
        "incidencia/<str:ticket>/",
        views.ver_incidencia,
        name="ver_incidencia"
     ),
    path("ticket/", views.consultar_ticket, name="consultar_ticket"),
    path("ticket/<str:ticket>/", views.ver_ticket, name="ver_ticket"),
    path("ticket/<str:ticket>/derivar/", views.derivar_ticket, name="derivar_ticket"),

]

    
