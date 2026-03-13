import streamlit as st
import pandas as pd
import psycopg2
import time
import plotly.express as px

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Banque Anomalies", layout="wide")

# --- INITIALISATION DU SESSION STATE ---
if 'user_id' not in st.session_state:
    st.session_state.update({
        'user_id': None,
        'user_role': None,
        'user_nom': None,
        'code_agence': None
    })

# --- FONCTION DE CONNEXION ---
def get_connection():
    try:
        return psycopg2.connect(
            host=st.secrets["postgres"]["host"],
            database=st.secrets["postgres"]["database"],
            user=st.secrets["postgres"]["user"],
            password=st.secrets["postgres"]["password"],
            port=st.secrets["postgres"]["port"],
            sslmode="require"
        )
    except Exception as e:
        st.error(f"❌ Erreur de connexion : {e}")
        return None

# --- LOGIQUE PRINCIPALE ---
if st.session_state['user_id'] is None:
    # --- ÉCRAN DE CONNEXION ---
    st.title("🔐 Accès Sécurisé - Contrôle Permanent")
    
    with st.form(key="login_form_main"):
        input_email = st.text_input("Identifiant (Email)").lower().strip()
        input_pwd = st.text_input("Mot de passe", type="password")
        submit_button = st.form_submit_button("Se connecter")

        if submit_button:
            if input_email and input_pwd:
                conn = get_connection()
                if conn:
                    try:
                        query = """
                            SELECT u.id_utilisateur, u.nom, u.prenom, r.nom_role, u.code_agence, u.actif
                            FROM utilisateurs u 
                            JOIN roles r ON u.id_role = r.id_role
                            WHERE u.email=%s AND u.password=%s
                        """
                        user_data = pd.read_sql(query, conn, params=[input_email, input_pwd])
                        
                        if not user_data.empty:
                            user = user_data.iloc[0]
                            if not user['actif']:
                                st.error("🚫 Compte désactivé.")
                            else:
                                st.session_state.update({
                                    'user_id': int(user['id_utilisateur']),
                                    'user_nom': f"{user['prenom']} {user['nom']}",
                                    'user_role': user['nom_role'],
                                    'code_agence': user['code_agence']
                                })
                                st.success(f"✅ Bienvenue {user['prenom']} !")
                                time.sleep(0.5)
                                st.rerun()
                        else:
                            st.error("❌ Identifiants incorrects.")
                    finally:
                        conn.close()
            else:
                st.warning("Veuillez remplir tous les champs.")

