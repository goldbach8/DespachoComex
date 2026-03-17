import streamlit as st
import pandas as pd
import io
from datetime import datetime
import json
import os
from pypdf import PdfReader 

# --- Importar módulos y utilidades ---
from initial_data import INITIAL_BK_LIST, INITIAL_DATE, INITIAL_SUPPLIERS
from utils_pdf_parser import extract_data_from_pdf_text, extract_bk_list_from_pdf_text, extract_vendors_from_first_page
from utils_data import get_grouped_data, generate_provider_summary
from utils_bk import classify_bk, build_bk_set, classify_bk_with_set

# --- CONFIGURACIÓN DE RUTAS ---
BK_LIST_PATH = "bk_list.json"
SUPPLIERS_PATH = "suppliers.json"

# --- ESTILOS CSS PERSONALIZADOS ---
def load_css():
    st.markdown("""
    <style>
        .step-container {
            display: flex;
            justify-content: space-between;
            margin-bottom: 2rem;
            background-color: #f0f2f6;
            padding: 15px;
            border-radius: 10px;
        }
        .step-item {
            text-align: center;
            font-weight: bold;
            color: #a3a8b8;
            flex: 1;
            position: relative;
        }
        .step-item.active {
            color: #0080ff;
            border-bottom: 3px solid #0080ff;
        }
        .step-item.completed {
            color: #28a745;
        }
        .stDataFrame { border: 1px solid #ddd; border-radius: 5px; }
        div[data-testid="stMetricValue"] { font-size: 1.4rem !important; }
        
        /* Estilo para alerta de Condición de Venta */
        .metric-alert-box {
            padding: 10px;
            border-radius: 5px;
            font-weight: bold;
            text-align: center;
        }
        .alert-red {
            background-color: #ffcccc;
            color: #cc0000;
            border: 1px solid #cc0000;
        }
        .alert-green {
            background-color: #ccffcc;
            color: #006600;
            border: 1px solid #006600;
        }
        
        /* Estilo para validación */
        .validation-warning {
            background-color: #fff3cd;
            color: #856404;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #ffeeba;
            margin-bottom: 15px;
        }
    </style>
    """, unsafe_allow_html=True)

def render_stepper(current_step):
    steps = {1: "1. Carga", 2: "2. Validación", 3: "3. Mapeo", 4: "4. Resultados"}
    html = '<div class="step-container">'
    for step_num, label in steps.items():
        class_name = "step-item"
        if step_num < current_step:
            class_name += " completed"; label = "✔ " + label
        elif step_num == current_step:
            class_name += " active"
        html += f'<div class="{class_name}">{label}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# --- UTILIDADES DE PERSISTENCIA ---
def load_list_from_json(path, fallback_list):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list): return data
            if isinstance(data, set): return sorted(list(data))
        except Exception: pass
    initial_list = sorted(list(set(fallback_list)))
    save_list_to_json(path, initial_list)
    return initial_list

def save_list_to_json(path, data_list):
    try:
        list_to_save = sorted(list(set(data_list))) 
        with open(path, "w", encoding="utf-8") as f:
            json.dump(list_to_save, f, indent=4)
    except Exception as e:
        st.error(f"Error al guardar {path}: {e}")

# --- GESTIÓN DE ESTADO ---
def next_step(step):
    st.session_state.app_step = step

def reset_app():
    st.session_state.pdf_reader = None
    st.session_state.pdf_data_loaded = False
    st.session_state.pdf_filename = ""
    st.session_state.data_items = pd.DataFrame()
    st.session_state.proveedor_mapping = {}
    st.session_state.referencia = ""
    st.session_state.global_fob_total = None
    st.session_state.cond_venta = None
    st.session_state.df_validation_fob = pd.DataFrame()
    st.session_state.df_results_grouped = pd.DataFrame()
    st.session_state.detected_vendors = []
    st.session_state.app_step = 1

def initialize_session_state():
    if 'app_step' not in st.session_state: reset_app()
    if 'bk_list' not in st.session_state:
        st.session_state.bk_list = load_list_from_json(BK_LIST_PATH, INITIAL_BK_LIST)
    if 'bk_list_date' not in st.session_state:
        st.session_state.bk_list_date = INITIAL_DATE 
    if 'known_suppliers' not in st.session_state:
        st.session_state.known_suppliers = load_list_from_json(SUPPLIERS_PATH, INITIAL_SUPPLIERS)

# --- CONFIGURACIÓN INICIAL ---
st.set_page_config(page_title="Despachos - NCM", layout="wide", initial_sidebar_state="collapsed")
load_css()
initialize_session_state()

