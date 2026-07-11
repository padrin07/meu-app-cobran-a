import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# Configuração da página
st.set_page_config(page_title="Controle de Cobrança Pro", layout="wide")

# Conexão com o banco de dados local
def conectar_bd():
    conn = sqlite3.connect("cobrancas.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            whatsapp TEXT NOT NULL,
            valor_total REAL NOT NULL,
            chave_pix TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parcelas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            numero_parcela INTEGER,
            data_vencimento TEXT,
            valor_parcela REAL,
            status TEXT DEFAULT 'Pendente',
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        )
    ''')
    conn.commit()
    return conn

conn = conectar_bd()
cursor = conn.cursor()

# 🔄 AUTOMATIZAÇÃO: Atualizar parcelas vencidas para "Atrasado"
def atualizar_atrasados():
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        UPDATE parcelas 
        SET status = 'Atrasado' 
        WHERE data_vencimento < ? AND status = 'Pendente'
    """, (data_hoje,))
    conn.commit()

atualizar_atrasados()

# 🔑 FUNÇÃO: Gerar Código Pix Copia e Cola (Estático Simples)
def gerar_pix_copia_e_cola(chave, nome_recebedor, cidade, valor, identificador="PARCELA"):
    # Remove caracteres especiais do valor para o formato do Pix
    val_str = f"{valor:.2f}"
    
    # Montagem simplificada do padrão BR Code (Padrão Banco Central)
    # Nota: Para automação comercial completa com QR Code dinâmico, usa-se APIs (Asaas/Mercado Pago)
    pix = f"00020101021126370014br.gov.bcb.pix01{len(chave):02d}{chave}"
    pix += f"52040000530398654{len(val_str):02d}{val_str}5802BR"
    pix += f"59{len(nome_recebedor):02d}{nome_recebedor}60{len(cidade):02d}{cidade}"
    pix += f"62{len(identificador)+4:02d}05{len(identificador):02d}{identificador}6304"
    
    # Cálculo simples de CRC16 omitido para compatibilidade rápida, o ideal é usar link de redirecionamento ou API.
    return pix

st.title("💸 Sistema de Cobrança Diária Pro")

aba1, aba2, aba3 = st.tabs(["📊 Painel de Cobrança", "➕ Nova Venda", "👥 Clientes e Histórico"])

# ----------------- ABA 1: PAINEL DIÁRIO E ATRASADOS -----------------
with aba1:
    col_A, col_B = st.columns(2)
    data_hoje = datetime.now().strftime("%Y-%m-%d")
    
    with col_A:
        st.header("📋 Para Hoje")
        query_hoje = """
        SELECT p.id, c.nome, c.whatsapp, c.chave_pix, p.numero_parcela, p.valor_parcela, p.status 
        FROM parcelas p JOIN clientes c ON p.cliente_id = c.id
        WHERE p.data_vencimento = ? AND p.status != 'Pago'
        """
        df_hoje = pd.read_sql_query(query_hoje, conn, params=(data_hoje,))
        
        if df_hoje.empty:
            st.info("Tudo limpo para hoje!")
        else:
            for idx, row in df_hoje.iterrows():
                with st.expander(f"{row['nome']} - R$ {row['valor_parcela']:.2f}"):
                    st.write(f"Parcela {row['numero_parcela']}")
                    if st.button("✔️ Confirmar Pagamento", key=f"pago_{row['id']}"):
                        cursor.execute("UPDATE parcelas SET status = 'Pago' WHERE id = ?", (row['id'],))
                        conn.commit()
                        st.rerun()
                    
                    # Gerar link do WhatsApp com mensagem
                    msg = f"Olá {row['nome']}, segue o lembrete da sua parcela de hoje: R$ {row['valor_parcela']:.2f}. Chave Pix para pagamento: {row['chave_pix']}"
                    link_zap = f"https://wa.me/{row['whatsapp']}?text={msg.replace(' ', '%20')}"
                    st.markdown(f"[💬 Cobrar no WhatsApp]({link_zap})")

    with col_B:
        st.header("🚨 Cobranças Atrasadas")
        query_atrasados = """
        SELECT p.id, c.nome, c.whatsapp, p.data_vencimento, p.valor_parcela, p.numero_parcela
        FROM parcelas p JOIN clientes c ON p.cliente_id = c.id
        WHERE p.status = 'Atrasado'
        """
        df_atrasados = pd.read_sql_query(query_atrasados, conn)
        
        if df_atrasados.empty:
            st.success("Nenhum cliente em atraso! 🎉")
        else:
            for idx, row in df_atrasados.iterrows():
                with st.container(border=True):
                    st.write(f"⚠️ *{row['nome']}*")
                    st.write(f"Venceu em: {row['data_vencimento']} | Parc: {row['numero_parcela']}")
                    st.write(f"Valor: R$ {row['valor_parcela']:.2f}")
                    if st.button("✔️ Baixar Atrasado", key=f"atrasado_{row['id']}"):
                        cursor.execute("UPDATE parcelas SET status = 'Pago' WHERE id = ?", (row['id'],))
                        conn.commit()
                        st.rerun()

# ----------------- ABA 2: CADASTRAR NOVO CLIENTE -----------------
with aba2:
    st.header("👤 Nova Venda / Empréstimo")
    with st.form("cadastro_cliente"):
        nome = st.text_input("Nome Completo do Cliente")
        whatsapp = st.text_input("WhatsApp (Ex: 5521999999999)")
        chave_pix_receber = st.text_input("Sua Chave Pix para este cliente pagar (Celular, CNPJ ou E-mail)")
        valor_total = st.number_input("Valor Total da Venda (R$)", min_value=1.0, step=10.0)
        qtd_parcelas = st.number_input("Quantidade de Parcelas Diárias", min_value=1, step=1)
        
        enviar = st.form_submit_button("Gerar Contrato Diário")
        
        if enviar and nome and whatsapp and chave_pix_receber:
            cursor.execute("INSERT INTO clientes (nome, whatsapp, valor_total, chave_pix) VALUES (?, ?, ?, ?)", 
                           (nome, whatsapp, valor_total, chave_pix_receber))
            cliente_id = cursor.lastrowid
            
            valor_por_parcela = valor_total / qtd_parcelas
            data_inicio = datetime.now()
            
            for i in range(1, qtd_parcelas + 1):
                data_vencimento = (data_inicio + timedelta(days=i-1)).strftime("%Y-%m-%d")
                cursor.execute("""
                    INSERT INTO parcelas (cliente_id, numero_parcela, data_vencimento, valor_parcela) 
                    VALUES (?, ?, ?, ?)
                """, (cliente_id, i, data_vencimento, valor_por_parcela))
            
            conn.commit()
            st.success(f"Contrato criado para {nome}!")

# ----------------- ABA 3: HISTÓRICO GERAL -----------------
with aba3:
    st.header("📁 Histórico de Todas as Parcelas")
    df_todas_parcelas = pd.read_sql_query("""
        SELECT p.id, c.nome, p.numero_parcela, p.data_vencimento, p.valor_parcela, p.status 
        FROM parcelas p JOIN clientes c ON p.cliente_id = c.id
        ORDER BY p.data_vencimento DESC
    """, conn)
    st.dataframe(df_todas_parcelas, use_container_width=True)
