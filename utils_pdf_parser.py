import re
import pandas as pd
import logging

# Configuración básica de logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- FUNCIÓN AUXILIAR ---

def parse_number(num_str):
    """
    Convierte string de formato SIM ("1.234,56") a float Python (1234.56).
    """
    if not num_str:
        return None
    s = num_str.replace('.', '')
    s = s.replace(',', '.')
    try:
        n = float(s)
        return n
    except ValueError:
        return None

# --- CONSTANTES DE REGEX ---

NCM_BK_PATTERN = re.compile(r'(\d{4}\.\d{2}\.\d{2})')
DESPACHO_PATTERN = re.compile(r'(\d{2})\s+(\d{3})\s+([A-Z0-9]{4})\s+(\d{6})\s+([A-Z])')
ITEM_HEADER_PATTERN = re.compile(r'N.? Item', re.IGNORECASE)
POSICION_PATTERN = re.compile(r'(\d{4}\.\d{2}\.\d{2}\.\d{3}[A-Z])')
FOB_AMOUNT_PATTERN = re.compile(r'\d{1,3}(?:\.\d{3})*,\d{2}')

SUBITEM_DETAILED_PATTERN = re.compile(
    r'Nro\. ítem:\s*(\d+)\s+Posición SIM:\s*([0-9\.A-Z]+)\s+Subitem Nro\.\s*:\s*(\d+)[\s\S]*?'
    r'Monto FOB:\s*(' + FOB_AMOUNT_PATTERN.pattern + r')[\s\S]*?'
    r'Sufijos de valor:[\s\S]*?AA\(\s*([^)]+?)\s*\)\s*=\s*MARCA', 
    re.IGNORECASE
)

DEFAULT_COLS = [
    'despacho', 'posicion', 'moneda', 'montoFob', 
    'proveedor', 'esSubitem', 'tieneSubitems', 'numItem', 
    'itemPrincipal'
]

# --- NUEVA FUNCIÓN: EXTRACCIÓN DE VENDEDORES (ROBUSTA V3) ---

