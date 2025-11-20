import streamlit as st
import pandas as pd
import io
import re
from datetime import datetime
import json
import os
from pypdf import PdfReader 

# --- Importar módulos y utilidades refactorizadas ---
from initial_data import INITIAL_BK_LIST, INITIAL_DATE, INITIAL_SUPPLIERS
from utils_pdf_parser import extract_data_from_pdf_text, extract_bk_list_from_pdf_text
from utils_data import get_grouped_data
from utils_bk import classify_bk 

# --- CONFIGURACIÓN DE RUTAS ---
BK_LIST_PATH = "bk_list.json"
SUPPLIERS_PATH = "suppliers.json"

# --- UTILIDADES DE PERSISTENCIA ---

def load_list_from_json(path: str, fallback_list):
    """Carga una lista desde un JSON si existe; si no, devuelve la lista de fallback."""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            if isinstance(data, set):
                return sorted(list(data))
        except Exception:
            pass # Si falla, usamos el fallback
    
    # Aseguramos que el fallback sea una lista y lo persistimos para futuros usos
    initial_list = sorted(list(set(fallback_list)))
    save_list_to_json(path, initial_list)
    return initial_list

def save_list_to_json(path: str, data_list):
    """Guarda una lista en un archivo JSON."""
    try:
        # Aseguramos que data_list sea una lista y eliminamos duplicados antes de guardar
        list_to_save = sorted(list(set(data_list))) 
        with open(path, "w", encoding="utf-8") as f:
            json.dump(list_to_save, f, indent=4)
    except Exception as e:
        st.error(f"Error al guardar los datos en {path}: {e}")

# --- UTILIDADES DE FLUJO DE APLICACIÓN ---

def next_step(step):
    """Avanza al siguiente paso de la aplicación."""
    st.session_state.app_step = step

def reset_app():
    """Resetea el estado para comenzar un nuevo proceso."""
    st.session_state.pdf_reader = None
    st.session_state.pdf_data_loaded = False
    st.session_state.data_items = pd.DataFrame()
    st.session_state.proveedor_mapping = {}
    st.session_state.referencia = ""
    st.session_state.global_fob_total = None
    st.session_state.df_revision_manual = pd.DataFrame() # Limpiar revisión
    st.session_state.df_validation_fob = pd.DataFrame() # Limpiar validación FOB
    next_step(1)

def initialize_session_state():
    """Inicializa el estado de la sesión si es la primera vez."""
    if 'app_step' not in st.session_state:
        reset_app()
    
    # Carga o inicializa la lista BK
    if 'bk_list' not in st.session_state:
        st.session_state.bk_list = load_list_from_json(BK_LIST_PATH, INITIAL_BK_LIST)
    if 'bk_list_date' not in st.session_state:
        st.session_state.bk_list_date = INITIAL_DATE 

    # Carga o inicializa la lista de proveedores conocidos
    if 'known_suppliers' not in st.session_state:
        st.session_state.known_suppliers = load_list_from_json(SUPPLIERS_PATH, INITIAL_SUPPLIERS)
    
    if 'df_revision_manual' not in st.session_state:
        st.session_state.df_revision_manual = pd.DataFrame()
        
    if 'df_validation_fob' not in st.session_state:
        st.session_state.df_validation_fob = pd.DataFrame()

# --- CONFIGURACIÓN E INICIALIZACIÓN DE STREAMLIT ---

