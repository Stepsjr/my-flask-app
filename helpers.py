from functools import wraps
from flask import session, render_template, redirect
import mysql.connector
from mysql.connector import pooling

def login_required(f):
    wraps(f)
    def wrapper():
        if session.get("user_id"):
            return f()
        else:
            return render_template("login.html")
    return wrapper


        



