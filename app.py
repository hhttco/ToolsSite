import os
from flask import Flask, render_template, request, send_file, make_response
from PIL import Image
import io
import sqlite3
import time

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp/tool_site_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── SQLite 初始化 ───
DB_PATH = os.path.join(os.path.dirname(__file__), 'counters.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, count INTEGER DEFAULT 0)')
    # 新增 text_clean, qrcode_tool, time_tool, img_compress 的计数器
    defaults = [
        ('total_visit', 0), ('image_convert', 0), ('doc_convert', 0), 
        ('password', 0), ('text_clean', 0), ('qrcode_tool', 0), 
        ('time_tool', 0), ('img_compress', 0)
    ]
    for key, val in defaults:
        cursor.execute('INSERT OR IGNORE INTO counters (key, count) VALUES (?, ?)', (key, val))
    cursor.execute('CREATE TABLE IF NOT EXISTS ip_logs (ip TEXT PRIMARY KEY, last_visit_time INTEGER)')
    conn.commit()
    conn.close()

def get_counters():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT key, count FROM counters')
    counts = dict(cursor.fetchall())
    conn.close()
    return counts

def inc_counter(key):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE counters SET count = count + 1 WHERE key = ?', (key,))
    conn.commit()
    conn.close()

init_db()

def get_real_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def check_and_inc_total_visit():
    user_ip = get_real_ip()
    current_time = int(time.time())
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT last_visit_time FROM ip_logs WHERE ip = ?', (user_ip,))
    row = cursor.fetchone()
    if row is None:
        cursor.execute('INSERT INTO ip_logs (ip, last_visit_time) VALUES (?, ?)', (user_ip, current_time))
        conn.commit()
        conn.close()
        inc_counter('total_visit')
    else:
        if current_time - row[0] > 3600:
            cursor.execute('UPDATE ip_logs SET last_visit_time = ? WHERE ip = ?', (current_time, user_ip))
            conn.commit()
            conn.close()
            inc_counter('total_visit')
        else:
            conn.close()

# ─── 原有路由 ───
@app.route('/', methods=['GET', 'POST'])
@app.route('/image-convert', methods=['GET', 'POST'])
def image_convert():
    if request.method == 'POST':
        file = request.files.get('image')
        target_format = request.form.get('format', 'PNG').upper()
        quality = int(request.form.get('quality', 90))
        scale = float(request.form.get('scale', 1.0))
        ico_size = int(request.form.get('ico_size', 32))
        if file and file.filename != '':
            inc_counter('image_convert')
            img = Image.open(file.stream)
            if scale != 1.0 and target_format != 'ICO':
                img = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)
            if target_format in ['JPEG', 'JPG'] and img.mode in ['RGBA', 'LA']:
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3] if img.mode=='RGBA' else img.split()[1])
                img = background
            elif target_format == 'ICO':
                img = img.convert('RGBA').resize((ico_size, ico_size), Image.Resampling.LANCZOS)
            img_io = io.BytesIO()
            save_args = {'format': target_format}
            if target_format in ['JPEG', 'JPG', 'WEBP']: save_args['quality'] = quality
            elif target_format == 'ICO': save_args['sizes'] = [(ico_size, ico_size)]
            img.save(img_io, **save_args)
            img_io.seek(0)
            return send_file(img_io, mimetype=f'image/{target_format.lower()}', as_attachment=True, download_name=f'converted.{target_format.lower()}')
    check_and_inc_total_visit()
    return render_template('image_convert.html', active_page='image_convert', counts=get_counters())