st.set_page_config(
    page_title="Analizador de Despachos SIM",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Aplicar estilo de barra de progreso
st.markdown("""
    <style>
    .stProgress > div > div > div > div {
        background-color: #0080ff; /* Color azul */
    }
    </style>
    """, unsafe_allow_html=True)

initialize_session_state()

# --- BARRA LATERAL (SIDEBAR) ---

with st.sidebar:
    st.title("⚙️ Configuración")
    st.header("Flujo de Trabajo")
    
    # Barra de progreso basada en el paso actual
    step_labels = {1: "Carga", 2: "Mapeo", 3: "Resultados"}
    current_step = st.session_state.app_step
    
    # Muestra los pasos con un emoji que indica el estado
    for step, label in step_labels.items():
        if step < current_step:
            st.markdown(f"**✅ {label}**")
        elif step == current_step:
            st.markdown(f"**➡️ {label}**")
        else:
            st.markdown(f"**◻️ {label}**")

    # Botón para reiniciar
    if st.button("🔄 Comenzar de Nuevo"):
        reset_app()
        st.rerun()

    st.markdown("---")
    st.header("Lista de Bienes de Capital (BK)")
    st.info(f"Última actualización: {st.session_state.bk_list_date}")
    
    # Sección para actualizar la lista BK
    with st.expander("Actualizar Lista BK"):
        bk_file = st.file_uploader(
            "Subir PDF con el listado BK actualizado", 
            type=["pdf"], 
            key="bk_update_uploader"
        )
        if bk_file:
            if st.button("Aplicar Actualización BK"):
                try:
                    pdf_reader_bk = PdfReader(bk_file)
                    full_text_pages = [page.extract_text() for page in pdf_reader_bk.pages]
                    full_text = "\n".join(full_text_pages)
                    
                    # Extraer la nueva lista BK (Función importada)
                    new_bk_list = extract_bk_list_from_pdf_text(full_text)
                    
                    if not new_bk_list:
                        st.error("No se pudieron extraer códigos NCM de 8 dígitos válidos del nuevo PDF. Revise el formato.")
                    else:
                        # 1) Actualizamos el listado activo en memoria
                        st.session_state.bk_list = sorted(list(set(new_bk_list)))

                        # 2) Persistimos en disco para que quede como "último listado BK"
                        save_list_to_json(BK_LIST_PATH, st.session_state.bk_list)

                        # 3) Actualizamos la fecha de última actualización
                        st.session_state.bk_list_date = datetime.now().strftime("%d-%m-%Y %H:%M:%S")

                        # 4) Feedback al usuario
                        st.success(
                            f"¡Listado BK actualizado con éxito desde el último PDF subido! "
                            f"Nuevo total de códigos: **{len(st.session_state.bk_list)}**."
                        )
                        st.balloons()
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"Ocurrió un error al procesar el PDF de actualización: {e}")

# --- CONTENIDO PRINCIPAL ---

st.title("🗃️ Analizador y Clasificador de Despachos SIM")
st.markdown("Siga los tres pasos para obtener el reporte agrupado por proveedor y posición arancelaria.")

# --- PASO 1: CARGA DEL ARCHIVO ---
st.header("1. Carga del Despacho SIM")
if st.session_state.app_step == 1:
    sim_file = st.file_uploader(
        "Subir PDF de Despacho SIM", 
        type=["pdf"], 
        key="sim_uploader"
    )

    if sim_file:
        if st.button("Procesar Archivo PDF", type="primary"):
            try:
                # Almacenar el lector PDF
                pdf_reader = PdfReader(sim_file)
                st.session_state.pdf_reader = pdf_reader

                # Lee el texto de todas las páginas
                full_text_pages = [page.extract_text() for page in st.session_state.pdf_reader.pages]
                full_text = "\n".join(full_text_pages)
                
                # El parser ahora retorna el DataFrame y el FOB Global
                df_items, global_fob = extract_data_from_pdf_text(full_text)
                
                st.session_state.data_items = df_items
                st.session_state.global_fob_total = global_fob 

                if st.session_state.data_items.empty:
                    st.error("No se pudieron extraer ítems del PDF. Revise el formato del archivo.")
                else:
                    st.session_state.app_step = 2 # Avanza al paso 2
                    st.session_state.pdf_data_loaded = True
                    st.success(f"Archivo cargado y **{len(st.session_state.data_items)}** ítems extraídos. ¡Listo para mapear!")
                    st.rerun()
                    
            except Exception as e:
                st.error(f"Ocurrió un error al procesar el PDF: {e}")
                st.exception(e)
elif st.session_state.app_step > 1:
    st.success(f"Archivo procesado. **{len(st.session_state.data_items)}** ítems extraídos.")
    if st.button("Volver a Cargar Archivo"):
        reset_app()
        st.rerun()

st.markdown("---")

