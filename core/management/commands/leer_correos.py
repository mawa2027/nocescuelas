import imaplib
import email
import re
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Incidencia


class Command(BaseCommand):
    help = "Lee correos desde ayer y actualiza tickets automáticamente"

    def handle(self, *args, **kwargs):

        try:
            # Conectar a Gmail IMAP
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            mail.select("INBOX")

            # Fecha de ayer (incluye hoy automáticamente)
            ayer = (datetime.now() - timedelta(days=1)).strftime("%d-%b-%Y")
            
            status, messages = mail.search( None, '(UNSEEN SUBJECT "NOC-")'
            )
            
            if status != "OK":
                self.stdout.write(self.style.ERROR("Error al buscar correos"))
                return

            if not messages[0]:
                self.stdout.write("No hay correos nuevos desde ayer.")
                return

            for num in messages[0].split():

                status, data = mail.fetch(num, "(RFC822)")
                if status != "OK":
                    continue

                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = msg["subject"]
                if not subject:
                    continue

                subject = subject.upper().strip()

                # Buscar código tipo NOC-XXXXXXXX
                match_codigo = re.search("NOC-([A-Z0-9]+)", subject)

                # Buscar estado al final del asunto
                match_estado = re.search(
                    r"(RESUELTO|EN PROCESO|RECHAZADO)\s*$",
                    subject
                )

                if not match_codigo or not match_estado:
                    continue

                codigo = match_codigo.group(1).strip()
                estado_mail = match_estado.group(1).strip()

                ticket_completo = match_codigo.group(0)

                try:
                    incidencia = Incidencia.objects.get(
                        ticket__iexact=ticket_completo
                    )
                except Incidencia.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Ticket {ticket_completo} no existe"
                        )
                    )
                    continue

                # 🔁 Si estaba cerrado y llega mail nuevo → reabrir
                if incidencia.estado == "CERRADO":
                    incidencia.estado = "EN_PROCESO"

                # Cambiar estado según asunto del mail
                if estado_mail == "RESUELTO":
                    incidencia.estado = "RESUELTO"

                elif estado_mail == "EN PROCESO":
                    incidencia.estado = "EN_PROCESO"

                elif estado_mail == "RECHAZADO":
                    incidencia.estado = "RECHAZADO"

                # Obtener cuerpo del mail
                cuerpo = ""

                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            cuerpo = part.get_payload(
                                decode=True
                            ).decode(errors="ignore")
                            break
                else:
                    cuerpo = msg.get_payload(
                        decode=True
                    ).decode(errors="ignore")

                incidencia.observaciones = cuerpo
                incidencia.save()

                # Marcar como leído
                mail.store(num, '+FLAGS', '\\Seen')

                self.stdout.write(
                    self.style.SUCCESS(
                        f"{ticket_completo} → {incidencia.estado}"
                    )
                )

            mail.logout()

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"Error general: {e}")
                )
