import pandas as pd
from utils_pdf_parser import parse_number  # noqa: F401 – re-exportado por compatibilidad


def get_grouped_data(df_items: pd.DataFrame, proveedor_mapping: dict) -> pd.DataFrame:
    """
    Agrupa los datos por Despacho, Posición, Moneda y Proveedor.
    Lógica de filtrado: Excluye ítems principales que tienen subítems.
    """
    if df_items.empty:
        return pd.DataFrame()

    df = df_items.copy()

    # Mapeo de proveedores
    df['Proveedor_Mapeado'] = df['proveedor'].map(proveedor_mapping)
    df['Marca_Original'] = df['proveedor'].fillna('').apply(lambda x: x if x else 'SIN MARCA')
    df['Proveedor'] = df['Proveedor_Mapeado'].combine_first(df['Marca_Original'])

    # Filtrado lógico (evitar duplicidad padre-hijo):
    # 1. Item Principal SIN subítems  → se suma
    # 2. Subítem                       → se suma
    # 3. Item Principal CON subítems   → NO se suma (sus valores están en los subítems)
    filtro_item_principal_sin_sub = (df['esSubitem'] == False) & (df['tieneSubitems'] == False)
    filtro_subitem = (df['esSubitem'] == True)

    df_para_sumar = df[filtro_item_principal_sin_sub | filtro_subitem].copy()

    df_para_sumar['montoFob'] = pd.to_numeric(df_para_sumar['montoFob'], errors='coerce').fillna(0)

    grouped_df = df_para_sumar.groupby(
        ['despacho', 'posicion', 'moneda', 'Proveedor']
    ).agg({'montoFob': 'sum'}).reset_index()

    grouped_df['montoFob'] = grouped_df['montoFob'].round(2)

    grouped_df.columns = [
        'Despacho Nro', 'Posición', 'Moneda', 'Proveedor',
        'Monto Total de la Posición Arancelaria'
    ]

    return grouped_df


def generate_provider_summary(df_final: pd.DataFrame) -> pd.DataFrame:
    """
    Genera una tabla resumen:
    Proveedor | FOB Total | FOB BK | % BK
    """
    if df_final.empty:
        return pd.DataFrame(columns=['Proveedor', 'FOB Total', 'FOB BK', '% BK'])

    df = df_final.copy()
    col_monto = 'Monto Total de la Posición Arancelaria'

    df['monto_bk_temp'] = df.apply(
        lambda row: row[col_monto] if row['BK'] == 'X' else 0, axis=1
    )

    summary = df.groupby('Proveedor').agg(
        FOB_Total=(col_monto, 'sum'),
        FOB_BK=('monto_bk_temp', 'sum')
    ).reset_index()

    summary['% BK'] = (summary['FOB_BK'] / summary['FOB_Total'] * 100).fillna(0).round(1)

    summary = summary.sort_values(by='FOB_Total', ascending=False)
    summary.rename(columns={'FOB_Total': 'FOB Total', 'FOB_BK': 'FOB BK'}, inplace=True)

    return summary[['Proveedor', 'FOB Total', 'FOB BK', '% BK']]
