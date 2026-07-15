import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta

# Configuração da página
st.set_page_config(page_title="Controle de Cobrança Master", layout="wide")

# Conexão com o banco de dados local com isolamento de thread
def conectar_bd():
    conn = sqlite3.connect("cobrancas.db", check_same_thread=False)
    cursor = conn.cursor()
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

# Atualização automática de atrasados
data_hoje = datetime.now().strftime("%Y-%m-%d")
try:
    cursor.execute("UPDATE parcelas SET status = 'Atrasado' WHERE data_vencimento < ? AND status = 'Pendente'", (data_hoje,))
    conn.commit()
except:
    pass

st.title("💸 Sistema de Cobrança Diária Pro")

aba1, aba2, aba3, aba4, aba5 = st.tabs([
    "📊 Painel de Cobrança", "➕ Nova Venda", "💰 Projeção e Lucros", "👥 Clientes e Histórico", "🗑️ Remover Dados"
])

# ----------------- ABA 1: PAINEL DE COBRANÇA -----------------
with aba1:
    col_A, col_B = st.columns(2)
    with col_A:
        st.header("📋 Para Hoje")
        try:
            query_hoje = """
            SELECT p.id, c.nome, c.whatsapp, c.chave_pix, p.numero_parcela, p.valor_parcela, p.status 
            FROM parcelas p 
            INNER JOIN clientes c ON p.cliente_id = c.id
            WHERE p.data_vencimento = ? AND p.status != 'Pago'
            """
            df_hoje = pd.read_sql_query(query_hoje, conn, params=(data_hoje,))
            if df_hoje.empty:
                st.info("Tudo limpo para hoje!")
            else:
                for idx, row in df_hoje.iterrows():
                    with st.expander(f"{row['nome']} - R$ {row['valor_parcela']:.2f}"):
                        if st.button("✔ Confirmar Pagamento", key=f"pago_{row['id']}"):
                            cursor.execute("UPDATE parcelas SET status = 'Pago' WHERE id = ?", (row['id'],))
                            conn.commit()
                            st.rerun()
                        msg = f"Olá {row['nome']}, lembrete da sua parcela de hoje: R$ {row['valor_parcela']:.2f}. Pix: {row['chave_pix']}"
                        link_zap = f"https://wa.me{row['whatsapp']}?text={msg.replace(' ', '%20')}"
                        st.markdown(f"[💬 Cobrar no WhatsApp]({link_zap})")
        except Exception as e:
            st.info("Aguardando a inserção de clientes ativos.")

    with col_B:
        st.header("🚨 Cobranças Atrasadas")
        try:
            query_atrasados = """
            SELECT p.id, c.nome, c.whatsapp, p.data_vencimento, p.valor_parcela, p.numero_parcela
            FROM parcelas p 
            INNER JOIN clientes c ON p.cliente_id = c.id 
            WHERE p.status = 'Atrasado'
            """
            df_atrasados = pd.read_sql_query(query_atrasados, conn)
            if df_atrasados.empty:
                st.success("Nenhum cliente em atraso! 🎉")
            else:
                for idx, row in df_atrasados.iterrows():
                    with st.container(border=True):
                        st.write(f"⚠️ **{row['nome']}** (Parc: {row['numero_parcela']})")
                        st.write(f"Valor: R$ {row['valor_parcela']:.2f} | Venceu: {row['data_vencimento']}")
                        if st.button("✔ Baixar Atrasado", key=f"atrasado_{row['id']}"):
                            cursor.execute("UPDATE parcelas SET status = 'Pago' WHERE id = ?", (row['id'],))
                            conn.commit()
                            st.rerun()
        except:
            st.info("Nenhum atraso registrado.")

