import mysql.connector
from flask import Flask, request, render_template, flash, redirect, url_for, session, jsonify
import urllib.request
import urllib.parse
import urllib.error
import json
import base64
from datetime import datetime
import ssl

app = Flask(__name__)
app.secret_key = "nejaky_tajny_kluc"

mydb = mysql.connector.connect(
    host="localhost",
    user="root", #podla pc na ktorom som robila
    password="12345",
    #user = "andrejka",
    #password="12345678",
    database="maturitna_praca"
)
mycursor = mydb.cursor(buffered=True)
# zmena pagu

@app.route('/homepage')
def homepage():
    return render_template("home.html")

@app.route('/signup')
def signup():
    return render_template("signup.html")

@app.route('/decky')
def decky():
    return render_template("decky.html")

# registrácia a prihlásenie page logika

@app.route('/add_user', methods=["GET", "POST"])
def add_user():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        with open("static/obrazky/default.jpg", "rb") as f:
            default_data = f.read()

        try:
            sql = "INSERT INTO users (username, heslo, email, picture) VALUES (%s, %s, %s, %s)"
            values = (username, password, email, default_data)
            mycursor.execute(sql, values)
            mydb.commit()

            flash("Registrácia prebehla úspešne!", "success")
            return redirect(url_for('forum'))

        except mysql.connector.IntegrityError:
            flash("Používateľ už existuje!", "error")
            return redirect(url_for('signup'))

    return render_template("signup.html")

