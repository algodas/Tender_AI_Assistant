# -*- coding: utf-8 -*-
from flask import Flask, request, jsonify, Response
import openai
import os
import time
import traceback
from werkzeug.utils import secure_filename

openai.api_key = ""

UPLOAD_FOLDER = "/var/www/html/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024
app.url_map.strict_slashes = False

ASSISTANT_ID_DEFAULT = "asst_HPqXDHHf9uo5cxmRVG3"
ASSISTANT_ID_LICITACAO = "asst_CuK3xFpKPy4Z7IbCr"
VECTOR_STORE_ID = "vs_6838fccc5c8081918e032"

@app.route("/assist/ask", methods=["POST"])
def ask():
    data = request.json
    message = data.get("message")
    if not message:
        return jsonify({"error": "Mensagem não fornecida"}), 400

    thread = openai.beta.threads.create()
    openai.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=message
    )

    run = openai.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=ASSISTANT_ID_DEFAULT
    )

    while True:
        status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if status.status == "completed":
            break
        time.sleep(1)

    messages = openai.beta.threads.messages.list(thread_id=thread.id)
    resposta = messages.data[0].content[0].text.value
    return jsonify({"response": resposta})


@app.route("/assist/upload", methods=["POST"])
def upload_to_vector_store():
    if "file" not in request.files:
        return jsonify({"error": "Nenhum arquivo fornecido"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Nome de arquivo vazio"}), 400

    filename = secure_filename(file.filename)
    local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(local_path)

    try:
        openai_file = openai.files.create(
            file=open(local_path, "rb"),
            purpose="assistants"
        )

        for _ in range(20):
            file_status = openai.files.retrieve(openai_file.id)
            if file_status.status == "processed":
                break
            time.sleep(2)
        else:
            return jsonify({"error": "Arquivo não foi processado a tempo pela OpenAI."}), 500

        result = openai.vector_stores.file_batches.create(
            vector_store_id=VECTOR_STORE_ID,
            file_ids=[openai_file.id]
        )

        return jsonify({
            "filename": filename,
            "file_id": openai_file.id,
            "vector_store_id": VECTOR_STORE_ID,
            "status": "Arquivo adicionado ao vector store com sucesso via file_batches.create()"
        })

    except Exception as e:
        return Response(
            f"<h3>❌ Erro detalhado ao adicionar ao vector store:</h3><pre>{traceback.format_exc()}</pre>",
            status=500,
            mimetype='text/html'
        )


@app.route("/assist/ask-file", methods=["POST"])
def ask_with_file():
    return process_file_request(ASSISTANT_ID_DEFAULT)

@app.route("/assist/ask-licitacao", methods=["POST"])
def ask_licitacao():
    return process_file_request(ASSISTANT_ID_LICITACAO)

def process_file_request(assistant_id):
    if "file" not in request.files or "message" not in request.form:
        return jsonify({"error": "Arquivo e mensagem são obrigatórios."}), 400

    file = request.files["file"]
    message = request.form["message"]

    if file.filename == "":
        return jsonify({"error": "Nome de arquivo vazio."}), 400

    filename = secure_filename(file.filename)
    local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(local_path)

    try:
        openai_file = openai.files.create(
            file=open(local_path, "rb"),
            purpose="assistants"
        )

        thread = openai.beta.threads.create()
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message,
            attachments=[
                {
                    "file_id": openai_file.id,
                    "tools": [{"type": "file_search"}]
                }
            ]
        )

        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant_id
        )

        while True:
            status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if status.status == "completed":
                break
            time.sleep(1)

        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        resposta = messages.data[0].content[0].text.value

        return jsonify({
            "resposta": resposta,
            "arquivo": filename,
            "thread_id": thread.id,
            "openai_file_id": openai_file.id
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "error": "Erro durante o envio de arquivo ou execução do assistente.",
            "details": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100, debug=True)
 
