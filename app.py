import os
from flask import Flask, render_template, request, send_file, jsonify, make_response
from PIL import Image
import io
import sqlite3
import time
import cv2
import numpy as np

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp/tool_site_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── 核心修复：纯 Python 物理路径锁定（动态移植 + 零漂移持久化） ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
os.makedirs(INSTANCE_DIR, exist_ok=True) # 自动创建同目录下的 instance 保护区
DB_PATH = os.path.join(INSTANCE_DIR, 'counters.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # A. 基础功能计数表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
    ''')
    defaults = [
        ('total_visit', 0), 
        ('image_convert', 0), 
        ('doc_convert', 0), 
        ('password', 0),
        ('text_clean', 0),
        ('qrcode_tool', 0),
        ('time_capsule', 0),
        ('beauty_booth', 0)
    ]
    for key, val in defaults:
        cursor.execute('INSERT OR IGNORE INTO counters (key, count) VALUES (?, ?)', (key, val))
        
    # B. 轻量级 IP 防刷沙盒日志表
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

# 程序启动时首先初始化数据库
init_db()


# ─── 核心算法：1小时滚动沙盒 IP 校验穿透器 ───
def get_real_ip():
    """彻底穿透 Nginx 反向代理，抓取外网用户的真实公网 IP"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def check_and_inc_total_visit():
    """检查 IP 状态：1小时内到访过的 IP 拒绝再次给总访问量加1"""
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


# ─── 智能美工舱图形处理核心底层算法 ───

def remove_watermark_core(img_bytes):
    """文本去水印核心算法（Telea修复矩阵）"""
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 针对浅灰色/半透明防复制水印的精准过滤区间
    lower_gray = np.array([0, 0, 200])
    upper_gray = np.array([180, 20, 250])
    mask = cv2.inRange(hsv, lower_gray, upper_gray)
    
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)
    dst = cv2.inpaint(img, mask, 5, cv2.INPAINT_TELEA)
    
    _, buffer = cv2.imencode('.png', dst)
    return io.BytesIO(buffer.tobytes())

def change_bg_core(img_bytes, target_hex):
    """证件照换底色核心算法（发丝柔化漫水容差）"""
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    hex_color = target_hex.lstrip('#')
    target_bgr = tuple(int(hex_color[i:i+2], 16) for i in (4, 2, 0))
    
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # 动态抓取左上角首个像素点作为纯色背景基准
    bg_sample = hsv[5, 5]
    
    lower_blue = np.array([max(0, bg_sample[0]-15), max(40, bg_sample[1]-40), max(40, bg_sample[2]-45)])
    upper_blue = np.array([min(180, bg_sample[0]+15), min(255, bg_sample[1]+40), min(255, bg_sample[2]+45)])
    
    mask = cv2.inRange(hsv, lower_blue, upper_blue)
    mask_blur = cv2.GaussianBlur(mask, (3, 3), 0)
    
    bg_canvas = np.zeros_like(img)
    bg_canvas[:] = target_bgr
    
    mask_3d = cv2.cvtColor(mask_blur, cv2.COLOR_GRAY2BGR) / 255.0
    dst = (img * (1 - mask_3d) + bg_canvas * mask_3d).astype(np.uint8)
    
    _, buffer = cv2.imencode('.png', dst)
    return io.BytesIO(buffer.tobytes())


# ─── 页面业务路由舱位 ───

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
            
            ext = target_format.lower()
            download_filename = 'favicon.ico' if target_format == 'ICO' else f'converted.{ext}'
            return send_file(img_io, mimetype=f'image/{ext}', as_attachment=True, download_name=download_filename)
            
    check_and_inc_total_visit()
    return render_template('image_convert.html', active_page='image_convert', counts=get_counters())

@app.route('/beauty-booth', methods=['GET', 'POST'])
def beauty_booth():
    if request.method == 'POST':
        file = request.files.get('image')
        action_type = request.form.get('action_type')
        bg_color = request.form.get('bg_color', '#ff0000')
        
        if file and file.filename != '':
            inc_counter('beauty_booth')
            img_bytes = file.read()
            if action_type == 'remove_watermark':
                out_io = remove_watermark_core(img_bytes)
                return send_file(out_io, mimetype='image/png', as_attachment=True, download_name='cleaned_image.png')
            elif action_type == 'change_bg':
                out_io = change_bg_core(img_bytes, bg_color)
                return send_file(out_io, mimetype='image/png', as_attachment=True, download_name='id_photo_changed.png')

    check_and_inc_total_visit()
    return render_template('beauty_booth.html', active_page='beauty_booth', counts=get_counters())

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

@app.route('/calculator')
def calculator():
    check_and_inc_total_visit()
    return render_template('calculator.html', active_page='calculator', counts=get_counters())

@app.route('/password')
def password_generator():
    check_and_inc_total_visit()
    return render_template('password.html', active_page='password', counts=get_counters())

@app.route('/text-clean')
def text_clean_page():
    check_and_inc_total_visit()
    return render_template('text_clean.html', active_page='text_clean', counts=get_counters())

@app.route('/qrcode-tool')
def qrcode_tool_page():
    check_and_inc_total_visit()
    return render_template('qrcode_tool.html', active_page='qrcode_tool', counts=get_counters())

@app.route('/client-compress')
def client_compress_page():
    check_and_inc_total_visit()
    return render_template('client_compress.html', active_page='client_compress', counts=get_counters())

@app.route('/time-capsule')
def time_capsule_page():
    check_and_inc_total_visit()
    return render_template('time_capsule.html', active_page='time_capsule', counts=get_counters())

@app.route('/api/inc-password', methods=['POST'])
def inc_password():
    inc_counter('password')
    return '', 204

@app.route('/api/inc-counter/<string:tool_key>', methods=['POST'])
def inc_generic_counter(tool_key):
    if tool_key in ['text_clean', 'client_compress', 'time_capsule']:
        inc_counter(tool_key)
    return '', 204

@app.route('/api/qr-generate', methods=['POST'])
def qr_generate():
    text = request.form.get('qr_text', '').strip()
    fill_color = request.form.get('fill_color', '#000000')
    back_color = request.form.get('back_color', '#ffffff')
    if not text: return "内容不能为空", 400
    try:
        import qrcode
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill_color, back_color=back_color).convert('RGB')
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        inc_counter('qrcode_tool')
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        return "渲染内部错误", 500

@app.route('/api/qr-decode', methods=['POST'])
def qr_decode():
    file = request.files.get('qr_image')
    if not file: return jsonify({'status': 'error', 'message': '未捕获到上传文件'}), 400
    try:
        img_bytes = file.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        data, bbox, straight_qrcode = detector.detectAndDecode(img)
        if data:
            inc_counter('qrcode_tool')
            return jsonify({'status': 'success', 'data': data})
        else:
            return jsonify({'status': 'error', 'message': '未在图片中检测到清晰的二维码矩阵图案'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'底层解码核心运行异常: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