st.title("🗃️ Despachos - NCM")
render_stepper(st.session_state.app_step)

# --- SIDEBAR ---
with st.sidebar:
    st.header("Configuración")
    if st.button("🔄 Reiniciar Proceso"):
        reset_app(); st.rerun()
    
    with st.expander("Base de Datos BK"):
        st.caption(f"Actualizado: {st.session_state.bk_list_date}")
        bk_file = st.file_uploader("Actualizar Listado BK (PDF)", type=["pdf"])
        if bk_file and st.button("Aplicar Actualización BK"):
            try:
                reader = PdfReader(bk_file)
                text = "\n".join([p.extract_text() for p in reader.pages])
                new_list = extract_bk_list_from_pdf_text(text)
                if new_list:
                    st.session_state.bk_list = sorted(list(set(new_list)))
                    save_list_to_json(BK_LIST_PATH, st.session_state.bk_list)
                    st.session_state.bk_list_date = datetime.now().strftime("%d-%m-%Y")
                    st.success(f"BK Actualizado: {len(new_list)} códigos.")
            except Exception as e:
                st.error(f"Error: {e}")

# ==============================================================================
# PASO 1: CARGA
# ==============================================================================
if st.session_state.app_step == 1:
    st.markdown("### 📤 Carga del Documento")
    col1, col2 = st.columns([2, 1])
    with col1:
        sim_file = st.file_uploader("Arrastra o selecciona el PDF del Despacho SIM", type=["pdf"])
    with col2:
        st.info("El sistema extraerá automáticamente los ítems y detectará los vendedores declarados en la carátula.")

    if sim_file:
        if st.button("Procesar PDF", type="primary", use_container_width=True):
            with st.spinner("Analizando estructura del PDF..."):
                try:
                    reader = PdfReader(sim_file)
                    st.session_state.pdf_reader = reader
                    
                    full_text_pages = [p.extract_text() for p in reader.pages]
                    full_text = "\n".join(full_text_pages)
                    
                    df_items, global_fob, cond_venta = extract_data_from_pdf_text(full_text)
                    
                    first_page_text = full_text_pages[0] if full_text_pages else ""
                    detected_vendors = extract_vendors_from_first_page(first_page_text)
                    
                    if df_items.empty:
                        st.error("No se encontraron datos. Verifique el PDF.")
                    else:
                        st.session_state.data_items = df_items
                        st.session_state.global_fob_total = global_fob
                        st.session_state.cond_venta = cond_venta
                        st.session_state.pdf_data_loaded = True
                        st.session_state.pdf_filename = sim_file.name
                        st.session_state.detected_vendors = detected_vendors
                        
                        if detected_vendors:
                            st.toast(f"🏢 Se detectaron {len(detected_vendors)} vendedores en carátula.")
                        
                        next_step(2)
                        st.rerun()
                except Exception as e:
                    st.error(f"Error crítico: {e}")

