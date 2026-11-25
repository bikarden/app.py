"""
diagnostic_wifi.py - Trouve ce qui ralentit ton wifi.

Comment l'utiliser :
    1. Connecte ton ordinateur à ton wifi (pas au câble).
    2. Ouvre un terminal dans le dossier de ce fichier.
    3. Tape :  python diagnostic_wifi.py
       (sur Mac/Linux, parfois : python3 diagnostic_wifi.py)

Le programme ne modifie RIEN sur ton routeur et ne demande aucun mot de passe.
Il fait seulement des mesures (comme un thermomètre) et te donne un verdict.

Fonctionne sur Windows, Mac et Linux. Aucune installation nécessaire.
"""

import platform  # pour savoir si on est sur Windows, Mac ou Linux
import re  # pour chercher des nombres dans du texte
import socket  # pour mesurer la vitesse du DNS
import statistics  # pour calculer des moyennes
import subprocess  # pour lancer des commandes du système (ping, etc.)
import time  # pour chronométrer

SYSTEME = platform.system()  # "Windows", "Darwin" (= Mac) ou "Linux"
NOMBRE_DE_PINGS = 20


def lancer(commande):
    """Lance une commande du système et renvoie ce qu'elle affiche (texte)."""
    try:
        resultat = subprocess.run(
            commande,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
        return resultat.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


# ---------------------------------------------------------------------------
# Étape 1 : trouver l'adresse de ton routeur
# ---------------------------------------------------------------------------
def trouver_routeur():
    if SYSTEME == "Windows":
        texte = lancer(["ipconfig"])
        # On cherche la ligne "Passerelle par défaut" (ou "Default Gateway")
        for ligne in texte.splitlines():
            if "Passerelle" in ligne or "Gateway" in ligne:
                trouve = re.search(r"(\d+\.\d+\.\d+\.\d+)", ligne)
                if trouve:
                    return trouve.group(1)
    elif SYSTEME == "Darwin":
        texte = lancer(["route", "-n", "get", "default"])
        trouve = re.search(r"gateway:\s*(\d+\.\d+\.\d+\.\d+)", texte)
        if trouve:
            return trouve.group(1)
    else:
        texte = lancer(["ip", "route"])
        trouve = re.search(r"default via (\d+\.\d+\.\d+\.\d+)", texte)
        if trouve:
            return trouve.group(1)
    return None


# ---------------------------------------------------------------------------
# Étape 2 : mesurer le temps de réponse (ping)
# ---------------------------------------------------------------------------
def mesurer_ping(adresse):
    """Envoie plusieurs pings et renvoie (moyenne, variation, pourcentage perdu)."""
    if SYSTEME == "Windows":
        commande = ["ping", "-n", str(NOMBRE_DE_PINGS), adresse]
    else:
        commande = ["ping", "-c", str(NOMBRE_DE_PINGS), adresse]

    texte = lancer(commande)
    # Chaque réponse contient "time=12.3" ou "temps=12" ou "temps<1"
    temps = re.findall(r"(?:time|temps)[=<]\s*([\d.,]+)", texte)
    temps = [float(t.replace(",", ".")) for t in temps]

    if not temps:
        return None, None, 100.0

    perdus = (NOMBRE_DE_PINGS - len(temps)) / NOMBRE_DE_PINGS * 100
    moyenne = statistics.mean(temps)
    # La "gigue" = à quel point le temps change d'un ping à l'autre
    gigue = statistics.pstdev(temps)
    return moyenne, gigue, perdus


# ---------------------------------------------------------------------------
# Étape 3 : mesurer la vitesse du DNS (l'annuaire d'Internet)
# ---------------------------------------------------------------------------
def mesurer_dns():
    sites = ["google.com", "wikipedia.org", "youtube.com", "amazon.fr"]
    durees = []
    for site in sites:
        debut = time.perf_counter()
        try:
            socket.gethostbyname(site)
            durees.append((time.perf_counter() - debut) * 1000)
        except socket.gaierror:
            pass
    if not durees:
        return None
    return max(durees)  # le plus lent, c'est celui qui se ressent


# ---------------------------------------------------------------------------
# Étape 4 : lire la qualité du signal wifi
# ---------------------------------------------------------------------------
def infos_wifi():
    """Renvoie (signal en %, canal). Peut renvoyer None si introuvable."""
    signal, canal = None, None

    if SYSTEME == "Windows":
        texte = lancer(["netsh", "wlan", "show", "interfaces"])
        s = re.search(r"Signal\s*:\s*(\d+)\s*%", texte)
        c = re.search(r"(?:Canal|Channel)\s*:\s*(\d+)", texte)
        if s:
            signal = int(s.group(1))
        if c:
            canal = int(c.group(1))

    elif SYSTEME == "Darwin":
        texte = lancer(["system_profiler", "SPAirPortDataType"])
        s = re.search(r"Signal / Noise:\s*(-\d+)\s*dBm", texte)
        c = re.search(r"Channel:\s*(\d+)", texte)
        if s:
            # On convertit les dBm (-30 = excellent, -90 = nul) en pourcentage
            dbm = int(s.group(1))
            signal = max(0, min(100, 2 * (dbm + 100)))
        if c:
            canal = int(c.group(1))

    else:
        texte = lancer(["nmcli", "-t", "-f", "IN-USE,SIGNAL,CHAN", "dev", "wifi"])
        for ligne in texte.splitlines():
            if ligne.startswith("*"):  # l'étoile = le réseau où tu es connecté
                morceaux = ligne.split(":")
                signal, canal = int(morceaux[1]), int(morceaux[2])

    return signal, canal


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------
def afficher_ping(nom, moyenne, gigue, perdus):
    if moyenne is None:
        print(f"  {nom} : AUCUNE RÉPONSE")
    else:
        print(f"  {nom} : {moyenne:.0f} ms en moyenne, "
              f"variation {gigue:.0f} ms, {perdus:.0f} % perdus")


def main():
    print("=== Diagnostic de ton wifi ===\n")
    problemes = []

    # --- Signal wifi ---
    signal, canal = infos_wifi()
    print("1) Signal wifi")
    if signal is not None:
        print(f"  Force du signal : {signal} %")
        if signal < 50:
            problemes.append(
                "Signal FAIBLE : tu es trop loin du routeur ou il y a des murs/"
                "obstacles. Rapproche-toi, ou déplace le routeur en hauteur, "
                "au centre de la maison, loin du micro-ondes et des miroirs."
            )
    else:
        print("  (impossible de lire le signal sur cet ordinateur)")
    if canal is not None:
        bande = "2,4 GHz" if canal <= 14 else "5 GHz"
        print(f"  Canal : {canal} ({bande})")
        if canal <= 14:
            problemes.append(
                "Tu es sur la bande 2,4 GHz, souvent encombrée par les voisins. "
                "Si ton routeur propose un réseau 5 GHz, connecte-toi dessus "
                "(plus rapide quand tu es proche du routeur)."
            )

    # --- Ping vers le routeur ---
    print(f"\n2) Liaison ordinateur -> routeur ({NOMBRE_DE_PINGS} pings, patiente...)")
    routeur = trouver_routeur()
    moy_r = None
    if routeur:
        print(f"  Adresse du routeur : {routeur}")
        moy_r, gig_r, perdu_r = mesurer_ping(routeur)
        afficher_ping("Routeur", moy_r, gig_r, perdu_r)
        if moy_r is not None and (moy_r > 20 or gig_r > 15 or perdu_r > 1):
            problemes.append(
                "La liaison entre ton appareil et le routeur est MAUVAISE. "
                "Le problème vient du wifi chez toi (distance, obstacles, "
                "interférences, trop d'appareils connectés), pas d'Internet."
            )
    else:
        print("  Routeur introuvable.")

    # --- Ping vers Internet ---
    print(f"\n3) Liaison vers Internet ({NOMBRE_DE_PINGS} pings, patiente...)")
    moy_i, gig_i, perdu_i = mesurer_ping("1.1.1.1")
    afficher_ping("Internet (1.1.1.1)", moy_i, gig_i, perdu_i)
    routeur_ok = moy_r is not None and moy_r <= 20
    if moy_i is None:
        problemes.append("Internet ne répond pas du tout : vérifie ta box / appelle ton fournisseur.")
    elif routeur_ok and (moy_i - moy_r > 60 or perdu_i > 2):
        problemes.append(
            "Ton wifi est bon, mais la connexion de la box vers Internet est "
            "lente. Redémarre la box ; si ça continue, contacte ton fournisseur "
            "d'accès (le problème est sur leur ligne)."
        )

    # --- DNS ---
    print("\n4) Vitesse du DNS (traduction des noms de sites)")
    dns = mesurer_dns()
    if dns is None:
        print("  Le DNS ne répond pas.")
        problemes.append("Le DNS ne marche pas : les sites ne peuvent pas s'ouvrir.")
    else:
        print(f"  Le plus lent : {dns:.0f} ms")
        if dns > 150:
            problemes.append(
                "Le DNS est LENT (les pages mettent du temps à démarrer). "
                "Tu peux mettre le DNS 1.1.1.1 ou 8.8.8.8 dans les réglages "
                "de ton ordinateur ou de ta box."
            )

    # --- Verdict ---
    print("\n=== Verdict ===")
    if problemes:
        for numero, probleme in enumerate(problemes, start=1):
            print(f"{numero}. {probleme}\n")
    else:
        print("Tout semble normal au moment du test.")
        print("Si c'est lent à certains moments seulement, relance le test à ce moment-là.")


if __name__ == "__main__":
    main()
