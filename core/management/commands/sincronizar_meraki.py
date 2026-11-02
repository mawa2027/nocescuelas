import os
import requests
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import Escuela, Incidencia, EstadoConectividad, EventoConectividad
from core.utils import norm

FALLOS_PARA_CAIDA = 1      # caída = offline en la primera fotografía
UMBRAL_APS = 0.4           # 40 % de APs caídos = "degradada"
CREAR_TICKETS = False      # no crea tickets automáticos
ESTADO_ESCUELA = {"online": "OK", "caida": "CAIDO",
                  "degradada": "LENTO", "inactiva": "SIN_DATOS"}
ABIERTAS = ("ABIERTO", "DERIVADO", "DERIVADA", "EN_PROCESO")


def get_all(base, path, headers, params=None):
    url, params, out = f"{base}/{path}", {"perPage": 1000, **(params or {})}, []
    while url:
        r = requests.get(url, headers=headers, params=params, timeout=120)
        r.raise_for_status()
        out += r.json()
        url, params = r.links.get("next", {}).get("url"), None
    return out


class Command(BaseCommand):
    help = "Sincroniza el estado de conectividad de las escuelas con Meraki"

    def add_arguments(self, parser):
        parser.add_argument("--baseline", action="store_true",
                            help="Carga inicial: sin eventos ni tickets")

    def handle(self, *args, **opts):
        H = {"X-Cisco-Meraki-API-Key": os.environ["MERAKI_API_KEY"].strip()}
        base = ("https://api.meraki.com/api/v1/organizations/"
                + os.environ["MERAKI_ORG_ID"].strip())

        redes = {n["id"]: norm(n["name"]) for n in get_all(base, "networks", H)}
        por_red = {}
        for d in get_all(base, "devices/statuses", H):
            por_red.setdefault(d["networkId"], []).append(d)

        por_predio = {}
        for e in Escuela.objects.all():
            for campo in (e.predio, e.predio_final, e.unificar):
                k = norm(campo)
                if k and e not in por_predio.setdefault(k, []):
                    por_predio[k].append(e)

        existentes = {s.escuela_id: s for s in EstadoConectividad.objects.all()}
        ahora, conteo = timezone.now(), {}
        redes_sin_escuela, predios_vistos = [], set()

        for net_id, devs in por_red.items():
            mxs = [d for d in devs if d["productType"] == "appliance"]
            if not mxs:
                continue
            predio = redes.get(net_id, "")
            escuelas = por_predio.get(predio)
            if not escuelas:
                redes_sin_escuela.append(predio)
                continue
            predios_vistos.add(predio)

            estados = {d["status"] for d in mxs}
            st_mx = ("online" if "online" in estados else
                     "offline" if "offline" in estados else
                     "alerting" if "alerting" in estados else "dormant")
            ult = [d["lastReportedAt"] for d in mxs if d.get("lastReportedAt")]
            ultimo = parse_datetime(max(ult)) if ult else None

            aps = [d for d in devs
                   if d["productType"] == "wireless" and d["status"] != "dormant"]
            aps_off = sum(1 for d in aps if d["status"] == "offline")

            for esc in escuelas:
                est = existentes.get(esc.id)
                if not est:
                    est = EstadoConectividad(escuela=esc, estado="online", desde=ahora)
                    existentes[esc.id] = est

                if st_mx == "offline":
                    fallos = (FALLOS_PARA_CAIDA if opts["baseline"]
                              else est.fallos_consecutivos + 1)
                    nuevo = "caida" if fallos >= FALLOS_PARA_CAIDA else est.estado
                else:
                    fallos = 0
                    if st_mx == "dormant":
                        nuevo = "inactiva"
                    elif st_mx == "alerting" or (aps and aps_off / len(aps) >= UMBRAL_APS):
                        nuevo = "degradada"
                    else:
                        nuevo = "online"

                if nuevo != est.estado:
                    if not opts["baseline"]:
                        EventoConectividad.objects.create(
                            escuela=esc, estado_anterior=est.estado, estado_nuevo=nuevo)
                    est.estado = nuevo
                    est.desde = ultimo if (nuevo == "caida" and ultimo) else ahora

                if (CREAR_TICKETS and not opts["baseline"] and nuevo == "caida"
                        and fallos >= 2
                        and not esc.incidencias.filter(estado__in=ABIERTAS).exists()):
                    Incidencia.objects.create(
                        escuela=esc,
                        diagnostico="Caída persistente detectada automáticamente (Meraki)",
                        observaciones=f"Último contacto del MX: {ultimo}",
                    )

                est.fallos_consecutivos = fallos
                est.ultimo_contacto = ultimo
                est.aps_total, est.aps_offline = len(aps), aps_off
                est.save()

                nuevo_esc = ESTADO_ESCUELA[est.estado]
                if esc.estado != nuevo_esc:
                    esc.estado = nuevo_esc
                    esc.save(update_fields=["estado"])
                conteo[est.estado] = conteo.get(est.estado, 0) + 1

        sin_red = [k for k in por_predio if k not in predios_vistos]
        self.stdout.write(f"Estados: {conteo}")
        self.stdout.write(f"Redes de Meraki sin escuela en el sistema: "
                          f"{len(redes_sin_escuela)} (ej.: {redes_sin_escuela[:5]})")
        self.stdout.write(f"Predios del sistema sin red/MX en Meraki: "
                          f"{len(sin_red)} (ej.: {sin_red[:5]})")