def extract_vendors_from_first_page(first_page_text):
    """
    Extrae vendedores buscando el bloque específico 'Vendedor' en la carátula.
    Incluye lógica para separar nombres pegados y limpieza agresiva de basura.
    """
    if not first_page_text:
        return []
    
    lines = [l.strip() for l in first_page_text.split('\n') if l.strip()]
    vendors = []
    
    # Palabras clave de parada (Fin del bloque Vendedor) - AMPLIADA
    stop_keywords = [
        "VIA", "VÍA", "DOCUMENTO", "IDENTIFICADOR", "MANIFIESTO", 
        "NOMBRE", "BANDERA", "PUERTO", "FECHA", "MARCAS", 
        "EMBALAJE", "TOTAL", "PESO", "ADUANA", "SUBREGIMEN",
        "VALOR", "MERCADERIA", "LIQUIDACION", "INFORMACION",
        "NALADISA", "GATT", "AFIP", "ITEM", "POSICION", "SIM",
        "ESTADO", "ORIGEN", "PROCEDENCIA", "DESTINO", "UNIDAD"
    ]
    
    # Palabras clave de "Basura" (Líneas que NO son vendedores)
    trash_keywords = [
        "IMPORTE", "TASA", "DERECHOS", "PAGADO", "GARANTIZADO", 
        "A COBRAR", "CANAL", "OFICIALIZADO", "SIM", "HOJA", 
        "2025", "2024", "CUIT", "N°", "P/G/C", "CONCEPTOS",
        "ESTADOS UNIDOS", "KILOGRAMO", "CANTIDAD", "ESTADISTICA",
        "COEF.", "BASE IVA", "IMPUESTOS", "1993"
    ]

    # 1. ESTRATEGIA POSICIONAL (Bloque Vendedor)
    start_idx = -1
    for i, line in enumerate(lines):
        line_upper = line.upper()
        # Buscamos el encabezado exacto "Vendedor", ignorando "VARIOS VENDEDORES"
        if "VENDEDOR" in line_upper and "VARIOS" not in line_upper:
            start_idx = i
            break
    
    if start_idx != -1:
        # Escanear líneas hacia abajo desde "Vendedor"
        max_lines_to_scan = 12 # Reducido para evitar leer demasiado
        scan_count = 0
        
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            line_upper = line.upper()
            scan_count += 1
            
            if scan_count > max_lines_to_scan:
                break
            
            # Si encontramos un encabezado de parada, terminamos
            if any(keyword in line_upper for keyword in stop_keywords):
                break
            
            # --- FILTROS DE BASURA ---
            if len(line) < 3: continue
            if re.search(r'\d{2}-\d{8}-\d', line): continue # CUIT
            if "CUIT" in line_upper: continue
            if any(tk in line_upper for tk in trash_keywords): continue
            # Códigos alfanuméricos sueltos (ids internos)
            if re.match(r'^[A-Z0-9]+$', line) and len(line) < 8 and not any(c.isalpha() for c in line):
                continue

            # --- LÓGICA DE SEPARACIÓN Y EXTRACCIÓN ---
            
            # Caso Específico: "COSTEX TRACTOR PARTS MIRANDA CONSULTING"
            # A veces el PDF pierde el guion o espacio grande.
            if "COSTEX" in line_upper and "MIRANDA" in line_upper:
                 # Forzamos la separación
                 vendors.append("COSTEX TRACTOR PARTS")
                 vendors.append("MIRANDA CONSULTING")
                 continue

            # Separar si hay múltiples vendedores en una línea (separados por / o -)
            current_candidates = []
            if " / " in line:
                current_candidates = [p.strip() for p in line.split(" / ")]
            elif " - " in line and not re.search(r'\d', line): # Guión como separador de texto
                 current_candidates = [p.strip() for p in line.split(" - ")]
            else:
                current_candidates = [line]
            
            for cand in current_candidates:
                if len(cand) > 2:
                    vendors.append(cand)

    # 2. LIMPIEZA FINAL Y FORMATEO
    clean_vendors = []
    for v in sorted(list(set(vendors))):
        v_up = v.upper()
        # Filtros finales de seguridad contra basura persistente
        if any(x in v_up for x in ["OM-1993", "PAGINA", "HOJA", "DECLARACION", "LIQUIDACION"]):
            continue
        if len(v) < 3: continue
        
        clean_vendors.append(v)

    return clean_vendors

# --- FUNCIÓN DE EXTRACCIÓN DE FOB GLOBAL ---

def extract_global_fob_total(full_text):
    if not full_text: return None
    fob_match = re.search(
        r'FOB\s*Total\s*Divisa[\s\S]*?(' + FOB_AMOUNT_PATTERN.pattern + r')\b', 
        full_text, re.IGNORECASE
    )
    if fob_match:
        return parse_number(fob_match.group(1))
    return None

# --- NUEVA FUNCIÓN: EXTRACCIÓN DE CONDICIÓN DE VENTA ---

def extract_cond_venta(full_text):
    """
    Busca la condición de venta (ej. FOB, CIF, FCA, EXW) en el texto.
    Generalmente aparece como "Cond. Venta XXX".
    """
    if not full_text: return None
    
    # Patrón regex: Busca "Cond. Venta" seguido opcionalmente por espacios y captura las siguientes 3 letras mayúsculas
    match = re.search(r'Cond\.?\s*Venta\s*([A-Z]{3})', full_text, re.IGNORECASE)
    
    if match:
        return match.group(1).upper()
    
    # Intento secundario menos estricto si el formato varía
    match_loose = re.search(r'\b(FOB|CIF|EXW|FCA|CFR|CPT|CIP|DAP|DPU|DDP|FAS)\b', full_text, re.IGNORECASE)
    if match_loose:
        # Verificar que no sea parte de "FOB Total"
        start_idx = match_loose.start()
        # Miramos un poco antes para ver el contexto si es posible, o devolvemos el hallazgo si parece razonable
        # Para evitar falsos positivos con "FOB Total", simplemente devolvemos lo encontrado
        # pero la lógica de app.py manejará la validación.
        return match_loose.group(1).upper()
        
    return None

# --- FUNCIÓN PRINCIPAL DE EXTRACCIÓN DE DATOS ---

