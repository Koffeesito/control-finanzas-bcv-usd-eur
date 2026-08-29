# -*- coding: utf-8 -*-
import streamlit as st
import sqlite3
import requests
import pandas as pd
from datetime import datetime, date
import io
import time
import plotly.express as px

# ReportLab para generación de reportes PDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA Y TEMA NARANJA
# -------------------------------------------------------------
st.set_page_config(page_title="Control Financiero BCV", page_icon="💰", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #FFF7F0; }
    div[data-baseweb="select"] > div, input { border-color: #FF8C00 !important; }
    .stButton>button {
        background-color: #FF7F11;
        color: white;
        border-radius: 8px;
        border: none;
        font-weight: bold;
    }
    .stButton>button:hover { background-color: #E06000; color: white; }
    .metric-card {
        background-color: #FFFFFF;
        padding: 15px;
        border-radius: 10px;
        border-left: 5px solid #FF7F11;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .metric-card p {
        margin: 2px 0;
        font-size: 0.9em;
        color: #444444;
    }
    </style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------
# MÓDULO DE TASAS BCV
# -------------------------------------------------------------
@st.cache_data(ttl=3600)
def obtener_tasas_bcv():
    headers = {'User-Agent': 'Mozilla/5.0'}
    tasa_usd, tasa_eur = 0.0, 0.0
    
    try:
        r_usd = requests.get("https://ve.dolarapi.com/v1/dolares/oficial", headers=headers, timeout=5)
        r_eur = requests.get("https://ve.dolarapi.com/v1/euros/oficial", headers=headers, timeout=5)
        if r_usd.status_code == 200 and r_eur.status_code == 200:
            tasa_usd = r_usd.json().get("promedio", 0.0)
            tasa_eur = r_eur.json().get("promedio", 0.0)
    except Exception:
        pass

    if tasa_usd == 0.0:
        try:
            r = requests.get("https://pydolarvenezuela-api.vercel.app/api/v1/dollar?page=bcv", headers=headers, timeout=5)
            if r.status_code == 200:
                tasa_usd = r.json().get("moneda", {}).get("promedio", 36.50)
                tasa_eur = tasa_usd * 1.08
        except Exception:
            tasa_usd, tasa_eur = 36.50, 39.80

    return tasa_usd, tasa_eur

# -------------------------------------------------------------
# GENERADOR DE PDF (REPORTLAB)
# -------------------------------------------------------------
def generar_reporte_pdf(df_filtrado, tasa_usd, tasa_eur, cat_filtro, f_inicio, f_fin):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18,
        textColor=colors.HexColor("#FF7F11"), spaceAfter=6
    )
    subtitle_style = ParagraphStyle(
        'SubTitleStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10,
        textColor=colors.HexColor("#555555"), spaceAfter=15
    )
    section_style = ParagraphStyle(
        'SectionStyle', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12,
        textColor=colors.HexColor("#333333"), spaceBefore=10, spaceAfter=10
    )

    fecha_emision = datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(Paragraph("Reporte de Finanzas Personales", title_style))
    story.append(Paragraph(f"Emitido el: {fecha_emision} | Tasas BCV: <b>USD:</b> {tasa_usd:.2f} Bs | <b>EUR:</b> {tasa_eur:.2f} Bs", subtitle_style))
    story.append(Spacer(1, 5))

    criterios = f"<b>Filtro de Categoría:</b> {cat_filtro} | <b>Rango de Fechas:</b> {f_inicio.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')}"
    story.append(Paragraph(criterios, styles['Normal']))
    story.append(Spacer(1, 10))

    ingresos_total = df_filtrado[df_filtrado['tipo'] == 'INGRESO']['monto_bs'].sum()
    gastos_total = df_filtrado[df_filtrado['tipo'] == 'GASTO']['monto_bs'].sum()
    balance_total = ingresos_total - gastos_total

    data_resumen = [
        ["Concepto", "Monto en Bolívares (Bs)", "Equivalente en USD", "Equivalente en EUR"],
        ["Total Ingresos", f"{ingresos_total:,.2f} Bs", f"${ingresos_total/tasa_usd:,.2f}", f"€{ingresos_total/tasa_eur:,.2f}"],
        ["Total Gastos", f"{gastos_total:,.2f} Bs", f"${gastos_total/tasa_usd:,.2f}", f"€{gastos_total/tasa_eur:,.2f}"],
        ["Balance Neto", f"{balance_total:,.2f} Bs", f"${balance_total/tasa_usd:,.2f}", f"€{balance_total/tasa_eur:,.2f}"]
    ]
    t_resumen = Table(data_resumen, colWidths=[135, 135, 135, 135])
    t_resumen.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#FF7F11")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#FFF7F0")),
    ]))
    story.append(t_resumen)
    story.append(Spacer(1, 15))

    story.append(Paragraph("Detalle de Transacciones", section_style))
    headers_tabla = ["ID", "Fecha", "Descripción", "Tipo", "Categoría", "Monto (Bs)", "Monto ($)", "Monto (€)"]
    data_transacciones = [headers_tabla]

    for _, row in df_filtrado.iterrows():
        f_str = pd.to_datetime(row['fecha']).strftime("%d/%m/%Y %H:%M")
        m_usd = row['monto_bs'] / tasa_usd
        m_eur = row['monto_bs'] / tasa_eur
        data_transacciones.append([
            str(row['id']), f_str, Paragraph(str(row['descripcion']), styles['Normal']),
            str(row['tipo']), Paragraph(str(row['categoria']), styles['Normal']),
            f"{row['monto_bs']:,.2f}", f"${m_usd:,.2f}", f"€{m_eur:,.2f}"
        ])

    t_detalle = Table(data_transacciones, colWidths=[25, 75, 130, 45, 85, 70, 55, 55])
    t_detalle.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#333333")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ALIGN', (0, 0), (1, -1), 'CENTER'),
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),
        ('ALIGN', (5, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E0E0E0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAFAFA")]),
    ]))

    story.append(t_detalle)
    doc.build(story)
    buffer.seek(0)
    return buffer

