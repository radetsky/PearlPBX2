from django import template

register = template.Library()

@register.filter
def get_dict_item(dictionary, key):
    return dictionary.get(key)
