"""Zajedničke konstante za ceo servis: vremenska zona i nazivi dana."""

from zoneinfo import ZoneInfo

TIMEZONE_NAME = "Europe/Belgrade"
TZ = ZoneInfo(TIMEZONE_NAME)

# Indeks 0 je ponedeljak, kao kod datetime.weekday().
DAYS = ["Ponedeljak", "Utorak", "Sreda", "Četvrtak", "Petak", "Subota", "Nedelja"]
DAY_SHORT = ["Pon", "Uto", "Sre", "Čet", "Pet", "Sub", "Ned"]
