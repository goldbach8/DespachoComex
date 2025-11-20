import re
import pandas as pd
import logging

# Configuración básica de logging para capturar la salida
# En Streamlit esto se redirige a la consola de la terminal
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- FUNCIÓN AUXILIAR ---

def parse_number(num_str):
    """
    Convierte string de formato SIM ("1.234,56") a float Python (1234.56).
    """
    if not num_str:
        return None
    # 1. Eliminar separador de miles (puntos)
    s = num_str.replace('.', '')
    # 2. Reemplazar separador decimal (coma) por punto
    s = s.replace(',', '.')
    
    try:
        n = float(s)
        return n
    except ValueError:
        return None

# --- CONSTANTES DE REGEX ---

# Patrón para extraer solo NCM de 8 dígitos para la lista BK (dddd.dd.dd)
NCM_BK_PATTERN = re.compile(r'(\d{4}\.\d{2}\.\d{2})')

# Patrón para el Nro de Despacho en el encabezado
DESPACHO_PATTERN = re.compile(r'(\d{2})\s+(\d{3})\s+([A-Z0-9]{4})\s+(\d{6})\s+([A-Z])')

# Patrón para encontrar la cabecera de Item (Anclaje de Bloque)
ITEM_HEADER_PATTERN = re.compile(r'N.? Item', re.IGNORECASE)

# Patrón para el NCM completo (Posición SIM)
POSICION_PATTERN = re.compile(r'(\d{4}\.\d{2}\.\d{2}\.\d{3}[A-Z])')

# Patrón para el Monto FOB Total Divisa (global o en bloque, formato 1.234,56)
FOB_AMOUNT_PATTERN = re.compile(r'\d{1,3}(?:\.\d{3})*,\d{2}')

# Patrón para encontrar Subitems detallados 
SUBITEM_DETAILED_PATTERN = re.compile(
    r'Nro\. ítem:\s*(\d+)\s+Posición SIM:\s*([0-9\.A-Z]+)\s+Subitem Nro\.\s*:\s*(\d+)[\s\S]*?'
    r'Monto FOB:\s*(' + FOB_AMOUNT_PATTERN.pattern + r')[\s\S]*?'
    r'Sufijos de valor:[\s\S]*?AA\(\s*([^)]+?)\s*\)\s*=\s*MARCA', 
    re.IGNORECASE
)

# Columnas mínimas de salida del parser
DEFAULT_COLS = [
    'despacho', 'posicion', 'moneda', 'montoFob', 
    'proveedor', 'esSubitem', 'tieneSubitems', 'numItem', 
    'itemPrincipal'
]


# --- FUNCIÓN DE EXTRACCIÓN DE FOB GLOBAL (Validación 3) ---

def extract_global_fob_total(full_text):
    """Extrae el monto FOB Total Divisa del texto completo."""
    if not full_text:
        return None
    
    # Patrón: "FOB Total Divisa" seguido de cualquier cosa, y luego un número 
    # grande en formato SIM (con . para miles y , para decimales)
    fob_match = re.search(
        r'FOB\s*Total\s*Divisa[\s\S]*?(' + FOB_AMOUNT_PATTERN.pattern + r')\b', 
        full_text, 
        re.IGNORECASE
    )
    
    if fob_match:
        fob_str = fob_match.group(1)
        return parse_number(fob_str) 
        
    return None

