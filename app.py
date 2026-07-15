import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# Configuração da página
st.set_page_config(page_title="Controle de Cobrança Pro", layout="wide")

# Conexão com o banco de dados local
def conectar_bd():
    conn = sqlite3.connect("cobrancas.db", check_same_thread=False)
    cursor = conn.cursor()
    # Criar tabela de clientes (com a coluna de porcentagem de lucro)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            whatsapp TEXT NOT NULL,
            valor_total REAL NOT NULL,
            chave_pix TEXT,
            porcentagem_lucro REAL DEFAULT 35.0
        )
    ''')
    # Criar tabela de parcelas diárias
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
data_hoje = datetime.now().strftime("%Y-%m-%d")
cursor.execute("UPDATE parcelas SET status = 'Atrasado' WHERE data_vencimento < ? AND status = 'Pendente'", (data_hoje,))
conn.commit()

st.title("💸 Sistema de Cobrança Diária Pro")

# Criando as abas (Adicionada a aba de Estatísticas Financeiras)
aba1, aba2, aba3, aba4 = st.tabs(["📊 Painel de Cobrança", "➕ Nova Venda", "📈 Estatísticas Financeiras", "👥 Clientes e Histórico"])

# ----------------- ABA 1: PAINEL DIÁRIO E ATRASADOS -----------------
with aba1:
    col_A, col_B = st.columns(2)
    
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
                    if st.button("✔ Confirmar Pagamento", key=f"pago_{row['id']}"):
                        cursor.execute("UPDATE parcelas SET status = 'Pago' WHERE id = ?", (row['id'],))
                        conn.commit()
                        st.rerun()
                    
                    msg = f"Olá {row['nome']}, segue o lembrete da sua parcela de hoje: R$ {row['valor_parcela']:.2f}. Chave Pix para pagamento: {row['chave_pix']}"
                    link_zap = f"https://wa.me{row['whatsapp']}?text={msg.replace(' ', '%20')}"
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
                    st.write(f"⚠️ **{row['nome']}**")
                    st.write(f"Venceu em: {row['data_vencimento']} | Parc: {row['numero_parcela']}")
                    st.write(f"Valor: R$ {row['valor_parcela']:.2f}")
                    if st.button("✔ Baixar Atrasado", key=f"atrasado_{row['id']}"):
                        cursor.execute("UPDATE parcelas SET status = 'Pago' WHERE id = ?", (row['id'],))
                        conn.commit()
                        st.rerun()

# ----------------- ABA 2: CADASTRAR NOVO CLIENTE (COM AJUSTES) -----------------
with aba2:
    st.header("👤 Nova Venda / Empréstimo")
    with st.form("cadastro_cliente"):
        nome = st.text_input("Nome Completo do Cliente")
        whatsapp = st.text_input("WhatsApp (Ex: 5521999999999)")
        chave_pix_receber = st.text_input("Sua Chave Pix para este cliente")
        valor_total = st.number_input("Valor Total da Venda (R$)", min_value=1.0, step=10.0)
        qtd_parcelas = st.number_input("Quantidade de Parcelas Diárias", min_value=1, step=1)
        
        # 📊 NOVA FUNÇÃO: Escolha da porcentagem de lucro da venda
        pct_lucro = st.number_input("Porcentagem de Lucro desta venda (%)", min_value=0.0, max_value=100.0, value=35.0, step=1.0)
        
        # 🔄 NOVA FUNÇÃO: Seletor de parcelas já pagas anteriormente
        parcelas_ja_pagas = st.number_input("Quantas parcelas diárias o cliente JÁ PAGOU antes de você cadastrar?", min_value=0, max_value=int(qtd_parcelas), value=0, step=1)
        
        enviar = st.form_submit_button("Gerar Contrato Diário")
        
        if enviar and nome and whatsapp and chave_pix_receber:
            cursor.execute("INSERT INTO clientes (nome, whatsapp, valor_total, chave_pix, porcentagem_lucro) VALUES (?, ?, ?, ?, ?)", 
                           (nome, whatsapp, valor_total, chave_pix_receber, pct_lucro))
            cliente_id = cursor.lastrowid
            
            valor_por_parcela = valor_total / qtd_parcelas
            data_inicio = datetime.now()
            
            for i in range(1, qtd_parcelas + 1):
                data_vencimento = (data_inicio + timedelta(days=i-1)).strftime("%Y-%m-%d")
                
                # Se o número da parcela for menor ou igual à quantidade já paga, ela entra direto como 'Pago'
                status_inicial = 'Pago' if i <= parcelas_ja_pagas else 'Pendente'
                
                cursor.execute("""
                    INSERT INTO parcelas (cliente_id, numero_parcela, data_vencimento, valor_parcela, status) 
                    VALUES (?, ?, ?, ?, ?)
                """, (cliente_id, i, data_vencimento, valor_por_parcela, status_inicial))
            
            conn.commit()
            st.success(f"Contrato criado para {nome}! {parcelas_ja_pagas} parcelas marcadas automaticamente como pagas.")
            st.rerun()

# ----------------- ABA 3:📈 ESTATÍSTICAS FINANCEIRAS (NOVA ABA) -----------------
with aba4: # Ajustado temporariamente para manter a ordem visual
    pass 

with aba3:
    st.header("📈 Resumo Financeiro Geral")
    
    # 💰 Cálculo do valor que ainda vai receber (Parcelas 'Pendente' ou 'Atrasado')
    cursor.execute("SELECT SUM(valor_parcela) FROM parcelas WHERE status != 'Pago'")
    total_a_receber = cursor.fetchone()[0] or 0.0
    
    # 💳 Cálculo do valor já recebido (Parcelas 'Pago')
    cursor.execute("SELECT SUM(valor_parcela) FROM parcelas WHERE status = 'Pago'")
    total_recebido = cursor.fetchone()[0] or 0.0

    # 📊 Cálculo do Lucro com base na porcentagem personalizada de cada cliente
    # Lucro já recebido
    query_lucro_pago = """
    SELECT SUM(p.valor_parcela * (c.porcentagem_lucro / 100.0)) 
    FROM parcelas p JOIN clientes c ON p.cliente_id = c.id WHERE p.status = 'Pago'
    """
    cursor.execute(query_lucro_pago)
    lucro_recebido = cursor.fetchone()[0] or 0.0

    # Lucro que ainda vai entrar
    query_lucro_futuro = """
    SELECT SUM(p.valor_parcela * (c.porcentagem_lucro / 100.0)) 
    FROM parcelas p JOIN clientes c ON p.cliente_id = c.id WHERE p.status != 'Pago'
    """
    cursor.execute(query_lucro_futuro)
    lucro_a_receber = cursor.fetchone()[0] or 0.0

    # Exibição dos Blocos de Informação Financeira
    col1, col2 = st.columns(2)
    with col1:
        st.metric(label="💰 Total a Receber (Futuro)", value=f"R$ {total_a_receber:.2f}")
        st.metric(label="🟢 Total Já Arrecadado", value=f"R$ {total_recebido:.2f}")
        
    with col2:
        st.metric(label="📈 Lucro Previsto (Das parcelas que faltam)", value=f"R$ {lucro_a_receber:.2f}", delta_color="normal")
        st.metric(label="💰 Lucro Realizado (Já no bolso)", value=f"R$ {lucro_recebido:.2f}")

# ----------------- ABA 4: HISTÓRICO GERAL E EXCLUSÃO -----------------
with aba4:
    st.header("📁 Todos os Clientes Cadastrados")
    df_clientes = pd.read_sql_query("SELECT id, nome, whatsapp, valor_total, porcentagem_lucro as 'Lucro (%)' FROM clientes", conn)
    st.dataframe(df_clientes, use_container_width=True)
    
    st.header("🔍 Histórico Completo de Parcelas")
    df_todas_parcelas = pd.read_sql_query("""
        SELECT p.id, c.nome, p.numero_parcela, p.data_vencimento, p.valor_parcela, p.status 
        FROM parcelas p JOIN clientes c ON p.cliente_id = c.id
        ORDER BY p.data_vencimento DESC
    """, conn)
    st.dataframe(df_todas_parcelas, use_container_width=True)
    
    # ❌ Função de Exclusão de Cliente
    st.markdown("---")
    st.header("❌ Excluir Cliente do Sistema")
    df_selecao = pd.read_sql_query("SELECT id, nome FROM clientes", conn)
    
    if not df_selecao.empty:
        opcoes_clientes = [f"{row['id']} - {row['nome']}" for idx, row in df_selecao.iterrows()]
        cliente_para_excluir = st.selectbox("Selecione quem deseja deletar permanentemente:", opciones_clientes)
        id_cliente_excluir = int(cliente_para_excluir.split(" - ")[0])
        nome_cliente_excluir = cliente_para_excluir.split(" - ")[1]
        
        if st.button(f"🗑️ Apagar {nome_cliente_excluir} e Histórico", type="primary"):
            cursor.execute("DELETE FROM parcelas WHERE cliente_id = ?", (id_cliente_excluir,))
            cursor.execute("DELETE FROM clientes WHERE id = ?", (id_cliente_excluir,))
