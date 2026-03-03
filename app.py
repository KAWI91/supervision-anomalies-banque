import streamlit as st
import psycopg2
import pandas as pd

# --- CONFIGURATION ---
st.set_page_config(page_title="Banque - Gestion des Anomalies", page_icon="🏦", layout="wide")

def init_connection():
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        database=st.secrets["postgres"]["database"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"],
        port=st.secrets["postgres"]["port"],
        sslmode="require"
    )

# --- SESSION STATE ---
if 'user_id' not in st.session_state:
    st.session_state.update({
        'user_id': None, 'user_role': None, 'user_nom': None, 
        'group_id': None, 'group_nom': None
    })

# --- CONNEXION ---
if st.session_state.user_id is None:
    st.title("🔐 Accès Sécurisé")
    with st.form("login_form"):
        email = st.text_input("Identifiant (Email)").lower().strip()
        pwd = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter"):
            try:
                conn = init_connection()
                query = f"""
                    SELECT u.id_utilisateur, u.nom, r.nom_role, u.id_groupe, g.nom_groupe 
                    FROM utilisateurs u 
                    JOIN groupes g ON u.id_groupe = g.id_groupe
                    JOIN roles r ON u.id_role = r.id_role
                    WHERE u.email='{email}' AND u.password='{pwd}'
                """
                user_data = pd.read_sql(query, conn)
                conn.close()
                if not user_data.empty:
                    st.session_state.update({
                        'user_id': int(user_data.iloc[0]['id_utilisateur']),
                        'user_role': user_data.iloc[0]['nom_role'],
                        'user_nom': user_data.iloc[0]['nom'],
                        'group_id': int(user_data.iloc[0]['id_groupe']),
                        'group_nom': user_data.iloc[0]['nom_groupe']
                    })
                    st.rerun()
                else:
                    st.error("Identifiants incorrects.")
            except Exception as e:
                st.error(f"Erreur : {e}")

