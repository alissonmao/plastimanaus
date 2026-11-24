from django import template

register = template.Library()


def _br(v, casas):
    s = f"{float(v):,.{casas}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


@register.filter
def brl(v):
    return "" if v in (None, "") else f"R$ {_br(v, 2)}"


@register.filter
def num(v, casas=2):
    return "" if v in (None, "") else _br(v, int(casas))


@register.filter
def pct(v, casas=1):
    return "—" if v in (None, "") else f"{_br(float(v) * 100, int(casas))}%"


@register.filter
def item(d, k):
    return d.get(k) if hasattr(d, "get") else d[k]
