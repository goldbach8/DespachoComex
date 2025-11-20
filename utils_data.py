import pandas as pd
import re

def parse_number(num_str):
    """Convierte un string de formato '1.234,56' a float 1234.56."""
    if not num_str:
        return None
    try:
        # Elimina separadores de miles (.), y reemplaza coma (,) por punto (.) para decimales
        s = num_str.replace('.', '').replace(',', '.')
        return float(s)
    except ValueError:
        return None

def get_grouped_data(df_items: pd.DataFrame, proveedor_mapping: dict) -> pd.DataFrame:
    """
    Agrupa los datos por Despacho, Posición, Moneda y Proveedor (usando el mapping).
    
    REGLA CRÍTICA DE FILTRADO (FOB):
    Se excluyen los ítems principales que contienen subítems para evitar doble contabilización.
    
    REGLA DE PROVEEDOR (Validaciones Adicionales):
    No se elimina ningún registro por falta de proveedor. Si no hay mapeo, usa la marca original.
    """
    if df_items.empty:
        return pd.DataFrame()
    
    df = df_items.copy()
    
    # Asegurar que las columnas existan
    for col in ['esSubitem', 'tieneSubitems']:
        if col not in df.columns:
            df[col] = False

    # 1. --- Mapeo de Proveedores (Cumple Validaciones 1 y 2) ---
    df['Proveedor_Mapeado'] = df['proveedor'].map(proveedor_mapping)
    
    # Columna auxiliar para la marca original. Si es nula/vacía, se usa 'SIN MARCA'.
    df['Marca_Original'] = df['proveedor'].fillna('').apply(lambda x: x if x else 'SIN MARCA')
    
    # La columna final 'Proveedor' usa el Mapeado si existe, si no, usa la Marca Original.
    df['Proveedor'] = df['Proveedor_Mapeado'].combine_first(df['Marca_Original'])
    
    # CRITICAL: Solo eliminamos si el montoFob es nulo/inválido.
    # No eliminamos por proveedor nulo/faltante, ya que asignamos 'SIN MARCA' si es necesario.
    df.dropna(subset=['montoFob'], inplace=True) 

    # 2. --- LÓGICA DE FILTRADO DE MONTO FOB (Etapa 4) ---
    
    # Máscara 1: Ítems principales (esSubitem=False) SIN subítems (tieneSubitems=False)
    filtro_item_principal_sin_sub = (df['esSubitem'] == False) & (df['tieneSubitems'] == False)
    
    # Máscara 2: Subítems detallados (esSubitem=True)
    filtro_subitem = (df['esSubitem'] == True)
    
    # Combinamos la máscara: Solo incluir si cumple 1 O 2
    df_para_sumar = df[filtro_item_principal_sin_sub | filtro_subitem]
    
    # 3. --- AGRUPACIÓN FINAL ---
    # Agrupar por las 4 claves y sumar el monto FOB
    grouped_df = df_para_sumar.groupby(
        ['despacho', 'posicion', 'moneda', 'Proveedor']
    ).agg(
        {'montoFob': 'sum'}
    ).reset_index()

    # Redondeamos el monto FOB y renombramos
    grouped_df['montoFob'] = grouped_df['montoFob'].round(2)
    
    grouped_df.columns = [
        'Despacho Nro', 
        'Posición', 
        'Moneda', 
        'Proveedor',
        'Monto Total de la Posición Arancelaria'
    ]

    # Reordenamos las columnas del resultado final para coincidir con el output de app.py (aunque app.py lo reordena después)
    grouped_df = grouped_df[[
        'Despacho Nro', 
        'Posición', 
        'Moneda', 
        'Monto Total de la Posición Arancelaria',
        'Proveedor' # Proveedor va al final antes de clasificar BK
    ]]

    return grouped_df