import re

def _normalize_ncm_to_8_digits(value):
    """
    Normaliza cualquier string que contenga un NCM a un código de 8 dígitos:
    - se quedan solo los dígitos
    - si hay 8 o más dígitos, toma los primeros 8
    """
    if not value:
        return None
    digits = re.sub(r'\D', '', str(value))
    if len(digits) < 8:
        return None
    return digits[:8]


def build_bk_set(bk_list):
    """Pre-normaliza la lista BK a un set de strings de 8 dígitos.
    Llamar una vez y reutilizar el resultado en classify_bk_fast."""
    return {_normalize_ncm_to_8_digits(ncm) for ncm in bk_list if _normalize_ncm_to_8_digits(ncm)}


def classify_bk(posicion_ncm, bk_list):
    """
    Clasifica una posición arancelaria como 'BK' o 'NO BK'.

    Args:
        posicion_ncm (str): posición completa, por ejemplo '8413.91.90.790R'.
        bk_list (iterable): lista o set de códigos BK en formato '8413.91.90' o '84139190'.

    Retorna:
        'BK' si la NCM de 8 dígitos está en la lista BK, 'NO BK' en caso contrario.
    """
    if not posicion_ncm or not bk_list:
        return 'NO BK'
    ncm_8_digits = _normalize_ncm_to_8_digits(posicion_ncm)
    if not ncm_8_digits:
        return 'NO BK'
    normalized_bk_set = build_bk_set(bk_list)
    return 'BK' if ncm_8_digits in normalized_bk_set else 'NO BK'


def classify_bk_with_set(posicion_ncm, normalized_bk_set):
    """Versión eficiente: recibe el set ya normalizado (ver build_bk_set).
    Usar cuando se clasifica múltiples filas con la misma lista BK."""
    if not posicion_ncm:
        return 'NO BK'
    ncm_8_digits = _normalize_ncm_to_8_digits(posicion_ncm)
    if not ncm_8_digits:
        return 'NO BK'
    return 'BK' if ncm_8_digits in normalized_bk_set else 'NO BK'