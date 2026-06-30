from django import template

register = template.Library()


@register.filter
def bootstrap_alert(tag):
    return {"error": "danger"}.get(tag, tag or "info")