else:
    # --- INTERFACE APPLICATION (CONNECTÉ) ---
    role_user = st.session_state['user_role']
    user_nom = st.session_state['user_nom']
    code_agence = st.session_state['code_agence']
    
    # Droits d'accès
    can_create = role_user in ["Controleur", "Controle régional/central", "Controle 2ème degré", "Administrateur"]
    is_admin = (role_user == "Administrateur")

    # Sidebar
    st.sidebar.title(f"👋 {user_nom}")
    st.sidebar.info(f"**Rôle :** {role_user}\n\n**Agence :** {code_agence}")
    
    menu = ["Tableau de bord"]
    if can_create:
        menu.append("Déclarer une Anomalie")
    menu.append("Mon Compte")
    if is_admin:
        menu.append("--- ADMINISTRATION ---") 
        menu.append("Paramétrage Global")
        menu.append("Gestion Utilisateurs")
    
    page = st.sidebar.radio("Navigation", menu)
    
    if st.sidebar.button("Se déconnecter"):
        for key in list(st.session_state.keys()):
            st.session_state[key] = None
        st.rerun()

    # --- ROUTAGE DES PAGES ---
    # ---TABLEAU DE BORD
    # --- PAGE : TABLEAU DE BORD ---
    if page == "Tableau de bord":
        st.title("📊 Pilotage des Anomalies & Risques")
        conn = get_connection()
        if conn:
            # 1. Requête principale (on récupère tout pour filtrer ensuite)
            query_base = """
                SELECT 
                    a.id_anomalie, a.date_constat, 
                    reg.nom_region as regionale, age.nom_agence as agence, 
                    u.nom as agent, ta.nom_type as type, 
                    a.montant_erreur, rc.libelle_crit as criticite, 
                    a.statut_regle,
                    a.description,
                    a.commentaire_resolution
                FROM anomalies a 
                JOIN utilisateurs u ON a.id_utilisateur = u.id_utilisateur 
                JOIN agences age ON a.code_agence = age.code_agence 
                JOIN regionales reg ON age.id_region = reg.id_region
                LEFT JOIN types_anomalies ta ON a.id_type = ta.id_type
                LEFT JOIN ref_criticite rc ON a.id_crit = rc.id_crit
            """
            
            # 2. Filtrage selon le rôle (Périmètre de vue)
            if role_user in ["Administrateur", "Controle 2ème degré"]:
                df = pd.read_sql(query_base, conn)
            elif role_user in ["Responsable Régional/Central", "Controle régional/central"]:
                sql = query_base + " WHERE age.id_region = (SELECT id_region FROM agences WHERE code_agence = %s)"
                df = pd.read_sql(sql, conn, params=[st.session_state.code_agence])
            else:
                sql = query_base + " WHERE a.code_agence = %s"
                df = pd.read_sql(sql, conn, params=[st.session_state.code_agence])

            if not df.empty:
                # --- PRÉPARATION DES DONNÉES ---
                df['date_constat'] = pd.to_datetime(df['date_constat'])
                
                # 1. Calcul des compteurs principaux
                total_ano = len(df)
                nb_reglees = len(df[df['statut_regle'] == True])
                nb_en_cours = len(df[df['statut_regle'] == False])
                taux_reglement = (nb_reglees / total_ano * 100) if total_ano > 0 else 0

                # --- AFFICHAGE DES MÉTRIQUES (Cartes) ---
                st.subheader("📌 Indicateurs de Synthèse")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Anomalies", total_ano)
                m2.metric("✅ Réglées", nb_reglees)
                m3.metric("⏳ En cours", nb_en_cours, delta=f"{(nb_en_cours/total_ano*100):.1f}%", delta_color="inverse")
                m4.metric("📈 Taux de Résolution", f"{taux_reglement:.1f}%")

                st.divider()

                # --- ANALYSE TEMPORELLE ET CUMUL ---
                st.subheader("📈 Évolution Temporelle")
                
                # Groupement par jour
                df_daily = df.groupby('date_constat').size().reset_index(name='nb_jour')
                df_daily = df_daily.sort_values('date_constat')
                # Calcul du cumul
                df_daily['Cumul'] = df_daily['nb_jour'].cumsum()

                c_time1, c_time2 = st.columns(2)
                with c_time1:
                    st.write("**Signalements par jour**")
                    st.line_chart(df_daily.set_index('date_constat')['nb_jour'])
                with c_time2:
                    st.write("**Cumul des anomalies**")
                    st.area_chart(df_daily.set_index('date_constat')['Cumul'])

                st.divider()

                # --- VENTILATION PAR RÉGION ET AGENCE ---
                st.subheader("🏢 Ventilation Géographique")
                
                col_v1, col_v2 = st.columns(2)
                
                with col_v1:
                    st.write("**Statut par Régionale**")
                    # Pivot table pour avoir Réglé / En cours par Région
                    df_reg = df.groupby(['regionale', 'statut_regle']).size().unstack(fill_value=0)
                    df_reg.columns = ['En cours', 'Réglées'] if len(df_reg.columns) == 2 else [df_reg.columns[0]]
                    st.bar_chart(df_reg)

                with col_v2:
                    st.write("**Statut par Agence (Top 10)**")
                    df_age = df.groupby(['agence', 'statut_regle']).size().unstack(fill_value=0)
                    df_age.columns = ['En cours', 'Réglées'] if len(df_age.columns) == 2 else [df_age.columns[0]]
                    # On trie par le total pour voir les agences les plus "critiques"
                    df_age['Total'] = df_age.sum(axis=1)
                    st.bar_chart(df_age.sort_values('Total', ascending=False).head(10)[['En cours', 'Réglées']])
                
                # --- AFFICHAGE GRAPHIQUES ---
                st.subheader("🏆 Analyse des Risques")
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Top Agences (Montant Erreurs)**")
                    top_age = df.groupby('agence')['montant_erreur'].sum().sort_values(ascending=False).head(5)
                    st.bar_chart(top_age)
                with c2:
                    st.write("**Répartition par Criticité**")
                    fig = px.pie(df, names='criticite', hole=0.4)
                    st.plotly_chart(fig, use_container_width=True)

                # --- 🟢 SECTION INSERTION : VALIDATION POUR LES DIRECTEURS 🟢 ---
                roles_decideurs = ["Directeur agence", "Responsable Régional/Central"]
                
                if role_user in roles_decideurs:
                    st.divider()
                    st.subheader("✅ Validation des règlements")
                        
                    df_a_regler = df[df['statut_regle'] == False].copy()
                        
                    if not df_a_regler.empty:
                            # On crée un formulaire pour la validation
                        with st.form("form_validation"):
                            st.info("Sélectionnez l'anomalie à clôturer et saisissez l'action corrective.")
                                
                            col_sel, col_com = st.columns([1, 2])
                                
                            with col_sel:
                                    # On choisit UNE anomalie à la fois pour être précis sur le commentaire
                                id_to_close = st.selectbox("Anomalie à régler :", 
                                                            options=df_a_regler['id_anomalie'].tolist())
                                
                            with col_com:
                                comm_direction = st.text_input("Commentaire de résolution / Action menée :")
                                
                            submit_val = st.form_submit_button("Valider la clôture", type="primary")

                            if submit_val:
                                if comm_direction:
                                    try:
                                        cur = conn.cursor()
                                        cur.execute("""
                                            UPDATE anomalies 
                                            SET statut_regle = True, 
                                                date_reglement = NOW(),
                                                commentaire_resolution = %s 
                                                WHERE id_anomalie = %s
                                            """, (comm_direction, id_to_close))
                                            
                                            # Audit
                                        cur.execute("""
                                            INSERT INTO audit_actions (id_administrateur, action_type, details)
                                            VALUES (%s, %s, %s)
                                            """, (st.session_state.user_id, 'CLOTURE_ANOMALIE', f"Anomalie #{id_to_close} réglée : {comm_direction}"))
                                            
                                        conn.commit()
                                        st.success(f"✅ L'anomalie #{id_to_close} a été clôturée avec succès !")
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        conn.rollback()
                                        st.error(f"Erreur : {e}")
                                else:
                                        st.warning("⚠️ Veuillez saisir un commentaire de résolution avant de valider.")
                            else:
                                st.success("🎉 Toutes les anomalies de votre périmètre sont réglées.")

                # --- FIN DE LA SECTION VALIDATION ---
                

                #st.divider()
                #st.write("**Détail complet des anomalies :**")
                #st.dataframe(df, use_container_width=True, hide_index=True)
                
                # --- FIN DE LA SECTION VALIDATION ---

                # --- 🔍 Rubrique : Consultation détaillée ---
                st.divider()
                st.subheader("🔎 Consultation détaillée & Fiche Anomalie")

                # Création du label de recherche
                df['search_label'] = df['id_anomalie'].astype(str) + " | " + df['agence'] + " | " + df['type']
                
                selection = st.selectbox(
                    "Choisir une anomalie pour afficher les détails complets :", 
                    options=["-- Sélectionner un ID --"] + df['search_label'].tolist()
                )

                if selection != "-- Sélectionner un ID --":
                    id_selectionne = int(selection.split(" | ")[0])
                    detail = df[df['id_anomalie'] == id_selectionne].iloc[0]
                    
                    # --- AFFICHAGE DE LA FICHE ---
                    with st.container(border=True):
                        st.markdown(f"### 📄 FICHE DÉTAILLÉE : Anomalie #{id_selectionne}")
                        
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.write(f"**📅 Date :** {detail['date_constat'].strftime('%d/%m/%Y')}")
                            st.write(f"**🏢 Régionale :** {detail['regionale']}")
                            st.write(f"**📍 Agence :** {detail['agence']}")
                        with c2:
                            st.write(f"**🛠️ Type :** {detail['type']}")
                            st.write(f"**👤 Déclarant :** {detail['agent']}")
                            st.write(f"**⚠️ Criticité :** {detail['criticite']}")
                        with c3:
                            st.write(f"**💰 Montant :** {detail['montant_erreur']} DZD")
                            statut = "🟢 Réglée" if detail['statut_regle'] else "🔴 En cours"
                            st.write(f"**📊 État actuel :** {statut}")

                        st.divider()
                        
                        # --- AFFICHAGE DE LA DESCRIPTION ---
                        st.markdown("**📝 Description détaillée des faits :**")
                        # On utilise st.caption ou un st.info pour faire ressortir le texte
                        desc_text = detail['description'] if detail['description'] else "Aucun commentaire renseigné."
                        st.info(desc_text)
                        
            
    
                        st.divider()
                        
                        col_desc, col_res = st.columns(2)
                        with col_desc:
                            st.markdown("**📝 Description (Agent) :**")
                            st.info(detail['description'] if detail['description'] else "Pas de description.")
                        
                        with col_res:
                            st.markdown("**🛠️ Résolution (Direction) :**")
                            if detail['statut_regle']:
                                st.success(detail['commentaire_resolution'] if detail['commentaire_resolution'] else "Régularisée sans commentaire.")
                            else:
                                st.warning("En attente de régularisation...")

                # --- TABLEAU GLOBAL (caché par défaut pour gagner de la place) ---
                with st.expander("📊 Voir le tableau récapitulatif complet"):
                    # On retire 'search_label' et 'description' pour que le tableau reste lisible
                    st.dataframe(
                        df.drop(columns=['search_label', 'description']), 
                        use_container_width=True, 
                        hide_index=True
                    )
                
            conn.close()
                
            #conn.close()
                
    # --- DECLARATION DES ANOMALIES ---
    elif page == "Déclarer une Anomalie":
        st.title("🚩 Saisie d'Incident")
        conn = get_connection()
        if conn:
            try:
                df_types = pd.read_sql("SELECT id_type, nom_type FROM types_anomalies", conn)
                df_crit = pd.read_sql("SELECT id_crit, libelle_crit FROM ref_criticite", conn)
                
                with st.form("form_anomalie"):
                    t_nom = st.selectbox("Type", options=df_types['nom_type'].tolist())
                    m = st.number_input("Montant (DA)", min_value=0.0)
                    d = st.date_input("Date constat")
                    crit = st.selectbox("Criticité", options=df_crit['libelle_crit'].tolist())
                    obs = st.text_area("Description")
                    
                    if st.form_submit_button("Enregistrer"):
                        id_t = int(df_types[df_types['nom_type'] == t_nom]['id_type'].iloc[0])
                        id_c = int(df_crit[df_crit['libelle_crit'] == crit]['id_crit'].iloc[0])
                        
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO anomalies (date_constat, id_type, montant_erreur, id_utilisateur, code_agence, description, id_crit, statut_regle)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, False)
                        """, (d, id_t, m, st.session_state.user_id, st.session_state.code_agence, obs, id_c))
                        conn.commit()
                        st.success("✅ Enregistré !")
            finally:
                conn.close()

    #---PARAMETRAGE GLOBAL---
    elif page == "Paramétrage Global" and is_admin:
        st.title("⚙️ Paramétrage Global du Système")
        
        # Création d'onglets pour ne pas encombrer l'écran
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "👥 Utilisateurs", 
            "🏢 Structure", 
            "🛡️ Risques", 
            "📋 Processus", 
            "🔐 Rôles",
            "📜 Historique des actions"# <-- Nouvel onglet
        ])

        conn = get_connection()
        if conn:
            # --- ONGLET 1 : CRÉATION UTILISATEUR ---
            # --- ONGLET 1 : CRÉATION UTILISATEUR ---
            with tab1:
                st.subheader("Ajouter un nouvel agent")
                
                # Récupération des données
                df_roles = pd.read_sql("SELECT id_role, nom_role FROM roles", conn)
                df_agences = pd.read_sql("SELECT code_agence, nom_agence FROM agences ORDER BY code_agence", conn)
                
                # 1. CRÉATION DU LIBELLÉ COMBINÉ (Code - Nom)
                df_agences['display_agence'] = df_agences['code_agence'].astype(str) + " - " + df_agences['nom_agence']
                
                with st.form("form_new_user"):
                    col1, col2 = st.columns(2)
                    nom = col1.text_input("Nom")
                    prenom = col2.text_input("Prénom")
                    email = col1.text_input("Email / Login")
                    pwd = col2.text_input("Mot de passe par défaut", value="12345")
                    
                    role_sel = col1.selectbox("Rôle", options=df_roles['nom_role'].tolist())
                    
                    # 2. UTILISATION DU LIBELLÉ COMBINÉ DANS LE SELECTBOX
                    age_sel_display = col2.selectbox("Agence", options=df_agences['display_agence'].tolist())
                    
                    if st.form_submit_button("Créer l'utilisateur"):
                        if nom and prenom and email:
                            conn = get_connection()
                            if conn:
                                try:
                                    # 3. EXTRACTION DU CODE AGENCE (On prend tout ce qui est avant le " - ")
                                    age_code_final = age_sel_display.split(" - ")[0]
                                    
                                    id_r = int(df_roles[df_roles['nom_role'] == role_sel]['id_role'].iloc[0])
                                    cur = conn.cursor()
                                    
                                    # Insertion avec le code agence extrait
                                    cur.execute("""
                                        INSERT INTO utilisateurs (nom, prenom, email, password, id_role, code_agence, actif)
                                        VALUES (%s, %s, %s, %s, %s, %s, True)
                                        RETURNING id_utilisateur
                                    """, (nom.upper(), prenom, email, pwd, id_r, age_code_final))
                                    
                                    new_user_id = cur.fetchone()[0]
                                    
                                    # Audit de la création
                                    cur.execute("""
                                        INSERT INTO audit_actions (id_administrateur, action_type, cible_utilisateur_id, details)
                                        VALUES (%s, %s, %s, %s)
                                    """, (st.session_state.user_id, 'CREATION_USER', new_user_id, 
                                        f"Création du compte pour {prenom} {nom.upper()}"))
                                    
                                    conn.commit()
                                    st.success(f"✅ Utilisateur {prenom} créé et audité !")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    conn.rollback()
                                    st.error(f"Erreur : {e}")
                                finally:
                                    cur.close()
                                    conn.close()
                        else:
                            st.warning("Veuillez remplir les champs obligatoires (Nom, Prénom, Email).")

            # --- ONGLET 2 : STRUCTURE ---
            with tab2:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.write("**Nouvelle Régionale**")
                    with st.form("form_reg"):
                        n_reg = st.text_input("Nom de la Régionale")
                        if st.form_submit_button("Ajouter Régionale"):
                            cur = conn.cursor()
                            cur.execute("INSERT INTO regionales (nom_region) VALUES (%s)", (n_reg,))
                            conn.commit()
                            st.rerun()
                with col_b:
                    st.write("**Nouvelle Agence**")
                    df_reg = pd.read_sql("SELECT id_region, nom_region FROM regionales", conn)
                    with st.form("form_age"):
                        c_age = st.text_input("Code Agence")
                        n_age = st.text_input("Nom Agence")
                        r_age = st.selectbox("Régionale", options=df_reg['nom_region'].tolist())
                        if st.form_submit_button("Ajouter Agence"):
                            id_reg = int(df_reg[df_reg['nom_region'] == r_age]['id_region'].iloc[0])
                            cur = conn.cursor()
                            cur.execute("INSERT INTO agences (code_agence, nom_agence, id_region) VALUES (%s, %s, %s)", 
                                       (c_age, n_age, id_reg))
                            conn.commit()
                            st.rerun()

            # --- ONGLET 3 : RISQUES (Criticité / Impact) ---
            with tab3:
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Ajouter une Criticité**")
                    with st.form("form_crit"):
                        crit_val = st.text_input("Libellé (ex: Élevé)")
                        if st.form_submit_button("Ajouter"):
                            cur = conn.cursor()
                            cur.execute("INSERT INTO ref_criticite (libelle_crit) VALUES (%s)", (crit_val,))
                            conn.commit()
                            st.rerun()
                with c2:
                    st.write("**Ajouter un Impact**")
                    with st.form("form_imp"):
                        imp_val = st.text_input("Libellé (ex: Financier)")
                        if st.form_submit_button("Ajouter"):
                            cur = conn.cursor()
                            cur.execute("INSERT INTO ref_impact (libelle_impact) VALUES (%s)", (imp_val,))
                            conn.commit()
                            st.rerun()

            # --- ONGLET 4 : PROCESSUS (Types d'anomalies) ---
            with tab4:
                st.write("**Ajouter un type d'anomalie / Processus**")
                with st.form("form_type"):
                    n_type = st.text_input("Nom du processus")
                    if st.form_submit_button("Ajouter le type"):
                        cur = conn.cursor()
                        cur.execute("INSERT INTO types_anomalies (nom_type) VALUES (%s)", (n_type,))
                        conn.commit()
                        st.rerun()
                        
            # --- ONGLET 5 : GESTION DES RÔLES ---
        with tab5:
            st.subheader("Gestion des Rôles")
            
            col_list, col_add = st.columns([2, 1])
            
            with col_list:
                st.write("**Rôles existants**")
                try:
                    df_roles_list = pd.read_sql("SELECT id_role, nom_role FROM roles ORDER BY id_role", conn)
                    st.dataframe(df_roles_list, use_container_width=True, hide_index=True)
                except Exception as e:
                    st.error(f"Erreur de lecture : {e}")

            with col_add:
                st.write("**Ajouter un Rôle**")
                with st.form("form_new_role", clear_on_submit=True):
                    n_role = st.text_input("Nom du rôle (ex: Auditeur)")
                    if st.form_submit_button("Enregistrer le rôle"):
                        if n_role:
                            try:
                                cur = conn.cursor()
                                cur.execute("INSERT INTO roles (nom_role) VALUES (%s)", (n_role,))
                                conn.commit()
                                st.success(f"Rôle '{n_role}' ajouté !")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur : {e}")
                            finally:
                                cur.close()
                        else:
                            st.warning("Veuillez saisir un nom.")
        with tab6:
            st.subheader("📜 Historique des actions de sécurité")
            df_audit = pd.read_sql("""
                SELECT a.date_action, u.nom as admin_nom, a.action_type, a.details
                FROM audit_actions a
                JOIN utilisateurs u ON a.id_administrateur = u.id_utilisateur
                ORDER BY a.date_action DESC
            """, conn)
            st.dataframe(df_audit, use_container_width=True)
                        
            conn.close()

    
    # --- GESTION DES UTILISATEURS---
    elif page == "Gestion Utilisateurs" and is_admin:
        st.title("👥 Gestion des comptes & Audit")
        conn = get_connection()
        if conn:
            try:
                query_list = """
                    SELECT u.id_utilisateur, u.actif AS "Accès", u.nom AS "Nom", u.prenom AS "Prénom", 
                           u.email AS "Login", r.nom_role AS "Rôle", u.code_agence AS "Agence"
                    FROM utilisateurs u 
                    JOIN roles r ON u.id_role = r.id_role
                    ORDER BY u.nom ASC
                """
                df_u = pd.read_sql(query_list, conn)
                
                # On garde une copie de l'état initial pour comparer
                st.write("### Liste des utilisateurs")
                edited_df = st.data_editor(
                    df_u, 
                    use_container_width=True, 
                    hide_index=True, 
                    column_config={"Accès": st.column_config.CheckboxColumn(), "id_utilisateur": None}
                )
                
                if st.button("Sauvegarder les modifications"):
                    cur = conn.cursor()
                    try:
                        changes_made = 0
                        for index, row in edited_df.iterrows():
                            # On récupère l'ancienne valeur pour cet utilisateur
                            old_status = df_u.loc[df_u['id_utilisateur'] == row['id_utilisateur'], 'Accès'].values[0]
                            new_status = bool(row["Accès"])
                            
                            if old_status != new_status:
                                # 1. Mise à jour de l'utilisateur
                                cur.execute("UPDATE utilisateurs SET actif = %s WHERE id_utilisateur = %s", 
                                           (new_status, int(row["id_utilisateur"])))
                                
                                # 2. Enregistrement dans la piste d'audit
                                action = "ACTIVATION" if new_status else "DESACTIVATION"
                                detail_log = f"Statut changé de {old_status} à {new_status} pour {row['Nom']} {row['Prénom']}"
                                
                                cur.execute("""
                                    INSERT INTO audit_actions (id_administrateur, action_type, cible_utilisateur_id, details)
                                    VALUES (%s, %s, %s, %s)
                                """, (st.session_state.user_id, action, int(row["id_utilisateur"]), detail_log))
                                
                                changes_made += 1
                        
                        if changes_made > 0:
                            conn.commit()
                            st.success(f"✅ {changes_made} modification(s) enregistrée(s) avec audit !")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.info("Aucune modification détectée.")
                            
                    except Exception as e_save:
                        conn.rollback()
                        st.error(f"Erreur : {e_save}")
                    finally:
                        cur.close()
            finally:
                conn.close()