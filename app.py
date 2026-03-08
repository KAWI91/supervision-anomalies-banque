import streamlit as st
import psycopg2
import pandas as pd
import time

@st.cache_resource
def init_connection():
    retries = 3
    while retries > 0:
        try:
            return psycopg2.connect(
                host=st.secrets["postgres"]["host"],
                database=st.secrets["postgres"]["database"],
                user=st.secrets["postgres"]["user"],
                password=st.secrets["postgres"]["password"],
                port=st.secrets["postgres"]["port"],
                sslmode="require",
                connect_timeout=10
            )
        except psycopg2.OperationalError as e:
            retries -= 1
            if retries == 0:
                st.error("Impossible de contacter la base de données. Vérifiez votre connexion internet.")
                raise e
            time.sleep(2) # Attendre 2 secondes avant de réessayer

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
# --- CONNEXION ---
if st.session_state.user_id is None:
    st.title("CONTRÖLE PERMANENT")
    st.title("Fiche de contrôle anomalies")
    st.title("🔐 Accès Sécurisé")
    with st.form("login_form"):
        email = st.text_input("Identifiant (Email)").lower().strip()
        pwd = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter"):
            try:
                conn = init_connection()
                query = f"""
                    SELECT u.id_utilisateur, u.nom, r.nom_role, u.id_groupe, g.nom_groupe, u.actif
                    FROM utilisateurs u 
                    JOIN groupes g ON u.id_groupe = g.id_groupe
                    JOIN roles r ON u.id_role = r.id_role
                    WHERE u.email='{email}' AND u.password='{pwd}'
                """
                user_data = pd.read_sql(query, conn)
                conn.close()
                
                if not user_data.empty:
                    # 1. Vérification du statut actif
                    if not user_data.iloc[0]['actif']:
                        st.error("🚫 Ce compte a été désactivé. Contactez l'administrateur.")
                    else:
                        # 2. REMPLISSAGE INDISPENSABLE DU SESSION STATE
                        user = user_data.iloc[0]
                        st.session_state.update({
                            'user_id': int(user['id_utilisateur']),
                            'user_nom': user['nom'],
                            'user_role': user['nom_role'],
                            'group_id': int(user['id_groupe']),
                            'group_nom': user['nom_groupe']
                        })
                        st.success(f"Bienvenue {user['nom']} !")
                        st.rerun()
                else:
                    st.error("Identifiants incorrects.")
            except Exception as e:
                st.error(f"Erreur de connexion : {e}")

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
    # --- PAGE : PARAMÉTRAGE GLOBAL ---
    elif page == "Paramétrage Global":
        st.title("⚙️ Configuration")
        t1, t2, t3, t4 = st.tabs(["📁 Régionales", "🏢 Agences", "🔑 Rôles", "🚩 Types"])
        
        # --- TAB 1 : RÉGIONALES ---
        # --- TAB 1 : RÉGIONALES ---
        with t1:
            st.subheader("Nouvelle Régionale")
            with st.form("f_reg", clear_on_submit=True):
                col_c, col_n = st.columns([1, 3])
                cod_r = col_c.text_input("Code (3 ch.)", max_chars=3)
                nom_r = col_n.text_input("Nom de la Régionale (ex: CENTRE)")
                
                if st.form_submit_button("Ajouter"):
                    if cod_r.isdigit() and len(cod_r) == 3 and nom_r:
                        try:
                            c = init_connection(); cur = c.cursor()
                            cur.execute("INSERT INTO regionales (code_region, nom_region) VALUES (%s, %s)", (cod_r, nom_r.upper().strip()))
                            c.commit(); c.close()
                            st.success(f"Régionale '{cod_r}' enregistrée.")
                            st.rerun()
                        except Exception as e: st.error(f"Erreur : {e}")
                    else:
                        st.warning("Veuillez saisir un code à 3 chiffres et un nom.")
            
            # Affichage de la liste
            st.write("---")
            conn = init_connection()
            df_list_reg = pd.read_sql("SELECT code_region AS Code, nom_region AS Régionale FROM regionales ORDER BY code_region", conn)
            conn.close()
            if not df_list_reg.empty:
                st.dataframe(df_list_reg, use_container_width=True, hide_index=True)

        # --- TAB 2 : AGENCES ---
        # --- TAB 2 : AGENCES ---
        with t2:
            st.subheader("Nouvelle Agence")
            conn = init_connection()
            df_reg_ref = pd.read_sql("SELECT id_region, code_region, nom_region FROM regionales", conn)
            conn.close()
            
            if not df_reg_ref.empty:
                with st.form("f_age", clear_on_submit=True):
                    c1, c2 = st.columns([1, 2])
                    cod_a = c1.text_input("Code (5 ch.)", max_chars=5)
                    nom_a = c2.text_input("Nom de l'Agence")
                    
                    reg_options = {f"{r['code_region']} - {r['nom_region']}": r['id_region'] for _, r in df_reg_ref.iterrows()}
                    p = st.selectbox("Rattachée à la Régionale :", options=list(reg_options.keys()))
                    
                    if st.form_submit_button("Enregistrer l'Agence"):
                        if cod_a.isdigit() and len(cod_a) == 5 and nom_a:
                            try:
                                c = init_connection(); cur = c.cursor()
                                cur.execute("INSERT INTO agences (code_agence, nom_agence, id_region) VALUES (%s, %s, %s)", 
                                           (cod_a, nom_a.upper().strip(), reg_options[p]))
                                c.commit(); c.close()
                                st.success(f"Agence '{cod_a}' créée.")
                                st.rerun()
                            except Exception as e: st.error(f"Erreur : {e}")
            
            # --- LISTE DES AGENCES (Version Tables Dédiées) ---
            st.write("---")
            st.subheader("Liste des Agences et Rattachements")
            
            conn = init_connection()
            query_agences = """
                SELECT 
                    a.code_agence AS "Code", 
                    a.nom_agence AS "Agence", 
                    r.nom_region AS "Régionale de rattachement"
                FROM agences a
                JOIN regionales r ON a.id_region = r.id_region
                ORDER BY r.nom_region, a.code_agence
            """
            try:
                df_list_age = pd.read_sql(query_agences, conn)
                if not df_list_age.empty:
                    # Ajout d'une option de suppression visuelle (optionnel)
                    df_list_age.insert(0, "Sél.", False)
                    st.dataframe(df_list_age, use_container_width=True, hide_index=True)
                else:
                    st.info("Aucune agence enregistrée dans la nouvelle structure.")
            except Exception as e:
                st.error(f"Erreur lors de la lecture des agences : {e}")
            finally:
                conn.close()

        # --- TAB 3 : RÔLES ---
        with t3:
            with st.form("f_role", clear_on_submit=True):
                n_role = st.text_input("Nom du Rôle")
                if st.form_submit_button("Ajouter le rôle"):
                    if n_role:
                        try:
                            c = init_connection(); cur = c.cursor()
                            cur.execute("INSERT INTO roles (nom_role) VALUES (%s)", (n_role.capitalize(),))
                            c.commit(); c.close()
                            st.toast(f"✅ Rôle {n_role} créé !", icon="🔑")
                            st.success(f"Rôle '{n_role}' ajouté.")
                        except Exception as e: st.error(f"Erreur : {e}")
            # Affichage de la liste existante
            conn = init_connection()
            df_roles = pd.read_sql("SELECT id_role, nom_role FROM roles ORDER BY nom_role", conn)
            conn.close()
            if not df_roles.empty:
                st.write("---")
                st.write("**Rôles actuels :**")
                df_roles.insert(0, "Sél.", False)
                edited_roles = st.data_editor(df_roles, hide_index=True, use_container_width=True, key="ed_role_admin")
                delete_items("roles", "id_role", edited_roles[edited_roles["Sél."] == True]["id_role"].tolist())
            
            

        # --- TAB 4 : TYPES ---
        with t4:
            with st.form("f_type_anom", clear_on_submit=True):
                n_type = st.text_input("Désignation de l'anomalie")
                if st.form_submit_button("Ajouter le processus"):
                    if n_type:
                        try:
                            c = init_connection(); cur = c.cursor()
                            cur.execute("INSERT INTO types_anomalies (nom_type) VALUES (%s)", (n_type.capitalize(),))
                            c.commit(); c.close()
                            st.toast(f"✅ Type enregistré !", icon="🚩")
                            st.success(f"Type '{n_type}' ajouté à la liste.")
                        except Exception as e: st.error(f"Erreur : {e}")
            
            # Affichage de la liste existante
            conn = init_connection()
            df_types = pd.read_sql("SELECT id_type, nom_type FROM types_anomalies ORDER BY nom_type", conn)
            conn.close()
            if not df_types.empty:
                st.write("---")
                st.write("**Types enregistrés :**")
                df_types.insert(0, "Sél.", False)
                edited_types = st.data_editor(df_types, hide_index=True, use_container_width=True, key="ed_type_admin")
                delete_items("types_anomalies", "id_type", edited_types[edited_types["Sél."] == True]["id_type"].tolist())

    # --- PAGE : GESTION UTILISATEURS ---
    # --- PAGE : GESTION UTILISATEURS ---
    # --- PAGE : GESTION UTILISATEURS (VERSION OPTIMISÉE) ---
    elif page == "Gestion Utilisateurs":
        st.title("👥 Administration des Comptes")
        # --- CHARGEMENT DES DONNÉES DE RÉFÉRENCE ---
        conn = init_connection()
        # Récupération des régionales pour info
        df_reg_ref = pd.read_sql("SELECT id_region, code_region, nom_region FROM regionales ORDER BY code_region", conn)
        # Récupération des agences avec le nom de leur régionale
        query_agences_list = """
            SELECT a.id_agence, a.code_agence, a.nom_agence, r.nom_region 
            FROM agences a 
            JOIN regionales r ON a.id_region = r.id_region 
            ORDER BY a.code_agence
        """
        df_age_ref = pd.read_sql(query_agences_list, conn)
        conn.close()
        
        # 1. INITIALISATION DES VARIABLES (Évite le NameError si la DB est lente)
        df_r = pd.DataFrame(columns=['id_role', 'nom_role'])
        df_g = pd.DataFrame(columns=['id_groupe', 'nom_groupe'])
        df_users = pd.DataFrame()
        conn = None

        # 2. CHARGEMENT UNIQUE DES DONNÉES
        try:
            conn = init_connection()
            # Chargement des rôles et groupes pour les listes déroulantes
            df_r = pd.read_sql("SELECT id_role, nom_role FROM roles ORDER BY nom_role", conn)
            df_g = pd.read_sql("SELECT id_groupe, nom_groupe FROM groupes ORDER BY nom_groupe", conn)
            
            # Chargement de la liste principale des utilisateurs
            # Modifie la requête SQL dans la section "Gestion Utilisateurs"
            query_users = """
                SELECT u.id_utilisateur, u.actif AS "Accès", u.matricule AS "Matricule", 
                    u.nom AS "Nom", u.prenom AS "Prénom", u.code_agence AS "Code Agence",
                    u.email AS "Email", r.nom_role AS "Rôle", g.nom_groupe AS "Affectation"
                FROM utilisateurs u
                JOIN roles r ON u.id_role = r.id_role
                JOIN groupes g ON u.id_groupe = g.id_groupe
                ORDER BY u.nom
            """
            
            df_users = pd.read_sql(query_users, conn)
            
        except Exception as e:
            st.error(f"⚠️ Erreur de connexion : {e}")
            st.info("Note : Si l'erreur persiste sur localhost, vérifiez que le port 5432 est ouvert dans votre firewall/antivirus.")

        # 3. FORMULAIRE DE CRÉATION
        if not df_r.empty and not df_g.empty:
            with st.expander("➕ Créer un nouvel utilisateur", expanded=False):
                with st.form("f_user_new", clear_on_submit=True):
                    c1, c2 = st.columns(2)
                    nom_new = c1.text_input("Nom de famille").upper()
                    prenom_new = c2.text_input("Prénom").capitalize()
                    
                    em_new = c1.text_input("Email (Login)").lower().strip()
                    mat_new = c2.text_input("Matricule (5 chiffres)", max_chars=5)
                    
                    # Sélection du Rôle
                    role_map = {r['nom_role']: r['id_role'] for _, r in df_r.iterrows()}
                    r_sel = c1.selectbox("Rôle attribué", options=list(role_map.keys()))
                    
                    # --- SÉLECTION DE L'AGENCE (LISTE DÉROULANTE) ---
                    # On crée une étiquette propre : "00101 - Agence Alger"
                    age_options = {f"{row['code_agence']} - {row['nom_agence']}": row['code_agence'] 
                                for _, row in df_age_ref.iterrows()}
                    
                    age_display = c2.selectbox("Affectation Agence", options=list(age_options.keys()))
                    code_age_final = age_options[age_display] # On récupère juste les 5 chiffres
                    
                    pw_new = st.text_input("Mot de passe par défaut", value="12345", type="password")
                    
                    if st.form_submit_button("Créer le compte"):
                        if nom_new and prenom_new and em_new and mat_new.isdigit() and len(mat_new) == 5:
                            try:
                                conn = init_connection()
                                cur = conn.cursor()
                                cur.execute("""
                                    INSERT INTO utilisateurs (nom, prenom, email, matricule, code_agence, id_role, id_groupe, password, actif) 
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, True)
                                """, (nom_new, prenom_new, em_new, mat_new, code_age_final, int(role_map[r_sel]), 1, pw_new)) 
                                # Note: id_groupe est mis à 1 par défaut ici, à adapter selon ta structure
                                conn.commit()
                                conn.close()
                                st.success(f"✅ Compte créé pour {prenom_new} {nom_new} (Agence {code_age_final})")
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Erreur : {ex}")
                        else:
                            st.warning("Vérifiez les champs (Nom, Prénom, Email et Matricule à 5 chiffres).")

        st.divider()

        # 4. TABLEAU D'ÉDITION DES ACCÈS ET AUDIT
        if not df_users.empty:
            st.subheader("Liste des comptes et accès")
            st.info("Cochez ou décochez la case 'Accès' puis cliquez sur le bouton Sauvegarder en bas.")
            
            edited_df = st.data_editor(
                df_users, 
                hide_index=True, 
                use_container_width=True,
                column_config={
                    "id_utilisateur": None, # ID masqué
                    "Accès": st.column_config.CheckboxColumn("Accès", help="Activer/Désactiver l'accès")
                },
                disabled=["Nom", "Email", "Rôle", "Affectation"]
            )
            
            if st.button("💾 Sauvegarder les modifications de statut", type="primary"):
                try:
                    cur = conn.cursor()
                    # Récupération de l'état actuel pour comparer et créer l'audit
                    cur.execute("SELECT id_utilisateur, actif, nom FROM utilisateurs")
                    old_states = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
                    
                    changes = 0
                    for _, row in edited_df.iterrows():
                        u_id = int(row["id_utilisateur"])
                        new_val = bool(row["Accès"])
                        old_val, u_nom = old_states.get(u_id, (None, "Inconnu"))
                        
                        if new_val != old_val:
                            # Mise à jour
                            cur.execute("UPDATE utilisateurs SET actif = %s WHERE id_utilisateur = %s", (new_val, u_id))
                            # Log audit
                            action_txt = "Activation" if new_val else "Désactivation"
                            cur.execute("""
                                INSERT INTO audit_log (admin_nom, utilisateur_cible, action, statut_final)
                                VALUES (%s, %s, %s, %s)
                            """, (st.session_state.user_nom, u_nom, action_txt, new_val))
                            changes += 1
                    
                    if changes > 0:
                        conn.commit()
                        st.toast(f"✅ {changes} comptes mis à jour !")
                        st.rerun()
                    else:
                        st.info("Aucune modification détectée.")
                except Exception as e:
                    st.error(f"Erreur lors de la sauvegarde : {e}")

            # 5. AFFICHAGE DU JOURNAL D'AUDIT
            with st.expander("📜 Journal d'audit (10 dernières actions)"):
                try:
                    df_audit = pd.read_sql("""
                        SELECT date_action as "Date", admin_nom as "Administrateur", 
                               utilisateur_cible as "Cible", action as "Action"
                        FROM audit_log ORDER BY date_action DESC LIMIT 10
                    """, conn)
                    if not df_audit.empty:
                        st.table(df_audit)
                    else:
                        st.write("Le journal est vide.")
                except:
                    st.write("Journal d'audit indisponible.")

        # FERMETURE DE LA CONNEXION UNIQUE
        if conn:
            conn.close()     
            

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