# -------------------------------------------------------------
# BASE DE DATOS LOCAL (SQLite)
# -------------------------------------------------------------
class FinanzasDB:
    def __init__(self):
        self.conn = sqlite3.connect("finanzas_personales.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.crear_tablas()

    def crear_tablas(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS transacciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                descripcion TEXT, monto_bs REAL, tipo TEXT, categoria TEXT, fecha TEXT
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS metas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nombre TEXT, monto_objetivo_usd REAL
            )
        ''')
        self.conn.commit()

    def registrar(self, desc, monto, moneda, tipo, cat, t_usd, t_eur):
        monto_bs = monto * t_usd if moneda == "USD" else (monto * t_eur if moneda == "EUR" else monto)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.cursor.execute(
            'INSERT INTO transacciones (descripcion, monto_bs, tipo, categoria, fecha) VALUES (?,?,?,?,?)',
            (desc, monto_bs, tipo, cat, fecha)
        )
        self.conn.commit()

    def actualizar_transaccion(self, trans_id, desc, monto, moneda, tipo, cat, t_usd, t_eur):
        monto_bs = monto * t_usd if moneda == "USD" else (monto * t_eur if moneda == "EUR" else monto)
        self.cursor.execute('''
            UPDATE transacciones 
            SET descripcion = ?, monto_bs = ?, tipo = ?, categoria = ? 
            WHERE id = ?
        ''', (desc, monto_bs, tipo, cat, trans_id))
        self.conn.commit()

    def eliminar_transaccion(self, trans_id):
        self.cursor.execute('DELETE FROM transacciones WHERE id = ?', (trans_id,))
        self.conn.commit()

    def obtener_transacciones_df(self):
        query = "SELECT id, fecha, descripcion, tipo, categoria, monto_bs FROM transacciones ORDER BY id DESC"
        return pd.read_sql_query(query, self.conn)

    def obtener_transaccion_por_id(self, trans_id):
        self.cursor.execute('SELECT id, descripcion, monto_bs, tipo, categoria FROM transacciones WHERE id = ?', (trans_id,))
        return self.cursor.fetchone()

    def obtener_balance(self):
        self.cursor.execute('''
            SELECT 
                SUM(CASE WHEN tipo = 'INGRESO' THEN monto_bs ELSE 0 END),
                SUM(CASE WHEN tipo = 'GASTO' THEN monto_bs ELSE 0 END)
            FROM transacciones
        ''')
        res = self.cursor.fetchone()
        ingresos = res[0] if res[0] else 0.0
        gastos = res[1] if res[1] else 0.0
        return ingresos, gastos, ingresos - gastos

    def agregar_meta(self, nombre, monto_usd):
        self.cursor.execute('INSERT INTO metas (nombre, monto_objetivo_usd) VALUES (?, ?)', (nombre, monto_usd))
        self.conn.commit()

    def obtener_metas(self):
        self.cursor.execute('SELECT nombre, monto_objetivo_usd FROM metas')
        return self.cursor.fetchall()

# -------------------------------------------------------------
# INTERFAZ GRÁFICA WEB
# -------------------------------------------------------------
db = FinanzasDB()
tasa_usd, tasa_eur = obtener_tasas_bcv()

st.title("🍊 Control de Finanzas Personales")
st.caption(f"Tasas oficiales BCV en tiempo real | **USD:** {tasa_usd:.2f} Bs | **EUR:** {tasa_eur:.2f} Bs")

opcion = st.sidebar.radio("Navegación", ["Resumen General", "Registrar Movimiento", "Gestión de Registros", "Metas de Ahorro"])

if opcion == "Resumen General":
    ingresos, gastos, balance = db.obtener_balance()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"""
            <div class='metric-card'>
                <h4>Total Ingresos</h4>
                <h3>{ingresos:,.2f} Bs</h3>
                <p>💵 <b>${ingresos/tasa_usd:,.2f} USD</b></p>
                <p>💶 <b>€{ingresos/tasa_eur:,.2f} EUR</b></p>
            </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
            <div class='metric-card'>
                <h4>Total Gastos</h4>
                <h3>{gastos:,.2f} Bs</h3>
                <p>💵 <b>${gastos/tasa_usd:,.2f} USD</b></p>
                <p>💶 <b>€{gastos/tasa_eur:,.2f} EUR</b></p>
            </div>
        """, unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
            <div class='metric-card'>
                <h4>Balance Neto</h4>
                <h3>{balance:,.2f} Bs</h3>
                <p>💵 <b>${balance/tasa_usd:,.2f} USD</b></p>
                <p>💶 <b>€{balance/tasa_eur:,.2f} EUR</b></p>
            </div>
        """, unsafe_allow_html=True)

    # --- SECCIÓN DE GRÁFICOS CIRCULARES ---
    st.divider()
    st.subheader("📊 Distribución por Categoría")
    
    df_all = db.obtener_transacciones_df()
    if not df_all.empty:
        col_g1, col_g2 = st.columns(2)
        
        # Gráfico de Gastos por Categoría
        df_gastos = df_all[df_all['tipo'] == 'GASTO']
        with col_g1:
            if not df_gastos.empty:
                df_gastos_cat = df_gastos.groupby('categoria')['monto_bs'].sum().reset_index()
                fig_gastos = px.pie(
                    df_gastos_cat, values='monto_bs', names='categoria',
                    title='Gastos por Categoría',
                    hole=0.4,
                    color_discrete_sequence=px.colors.sequential.Oranges_r
                )
                fig_gastos.update_traces(textinfo='percent+label', hoverinfo='label+value+percent')
                st.plotly_chart(fig_gastos, use_container_width=True)
            else:
                st.info("No hay gastos registrados para generar el gráfico.")
                
        # Gráfico de Ingresos por Categoría
        df_ingresos = df_all[df_all['tipo'] == 'INGRESO']
        with col_g2:
            if not df_ingresos.empty:
                df_ingresos_cat = df_ingresos.groupby('categoria')['monto_bs'].sum().reset_index()
                fig_ingresos = px.pie(
                    df_ingresos_cat, values='monto_bs', names='categoria',
                    title='Ingresos por Categoría',
                    hole=0.4,
                    color_discrete_sequence=px.colors.sequential.Teal_r
                )
                fig_ingresos.update_traces(textinfo='percent+label', hoverinfo='label+value+percent')
                st.plotly_chart(fig_ingresos, use_container_width=True)
            else:
                st.info("No hay ingresos registrados para generar el gráfico.")
    else:
        st.info("Registra movimientos para visualizar los gráficos de distribución.")

elif opcion == "Registrar Movimiento":
    st.subheader("Nuevo Registro")
    with st.form("form_transaccion"):
        tipo = st.selectbox("Tipo", ["INGRESO", "GASTO"])
        desc = st.text_input("Descripción")
        col_m, col_mon = st.columns(2)
        monto = col_m.number_input("Monto", min_value=0.01, step=0.5)
        moneda = col_mon.selectbox("Moneda de entrada", ["BS", "USD", "EUR"])
        cat = st.text_input("Categoría (ej. Sueldo, Comida, Servicios)")
        
        if st.form_submit_button("Guardar Transacción"):
            if desc:
                with st.spinner("Guardando registro en la base de datos..."):
                    db.registrar(desc, monto, moneda, tipo, cat, tasa_usd, tasa_eur)
                    time.sleep(0.4)
                
                st.toast(f"✅ {tipo} guardado: {desc}", icon="🎉")
                st.balloons()
                st.success(f"¡Transacción registrada correctamente en {moneda}!")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Por favor ingresa una descripción.")

elif opcion == "Gestión de Registros":
    st.subheader("Historial, Filtros y Edición de Registros")
    
    df = db.obtener_transacciones_df()
    if df.empty:
        st.info("No hay registros guardados en la base de datos.")
    else:
        df['fecha_dt'] = pd.to_datetime(df['fecha'])
        
        st.markdown("#### 🔍 Filtros de Búsqueda")
        col_f1, col_f2, col_f3 = st.columns(3)
        
        categorias_unicas = ["Todas"] + sorted(df['categoria'].dropna().unique().tolist())
        cat_seleccionada = col_f1.selectbox("Filtrar por Categoría:", categorias_unicas)
        
        fecha_min = df['fecha_dt'].min().date()
        fecha_max = df['fecha_dt'].max().date()
        
        fecha_inicio = col_f2.date_input("Fecha Inicio:", fecha_min)
        fecha_fin = col_f3.date_input("Fecha Fin:", fecha_max)
        
        df_filtrado = df.copy()
        
        if cat_seleccionada != "Todas":
            df_filtrado = df_filtrado[df_filtrado['categoria'] == cat_seleccionada]
            
        df_filtrado = df_filtrado[
            (df_filtrado['fecha_dt'].dt.date >= fecha_inicio) & 
            (df_filtrado['fecha_dt'].dt.date <= fecha_fin)
        ]
        
        df_filtrado['monto_usd'] = (df_filtrado['monto_bs'] / tasa_usd).round(2)
        df_filtrado['monto_eur'] = (df_filtrado['monto_bs'] / tasa_eur).round(2)
        
        subtotal_ingresos = df_filtrado[df_filtrado['tipo'] == 'INGRESO']['monto_bs'].sum()
        subtotal_gastos = df_filtrado[df_filtrado['tipo'] == 'GASTO']['monto_bs'].sum()
        
        col_m1, col_m2 = st.columns(2)
        col_m1.metric(
            "Ingresos en Selección", 
            f"{subtotal_ingresos:,.2f} Bs", 
            f"${subtotal_ingresos/tasa_usd:,.2f} USD | €{subtotal_ingresos/tasa_eur:,.2f} EUR"
        )
        col_m2.metric(
            "Gastos en Selección", 
            f"{subtotal_gastos:,.2f} Bs", 
            f"${subtotal_gastos/tasa_usd:,.2f} USD | €{subtotal_gastos/tasa_eur:,.2f} EUR"
        )
        
        df_display = df_filtrado[['id', 'fecha', 'descripcion', 'tipo', 'categoria', 'monto_bs', 'monto_usd', 'monto_eur']].rename(columns={
            'id': 'ID', 'fecha': 'Fecha', 'descripcion': 'Descripción',
            'tipo': 'Tipo', 'categoria': 'Categoría', 'monto_bs': 'Monto (Bs)',
            'monto_usd': 'Monto ($)', 'monto_eur': 'Monto (€)'
        })
        
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # Gráfico de gastos dentro del filtro aplicado
        df_gastos_filt = df_filtrado[df_filtrado['tipo'] == 'GASTO']
        if not df_gastos_filt.empty:
            st.markdown("#### 🍩 Distribución de Gastos en el Período Seleccionado")
            df_gastos_cat_filt = df_gastos_filt.groupby('categoria')['monto_bs'].sum().reset_index()
            fig_filt = px.pie(
                df_gastos_cat_filt, values='monto_bs', names='categoria',
                title='Proporción de Gastos Filtrados',
                hole=0.4,
                color_discrete_sequence=px.colors.sequential.Oranges_r
            )
            fig_filt.update_traces(textinfo='percent+label', hoverinfo='label+value+percent')
            st.plotly_chart(fig_filt, use_container_width=True)

        st.divider()
        st.markdown("#### 📄 Exportar Reporte")
        if not df_filtrado.empty:
            pdf_bytes = generar_reporte_pdf(df_filtrado, tasa_usd, tasa_eur, cat_seleccionada, fecha_inicio, fecha_fin)
            nombre_pdf = f"reporte_finanzas_{date.today().strftime('%Y%m%d')}.pdf"
            
            st.download_button(
                label="📥 Descargar Reporte en PDF",
                data=pdf_bytes,
                file_name=nombre_pdf,
                mime="application/pdf"
            )
        else:
            st.info("No hay datos en el filtro seleccionado para generar un reporte en PDF.")

        st.divider()
        st.subheader("Modificar o Eliminar Registro")
        lista_ids = df_filtrado['id'].tolist() if not df_filtrado.empty else df['id'].tolist()
        
        if lista_ids:
            id_seleccionado = st.selectbox("Selecciona el ID del registro a gestionar:", lista_ids)
            registro = db.obtener_transaccion_por_id(id_seleccionado)
            
            if registro:
                reg_id, reg_desc, reg_monto_bs, reg_tipo, reg_cat = registro
                
                with st.form("form_editar"):
                    st.markdown(f"**Modificando Registro ID #{reg_id}**")
                    edit_tipo = st.selectbox("Tipo", ["INGRESO", "GASTO"], index=0 if reg_tipo == "INGRESO" else 1)
                    edit_desc = st.text_input("Descripción", value=reg_desc)
                    
                    col_e1, col_e2 = st.columns(2)
                    edit_monto = col_e1.number_input("Monto", min_value=0.01, value=float(reg_monto_bs), step=0.5)
                    edit_moneda = col_e2.selectbox("Moneda de recálculo", ["BS", "USD", "EUR"])
                    
                    edit_cat = st.text_input("Categoría", value=reg_cat)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    guardar_cambios = col_btn1.form_submit_button("💾 Guardar Cambios")
                    eliminar_reg = col_btn2.form_submit_button("🗑️ Eliminar Registro")
                    
                    if guardar_cambios:
                        with st.spinner("Actualizando datos..."):
                            db.actualizar_transaccion(reg_id, edit_desc, edit_monto, edit_moneda, edit_tipo, edit_cat, tasa_usd, tasa_eur)
                        st.toast(f"Registro #{reg_id} modificado con éxito.", icon="✏️")
                        time.sleep(0.8)
                        st.rerun()
                        
                    if eliminar_reg:
                        with st.spinner("Eliminando datos..."):
                            db.eliminar_transaccion(reg_id)
                        st.toast(f"Registro #{reg_id} eliminado.", icon="🗑️")
                        time.sleep(0.8)
                        st.rerun()

elif opcion == "Metas de Ahorro":
    st.subheader("Objetivos Financieros")
    with st.form("form_meta"):
        nombre_meta = st.text_input("Nombre de la meta (ej. Comprar Laptop)")
        monto_meta_usd = st.number_input("Monto en USD", min_value=1.0)
        if st.form_submit_button("Crear Meta"):
            if nombre_meta:
                db.agregar_meta(nombre_meta, monto_meta_usd)
                st.toast(f"Meta '{nombre_meta}' agregada con éxito.", icon="🎯")
                st.balloons()
                time.sleep(0.8)
                st.rerun()

    st.divider()
    _, _, balance_actual = db.obtener_balance()
    metas = db.obtener_metas()
    
    for nombre, obj_usd in metas:
        obj_bs = obj_usd * tasa_usd
        obj_eur = obj_bs / tasa_eur
        progreso = min(max(balance_actual / obj_bs, 0.0), 1.0) if obj_bs > 0 else 0.0
        st.write(f"**{nombre}** — Objetivo: ${obj_usd:,.2f} USD | €{obj_eur:,.2f} EUR ({obj_bs:,.2f} Bs)")
        st.progress(progreso, text=f"{progreso*100:.1f}% alcanzado")