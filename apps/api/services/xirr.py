from __future__ import annotations

from datetime import date


def _npv(rate: float, flows: list[tuple[date, float]], t0: date) -> float:
    return sum(cf / (1 + rate) ** ((d - t0).days / 365.0) for d, cf in flows)


def xirr(flows: list[tuple[date, float]]) -> float | None:
    """Annualised return (as a fraction, 0.12 = 12%) for dated cash flows; negative = money invested.
    Returns None when it is undefined (no sign change) or cannot be bracketed."""
    flows = [(d, cf) for d, cf in flows if cf]
    if len(flows) < 2:
        return None
    if not (any(cf < 0 for _, cf in flows) and any(cf > 0 for _, cf in flows)):
        return None
    t0 = min(d for d, _ in flows)
    if max(d for d, _ in flows) == t0:
        return None  # everything on one day: no time passed

    lo, hi = -0.9999, 10.0
    f_lo, f_hi = _npv(lo, flows, t0), _npv(hi, flows, t0)
    while f_lo * f_hi > 0 and hi < 1e6:
        hi *= 10
        f_hi = _npv(hi, flows, t0)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = _npv(mid, flows, t0)
        if abs(f_mid) < 1e-7:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2