# --- PASO 2: MAPEO DE PROVEEDORES ---
st.header("2. Mapeo de Marcas a Proveedores")
if st.session_state.app_step == 2:
    if st.session_state.data_items.empty:
        st.warning("Debe cargar un archivo en el Paso 1 para continuar.")
    else:
        # Identificar todas las marcas únicas
        # Nota: Sólo consideramos marcas que no son nulas/vacías para el mapeo
        unique_marcas = st.session_state.data_items['proveedor'].dropna().unique()
        
        marcas_to_map = sorted([m for m in unique_marcas if m]) 
        
        st.info(f"Se detectaron **{len(marcas_to_map)}** marcas únicas a mapear. Asigne un proveedor final a cada una.")
        
        # Diccionario para almacenar el nuevo mapeo
        new_mapping = {}
        # Lista de proveedores conocidos + opción para ingresar nuevo
        supplier_options = ['-- Seleccionar/Ingresar Nuevo --'] + st.session_state.known_suppliers

        # Input de referencia (para guardar el mapeo)
        new_referencia = st.text_input(
            "Ingrese una Referencia para este Mapeo (Ej. FEB2024)", 
            key="mapping_reference_input"
        )
        
        # Contenedor para los selectbox
        cols = st.columns(3)
        
        for i, marca in enumerate(marcas_to_map):
            col = cols[i % 3]
            
            # Valor por defecto: intentar usar un proveedor conocido que sea idéntico a la marca
            default_index = 0
            if marca in st.session_state.known_suppliers:
                try:
                    default_index = supplier_options.index(marca)
                except ValueError:
                     default_index = 0 # No está en la lista de opciones, usar default

            # Selectbox para seleccionar proveedor
            selected_supplier = col.selectbox(
                f"Marca: **{marca}**",
                options=supplier_options,
                index=default_index,
                key=f"supplier_select_{marca}"
            )
            
            if selected_supplier == '-- Seleccionar/Ingresar Nuevo --':
                # Input para ingresar un nuevo proveedor
                new_supplier = col.text_input(
                    "Nuevo Proveedor",
                    key=f"new_supplier_input_{marca}"
                ).strip().upper()
                new_mapping[marca] = new_supplier if new_supplier else None
            else:
                new_mapping[marca] = selected_supplier

        st.markdown("---")
        
        # --- LÓGICA DEL BOTÓN DE MAPEO CON CORRECCIÓN ---
        if st.button("Finalizar Mapeo y Ver Resultados", type="primary"):
            if not new_referencia.strip():
                st.error("Debes ingresar una referencia nueva para poder continuar.")
            else:
                # 1. ACTUALIZAR EL MAPEO USADO EN EL PASO 3
                final_mapping = {
                    marca: final_value
                    for marca, final_value in new_mapping.items()
                    if final_value # Excluye valores None/vacíos
                }
                st.session_state.proveedor_mapping = final_mapping
                
                # 2. ALMACENAR LA REFERENCIA
                st.session_state.referencia = new_referencia.strip().upper() 
                
                st.success(f"Mapeo guardado para referencia {st.session_state.referencia}.")

                # Detectamos proveedores nuevos
                valid_new_suppliers = {
                    v
                    for v in final_mapping.values()
                    if isinstance(v, str) and v
                }

                newly_added_suppliers = valid_new_suppliers - set(st.session_state.known_suppliers)

                if newly_added_suppliers:
                    updated_suppliers = set(st.session_state.known_suppliers) | newly_added_suppliers
                    st.session_state.known_suppliers = sorted(list(updated_suppliers))
                    
                    # Persistimos en disco para próximos usos
                    save_list_to_json(SUPPLIERS_PATH, st.session_state.known_suppliers)

                    st.info(
                        "Se agregaron automáticamente nuevos proveedores al listado global: "
                        + ", ".join(sorted(newly_added_suppliers))
                    )
                
                # 3. AVANZAR AL PASO 3 
                next_step(3)
                st.rerun() 

elif st.session_state.app_step > 2:
    st.success(f"Mapeo de proveedores finalizado y guardado con la referencia: **{st.session_state.referencia}**.")
    if st.button("Volver al Mapeo"):
        next_step(2)
        st.rerun()

st.markdown("---")

