import sys
import os
import random
import zlib
import base64
import hashlib
import pyotp
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QTextEdit, QLineEdit, QPushButton, QMessageBox, 
                             QSpinBox, QCheckBox, QDialog, QVBoxLayout as QVDialog)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import qrcode
from PIL import Image
from io import BytesIO

SERVER_TEMPLATE = """\
from flask import Flask, jsonify, request
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
import base64
import pyotp

app = Flask(__name__)

AES_KEY = b"{aes_key}"
ECC_PRIVATE_KEY_PEM = b\"\"\"{ecc_private}\"\"\"
VALID_HASH = "{valid_file_hash}"
TOTP_SECRET = "{totp_secret}"

@app.route('/get_license', methods=['POST'])
def get_license():
    data = request.json
    
    client_hash = data.get('hash', '')
    if client_hash != VALID_HASH:
        return jsonify({{"error": "invalid_hash"}}), 403

    if TOTP_SECRET:
        totp_code = data.get('totp', '')
        totp = pyotp.TOTP(TOTP_SECRET)
        if not totp.verify(totp_code):
            return jsonify({{"error": "invalid_totp"}}), 403

    private_key = serialization.load_pem_private_key(ECC_PRIVATE_KEY_PEM, password=None)
    signature = private_key.sign(AES_KEY, ec.ECDSA(hashes.SHA256()))
    
    return jsonify({{
        "aes_key": AES_KEY.decode('utf-8'),
        "signature": base64.b64encode(signature).decode('utf-8')
    }})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
"""

CLIENT_TEMPLATE = """\
import sys
import os
import requests
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

{url_builder_func}

ENCRYPTED_PAYLOAD = b"{payload}"
ECC_PUBLIC_KEY_PEM = b\"\"\"{ecc_public}\"\"\"

def self_destruct():
    try:
        os.remove(os.path.abspath(sys.argv[0]))
    except:
        pass
    sys.exit(1)

def run_protected_code():
    try:
        with open(sys.argv[0], 'rb') as f:
            current_hash = hashlib.sha256(f.read()).hexdigest()
            
        server_url = get_hidden_string()
        payload = {{"hash": current_hash}}
        
        {totp_client_code}
        
        response = requests.post(server_url, json=payload, timeout=5)
        
        if response.status_code == 403:
            self_destruct()
            
        response.raise_for_status()
        data = response.json()
        
        aes_key = data.get("aes_key").encode('utf-8')
        signature = base64.b64decode(data.get("signature"))
        
    except Exception:
        self_destruct()

    try:
        public_key = serialization.load_pem_public_key(ECC_PUBLIC_KEY_PEM)
        public_key.verify(signature, aes_key, ec.ECDSA(hashes.SHA256()))
    except Exception:
        self_destruct()

    try:
        f = Fernet(aes_key)
        decrypted_code = f.decrypt(ENCRYPTED_PAYLOAD).decode('utf-8')
        exec(decrypted_code, {{}})
    except Exception:
        self_destruct()

if __name__ == "__main__":
    run_protected_code()
"""

class ObfuscatorApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Обфускатор Python')
        self.resize(750, 650)
        layout = QVBoxLayout()

        settings_layout = QHBoxLayout()
        settings_layout.addWidget(QLabel("URL сервера:"))
        self.url_input = QLineEdit("http://127.0.0.1:5000/get_license")
        settings_layout.addWidget(self.url_input)
        
        settings_layout.addWidget(QLabel("Слои обфускации:"))
        self.layers_spin = QSpinBox()
        self.layers_spin.setRange(1, 20)
        self.layers_spin.setValue(3)
        settings_layout.addWidget(self.layers_spin)
        
        layout.addLayout(settings_layout)

        totp_layout = QHBoxLayout()
        self.totp_checkbox = QCheckBox("Включить TOTP")
        self.totp_checkbox.stateChanged.connect(self.toggle_totp)
        totp_layout.addWidget(self.totp_checkbox)

        self.totp_secret_input = QLineEdit()
        self.totp_secret_input.setPlaceholderText("Секретный ключ (Base32)")
        self.totp_secret_input.setEnabled(False)
        totp_layout.addWidget(self.totp_secret_input)

        self.btn_gen_totp = QPushButton("Сгенерировать ключ")
        self.btn_gen_totp.setEnabled(False)
        self.btn_gen_totp.clicked.connect(lambda: self.totp_secret_input.setText(pyotp.random_base32()))
        totp_layout.addWidget(self.btn_gen_totp)

        self.btn_qr = QPushButton("Показать QR")
        self.btn_qr.setEnabled(False)
        self.btn_qr.clicked.connect(self.show_qr)
        totp_layout.addWidget(self.btn_qr)
        
        layout.addLayout(totp_layout)

        layout.addWidget(QLabel("Исходный код (Python):"))
        self.code_input = QTextEdit()
        layout.addWidget(self.code_input)

        self.generate_btn = QPushButton("Сгенерировать защищенные файлы")
        self.generate_btn.setStyleSheet("padding: 10px; font-weight: bold;")
        self.generate_btn.clicked.connect(self.generate)
        layout.addWidget(self.generate_btn)

        self.setLayout(layout)

    def toggle_totp(self):
        is_enabled = self.totp_checkbox.isChecked()
        self.totp_secret_input.setEnabled(is_enabled)
        self.btn_gen_totp.setEnabled(is_enabled)
        self.btn_qr.setEnabled(is_enabled)
        if is_enabled and not self.totp_secret_input.text():
            self.totp_secret_input.setText(pyotp.random_base32())

    def show_qr(self):
        secret = self.totp_secret_input.text().strip()
        if not secret:
            QMessageBox.warning(self, "Ошибка", "Нет TOTP секрета. Сначала сгенерируйте ключ.")
            return
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name="Protected Script", issuer_name="Obfuscator")
        qr = qrcode.make(uri)
        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        buffer.seek(0)
        pixmap = QPixmap()
        pixmap.loadFromData(buffer.read(), "PNG")
        dialog = QDialog(self)
        dialog.setWindowTitle("QR-код для TOTP")
        layout = QVDialog()
        label = QLabel()
        label.setPixmap(pixmap.scaled(300, 300, Qt.KeepAspectRatio))
        layout.addWidget(label)
        layout.addWidget(QLabel(f"Секрет: {secret}"))
        dialog.setLayout(layout)
        dialog.exec_()

    def generate_complex_math_for_number(self, target_num):
        base1 = random.randint(1000000, 9999999)
        base2 = random.randint(1000000, 9999999)
        offset = target_num - base1 + base2
        return f"-(-({base1} - {base2}) - {offset})" if random.choice([True, False]) else f"({base1} - {base2} + {offset})"

    def build_string_obfuscator(self, target_string):
        lines = ["def get_hidden_string():\n    res = []"]
        for char in target_string:
            char_code = ord(char)
            xor_key = random.randint(1000, 9999)
            strategies = [
                f"    res.append(chr({self.generate_complex_math_for_number(char_code)}))",
                f"    res.append(chr({char_code ^ xor_key} ^ {xor_key}))",
                f"    res.append(chr(int('{hex(char_code)}', 16)))"
            ]
            lines.append(random.choice(strategies))
        lines.append("    return ''.join(res)")
        return "\n".join(lines)

    def apply_obfuscation_layers(self, code, layers):
        for _ in range(layers):
            compressed = zlib.compress(code.encode('utf-8'))
            encoded = base64.b64encode(compressed).decode('ascii')
            var_data = "v_" + "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=10))
            code = f"import zlib, base64\n{var_data} = '{encoded}'\nexec(zlib.decompress(base64.b64decode({var_data}.encode())))"
        return code

    def generate(self):
        source_code = self.code_input.toPlainText()
        server_url = self.url_input.text().strip()
        layers = self.layers_spin.value()
        use_totp = self.totp_checkbox.isChecked()
        totp_secret = self.totp_secret_input.text().strip()

        if not source_code:
            QMessageBox.warning(self, "Ошибка", "Введите код!")
            return
        if use_totp and not totp_secret:
            QMessageBox.warning(self, "Ошибка", "Сгенерируйте TOTP ключ!")
            return

        try:
            aes_key = Fernet.generate_key()
            f = Fernet(aes_key)
            encrypted_payload = f.encrypt(source_code.encode('utf-8'))

            private_key = ec.generate_private_key(ec.SECP256R1())
            public_key = private_key.public_key()

            priv_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.PKCS8, encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')

            pub_pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')

            url_func = self.build_string_obfuscator(server_url)

            if use_totp:
                totp_client_code = "totp_code = input('Введите TOTP код из Authenticator: ').strip()\n        payload['totp'] = totp_code"
                server_totp_val = totp_secret
            else:
                totp_client_code = "# TOTP отключен"
                server_totp_val = ""

            raw_client_code = CLIENT_TEMPLATE.format(
                url_builder_func=url_func,
                payload=encrypted_payload.decode('utf-8'),
                ecc_public=pub_pem,
                totp_client_code=totp_client_code
            )

            final_client_code = self.apply_obfuscation_layers(raw_client_code, layers)
            client_hash = hashlib.sha256(final_client_code.encode('utf-8')).hexdigest()

            server_code = SERVER_TEMPLATE.format(
                aes_key=aes_key.decode('utf-8'),
                ecc_private=priv_pem,
                valid_file_hash=client_hash,
                totp_secret=server_totp_val
            )

            with open("server.py", "w", encoding="utf-8") as s_file:
                s_file.write(server_code)

            with open("client_protected.py", "wb") as c_file:
                c_file.write(final_client_code.encode('utf-8'))

            if use_totp:
                with open("totp_setup.txt", "w", encoding="utf-8") as t_file:
                    t_file.write(f"Добавьте этот ключ в Google Authenticator: {totp_secret}\n")
                    t_file.write(f"Или создайте QR код по URI: {pyotp.totp.TOTP(totp_secret).provisioning_uri(name='Protected Script', issuer_name='MyDRM')}")

            QMessageBox.information(self, "Успех", "Файлы сгенерированы!")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    dark_style = """
    QWidget {
        background-color: #2b2b2b;
        color: #f0f0f0;
        font-family: Consolas, monospace;
    }
    QLabel {
        color: #f0f0f0;
    }
    QLineEdit, QTextEdit, QSpinBox {
        background-color: #3c3c3c;
        color: #f0f0f0;
        border: 1px solid #5a5a5a;
        border-radius: 3px;
        padding: 2px;
    }
    QPushButton {
        background-color: #5a5a5a;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 5px 10px;
    }
    QPushButton:hover {
        background-color: #6e6e6e;
    }
    QPushButton:pressed {
        background-color: #3e3e3e;
    }
    QCheckBox {
        color: #f0f0f0;
    }
    QCheckBox::indicator {
        width: 13px;
        height: 13px;
    }
    """
    app.setStyleSheet(dark_style)
    ex = ObfuscatorApp()
    ex.show()
    sys.exit(app.exec_())