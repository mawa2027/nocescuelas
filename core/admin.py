from django.contrib import admin
from .models import Escuela
from .models import Incidencia

@admin.register(Escuela)
class EscuelaAdmin(admin.ModelAdmin):
    list_display = (
        "cue",
        "escuelas",
        "localidad",
        "departamento",
        "nivel",
        "internet",
    )

    search_fields = (
        "cue",
        "escuelas",
        "localidad",
        "departamento",
        "internet",
    )

    list_filter = (
        "departamento",
        "nivel",
        "internet",
    )
@admin.register(Incidencia)
class IncidenciaAdmin(admin.ModelAdmin):
    list_display = ("escuela", "estado", "fecha")
    list_filter = ("estado",)
