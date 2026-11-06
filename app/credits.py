"""API credits for the owner panel ("auto" backend). The balance can't be read
through the API (the Admin API cost report isn't available to individual
accounts), so every reply billed to the key logs its cost here, and the panel
shows API_CREDITS_TOTAL minus that: an upper bound if other apps spend the
same credits."""
import time
from datetime import date

from config import API_CREDITS_EXPIRES, API_CREDITS_TOTAL, CLAUDE_BACKEND, DATA_DIR
from i18n import LANG, t

_SPEND_FILE = DATA_DIR / "api_spend.log"


def enabled() -> bool:
    return CLAUDE_BACKEND == "auto" and API_CREDITS_TOTAL > 0


def record(cost_usd: float | None) -> None:
    """One line per reply, appended: survives restarts, no read-modify-write."""
    if cost_usd:
        with _SPEND_FILE.open("a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M')}\t{cost_usd}\n")


def spent() -> float:
    try:
        with _SPEND_FILE.open() as f:
            return sum(float(line.split("\t")[1]) for line in f if "\t" in line)
    except OSError:
        return 0.0


def _usd(x: float) -> str:
    s = f"{x:.2f}"
    return s.replace(".", ",") if LANG == "it" else s


def summary(api_key_off: bool) -> str:
    """HTML text for the panel."""
    if api_key_off:
        return t("credits_off")
    used = spent()
    left = max(API_CREDITS_TOTAL - used, 0)
    lines = [t("credits", spent=_usd(used), left=_usd(left), total=f"{API_CREDITS_TOTAL:.0f}")]
    if API_CREDITS_EXPIRES:
        days = (date.fromisoformat(API_CREDITS_EXPIRES) - date.today()).days
        lines.append(t("credits_expire", days=days) if days > 0 else t("credits_expired"))
    if left < 10:
        lines.append("\n" + t("credits_low"))
    lines.append("\n" + t("credits_note"))
    return "\n".join(lines)