@app.route('/login', methods=["GET", "POST"])
@app.route('/login_user', methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        sql = "SELECT username FROM users WHERE (username=%s OR email=%s) AND heslo=%s"
        values = (username, username, password)

        mycursor.execute(sql, values)
        user = mycursor.fetchone()

        if user:
            session["username"] = user[0]
            return redirect(url_for('forum'))
        else:
            flash("Nesprávne meno alebo heslo!", "error")
            return render_template("login.html")

    # Ak používateľ len otvorí stránku (metóda GET), zobrazí sa mu prihlasovací formulár
    return render_template("login.html")

@app.route('/logout', methods = ["GET","POST"])
def logout():
    session.pop('username', None)
    flash("Úspešne si sa odhlásila.", "success")
    return redirect(url_for('forum'))

@app.context_processor
def inject_user():
    profile_pic = None
    logged_in = False

    if "username" in session:
        logged_in = True
        sql = "SELECT picture FROM users WHERE username=%s"
        mycursor.execute(sql, (session["username"],))
        user_data = mycursor.fetchone()

        if user_data and user_data[0]:
            profile_pic = base64.b64encode(user_data[0]).decode("utf-8")

    return dict(
        logged_in=logged_in,
        profile_pic=profile_pic
    )


# --- ÚPRAVA PROFILU ---

@app.route('/editor')
def editor():
    if "username" not in session:
        flash("Pre úpravu profilu sa musíš prihlásiť.", "error")
        return redirect(url_for('login'))
        
    return render_template("editor.html")

@app.route('/update_profile_pic', methods=["POST"])
def update_profile_pic():
    if "username" not in session:
        return redirect(url_for('login'))

    file = request.files.get("profile-pic")

    if file and file.filename != '':
        file_data = file.read()
        sql = "UPDATE users SET picture = %s WHERE username = %s"
        values = (file_data, session["username"])
        
        mycursor.execute(sql, values)
        mydb.commit()

        flash("Profilová fotka bola úspešne zmenená!", "success")
    else:
        flash("Nevybrala si žiadny súbor.", "error")

    return redirect(url_for('editor'))


# --- FÓRUM (PRÍSPEVKY A KOMENTÁRE) ---

@app.route('/forum')
def forum():
    # Vytiahneme všetky príspevky z databázy (najnovšie prvé)
    mycursor.execute("SELECT idposty, nazov, obsah, plikes, pdatum, users_username FROM posty ORDER BY pdatum DESC")
    posts_data = mycursor.fetchall()
    
    posts = []
    for p in posts_data:
        post = {
            'idposty': p[0],
            'nazov': p[1],
            'obsah': p[2],
            'plikes': p[3],
            'pdatum': p[4],
            'autor': p[5],
            'komentare': []
        }
        
        # Vytiahneme komentáre priradené k tomuto príspevku
        # Vytiahneme komentáre priradené k tomuto príspevku (PRIDANÉ idkomenty)
        sql_komenty = "SELECT idkomenty, users_username, kobsah, kdatum FROM komenty WHERE posty_idposty = %s ORDER BY kdatum ASC"
        mycursor.execute(sql_komenty, (post['idposty'],))
        komenty_data = mycursor.fetchall()
        
        for k in komenty_data:
            post['komentare'].append({
                'idkomenty': k[0], # Uložíme si ID komentára pre funkciu vymazania
                'autor': k[1],
                'obsah': k[2],
                'datum': k[3]
            })
            
        posts.append(post)

    return render_template("forum.html", posts=posts)


@app.route('/pridaj_prispevok', methods=["POST"])
def pridaj_prispevok():
    if "username" not in session:
        flash("Pre pridanie príspevku sa musíš prihlásiť.", "error")
        return redirect(url_for('login'))

    nazov = request.form.get("nazov")
    obsah = request.form.get("obsah")
    autor = session["username"]

    aktualny_cas = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    sql = "INSERT INTO posty (nazov, obsah, plikes, users_username, pdatum) VALUES (%s, %s, 0, %s, %s)"
    
    
    mycursor.execute(sql, (nazov, obsah, autor, aktualny_cas))
    mydb.commit()

    flash("Príspevok bol úspešne pridaný!", "success")
    return redirect(url_for('forum'))


@app.route('/pridaj_komentar/<int:idposty>', methods=["POST"])
def pridaj_komentar(idposty):
    if "username" not in session:
        flash("Pre pridanie komentára sa musíš prihlásiť.", "error")
        return redirect(url_for('login'))

    kobsah = request.form.get("kobsah")
    autor = session["username"]

    aktualny_cas = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # ZMENA: Do príkazu INSERT sme pridali stĺpec 'kdatum' a ďalšie '%s'
    sql = "INSERT INTO komenty (kobsah, posty_idposty, users_username, kdatum) VALUES (%s, %s, %s, %s)"
    
    # ZMENA: Posielame 'aktualny_cas' ako štvrtú hodnotu
    mycursor.execute(sql, (kobsah, idposty, autor, aktualny_cas))
    mydb.commit()

    return redirect(url_for('forum'))

@app.route('/vymaz_prispevok/<int:idposty>', methods=["POST"])
def vymaz_prispevok(idposty):
    # Overíme, či je používateľ prihlásený
    if "username" not in session:
        flash("Na vymazanie príspevku sa musíš prihlásiť.", "error")
        return redirect(url_for('login'))

    aktualny_pouzivatel = session["username"]

    # Zistíme, kto je autorom tohto príspevku
    mycursor.execute("SELECT users_username FROM posty WHERE idposty = %s", (idposty,))
    post = mycursor.fetchone()

    # Ak príspevok existuje a prihlásený používateľ je jeho autorom
    if post and (post[0] == aktualny_pouzivatel or aktualny_pouzivatel == "admin"):
        # NAJPRV vymažeme všetky komentáre, ktoré patria k tomuto príspevku
        mycursor.execute("DELETE FROM komenty WHERE posty_idposty = %s", (idposty,))
        
        # POTOM vymažeme samotný príspevok
        mycursor.execute("DELETE FROM posty WHERE idposty = %s", (idposty,))
        
        mydb.commit()
        flash("Príspevok bol úspešne vymazaný.", "success")
    else:
        # Ak sa niekto snaží vymazať cudzí príspevok
        flash("Tento príspevok nemôžeš vymazať, pretože nie si jeho autorom.", "error")

    # Po úspešnom vymazaní (alebo chybe) obnovíme stránku fóra
    return redirect(url_for('forum'))


#logika hlaovania T-T
@app.route('/hlasuj/<int:idposty>/<akcia>', methods=["POST"])
def hlasuj(idposty, akcia):
    
    if "username" not in session:
        flash("Pre hlasovanie sa musíš prihlásiť.", "error")
        return redirect(url_for('forum'))

    aktualny_pouzivatel = session["username"]

    mycursor.execute("SELECT users_username FROM posty WHERE idposty = %s", (idposty,))
    post = mycursor.fetchone()
    
    if post and post[0] == aktualny_pouzivatel:
        flash("Nemôžeš hlasovať za svoj vlastný príspevok!", "error")
        return redirect(url_for('forum'))


    sql_kontrola = "SELECT hlasoval FROM hlasovania WHERE posty_idposty = %s AND users_username = %s"
    mycursor.execute(sql_kontrola, (idposty, aktualny_pouzivatel))
    uz_hlasoval = mycursor.fetchone()
    if not uz_hlasoval :
        dotaz = "Insert into hlasovania (posty_idposty, users_username, hlasoval) values (%s , %s, 0) "
        mycursor.execute(dotaz, (idposty, aktualny_pouzivatel))
        mydb.commit()
        sql_kontrola = "SELECT hlasoval FROM hlasovania WHERE posty_idposty = %s AND users_username = %s"
        mycursor.execute(sql_kontrola, (idposty, aktualny_pouzivatel))
        uz_hlasoval = mycursor.fetchone()
        
        
    xu = True
    x = True
    if uz_hlasoval[0] == 1:
        sql_update2 = "UPDATE posty SET plikes = plikes - 1 WHERE idposty = %s"
    elif uz_hlasoval[0] == -1:
        sql_update2 = "UPDATE posty SET plikes = plikes + 1 WHERE idposty = %s"
    else:
        x = False
        
    if akcia == "up" and uz_hlasoval[0] == -1:
        sql_update = "UPDATE posty SET plikes = plikes + 1 WHERE idposty = %s"
        hlasoval_update = "Update hlasovania set hlasoval = 1 WHERE posty_idposty = ( select idposty from posty where idposty = %s) and users_username = %s"
    elif akcia == "down" and uz_hlasoval[0] == 1:
        sql_update = "UPDATE posty SET plikes = plikes - 1 WHERE idposty = %s"
        hlasoval_update = "Update hlasovania set hlasoval = -1 WHERE posty_idposty = ( select idposty from posty where idposty = %s) and users_username = %s"
    else:
        if akcia == "up" :
            if uz_hlasoval[0] ==1 :
                hlasoval_update = "Update hlasovania set hlasoval = 0 WHERE posty_idposty = ( select idposty from posty where idposty = %s) and users_username = %s "
                xu = False
            else:
                sql_update = "UPDATE posty SET plikes = plikes + 1 WHERE idposty = %s"
                hlasoval_update = "Update hlasovania set hlasoval = 1 WHERE posty_idposty = ( select idposty from posty where idposty = %s) and users_username = %s "
        elif akcia == "down":
            if uz_hlasoval[0] ==-1 :
                hlasoval_update = "Update hlasovania set hlasoval = 0 WHERE posty_idposty = ( select idposty from posty where idposty = %s) and users_username = %s "
                xu = False
            else:
                sql_update = "UPDATE posty SET plikes = plikes - 1 WHERE idposty = %s"
                hlasoval_update = "Update hlasovania set hlasoval = -1 WHERE posty_idposty = ( select idposty from posty where idposty = %s) and users_username = %s"
        else: return redirect(url_for('forum'))

    sql_insert = "INSERT INTO hlasovania (posty_idposty, users_username) VALUES (%s, %s)"
    
    if x: mycursor.execute(sql_update2, (idposty,))
    if xu:mycursor.execute(sql_update, (idposty,))
    mycursor.execute(hlasoval_update, (idposty, aktualny_pouzivatel))
    mycursor.execute(sql_insert, (idposty, aktualny_pouzivatel))
    mydb.commit()

    return redirect(url_for('forum'))

@app.route('/vymaz_komentar/<int:idkomenty>', methods=["POST"])
def vymaz_komentar(idkomenty):
    # Overíme, či je používateľ vôbec prihlásený
    if "username" not in session:
        flash("Na vymazanie komentára sa musíš prihlásiť.", "error")
        return redirect(url_for('forum'))

    aktualny_pouzivatel = session["username"]

    # Zistíme, kto je autorom tohto konkrétneho komentára
    mycursor.execute("SELECT users_username FROM komenty WHERE idkomenty = %s", (idkomenty,))
    koment = mycursor.fetchone()

    # Ak komentár existuje a prihlásený používateľ je jeho autorom
    if koment and (koment[0] == aktualny_pouzivatel or aktualny_pouzivatel == "admin"):
        mycursor.execute("DELETE FROM komenty WHERE idkomenty = %s", (idkomenty,))
        mydb.commit()
        flash("Komentár bol úspešne vymazaný.", "success")
    else:
        # Ak sa niekto snaží vymazať cudzí komentár
        flash("Tento komentár nemôžeš vymazať, pretože nie si jeho autorom.", "error")

    return redirect(url_for('forum'))

KATALOG_CACHE = None

@app.route('/kartygal')
def kartygal():
    return render_template("kartygal.html")

@app.route('/api/karty')
def api_karty():
    global KATALOG_CACHE
    query = request.args.get('q', '').strip().lower()

    try:
        if KATALOG_CACHE is None:
            url = "https://openrift.app/api/v1/catalog?langs=EN"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Riftout-MaturitnaPraca/1.0 (student-project)",
                    "Accept": "application/json"
                }
            )
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=20, context=ctx) as response:
                raw_data = json.loads(response.read().decode('utf-8'))

            # 1. Zozbierame všetky unikátne karty (game objects) a všetky tlače (printings)
            all_cards = []
            all_printings = []

            def scan_catalog(node):
                if isinstance(node, dict):
                    # Objekt je printing (tlač), ak má imageId
                    img_id = node.get("imageId") if node.get("imageId") is not None else node.get("image_id")
                    if img_id is not None and str(img_id) != "":
                        all_printings.append(node)
                    # Objekt je karta, ak má 'name' a typické atribúty karty
                    elif "name" in node and any(k in node for k in ("domains", "energy", "printedRulesText", "tags", "slug", "type", "cardType")):
                        all_cards.append(node)

                    for val in node.values():
                        scan_catalog(val)
                elif isinstance(node, list):
                    for item in node:
                        scan_catalog(item)

            scan_catalog(raw_data)

            # 2. Priradíme ku každému ID karty iba JEDEN obrázok (uprednostníme základnú ne-promo verziu)
            printing_by_card_key = {}
            for p in all_printings:
                img_id = str(p.get("imageId") or p.get("image_id"))
                # Skontrolujeme, či nejde o promo (ak má printing príznak promo)
                is_promo = "promo" in str(p.get("setId", "")).lower() or "promo" in str(p.get("publicCode", "")).lower() or bool(p.get("isPromo"))

                for key in ("cardId", "card_id", "cardSlug", "card_slug", "id", "slug", "name"):
                    val = p.get(key)
                    if val is not None and str(val) != "":
                        k_str = str(val).lower()
                        # Uložíme prvú verziu, alebo prepíšeme promo verziu bežnou verziou
                        if k_str not in printing_by_card_key or (printing_by_card_key[k_str]["is_promo"] and not is_promo):
                            printing_by_card_key[k_str] = {
                                "imageId": img_id,
                                "publicCode": str(p.get("publicCode") or ""),
                                "is_promo": is_promo
                            }

            unique_cards = []
            seen_card_names = set()

            # 3. Prejdeme unikátne karty a ku každej priradíme práve 1 obrázok
            for c in all_cards:
                name = str(c.get("name") or "").strip()
                if not name:
                    continue

                # Kľúč pre unikátnosť karty (podľa mena karty, aby sa každá karta zobrazila len raz)
                name_key = name.lower()
                if name_key in seen_card_names:
                    continue

                matched_print = None
                # Skúsime spárovať cez vnorený zoznam printings na karte, ak existuje
                if isinstance(c.get("printings"), list) and len(c["printings"]) > 0:
                    for cp in c["printings"]:
                        if isinstance(cp, dict) and (cp.get("imageId") or cp.get("image_id")):
                            matched_print = {
                                "imageId": str(cp.get("imageId") or cp.get("image_id")),
                                "publicCode": str(cp.get("publicCode") or c.get("publicCode") or "")
                            }
                            break

                # Ak karta nemá vnorený printing, spárujeme ju cez jej ID/slug/meno
                if not matched_print:
                    for key in ("id", "cardId", "slug", "name", "publicCode"):
                        val = c.get(key)
                        if val is not None and str(val).lower() in printing_by_card_key:
                            matched_print = printing_by_card_key[str(val).lower()]
                            break

                # Ak má samotný objekt karty imageId
                if not matched_print and (c.get("imageId") or c.get("image_id")):
                    matched_print = {
                        "imageId": str(c.get("imageId") or c.get("image_id")),
                        "publicCode": str(c.get("publicCode") or "")
                    }

                if not matched_print:
                    continue

                seen_card_names.add(name_key)
                img_id = matched_print["imageId"]
                code = matched_print["publicCode"] or str(c.get("publicCode") or "")
                domains = " ".join(c.get("domains", [])) if isinstance(c.get("domains"), list) else str(c.get("domains") or "")
                tags = " ".join(c.get("tags", [])) if isinstance(c.get("tags"), list) else str(c.get("tags") or "")
                rules = str(c.get("printedRulesText") or "")

                unique_cards.append({
                    "name": name,
                    "publicCode": code,
                    "searchText": f"{name} {code} {domains} {tags} {rules} {img_id}".lower(),
                    "imageUrl": f"https://openrift.app/media/cards/{img_id}-240w.webp"
                })

            # Fallback: ak sú v JSONe iba printings, odfiltrujeme duplicity podľa cardId / mena
            if len(unique_cards) == 0:
                seen_keys = set()
                for p in all_printings:
                    img_id = str(p.get("imageId") or p.get("image_id"))
                    unique_key = str(p.get("cardId") or p.get("cardSlug") or p.get("name") or img_id).lower()
                    if unique_key in seen_keys:
                        continue
                    seen_keys.add(unique_key)
                    name = str(p.get("name") or p.get("cardSlug") or p.get("publicCode") or img_id)
                    code = str(p.get("publicCode") or "")
                    unique_cards.append({
                        "name": name,
                        "publicCode": code,
                        "searchText": f"{name} {code} {unique_key} {img_id}".lower(),
                        "imageUrl": f"https://openrift.app/media/cards/{img_id}-240w.webp"
                    })

            # Zoradíme karty abecedne podľa názvu
            unique_cards.sort(key=lambda x: x["name"].lower())
            KATALOG_CACHE = unique_cards

        if query:
            filtered = [c for c in KATALOG_CACHE if query in c["searchText"]]
        else:
            filtered = KATALOG_CACHE

        return jsonify({"cards": filtered}), 200

    except Exception as e:
        print("Chyba v /api/karty:", e)
        return jsonify({"error": str(e)}), 500