@app.route('/doc-convert', methods=['GET', 'POST'])
def doc_convert():
    if request.method == 'POST':
        convert_type = request.form.get('convert_type')
        file = request.files.get('doc_file')
        if convert_type == 'pdf_to_word' and file and file.filename != '':
            inc_counter('doc_convert')
            input_path = os.path.join(UPLOAD_FOLDER, file.filename)
            output_name = file.filename.rsplit('.', 1)[0] + '.docx'
            output_path = os.path.join(UPLOAD_FOLDER, output_name)
            file.save(input_path)
            try:
                from pdf2docx import Converter
                cv = Converter(input_path)
                cv.convert(output_path, start=0, end=None)
                cv.close()
                return send_file(output_path, as_attachment=True, download_name=output_name)
            finally:
                if os.path.exists(input_path): os.remove(input_path)
                if os.path.exists(output_path): os.remove(output_path)
        elif convert_type == 'pdf_to_excel' and file and file.filename != '':
            inc_counter('doc_convert')
            input_path = os.path.join(UPLOAD_FOLDER, file.filename)
            output_name = file.filename.rsplit('.', 1)[0] + '.xlsx'
            output_path = os.path.join(UPLOAD_FOLDER, output_name)
            file.save(input_path)
            try:
                import pdfplumber
                from openpyxl import Workbook
                wb = Workbook()
                ws = wb.active
                ws.title = "Sheet1"
                with pdfplumber.open(input_path) as pdf:
                    for page in pdf.pages:
                        tables = page.extract_tables()
                        for table in tables:
                            for row in table:
                                if any(row): ws.append(row)
                wb.save(output_path)
                return send_file(output_path, as_attachment=True, download_name=output_name)
            except Exception as e: return f"转换失败: {str(e)}", 500
            finally:
                if os.path.exists(input_path): os.remove(input_path)
                if os.path.exists(output_path): os.remove(output_path)
        elif convert_type == 'pdf_merge':
            files = request.files.getlist('merge_files')
            if files and len(files) > 1:
                inc_counter('doc_convert')
                from pypdf import PdfMerger
                merger = PdfMerger()
                saved_paths = []
                try:
                    for f in files:
                        if f.filename != '':
                            path = os.path.join(UPLOAD_FOLDER, f.filename)
                            f.save(path)
                            saved_paths.append(path)
                            merger.append(path)
                    output_path = os.path.join(UPLOAD_FOLDER, 'merged.pdf')
                    merger.write(output_path)
                    merger.close()
                    return send_file(output_path, as_attachment=True, download_name='合并文档.pdf')
                finally:
                    for p in saved_paths:
                        if os.path.exists(p): os.remove(p)
                    if os.path.exists(output_path): os.remove(output_path)
    check_and_inc_total_visit()
    return render_template('doc_convert.html', active_page='doc_convert', counts=get_counters())

@app.route('/calculator')
def calculator():
    check_and_inc_total_visit()
    return render_template('calculator.html', active_page='calculator', counts=get_counters())

@app.route('/password')
def password_generator():
    check_and_inc_total_visit()
    return render_template('password.html', active_page='password', counts=get_counters())

@app.route('/api/inc-password', methods=['POST'])
def inc_password():
    inc_counter('password')
    return '', 204


# ─── 🆕 新增 4 大工具页面路由与异步统计 ───

# 1. 文本清洗舱
@app.route('/text-clean')
def text_clean():
    check_and_inc_total_visit()
    return render_template('text_clean.html', active_page='text_clean', counts=get_counters())

@app.route('/api/inc-text-clean', methods=['POST'])
def inc_text_clean():
    inc_counter('text_clean')
    return '', 204

# 2. 二维码矩阵
@app.route('/qrcode-tool', methods=['GET', 'POST'])
def qrcode_tool():
    if request.method == 'POST':
        qr_text = request.form.get('qr_text', '')
        if qr_text:
            inc_counter('qrcode_tool')
            import qrcode
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(qr_text)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img_io = io.BytesIO()
            img.save(img_io, 'PNG')
            img_io.seek(0)
            return send_file(img_io, mimetype='image/png', as_attachment=True, download_name='qrcode.png')
    check_and_inc_total_visit()
    return render_template('qrcode_tool.html', active_page='qrcode_tool', counts=get_counters())

# 3. 时间沙漏
@app.route('/time-tool')
def time_tool():
    check_and_inc_total_visit()
    return render_template('time_tool.html', active_page='time_tool', counts=get_counters())

@app.route('/api/inc-time-tool', methods=['POST'])
def inc_time_tool():
    inc_counter('time_tool')
    return '', 204

# 4. 图片纯前端压缩
@app.route('/img-compress')
def img_compress():
    check_and_inc_total_visit()
    return render_template('img_compress.html', active_page='img_compress', counts=get_counters())

@app.route('/api/inc-img-compress', methods=['POST'])
def inc_img_compress():
    inc_counter('img_compress')
    return '', 204

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
