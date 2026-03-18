import re

def _normalize_ncm_to_8_digits(value):
    """
    Normaliza cualquier string que contenga un NCM a un código de 8 dígitos:
    - se quedan solo los dígitos
    - si hay 8 o más dígitos, toma los primeros 8
    """
    if not value:
        return None
    
    # Dejar solo dígitos (por si viene con puntos, letras, etc.)
    digits = re.sub(r'\D', '', str(value))
    
    if len(digits) < 8:
        # No tiene suficientes dígitos para ser NCM de 8
        return None
    
    return digits[:8]


def classify_bk(posicion_ncm, bk_list):
    """
    Clasifica una posición arancelaria como 'BK' o 'NO BK'.

    Args:
        posicion_ncm (str): posición completa, por ejemplo '8413.91.90.790R'
                            o '8413.91.90'.
        bk_list (iterable): lista o set de códigos BK, ya sea en formato
                            '8413.91.90' o '84139190'.

    Retorna:
        'BK' si la NCM de 8 dígitos está en la lista BK, 'NO BK' en caso contrario.
    """
    if not posicion_ncm or not bk_list:
        return 'NO BK'

    # Normalizar la posición a NCM de 8 dígitos (ej. '84139190')
    ncm_8_digits = _normalize_ncm_to_8_digits(posicion_ncm)

    if not ncm_8_digits:
        return 'NO BK' # No se pudo determinar la NCM de 8 dígitos

    # Normalizar la lista BK (por si viene con puntos)
    normalized_bk_set = {_normalize_ncm_to_8_digits(ncm) for ncm in bk_list if _normalize_ncm_to_8_digits(ncm)}
    
    if ncm_8_digits in normalized_bk_set:
        return 'BK'
    else:
        return 'NO BK'