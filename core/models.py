from django.db import models
from datetime import timedelta
from django.utils import timezone
import uuid


class Escuela(models.Model):
    ESTADOS = [
        ("OK", "Operativo"),
        ("LENTO", "Lento"),
        ("CAIDO", "Caído"),
        ("SIN_DATOS", "Sin datos"),
    ]

    numero = models.IntegerField(null=True, blank=True)
    predio_final = models.CharField(max_length=50, blank=True)
    unificar = models.CharField(max_length=50, blank=True)
    predio = models.CharField(max_length=50, blank=True)
    cue = models.CharField(max_length=20)
    escuelas = models.CharField(max_length=250)
    localidad = models.CharField(max_length=150)
    departamento = models.CharField(max_length=150)
    nivel = models.CharField(max_length=100)
    lat = models.FloatField(null=True, blank=True)
    lon = models.FloatField(null=True, blank=True)
    internet = models.CharField(max_length=100, blank=True)

    estado = models.CharField(
        max_length=10,
        choices=ESTADOS,
        default="SIN_DATOS"
    )

    def __str__(self):
        return f"{self.cue} - {self.escuelas}"
class Incidencia(models.Model):

    escuela = models.ForeignKey(
        Escuela,
        on_delete=models.CASCADE,
        related_name="incidencias"
    )

    fecha = models.DateTimeField(auto_now_add=True)
    fecha_limite = models.DateTimeField(null=True, blank=True)

    # 🔥 NUEVO CAMPO
    fecha_cierre = models.DateTimeField(null=True, blank=True)

    ticket = models.CharField(max_length=20, blank=True)

    contacto = models.CharField(max_length=150, blank=True, null=True)
    telefono = models.CharField(max_length=50, blank=True, null=True)

    navega = models.BooleanField(null=True)
    navega_lento = models.BooleanField(null=True)
    ve_red_estudiante = models.BooleanField(null=True)
    ve_red_docente = models.BooleanField(null=True)

    luces_utmc = models.BooleanField(null=True)
    luces_switch = models.BooleanField(null=True)
    luces_modem = models.BooleanField(null=True)

    es_rural = models.BooleanField(default=False)
    tiene_energia = models.BooleanField(null=True)

    observaciones = models.TextField(blank=True)

    diagnostico = models.CharField(max_length=200, blank=True)
    
    ESTADOS = [
        ("ABIERTO", "Abierto"),
        ("DERIVADO", "Derivado"),
        ("EN_PROCESO", "En proceso"),
        ("RESUELTO", "Resuelto"),       
        ("RECHAZADO", "Rechazado"),
        ("CERRADO", "Cerrado"),

    ]

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="ABIERTO"
    )
        
    def esta_vencida(self):
        if self.estado != "RESUELTA" and self.fecha_limite:
            return timezone.now() > self.fecha_limite
        return False

    def save(self, *args, **kwargs):

        # Generar ticket si no existe
        if not self.ticket:
            self.ticket = f"NOC-{uuid.uuid4().hex[:8].upper()}"

        # 🔥 Si se marca como RESUELTA → guardar fecha cierre
        if self.estado == "RESUELTA" and not self.fecha_cierre:
            self.fecha_cierre = timezone.now()

        # 🔥 Si se vuelve a abrir → borrar fecha cierre
        if self.estado != "RESUELTA":
            self.fecha_cierre = None

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.escuela.cue} - {self.estado}"
class Derivacion(models.Model):

    EMPRESAS = [
        ("EDUCAR", "Piso Tecnológico - EDUCAR"),
        ("ENERSESAPEN", "Proveedor de Internet"),
        ("CIDD", "antenas de Starlink/paneles solares de antenas"),
        ("ENERGIA", "Energía / Paneles solares"),
        
    ]

    incidencia = models.ForeignKey(
        Incidencia,
        on_delete=models.CASCADE,
        related_name="derivaciones"
    )

    empresa = models.CharField(max_length=30, choices=EMPRESAS)

    fecha = models.DateTimeField(auto_now_add=True)

    estado = models.CharField(
        max_length=20,
        choices=[
            ("ENVIADA", "Enviada"),
            ("EN_PROCESO", "En proceso"),
            ("RESUELTA", "Resuelta"),
            ],
        default="ENVIADA"
    )

    observaciones = models.TextField(blank=True)

    def __str__(self):
        return f"{self.empresa} - {self.estado}"

