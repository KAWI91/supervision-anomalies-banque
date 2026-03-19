import streamlit as st
import pandas as pd
import psycopg2
import time
import plotly.express as px



if 'enrg_ok' not in st.session_state:
    st.session_state['enrg_ok'] = False

st.markdown(
    """
    <style>
    /* 1. On s'assure que le fond reste bien sombre */
    .stApp {
        background-color: #0E1117;
    }

    /* 2. Style des cartes de métriques (Metrics) en mode sombre */
    [data-testid="stMetric"] {
        background-color: #1A1C24;
        border: 1px solid #30363D;
        padding: 15px;
        border-radius: 10px;
    }
    
    /* 3. Couleur des titres pour qu'ils "claquent" */
    h1, h2, h3 {
        color: #00E676 !important; /* Vert émeraude pour le côté tech/banque */
    }

    /* 4. Amélioration de la lisibilité des tableaux */
    .stDataFrame {
        border: 1px solid #30363D;
        border-radius: 10px;
    }

    /* 5. Sidebar personnalisée */
    [data-testid="stSidebar"] {
        background-color: #0B0E14 !important;
        border-right: 1px solid #30363D;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# --- CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Base Anomalies", layout="wide")



# --- INITIALISATION DES VARIABLES DE SESSION ---
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None
if 'force_password_change' not in st.session_state:
    st.session_state['force_password_change'] = False
if 'temp_user_data' not in st.session_state:
    st.session_state['temp_user_data'] = None

# --- FONCTION DE CONNEXION ---
@st.cache_resource
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
    
    # CAS A : L'UTILISATEUR DOIT CHANGER SON MOT DE PASSE
    if st.session_state['force_password_change']:
        st.title("🔒 Sécurité : Nouveau mot de passe requis")
        st.info(f"Utilisateur : {st.session_state['temp_user_data']['email']}")
        
        with st.form("form_change_pwd"):
            new_p = st.text_input("Nouveau mot de passe", type="password")
            confirm_p = st.text_input("Confirmer le mot de passe", type="password")
            submit_change = st.form_submit_button("Valider la modification")
            
            if submit_change:
                if new_p == confirm_p and len(new_p) >= 4:
                    conn = get_connection()
                    if conn:
                        try:
                            cur = conn.cursor()
                            cur.execute("""
                                UPDATE utilisateurs 
                                SET password=%s, doit_changer_mdp=False 
                                WHERE id_utilisateur=%s
                            """, (new_p, st.session_state['temp_user_data']['id']))
                            conn.commit()
                            st.success("✅ Mot de passe mis à jour ! Veuillez vous connecter.")
                            # On réinitialise l'état pour revenir au login
                            st.session_state['force_password_change'] = False
                            st.session_state['temp_user_data'] = None
                            time.sleep(2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erreur SQL : {e}")
                else:
                    st.error("❌ Les mots de passe ne correspondent pas ou sont trop courts (min 4).")
        
        if st.button("⬅️ Retour à la connexion"):
            st.session_state['force_password_change'] = False
            st.rerun()

    # CAS B : ÉCRAN DE CONNEXION NORMAL
    else:
        st.title( "☘️ Base anomalies")
        st.title("🔐 Accès Sécurisé")
        
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
                            SELECT u.id_utilisateur, u.nom, u.prenom, r.nom_role, 
                                   u.code_agence, u.matricule, u.fonction, u.actif, u.doit_changer_mdp 
                            FROM utilisateurs u 
                            JOIN roles r ON u.id_role = r.id_role
                            WHERE u.email=%s AND u.password=%s
                        """
                        user_data = pd.read_sql(query, conn, params=[input_email, input_pwd])
                        
                        if not user_data.empty:
                            user = user_data.iloc[0]
                            
                            if not user['actif']:
                                st.error("🚫 Compte désactivé.")
                            
                            elif user['doit_changer_mdp']:
                                # ON BASCULE VERS L'ÉCRAN DE CHANGEMENT
                                st.session_state['force_password_change'] = True
                                st.session_state['temp_user_data'] = {
                                    'id': int(user['id_utilisateur']),
                                    'email': input_email
                                }
                                st.rerun()
                            
                            else:
                                # CONNEXION RÉUSSIE
                                st.session_state.update({
                                    'user_id': int(user['id_utilisateur']),
                                    'user_nom': f"{user['prenom']} {user['nom']}",
                                    'user_role': user['nom_role'],
                                    'code_agence': user['code_agence'],
                                    'matricule': user['matricule'],
                                    'fonction': user['fonction']
                                })
                                
                                st.success(f"✅ Bienvenue {user['prenom']} !")
                                time.sleep(0.5)
                                st.rerun()
                        else:
                            st.error("❌ Identifiants incorrects.")
                    except Exception as e:
                        st.error(f"⚠️ Erreur lors de l'authentification : {e}")
            else:
                st.warning("Veuillez remplir tous les champs.")


  
# --- INTERFACE APPLICATION (CONNECTÉ) ---
else:
   
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
                    a.matricule_auteur, 
                    a.montant_erreur, rc.libelle_crit as criticite, 
                    a.statut_regle,
                    a.description,
                    a.commentaire_resolution,
                    a.num_compte,      
                    a.ref_operation,  
                    a.ref_risque     
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
                    fig.update_layout(
                    template="plotly_dark",           # Force le thème sombre de Plotly
                    paper_bgcolor='rgba(0,0,0,0)',    # Fond transparent
                    plot_bgcolor='rgba(0,0,0,0)',     # Fond du tracé transparent
                    font_color='#FFFFFF',             # Texte en blanc
                    margin=dict(t=20, b=20, l=20, r=20) # Réduit les marges pour gagner de la place
    )                                                      
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
                df['search_label'] = (
                    df['id_anomalie'].astype(str) + " | " + 
                    df['num_compte'].fillna("N/A") + " | " +
                    df['agence'] + " | " + 
                    df['type']
                )
                
                if 'num_compte' in df.columns:
                    df['search_label'] = (
                    df['id_anomalie'].astype(str) + " | Compte: " + 
                    df['num_compte'].fillna("N/A").astype(str) + " | " + 
                    df['agence'] + " | " + df['type']
                )
                else:
                # Fallback si la colonne n'est toujours pas chargée
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
                        
                        c1, c2, c3, c4 = st.columns(4)
                        with c1:
                            st.write(f"**📅 Date :** {detail['date_constat'].strftime('%d/%m/%Y')}")
                            st.write(f"**🏢 Régionale :** {detail['regionale']}")
                            st.write(f"**📍 Agence :** {detail['agence']}")
                        with c2:
                            st.write(f"**🛠️ Type :** {detail['type']}")
                            st.write(f"**👤 Déclarant :** {detail['agent']}")
                            st.write(f"**⚠️ Criticité :** {detail['criticite']}")
                        
                        with c3:   
                            st.write(f"**💳 N° Compte :** `{detail['num_compte'] if detail['num_compte'] else 'N/A'}`")
                            st.write(f"**🔢 Réf. Opé :** `{detail['ref_operation'] if detail['ref_operation'] else 'N/A'}`")
                            st.write(f"**🛡️ Réf. Risque :** `{detail['ref_risque'] if detail['ref_risque'] else 'N/A'}`")
                        
                        with c4:
                            montant_formate = f"{detail['montant_erreur']:,.2f}".replace(",", " ")
                            st.write(f"**💰 Montant :** {montant_formate} DZD")
                            
                            #st.write(f"**💰 Montant :** {detail['montant_erreur']} DZD")
                            statut = "🟢 Réglée" if detail['statut_regle'] else "🔴 En cours"
                            st.write(f"**📊 État actuel :** {statut}")
                            st.write(f"**👤 Matricule de l'auteur :** {detail['matricule_auteur']}")

                        st.divider()
                        
                        # --- AFFICHAGE DE LA DESCRIPTION ---
                        st.markdown("**📝 Description détaillée de l'anomalie par le Contrôle :**")
                        # On utilise st.caption ou un st.info pour faire ressortir le texte
                        desc_text = detail['description'] if detail['description'] else "Aucun commentaire renseigné."
                        st.info(desc_text)
                        
            
    
                        st.divider()
                                                                   
    
                        st.markdown("**🛠️ Résolution - Commentaire de la Direction :**")
                            # Vérifie si la colonne commentaire_resolution existe bien dans ton DF
                        if detail['statut_regle']:
                            msg = detail['commentaire_resolution'] if 'commentaire_resolution' in detail and detail['commentaire_resolution'] else "Régularisée sans commentaire."
                            st.success(msg)
                        else:
                            st.warning("En attente de régularisation...")

                # --- TABLEAU GLOBAL (caché par défaut pour gagner de la place) ---
                with st.expander("📊 Voir le tableau récapitulatif complet"):
                # On retire les colonnes techniques pour le tableau
                    cols_to_drop = ['search_label', 'description']
                    st.dataframe(
                        df.drop(columns=[c for c in cols_to_drop if c in df.columns]), 
                        use_container_width=True, 
                        hide_index=True
                    )
                
            #conn.close()
                
            #conn.close()
            
    # --- DECLARATION DES ANOMALIES ---
    elif page == "Déclarer une Anomalie":
        st.title("🚩 Saisie d'Incident")
        conn = get_connection()
        if conn:
            try:
                df_types = pd.read_sql("SELECT id_type, nom_type FROM types_anomalies", conn)
                df_crit = pd.read_sql("SELECT id_crit, libelle_crit FROM ref_criticite", conn)
                # ✅ AJOUT DE clear_on_submit=True
                with st.form("form_anomalie", clear_on_submit=True):
                    t_nom = st.selectbox("Type d'anomalie", options=df_types['nom_type'].tolist()) 
                    col_ref1, col_ref2= st.columns(2)
                    with col_ref1:                        
                        n_compte = st.text_input("N° de Compte (Facultatif)", max_chars=20)
                        r_risque = st.text_input("Référence Risque (Facultatif)", max_chars=10)
                        
                    
                    with col_ref2:
                        r_op = st.text_input("Réf. Opération / Dossier (Facultatif)", max_chars=15)
                        matricule_auteur = st.text_input("Matricule de l'auteur de l'anomalie", max_chars=7)
                                        
                    # m = st.number_input("Montant de l'incidence (DA)", 
                    #                     min_value=0.0,
                    #                     value=None,
                    #                     placeholder="Ex: 12 000,00", 
                    #                     format="%.2f", # Force l'affichage de deux décimales
                    #                     step=100.0, 
                    #                     help="Laissez à 0 si l'anomalie est purement administrative.")
                    
                    m= st.number_input("Montant de l'erreur (DZD)", min_value=0.0, value=None, placeholder="0.00")

                    # Si un montant est saisi, on l'affiche en gros et formaté juste en dessous
                    if m:
                        format_visuel = f"{m:,.2f}".replace(",", " ")
                        st.caption(f"💰 Montant saisi : **{format_visuel} DZD**")
                                        
                    d = st.date_input("Date du constat")
                    crit = st.selectbox("Criticité", options=df_crit['libelle_crit'].tolist())
                    obs = st.text_area("Description détaillée de l'anomalie")
                    
                    submit = st.form_submit_button("Enregistrer l'incident", type="primary")

                    if submit:
                        if not obs.strip():
                            st.error("⚠️ Veuillez fournir une description, surtout si le montant est nul.")
                        else:
                            id_t = int(df_types[df_types['nom_type'] == t_nom]['id_type'].iloc[0])
                            id_c = int(df_crit[df_crit['libelle_crit'] == crit]['id_crit'].iloc[0])
                            
                            # Nettoyage des valeurs facultatives (évite d'envoyer des chaînes vides à la DB)
                            n_compte = n_compte.strip() if n_compte.strip() else None
                            r_op = r_op.strip() if r_op.strip() else None
                            r_risque = r_risque.strip() if r_risque.strip() else None

                            cur = conn.cursor()
                            # --- MISE À JOUR DE LA REQUÊTE SQL (INSERT) ---
                            cur.execute("""
                                INSERT INTO anomalies 
                                (date_constat, id_type, montant_erreur, id_utilisateur, code_agence, description, id_crit, statut_regle, 
                                num_compte, ref_operation, ref_risque, matricule_auteur)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, False, %s, %s, %s, %s)
                            """, (d, id_t, m, st.session_state.user_id, st.session_state.code_agence, obs, id_c, 
                                n_compte, r_op, r_risque, matricule_auteur))
                            # ----------------------------------------------
                            conn.commit()

                            # --- ON ACTIVE LA MÉMOIRE DE SUCCÈS ---
                            st.session_state.enrg_ok = True
                            st.rerun() # On relance pour afficher le message hors du formulaire
                
                
                    if st.session_state.enrg_ok:
                        st.success("✅ Anomalie enregistrée avec succès !")
                        time.sleep(1)
                        st.rerun()
        
                # Le bouton qui va vider le formulaire
                #if st.button("➕ Faire un nouvel enregistrement", type="primary"):
                    #st.session_state.enrg_ok = False
                    #st.rerun()
                
                                
            except Exception as e:
                st.error(f"Une erreur est survenue : {e}")   
            #finally:
                #conn.close()

# --- 8. PAGE : MON COMPTE ---
    # --- 8. PAGE : MON COMPTE ---
    elif page == "Mon Compte":
        st.title("👤 Mon Profil")
        
        # Récupération sécurisée des données de session
        user_id = st.session_state.get('user_id')
        nom_complet = st.session_state.get('user_nom', 'N/A')
        role = st.session_state.get('user_role', 'N/A')
        agence = st.session_state.get('code_agence', 'N/A')
        mat = st.session_state.get('matricule', 'N/A')
        fct = st.session_state.get('fonction', 'Non renseignée')

        # Affichage des informations
        col_info1, col_info2 = st.columns(2)
        with col_info1:
            st.write(f"**Nom :** {nom_complet}")
            st.write(f"**Rôle :** {role}")
            st.write(f"**Code Agence :** {agence}")
        with col_info2:
            st.write(f"**Matricule :** {mat}")
            st.write(f"**Fonction :** {fct}")

        st.divider()

        # --- SECTION CHANGEMENT DE MOT DE PASSE ---
        st.subheader("🔐 Changer mon mot de passe")
        
        with st.form("form_update_pwd", clear_on_submit=True):
            new_p = st.text_input("Nouveau mot de passe", type="password")
            confirm_p = st.text_input("Confirmer le nouveau mot de passe", type="password")
            submit_pw = st.form_submit_button("Mettre à jour mon mot de passe")

            if submit_pw:
                if not new_p or not confirm_p:
                    st.warning("⚠️ Veuillez remplir les deux champs.")
                elif new_p != confirm_p:
                    st.error("❌ Les mots de passe ne correspondent pas.")
                elif len(new_p) < 4:
                    st.error("❌ Le mot de passe doit contenir au moins 4 caractères.")
                else:
                    conn = get_connection()
                    if conn:
                        try:
                            cur = conn.cursor()
                            # Mise à jour en base de données
                            cur.execute("""
                                UPDATE utilisateurs 
                                SET password = %s, doit_changer_mdp = False 
                                WHERE id_utilisateur = %s
                            """, (new_p, user_id))
                            
                            # Ajout à l'audit pour la traçabilité
                            cur.execute("""
                                INSERT INTO audit_actions (id_administrateur, action_type, details)
                                VALUES (%s, %s, %s)
                            """, (user_id, 'MODIF_MDP_PERSO', f"L'utilisateur {mat} a changé son propre mot de passe."))
                            
                            conn.commit()
                            st.success("✅ Votre mot de passe a été modifié avec succès !")
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erreur lors de la mise à jour : {e}")
                        finally:
                            cur.close()
        

    #---PARAMETRAGE GLOBAL---
    elif page == "Paramétrage Global" and is_admin:
        st.title("⚙️ Paramétrage Global du Système")
        
        # Création d'onglets pour ne pas encombrer l'écran
        tab1, tab2, tab3, tab4, tab6 = st.tabs([
            "👥 Utilisateurs", 
            "🏢 Structure", 
            "🛡️ Risques", 
            "📋 Processus",           
            "📜 Historique des MAJ utilisateurs"# <-- Nouvel onglet
        ])

        conn = get_connection()
        if conn:
            # --- ONGLET 1 : CRÉATION UTILISATEUR ---
            # --- ONGLET 1 : CRÉATION UTILISATEUR ---
            # --- ONGLET 1 : CRÉATION UTILISATEUR ---
            with tab1:
                st.subheader("Ajouter un nouvel agent")
                #Récupération des données pour les menus déroulants
                # Récupération des données (Roles et Agences)
                df_roles = pd.read_sql("SELECT id_role, nom_role FROM roles", conn)
                df_agences = pd.read_sql("SELECT code_agence, nom_agence FROM agences ORDER BY code_agence", conn)
                df_agences['display_agence'] = df_agences['code_agence'].astype(str) + " - " + df_agences['nom_agence']
                
                with st.form("form_new_user", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    
                    # --- LIGNE 1 : INFOS PERSONNELLES ---
                    nom = col1.text_input("Nom")
                    prenom = col2.text_input("Prénom")
                    
                    # --- LIGNE 2 : IDENTIFIANT ET FONCTION ---
                    # 1. MATRICULE AVEC LIMITE PHYSIQUE
                    matricule = col1.text_input(
                        "Matricule (5 caractères)", 
                        max_chars=5, 
                        help="Le matricule doit comporter exactement 5 caractères."
                    ).strip().upper()
                    fonction = col2.text_input("Fonction / Poste", placeholder="Ex: Agent de sécurité, Superviseur...").strip()
                    
                     # --- LIGNE 3 : CONNEXION --
                    email = col2.text_input("Email / Login").lower().strip()
                    pwd = col1.text_input("Mot de passe par défaut", value="12345")
                    
                    # --- LIGNE 4 : DROITS ET AFFECTATION ---
                    role_sel = col1.selectbox("Rôle", options=df_roles['nom_role'].tolist())
                    age_sel_display = col2.selectbox("Agence d'affectation", options=df_agences['display_agence'].tolist())
                   
                                         
                    # Petit indicateur visuel sous le champ matricule (optionnel mais sympa)
                    if matricule and len(matricule) < 5:
                        st.caption(f"⚠️ Longueur actuelle : {len(matricule)}/5 (Trop court)")
                    elif len(matricule) == 5:
                        st.caption("✅ Longueur correcte")

                    # 2. BOUTON DE SOUMISSION
                    if st.form_submit_button("Créer l'utilisateur"):
                        # VERIFICATIONS AVANT INSERTION
                        if not (nom and prenom and email and matricule):
                            st.error("❌ Veuillez remplir tous les champs obligatoires.")
                        elif len(matricule) != 5:
                            st.error("❌ Le matricule doit faire exactement 5 caractères.")
                        else:
                            conn = get_connection()
                            if conn:
                                try:
                                    age_code_final = age_sel_display.split(" - ")[0]
                                    id_r = int(df_roles[df_roles['nom_role'] == role_sel]['id_role'].iloc[0])
                                    
                                    cur = conn.cursor()
                                    
                                    # INSERTION (7 %s pour 7 variables, les 2 derniers sont True en dur)
                                    cur.execute("""
                                        INSERT INTO utilisateurs (
                                            nom, prenom, matricule, fonction, email, password, 
                                            id_role, code_agence, actif, doit_changer_mdp
                                        )
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, True, True)
                                        RETURNING id_utilisateur
                                    """, (nom.upper(), prenom, matricule, fonction,  email, pwd, id_r, age_code_final))
                                    
                                    new_user_id = cur.fetchone()[0]
                                    
                                    # AUDIT
                                    cur.execute("""
                                        INSERT INTO audit_actions (id_administrateur, action_type, cible_utilisateur_id, details)
                                        VALUES (%s, %s, %s, %s)
                                    """, (st.session_state.user_id, 'CREATION_USER', new_user_id, 
                                        f"Création agent {prenom} {nom.upper()} - Matricule: {matricule} ({fonction}) | Agence: {age_code_final}"))
                                    
                                    conn.commit()
                                    st.success(f"✅ Utilisateur {matricule} créé avec succès !")
                                    time.sleep(1)
                                    st.rerun()
                                    
                                except Exception as e:
                                    conn.rollback()
                                    if "unique_matricule" in str(e) or "duplicate key" in str(e).lower():
                                        st.error("❌ Ce matricule ou cet email existe déjà.")
                                    else:
                                        st.error(f"Erreur base de données : {e}")
                                finally:
                                    cur.close()
                        

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
                        
          
        with tab6:
            st.subheader("📜 Historique des actions de sécurité")
            df_audit = pd.read_sql("""
                SELECT a.date_action, u.nom as admin_nom, a.action_type, a.details
                FROM audit_actions a
                JOIN utilisateurs u ON a.id_administrateur = u.id_utilisateur
                ORDER BY a.date_action DESC
            """, conn)
            st.dataframe(df_audit, use_container_width=True)
                        
            #conn.close()

    
    # --- GESTION DES UTILISATEURS---
    # --- GESTION DES UTILISATEURS ---
    elif page == "Gestion Utilisateurs" and is_admin:
        st.title("👥 Gestion des comptes & Audit")
        conn = get_connection()
        if conn:
            try:
                # 1. Chargement et Filtrage (votre code actuel)
                query_list = "SELECT u.id_utilisateur, u.actif AS \"Accès\", u.nom AS \"Nom\", u.prenom AS \"Prénom\", u.email AS \"Login\", r.nom_role AS \"Rôle\", u.code_agence AS \"Agence\" FROM utilisateurs u JOIN roles r ON u.id_role = r.id_role ORDER BY u.nom ASC"
                df_u = pd.read_sql(query_list, conn)

                search_term = st.text_input("🔍 Rechercher un utilisateur", "").strip().lower()
                if search_term:
                    mask = (df_u['Nom'].str.lower().str.contains(search_term, na=False) | 
                            df_u['Prénom'].str.lower().str.contains(search_term, na=False) |
                            df_u['Agence'].astype(str).str.lower().str.contains(search_term, na=False))
                    df_u_filtered = df_u[mask]
                else:
                    df_u_filtered = df_u

                # 2. Affichage du tableau
                edited_df = st.data_editor(
                    df_u_filtered, 
                    use_container_width=True, 
                    hide_index=True, 
                    column_config={"Accès": st.column_config.CheckboxColumn(), "id_utilisateur": None}
                )

                col_save, col_reset = st.columns([1, 1])

                with col_save:
                    if st.button("💾 Sauvegarder les accès", use_container_width=True):
                        # ... (votre logique de sauvegarde actuelle) ...
                        st.success("Modifications enregistrées")
                        time.sleep(1)
                        st.rerun()

                # --- NOUVELLE SECTION : RÉINITIALISATION MOT DE PASSE ---
                st.divider()
                st.subheader("🔑 Réinitialisation de sécurité")
                
                with st.expander("Ouvrir le panneau de réinitialisation"):
                    # On propose uniquement les utilisateurs visibles dans le tableau filtré
                    user_list = df_u_filtered['Nom'] + " " + df_u_filtered['Prénom'] + " (" + df_u_filtered['Login'] + ")"
                    selected_user_text = st.selectbox("Sélectionner l'agent à réinitialiser :", options=user_list)

                    if st.button("🔄 Réinitialiser le mot de passe à '12345'", type="primary"):
                        # Extraire l'email (Login) entre parenthèses pour identifier l'user
                        target_email = selected_user_text.split("(")[-1].replace(")", "")
                        
                        try:
                            cur = conn.cursor()
                            # 1. Update du password
                            cur.execute("UPDATE utilisateurs SET password = %s, doit_changer_mdp = TRUE WHERE email = %s", ("12345", target_email))
                            
                            # 2. Audit de l'action
                            cur.execute("""
                                INSERT INTO audit_actions (id_administrateur, action_type, details)
                                VALUES (%s, %s, %s)
                            """, (st.session_state.user_id, 'RESET_PWD', f"Mot de passe réinitialisé pour {target_email}"))
                            
                            conn.commit()
                            st.warning(f"⚠️ Le mot de passe de {target_email} a été remis à '12345'.")
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"Erreur lors de la réinitialisation : {e}")
                        finally:
                            cur.close()

            except Exception as e:
                st.error(f"Erreur : {e}")