# ==============================================================================
# PASO 2: VALIDACIÓN Y EDICIÓN
# ==============================================================================
elif st.session_state.app_step == 2:
    st.markdown("### 🛡️ Validación de Datos Crudos")
    if st.session_state.data_items.empty:
        st.warning("Sin datos."); st.stop()
    
    df_work = st.session_state.data_items.copy()

    # Mostrar métricas de extracción
    n_principales = len(df_work[df_work['esSubitem'] == False])
    n_subitems = len(df_work[df_work['esSubitem'] == True])
    n_con_sub = len(df_work[df_work['tieneSubitems'] == True])
    fob_sum = df_work[(df_work['esSubitem'] == True) | ((df_work['esSubitem'] == False) & (df_work['tieneSubitems'] == False))]['montoFob'].sum()
    global_fob = st.session_state.get('global_fob_total')

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ítems principales", n_principales)
    c2.metric("Sub-ítems", n_subitems)
    c3.metric("Ítems con sub-ítems", n_con_sub)
    if global_fob:
        delta = round(fob_sum - global_fob, 2)
        c4.metric("FOB extraído", f"{fob_sum:,.2f}", delta=f"{delta:,.2f} vs PDF")
    else:
        c4.metric("FOB extraído", f"{fob_sum:,.2f}")
    st.markdown("---")

    # Filtrar solo items relevantes
    mask_relevant = (df_work['esSubitem'] == True) | ((df_work['esSubitem'] == False) & (df_work['tieneSubitems'] == False))
    
    # Identificar errores
    mask_fob_error = mask_relevant & df_work['montoFob'].isna()
    mask_brand_error = mask_relevant & (df_work['proveedor'].isna() | (df_work['proveedor'] == ''))
    mask_error = mask_fob_error | mask_brand_error
    
    df_errors = df_work[mask_error].copy()
    st.markdown("---")
    st.markdown("### ⚖️ Validación Cruzada: Ítems vs. Subítems")
    
    # 1. Identificar Ítems Principales que tienen estructura de subítems
    parents_with_subs = df_work[df_work['tieneSubitems'] == True]
    
    inconsistencies = []
    
    # 2. Iterar y comparar
    for _, parent in parents_with_subs.iterrows():
        p_item = parent['numItem']
        # Asegurar float, tratar NaN como 0
        p_fob = float(parent['montoFob']) if pd.notna(parent['montoFob']) else 0.0
        
        # Filtrar los hijos correspondientes a este padre
        children = df_work[
            (df_work['esSubitem'] == True) & 
            (df_work['itemPrincipal'] == p_item)
        ]
        
        # Calcular suma de hijos
        c_fob_sum = children['montoFob'].sum()
        c_count = len(children)
        
        # Calcular diferencia
        diff = p_fob - c_fob_sum
        
        # Si la diferencia es mayor a 1 centavo (para evitar errores de float), reportar
        if abs(diff) > 0.01:
            inconsistencies.append({
                "Item": p_item,
                "FOB Principal": p_fob,
                "Suma Subítems": c_fob_sum,
                "Diferencia": round(diff, 2),
                "Cant. Subítems Leídos": c_count
            })
    
    # 3. Mostrar resultados
    if inconsistencies:
        df_inc = pd.DataFrame(inconsistencies)
        
        st.error(
            f"⚠️ **Diferencia Detectada:** Se encontraron {len(df_inc)} ítems donde la suma de sus partes no coincide con el total declarado."
        )
        
        st.dataframe(
            df_inc.style.format({
                "FOB Principal": "{:,.2f}",
                "Suma Subítems": "{:,.2f}",
                "Diferencia": "{:,.2f}"
            }),
            use_container_width=True,
            hide_index=True
        )
        
        st.info(
            """
            **Diagnóstico:**
            * Si la **Diferencia es positiva** (ej: 500.00), significa que faltan subítems por leer (probablemente cortados por salto de página).
            * Si la **Diferencia es negativa**, puede haber un error leyendo un monto (ej: leer cantidad como precio).
            """
        )
    else:
        st.success("✅ **Validación Exitosa:** La suma de todos los subítems coincide perfectamente con sus ítems principales.")
        
    if not df_errors.empty:
        # Calcular contadores
        count_fob = df_errors['montoFob'].isna().sum()
        count_brand = (df_errors['proveedor'].isna() | (df_errors['proveedor'] == '')).sum()
        
        st.markdown(
            f"""
            <div class="validation-warning">
                <h4>⚠️ Atención Requerida</h4>
                <p>Se encontraron <strong>{len(df_errors)}</strong> registros incompletos que necesitan corrección manual:</p>
                <ul>
                    <li><strong>{count_fob}</strong> ítems sin valor FOB (Precio).</li>
                    <li><strong>{count_brand}</strong> ítems sin Marca/Proveedor.</li>
                </ul>
                <p>Por favor, completa los campos resaltados en la tabla inferior.</p>
            </div>
            """, 
            unsafe_allow_html=True
        )
        
        # Preparar dataframe para edición
        df_to_edit = df_errors[['numItem', 'posicion', 'montoFob', 'proveedor']].copy()
        
        # Agregar columna visual de estado para guiar al usuario
        # (Aunque data_editor no muestra colores condicionales en celdas, podemos usar esto)
        
        edited_df = st.data_editor(
            df_to_edit,
            column_config={
                "numItem": st.column_config.TextColumn("Item", disabled=True, help="Número de ítem en el despacho"),
                "posicion": st.column_config.TextColumn("Posición NCM", disabled=True),
                "montoFob": st.column_config.NumberColumn(
                    "Monto FOB ✏️", 
                    required=True, 
                    min_value=0.0, 
                    format="%.2f",
                    help="Este campo es obligatorio. Ingrese el valor FOB."
                ),
                "proveedor": st.column_config.TextColumn(
                    "Marca/Proveedor ✏️", 
                    required=True,
                    help="Este campo es obligatorio. Ingrese la marca."
                ),
            },
            use_container_width=True,
            key="editor_validation_raw",
            hide_index=True
        )
        
        col_v1, col_v2 = st.columns([1, 1])
        if col_v1.button("⬅️ Volver a Carga"):
            reset_app(); st.rerun()
            
        # Validación antes de avanzar
        if col_v2.button("✅ Guardar Correcciones y Continuar", type="primary"):
            # Verificar si aún quedan nulos en lo editado
            still_missing_fob = edited_df['montoFob'].isna().any()
            still_missing_brand = (edited_df['proveedor'].isna() | (edited_df['proveedor'] == '')).any()
            
            if still_missing_fob or still_missing_brand:
                st.error("❌ Aún hay campos vacíos en la tabla. Por favor complétalos todos para continuar.")
            else:
                for idx, row in edited_df.iterrows():
                    st.session_state.data_items.at[idx, 'montoFob'] = row['montoFob']
                    st.session_state.data_items.at[idx, 'proveedor'] = str(row['proveedor']).strip().upper()
                next_step(3); st.rerun()
    else:
        st.success("✅ Todos los datos obligatorios (FOB y Marca) están completos.")
        if st.button("Continuar al Mapeo", type="primary"):
            next_step(3); st.rerun()

