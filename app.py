from flask import Flask, redirect, render_template, request, session, jsonify
import mysql.connector
from flask_session  import Session
from flask_socketio import  SocketIO, send, emit, join_room, leave_room
from helpers import login_required
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
import os 
import uuid, random
from mysql.connector import pooling
from dotenv import load_dotenv

app = Flask("__name__")
app.config["SECRET_KEY"] = "123456"
UPLOAD_FLODER = "C:/Users/hp/Documents/Vs Code/Flask_1/static/images/profile_pictures"
UPLOAD_DB = "images/profile_pictures"
app.config["UPLOAD_FLODER"] = UPLOAD_FLODER
app.config["UPLOAD_DB"] = UPLOAD_DB
socketio = SocketIO(app)



load_dotenv()  # This loads variables from .env into os.environ

db_pool = pooling.MySQLConnectionPool(
    pool_name="mypool",
    pool_size=7,
    user=os.environ.get("MYSQLUSER"),               # Should be "root"
    host=os.environ.get("MYSQL_PUBLIC_HOST"),         # Set this in your .env, e.g., "switchyard.proxy.rlwy.net"
    passwd=os.environ.get("MYSQLPASSWORD"),           # Your Railway password
    database=os.environ.get("MYSQL_DATABASE"),        # "railway"
    port=int(os.environ.get("MYSQL_PUBLIC_PORT", 3306)), # Set your public port, e.g., 52785
    connection_timeout=10
)



# db_pool = pooling.MySQLConnectionPool(
#     pool_name="mypool",
#     pool_size=7,
#     user="root",  # Railway MYSQLUSER (should be 'root')
#     host="switchyard.proxy.rlwy.net",  # Replace with your public hostname from MYSQL_PUBLIC_URL
#     passwd="WrhrerqcRdqExsPthQCncURJvfyiDTcL",  # Your MYSQL_ROOT_PASSWORD
#     database="railway",  # Your MYSQL_DATABASE
#     port=52785,  # Use the public port if given in MYSQL_PUBLIC_URL; if not, then 3306
#     connection_timeout=10
# )




def get_sql_connection():
    try:
        return db_pool.get_connection()
    except Exception as e:
        print(f"pool error:{e}. Creating a direct connection instead")
        return mysql.connector.connect(
            user = 'root',
            host = 'localhost',
            passwd = '44443612',
            database = 'myapp'
        )

app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

online={}

@app.route("/")
@login_required
def index():
    con = get_sql_connection()
    db = con.cursor()

    db.execute("select * from users")
    users =  db.fetchall()
    db.execute("select * from users where username = %s", (session.get("username"),))
    user_info = db.fetchone()  
   
    # db.execute("select g.room_name, g.user_id from groups_created g join users u on g.user_id = u.id where g.room in (select room from groups_created where user_id = %s) ",(session.get("user_id")))
    db.close()
    con.close()
    return render_template("index.html", user_info = user_info, users=users) 
    


@app.route("/login", methods = ["POST", "GET"])
def login():
    
    if request.method == "POST":
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
         
        if not username or not password:
            return jsonify({"message":"Fill the form"}),400
        
        con = get_sql_connection()
        db = con.cursor()

        try:
            db.execute("select * from users where username = %s", (username,))
            valid = db.fetchall()
            db.close()
            con.close()
            
            if len(valid) == 1 and check_password_hash(
                valid[0][2], password
            ):
                session["user_id"] = valid[0][0]
                session["username"] = valid[0][1]
                return redirect("/")
            else:
                return jsonify({"message":"Incorrect password and/or username"}),400
            
        except Exception as e:
            db.close()
            con.close()
            app.logger.error(f"Database operation failed:{e}")
            return jsonify({"message":"An internal server error occurred",}),500
    
    else:
        return render_template("login.html")
    

