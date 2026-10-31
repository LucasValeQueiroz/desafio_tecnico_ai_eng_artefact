"""Store time: opening hours from section 2 of the manual, in Campo Grande's timezone."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

STORE_TZ = ZoneInfo("America/Campo_Grande")

# Weekday -> (opens, closes). Sunday is absent because the store doesn't open.
OPENING_HOURS = {0: (9, 18), 1: (9, 18), 2: (9, 18), 3: (9, 18), 4: (9, 18), 5: (9, 13)}

# National fixed-date holidays. Municipal and movable holidays aren't known to the system.
FIXED_HOLIDAYS = {(1, 1), (4, 21), (5, 1), (9, 7), (10, 12), (11, 2), (11, 15), (11, 20), (12, 25)}

WEEKDAYS_PT = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def _hours_on(day: date) -> tuple[int, int] | None:
    if (day.month, day.day) in FIXED_HOLIDAYS:
        return None
    return OPENING_HOURS.get(day.weekday())


def _format(moment: datetime) -> str:
    return f"{WEEKDAYS_PT[moment.weekday()]}, {moment:%d/%m/%Y}, às {moment:%H:%M}"


class StoreClock:
    def __init__(self, fixed_now: datetime | None = None) -> None:
        self._fixed_now = fixed_now

    def now(self) -> datetime:
        if self._fixed_now is None:
            return datetime.now(STORE_TZ)
        return self._fixed_now.replace(tzinfo=STORE_TZ) if self._fixed_now.tzinfo is None else self._fixed_now.astimezone(STORE_TZ)

    def today(self) -> date:
        return self.now().date()

    def is_open(self) -> bool:
        now = self.now()
        hours = _hours_on(now.date())
        return hours is not None and hours[0] <= now.hour < hours[1]

    def next_opening(self) -> datetime:
        now = self.now()
        for offset in range(0, 15):
            day = now.date() + timedelta(days=offset)
            hours = _hours_on(day)
            if hours is None:
                continue
            opening = datetime(day.year, day.month, day.day, hours[0], tzinfo=STORE_TZ)
            if opening > now:
                return opening
        raise RuntimeError("No opening found in the next two weeks.")

    def context_line(self) -> str:
        """Trusted description of the current moment, sent to the model on each turn."""
        now = self.now()
        moment = f"Agora é {_format(now)} (horário de Campo Grande)."
        if self.is_open():
            return f"{moment} A loja está aberta."
        return f"{moment} A loja está fechada. Próxima abertura: {_format(self.next_opening())}."
