from prisma import Prisma
from flask import Flask, request, render_template, redirect, url_for, send_file, jsonify, make_response
import os,io, jwt, datetime, pdfkit, hashlib, uuid
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
app.config['SECRET_KEY'] = 'e1b87dcbbf5dd58486a12f94159f8777619b5006943c549118d3f92eb579d67748ac3aa94bc54021af7bfe98785d8364254a36a43cc06a6d4a7208349d6c1a95'
app.config['UPLOAD_FOLDER'] = './static/uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
prisma = Prisma()

def validate_token(f):
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization').split(" ")[1]
        if not token:
            return jsonify({"message": "No token provided"}), 401
        
        try:
            # Check if the token is valid
            session = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            session['expiresAt'] = datetime.datetime.strptime(session['expiresAt'], '%Y-%m-%dT%H:%M:%S.%f')
            if datetime.datetime.now() > session['expiresAt']:
                return jsonify({"message": "Token expired"}), 401
            
            # Check if the user exists
            prisma.connect()
            res = prisma.user.find_unique({
                "email": session['email']
            })
            if not res:
                return jsonify({"message": "Invalid user"}), 401
            prisma.disconnect()
            return f(*args, **kwargs)
        except Exception as e:
            print(e)
            return jsonify({"message": "Invalid token"}), 401
            
    wrapper.__name__ = f.__name__
    return wrapper

def secure_filename(filename):
    return filename.replace(" ", "_")

def criar_pagina_conteudo(html_content):
     # Converte o HTML em PDF e armazena em um buffer
    pdf_buffer = io.BytesIO(pdfkit.from_string(html_content, False))
    return pdf_buffer

@app.route('/api/v1/upload', methods=['POST'])
@validate_token
def upload_pdf():
    file = request.files['file']
    if file.filename == '' or not file.filename.endswith('.pdf'):
        return 'Invalid file or not a PDF', 400
    print(file.filename)
    try:
        # Save the file
        basedir = os.path.abspath(os.path.dirname(__file__))
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        # save the file to the database
        prisma.connect()
        res = prisma.session.find_unique({
            "token": request.headers.get('Authorization').split(" ")[1],
            "expiresAt": {
                "gte": datetime.datetime.now()
            }
        })
        if not res:
            return jsonify({
                "message": "Invalid token"
            }), 401
        res = prisma.files.create({
            "path": os.path.join(app.config['UPLOAD_FOLDER'], filename),
            "ownerId": res.userId
        })
        prisma.disconnect()
        return jsonify({
            "message": "File uploaded successfully",
            "fileId": res.id,
            "path": os.path.join(app.config['UPLOAD_FOLDER'], filename)
        }), 200
    except Exception as e:
        return str(e), 500

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')
    # Create the user
    try:
        prisma.connect()
    except Exception as e:
        print(e)
    user = request.form['email']
    name = request.form['username']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    if password != confirm_password:
        return 'Passwords do not match', 400
    # Check if the user already exists
    res = prisma.user.find_unique({
        "email": user
    })

    if res:
        prisma.disconnect()
        return jsonify({
            "message": "User already exists"
        }, 400)
    # Create the user
    prisma.user.create({
        "name": name,
        "email": user,
        "password": password        
    })
    prisma.disconnect()
    return jsonify({
        "name": name,
        "email": user,
        "password": password        
    },201)

@app.route('/api/v1/login', methods=['GET', 'POST'])
def login():
    try:
        prisma.connect()
        form = request.get_json()
        user = form.get('username')
        password = form.get('password')
        res = prisma.user.find_unique({
            "email": user
        })
        if not res:
            return jsonify({
                "message": "User does not exist"
            }),400
        # Check if the password is correct
        if not res.password == password:
            return jsonify({
                "message": "Incorrect password"
            }),400
        # Create the session
        session = {
            "user": res.name,
            "email": res.email,
            "expiresAt": (datetime.datetime.now() + datetime.timedelta(hours=3)).isoformat(),
        }
        token = jwt.encode(session, app.config['SECRET_KEY'], algorithm='HS256')
        #persist the token in database
        prisma.session.create({
            "userId": res.id,
            "token": token,
            "expiresAt": datetime.datetime.now() + datetime.timedelta(days=1)
        })
        
        prisma.disconnect()
        return jsonify({
            "token": token
        }), 200
    except Exception as e:
        prisma.disconnect()
        print(e)
        return jsonify({
            "message": "Something went wrong"
        }),500

@app.route('/api/v1/logout', methods=['GET', 'POST'])
@validate_token
def logout():
    try:
        prisma.connect()
        token = request.headers.get('Authorization').split(" ")[1]
        prisma.session.delete({
            "token": token
        })
        prisma.disconnect()
        return jsonify({
            "message": "Logged out successfully"
        }), 200
    except Exception as e:
        prisma.disconnect()
        print(e)
        return jsonify({
            "message": "Something went wrong"
        }),500
    

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


@app.route('/api/v1/sign', methods=['POST'])
@validate_token
def signFile():
    try:
        prisma.connect()
        token = request.headers.get('Authorization').split(" ")[1]
        res = prisma.session.find_unique({
            "token": token,
        })
        if not res:
            return jsonify({
                "message": "Invalid token"
            }), 401
        user  = prisma.user.find_unique({
            "id": res.userId
        })
        # Check if the file exists
        form = request.get_json()
        prisma.filesigns.create({
            "fileId": form.get('fileId'),
            "userId": res.userId,
            "sig_token": hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
        })
        prisma.disconnect()
        return redirect(f'/api/v1/file/{form.get('fileId')}',302)
    except Exception as e:
        prisma.disconnect()
        return jsonify({
            "message": "Something went wrong",
            "error": str(e)
        }),500

@app.route('/api/v1/file/<fileId>', methods=['GET'])
def getFile(fileId):
    try:
        prisma.connect()
        file = prisma.files.find_unique({
            "id": fileId
        })
        if not file:
            return jsonify({
                "message": "File does not exist"
            }), 400
        
        signs = prisma.filesigns.find_many(where={
            "fileId": fileId
        })
        for sign in signs:
            print(sign.sig_token + " " + sign.userId)
        reader = PdfReader(open(file.path, "rb"))
        writer = PdfWriter()
        if len(signs) == 1:
            for pagina in reader.pages:
                writer.add_page(pagina)
        else:
            for pagina in reader.pages[:-1]:
                writer.add_page(pagina) 
        assinaturas = ""
        for sign in signs:
            user = prisma.user.find_unique({
                "id": sign.userId
            })
            assinaturas += f"""
                <div style="font-size: 12px; color: #333;width: 100%;">
                    <p>{sign.sig_token}</p>
                    <p>Assinatura: {user.name}</p>
                    <p>Data: {(sign.signed_at - datetime.timedelta(hours=3)).strftime("%d/%m/%Y %H:%M:%S")}</p>
                </div>
            """
        
        nova_pagina_pdf = PdfReader(criar_pagina_conteudo(assinaturas))
        writer.add_page(nova_pagina_pdf.pages[0])  # Adiciona a nova página ao final
        # Salva o novo PDF com a página adicional
        with open(f'./static/temp/{fileId}.pdf', "wb") as novo_pdf_file:
            writer.write(novo_pdf_file)
        prisma.disconnect()
        return send_file(file.path, as_attachment=True)
    except Exception as e:
        prisma.disconnect()
        print(e)
        return jsonify({
            "message": "Something went wrong",
            "error": str(e)
        }), 500
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
