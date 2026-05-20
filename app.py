import os
from flask import Flask, render_template, request, send_file, make_response
from PIL import Image
import io
import sqlite3
import time

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp/tool_site_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── 轻量级 SQLite 计数与 IP 日志初始化 ───
DB_PATH = os.path.join(os.path.dirname(__file__), 'counters.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # A. 基础计数表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
    ''')
    # 初始化所有可能用到的计数器（排除在线计算机）
    defaults = [
        ('total_visit', 0), 
        ('image_convert', 0), 
        ('doc_convert', 0), 
        ('password', 0),
        ('text_clean', 0),
        ('qrcode_tool', 0),
        ('timestamp', 0),
        ('client_compress', 0)
    ]
    for key, val in defaults:
        cursor.execute('INSERT OR IGNORE INTO counters (key, count) VALUES (?, ?)', (key, val))
        
    # B. 1小时滚动防刷沙盒表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ip_logs (
            ip TEXT PRIMARY KEY,
            last_visit_time INTEGER
        )
    ''')
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

# 程序启动时自动执行数据库初始化
init_db()

# ─── 核心算法：1小时滚动沙盒 IP 校验穿透器 ───
def get_real_ip():
    """彻底穿透 Nginx 反向代理，抓取外网用户的真实公网 IP"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def check_and_inc_total_visit():
    """1小时内到访过的 IP 拒绝再次给总访问量加1"""
    user_ip = get_real_ip()
    current_time = int(time.time())
    one_hour_secs = 3600

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
        last_visit = row[0]
        if current_time - last_visit > one_hour_secs:
            cursor.execute('UPDATE ip_logs SET last_visit_time = ? WHERE ip = ?', (current_time, user_ip))
            conn.commit()
            conn.close()
            inc_counter('total_visit')
        else:
            conn.close()


# ─── 页面路由逻辑舱 ───

# 1. 首页重定向 / 图片格式转换
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
                new_width = int(img.width * scale)
                new_height = int(img.height * scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            if target_format in ['JPEG', 'JPG'] and img.mode in ['RGBA', 'LA']:
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split() if img.mode == 'RGBA' else img.split((1,)))
                img = background
            elif target_format == 'ICO':
                img = img.convert('RGBA').resize((ico_size, ico_size), Image.Resampling.LANCZOS)

            img_io = io.BytesIO()
            save_args = {'format': target_format}
            if target_format in ['JPEG', 'JPG', 'WEBP']:
                save_args['quality'] = quality
            elif target_format == 'ICO':
                save_args['sizes'] = [(ico_size, ico_size)]

            img.save(img_io, **save_args)
            img_io.seek(0)
            return send_file(img_io, mimetype=f'image/{target_format.lower()}', as_attachment=True, download_name=f'converted.{target_format.lower()}')
            
    check_and_inc_total_visit()
    return render_template('image_convert.html', active_page='image_convert', counts=get_counters())

# 2. 文档转换舱
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
            except Exception as e:
                return f"转换失败: {str(e)}", 500
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

# 3. 在线计算机
@app.route('/calculator')
def calculator():
    check_and_inc_total_visit()
    return render_template('calculator.html', active_page='calculator', counts=get_counters())

# 4. 密码生成器
@app.route('/password')
def password_generator():
    check_and_inc_total_visit()
    return render_template('password.html', active_page='password', counts=get_counters())


# ─── [新扩展功能路由舱] ───

# 5. 文本清洗与去重舱
@app.route('/text-clean')
def text_clean():
    check_and_inc_total_visit()
    return render_template('text_clean.html', active_page='text_clean', counts=get_counters())

# 6. 二维码矩阵舱
@app.route('/qrcode-tool')
def qrcode_tool():
    check_and_inc_total_visit()
    return render_template('qrcode_tool.html', active_page='qrcode_tool', counts=get_counters())

# 7. 时间戳转换舱
@app.route('/timestamp')
def timestamp_tool():
    check_and_inc_total_visit()
    return render_template('timestamp.html', active_page='timestamp', counts=get_counters())

# 8. 零负载本地图片压缩
@app.route('/client-compress')
def client_compress():
    check_and_inc_total_visit()
    return render_template('client_compress.html', active_page='client_compress', counts=get_counters())


# ─── 统一纯前端工具异步点击计数 API ───
@app.route('/api/inc-counter/<string:tool_key>', methods=['POST'])
def inc_generic_counter(tool_key):
    """供前端工具在明确点击执行、清洗、生成、或下载动作成功后，无刷新增加各自对应的累计次数"""
    valid_keys = ['password', 'text_clean', 'qrcode_tool', 'timestamp', 'client_compress']
    if tool_key in valid_keys:
        inc_counter(tool_key)
    return '', 204

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
