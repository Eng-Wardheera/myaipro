from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy

import markdown
import PyPDF2
import docx2txt
import os

app = Flask(__name__)
# Database-ka cusub oo leh sessions
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///advanced_chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

client = os.getenv("GROQ_API_KEY")

# 1. Model-ka Sheekooyinka (Sessions)
class ChatSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), default="New Chat")
    messages = db.relationship('ChatMessage', backref='session', lazy=True, cascade="all, delete-orphan")

# 2. Model-ka Fariimaha (Messages)
class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('chat_session.id'), nullable=False)
    role = db.Column(db.String(10)) # 'user' ama 'ai'
    content = db.Column(db.Text, nullable=False)
    file_name = db.Column(db.String(100), nullable=True)

# Abuur Database-ka
with app.app_context():
    db.create_all()

def extract_text(file):
    if not file: return ""
    filename = file.filename.lower()
    try:
        if filename.endswith('.txt'):
            return file.read().decode('utf-8')
        elif filename.endswith('.pdf'):
            pdf_reader = PyPDF2.PdfReader(file)
            return "".join([page.extract_text() for page in pdf_reader.pages])
        elif filename.endswith('.docx'):
            return docx2txt.process(file)
    except Exception as e:
        print(f"File Error: {e}")
        return ""
    return ""

@app.route('/')
def home():
    # Soo qaado dhamaann sessions-ka jira
    sessions = ChatSession.query.order_by(ChatSession.id.desc()).all()
    
    # Haddii aysan jirin session, abuur midka ugu horeeya
    if not sessions:
        first_session = ChatSession(title="Sheekada Koowaad")
        db.session.add(first_session)
        db.session.commit()
        sessions = [first_session]

    # Baro session-ka hadda la furay (Default waa kan ugu dambeeyay)
    chat_id = request.args.get('chat_id', sessions[0].id, type=int)
    current_chat = ChatMessage.query.filter_by(session_id=chat_id).all()
    
    return render_template('index.html', sessions=sessions, history=current_chat, current_id=chat_id)

@app.route('/new_chat', methods=['POST'])
def new_chat():
    count = ChatSession.query.count() + 1
    new_s = ChatSession(title=f"Chat {count}")
    db.session.add(new_s)
    db.session.commit()
    return jsonify({"id": new_s.id})

@app.route('/ask', methods=['POST'])
def ask_ai():
    session_id = request.form.get('session_id')
    user_query = request.form.get('user_input', '').strip()
    file = request.files.get('file_upload')
    
    if not session_id:
        return jsonify({"answer": "Error: No session ID provided."}), 400

    file_text = ""
    file_name = None
    if file and file.filename != '':
        file_name = file.filename
        file_text = extract_text(file)

    if not user_query and not file_text:
        return jsonify({"answer": "Fadlan wax qor..."})

    # 1. Keydi fariinta User-ka
    user_msg = ChatMessage(session_id=session_id, role='user', content=user_query, file_name=file_name)
    db.session.add(user_msg)

    try:
        # Prompt-ka AI-ga loo dirayo
        prompt = f"User Query: {user_query}\n\n[Dukumiintiga la socda: {file_text}]" if file_text else user_query
        
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "Waxaad tahay AI kaaliye ah oo ku hadla Af-Soomaali. Jawaabahaaga u qaabee si qurux badan."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        
        ai_response = completion.choices[0].message.content
        formatted_ai_response = markdown.markdown(ai_response)
        
        # 2. Keydi fariinta AI-ga
        ai_msg = ChatMessage(session_id=session_id, role='ai', content=formatted_ai_response)
        db.session.add(ai_msg)
        
        # Haddii ay tahay fariintii ugu horeysay, cusboonaysii Title-ka session-ka
        session = ChatSession.query.get(session_id)
        if session.title.startswith("Chat "):
            session.title = user_query[:30] + ("..." if len(user_query) > 30 else "")
            
        db.session.commit()
        
        return jsonify({"answer": formatted_ai_response})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"answer": f"Khalad: {str(e)}"})

@app.route('/clear', methods=['POST'])
def clear_chat():
    session_id = request.form.get('session_id')
    if session_id:
        ChatMessage.query.filter_by(session_id=session_id).delete()
        db.session.commit()
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)