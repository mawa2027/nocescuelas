from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
urlpatterns = [
    path("", views.lista_escuelas, name="inicio"),
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
    path("inestables/", views.escuelas_inestables, name="inestables"),
    path("caidas/", views.caidas_meraki, name="caidas_meraki"),
    path("login/", auth_views.LoginView.as_view(
        template_name="core/login.html", redirect_authenticated_user=True), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    
    ]