# ==============================================================================
# PASO 3: MAPEO DE PROVEEDORES
# ==============================================================================
elif st.session_state.app_step == 3:
    st.markdown("### 🏷️ Mapeo de Proveedores")
    
    unique_marcas = sorted([m for m in st.session_state.data_items['proveedor'].dropna().unique() if m])
    new_mapping = {}
    
    detected = st.session_state.get('detected_vendors', [])
    known = st.session_state.known_suppliers
    known_filtered = sorted([k for k in known if k not in detected])
    options = ['-- Ignorar/Original --'] + detected + ['--- Otros Históricos ---'] + known_filtered
    
    if detected:
        st.info(f"🏢 Se identificaron los siguientes proveedores en el despacho: **{', '.join(detected)}**")
    else:
        st.info("No se detectaron proveedores específicos en la carátula (usando histórico general).")

    col_ref, col_info = st.columns([1, 2])
    with col_ref:
        ref_input = st.text_input("Referencia del Despacho (Ej: R550)", value=st.session_state.referencia)
    
    with st.container(border=True):
        cols = st.columns(3)
        for i, marca in enumerate(unique_marcas):
            col = cols[i % 3]
            default_idx = 0
            if marca in options:
                default_idx = options.index(marca)
            
            sel = col.selectbox(f"Marca: {marca}", options, index=default_idx, key=f"map_{i}")
            
            if sel == '-- Ignorar/Original --':
                custom = col.text_input(f"¿Nuevo para {marca}?", key=f"new_{i}").strip().upper()
                new_mapping[marca] = custom if custom else marca
            elif sel == '--- Otros Históricos ---':
                new_mapping[marca] = marca 
            else:
                new_mapping[marca] = sel

    col_b1, col_b2 = st.columns([1, 5])
    if col_b1.button("Atrás"):
        next_step(2); st.rerun()
    
    if col_b2.button("Confirmar Mapeo y Generar Reporte", type="primary"):
        if not ref_input:
            st.toast("⚠️ Ingresa una referencia para continuar.")
        else:
            st.session_state.referencia = ref_input.upper()
            st.session_state.proveedor_mapping = new_mapping
            
            new_sups = {v for v in new_mapping.values() if v and v not in options}
            if new_sups:
                st.session_state.known_suppliers = sorted(list(set(st.session_state.known_suppliers) | new_sups))
                save_list_to_json(SUPPLIERS_PATH, st.session_state.known_suppliers)
            
            next_step(4); st.rerun()