# --- LOBBY A HRANIE (/play.page) ---

@app.route('/play.page')
def playpage():
    # Načítame všetky dostupné decky (spolu s menom legendy z tabuľky legends)
    # Obaja hráči si tak môžu vybrať ktorýkoľvek deck (aj ten istý)
    sql_decks = """
        SELECT d.iddeck, d.users_username, l.meno, l.farba1, l.farba2
        FROM deck d
        LEFT JOIN legends l ON d.legends_idlegends = l.idlegends
        ORDER BY d.iddeck DESC
    """
    mycursor.execute(sql_decks)
    decks_data = mycursor.fetchall()

    decks = []
    for d in decks_data:
        decks.append({
            'iddeck': d[0],
            'autor': d[1],
            'legenda': d[2] if d[2] else f"Deck #{d[0]}",
            'farba1': d[3] or "",
            'farba2': d[4] or ""
        })

    # Načítame všetky aktívne lobby (čakajúce aj prebiehajúce)
    sql_lobbies = """
        SELECT l.idlobby, l.player1_username, l.player1_iddeck,
               l.player2_username, l.player2_iddeck, l.stav, l.vytvorenie,
               leg1.meno AS p1_legenda, leg2.meno AS p2_legenda
        FROM lobby l
        LEFT JOIN deck d1 ON l.player1_iddeck = d1.iddeck
        LEFT JOIN legends leg1 ON d1.legends_idlegends = leg1.idlegends
        LEFT JOIN deck d2 ON l.player2_iddeck = d2.iddeck
        LEFT JOIN legends leg2 ON d2.legends_idlegends = leg2.idlegends
        ORDER BY l.vytvorenie DESC
    """
    mycursor.execute(sql_lobbies)
    lobbies_data = mycursor.fetchall()

    lobbies = []
    for row in lobbies_data:
        lobbies.append({
            'idlobby': row[0],
            'player1': row[1],
            'player1_iddeck': row[2],
            'player2': row[3],
            'player2_iddeck': row[4],
            'stav': row[5],
            'vytvorenie': row[6],
            'p1_legenda': row[7] if row[7] else f"Deck #{row[2]}",
            'p2_legenda': row[8] if row[8] else (f"Deck #{row[4]}" if row[4] else None)
        })

    return render_template("playpage.html", decks=decks, lobbies=lobbies)


