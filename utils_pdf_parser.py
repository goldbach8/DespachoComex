import re
import pandas as pd
import logging

# Configuración básica de logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- FUNCIÓN AUXILIAR ---

def parse_number(num_str):
    """Convierte string de formato SIM ("1.234,56") a float Python."""
    if not num_str: return None
    s = num_str.replace('.', '').replace(',', '.')
    try: return float(s)
    except ValueError: return None

# --- CONSTANTES DE REGEX ---

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

DEFAULT_COLS = ['despacho', 'posicion', 'moneda', 'montoFob', 'proveedor', 'esSubitem', 'tieneSubitems', 'numItem', 'itemPrincipal']

# --- FUNCIÓN: EXTRACCIÓN DE VENDEDORES (ROBUSTA V6) ---

def extract_vendors_from_first_page(first_page_text):
    if not first_page_text: return []
    lines = [l.strip() for l in first_page_text.split('\n') if l.strip()]
    vendors = []
    
    stop_keywords = ["VIA", "VÍA", "DOCUMENTO", "IDENTIFICADOR", "MANIFIESTO", "NOMBRE", "BANDERA", "PUERTO", "FECHA", "MARCAS", "EMBALAJE", "TOTAL", "PESO", "ADUANA", "SUBREGIMEN", "VALOR", "MERCADERIA", "LIQUIDACION", "INFORMACION", "NALADISA", "GATT", "AFIP", "ITEM", "POSICION", "SIM", "ESTADO", "ORIGEN", "PROCEDENCIA", "DESTINO", "UNIDAD"]
    trash_keywords = ["IMPORTE", "TASA", "DERECHOS", "PAGADO", "GARANTIZADO", "A COBRAR", "CANAL", "OFICIALIZADO", "SIM", "HOJA", "2025", "2026", "2024", "CUIT", "N°", "P/G/C", "CONCEPTOS", "KILOGRAMO", "CANTIDAD", "ESTADISTICA", "COEF.", "BASE IVA", "IMPUESTOS", "1993", "OM-1993", "FORMULARIO", "PAGINA", "DECLARACION"]

    start_idx = -1
    for i, line in enumerate(lines):
        line_upper = line.upper()
        if "VENDEDOR" in line_upper and "VARIOS" not in line_upper:
            start_idx = i
            break
    
    if start_idx != -1:
        max_lines_to_scan = 8
        scan_count = 0
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            line_upper = line.upper()
            scan_count += 1
            if scan_count > max_lines_to_scan: break
            if any(keyword in line_upper for keyword in stop_keywords): break
            if len(line) < 3: continue
            if re.search(r'\d{2}-\d{8}-\d', line): continue
            if "CUIT" in line_upper: continue
            if any(tk in line_upper for tk in trash_keywords): continue
            if re.match(r'^[A-Z0-9]+$', line) and len(line) < 8 and not any(c.isalpha() for c in line): continue

            # Separar por guiones o barras, incluso si no hay espacios (Ej: COSTEX-MIRANDA)
            parts = re.split(r'[-/]', line)
            for part in parts:
                clean_part = part.strip()
                if len(clean_part) > 2 and not any(tk in clean_part.upper() for tk in trash_keywords):
                    vendors.append(clean_part)

    clean_vendors = []
    for v in sorted(list(set(vendors))):
        if len(v) < 3: continue
        clean_vendors.append(v)
    return clean_vendors

# --- EXTRACCION DATOS GLOBALES ---

def extract_global_fob_total(full_text):
    if not full_text: return None
    fob_match = re.search(r'FOB\s*Total\s*Divisa[\s\S]*?(' + FOB_AMOUNT_PATTERN.pattern + r')\b', full_text, re.IGNORECASE)
    if fob_match: return parse_number(fob_match.group(1))
    return None

def extract_cond_venta(full_text):
    if not full_text: return None
    match = re.search(r'Cond\.?\s*Venta\s*([A-Z]{3})', full_text, re.IGNORECASE)
    if match: return match.group(1).upper()
    match_loose = re.search(r'\b(FOB|CIF|EXW|FCA|CFR|CPT|CIP|DAP|DPU|DDP|FAS)\b', full_text, re.IGNORECASE)
    if match_loose: return match_loose.group(1).upper()
    return None

# --- VALIDACIÓN DE MARCA ---