# --- PASO 3: AGRUPACIÓN, CLASIFICACIÓN Y RESULTADOS ---
st.header("3. Agrupación y Exportación")
if st.session_state.app_step == 3:
    if st.session_state.data_items.empty:
        st.warning("Falta cargar y mapear datos para ver los resultados.")
    else:
        with st.spinner("Agrupando y clasificando datos..."):
            
            df_crudo = st.session_state.data_items.copy()
            
            # 1. --- IDENTIFICACIÓN DE REGISTROS PARA REVISIÓN MANUAL (FALLOS FOB/MARCA) ---
            
            # a) Fallo en Ítem Principal sin Subitems (debe tener sus propios datos)
            filtro_simple_item = (df_crudo['esSubitem'] == False) & (df_crudo['tieneSubitems'] == False)
            fallo_simple_item = filtro_simple_item & (df_crudo['montoFob'].isnull() | df_crudo['proveedor'].isnull())
            
            # b) Fallo en Subitem (debe tener sus propios datos)
            filtro_subitem = (df_crudo['esSubitem'] == True)
            fallo_subitem = filtro_subitem & (df_crudo['montoFob'].isnull() | df_crudo['proveedor'].isnull())

            # Máscara final de revisión: Fallo en ítem simple O Fallo en subitem
            mask_revision = fallo_simple_item | fallo_subitem
            
            df_revision = df_crudo[mask_revision].copy()
            
            if not df_revision.empty:
                # 2. Asignar el proveedor final para la columna de revisión
                proveedor_map = st.session_state.proveedor_mapping
                df_revision['Proveedor_Mapeado'] = df_revision['proveedor'].map(proveedor_map)
                df_revision['Marca_Original'] = df_revision['proveedor'].fillna('').apply(lambda x: x if x else 'SIN MARCA')
                df_revision['Proveedor_Final'] = df_revision['Proveedor_Mapeado'].combine_first(df_revision['Marca_Original'])

                # 3. Seleccionar columnas relevantes para la revisión y añadir Motivo
                df_revision = df_revision[['despacho', 'posicion', 'moneda', 'montoFob', 'proveedor', 'esSubitem', 'numItem', 'itemPrincipal', 'Proveedor_Final']]
                
                df_revision['Motivo Revisión'] = df_revision.apply(
                    lambda row: (
                        ("FOB Nulo/Inválido" if pd.isna(row['montoFob']) else "") + 
                        (" / Marca Nula/Vacía" if pd.isna(row['proveedor']) else "")
                    ).strip(' / '),
                    axis=1
                )
            
            st.session_state.df_revision_manual = df_revision

            # 4. --- VALIDACIÓN ADICIONAL: Suma de Subitems vs. Item Principal FOB ---
            df_validation_fob = pd.DataFrame()
            
            # Identificar items principales que tienen subitems (solo los que tienen datos válidos)
            df_principales_con_sub = df_crudo[
                (df_crudo['esSubitem'] == False) & (df_crudo['tieneSubitems'] == True) & (df_crudo['montoFob'].notnull())
            ].copy()
            
            if not df_principales_con_sub.empty:
                # Calcular la suma de FOBs de los subitems asociados
                df_subitems = df_crudo[df_crudo['esSubitem'] == True].copy()
                
                # Agrupar subitems por su padre (itemPrincipal) y sumar FOB
                df_sum_subitems = df_subitems.groupby('itemPrincipal')['montoFob'].sum().round(2).reset_index()
                df_sum_subitems.rename(columns={'montoFob': 'FOB_Subitems_Sumado'}, inplace=True)
                
                # Unir con los ítems principales
                df_validation = pd.merge(
                    df_principales_con_sub[['despacho', 'posicion', 'montoFob', 'numItem']], 
                    df_sum_subitems, 
                    left_on='numItem', 
                    right_on='itemPrincipal',
                    how='left'
                )
                
                df_validation['FOB_Subitems_Sumado'] = df_validation['FOB_Subitems_Sumado'].fillna(0)
                df_validation.rename(columns={'montoFob': 'FOB_Item_Principal'}, inplace=True)
                
                # Calcular la diferencia
                df_validation['Diferencia_FOB'] = (df_validation['FOB_Item_Principal'] - df_validation['FOB_Subitems_Sumado']).round(2)
                
                # Filtrar solo aquellos con diferencia significativa (mayor a 0.01)
                df_validation_fob = df_validation[abs(df_validation['Diferencia_FOB']) > 0.01].copy()
                
                # Seleccionar columnas para el reporte
                df_validation_fob = df_validation_fob[[
                    'despacho', 'numItem', 'posicion', 'FOB_Item_Principal', 'FOB_Subitems_Sumado', 'Diferencia_FOB'
                ]]
            
            st.session_state.df_validation_fob = df_validation_fob
            
            # 5. --- AGRUPACIÓN FINAL (usando utils_data.py) ---
            grouped_data = get_grouped_data(
                st.session_state.data_items,
                st.session_state.proveedor_mapping
            )
            
            if grouped_data.empty:
                 st.error("No se generaron resultados agrupados. Asegúrese de que el mapeo se haya completado y haya datos válidos para sumar.")
                 st.stop()

            # 6. --- CLASIFICACIÓN Y REORDENAMIENTO FINAL ---
            
            # Aplicar clasificación BK (función de utils_bk.py)
            grouped_data['Clasificación BK'] = grouped_data.apply(
                lambda row: classify_bk(row['Posición'], st.session_state.bk_list), 
                axis=1
            )
            
            # Crear las columnas BK y NO BK con 'X'
            grouped_data['BK'] = grouped_data['Clasificación BK'].apply(lambda x: 'X' if x == 'BK' else '')
            grouped_data['NO BK'] = grouped_data['Clasificación BK'].apply(lambda x: 'X' if x == 'NO BK' else '')
            
            # Reordenar las columnas
            final_columns = [
                'Despacho Nro', 
                'Posición', 
                'Moneda', 
                'Monto Total de la Posición Arancelaria', 
                'BK', 
                'NO BK', 
                'Proveedor'
            ]
            
            df_final_output = grouped_data[final_columns]
            st.session_state.df_results_grouped = df_final_output

        st.success("Proceso completado.")
        
        # --------------------------------------------------------
        # BLOQUE DE RESULTADOS AGRUPADOS
        # --------------------------------------------------------
        st.subheader(f"📊 Reporte Final Agrupado ({len(st.session_state.df_results_grouped)} Registros)")
        
        st.dataframe(st.session_state.df_results_grouped, use_container_width=True)

        # --- Exportación a XLSX (Excel) ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_final_output.to_excel(writer, sheet_name='Reporte_Agrupado', index=False)
            
            if not st.session_state.df_revision_manual.empty:
                 st.session_state.df_revision_manual.to_excel(writer, sheet_name='Revision_Manual', index=False)
                 
            if not st.session_state.df_validation_fob.empty:
                 st.session_state.df_validation_fob.to_excel(writer, sheet_name='Validacion_FOB_Principal', index=False)
                 
        st.download_button(
            label="Descargar XLSX (Reporte + Revisiones)",
            data=buffer,
            file_name=f"COM7466 - {st.session_state.referencia}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="secondary"
        )
        
        st.markdown("---")
        
        # --------------------------------------------------------
        # BLOQUE DE REVISIÓN MANUAL (FOB/MARCA)
        # --------------------------------------------------------
        if not st.session_state.df_revision_manual.empty:
            st.subheader(f"⚠️ Registros a Revisión Manual ({len(st.session_state.df_revision_manual)} Fallos FOB/Marca)")
            st.warning("Los siguientes ítems/subítems no tienen FOB o Marca/Proveedor y no se incluyeron en la suma.")
            st.dataframe(st.session_state.df_revision_manual, use_container_width=True)
        else:
            st.success("✅ No se detectaron fallos de FOB o marca en los ítems/subítems que deben tenerlos.")
            
        st.markdown("---")
        
        # --------------------------------------------------------
        # BLOQUE DE VALIDACIÓN FOB PRINCIPAL VS SUBITEMS
        # --------------------------------------------------------
        if not st.session_state.df_validation_fob.empty:
            st.subheader(f"❗ Discrepancias en FOB Principal vs. Subítems ({len(st.session_state.df_validation_fob)} Fallos)")
            st.error("Se encontraron ítems principales donde el FOB no coincide con la suma de sus subítems.")
            st.dataframe(st.session_state.df_validation_fob, use_container_width=True)
        else:
            st.success("✅ Validación de suma FOB de subítems exitosa.")
        
        st.markdown("---")
        
        # --------------------------------------------------------
        # BLOQUE DE VALIDACIÓN FOB TOTAL (GLOBAL)
        # --------------------------------------------------------
        st.subheader("Validación de Monto FOB Total Global 💰")
        
        global_fob = st.session_state.get('global_fob_total')
        
        if global_fob is not None:
            # Sumamos los montos del reporte final (solo ítems válidos incluidos)
            calculated_fob = st.session_state.df_results_grouped['Monto Total de la Posición Arancelaria'].sum().round(2)
            
            global_fob_rounded = round(global_fob, 2)
            moneda = st.session_state.data_items['moneda'].iloc[0] if not st.session_state.data_items.empty else "USD"
            
            col_ext, col_calc = st.columns(2)
            
            col_ext.metric(
                label="FOB Total Divisa (Extraído del PDF)", 
                value=f"{global_fob_rounded:,.2f} {moneda}"
            )
            col_calc.metric(
                label="Suma de FOBs Agrupados (Reporte Final)", 
                value=f"{calculated_fob:,.2f} {moneda}"
            )

            if abs(calculated_fob - global_fob_rounded) < 0.01:
                st.success("✅ **¡Validación Exitosa!** La suma de los FOBs agrupados coincide con el FOB Total Divisa del PDF.")
            else:
                st.error(
                    f"❌ **¡Error de Validación Global!** La diferencia es de **{abs(calculated_fob - global_fob_rounded):.2f} {moneda}**. "
                    "Esta diferencia puede deberse a ítems excluidos por fallos de FOB/Marca (Revisión Manual)."
                )
        else:
             st.warning("No se pudo extraer el FOB Total Divisa del PDF para realizar la validación global.")