def extract_data_from_pdf_text(full_text):
    """
    Retorna: DataFrame, global_fob, cond_venta
    """
    if not full_text:
        return pd.DataFrame(columns=DEFAULT_COLS), None, None

    full_text = full_text.replace('\r\n', '\n')
    
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

    # c) FOB Global
    global_fob = extract_global_fob_total(full_text)

    # d) Condición de Venta (NUEVO)
    cond_venta = extract_cond_venta(full_text)
    
    # 2. --- LOCALIZAR BLOQUES ---
    starts = [m.start() for m in ITEM_HEADER_PATTERN.finditer(full_text)]
    data = []
    
    # 3. --- ÍTEMS PRINCIPALES ---
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(full_text)
        block = full_text[start:end]
        lines = [l.strip() for l in block.split('\n') if l.strip()]

        num_item = None
        idx_num = None
        for idx, line in enumerate(lines):
            m_num = re.match(r'^(\d{4})\s+N\b', line)
            if m_num:
                num_item = m_num.group(1)
                idx_num = idx
                break

        posicion = None
        if idx_num is not None:
            for li in range(idx_num, len(lines)):
                m_pos = POSICION_PATTERN.search(lines[li])
                if m_pos:
                    posicion = m_pos.group(1)
                    break
        if not posicion:
            for li in range(len(lines)):
                m_pos = POSICION_PATTERN.search(lines[li])
                if m_pos:
                    posicion = m_pos.group(1)
                    break

        if not posicion: continue

        proveedor = None
        marca_match = re.search(r'AA\s*\(\s*([^)]+?)\s*\)', block)
        if marca_match:
            proveedor = marca_match.group(1).strip()

        monto_fob = None
        idx_unidad = next((i for i, l in enumerate(lines) if "UNIDAD" in l), -1)
        numeros_str = []
        if idx_unidad != -1:
            for li in range(idx_unidad, len(lines)):
                nums_line = FOB_AMOUNT_PATTERN.findall(lines[li])
                if nums_line:
                    numeros_str.extend(nums_line)
                if len(numeros_str) >= 4: break
            
            if len(numeros_str) >= 2: monto_fob = parse_number(numeros_str[1])
            if len(numeros_str) >= 3: monto_fob = parse_number(numeros_str[1])
            if len(numeros_str) >= 4: monto_fob = parse_number(numeros_str[2])
            if len(numeros_str) >= 5: monto_fob = parse_number(numeros_str[3])

        data.append({
            'despacho': despacho,
            'posicion': posicion,
            'moneda': moneda_global,
            'montoFob': monto_fob,
            'proveedor': proveedor,
            'esSubitem': False,
            'tieneSubitems': False,
            'numItem': num_item,
            'itemPrincipal': None,
        })

    # 4. --- SUBITEMS ---
    for sm in SUBITEM_DETAILED_PATTERN.finditer(full_text):
        nro_item_principal = sm.group(1).zfill(4)
        posicion_sub = sm.group(2).strip()
        num_subitem = sm.group(3).zfill(4)
        fob_str = sm.group(4)
        proveedor_sub_str = sm.group(5).strip()

        monto_sub_fob = parse_number(fob_str)
        proveedor_sub = proveedor_sub_str if proveedor_sub_str else None
        
        data.append({
            'despacho': despacho,
            'posicion': posicion_sub,
            'moneda': moneda_global,
            'montoFob': monto_sub_fob,
            'proveedor': proveedor_sub,
            'esSubitem': True,
            'tieneSubitems': False,
            'numItem': num_subitem,
            'itemPrincipal': nro_item_principal,
        })
    
    # 5. --- SALIDA ---
    if not data:
        return pd.DataFrame(columns=DEFAULT_COLS), global_fob, cond_venta

    df = pd.DataFrame(data)
    df['tieneSubitems'] = False
    if not df.empty:
        principales_con_sub = set(df.loc[df['esSubitem'], 'itemPrincipal'].dropna().unique())
        mask_principales = (df['esSubitem'] == False) & df['numItem'].isin(principales_con_sub)
        df.loc[mask_principales, 'tieneSubitems'] = True

    return df, global_fob, cond_venta

def extract_bk_list_from_pdf_text(full_text):
    if not full_text: return []
    matches = NCM_BK_PATTERN.findall(full_text)
    return [ncm.replace('.', '') for ncm in matches]