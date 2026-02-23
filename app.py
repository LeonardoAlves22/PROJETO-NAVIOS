import streamlit as st
import pandas as pd
from datetime import datetime
from ws_robot import extrair_checklist_ws

# ... (Mantenha as suas funções de limpar_nome e buscar_dados aqui em cima) ...

st.sidebar.divider()
st.sidebar.subheader("🔒 Acesso Visitador")
ws_user = st.sidebar.text_input("Usuário WS")
ws_pass = st.sidebar.text_input("Senha WS", type="password")

if st.button("🚀 Sincronizar Checklist de TODOS os Navios"):
    if not ws_user or not ws_pass:
        st.warning("Preencha as credenciais na lateral.")
    else:
        # Pega a lista de navios processada na última atualização
        # Nota: assumindo que 'res_slz' e 'res_bel' foram gerados no clique anterior
        if 'res_slz' not in locals() and 'res_bel' not in locals():
            # Se as variáveis não existem, rodamos a busca de dados primeiro
            slz_b, bel_b, e_db, corte = buscar_dados()
            # Lógica simplificada para obter apenas os nomes limpos
            lista_navios = [limpar_nome_navio(n) for n in (slz_b + bel_b)]
        else:
            lista_navios = [d['navio'] for d in (res_slz + res_bel)]

        if not lista_navios:
            st.error("Nenhum navio encontrado para processar.")
        else:
            with st.spinner("Iniciando processamento em lote..."):
                progresso = st.progress(0)
                status_msg = st.empty()
                resultados_finais = []

                for i, nome in enumerate(lista_navios):
                    status_msg.text(f"Consultando {nome} ({i+1}/{len(lista_navios)})...")
                    
                    # Chama o robô para o navio individual
                    res_robot = extrair_checklist_ws(ws_user, ws_pass, EMAIL_USER, EMAIL_PASS, nome)
                    
                    if "Erro" not in res_robot:
                        res_robot["Navio"] = nome
                        resultados_finais.append(res_robot)
                    else:
                        resultados_finais.append({"Navio": nome, "Status": "Erro no Acesso"})
                    
                    progresso.progress((i + 1) / len(lista_navios))

                status_msg.success("Processamento concluído!")
                
                # Exibe a tabela consolidada
                st.subheader("📊 Resumo de Checklists Operacionais")
                df_final = pd.DataFrame(resultados_finais)
                # Reorganiza colunas para o Navio vir primeiro
                cols = ["Navio"] + [c for c in df_final.columns if c != "Navio"]
                st.dataframe(df_final[cols], use_container_width=True, hide_index=True)