# --- FUNCIÓN PRINCIPAL DE EXTRACCIÓN DE DATOS ---
def extract_data_from_pdf_text(full_text):
    """
    Procesa el texto completo del PDF de despacho SIM para extraer ítems, subítems 
    y datos globales, siguiendo la lógica de filtrado original.

    Retorna:
        pd.DataFrame: DataFrame con ítems y subítems.
        float: El monto FOB Total Divisa global.
    """
    if not full_text:
        logger.info("Texto de PDF vacío, retornando datos vacíos.")
        return pd.DataFrame(columns=DEFAULT_COLS), None

    # Normalizar saltos de línea y texto
    full_text = full_text.replace('\r\n', '\n')
    
    # 1. --- DATOS GLOBALES ---
    
    # a) Despacho
    despacho = ""
    despacho_match = DESPACHO_PATTERN.search(full_text)
    if despacho_match:
        despacho = "".join(despacho_match.groups()) 

    # b) Moneda Global
    moneda_global = "USD"
    moneda_match = re.search(r'FOB Total Divisa[\s\S]*?\b(USD|DOL|EUR|ARS)\b', full_text)
    if not moneda_match:
        moneda_match = re.search(r'\b(USD|DOL|EUR|ARS)\b', full_text)
    if moneda_match:
        moneda_global = moneda_match.group(1)

    # c) FOB Global (Validación 3)
    global_fob = extract_global_fob_total(full_text)
    logger.info(f"--- Extracción de Despacho SIM ---")
    logger.info(f"Despacho Nro: {despacho} | Moneda: {moneda_global} | FOB Total Global: {global_fob}")
    
    # 2. --- LOCALIZAR BLOQUES DE ÍTEMS PRINCIPALES ---
    starts = [m.start() for m in ITEM_HEADER_PATTERN.finditer(full_text)]
    
    data = []  # Lista para almacenar los resultados
    
    # 3. --- PROCESAR ÍTEMS PRINCIPALES ---
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(full_text)
        block = full_text[start:end]
        lines = [l.strip() for l in block.split('\n') if l.strip()]

        # 3.1) Extraer Nro de Ítem y su índice
        num_item = None
        idx_num = None
        for idx, line in enumerate(lines):
            m_num = re.match(r'^(\d{4})\s+N\b', line)
            if m_num:
                num_item = m_num.group(1)
                idx_num = idx
                break

        # 3.2) Buscar la posición SIM (NCM) en el bloque, idealmente desde la línea del ítem
        posicion = None
        if idx_num is not None:
            for li in range(idx_num, len(lines)):
                m_pos = POSICION_PATTERN.search(lines[li])
                if m_pos:
                    posicion = m_pos.group(1)
                    break

        # Fallback: buscar en todo el bloque
        if not posicion:
            for li in range(len(lines)):
                m_pos = POSICION_PATTERN.search(lines[li])
                if m_pos:
                    posicion = m_pos.group(1)
                    break

        if not posicion:
            # Si seguimos sin posición, descartamos el bloque
            continue

        # 3.3) Proveedor (marca AA(...))
        proveedor = None
        marca_match = re.search(r'AA\s*\(\s*([^)]+?)\s*\)', block)
        if marca_match:
            proveedor_str = marca_match.group(1).strip()
            if proveedor_str:
                proveedor = proveedor_str

        # 3.4) montoFob: buscar a partir de "UNIDAD"
        monto_fob = None
        idx_unidad = next((i for i, l in enumerate(lines) if "UNIDAD" in l), -1)

        numeros_str = []
        if idx_unidad != -1:
            for li in range(idx_unidad, len(lines)):
                nums_line = FOB_AMOUNT_PATTERN.findall(lines[li])
                if nums_line:
                    numeros_str.extend(nums_line)
                if len(numeros_str) >= 4:
                    break

            # Ajustar estos índices según tu layout real:
            if len(numeros_str) >= 2:
                monto_fob = parse_number(numeros_str[1])
            if len(numeros_str) >= 3:
                monto_fob = parse_number(numeros_str[1])
            if len(numeros_str) >= 4:
                monto_fob = parse_number(numeros_str[2])
            if len(numeros_str) >= 5:
                monto_fob = parse_number(numeros_str[3])

        logger.info(
            f"  [Item Principal {num_item}] Posición: {posicion}, Proveedor: '{proveedor}'. "
            f"Números (Cants/FOB): {numeros_str}. FOB Extraído: {monto_fob}."
        )

        # OJO: por ahora NO marcamos tieneSubitems; se corregirá luego
        data.append({
            'despacho': despacho,
            'posicion': posicion,
            'moneda': moneda_global,
            'montoFob': monto_fob,
            'proveedor': proveedor,
            'esSubitem': False,
            'tieneSubitems': False,   # placeholder, se recalcula después
            'numItem': num_item,
            'itemPrincipal': None,
        })

    # 4. --- PROCESAR SUBITEMS ---
    subitem_count = 0
    for sm in SUBITEM_DETAILED_PATTERN.finditer(full_text):
        nro_item_principal = sm.group(1).zfill(4)
        posicion_sub = sm.group(2).strip()
        num_subitem = sm.group(3).zfill(4)
        fob_str = sm.group(4)
        proveedor_sub_str = sm.group(5).strip()

        monto_sub_fob = parse_number(fob_str)
        proveedor_sub = proveedor_sub_str if proveedor_sub_str else None
        
        logger.info(
            f"  [Subitem {nro_item_principal}-{num_subitem}] Posición: {posicion_sub}, "
            f"Proveedor: '{proveedor_sub}'. FOB Extraído: {monto_sub_fob}"
        )
        subitem_count += 1

        data.append({
            'despacho': despacho,
            'posicion': posicion_sub,
            'moneda': moneda_global,
            'montoFob': monto_sub_fob,
            'proveedor': proveedor_sub,
            'esSubitem': True,
            'tieneSubitems': False,   # los subitems nunca "tienen subitems"
            'numItem': num_subitem,
            'itemPrincipal': nro_item_principal,
        })
    
    logger.info(f"Total de Subitems procesados: {subitem_count}")

    # 5. --- SALIDA FINAL ---
    if not data:
        return pd.DataFrame(columns=DEFAULT_COLS), global_fob

    df = pd.DataFrame(data)

    # Recalcular tieneSubitems de forma CORRECTA:
    # un ítem principal tiene subitems si existe algún registro con esSubitem=True
    # cuyo itemPrincipal == numItem de ese ítem.
    df['tieneSubitems'] = False
    if not df.empty:
        principales_con_sub = set(
            df.loc[df['esSubitem'], 'itemPrincipal'].dropna().unique()
        )
        mask_principales = (df['esSubitem'] == False) & df['numItem'].isin(principales_con_sub)
        df.loc[mask_principales, 'tieneSubitems'] = True

    return df, global_fob



# --- FUNCIÓN DE EXTRACCIÓN DE LISTA BK (Mantenida) ---

def extract_bk_list_from_pdf_text(full_text):
    """
    Extrae códigos NCM de 8 dígitos de un PDF de listado BK.
    
    Retorna:
        list: Una lista de strings de NCM limpios (8 dígitos sin puntos).
    """
    if not full_text:
        return []
        
    # Buscar todos los códigos NCM de 8 dígitos (dddd.dd.dd). 
    matches = NCM_BK_PATTERN.findall(full_text)
    
    # Limpiar y convertir a 8 dígitos sin puntos (ej. 84139190)
    cleaned_ncm = [
        ncm.replace('.', '')
        for ncm in matches
    ]
    
    return cleaned_ncm