@app.route('/create_lobby', methods=["POST"])
def create_lobby():
    if "username" not in session:
        flash("Pre vytvorenie lobby sa musíš prihlásiť.", "error")
        return redirect(url_for('login'))

    iddeck = request.form.get("iddeck")
    if not iddeck:
        flash("Musíš si vybrať deck!", "error")
        return redirect(url_for('playpage'))

    aktualny_cas = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sql = """
        INSERT INTO lobby (player1_username, player1_iddeck, stav, vytvorenie)
        VALUES (%s, %s, 'waiting', %s)
    """
    mycursor.execute(sql, (session["username"], iddeck, aktualny_cas))
    mydb.commit()

    flash("Lobby bolo úspešne vytvorené! Čaká sa na druhého hráča.", "success")
    return redirect(url_for('playpage'))


@app.route('/join_lobby/<int:idlobby>', methods=["POST"])
def join_lobby(idlobby):
    if "username" not in session:
        flash("Pre pripojenie do lobby sa musíš prihlásiť.", "error")
        return redirect(url_for('login'))

    iddeck = request.form.get("iddeck")
    if not iddeck:
        flash("Musíš si vybrať deck!", "error")
        return redirect(url_for('playpage'))

    aktualny_hrac = session["username"]

    mycursor.execute("SELECT player1_username, player2_username FROM lobby WHERE idlobby = %s", (idlobby,))
    lobby_row = mycursor.fetchone()

    if not lobby_row:
        flash("Lobby neexistuje.", "error")
        return redirect(url_for('playpage'))

    if lobby_row[0] == aktualny_hrac:
        flash("Nemôžeš sa pripojiť do vlastného lobby ako druhý hráč!", "error")
        return redirect(url_for('playpage'))

    if lobby_row[1] is not None:
        flash("Toto lobby je už plné.", "error")
        return redirect(url_for('playpage'))

    sql = """
        UPDATE lobby
        SET player2_username = %s, player2_iddeck = %s, stav = 'playing'
        WHERE idlobby = %s
    """
    mycursor.execute(sql, (aktualny_hrac, iddeck, idlobby))
    mydb.commit()

    flash("Úspešne si sa pripojila do lobby! Hra začína.", "success")
    return redirect(url_for('playpage'))


@app.route('/delete_lobby/<int:idlobby>', methods=["POST"])
def delete_lobby(idlobby):
    if "username" not in session:
        return redirect(url_for('login'))

    aktualny_hrac = session["username"]
    mycursor.execute("SELECT player1_username, player2_username FROM lobby WHERE idlobby = %s", (idlobby,))
    lobby_row = mycursor.fetchone()

    if lobby_row and (aktualny_hrac in (lobby_row[0], lobby_row[1]) or aktualny_hrac == "admin"):
        mycursor.execute("DELETE FROM lobby WHERE idlobby = %s", (idlobby,))
        mydb.commit()
        flash("Lobby bolo ukončené a vymazané.", "success")

    return redirect(url_for('playpage'))

# --- SPUSTENIE SERVERA (MUSÍ BYŤ ÚPLNE NA KONCI) ---
if __name__ == "__main__":
    app.run(debug=True)