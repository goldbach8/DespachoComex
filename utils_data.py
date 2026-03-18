import pandas as pd

def parse_number(num_str):
    """Convierte un string de formato '1.234,56' a float 1234.56."""
    if not num_str: return None
    try:
        s = num_str.replace('.', '').replace(',', '.')
        return float(s)
    except ValueError:
        return None

def get_grouped_data(df_items: pd.DataFrame, proveedor_mapping: dict) -> pd.DataFrame:
    """
    Agrupa los datos por Despacho, Posición, Moneda y Proveedor.
    Lógica de filtrado: Excluye ítems principales que tienen subítems.
    """
    if df_items.empty: return pd.DataFrame()
    
    df = df_items.copy()
    
    # Mapeo de proveedores
    # Aplicar el mapeo, si no existe, queda NaN, luego llenamos con la marca original, luego 'SIN MARCA'
    df['Proveedor_Mapeado'] = df['proveedor'].map(proveedor_mapping)
    df['Marca_Original'] = df['proveedor'].fillna('').apply(lambda x: x if x else 'SIN MARCA')
    df['Proveedor'] = df['Proveedor_Mapeado'].combine_first(df['Marca_Original'])
    
    # Filtrado lógico (evitar duplicidad padre-hijo)
    # 1. Item Principal SIN subitems -> Se suma.
    # 2. Subitem -> Se suma.
    # 3. Item Principal CON subitems -> NO se suma (sus valores están en los subitems).
    
    filtro_item_principal_sin_sub = (df['esSubitem'] == False) & (df['tieneSubitems'] == False)
    filtro_subitem = (df['esSubitem'] == True)
    
    df_para_sumar = df[filtro_item_principal_sin_sub | filtro_subitem].copy()
    
    # Importante: Asegurar que montoFob sea numérico y llenar NaN con 0 para evitar errores de suma
    df_para_sumar['montoFob'] = pd.to_numeric(df_para_sumar['montoFob'], errors='coerce').fillna(0)
    
    # Agrupación
    grouped_df = df_para_sumar.groupby(
        ['despacho', 'posicion', 'moneda', 'Proveedor']
    ).agg(
        {'montoFob': 'sum'}
    ).reset_index()

    grouped_df['montoFob'] = grouped_df['montoFob'].round(2)
    
    grouped_df.columns = [
        'Despacho Nro', 'Posición', 'Moneda', 'Proveedor', 'Monto Total de la Posición Arancelaria'
    ]
    
    return grouped_df

def generate_provider_summary(df_final: pd.DataFrame) -> pd.DataFrame:
    """
    Genera una tabla resumen con:
    Proveedor | FOB Total | % BK (Porcentaje del FOB que es BK)
    
    Espera df_final con columnas: 'Proveedor', 'Monto Total de la Posición Arancelaria', 'BK' ('X' o '')
    """
    if df_final.empty:
        return pd.DataFrame(columns=['Proveedor', 'FOB Total', 'FOB BK', '% BK'])
        
    # Asegurarnos de trabajar con números
    df = df_final.copy()
    col_monto = 'Monto Total de la Posición Arancelaria'
    
    # Calcular columna auxiliar de monto BK
    df['monto_bk_temp'] = df.apply(
        lambda row: row[col_monto] if row['BK'] == 'X' else 0, axis=1
    )
    
    # Agrupar por proveedor
    summary = df.groupby('Proveedor').agg(
        FOB_Total=(col_monto, 'sum'),
        FOB_BK=('monto_bk_temp', 'sum')
    ).reset_index()
    
    # Calcular porcentaje
    summary['% BK'] = (summary['FOB_BK'] / summary['FOB_Total'] * 100).fillna(0).round(1)
    
    # Limpieza y orden
    summary = summary[['Proveedor', 'FOB_Total', '% BK']].sort_values(by='FOB_Total', ascending=False)
    summary.rename(columns={'FOB_Total': 'FOB Total'}, inplace=True)
    
    return summary