def is_valid_brand(candidate):
    """Verifica si el texto extraído es una marca válida o basura del PDF."""
    if not candidate or len(candidate) < 2: return False
    
    cand_up = candidate.upper().strip()
    
    # Lista Negra Estricta
    blacklist = [
        "ESTADOS UNIDOS", "ESTADOS", "UNIDOS", "CHINA", "ITALIA", "ALEMANIA", 
        "BRASIL", "INDIA", "JAPON", "KOREA", "COREA", "TAIWAN", "VIETNAM",
        "SIN MARCA", "MARCAS Y NUMEROS", "MARCAS Y NÚMEROS", "MARCA",
        "CODIGO", "MODELO", "CANTIDAD", "UNIDAD", "KILOGRAMO", "LITRO",
        "PRESENTACION", "NINGUNO", "NO VALIDA", "NO_VALIDA"
    ]
    
    if any(bad == cand_up for bad in blacklist): return False # Coincidencia exacta
    if any(bad in cand_up for bad in ["ESTADOS UNIDOS", "MARCAS Y"]): return False # Coincidencia parcial peligrosa
    
    return True

# --- FUNCIÓN PRINCIPAL ---

def extract_data_from_pdf_text(full_text):
    if not full_text: return pd.DataFrame(columns=DEFAULT_COLS), None, None

    full_text = full_text.replace('\r\n', '\n')
    
    despacho = ""
    m_desp = DESPACHO_PATTERN.search(full_text)
    if m_desp: despacho = "".join(m_desp.groups()) 

    moneda = "USD"
    m_mon = re.search(r'FOB Total Divisa[\s\S]*?\b(USD|DOL|EUR|ARS)\b', full_text)
    if not m_mon: m_mon = re.search(r'\b(USD|DOL|EUR|ARS)\b', full_text)
    if m_mon: moneda = m_mon.group(1)

    global_fob = extract_global_fob_total(full_text)
    cond_venta = extract_cond_venta(full_text)
    
    starts = [m.start() for m in ITEM_HEADER_PATTERN.finditer(full_text)]
    data = []
    
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

        # --- EXTRACCIÓN DE MARCA (Secuencia de Estrategias) ---
        proveedor = None
        
        # Lista de regex a probar en orden
        regex_strategies = [
            # 1. AA(MARCA) o A A(MARCA) - Estándar SIM
            r'(?:AA|A\s*A)\s*\(\s*([^)]+?)\s*\)',
            
            # 2. Inversa: (...) = MARCA o (...) MARCA
            r'\(\s*([^)]+?)\s*\)\s*(?:=|:)?\s*MARCA',
            
            # 3. Solicitud Usuario (Estrategia 4 Anterior): Texto plano "MARCA: XXX"
            # NOTA: Esto es peligroso, por eso aplicaremos validación estricta abajo.
            r'\bMARCA\s*:?\s*([A-Z0-9\.\-\s]{2,30})(?:$|\n|;)',
            
            # 4. Multilínea: AA [salto] (MARCA)
            r'(?:AA|A\s*A)\s*\n\s*\(\s*([^)]+?)\s*\)'
        ]
        
        for pattern in regex_strategies:
            # Buscamos TODAS las coincidencias en el bloque, no solo la primera
            # Esto ayuda si la primera coincidencia es basura (ej: "SIN MARCA" en un encabezado)
            matches = re.finditer(pattern, block, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                candidate = match.group(1).strip()
                
                # Limpieza de espacios internos (C A T -> CAT)
                if re.match(r'^[A-Z\s]+$', candidate) and " " in candidate:
                     compact = candidate.replace(" ", "")
                     if len(candidate) > len(compact) * 1.5: candidate = compact
                
                # VALIDACIÓN ESTRICTA
                if is_valid_brand(candidate):
                    proveedor = candidate
                    break # Encontramos una marca válida con esta estrategia
            
            if proveedor: break # Ya tenemos proveedor, no probar más estrategias

        monto_fob = None
        idx_unidad = next((i for i, l in enumerate(lines) if "UNIDAD" in l), -1)
        if idx_unidad != -1:
            numeros_str = []
            for li in range(idx_unidad, len(lines)):
                nums_line = FOB_AMOUNT_PATTERN.findall(lines[li])
                if nums_line: numeros_str.extend(nums_line)
                if len(numeros_str) >= 4: break
            
            if len(numeros_str) >= 2: monto_fob = parse_number(numeros_str[1])
            if len(numeros_str) >= 3: monto_fob = parse_number(numeros_str[1])
            if len(numeros_str) >= 4: monto_fob = parse_number(numeros_str[2])
            if len(numeros_str) >= 5: monto_fob = parse_number(numeros_str[3])

        data.append({
            'despacho': despacho,
            'posicion': posicion,
            'moneda': moneda,
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
        # Validar también el proveedor del subitem por si acaso
        proveedor_sub = proveedor_sub_str if is_valid_brand(proveedor_sub_str) else None
        
        data.append({
            'despacho': despacho,
            'posicion': posicion_sub,
            'moneda': moneda,
            'montoFob': monto_sub_fob,
            'proveedor': proveedor_sub,
            'esSubitem': True,
            'tieneSubitems': False,
            'numItem': num_subitem,
            'itemPrincipal': nro_item_principal,
        })
    
    if not data: return pd.DataFrame(columns=DEFAULT_COLS), global_fob, cond_venta

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