# ----------------- ABA 2: NOVA VENDA -----------------
with aba2:
    st.header("👤 Nova Venda / Empréstimo")
    with st.form("cadastro_cliente"):
        nome = st.text_input("Nome Completo do Cliente")
        whatsapp = st.text_input("WhatsApp (Ex: 5521999999999)")
        chave_pix_receber = st.text_input("Sua Chave Pix para Receber")
        valor_total = st.number_input("Valor Total da Venda (R$)", min_value=1.0, step=10.0)
        qtd_parcelas = st.number_input("Quantidade de Parcelas Diárias", min_value=1, step=1)
        lucro_pct = st.number_input("Porcentagem de Lucro desta Venda (%)", min_value=1.0, max_value=100.0, value=35.0, step=1.0)
        parcelas_ja_pagas = st.number_input("Quantas parcelas diárias o cliente JÁ PAGOU antes de você cadastrar?", min_value=0, max_value=1000, value=0, step=1)
        
        enviar = st.form_submit_button("Gerar Contrato Diário")
        
        if enviar and nome and whatsapp and chave_pix_receber:
            cursor.execute("INSERT INTO clientes (nome, whatsapp, valor_total, chave_pix, porcentagem_lucro) VALUES (?, ?, ?, ?, ?)", 
                           (nome, whatsapp, valor_total, chave_pix_receber, lucro_pct))
            cliente_id = cursor.lastrowid
            
            valor_por_parcela = valor_total / qtd_parcelas
            data_inicio = datetime.now()
            
            for i in range(1, qtd_parcelas + 1):
                data_vencimento = (data_inicio + timedelta(days=i-1)).strftime("%Y-%m-%d")
                status_inicial = 'Pago' if i <= parcelas_ja_pagas else 'Pendente'
                
                cursor.execute("""
                    INSERT INTO parcelas (cliente_id, numero_parcela, data_vencimento, valor_parcela, status) 
                    VALUES (?, ?, ?, ?, ?)
                """, (cliente_id, i, data_vencimento, valor_por_parcela, status_inicial))
            
            conn.commit()
            st.success(f"Contrato criado para {nome}!")
            st.rerun()

# ----------------- ABA 3: PROJEÇÃO E LUCROS -----------------
with aba3:
    st.header("📈 Relatório Financeiro e Lucratividade")
    try:
        total_receber = pd.read_sql_query("SELECT SUM(valor_parcela) as total FROM parcelas WHERE status != 'Pago'", conn)['total'].fillna(0).values
        total_recebido = pd.read_sql_query("SELECT SUM(valor_parcela) as total FROM parcelas WHERE status = 'Pago'", conn)['total'].fillna(0).values
        
        col1, col2 = st.columns(2)
        col1.metric("💰 Total a Receber (Futuro)", f"R$ {total_receber:.2f}")
        col2.metric("✅ Total Já Recebido (Em Caixa)", f"R$ {total_recebido:.2f}")
        
        st.markdown("---")
        st.subheader("📊 Cálculo de Lucros por Venda")
        
        df_lucros = pd.read_sql_query("SELECT id, nome, valor_total, porcentagem_lucro FROM clientes", conn)
        
        if not df_lucros.empty:
            df_lucros['Lucro Estimado (R$)'] = (df_lucros['valor_total'] * df_lucros['porcentagem_lucro']) / 100
            st.dataframe(df_lucros, use_container_width=True)
            lucro_total_geral = df_lucros['Lucro Estimado (R$)'].sum()
            st.info(f"✨ Seu lucro total estimado com base nos contratos atuais é de: **R$ {lucro_total_geral:.2f}**")
        else:
            st.info("Nenhum contrato ativo para calcular lucros.")
    except:
        st.info("Aguardando registros para gerar os relatórios.")

# ----------------- ABA 4: HISTÓRICO GERAL -----------------
with aba4:
    st.header("📁 Histórico de Todas as Parcelas")
    try:
        df_todas_parcelas = pd.read_sql_query("""
            SELECT p.id, c.nome, p.numero_parcela, p.data_vencimento, p.valor_parcela, p.status 
            FROM parcelas p INNER JOIN clientes c ON p.cliente_id = c.id ORDER BY p.data_vencimento DESC
        """, conn)
        if not df_todas_parcelas.empty:
            st.dataframe(df_todas_parcelas, use_container_width=True)
        else:
            st.info("Nenhuma parcela registrada no histórico.")
    except:
        st.info("Histórico de parcelas vazio.")

# ----------------- ABA 5: REMOVER DADOS -----------------
with aba5:
    st.header("❌ Excluir Cliente do Sistema")
    df_selecao = pd.read_sql_query("SELECT id, nome FROM clientes", conn)
    
    if not df_selecao.empty:
        opcoes_clientes = [f"{row['id']} - {row['nome']}" for idx, row in df_selecao.iterrows()]
        cliente_para_excluir = st.selectbox("Selecione o cliente para deletar:", opciones_clientes)
        
        id_cliente_excluir = int(cliente_para_excluir.split(" - ")[0])
        nome_cliente_excluir = cliente_para_excluir.split(" - ")[1]
        
        if st.button(f"🗑️ Apagar {nome_cliente_excluir} permanentemente", type="primary"):
            cursor.execute("DELETE FROM parcelas WHERE cliente_id = ?", (id_cliente_excluir,))
            cursor.execute("DELETE FROM clientes WHERE id = ?", (id_cliente_excluir,))
            conn.commit()
            st.success(f"Cliente {nome_cliente_excluir} removido com sucesso!")
            st.rerun()
    else:
        st.info("Nenhum cliente cadastrado no momento para exclusão.")
