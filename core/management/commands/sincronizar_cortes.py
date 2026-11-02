import os
import requests
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.models import CambioDisponibilidad

BASE = "https://api.meraki.com/api/v1/organizations/635570497412661776"
FMT = "%Y-%m-%dT%H:%M:%SZ"


def estado(lista):
    return next((x["value"] for x in lista or [] if x.get("name") == "status"), "")


class Command(BaseCommand):
    help = "Guarda los cambios de disponibilidad (cortes) de los MX"

    def handle(self, *args, **opts):
        H = {"X-Cisco-Meraki-API-Key": os.environ["MERAKI_API_KEY"].strip()}
        ahora = timezone.now()
        ultimo = (CambioDisponibilidad.objects.order_by("-ts")
                  .values_list("ts", flat=True).first())
        # 1 hora de solapamiento; Meraki permite hasta 14 días por consulta
        t0 = (ultimo - timedelta(hours=1)) if ultimo else ahora - timedelta(days=13)
        t0 = max(t0, ahora - timedelta(days=13))

        url = f"{BASE}/devices/availabilities/changeHistory"
        params = {"t0": t0.strftime(FMT), "t1": ahora.strftime(FMT),
                  "perPage": 1000, "productTypes[]": "appliance"}
        nuevos = []
        while url:
            r = requests.get(url, headers=H, params=params, timeout=120)
            r.raise_for_status()
            for e in r.json():
                ts = parse_datetime(e["ts"])
                if not ts or ts < t0 or ts > ahora:   # filtro propio por fecha
                    continue
                red, det = e.get("network") or {}, e.get("details") or {}
                nuevos.append(CambioDisponibilidad(
                    predio=str(red.get("name", "")).strip(),
                    network_id=red.get("id", ""),
                    serial=(e.get("device") or {}).get("serial", ""),
                    ts=ts,
                    estado_anterior=estado(det.get("old")),
                    estado_nuevo=estado(det.get("new")),
                ))
            url, params = r.links.get("next", {}).get("url"), None

        CambioDisponibilidad.objects.bulk_create(
            nuevos, ignore_conflicts=True, batch_size=500)
        self.stdout.write(f"{len(nuevos)} cambios procesados (desde {t0:%d/%m %H:%M})")