@app.route("/register", methods = ["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
        conformation = data.get("conformation")

        if not password or not conformation or not username:
            return jsonify({"message":"Fill the form"}),400
        if password != conformation:
            return jsonify({"message":"Password and conformation must match"}),400
        
        con = get_sql_connection()
        db = con.cursor()
        try:
            db.execute("select * from users where username = %s",(username,))
            valid = db.fetchall()

            if valid:
                db.close()
                con.close()
                return jsonify({"message":"Username taken"}),400
            
            hash = generate_password_hash(password)
            db.execute("insert into users (username, hash ) values (%s, %s)", (username, hash,))
            con.commit()

            db.execute("select * from users where username = %s",(username,))
            data = db.fetchall()
            if data:
                session["username"] = data[0][1]
                session["user_id"] = data[0][0]
            db.close()
            con.close()
            return redirect("/")
        
        except Exception as e:
            db.close()
            con.close()
            app.logger.error(f"Database operation failed: {e}")
            return jsonify({"message": "Unexcepted error occured"}), 500
        
    else:
        return render_template("register.html", boolian = "True")
    
@socketio.on("connect")
def connect():
    con = get_sql_connection()
    db = con.cursor()
    db.execute("select room from groups_created where user_id = %s", (session.get("user_id"),))
    rooms = db.fetchall()
    if rooms:
        for room in rooms:
            join_room(room[0])
    id = session.get("user_id")
    if id:    
        online[id] = request.sid
        db.close()
        con.close()
        emit('online', list(online.keys()), broadcast=True)

@app.route("/onlinee")
def onlinee():
    return jsonify(list(online.keys()))

@socketio.on("disconnect")
def disconnect():
    con = get_sql_connection()
    db = con.cursor()
    online.pop(session.get("user_id"))
    db.execute("select room from groups_created where user_id = %s", (session.get("user_id"),))
    rooms = db.fetchall()
    if rooms:
        for room in rooms:
            leave_room(room)
    db.close()
    con.close()
    emit('online', list(online.keys()), broadcast=True)

@socketio.on("private_message")
def private_message(data):
    con = get_sql_connection()
    db = con.cursor()
    if data.get("receiver"):
        db.execute("insert into messages (recipient_id, sender_id, message) values (%s , %s, %s) ",(data["receiver"],session.get("user_id"),data["message"] ))
        con.commit()
        key = online.get(data["receiver"])
        if key:
            db.close()
            con.close()
            emit('private_message', {"sender": session.get("username"),"sender_id": session.get("user_id"), "message": data["message"]}, room=key)
    elif data.get("room"):
        db.execute("select * from groups_created where room = %s and user_id = %s ", (data["room"], session.get("user_id")))
        valid = db.fetchone()
        if not valid:
            db.close()
            con.close()
            return jsonify({"error": "Error occured while sending messages"})
        db.execute("insert into group_messages (room_id, sender_id, message) values (%s, %s, %s)",(data["room"],session.get("user_id"), data["message"] ))
        con.commit()
        db.close()
        con.close()
        emit('group_message',{"sender": session.get("username"),"message": data["message"], "room":data["room"]}, to = data["room"])



@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/users")
def users():
    con = get_sql_connection()
    db = con.cursor()
    if request.args.get("groups"):
        db.execute("select * from groups_created g join users u on g.user_id = u.id where g.room in (select room from groups_created where user_id = %s) ",(session.get("user_id"),))
        groups = db.fetchall()
        db.close()
        con.close()
        return jsonify(groups)
    
    elif request.args.get("profile"):
        room = request.args.get("profile")
        if not room:
            db.close()
            con.close()
            return({"Error":"Error in getting data"}),400
        room = (int(room))
        db.execute("select * from groups_created where user_id = %s and room = %s ",(session.get("user_id"), room))
        valid = db.fetchall()
        if not valid:
            db.close()
            con.close()
            return({"Error":"Error in getting data"}),400
        db.execute("select * from users where id in(select user_id from groups_created where room = %s)", (room,))
        data = db.fetchall()
        db.execute("select * from users where id = (select user_id from groups_created where room = %s and group_admin = %s)", (room, True))
        admin = db.fetchone()
        db.close()
        con.close()
        return jsonify(data, admin)
    elif request.args.get("individuals"):
        db.execute("select * from users")
        users = db.fetchall()
        db.close()
        con.close()
        return jsonify(users)
    
    # db.execute("select room from groups_created where user_id = %s",(session.get("user_id"),))
    # # groups = db.fetchall()

    


@app.route("/create_group", methods = ["POST"])
def create_group():
    data = request.get_json()
    users = data.get("users")
    group_name = data.get("group_name")
    if not users or len(users) < 1:
        return jsonify({"error": "Select at least one user"}),400
    if not group_name:
        return jsonify({"error": "Group name requerid"}),400
    users = list(map(int,users))
    con = get_sql_connection()
    db = con.cursor()
    query = "select id from users where id in ({})".format(','.join(["%s"] * len(users)))
    db.execute(query, users)
    ans = db.fetchall()
    data = []
    for i in ans:
        data.append(i[0])
    if not all(item in users for item in data) or len(users) != len(data):
        db.close()
        con.close()
        return jsonify({"error":"Error ocurred"}),400
    while True:
        code = random.randint(1000000,1000000000)
        db.execute("select * from groups_created where room = %s",(code,))
        valid = db.fetchall()
        if not valid:
            break
    query_2 = "insert into groups_created (room, room_name, user_id) values (%s, %s, %s)"
    values = [(code , group_name, user) for user in users]
    db.executemany(query_2, values)
    con.commit()
    db.execute("insert into groups_created (room, room_name, user_id, group_admin) values(%s, %s, %s, %s)", (code, group_name, session.get("user_id"), True))
    con.commit()
    db.close()
    con.close()

    
@app.route("/history", methods=["POST"])
def history():
    con = get_sql_connection()
    db = con.cursor()
    acsess = request.get_json()
    # recipient = receiver.get("recipient")

    if acsess.get("recipient"):
        recipient = acsess.get("recipient")
        db.execute("select profile_picture from users where id = %s",(recipient,))
        user = db.fetchone()

        db.execute("select * from messages where (sender_id = %s and recipient_id = %s) or (sender_id = %s and recipient_id = %s ) order by timestamp", (recipient,session.get("user_id"),session.get("user_id"), recipient))
        data = db.fetchall()
        db.close()
        con.close()
        return jsonify(data, user)
    
    elif acsess.get("room"):
        room = acsess.get("room")
        db.execute("select * from group_messages g join users u on g.sender_id = u.id where g.room_id = %s order by timestamp",(room,))
        data = db.fetchall()
        db.close()
        con.close()
        return jsonify(data)

    

@app.route("/update_profile_picture", methods=["POST"])
def upp():
    if "profile_picture" in request.files:
        profile = request.files["profile_picture"]
        print("am in")
        if profile.filename == '':
            return jsonify({"error":"Input has no file name "}),400
        
        extention = os.path.splitext(profile.name)[1]
        con = get_sql_connection()
        db = con.cursor()
        while True:
            filename = f'{uuid.uuid4().hex}{extention}'
            db_path = os.path.join(app.config["UPLOAD_DB"],filename)

            db.execute("select * from users where profile_picture = %s", (db_path,))
            check = db.fetchone()

            if not check:
                break
        
        upload_path = os.path.join(app.config["UPLOAD_FLODER"], filename)
        profile.save(upload_path)

        db.execute("update users set profile_picture = %s where username = %s",(db_path, session.get("username")))
        con.commit()
        db.close()
        con.close()
        return jsonify({"path":f'{db_path}'})
    
    
    elif "delete_pp" in request.get_json():
        con = get_sql_connection()
        db = con.cursor()

        db.execute("select * from users where id = %s",(session.get("user_id"),))
        pp = db.fetchone()

        if pp[3] != "images/profile_pictures/default.jpg":
            db.execute("update users set profile_picture = %s where id = %s",("images/profile_pictures/default.jpg",session.get("user_id")) )
            con.commit()
        return jsonify({"path":"images/profile_pictures/default.jpg"})

@app.route("/search")
def search():
    con = get_sql_connection()
    db = con.cursor()
    if "users" in request.args:
        name = request.args.get("users")
        db.execute("select * from users where username like %s", ("%" + name + "%",))
        names = db.fetchall()
        db.close()
        con.close()
        print(name)
        return jsonify(names)
    elif "groups" in request.args:
        name = request.args.get("groups")
        db.execute("select * from groups_created g join users u on g.user_id = u.id where g.room_name like %s", ("%" + name + "%",))
        groups = db.fetchall()
        db.close()
        con.close()
        return jsonify(groups)

if __name__ == "__main__":
    # app.run(host='0.0.0.0', port = 5000)
    # socketio.run(app, host='192.168.1.7', port=5000, debug=True)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
    # socketio.run(app, debug=True)

#196.188.181.135
