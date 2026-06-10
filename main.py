from flask import Flask, request, redirect, jsonify, session, make_response
from functools import wraps
import requests
import os
import time
import ssl
import certifi
import json
import math

ssl._create_default_https_context = ssl.create_default_context
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
os.environ['SSL_CERT_FILE'] = certifi.where()

app = Flask(__name__)

# ─── VERSION ────────────────────────────────────────────────────────────────────
VERSION       = "2.24"
from datetime import date as _date
VERSION_DATE  = _date.today().strftime("%d/%m/%Y")
VERSION_LABEL = f"v{VERSION} — {VERSION_DATE}"
# ────────────────────────────────────────────────────────────────────────────────

API_KEY           = os.environ.get("SHOPIFY_API_KEY", "")
API_SECRET        = os.environ.get("SHOPIFY_API_SECRET", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SHOPIFY_TOKEN     = os.environ.get("SHOPIFY_TOKEN", "").strip()
APP_PASSWORD      = os.environ.get("APP_PASSWORD", "")
app.secret_key    = os.environ.get("SECRET_KEY", "changeme-please-set-in-render")
SCOPES            = "read_products,write_products,read_inventory,write_inventory,read_product_listings,write_product_listings"

# ─── AUTH ───────────────────────────────────────────────────────────────────────

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("auth"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD and APP_PASSWORD:
            session["auth"] = True
            return redirect("/")
        error = '<p style="color:#c0392b;margin:8px 0">Mot de passe incorrect.</p>'
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>Connexion – Ma Maison Cocoon™</title>
    <style>
      body{{font-family:Georgia,serif;background:#FDF6F0;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
      .box{{background:white;padding:40px;border-radius:12px;box-shadow:0 4px 20px rgba(0,0,0,0.1);width:320px;text-align:center}}
      h1{{color:#8B4513;font-size:1.2rem;margin-bottom:20px}}
      input{{width:100%;padding:10px;margin:8px 0;border:1px solid #ccc;border-radius:6px;box-sizing:border-box;font-size:1rem}}
      button{{background:#8B4513;color:white;border:none;padding:10px 24px;border-radius:6px;font-size:1rem;cursor:pointer;width:100%;margin-top:8px}}
      button:hover{{background:#6B3410}}
    </style></head><body>
    <div class="box">
      <h1>🕯️ Ma Maison Cocoon™<br><span style="font-weight:normal;font-size:0.9rem">Automation – Accès sécurisé</span></h1>
      {error}
      <form method="POST">
        <input type="password" name="password" placeholder="Mot de passe" autofocus>
        <button type="submit">Connexion</button>
      </form>
    </div></body></html>"""

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ─── TRADUCTIONS ───────────────────────────────────────────────────────────────

COULEURS = {
    "red":"Rouge","blue":"Bleu","green":"Vert","black":"Noir","white":"Blanc",
    "pink":"Rose","purple":"Violet","yellow":"Jaune","orange":"Orange",
    "grey":"Gris","gray":"Gris","brown":"Marron","beige":"Beige",
    "gold":"Doré","silver":"Argenté","navy":"Bleu marine","cream":"Crème",
    "ivory":"Ivoire","teal":"Bleu canard","coral":"Corail","nude":"Nude",
    "khaki":"Kaki","mint":"Menthe","multicolor":"Multicolore","multi":"Multicolore",
    "rose gold":"Or rose","dark green":"Vert foncé","light blue":"Bleu clair",
    "dark blue":"Bleu foncé","light pink":"Rose clair","dark gray":"Gris foncé",
    "light gray":"Gris clair","off white":"Blanc cassé","dark brown":"Marron foncé",
    "chocolate":"Chocolat","leopard":"Léopard"
}

TAILLES = {
    "one size":"Taille unique","free size":"Taille unique","universal size":"Taille unique",
    "x-small":"XS","x small":"XS","extra small":"XS","xs":"XS",
    "small":"S","medium":"M","large":"L",
    "x-large":"XL","x large":"XL","extra large":"XL","xl":"XL",
    "xx-large":"XXL","xx large":"XXL","2xl":"XXL","xxl":"XXL",
    "xxx-large":"XXXL","3xl":"XXXL","xxxl":"XXXL",
    "4xl":"4XL","5xl":"5XL","6xl":"6XL",
    "single":"Taille unique","universal":"Universel"
}

MATIERES = {
    "velvet":"Velours","fleece":"Polaire","cotton":"Coton","linen":"Lin",
    "silk":"Soie","satin":"Satin","bamboo":"Bambou","wool":"Laine",
    "polyester":"Polyester","sherpa":"Sherpa","chenille":"Chenille",
    "plush":"Peluche","acrylic":"Acrylique","microfiber":"Microfibre",
    "microfibre":"Microfibre","cashmere":"Cachemire","leather":"Cuir",
    "suede":"Suède","lace":"Dentelle","mesh":"Filet","knit":"Tricot"
}

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def get_all_products(token, shop):
    products = []
    url = f"https://{shop}/admin/api/2026-04/products.json?limit=250"
    headers = {"X-Shopify-Access-Token": token}
    while url:
        res = requests.get(url, headers=headers)
        data = res.json()
        if "errors" in data:
            raise Exception(f"Shopify API error: {data['errors']}")
        products.extend(data.get("products", []))
        link = res.headers.get("Link", "")
        url = None
        if 'rel="next"' in link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
        if url:
            time.sleep(0.5)
    return products

def traduire_valeur(valeur, dictionnaire):
    """Traduit une valeur — gère les correspondances exactes ET les mots contenus (ex: 'Nordic blue' → 'Nordic Bleu')"""
    if not valeur:
        return valeur
    v = valeur.strip()
    v_lower = v.lower()
    # 1. Correspondance exacte (priorité)
    if v_lower in dictionnaire:
        return dictionnaire[v_lower]
    # 2. Cherche si un mot-clé du dictionnaire est contenu dans la valeur
    # Trie par longueur décroissante pour matcher d'abord les plus longs (ex: "dark blue" avant "blue")
    result = v
    for key in sorted(dictionnaire.keys(), key=len, reverse=True):
        if key in v_lower:
            # Remplace le mot anglais par sa traduction en conservant la casse du reste
            translated = dictionnaire[key]
            # Reconstruction : on remplace le mot trouvé dans la chaîne originale
            import re
            pattern = re.compile(re.escape(key), re.IGNORECASE)
            result = pattern.sub(translated, result)
            break  # Un seul remplacement par valeur
    return result

def detecter_matiere(titre):
    titre_lower = titre.lower()
    for en, fr in sorted(MATIERES.items(), key=lambda x: len(x[0]), reverse=True):
        if en in titre_lower:
            return fr
    return ""

def detecter_couleur_titre(titre):
    titre_lower = titre.lower()
    for en, fr in sorted(COULEURS.items(), key=lambda x: len(x[0]), reverse=True):
        if en in titre_lower:
            return fr
    return ""

# Options à supprimer automatiquement (variants techniques AliExpress)
OPTIONS_A_SUPPRIMER = ["ships from", "ship from", "expédié de", "expedie de"]
VALEURS_A_SUPPRIMER = ["china mainland", "china", "mainland", "aliexpress", "warehouse"]

def filtrer_variants_aliexpress(variants, token, shop, pid):
    """Supprime les variants techniques AliExpress (Ships From, China Mainland, etc.)"""
    options_a_supprimer_ids = []
    for v in variants:
        for opt_key in ["option1", "option2", "option3"]:
            val = (v.get(opt_key) or "").lower().strip()
            if any(s in val for s in VALEURS_A_SUPPRIMER):
                options_a_supprimer_ids.append(v["id"])
                break
    # Supprimer ces variants via l'API
    for vid in options_a_supprimer_ids:
        requests.delete(
            f"https://{shop}/admin/api/2026-04/variants/{vid}.json",
            headers={"X-Shopify-Access-Token": token})
        time.sleep(0.2)
    # Aussi supprimer les options dont le nom est "Ships From" etc.
    res = requests.get(
        f"https://{shop}/admin/api/2026-04/products/{pid}.json",
        headers={"X-Shopify-Access-Token": token})
    prod = res.json().get("product", {})
    options = prod.get("options", [])
    options_nettoyees = []
    for opt in options:
        nom_lower = opt.get("name","").lower()
        if not any(s in nom_lower for s in OPTIONS_A_SUPPRIMER):
            options_nettoyees.append(opt)
    # Retourner les variants filtrés
    return [v for v in variants if v["id"] not in options_a_supprimer_ids]

def optimiser_variants(variants):
    result = []
    dico_couleurs = COULEURS
    dico_tailles  = TAILLES
    for v in variants:
        opt1_orig = v.get("option1", "") or ""
        opt2_orig = v.get("option2", "") or ""
        opt3_orig = v.get("option3", "") or ""
        # Essaie couleurs d'abord, puis tailles
        def traduire_option(val):
            t = traduire_valeur(val, dico_couleurs)
            if t == val:  # pas trouvé dans couleurs
                t = traduire_valeur(val, dico_tailles)
            return t
        opt1 = traduire_option(opt1_orig)
        opt2 = traduire_option(opt2_orig)
        opt3 = traduire_option(opt3_orig)
        result.append({
            "id": v["id"],
            "option1_original": opt1_orig, "option1_traduit": opt1,
            "option2_original": opt2_orig, "option2_traduit": opt2,
            "option3_original": opt3_orig, "option3_traduit": opt3,
            "changed": opt1 != opt1_orig or opt2 != opt2_orig or opt3 != opt3_orig
        })
    return result

def appel_claude(prompt, max_tokens=1000):
    """Appel générique à l'API Claude Haiku"""
    if not ANTHROPIC_API_KEY:
        return None, "Clé ANTHROPIC_API_KEY manquante dans les variables Render"
    try:
        import urllib.request
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"], None
    except Exception as e:
        return None, str(e)

def optimiser_fiche_complete(product):
    """
    Envoie toutes les données brutes du produit à Claude
    et récupère une fiche complète optimisée en JSON.
    """
    titre_orig  = product.get("title", "")
    desc_orig   = product.get("body_html", "") or ""
    tags_orig   = product.get("tags", "")
    variants    = product.get("variants", [])
    images      = product.get("images", [])

    # Préparer les variants pour le prompt
    variants_str = ""
    for v in variants:
        parts = [x for x in [v.get("option1",""), v.get("option2",""), v.get("option3","")] if x]
        if parts:
            variants_str += f"  - {' / '.join(parts)}\n"

    # Nettoyer la description des balises HTML pour le prompt
    import re
    desc_texte = re.sub(r'<[^>]+>', ' ', desc_orig).strip()
    desc_texte = re.sub(r'\s+', ' ', desc_texte)[:500]

    nb_images = len(images)

    prompt = f"""Tu es un rédacteur expert en e-commerce français pour la boutique Ma Maison Cocoon (maison, bien-être, cocooning).

DONNÉES BRUTES DU PRODUIT (peuvent être en anglais, chinois ou charabia AliExpress) :
- Titre original : {titre_orig}
- Description originale : {desc_texte if desc_texte else "Aucune"}
- Variants : 
{variants_str if variants_str else "  Aucun variant"}
- Tags existants : {tags_orig if tags_orig else "Aucun"}
- Nombre d'images : {nb_images}

ÉTAPE 1 — ANALYSE :
Identifie la catégorie réelle du produit et toutes ses caractéristiques techniques visibles dans les données brutes (matière, dimensions, couleurs, usage, etc.). Adapte ton ton à la catégorie (doux/cocooning pour textile, pratique pour ustensile, ludique pour enfant, etc.)

ÉTAPE 2 — RÉDACTION :
Rédige une fiche produit complète en HTML en respectant EXACTEMENT cette structure :

<p>[Accroche émotionnelle 2-3 lignes — OBLIGATOIRE : choisis UNE approche différente parmi ces styles, selon ce qui convient le mieux au produit :
- Scène de vie immersive : "Un dimanche matin, encore à moitié endormie, vous glissez les pieds dans..."
- Question rhétorique : "Et si votre routine du soir devenait un vrai rituel de bien-être ?"
- Constat poétique court : "La douceur, ça se cultive. Même dans les gestes les plus simples."
- Invitation directe : "Bienvenue dans votre nouveau rituel du matin."
- Bénéfice inattendu : "Ce petit accessoire discret change tout — vous ne pourrez plus vous en passer."
- Émotion du quotidien : "Il y a des objets qui transforment les gestes ordinaires en moments de plaisir."
- Contraste : "On pense souvent aux grands voyages pour se ressourcer. Parfois, il suffit de..."
INTERDIT : ne jamais commencer par "Certains soirs", "Après une longue journée", "Ces moments où", "Transformez votre". Chaque fiche doit avoir une accroche unique et originale.]</p>

<p><strong>Points forts :</strong></p>
<ul>
<li>[Bénéfice clé 1]</li>
<li>[Bénéfice clé 2]</li>
<li>[Bénéfice clé 3]</li>
<li>[Bénéfice clé 4]</li>
</ul>

<p><strong>Caractéristiques :</strong></p>
<ul>
<li>Matière : [extraite des données brutes]</li>
<li>Coloris : [extraits des variants/données]</li>
<li>Dimensions/Tailles : [si disponibles dans les données]</li>
<li>Utilisation : [intérieur/extérieur, usage spécifique]</li>
</ul>

<p><strong>Utilisations idéales :</strong></p>
<ul>
<li>[Usage concret 1]</li>
<li>[Usage concret 2]</li>
<li>[Usage concret 3]</li>
<li>[Usage concret 4]</li>
</ul>

<p><strong>Précautions et entretien :</strong></p>
<p>[Conseils d'entretien adaptés à la matière du produit. 1-2 phrases pratiques.]</p>

<p><em>Remarque : En raison des conditions de prise de vue et des variations d'affichage selon les écrans, les couleurs peuvent légèrement différer de la réalité.</em></p>
[UNIQUEMENT si le produit est en tissu, textile, coton, polyester, velours, polaire, sherpa, laine, soie, satin, bambou, microfibre, ou tout matériau souple (coussin, tapis, plaid, vêtement, chaussettes, peignoir, serviette, lange, peluche...) — ajouter ce paragraphe juste après :
<p><em>Les dimensions et tailles indiquées sont données à titre indicatif. De légères variations peuvent exister en raison du processus de fabrication et des méthodes de mesure.</em></p>
Pour les produits rigides (plastique, métal, verre, bois) — ne pas ajouter ce paragraphe.]

RÈGLES ABSOLUES :
- NE PAS mentionner AliExpress, Chine, dropshipping, importé, fournisseur, livraison
- NE PAS utiliser "artisanal" ni "fait main"
- NE PAS inventer de dimensions ou caractéristiques non visibles dans les données brutes
- Si une info n'est pas disponible (ex: dimensions), ne pas mettre ce bullet
- Tout en français impeccable, ton chaleureux et lifestyle
- Titre : 60-80 caractères max, clair, avec mots-clés SEO naturels
- Meta title : 50-60 caractères max
- Meta description : 140-160 caractères max, incitative
- JAMAIS de tirets em (—) dans la description. Utiliser uniquement des balises HTML <ul><li> pour les listes.
- Variants : traduis CHAQUE variant en français (couleurs, tailles, matières)
- Couleur principale : en français si détectable
- Matière principale : en français si détectable

TAGS — Taxonomie stricte (4 à 6 tags maximum, séparés par des virgules) :
Choisis UNIQUEMENT dans ces catégories, sans inventer d'autres tags :
1. Matière (1-2 max) : velours, sherpa, polaire, coton, soie, bambou, peluche, microfibre, laine, satin, lin, chenille
2. Saison/Usage (1-2 max) : hiver, été, toutes saisons, intérieur, maison, bureau
3. Occasion (0-1) : cadeau, noël, anniversaire, naissance — UNIQUEMENT si clairement pertinent
4. Cible (0-1) : femme, homme, enfant, bébé, mixte — UNIQUEMENT si le produit est clairement genré
NE PAS inclure : noms de catégories de navigation (chaussons, plaid, coussin...), adjectifs génériques (doux, confortable, chaud...), ni aucun tag qui ressemble à un nom de collection.

GENDER : Détermine le genre cible du produit :
- "Unisex" : par défaut pour tous les produits neutres (maison, déco, cocooning, cuisine, bien-être)
- "Female" : uniquement si clairement destiné aux femmes (lingerie, vêtements femme, sacs femme, cosmétiques femme)
- "Male" : uniquement si clairement destiné aux hommes (vêtements homme, rasage, accessoires homme)
- "Unisex Kids" : pour les produits enfants (jouets, peluches, vêtements enfants, doudous)
- "Unisex Infant" : pour les produits bébés (langes, turbans bébé, bodys bébé)
En cas de doute, mettre "Unisex".

AGE_GROUP : Détermine la tranche d'âge cible du produit :
- "adult" : par défaut pour tous les produits adultes (meubles, déco, vêtements adultes, bien-être, cuisine, etc.)
- "kids" : uniquement si c'est clairement un produit pour enfants 5-13 ans (jouets, peluches, vêtements enfants, accessoires enfants)
- "infant" : uniquement si c'est clairement pour bébés 0-3 ans (langes, turbans bébé, jouets bébé, bodys)
- "toddler" : uniquement si c'est clairement pour tout-petits 1-5 ans
En cas de doute, mettre "adult".

QUANTITÉ INCERTAINE : Si la quantité vendue par unité n'est pas clairement précisée dans les données (titre, description, variants), mets "quantite_incertaine" à true et explique pourquoi dans "alerte_quantite". Si la quantité est claire (ex: "lot de 3", "1 pièce", "set of 2", variants avec quantités), mets false.

- Noms d'options : traduis les noms d'options en français en tenant compte de la catégorie du produit. Ex: "height" → "Taille" pour vêtements/peluches, "Hauteur" pour objets/meubles. "size" → "Taille", "color" → "Couleur", "weight" → "Poids", "length" → "Longueur", "shoe size" / "shoes size" / "foot size" → "Pointure", etc.

RÉPONDS UNIQUEMENT avec ce JSON valide, sans texte avant ni après, sans balises markdown :
{{
  "categorie_detectee": "...",
  "titre_fr": "...",
  "description_html": "...",
  "meta_title": "...",
  "meta_description": "...",
  "tags_fr": "...",
  "couleur": "...",
  "matiere": "...",
  "quantite_incertaine": false,
  "alerte_quantite": "",
  "age_group": "adult",
  "gender": "Unisex",
  "options_noms_traduits": {{
    "Color": "Couleur",
    "Size": "Taille",
    "Height": "Taille ou Hauteur selon le produit"
  }},
  "variants_traduits": [
    {{"original": "...", "traduit": "..."}}
  ]
}}"""

    reponse, err = appel_claude(prompt, max_tokens=1200)
    if err:
        return None, err

    # Parser le JSON retourné par Claude
    try:
        # Nettoyer les backticks markdown
        reponse_clean = re.sub(r"^```json\s*", "", reponse.strip())
        reponse_clean = re.sub(r"\s*```$", "", reponse_clean)
        # Tentative 1 : parsing direct
        try:
            fiche = json.loads(reponse_clean)
            return fiche, None
        except json.JSONDecodeError:
            pass
        # Tentative 2 : extraire uniquement le bloc JSON avec regex
        match = re.search(r'\{.*\}', reponse_clean, re.DOTALL)
        if match:
            try:
                fiche = json.loads(match.group())
                return fiche, None
            except json.JSONDecodeError:
                pass
        # Tentative 3 : parser champ par champ avec extraction regex
        fiche = {}
        for champ in ["categorie_detectee","titre_fr","meta_title","meta_description","tags_fr","couleur","matiere"]:
            m = re.search(rf'"{champ}"\s*:\s*"((?:[^"\\]|\\.)*)"', reponse_clean)
            if m:
                fiche[champ] = m.group(1)
        # Description HTML — peut contenir des guillemets
        m_desc = re.search(r'"description_html"\s*:\s*"(.*?)(?<!\\)"(?=\s*,\s*"(?:meta_title|meta_description|tags_fr|couleur|matiere|quantite|variants))', reponse_clean, re.DOTALL)
        if m_desc:
            fiche["description_html"] = m_desc.group(1).replace('\\"', '"').replace('\\n', '\n')
        # quantite_incertaine
        m_q = re.search(r'"quantite_incertaine"\s*:\s*(true|false)', reponse_clean)
        if m_q:
            fiche["quantite_incertaine"] = m_q.group(1) == "true"
        m_aq = re.search(r'"alerte_quantite"\s*:\s*"((?:[^"\\]|\\.)*)"', reponse_clean)
        if m_aq:
            fiche["alerte_quantite"] = m_aq.group(1)
        # variants_traduits
        variants_matches = re.findall(r'"original"\s*:\s*"([^"]*)"\s*,\s*"traduit"\s*:\s*"([^"]*)"', reponse_clean)
        if variants_matches:
            fiche["variants_traduits"] = [{"original": o, "traduit": t} for o, t in variants_matches]
        if fiche.get("titre_fr"):
            return fiche, None
        return None, f"Impossible de parser la réponse Claude: {reponse_clean[:300]}"
    except Exception as e:
        return None, f"Erreur parsing JSON Claude: {str(e)} — Réponse: {reponse[:200]}"

def generer_description_claude(titre, tags="", matiere="", couleur=""):
    """Garde pour compatibilité — délègue à optimiser_fiche_complete"""
    product = {"title": titre, "tags": tags}
    fiche, err = optimiser_fiche_complete(product)
    if err:
        return None, err
    return fiche.get("description_html", ""), None

NOMS_OPTIONS = {
    "color":"Couleur","colour":"Couleur","size":"Taille","material":"Matière",
    "style":"Style","type":"Type","model":"Modèle","pattern":"Motif",
    "weight":"Poids","length":"Longueur","width":"Largeur","height":"Taille",
    "quantity":"Quantité","pack":"Lot","set":"Ensemble","design":"Design",
    "specification":"Spécification","spec":"Spécification","shape":"Forme",
    "scent":"Parfum","flavor":"Parfum","capacity":"Capacité","power":"Puissance",
    "voltage":"Tension","count":"Quantité","number":"Quantité","pieces":"Pièces",
    "pack size":"Format","version":"Version","edition":"Édition",
    "shoe size":"Pointure","shoes size":"Pointure","foot size":"Pointure",
    "us size":"Pointure","eu size":"Pointure","uk size":"Pointure"
}

# Conversions pouces → cm pour les dimensions dans les variants
def convertir_dimensions(valeur):
    """Convertit les dimensions en pouces vers cm dans les valeurs de variants"""
    import re
    def inch_to_cm(match):
        inches = float(match.group(1))
        cm = round(inches * 2.54)
        return f"{cm}cm"
    # Pattern: nombre×nombreinch ou nombreinch
    valeur = re.sub(r'(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*inch(?:es)?',
                   lambda m: f"{round(float(m.group(1))*2.54)}×{round(float(m.group(2))*2.54)}cm",
                   valeur, flags=re.IGNORECASE)
    valeur = re.sub(r'(\d+(?:\.\d+)?)\s*inch(?:es)?', inch_to_cm, valeur, flags=re.IGNORECASE)
    # Traduire square/round/rectangle
    valeur = re.sub(r'\(square\)', '(carré)', valeur, flags=re.IGNORECASE)
    valeur = re.sub(r'\(round\)', '(rond)', valeur, flags=re.IGNORECASE)
    valeur = re.sub(r'\(rectangle\)', '(rectangle)', valeur, flags=re.IGNORECASE)
    valeur = re.sub(r'\(oval\)', '(ovale)', valeur, flags=re.IGNORECASE)
    return valeur

# Mots-clés pour détection du genre
MOTS_FEMME = ["women","woman","female","ladies","lady","girl","femme","feminin",
              "feminine","she","her","madame","mama","maman","maternite",
              "grossesse","allaitement","lingerie"]
MOTS_HOMME = ["men","man","male","boy","guy","homme","masculin","masculine",
              "he","him","monsieur","papa","barbe","rasage"]
MOTS_ENFANT = ["kids","kid","child","children","baby","infant","toddler","enfant",
               "bebe","garcon","fille","jouet","doudou","peluche","scolaire"]

def detecter_genre(titre, tags=""):
    """Detecte le genre a partir du titre et des tags — valeurs Google valides : male, female, unisex"""
    texte = (titre + " " + tags).lower()
    score_femme = sum(1 for m in MOTS_FEMME if m in texte)
    score_homme = sum(1 for m in MOTS_HOMME if m in texte)
    if score_femme > score_homme and score_femme > 0:
        return "female"
    if score_homme > score_femme and score_homme > 0:
        return "male"
    return "unisex"

def get_collections(token, shop):
    collections = []
    for endpoint in ["custom_collections", "smart_collections"]:
        res = requests.get(
            f"https://{shop}/admin/api/2026-04/{endpoint}.json?limit=250",
            headers={"X-Shopify-Access-Token": token})
        collections.extend(res.json().get(endpoint, []))
    return collections

def assigner_collection(token, shop, pid, collection_id):
    r = requests.post(
        f"https://{shop}/admin/api/2026-04/collects.json",
        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
        json={"collect": {"product_id": int(pid), "collection_id": collection_id}})
    return r.status_code in [200, 201]

# ─── TABLE DE CORRESPONDANCE MENU → TAGS ─────────────────────────────────────
# Structure : menu_general → [tag_general, {sous_menu → [tags_sous_menu]}]
STRUCTURE_MENU = {
    "Mon Salon": {
        "tag_general": "mon salon cocoon",
        "sous_menus": {
            "Coussin Cocoon":       ["coussin cocoon"],
            "Housse de Coussin":    ["housse coussin"],
            "Jeté de Canapé":      ["jeté de canapé"],
            "Plaid pour Canapé":   ["plaid pour canapé", "plaid"],
            "Tapis Cocoon":        ["Tapis cocoon", "salon cocoon"],
        }
    },
    "Ma Chambre": {
        "tag_general": "ma chambre cocoon",
        "sous_menus": {
            "Descente de Lit":              ["descente de lit"],
            "Parure de lit":               ["parure de lit"],
            "Plaid - Couverture - Dessus de lit": ["couvre lit", "dessus de lit", "couverture"],
        }
    },
    "Ma Salle de Bain": {
        "tag_general": "ma salle de bain cocoon",
        "sous_menus": {
            "Accessoires de Soin":  ["accessoires de soin", "soin du corps", "hygiène corps"],
            "Peignoir de Bain":    ["peignoir de bain", "peignoir"],
            "Pour ma Baignoire":   ["baignoire"],
            "Serviette":           ["serviette", "serviette de bain"],
            "Tapis de Bain":       ["tapis de bain"],
            "WC Cocoon":           ["wc"],
        }
    },
    "Me Cocooner": {
        "tag_general": "me cocooner",
        "sous_menus": {
            "Chaussettes":    ["chaussettes"],
            "Chaussons":      ["Chaussons"],
            "Gants":          ["gants"],
            "Jambières":     ["jambiere"],
            "Plaid à porter": ["plaid", "poncho"],
            "Rituel Sommeil": ["rituel sommeil", "sommeil", "masque nuit"],
            "Tour de Cou":    ["tour de cou"],
        }
    },
    "Mon enfant cocooné": {
        "tag_general": "mon enfant cocooné",
        "sous_menus": {
            "Accessoires":          ["accessoires enfant"],
            "Chambre - Sol et Murs":["chambre enfant", "végétalisation"],
            "Linges Cocooning":    ["linges cocooning"],
            "Epanouissement":      ["épanouissement"],
        }
    },
    "Accessoires Cocooning": {
        "tag_general": "accessoires cocooning",
        "sous_menus": {
            "Bouillotte":           ["bouillotte"],
            "Chauffe Pieds-Mains":  ["chauffe pieds", "chauffe mains"],
            "Couverture chauffante":["couverture chauffante"],
            "Coussin Confort":      ["coussin confort"],
            "Déco Cocoon":         ["Déco Cocoon"],
            "Eclairage Cocoon":    ["éclairage"],
            "Gadgets Cocoon":      ["gadgets cocoon"],
            "Mon Animal de Compagnie": ["mon animal de compagnie"],
            "Rangement Déco":      ["rangement"],
        }
    },
}

def detecter_menu_et_tags(titre_fr, tags_fr, categorie):
    """Demande à Claude de choisir le bon menu + sous-menu parmi la structure existante"""
    if not ANTHROPIC_API_KEY:
        return None, None, []

    # Construire la liste pour Claude
    structure_str = ""
    for menu, data in STRUCTURE_MENU.items():
        structure_str += f"\n{menu} (tag: {data['tag_general']}):\n"
        for sous_menu, tags in data["sous_menus"].items():
            structure_str += f"  - {sous_menu} (tags: {', '.join(tags)})\n"

    prompt = f"""Tu dois classer ce produit dans la bonne catégorie de la boutique Ma Maison Cocoon.

Produit : {titre_fr}
Catégorie détectée : {categorie}
Tags générés : {tags_fr}

Structure de navigation de la boutique (menu → sous-menus) :
{structure_str}

Règles de classification :
- Peluches, doudous, jouets → Mon enfant cocooné > Accessoires
- Linges bébé, langes, turbans, serviettes bébé → Mon enfant cocooné > Linges Cocooning
- Déco chambre enfant → Mon enfant cocooné > Chambre - Sol et Murs
- Coussins canapé, jeté, plaid canapé → Mon Salon
- Tapis → Mon Salon > Tapis Cocoon
- Serviette de bain, peignoir → Ma Salle de Bain
- Brosse, gant, lime, éponge, accessoire douche → Ma Salle de Bain > Accessoires de Soin
- Chaussettes, chaussons, gants, plaid à porter → Me Cocooner
- Bouillotte, chauffe-pieds → Accessoires Cocooning

Choisis le menu principal ET le sous-menu les plus appropriés.
Si le produit ne correspond à aucune catégorie existante, indique null pour les deux.

Réponds UNIQUEMENT avec ce JSON sans markdown :
{{"menu": "Nom du menu principal", "sous_menu": "Nom du sous-menu"}}
ou {{"menu": null, "sous_menu": null}}"""

    reponse, err = appel_claude(prompt, max_tokens=80)
    if err:
        return None, None, []
    try:
        import re
        clean = re.sub(r"```json|```", "", reponse.strip())
        data = json.loads(clean)
        menu = data.get("menu")
        sous_menu = data.get("sous_menu")
        if not menu or menu not in STRUCTURE_MENU:
            return None, None, []
        tags_a_ajouter = [STRUCTURE_MENU[menu]["tag_general"]]
        if sous_menu and sous_menu in STRUCTURE_MENU[menu]["sous_menus"]:
            tags_a_ajouter.extend(STRUCTURE_MENU[menu]["sous_menus"][sous_menu])
        return menu, sous_menu, tags_a_ajouter
    except:
        return None, None, []

def detecter_collection(titre_fr, tags_fr, categorie, collections):
    """Trouve les collections correspondant au menu et sous-menu détectés"""
    menu, sous_menu, tags_menu = detecter_menu_et_tags(titre_fr, tags_fr, categorie)
    if not menu:
        return [], tags_menu

    # Chercher les collections correspondantes dans Shopify
    collections_assignees = []
    for c in collections:
        titre_coll = c["title"].lower().strip()
        # Collection menu général
        if titre_coll == menu.lower().strip():
            collections_assignees.append(c)
        # Collection sous-menu
        elif sous_menu and titre_coll == sous_menu.lower().strip():
            collections_assignees.append(c)

    return collections_assignees, tags_menu

def calculer_prix(prix_actuel):
    """Calcule le prix final : floor(prix_dsers + 2) + 0.99
    DSers a déjà appliqué × 2.5, on ajoute 2€ et on arrondit au .99"""
    try:
        prix = float(prix_actuel)
        prix_plus_deux = prix + 2
        prix_final = math.floor(prix_plus_deux) + 0.99
        return prix_final
    except:
        return None

def publier_produit(token, shop, pid):
    """Passe le produit de brouillon à actif et publie sur tous les canaux"""
    r = requests.put(
        f"https://{shop}/admin/api/2026-04/products/{pid}.json",
        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
        json={"product": {"id": int(pid), "status": "active",
                          "published_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}})
    return r.status_code == 200

def publier_sur_canaux(token, shop, pid):
    """Active la publication sur tous les canaux via GraphQL"""
    # Récupérer les sales channels disponibles via GraphQL
    query = """
    {
      publications(first: 10) {
        edges {
          node {
            id
            name
            supportsFuturePublishing
          }
        }
      }
    }
    """
    res = requests.post(
        f"https://{shop}/admin/api/2026-04/graphql.json",
        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
        json={"query": query})
    if res.status_code != 200:
        return []
    
    canaux_actives = []
    try:
        publications = res.json().get("data", {}).get("publications", {}).get("edges", [])
    except Exception:
        publications = []
    
    # ID GraphQL du produit
    product_gid = f"gid://shopify/Product/{pid}"
    
    for edge in publications:
        node = edge.get("node", {})
        nom = node.get("name", "").lower()
        pub_id = node.get("id", "")
        if any(k in nom for k in ["online store", "boutique", "google", "youtube", "tiktok", "shop"]):
            mutation = """
            mutation publishablePublish($id: ID!, $input: [PublicationInput!]!) {
              publishablePublish(id: $id, input: $input) {
                publishable {
                  ... on Product {
                    title
                  }
                }
                userErrors {
                  field
                  message
                }
              }
            }
            """
            r = requests.post(
                f"https://{shop}/admin/api/2026-04/graphql.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"query": mutation, "variables": {
                    "id": product_gid,
                    "input": [{"publicationId": pub_id}]
                }})
            if r.status_code == 200:
                errors = r.json().get("data", {}).get("publishablePublish", {}).get("userErrors", [])
                if not errors:
                    canaux_actives.append(node["name"])
    return canaux_actives

def mettre_a_jour_handle(token, shop, pid, titre_fr):
    import re, unicodedata
    handle = unicodedata.normalize("NFD", titre_fr)
    handle = "".join(c for c in handle if unicodedata.category(c) != "Mn")
    handle = handle.lower()
    handle = re.sub(r"[^a-z0-9\s-]", "", handle)
    handle = re.sub(r"[\s-]+", "-", handle).strip("-")[:255]
    r = requests.put(
        f"https://{shop}/admin/api/2026-04/products/{pid}.json",
        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
        json={"product": {"id": int(pid), "handle": handle}})
    return handle if r.status_code == 200 else None

def construire_metafields(matiere, couleur, token, shop, pid, age_group="adult", titre_produit="", tags_produit="", **kwargs):
    res = requests.get(
        f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
        headers={"X-Shopify-Access-Token": token}
    )
    existing = {m["key"] for m in res.json().get("metafields", [])}
    to_add = []
    if matiere and "material" not in existing:
        to_add.append({"namespace":"google","key":"material","value":matiere,"type":"single_line_text_field"})
    if couleur and "color" not in existing:
        to_add.append({"namespace":"google","key":"color","value":couleur,"type":"single_line_text_field"})
    if "age_group" not in existing:
        to_add.append({"namespace":"google","key":"age_group","value":age_group,"type":"single_line_text_field"})
    if "gender" not in existing:
        # Priorité : valeur Claude si différente de Unisex
        genre_claude = kwargs.get("genre_claude", "Unisex") if kwargs else "Unisex"
        if genre_claude and genre_claude != "Unisex":
            genre = genre_claude  # Claude a détecté Female/Male/Unisex Kids
        else:
            # Fallback : dictionnaire mots-clés
            genre_dict = detecter_genre(titre_produit, tags_produit)
            genre = genre_dict if genre_dict != "Unisex" else genre_claude
        to_add.append({"namespace":"google","key":"gender","value":genre,"type":"single_line_text_field"})
    added = []
    for mf in to_add:
        r = requests.post(
            f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json={"metafield": mf}
        )
        if r.status_code in [200, 201]:
            added.append(mf["key"])
    return added

# ─── INTERFACE HTML ─────────────────────────────────────────────────────────────

@app.route("/")
@require_auth
def index():
    from flask import make_response
    html = """<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
    <title>Shopify Automation — Ma Maison Cocoon</title>
    <style>
    body{font-family:Arial,sans-serif;max-width:860px;margin:50px auto;padding:20px;background:#FDF6EE;color:#2C1A0E}
    h1{color:#8B4513}h2{color:#C4803A}
    .btn{background:#8B4513;color:white;padding:10px 18px;border:none;border-radius:6px;cursor:pointer;
         font-size:14px;margin:5px;text-decoration:none;display:inline-block}
    .btn:hover{background:#C4803A}.btn-green{background:#2E7D32}.btn-green:hover{background:#1B5E20}
    .btn-blue{background:#1565C0}.btn-blue:hover{background:#0D47A1}
    .card{background:white;padding:20px;margin:16px 0;border-radius:8px;border-left:4px solid #C4803A}
    .warn{border-left-color:#FFC107;background:#FFFDE7}
    .section-title{color:#8B4513;font-size:15px;font-weight:bold;margin:14px 0 6px}
    input[type=text]{width:98%;padding:8px;margin:6px 0;border:1px solid #ccc;border-radius:4px;box-sizing:border-box}
    select{padding:6px;border-radius:4px;border:1px solid #ccc}
    pre{background:#f0f0f0;padding:12px;border-radius:6px;overflow:auto;font-size:12px;max-height:400px}
    hr{border:none;border-top:1px solid #e0d0c0;margin:14px 0}
    </style></head><body>
    <h1>🕯️ Shopify Automation — Ma Maison Cocoon™ <span style="font-size:0.65rem;font-weight:normal;color:#aaa;vertical-align:middle">v2.18 — 09/06/2026</span></h1>
    <div class="card warn"><strong>⚡ Mode d'emploi :</strong><br>
    Pour les nouvelles actions : commence toujours par <strong>Simuler</strong> avant d'appliquer
    &nbsp;|&nbsp; <a href="/logout" style="color:#8B4513">🔒 Déconnexion</a></div>

    <div class="card"><h2>🔑 Configuration</h2>
    <label>URL Shopify :</label>
    <input type="text" id="shop" value="ma-maison-cocoon.myshopify.com">
    <div style="margin-top:10px;font-size:0.82rem;color:#888">🔐 Token Shopify expiré ou révoqué ? <a href="/auth" style="color:#8B4513;font-weight:bold">Générer un nouveau token via OAuth</a> — puis mettre à jour la variable <code>SHOPIFY_TOKEN</code> dans Render.</div>
    </div>

    <div class="card"><h2>🛠️ Actions catalogue</h2>
    <div class="section-title">Métadonnées Google Merchant (GMC)</div>
    <div style="margin-bottom:6px">
    <strong style="font-size:0.85rem;color:#666">Tout le catalogue :</strong><br>
    <button class="btn" onclick="(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='Traitement...';fetch('/fix-gmc-all?dry=true&shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — logs Render':'Session expiree — /logout';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">🔎 Tout vérifier GMC</button>
    <button class="btn btn-green" onclick="(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='Traitement...';fetch('/fix-gmc-all?dry=false&shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — logs Render':'Session expiree — /logout';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">✅ Tout corriger GMC</button>
    </div>
    <div style="margin-top:8px">
    <strong style="font-size:0.85rem;color:#666">Par catégorie :</strong><br>
    <button class="btn" onclick="(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='Traitement...';fetch('/fix-gender?shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — logs Render':'Session expiree — /logout';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">♀ Sexe</button>
    <button class="btn" onclick="(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='Traitement...';fetch('/fix-age-group?shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — logs Render':'Session expiree — /logout';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">👶 Âge</button>
    <button class="btn" onclick="(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='Traitement...';fetch('/fix-color?shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — logs Render':'Session expiree — /logout';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">🎨 Couleur</button>
    <button class="btn" onclick="(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='Traitement...';fetch('/fix-size?shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — logs Render':'Session expiree — /logout';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">📐 Taille</button>
    </div>
    <hr>
    <div class="section-title">Tags & Audit</div>
    <button class="btn" onclick="(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';fetch('/fix-tags?shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">🏷️ Optimiser tags</button>
    <button class="btn" onclick="(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';fetch('/fix-seo?shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">🔍 Audit SEO</button>
    <button class="btn" onclick="window.open('/export-products?format=json&shop='+document.getElementById('shop').value,'_blank')">📊 Exporter JSON</button>
    <button class="btn" onclick="window.open('/export-products?format=csv&shop='+document.getElementById('shop').value,'_blank')">📋 Exporter CSV</button>
    <div class="section-title" style="margin-top:14px">Descriptions — Phrases globales</div>
    <button class="btn" onclick="(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';fetch('/fix-disclaimers?dry=true&shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">👁 Vérifier disclaimers</button>
    <button class="btn" style="background:#C4803A" onclick="if(!confirm('Ajouter disclaimers ?'))return;(function(){var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';fetch('/fix-disclaimers?dry=false&shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">🔧 Ajouter disclaimers manquants</button>
    <div style="margin:10px 0 6px 0">
      <input type="text" id="append-phrase" placeholder="Phrase à ajouter à toutes les fiches..." style="width:100%;margin-bottom:6px">
      <select id="append-filter" style="width:auto;margin:0 8px 0 0">
        <option value="all">Tous les produits</option>
        <option value="active">Publiés uniquement</option>
        <option value="drafts">Brouillons uniquement</option>
      </select>
      <button class="btn" onclick="(function(){var phrase=document.getElementById('append-phrase').value.trim();if(!phrase){alert('Entre une phrase');return;}var filtre=document.getElementById('append-filter').value;var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';fetch('/append-to-all?dry=true&filter='+filtre+'&phrase='+encodeURIComponent(phrase)+'&shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">👁 Simuler</button>
      <button class="btn btn-green" onclick="(function(){var phrase=document.getElementById('append-phrase').value.trim();if(!phrase){alert('Entre une phrase');return;}if(!confirm('Appliquer ?'))return;var filtre=document.getElementById('append-filter').value;var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';fetch('/append-to-all?dry=false&filter='+filtre+'&phrase='+encodeURIComponent(phrase)+'&shop='+document.getElementById('shop').value).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">✅ Appliquer à tous</button>
    </div>
    </div>

    <div class="card"><h2>✨ Optimisation fiches produits (Claude AI)</h2>
    <div class="section-title">Test sur 1 produit</div>
    <input type="text" id="product-id" placeholder="ID produit Shopify (ex: 8765432109876)">
    <div style="margin:8px 0">
      <label><input type="checkbox" id="act-desc" checked> Description SEO</label>&nbsp;&nbsp;
      <label><input type="checkbox" id="act-var" checked> Traduction variants (couleurs/tailles)</label>&nbsp;&nbsp;
      <label><input type="checkbox" id="act-meta" checked> Métadonnées Google Merchant</label>
    </div>
    <div style="display:flex;gap:10px;margin:8px 0">
      <div style="flex:1">
        <label style="font-size:0.82rem;color:#666;display:block;margin-bottom:3px">Collection à forcer <span style="color:#bbb">(optionnel)</span></label>
        <input type="text" id="force-collection" placeholder="ex: rituel-sommeil" style="margin:0">
      </div>
      <div style="flex:1">
        <label style="font-size:0.82rem;color:#666;display:block;margin-bottom:3px">Tags supplémentaires <span style="color:#bbb">(optionnel, séparés par virgules)</span></label>
        <input type="text" id="tags-extra" placeholder="ex: sommeil, cadeau" style="margin:0">
      </div>
    </div>
    <button class="btn btn-blue" onclick="(function(){var pid=document.getElementById('product-id').value.trim();if(!pid){alert('ID requis');return;}var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';var a=[];var d=document.getElementById('act-desc');if(d&&d.checked)a.push('description');var v=document.getElementById('act-var');if(v&&v.checked)a.push('variants');var m=document.getElementById('act-meta');if(m&&m.checked)a.push('metafields');var fc=document.getElementById('force-collection').value.trim();var te=document.getElementById('tags-extra').value.trim();var url='/optimize-product?id='+pid+'&dry=true&actions='+a.join(',')+'&shop='+document.getElementById('shop').value;if(fc)url+='&force_collection='+encodeURIComponent(fc);if(te)url+='&tags_extra='+encodeURIComponent(te);fetch(url).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">👁 Simuler (dry run)</button>
    <button class="btn btn-green" onclick="(function(){var pid=document.getElementById('product-id').value.trim();if(!pid){alert('ID requis');return;}if(!confirm('Appliquer ?'))return;var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';var a=[];var d=document.getElementById('act-desc');if(d&&d.checked)a.push('description');var v=document.getElementById('act-var');if(v&&v.checked)a.push('variants');var m=document.getElementById('act-meta');if(m&&m.checked)a.push('metafields');var fc=document.getElementById('force-collection').value.trim();var te=document.getElementById('tags-extra').value.trim();var url='/optimize-product?id='+pid+'&dry=false&actions='+a.join(',')+'&shop='+document.getElementById('shop').value;if(fc)url+='&force_collection='+encodeURIComponent(fc);if(te)url+='&tags_extra='+encodeURIComponent(te);fetch(url).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">✅ Appliquer sur ce produit</button>
    <hr>
    <div class="section-title">Batch — plusieurs produits</div>
    <div style="margin:8px 0">
      Filtre :
      <select id="batch-filter">
        <option value="drafts">Brouillons uniquement (nouveaux imports DSers)</option>
        <option value="no-description">Sans description (ou &lt; 100 car.)</option>
        <option value="all">Tous les produits</option>
      </select>
      &nbsp; Limite :
      <select id="batch-limit">
        <option value="5">5 produits</option>
        <option value="10" selected>10 produits</option>
        <option value="25">25 produits</option>
        <option value="50">50 produits</option>
      </select>
    </div>
    <div style="display:flex;gap:10px;margin:8px 0">
      <div style="flex:1">
        <label style="font-size:0.82rem;color:#666;display:block;margin-bottom:3px">Collection à forcer <span style="color:#bbb">(optionnel)</span></label>
        <input type="text" id="batch-force-collection" placeholder="ex: rituel-sommeil" style="margin:0">
      </div>
      <div style="flex:1">
        <label style="font-size:0.82rem;color:#666;display:block;margin-bottom:3px">Tags supplémentaires <span style="color:#bbb">(optionnel, séparés par virgules)</span></label>
        <input type="text" id="batch-tags-extra" placeholder="ex: sommeil, cadeau" style="margin:0">
      </div>
    </div>
    <button class="btn btn-blue" onclick="(function(){var f=document.getElementById('batch-filter').value;var l=document.getElementById('batch-limit').value;var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';var a=[];var d=document.getElementById('act-desc');if(d&&d.checked)a.push('description');var v=document.getElementById('act-var');if(v&&v.checked)a.push('variants');var m=document.getElementById('act-meta');if(m&&m.checked)a.push('metafields');var fc=document.getElementById('batch-force-collection').value.trim();var te=document.getElementById('batch-tags-extra').value.trim();var url='/optimize-batch?filter='+f+'&limit='+l+'&dry=true&actions='+a.join(',')+'&shop='+document.getElementById('shop').value;if(fc)url+='&force_collection='+encodeURIComponent(fc);if(te)url+='&tags_extra='+encodeURIComponent(te);fetch(url).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">👁 Simuler batch</button>
    <button class="btn btn-green" onclick="(function(){var f=document.getElementById('batch-filter').value;var l=document.getElementById('batch-limit').value;if(!confirm('Appliquer sur '+l+' produits ?'))return;var o=document.getElementById('out');o.style.color='#333';o.style.fontStyle='normal';o.innerText='...';var a=[];var d=document.getElementById('act-desc');if(d&&d.checked)a.push('description');var v=document.getElementById('act-var');if(v&&v.checked)a.push('variants');var m=document.getElementById('act-meta');if(m&&m.checked)a.push('metafields');var fc=document.getElementById('batch-force-collection').value.trim();var te=document.getElementById('batch-tags-extra').value.trim();var url='/optimize-batch?filter='+f+'&limit='+l+'&dry=false&actions='+a.join(',')+'&shop='+document.getElementById('shop').value;if(fc)url+='&force_collection='+encodeURIComponent(fc);if(te)url+='&tags_extra='+encodeURIComponent(te);fetch(url).then(function(r){var status=r.status;return r.text().then(function(t){return {s:status,t:t};});}).then(function(x){if(x.t.indexOf('<')===0){o.style.color='red';o.innerText=x.s===500?'Erreur serveur 500 — verifier les logs Render (token Shopify invalide ?)':'Session expiree — allez sur /logout puis reconnectez-vous';return;}try{o.style.color='#333';o.innerText=JSON.stringify(JSON.parse(x.t),null,2);}catch(e){o.innerText=x.t;}}).catch(function(e){o.innerText='Err:'+e;});})()">🚀 Appliquer batch</button>
    </div>

    <div class="card" id="res"><h2>📋 Résultat</h2>
    <button onclick="try{document.getElementById('out').innerText='✅ JS fonctionne — cliquez une action ci-dessus';}catch(e){alert('Erreur: '+e)}" style="background:#eee;border:1px solid #ccc;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:0.8rem;margin-bottom:4px">🧪 Tester le JS</button>
    <button onclick="document.getElementById('out').style.color='#333';document.getElementById('out').style.fontStyle='normal';document.getElementById('out').innerText='Envoi requete...';fetch('/fix-seo?shop=ma-maison-cocoon.myshopify.com').then(function(r){return r.text();}).then(function(t){document.getElementById('out').innerText=t.substring(0,500);}).catch(function(e){document.getElementById('out').innerText='ERREUR FETCH: '+e;})" style="background:#eee;border:1px solid #ccc;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:0.8rem;margin-bottom:8px">🔬 Tester requête serveur</button>
    <pre id="out" style="color:#aaa;font-style:italic">En attente d'une action...</pre></div>

    <script>
    (function(){
      var shopEl=document.getElementById('shop');
      if(shopEl) shopEl.addEventListener('input',function(){
        var btn=document.getElementById('oauthBtn'); if(btn) btn.href='/auth?shop='+this.value;
      });
    })();
    </script></body></html>"""
    resp = make_response(html)
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

# ─── ROUTES EXISTANTES (inchangées) ────────────────────────────────────────────

@app.route("/auth")
def auth():
    shop = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    redirect_uri = request.host_url + "callback"
    return redirect(f"https://{shop}/admin/oauth/authorize?client_id={API_KEY}&scope={SCOPES}&redirect_uri={redirect_uri}")

@app.route("/callback")
def callback():
    code = request.args.get("code")
    shop = request.args.get("shop")
    if not code or not shop:
        return "Erreur: paramètres manquants", 400
    res = requests.post(f"https://{shop}/admin/oauth/access_token",
        json={"client_id": API_KEY, "client_secret": API_SECRET, "code": code})
    data = res.json()
    token = data.get("access_token")
    if not token:
        return f"Erreur OAuth: {data}", 400
    return f"""<h1 style="color:green">✅ Connexion réussie !</h1>
    <p>Ton access token (copie-le) :</p>
    <code style="background:#f0f0f0;padding:10px;display:block;word-break:break-all">{token}</code>
    <br><a href="/" style="background:#8B4513;color:white;padding:10px 20px;border-radius:6px;text-decoration:none">← Retour</a>"""

@app.route("/fix-gender")
def fix_gender():
    token = SHOPIFY_TOKEN
    shop  = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    dry   = request.args.get("dry", "false") == "true"
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    updated = errors = 0
    for product in products:
        pid = product["id"]
        meta_res = requests.get(f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
            headers={"X-Shopify-Access-Token": token})
        metafields = meta_res.json().get("metafields", [])
        gender_mf = next((m for m in metafields if m.get("key") == "gender"), None)
        valeurs_valides = ["male", "female", "unisex"]
        if gender_mf and gender_mf.get("value", "").lower() in valeurs_valides:
            continue
        if dry:
            updated += 1
            continue
        new_value = detecter_genre(product.get("title",""), product.get("tags",""))
        if gender_mf:
            # Mettre à jour la valeur invalide existante
            res = requests.put(f"https://{shop}/admin/api/2026-04/products/{pid}/metafields/{gender_mf['id']}.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"metafield": {"id": gender_mf["id"], "value": new_value, "type": "single_line_text_field"}})
        else:
            # Créer le metafield manquant
            res = requests.post(f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"metafield": {"namespace": "google", "key": "gender", "value": new_value, "type": "single_line_text_field"}})
        if res.status_code in [200, 201]:
            updated += 1
        else:
            errors += 1
        time.sleep(0.3)
    return jsonify({"action": "fix-gender", "total": len(products), "updated": updated, "errors": errors, "dry_run": dry})

@app.route("/fix-age-group")
def fix_age_group():
    token = SHOPIFY_TOKEN
    shop  = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    dry   = request.args.get("dry", "false") == "true"
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    updated = errors = 0
    for product in products:
        pid = product["id"]
        meta_res = requests.get(
            f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
            headers={"X-Shopify-Access-Token": token})
        metafields = meta_res.json().get("metafields", [])
        if any(m.get("key") == "age_group" for m in metafields):
            continue
        if dry:
            updated += 1
            continue
        res = requests.post(
            f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json={"metafield": {"namespace": "google", "key": "age_group", "value": "adult", "type": "single_line_text_field"}})
        if res.status_code in [200, 201]:
            updated += 1
        else:
            errors += 1
        time.sleep(0.3)
    return jsonify({"action": "fix-age-group", "total": len(products), "updated": updated, "errors": errors, "dry_run": dry})


@app.route("/fix-gmc-all")
def fix_gmc_all():
    token = SHOPIFY_TOKEN
    shop  = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    dry   = request.args.get("dry", "false") == "true"
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    NOMS_COULEUR = {"couleur", "color", "colour"}
    NOMS_TAILLE  = {"taille", "size", "pointure", "hauteur", "longueur"}
    VALEURS_VALIDES_GENDER = ["male", "female", "unisex"]

    gender_updated = age_updated = color_updated = size_updated = errors = 0

    for product in products:
        pid = product["id"]
        meta_res = requests.get(
            f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
            headers={"X-Shopify-Access-Token": token})
        metafields = meta_res.json().get("metafields", [])
        mf_map = {m["key"]: m for m in metafields if m.get("namespace") == "google"}

        to_set = []

        # Gender
        gm = mf_map.get("gender")
        if not gm or gm.get("value", "").lower() not in VALEURS_VALIDES_GENDER:
            new_val = detecter_genre(product.get("title",""), product.get("tags",""))
            if gm and not dry:
                requests.put(f"https://{shop}/admin/api/2026-04/products/{pid}/metafields/{gm['id']}.json",
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                    json={"metafield": {"id": gm["id"], "value": new_val, "type": "single_line_text_field"}})
            else:
                to_set.append({"namespace": "google", "key": "gender", "value": new_val, "type": "single_line_text_field"})
            gender_updated += 1

        # Age group
        if "age_group" not in mf_map:
            to_set.append({"namespace": "google", "key": "age_group", "value": "adult", "type": "single_line_text_field"})
            age_updated += 1

        # Color
        if "color" not in mf_map:
            options = product.get("options", [])
            couleurs = []
            for opt in options:
                if opt.get("name", "").lower() in NOMS_COULEUR:
                    for val in opt.get("values", []):
                        if val and val not in couleurs:
                            couleurs.append(val)
            if couleurs:
                to_set.append({"namespace": "google", "key": "color", "value": " / ".join(couleurs[:3]), "type": "single_line_text_field"})
                color_updated += 1

        # Size
        if "size" not in mf_map:
            options = product.get("options", [])
            tailles = []
            for opt in options:
                if opt.get("name", "").lower() in NOMS_TAILLE:
                    for val in opt.get("values", []):
                        if val and val not in tailles:
                            tailles.append(val)
            if tailles:
                if len(tailles) == 1 and tailles[0].lower() in {"one size", "taille unique", "unique"}:
                    size_val = "Taille unique"
                else:
                    size_val = tailles[0]
                to_set.append({"namespace": "google", "key": "size", "value": size_val, "type": "single_line_text_field"})
                size_updated += 1

        if to_set and not dry:
            for mf in to_set:
                res = requests.post(
                    f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                    json={"metafield": mf})
                if res.status_code not in [200, 201]:
                    errors += 1
            time.sleep(0.3)

    return jsonify({
        "action": "fix-gmc-all",
        "total": len(products),
        "gender_updated": gender_updated,
        "age_group_updated": age_updated,
        "color_updated": color_updated,
        "size_updated": size_updated,
        "errors": errors,
        "dry_run": dry
    })



def fix_color():
    token = SHOPIFY_TOKEN
    shop  = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    dry   = request.args.get("dry", "false") == "true"
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    updated = skipped = errors = 0
    NOMS_COULEUR = {"couleur", "color", "colour"}
    for product in products:
        pid = product["id"]
        meta_res = requests.get(
            f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
            headers={"X-Shopify-Access-Token": token})
        metafields = meta_res.json().get("metafields", [])
        if any(m.get("key") == "color" and m.get("namespace") == "google" for m in metafields):
            skipped += 1
            continue
        # Extraire les couleurs uniques depuis les variants
        couleurs = []
        for v in product.get("variants", []):
            for opt in v.get("option_values", []) if "option_values" in v else []:
                if opt.get("presentation_name", "").lower() in NOMS_COULEUR:
                    val = opt.get("name", "").strip()
                    if val and val not in couleurs:
                        couleurs.append(val)
        # Fallback : lire via les options du produit
        if not couleurs:
            options = product.get("options", [])
            for opt in options:
                if opt.get("name", "").lower() in NOMS_COULEUR:
                    for val in opt.get("values", []):
                        if val and val not in couleurs:
                            couleurs.append(val)
        if not couleurs:
            skipped += 1
            continue
        color_value = " / ".join(couleurs[:3])  # Google accepte max 3 couleurs
        if dry:
            updated += 1
            continue
        res = requests.post(
            f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json={"metafield": {"namespace": "google", "key": "color", "value": color_value, "type": "single_line_text_field"}})
        if res.status_code in [200, 201]:
            updated += 1
        else:
            errors += 1
        time.sleep(0.3)
    return jsonify({"action": "fix-color", "total": len(products), "updated": updated, "skipped": skipped, "errors": errors, "dry_run": dry})


@app.route("/fix-size")
def fix_size():
    token = SHOPIFY_TOKEN
    shop  = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    dry   = request.args.get("dry", "false") == "true"
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    updated = skipped = errors = 0
    NOMS_TAILLE = {"taille", "size", "pointure", "hauteur", "longueur"}
    for product in products:
        pid = product["id"]
        meta_res = requests.get(
            f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
            headers={"X-Shopify-Access-Token": token})
        metafields = meta_res.json().get("metafields", [])
        if any(m.get("key") == "size" and m.get("namespace") == "google" for m in metafields):
            skipped += 1
            continue
        # Extraire les tailles uniques depuis les options du produit
        tailles = []
        options = product.get("options", [])
        for opt in options:
            if opt.get("name", "").lower() in NOMS_TAILLE:
                for val in opt.get("values", []):
                    if val and val not in tailles:
                        tailles.append(val)
        if not tailles:
            skipped += 1
            continue
        # Si taille unique → "Taille unique", sinon première valeur représentative
        if len(tailles) == 1 and tailles[0].lower() in {"one size", "taille unique", "unique"}:
            size_value = "Taille unique"
        else:
            size_value = tailles[0]  # Valeur représentative (Google veut 1 valeur au niveau produit)
        if dry:
            updated += 1
            continue
        res = requests.post(
            f"https://{shop}/admin/api/2026-04/products/{pid}/metafields.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json={"metafield": {"namespace": "google", "key": "size", "value": size_value, "type": "single_line_text_field"}})
        if res.status_code in [200, 201]:
            updated += 1
        else:
            errors += 1
        time.sleep(0.3)
    return jsonify({"action": "fix-size", "total": len(products), "updated": updated, "skipped": skipped, "errors": errors, "dry_run": dry})



def fix_prices():
    token = SHOPIFY_TOKEN
    shop   = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    margin = float(request.args.get("margin", "2.5"))
    dry    = request.args.get("dry", "true") == "true"
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    updated = skipped = 0
    for product in products:
        pid = product["id"]
        variants = product.get("variants", [])
        new_variants = []
        for v in variants:
            price   = float(v.get("price", 0))
            compare = float(v.get("compare_at_price") or 0)
            if compare == 0 and price > 0:
                new_variants.append({"id": v["id"], "compare_at_price": str(round(price * margin, 2))})
            else:
                skipped += 1
        if new_variants:
            if not dry:
                res = requests.put(f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                    json={"product": {"id": pid, "variants": new_variants}})
                if res.status_code == 200:
                    updated += 1
            else:
                updated += 1
        time.sleep(0.3)
    return jsonify({"action": "fix-prices", "margin": f"x{margin}", "total": len(products),
                    "updated": updated, "skipped": skipped, "dry_run": dry})

@app.route("/fix-tags")
def fix_tags():
    token = SHOPIFY_TOKEN
    shop  = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    dry   = request.args.get("dry", "false") == "true"
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    rules = {
        "tapis":     ["tapis", "décoration", "salon cocooning"],
        "bougie":    ["bougie", "rituel", "bien-être", "cocooning"],
        "plaid":     ["plaid", "cocooning", "salon", "douceur"],
        "coussin":   ["coussin", "décoration", "confort"],
        "pyjama":    ["pyjama", "nuit", "cocooning"],
        "sherpa":    ["sherpa", "douceur", "cocooning"],
        "bambou":    ["bambou", "naturel", "écologique"],
        "diffuseur": ["diffuseur", "aromathérapie", "bien-être"],
    }
    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    updated = 0
    for product in products:
        pid   = product["id"]
        title = product.get("title", "").lower()
        existing = set(t.strip() for t in product.get("tags", "").split(",") if t.strip())
        new_tags = set(existing)
        for kw, tags in rules.items():
            if kw in title:
                new_tags.update(tags)
        if new_tags != existing:
            if not dry:
                res = requests.put(f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                    json={"product": {"id": pid, "tags": ", ".join(sorted(new_tags))}})
                if res.status_code == 200:
                    updated += 1
            else:
                updated += 1
        time.sleep(0.3)
    return jsonify({"action": "fix-tags", "total": len(products), "updated": updated, "dry_run": dry})

@app.route("/fix-seo")
def fix_seo():
    import re
    token = SHOPIFY_TOKEN
    shop  = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500

    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # Mots anglais courants pour détecter contenu en anglais
    mots_anglais = ["the","and","for","with","you","your","this","that","have",
                    "from","soft","comfortable","perfect","material","color","size",
                    "brand","product","quality","specifications","application"]

    def est_anglais(texte):
        if not texte: return False
        texte_lower = texte.lower()
        score = sum(1 for m in mots_anglais if f" {m} " in texte_lower or texte_lower.startswith(m+" "))
        return score >= 3

    def variants_non_traduits(variants):
        combined = {**COULEURS, **TAILLES}
        non_traduits = []
        for v in variants:
            for opt in ["option1","option2","option3"]:
                val = (v.get(opt) or "").strip()
                if not val:
                    continue
                v_lower = val.lower()
                if v_lower in combined:
                    traduction = combined[v_lower]
                    # Ne flaguer que si c'est un vrai mot différent (autre langue)
                    # Ignorer les différences de casse uniquement : "beige" vs "Beige" = OK
                    if val.lower() != traduction.lower():
                        non_traduits.append(val)
        return list(set(non_traduits))

    stats = {
        "total": len(products),
        "problemes": {
            "titre_anglais": [],
            "description_absente": [],
            "description_courte": [],
            "description_anglaise": [],
            "sans_image": [],
            "sans_tags": [],
            "variants_non_traduits": [],
            "prix_zero": [],
        }
    }

    for p in products:
        pid = str(p["id"])
        titre = p.get("title","")
        desc = p.get("body_html","") or ""
        desc_texte = re.sub(r'<[^>]+>',' ',desc).strip()
        tags = p.get("tags","")
        variants = p.get("variants",[])
        item = {"id": pid, "titre": titre[:60]}

        if est_anglais(titre):
            stats["problemes"]["titre_anglais"].append(item)

        if not desc_texte:
            stats["problemes"]["description_absente"].append(item)
        elif len(desc_texte) < 100:
            stats["problemes"]["description_courte"].append({**item, "longueur": len(desc_texte)})
        elif est_anglais(desc_texte):
            stats["problemes"]["description_anglaise"].append(item)

        if not p.get("images"):
            stats["problemes"]["sans_image"].append(item)

        if not tags:
            stats["problemes"]["sans_tags"].append(item)

        non_traduits = variants_non_traduits(variants)
        if non_traduits:
            stats["problemes"]["variants_non_traduits"].append({**item, "variants": non_traduits[:5]})

        for v in variants:
            prix = float(v.get("price",0) or 0)
            if prix == 0:
                stats["problemes"]["prix_zero"].append(item)
                break

    # Résumé
    stats["resume"] = {k: len(v) for k,v in stats["problemes"].items()}
    stats["score_sante"] = round((1 - sum(stats["resume"].values()) / max(len(products)*8, 1)) * 100, 1)

    # Limiter les listes à 30 items pour lisibilité
    for k in stats["problemes"]:
        stats["problemes"][k] = stats["problemes"][k][:30]

    return jsonify(stats)

# ─── DISCLAIMERS & APPEND ───────────────────────────────────────────────────────

DISCLAIMER_COULEUR = "<p><em>Remarque : En raison des conditions de prise de vue et des variations d'affichage selon les écrans, les couleurs peuvent légèrement différer de la réalité.</em></p>"
DISCLAIMER_DIMENSIONS = '<p><em>Les dimensions et tailles indiquées sont données à titre indicatif. De légères variations peuvent exister en raison du processus de fabrication et des méthodes de mesure.</em></p>'

@app.route("/fix-disclaimers")
def fix_disclaimers():
    """Vérifie et ajoute les deux phrases disclaimer sur tous les produits qui ne les ont pas."""
    token = SHOPIFY_TOKEN
    shop  = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    dry   = request.args.get("dry", "true") == "true"
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500

    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    updated, skipped, sans_couleur, sans_dimensions = 0, 0, [], []

    for p in products:
        pid   = str(p["id"])
        titre = p.get("title", "")[:60]
        body  = p.get("body_html", "") or ""
        if not body:
            skipped += 1
            continue

        a_couleur     = "prise de vue" in body.lower()
        a_dimensions  = "titre indicatif" in body.lower() or "à titre indicatif" in body.lower()
        if a_couleur and a_dimensions:
            skipped += 1
            continue

        ajouts = ""
        if not a_couleur:
            ajouts += DISCLAIMER_COULEUR
            sans_couleur.append({"id": pid, "titre": titre})
        if not a_dimensions:
            ajouts += DISCLAIMER_DIMENSIONS
            sans_dimensions.append({"id": pid, "titre": titre})

        if not dry:
            requests.put(
                f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"product": {"id": int(pid), "body_html": body + ajouts}})
            time.sleep(0.3)
        updated += 1

    return jsonify({
        "action": "fix-disclaimers",
        "dry_run": dry,
        "total": len(products),
        "skipped_deja_ok": skipped,
        "updated": updated,
        "sans_disclaimer_couleur": len(sans_couleur),
        "sans_disclaimer_dimensions": len(sans_dimensions),
        "statut": "simulation" if dry else "appliqué"
    })


@app.route("/append-to-all")
def append_to_all():
    """Ajoute un bloc HTML personnalisé à la fin de toutes les descriptions."""
    token = SHOPIFY_TOKEN
    shop   = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    dry    = request.args.get("dry", "true") == "true"
    phrase = request.args.get("phrase", "").strip()
    filtre = request.args.get("filter", "all")  # all | active | drafts

    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    if not phrase:
        return jsonify({"error": "Paramètre 'phrase' manquant"}), 400

    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    if filtre == "active":
        products = [p for p in products if p.get("status") == "active"]
    elif filtre == "drafts":
        products = [p for p in products if p.get("status") == "draft"]

    bloc_html = f"<p>{phrase}</p>"
    updated, skipped = 0, 0

    for p in products:
        pid  = str(p["id"])
        body = p.get("body_html", "") or ""
        if not body:
            skipped += 1
            continue
        # Ne pas ajouter si la phrase est déjà présente
        if phrase[:40] in body:
            skipped += 1
            continue
        if not dry:
            requests.put(
                f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"product": {"id": int(pid), "body_html": body + bloc_html}})
            time.sleep(0.3)
        updated += 1

    return jsonify({
        "action": "append-to-all",
        "phrase_ajoutee": phrase,
        "filtre": filtre,
        "dry_run": dry,
        "total": len(products),
        "updated": updated,
        "skipped_deja_present_ou_vide": skipped,
        "statut": "simulation" if dry else "appliqué"
    })


@app.route("/export-products")
def export_products():
    import csv, io
    from flask import Response
    token = SHOPIFY_TOKEN
    shop   = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    format = request.args.get("format", "json")
    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    export = []
    for p in products:
        variants = p.get("variants", [])
        prix = variants[0]["price"] if variants else "0"
        prix_barre = variants[0].get("compare_at_price","") if variants else ""
        export.append({
            "id": str(p["id"]),
            "titre": p.get("title",""),
            "statut": p.get("status",""),
            "prix": prix,
            "prix_barre": prix_barre or "",
            "tags": p.get("tags",""),
            "nb_images": len(p.get("images",[])),
            "nb_variants": len(variants),
            "url": f"https://{shop}/products/{p.get('handle','')}",
            "meta_title": p.get("metafields_global_title_tag","") or "",
            "meta_description": p.get("metafields_global_description_tag","") or "",
        })

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=export[0].keys() if export else [],
                               delimiter=";", quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(export)
        csv_data = output.getvalue()
        return Response(
            "﻿" + csv_data,  # BOM UTF-8 pour Excel
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=catalogue-ma-maison-cocoon.csv"}
        )
    return jsonify({"total": len(export), "products": export})

@app.route("/version")
def version():
    return jsonify({"version": VERSION, "date": VERSION_DATE, "label": VERSION_LABEL})

@app.route("/optimize-form")
def optimize_form():
    """Interface web pour lancer une optimisation produit sans construire l'URL à la main"""
    token = SHOPIFY_TOKEN
    shop  = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Optimiser un produit – Ma Maison Cocoon</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px; background: #faf9f7; color: #333; }}
  h1 {{ font-size: 1.3rem; color: #5c4033; margin-bottom: 4px; }}
  p.sub {{ color: #888; font-size: 0.85rem; margin-top: 0; margin-bottom: 28px; }}
  label {{ display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 5px; color: #555; }}
  input, select {{ width: 100%; padding: 9px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 0.95rem; box-sizing: border-box; background: #fff; margin-bottom: 18px; }}
  input:focus {{ outline: none; border-color: #a0856e; }}
  .hint {{ font-size: 0.78rem; color: #999; margin-top: -14px; margin-bottom: 16px; }}
  .row {{ display: flex; gap: 12px; }}
  .row > div {{ flex: 1; }}
  button {{ background: #5c4033; color: #fff; border: none; padding: 11px 28px; border-radius: 8px; font-size: 1rem; cursor: pointer; width: 100%; margin-top: 4px; }}
  button:hover {{ background: #7a5544; }}
  .dry-toggle {{ display: flex; align-items: center; gap: 10px; margin-bottom: 20px; }}
  .dry-toggle input {{ width: auto; margin: 0; }}
  .dry-toggle label {{ margin: 0; font-weight: normal; }}
  #result {{ margin-top: 24px; background: #fff; border: 1px solid #eee; border-radius: 10px; padding: 16px; font-size: 0.82rem; white-space: pre-wrap; word-break: break-all; display: none; }}
  .tag-ok {{ color: #2e7d32; font-weight: 600; }}
  .tag-err {{ color: #c62828; font-weight: 600; }}
</style>
</head>
<body>
<h1>Optimiser un produit</h1>
<p class="sub">Ma Maison Cocoon – Automatisation Shopify</p>

<label>ID Produit Shopify *</label>
<input type="text" id="pid" placeholder="ex: 8742631948..." />

<label>Boutique</label>
<input type="text" id="shop" value="{shop}" />

<label>Collection à forcer <span style="font-weight:normal;color:#aaa">(optionnel)</span></label>
<input type="text" id="force_col" placeholder="ex: rituel-sommeil" />
<p class="hint">Laisser vide pour détection automatique. Utiliser le handle Shopify (sans espaces).</p>

<label>Tags supplémentaires <span style="font-weight:normal;color:#aaa">(optionnel)</span></label>
<input type="text" id="tags_extra" placeholder="ex: sommeil, bien-être nuit, cadeau" />
<p class="hint">Séparés par des virgules. Ajoutés en plus des tags générés automatiquement.</p>

<div class="dry-toggle">
  <input type="checkbox" id="dry" checked />
  <label for="dry">Mode simulation (dry run) – ne modifie rien dans Shopify</label>
</div>

<button onclick="lancer()">Lancer l'optimisation</button>

<div id="result"></div>

<script>
async function lancer() {{
  const pid   = document.getElementById('pid').value.trim();
  const shop  = document.getElementById('shop').value.trim();
  const fc    = document.getElementById('force_col').value.trim();
  const te    = document.getElementById('tags_extra').value.trim();
  const dry   = document.getElementById('dry').checked;

  if (!pid) {{
    alert('ID produit obligatoire.');
    return;
  }}

  const div = document.getElementById('result');
  div.style.display = 'block';
  div.innerHTML = '⏳ Optimisation en cours...';

  let url = `/optimize-product?id=${{pid}}&shop=${{shop}}&dry=${{dry}}`;
  if (fc)  url += `&force_collection=${{encodeURIComponent(fc)}}`;
  if (te)  url += `&tags_extra=${{encodeURIComponent(te)}}`;

  try {{
    const res  = await fetch(url);
    const data = await res.json();
    const ok   = data.statut === 'appliqué' || data.statut === 'simulation';
    div.innerHTML = (ok ? '<span class="tag-ok">✅ ' : '<span class="tag-err">❌ ') +
      (data.statut || 'Erreur') + '</span>\n\n' + JSON.stringify(data, null, 2);
  }} catch(e) {{
    div.innerHTML = '<span class="tag-err">❌ Erreur réseau</span>\n' + e;
  }}
}}
</script>
</body>
</html>"""
    return html


# ─── NOUVELLES ROUTES — OPTIMISATION FICHES PRODUITS ───────────────────────────

@app.route("/optimize-product")
def optimize_product():
    token = SHOPIFY_TOKEN
    shop            = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    pid             = request.args.get("id", "")
    dry             = request.args.get("dry", "true") == "true"
    force_collection = request.args.get("force_collection", "").strip()  # nom ou handle de collection à forcer
    tags_extra      = request.args.get("tags_extra", "").strip()         # tags supplémentaires à forcer

    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500
    if not pid:
        return jsonify({"error": "ID produit manquant"}), 400

    res = requests.get(
        f"https://{shop}/admin/api/2026-04/products/{pid}.json",
        headers={"X-Shopify-Access-Token": token})
    product = res.json().get("product", {})
    if not product:
        return jsonify({"error": "Produit introuvable"}), 404

    titre_orig = product.get("title", "")

    # Nettoyer les variants AliExpress (Ships From, China Mainland, etc.)
    variants_bruts = product.get("variants", [])
    variants_filtres = filtrer_variants_aliexpress(variants_bruts, token, shop, pid)
    product["variants"] = variants_filtres

    fiche, err = optimiser_fiche_complete(product)
    if err:
        return jsonify({"error": err, "id": pid, "titre_original": titre_orig}), 500

    result = {
        "id": pid,
        "titre_original": titre_orig,
        "dry_run": dry,
        "fiche_generee": fiche
    }

    if not dry:
        updates = {"id": pid}
        if fiche.get("titre_fr"):
            updates["title"] = fiche["titre_fr"]
        if fiche.get("description_html"):
            updates["body_html"] = fiche["description_html"]
        if fiche.get("tags_fr"):
            tags_nouveaux = fiche["tags_fr"]
            if "handle-fr-set" in product.get("tags", ""):
                tags_nouveaux = tags_nouveaux + ", handle-fr-set"
            updates["tags"] = tags_nouveaux
        if fiche.get("meta_title"):
            updates["metafields_global_title_tag"] = fiche["meta_title"]
        if fiche.get("meta_description"):
            updates["metafields_global_description_tag"] = fiche["meta_description"]
        # Calcul prix : (prix_aliexpress × 2.5) + 2€
        variants_orig = product.get("variants", [])
        new_variants_prix = []
        for v in variants_orig:
            nouveau_prix = calculer_prix(v.get("price", 0))
            if nouveau_prix:
                new_variants_prix.append({"id": v["id"], "price": str(nouveau_prix), "compare_at_price": ""})
        if new_variants_prix:
            updates["variants"] = new_variants_prix
        # Publier (brouillon → actif)
        # Bloquer si quantité incertaine
        if fiche.get("quantite_incertaine"):
            updates["status"] = "draft"
            alerte = fiche.get("alerte_quantite", "Quantité à vérifier")
            updates["body_html"] = f'<p style="background:#FFF3CD;padding:12px;border-left:4px solid #FFC107;"><strong>⚠️ Quantité à vérifier avant publication :</strong> {alerte}</p>' + updates.get("body_html", "")
            result["alerte_quantite"] = alerte
            result["statut"] = "brouillon — quantité à vérifier"
        else:
            updates["status"] = "active"
            updates["published_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        requests.put(
            f"https://{shop}/admin/api/2026-04/products/{pid}.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json={"product": updates})
        variants_traduits = fiche.get("variants_traduits", [])
        variants_orig = product.get("variants", [])
        dico_all = {**COULEURS, **TAILLES}
        # Créer un index des traductions Claude par valeur originale
        trad_index = {vt.get("original","").lower(): vt.get("traduit","") for vt in variants_traduits}
        for i, v in enumerate(variants_orig):
            updates_v = {"id": v["id"]}
            for opt_key in ["option1", "option2", "option3"]:
                val = (v.get(opt_key) or "").strip()
                if not val:
                    continue
                # 1. Chercher dans l'index Claude
                trad = trad_index.get(val.lower(), "")
                # 2. Si pas trouvé, traduire directement avec dictionnaire
                if not trad:
                    trad = traduire_valeur(val, dico_all)
                if trad and trad != val:
                    updates_v[opt_key] = trad
            if len(updates_v) > 1:
                requests.put(
                    f"https://{shop}/admin/api/2026-04/variants/{v['id']}.json",
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                    json={"variant": updates_v})
                time.sleep(0.3)
        # Traduire le nom de l'option (Color → Couleur, Size → Taille, etc.)
        noms_options = NOMS_OPTIONS
        res_options = requests.get(
            f"https://{shop}/admin/api/2026-04/products/{pid}.json",
            headers={"X-Shopify-Access-Token": token})
        prod_data = res_options.json().get("product", {})
        options = prod_data.get("options", [])
        # Utiliser les traductions de Claude si disponibles, sinon dictionnaire
        options_claude = fiche.get("options_noms_traduits", {}) if fiche else {}
        options_modifiees = []
        for opt in options:
            nom_orig = opt.get("name","")
            nom_lower = nom_orig.lower()
            # Priorité : traduction Claude → dictionnaire → original
            if nom_orig in options_claude:
                nouveau_nom = options_claude[nom_orig]
            elif nom_orig.lower() in {k.lower(): v for k,v in options_claude.items()}:
                nouveau_nom = next(v for k,v in options_claude.items() if k.lower() == nom_lower)
            else:
                nouveau_nom = noms_options.get(nom_lower, nom_orig)
            options_modifiees.append({"id": opt["id"], "name": nouveau_nom})
        if options_modifiees:
            requests.put(
                f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                json={"product": {"id": int(pid), "options": options_modifiees}})
            time.sleep(0.2)
        couleur    = fiche.get("couleur", "")
        matiere    = fiche.get("matiere", "")
        age_group  = fiche.get("age_group", "adult")
        added_mf   = construire_metafields(matiere, couleur, token, shop, pid, age_group, titre_orig, fiche.get("tags_fr",""), genre_claude=fiche.get("gender","Unisex"))
        result["metafields_ajoutes"] = added_mf
        # Handle/URL : seulement à la première optimisation (protège les URLs indexées par Google)
        handle_deja_fr = "handle-fr-set" in product.get("tags", "")
        if fiche.get("titre_fr") and not handle_deja_fr:
            new_handle = mettre_a_jour_handle(token, shop, pid, fiche["titre_fr"])
            result["handle"] = new_handle
            # Marquer le handle comme protégé pour les prochaines optimisations
            tags_actuels = updates.get("tags", product.get("tags", ""))
            if "handle-fr-set" not in tags_actuels:
                requests.put(
                    f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                    json={"product": {"id": int(pid), "tags": tags_actuels + ", handle-fr-set"}})
        elif fiche.get("titre_fr"):
            result["handle"] = product.get("handle", "")
            result["handle_protege"] = True
        # Collection : force_collection prioritaire sur détection automatique
        collections = get_collections(token, shop)
        noms_colls = []
        tags_menu = []
        if force_collection:
            # Cherche la collection par nom ou handle (insensible à la casse)
            fc_lower = force_collection.lower().replace("-", " ")
            coll_forcee = next(
                (c for c in collections if
                 c["title"].lower() == fc_lower or
                 c.get("handle","").lower() == force_collection.lower()),
                None)
            if coll_forcee:
                assigner_collection(token, shop, pid, coll_forcee["id"])
                noms_colls.append(coll_forcee["title"])
                result["collection_forcee"] = coll_forcee["title"]
            else:
                result["collection_forcee_erreur"] = f"Collection '{force_collection}' introuvable dans Shopify"
        else:
            colls_assignees, tags_menu = detecter_collection(
                fiche.get("titre_fr",""), fiche.get("tags_fr",""),
                fiche.get("categorie_detectee",""), collections)
            for c in colls_assignees:
                assigner_collection(token, shop, pid, c["id"])
                noms_colls.append(c["title"])
        result["collections_assignees"] = noms_colls
        # Tags : Claude + navigation + tags_extra forcés
        tags_fr_claude = fiche.get("tags_fr","")
        tags_finaux_set = set(t.strip() for t in tags_fr_claude.split(",") if t.strip())
        tags_finaux_set.update(tags_menu)
        if tags_extra:
            tags_finaux_set.update(t.strip() for t in tags_extra.split(",") if t.strip())
            result["tags_extra_ajoutes"] = tags_extra
        tous_tags = ", ".join(sorted(tags_finaux_set))
        requests.put(
            f"https://{shop}/admin/api/2026-04/products/{pid}.json",
            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
            json={"product": {"id": int(pid), "tags": tous_tags}})
        result["tags_menu_ajoutes"] = tags_menu
        # Publication sur les 3 canaux
        canaux = publier_sur_canaux(token, shop, pid)
        result["canaux_publies"] = canaux
        result["statut"] = "appliqué"
    else:
        collections = get_collections(token, shop)
        colls_assignees, tags_menu = detecter_collection(
            fiche.get("titre_fr",""), fiche.get("tags_fr",""),
            fiche.get("categorie_detectee",""), collections)
        result["collections_prevues"] = [c["title"] for c in colls_assignees]
        result["tags_menu_prevus"] = tags_menu
        # Simuler les prix
        prix_simules = []
        for v in product.get("variants", []):
            nouveau_prix = calculer_prix(v.get("price", 0))
            prix_simules.append({
                "variant": v.get("option1","") or v.get("title",""),
                "prix_dsers": v.get("price",""),
                "prix_final": str(nouveau_prix) + "€" if nouveau_prix else "erreur",
                "calcul": f"floor({float(v.get('price',0)):.2f} + 2) + 0.99"
            })
        result["prix_simules"] = prix_simules
        if fiche.get("quantite_incertaine"):
            result["alerte_quantite"] = fiche.get("alerte_quantite", "")
            result["attention"] = "⚠️ Ce produit resterait en BROUILLON — quantité à vérifier"
        result["statut"] = "simulation — aucune modification effectuée"

    return jsonify(result)


@app.route("/optimize-batch")
def optimize_batch():
    token = SHOPIFY_TOKEN
    shop    = request.args.get("shop", "ma-maison-cocoon.myshopify.com")
    filtre  = request.args.get("filter", "no-description")
    limit   = int(request.args.get("limit", "10"))
    dry              = request.args.get("dry", "true") == "true"
    actions          = request.args.get("actions", "description,variants,metafields").split(",")
    force_collection = request.args.get("force_collection", "").strip()
    tags_extra       = request.args.get("tags_extra", "").strip()

    if not token:
        return jsonify({"error": "Token non configuré — vérifier SHOPIFY_TOKEN dans Render"}), 500

    try:
        products = get_all_products(token, shop)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if filtre == "drafts":
        cibles = [p for p in products if p.get("status") == "draft"]
    elif filtre == "no-description":
        cibles = [p for p in products if len(p.get("body_html", "") or "") < 100]
    else:
        cibles = products

    total_cibles = len(cibles)
    cibles = cibles[:limit]
    resultats = []

    for product in cibles:
        pid      = str(product["id"])
        titre    = product.get("title", "")
        desc     = product.get("body_html", "") or ""
        tags     = product.get("tags", "")
        variants = product.get("variants", [])
        item     = {"id": pid, "titre": titre}

        # Nettoyer les variants AliExpress (Ships From, China Mainland, etc.)
        variants_filtres = filtrer_variants_aliexpress(variants, token, shop, pid)
        product["variants"] = variants_filtres

        # Appel Claude — fiche complète pour ce produit
        fiche, err = optimiser_fiche_complete(product)
        if err:
            item["erreur"] = err
        else:
            item["fiche_generee"] = {
                "titre_fr":        fiche.get("titre_fr", ""),
                "meta_title":      fiche.get("meta_title", ""),
                "meta_description":fiche.get("meta_description", ""),
                "tags_fr":         fiche.get("tags_fr", ""),
                "couleur":         fiche.get("couleur", ""),
                "matiere":         fiche.get("matiere", ""),
                "description_apercu": (fiche.get("description_html","")[:150] + "..."),
                "variants_traduits": fiche.get("variants_traduits", [])
            }
            if not dry and not err:
                updates = {"id": pid}
                if fiche.get("titre_fr"):        updates["title"]     = fiche["titre_fr"]
                if fiche.get("description_html"):updates["body_html"] = fiche["description_html"]
                if fiche.get("tags_fr"):
                    tags_nouveaux = fiche["tags_fr"]
                    if "handle-fr-set" in product.get("tags", ""):
                        tags_nouveaux = tags_nouveaux + ", handle-fr-set"
                    updates["tags"] = tags_nouveaux
                if fiche.get("meta_title"):
                    updates["metafields_global_title_tag"]       = fiche["meta_title"]
                if fiche.get("meta_description"):
                    updates["metafields_global_description_tag"] = fiche["meta_description"]
                # Prix : (prix_aliexpress × 2.5) + 2€
                new_variants_prix = []
                for v in variants:
                    nouveau_prix = calculer_prix(v.get("price", 0))
                    if nouveau_prix:
                        new_variants_prix.append({"id": v["id"], "price": str(nouveau_prix), "compare_at_price": ""})
                if new_variants_prix:
                    updates["variants"] = new_variants_prix
                # Publier
                # Bloquer si quantité incertaine
                if fiche.get("quantite_incertaine"):
                    updates["status"] = "draft"
                    alerte = fiche.get("alerte_quantite", "Quantité à vérifier")
                    updates["body_html"] = f'<p style="background:#FFF3CD;padding:12px;border-left:4px solid #FFC107;"><strong>⚠️ Quantité à vérifier avant publication :</strong> {alerte}</p>' + updates.get("body_html", "")
                    item["alerte_quantite"] = alerte
                    item["statut"] = "brouillon — quantité à vérifier"
                else:
                    updates["status"] = "active"
                    updates["published_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                requests.put(
                    f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                    json={"product": updates})
                # Variants — traduire option1, option2, option3
                variants_traduits = fiche.get("variants_traduits", [])
                dico_all = {**COULEURS, **TAILLES}
                trad_index = {vt.get("original","").lower(): vt.get("traduit","") for vt in variants_traduits}
                for i, v in enumerate(variants):
                    updates_v = {"id": v["id"]}
                    for opt_key in ["option1", "option2", "option3"]:
                        val = (v.get(opt_key) or "").strip()
                        if not val:
                            continue
                        trad = trad_index.get(val.lower(), "")
                        if not trad:
                            trad = traduire_valeur(val, dico_all)
                        if trad and trad != val:
                            updates_v[opt_key] = trad
                    if len(updates_v) > 1:
                        requests.put(
                            f"https://{shop}/admin/api/2026-04/variants/{v['id']}.json",
                            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                            json={"variant": updates_v})
                        time.sleep(0.3)
                # Traduire nom option (Color → Couleur etc.)
                noms_options = NOMS_OPTIONS
                res_opt = requests.get(
                    f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                    headers={"X-Shopify-Access-Token": token})
                options = res_opt.json().get("product", {}).get("options", [])
                options_claude = fiche.get("options_noms_traduits", {})
                options_modifiees = []
                for opt in options:
                    nom_orig = opt.get("name","")
                    nom_lower = nom_orig.lower()
                    if nom_orig in options_claude:
                        nouveau_nom = options_claude[nom_orig]
                    elif any(k.lower() == nom_lower for k in options_claude):
                        nouveau_nom = next(v for k,v in options_claude.items() if k.lower() == nom_lower)
                    else:
                        nouveau_nom = noms_options.get(nom_lower, nom_orig)
                    options_modifiees.append({"id": opt["id"], "name": nouveau_nom})
                if options_modifiees:
                    requests.put(
                        f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                        json={"product": {"id": int(pid), "options": options_modifiees}})
                    time.sleep(0.2)
                # Métadonnées
                construire_metafields(fiche.get("matiere",""), fiche.get("couleur",""), token, shop, pid, fiche.get("age_group","adult"), titre, fiche.get("tags_fr",""), genre_claude=fiche.get("gender","Unisex"))
                # Handle/URL : seulement à la première optimisation (protège les URLs indexées par Google)
                handle_deja_fr = "handle-fr-set" in product.get("tags", "")
                if fiche.get("titre_fr") and not handle_deja_fr:
                    mettre_a_jour_handle(token, shop, pid, fiche["titre_fr"])
                    # Marquer le handle comme protégé pour les prochaines optimisations
                    tags_actuels = updates.get("tags", product.get("tags", ""))
                    if "handle-fr-set" not in tags_actuels:
                        requests.put(
                            f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                            headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                            json={"product": {"id": int(pid), "tags": tags_actuels + ", handle-fr-set"}})
                    item["handle_nouveau"] = True
                else:
                    item["handle_protege"] = True
                collections = get_collections(token, shop)
                noms_colls = []
                tags_menu = []
                if force_collection:
                    fc_lower = force_collection.lower().replace("-", " ")
                    coll_forcee = next(
                        (c for c in collections if
                         c["title"].lower() == fc_lower or
                         c.get("handle","").lower() == force_collection.lower()),
                        None)
                    if coll_forcee:
                        assigner_collection(token, shop, pid, coll_forcee["id"])
                        noms_colls.append(coll_forcee["title"])
                else:
                    colls_assignees, tags_menu = detecter_collection(
                        fiche.get("titre_fr",""), fiche.get("tags_fr",""),
                        fiche.get("categorie_detectee",""), collections)
                    for c in colls_assignees:
                        assigner_collection(token, shop, pid, c["id"])
                        noms_colls.append(c["title"])
                item["collections_assignees"] = noms_colls
                tags_fr_claude = fiche.get("tags_fr","")
                tags_finaux_set = set(t.strip() for t in tags_fr_claude.split(",") if t.strip())
                tags_finaux_set.update(tags_menu)
                if tags_extra:
                    tags_finaux_set.update(t.strip() for t in tags_extra.split(",") if t.strip())
                tous_tags = ", ".join(sorted(tags_finaux_set))
                requests.put(
                    f"https://{shop}/admin/api/2026-04/products/{pid}.json",
                    headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                    json={"product": {"id": int(pid), "tags": tous_tags}})
                item["tags_menu_ajoutes"] = tags_menu
                canaux = publier_sur_canaux(token, shop, pid)
                item["canaux_publies"] = canaux
                item["statut"] = "appliqué"
            else:
                item["statut"] = "simulation"

        resultats.append(item)
        time.sleep(0.5)

    return jsonify({
        "action": "optimize-batch",
        "filtre": filtre,
        "dry_run": dry,
        "total_catalogue": len(products),
        "total_cibles": total_cibles,
        "traites": len(resultats),
        "resultats": resultats
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
