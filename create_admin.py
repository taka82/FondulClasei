"""Creeaza un cont de administrator sau reseteaza parola unui cont din consola.

Pe un server public pagina /setup este dezactivata, deci contul de administrator se creeaza asa:

    python3 create_admin.py                  # cont nou de administrator (cere utilizator si parola)
    python3 create_admin.py --reset NUME     # schimba parola unui cont existent (ex: ai uitat-o)

Foloseste aceeasi versiune de Python ca aplicatia web (ex: python3.12).
"""
import argparse
import getpass
import sys

from werkzeug.security import generate_password_hash

import app as fond
import db


def create_admin(username, password, class_name=None):
    error = fond.credentials_error(username, password)
    if error:
        raise ValueError(error)
    with fond.app.app_context():
        if db.one("SELECT 1 FROM users WHERE username = ?", (username,)):
            raise ValueError("Există deja un utilizator cu acest nume.")
        db.execute("INSERT INTO users(username, password_hash, role) VALUES (?, ?, 'admin')",
                   (username, generate_password_hash(password)))
        if class_name:
            db.set_setting("class_name", class_name)


def reset_password(username, password):
    if len(password) < fond.PASSWORD_MIN:
        raise ValueError(f"Parola trebuie să aibă minim {fond.PASSWORD_MIN} caractere.")
    with fond.app.app_context():
        cur = db.execute("UPDATE users SET password_hash = ? WHERE username = ?",
                         (generate_password_hash(password), username))
        if cur.rowcount == 0:
            raise ValueError(f"Nu există utilizatorul „{username}”.")


def ask_password():
    password = getpass.getpass("Parola (minim 8 caractere, nu se vede la tastare): ")
    if password != getpass.getpass("Repetă parola: "):
        raise ValueError("Parolele nu coincid.")
    return password


def main():
    parser = argparse.ArgumentParser(description="Creează un cont de administrator sau resetează parola unui cont.")
    parser.add_argument("--reset", metavar="NUME", help="schimbă parola contului existent NUME")
    args = parser.parse_args()
    try:
        if args.reset:
            reset_password(args.reset, ask_password())
            print(f"Parola contului „{args.reset}” a fost schimbată.")
        else:
            username = input("Utilizator (3-32 caractere: litere, cifre, . _ -): ").strip()
            class_name = input("Numele clasei (ex: Clasa a V-a; Enter = lasă neschimbat): ").strip() or None
            create_admin(username, ask_password(), class_name)
            print(f"Contul de administrator „{username}” a fost creat. Te poți autentifica pe site.")
    except ValueError as e:
        sys.exit(f"Eroare: {e}")


if __name__ == "__main__":
    main()