else:
    # --- SIDEBAR ---
    st.sidebar.title(f"👋 {st.session_state.user_nom}")
    st.sidebar.info(f"Rôle : {st.session_state.user_role}\nPérimètre : {st.session_state.group_nom}")
    
    menu = ["Tableau de bord", "Déclarer une Anomalie", "Mon Compte"]
    if st.session_state.user_role == 'Administrateur':
        menu.extend(["--- Admin ---", "Paramétrage Global", "Gestion Utilisateurs"])
    
    page = st.sidebar.radio("Navigation", menu)
    
    if st.sidebar.button("Se déconnecter"):
        for key in list(st.session_state.keys()): st.session_state[key] = None
        st.rerun()

    # --- FONCTION GÉNÉRIQUE DE SUPPRESSION ---
    def delete_items(table_name, id_column, selected_ids):
        if selected_ids:
            if st.button(f"Supprimer la sélection ({len(selected_ids)})", type="primary", key=f"del_{table_name}"):
                try:
                    c = init_connection(); cur = c.cursor()
                    if len(selected_ids) > 1:
                        cur.execute(f"DELETE FROM {table_name} WHERE {id_column} IN %s", (tuple(selected_ids),))
                    else:
                        cur.execute(f"DELETE FROM {table_name} WHERE {id_column} = %s", (selected_ids[0],))
                    c.commit(); c.close()
                    st.success("✅ Suppression réussie !")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Impossible de supprimer : l'élément est utilisé ailleurs. {e}")

    # --- PAGE : TABLEAU DE BORD ---
    # --- PAGE : TABLEAU DE BORD (COMPLET AVEC FILTRE DATE) ---
    if page == "Tableau de bord":
        st.title("📊 Tableau de Bord Stratégique")
        try:
            conn = init_connection()
            # Requête avec Auto-Jointure pour la hiérarchie
            query_base = """
                SELECT 
                    a.date_constat, 
                    COALESCE(g_parent.nom_groupe, g.nom_groupe) as regionale,
                    g.nom_groupe as agence, 
                    u.nom as agent, 
                    ta.nom_type as type, 
                    a.montant_erreur 
                FROM anomalies a 
                JOIN utilisateurs u ON a.id_utilisateur = u.id_utilisateur 
                JOIN groupes g ON u.id_groupe = g.id_groupe 
                LEFT JOIN groupes g_parent ON g.id_parent = g_parent.id_groupe
                LEFT JOIN types_anomalies ta ON a.id_type = ta.id_type
            """
            
            # Récupération initiale des données
            if st.session_state.user_role != 'Administrateur':
                query_ids = f"SELECT id_groupe FROM groupes WHERE id_groupe = {st.session_state.group_id} OR id_parent = {st.session_state.group_id}"
                ids_list = pd.read_sql(query_ids, conn)['id_groupe'].tolist()
                ids = tuple(ids_list)
                filtre_sql = f" WHERE u.id_groupe IN {ids}" if len(ids) > 1 else f" WHERE u.id_groupe = {ids[0]}"
                df = pd.read_sql(query_base + filtre_sql, conn)
            else:
                df = pd.read_sql(query_base, conn)

            conn.close()

            # Conversion de la colonne date en format Date Python
            df['date_constat'] = pd.to_datetime(df['date_constat']).dt.date

            # --- ZONE DE FILTRES ---
            with st.expander("🔍 Filtres de recherche", expanded=True):
                # Filtre par Date (accessible à tous)
                c_d1, c_d2 = st.columns(2)
                date_min = df['date_constat'].min() if not df.empty else None
                date_max = df['date_constat'].max() if not df.empty else None
                
                start_date = c_d1.date_input("Date de début", value=date_min)
                end_date = c_d2.date_input("Date de fin", value=date_max)
                
                # Application du filtre date
                df = df[(df['date_constat'] >= start_date) & (df['date_constat'] <= end_date)]

                # Filtres hiérarchiques (Admin uniquement)
                if st.session_state.user_role == 'Administrateur':
                    st.divider()
                    c1, c2, c3 = st.columns(3)
                    
                    sel_reg = c1.multiselect("Régionale", options=df['regionale'].unique())
                    if sel_reg:
                        df = df[df['regionale'].isin(sel_reg)]
                    
                    sel_age = c2.multiselect("Agence", options=df['agence'].unique())
                    if sel_age:
                        df = df[df['agence'].isin(sel_age)]
                        
                    sel_type = c3.multiselect("Type d'anomalie", options=df['type'].unique())
                    if sel_type:
                        df = df[df['type'].isin(sel_type)]

            if not df.empty:
                # --- KPI ---
                st.subheader("Indicateurs Clés")
                col1, col2, col3 = st.columns(3)
                col1.metric("Nb Anomalies", len(df))
                col2.metric("Montant Total", f"{df['montant_erreur'].sum():,.2f} DA")
                col3.metric("Moyenne / Incident", f"{df['montant_erreur'].mean():,.2f} DA")
                
                st.divider()
                
                # --- GRAPHIQUES ---
                import plotly.express as px
                gc1, gc2 = st.columns(2)
                
                with gc1:
                    st.write("**Répartition Financière par Type**")
                    fig_pie = px.pie(df, names='type', values='montant_erreur', hole=0.4, 
                                     color_discrete_sequence=px.colors.qualitative.Pastel)
                    st.plotly_chart(fig_pie, use_container_width=True)
                    
                with gc2:
                    st.write("**Évolution Temporelle (Montants)**")
                    # On regroupe par date pour le graphique linéaire
                    df_trend = df.groupby('date_constat')['montant_erreur'].sum().reset_index()
                    fig_line = px.line(df_trend, x='date_constat', y='montant_erreur', markers=True)
                    st.plotly_chart(fig_line, use_container_width=True)

                st.subheader("Détail des opérations")
                st.dataframe(df, use_container_width=True)
                # --- SECTION EXPORT ---
                st.divider()
                st.subheader("📦 Exportation des données")
                
                # Préparation du fichier CSV
                csv = df.to_csv(index=False).encode('utf-8-sig') # utf-8-sig pour le support des accents sous Excel
                
                c_exp1, c_exp2 = st.columns([1, 4])
                with c_exp1:
                    st.download_button(
                        label="⬇️ Télécharger en CSV",
                        data=csv,
                        file_name=f"anomalies_{start_date}_au_{end_date}.csv",
                        mime="text/csv",
                    )
                with c_exp2:
                    st.info("💡 Le fichier CSV contient uniquement les données correspondant à vos filtres actuels.")
            else:
                st.info("⚠️ Aucune anomalie trouvée pour cette période ou ces critères.")
                
        except Exception as e:
            st.error(f"Erreur de traitement : {e}")
            

    # --- PAGE : PARAMÉTRAGE GLOBAL ---
    elif page == "Paramétrage Global":
        st.title("⚙️ Configuration")
        t1, t2, t3, t4 = st.tabs(["📁 Régionales", "🏢 Agences", "🔑 Rôles", "🚩 Types"])
        # (Le code des onglets reste le même que celui que vous avez fourni)
        with t1:
            with st.form("f_reg"):
                n = st.text_input("Nom de la Régionale")
                if st.form_submit_button("Ajouter"):
                    c = init_connection(); cur = c.cursor()
                    cur.execute("INSERT INTO groupes (nom_groupe) VALUES (%s)", (n.upper(),))
                    c.commit(); c.close(); st.rerun()

    # --- PAGE : GESTION UTILISATEURS ---
    elif page == "Gestion Utilisateurs":
        st.title("👥 Administration des Comptes")
        conn = init_connection()
        df_r = pd.read_sql("SELECT * FROM roles", conn)
        df_g = pd.read_sql("SELECT * FROM groupes ORDER BY nom_groupe", conn)
        conn.close()
        with st.expander("➕ Créer un utilisateur"):
            with st.form("f_user"):
                nom = st.text_input("Nom")
                em = st.text_input("Email")
                role_map = {r['nom_role']: r['id_role'] for _, r in df_r.iterrows()}
                grp_map = {g['nom_groupe']: g['id_groupe'] for _, g in df_g.iterrows()}
                r_sel = st.selectbox("Rôle", options=list(role_map.keys()))
                g_sel = st.selectbox("Groupe", options=list(grp_map.keys()))
                if st.form_submit_button("Créer"):
                    try:
                        c = init_connection(); cur = c.cursor()
                        cur.execute("INSERT INTO utilisateurs (nom, email, id_role, id_groupe, password) VALUES (%s,%s,%s,%s,'12345')",
                                   (nom, em.lower(), int(role_map[r_sel]), int(grp_map[g_sel])))
                        c.commit(); c.close(); st.rerun()
                    except Exception as e: st.error(f"Erreur : {e}")

    # --- PAGE : DÉCLARER UNE ANOMALIE ---
    elif page == "Déclarer une Anomalie":
        st.title("🚩 Saisie d'Incident")
        if 'form_success' not in st.session_state: st.session_state.form_success = False
        conn = init_connection()
        df_t = pd.read_sql("SELECT * FROM types_anomalies ORDER BY nom_type", conn)
        conn.close()
        with st.form("form_anomalie", clear_on_submit=True):
            t_nom = st.selectbox("Type", options={row['nom_type']: row['id_type'] for _, row in df_t.iterrows()})
            m = st.number_input("Montant (DA)", min_value=0.0)
            d = st.date_input("Date")
            obs = st.text_area("Description")
            c_save, c_new = st.columns([1, 4])
            submit = c_save.form_submit_button("Enregistrer")
            if c_new.form_submit_button("Effacer / Nouveau"): st.rerun()
            
            if submit:
                if m > 0:
                    try:
                        id_t = int(df_t.set_index('nom_type').loc[t_nom, 'id_type'])
                        c = init_connection(); cur = c.cursor()
                        cur.execute("INSERT INTO anomalies (date_constat, id_type, montant_erreur, id_utilisateur, description) VALUES (%s,%s,%s,%s,%s)",
                                   (d, id_t, m, st.session_state.user_id, obs))
                        c.commit(); c.close()
                        st.success("✅ Enregistré !")
                        st.session_state.form_success = True
                    except Exception as e: st.error(f"Erreur : {e}")
        if st.session_state.form_success:
            if st.button("Saisir une autre"):
                st.session_state.form_success = False
                st.rerun()