# ==============================================================================
# PASO 4: RESULTADOS
# ==============================================================================
elif st.session_state.app_step == 4:
    st.markdown(f"### 📊 Reporte Final: {st.session_state.referencia}")
    try:
        grouped_data = get_grouped_data(st.session_state.data_items, st.session_state.proveedor_mapping)
        bk_set = build_bk_set(st.session_state.bk_list)
        grouped_data['Clasificación BK'] = grouped_data['Posición'].apply(lambda p: classify_bk_with_set(p, bk_set))
        grouped_data['BK'] = grouped_data['Clasificación BK'].apply(lambda x: 'X' if x == 'BK' else '')
        grouped_data['NO BK'] = grouped_data['Clasificación BK'].apply(lambda x: 'X' if x == 'NO BK' else '')
        
        cols_final = ['Despacho Nro', 'Posición', 'Moneda', 'Monto Total de la Posición Arancelaria', 'BK', 'NO BK', 'Proveedor']
        df_final = grouped_data[cols_final]
        df_summary = generate_provider_summary(df_final)

        # Métricas
        global_fob_pdf = st.session_state.get('global_fob_total')
        cond_venta = st.session_state.get('cond_venta', 'DESC') 
        
        total_grouped_fob = df_final['Monto Total de la Posición Arancelaria'].sum()
        moneda = df_final['Moneda'].iloc[0] if not df_final.empty else "USD"
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        col_m1.metric("Suma FOB Items", f"{total_grouped_fob:,.2f} {moneda}")
        
        if global_fob_pdf is not None:
            delta = total_grouped_fob - global_fob_pdf
            if abs(delta) < 0.01:
                delta_color = "off"
            else:
                delta_color = "inverse" if delta > 0 else "normal"

            col_m2.metric(
                label="FOB Global (PDF)", 
                value=f"{global_fob_pdf:,.2f} {moneda}", 
                delta=f"{delta:,.2f} Diff", 
                delta_color=delta_color)
        else:
            col_m2.metric("FOB Global (PDF)", "No detectado")
            
        col_m3.metric("Proveedores", len(df_summary))
        
        # MÉTRICA DE CONDICIÓN DE VENTA CON ALERTA VISUAL
        # MÉTRICA DE CONDICIÓN DE VENTA (LÓGICA TRI-ESTADO: Gris, Verde, Rojo)
        with col_m4:
            raw_cond = st.session_state.get('cond_venta')
            
            if raw_cond:
                cond_str = str(raw_cond).strip().upper()
                if cond_str == 'FOB':
                    # Caso ideal: Verde
                    st.markdown(
                        f"""
                        <div class="metric-alert-box alert-green">
                            Cond. Venta<br><span style="font-size: 1.4rem;">{cond_str}</span>
                        </div>
                        """, unsafe_allow_html=True
                    )
                else:
                    # Cualquier otro valor (ej. FCA): Rojo
                    st.markdown(
                        f"""
                        <div class="metric-alert-box alert-red">
                            Cond. Venta<br><span style="font-size: 1.4rem;">{cond_str}</span>
                        </div>
                        """, unsafe_allow_html=True
                    )
            else:
                # No encontrado: Gris
                st.markdown(
                    """
                    <div class="metric-alert-box" style="background-color: #f0f2f6; color: #6c757d; border: 1px solid #d1d5db;">
                        Cond. Venta<br><span style="font-size: 1.2rem;">NO IDENTIFICADO</span>
                    </div>
                    """, unsafe_allow_html=True
                )
        
        st.markdown("---")
        st.subheader("📋 Resumen por Proveedor y % BK")
        st.dataframe(
            df_summary.style.format({"FOB Total": "{:,.2f}", "FOB BK": "{:,.2f}", "% BK": "{:.1f}%"}),
            use_container_width=True,
            hide_index=True
        )

        st.subheader("📑 Detalle Agrupado por Posición")
        st.dataframe(df_final, use_container_width=True, hide_index=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_final.to_excel(writer, sheet_name='Detalle', index=False)
            df_summary.to_excel(writer, sheet_name='Resumen_Proveedores', index=False)

            wb = writer.book
            fmt_num = wb.add_format({'num_format': '#,##0.00'})
            fmt_pct = wb.add_format({'num_format': '0.0"%"'})
            fmt_header = wb.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})

            ws_det = writer.sheets['Detalle']
            ws_det.set_column('A:A', 18)   # Despacho Nro
            ws_det.set_column('B:B', 22)   # Posición
            ws_det.set_column('C:C', 10)   # Moneda
            ws_det.set_column('D:D', 30, fmt_num)  # Monto
            ws_det.set_column('E:F', 8)    # BK / NO BK
            ws_det.set_column('G:G', 25)   # Proveedor

            ws_sum = writer.sheets['Resumen_Proveedores']
            ws_sum.set_column('A:A', 30)   # Proveedor
            ws_sum.set_column('B:C', 15, fmt_num)  # FOB Total, FOB BK
            ws_sum.set_column('D:D', 10, fmt_pct)  # % BK

        st.download_button(
            "📥 Descargar Excel Completo (.xlsx)",
            data=buffer,
            file_name=f"COM7466 - {st.session_state.referencia}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )
        
        if st.button("🔄 Iniciar Nuevo Análisis"):
            reset_app(); st.rerun()
            
    except Exception as e:
        st.error(f"Error al generar el reporte: {e}"); st.exception(e)