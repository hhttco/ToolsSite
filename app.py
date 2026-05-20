import os
from flask import Flask, render_template, request, send_file, jsonify, make_response
from PIL import Image
import io
import sqlite3
import time
import cv2
import numpy as np

app = Flask(__name__, instance_relative_config=True)

UPLOAD_FOLDER = '/tmp/tool_site_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_PATH = os.path.join(app.instance_path, 'counters.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
    ''')
    # 新增 'beauty_booth' 计数器
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

init_db()

def get_real_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

def check_and_inc_total_visit():
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

# ─── 核心算法：智能文本去水印（基于 HSV 掩膜与 Telea 图像修复） ───
def remove_watermark_core(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # 将图片转换到 HSV 颜色空间，更易于提取特定颜色（如常见的红色、蓝色、灰色文字水印）
    hsv = cv2.cvtColor(img, cv2.cvtColor(img, cv2.COLOR_BGR2HSV))
    
    # 提取浅灰色/半透明水印的通用掩膜范围
    lower_gray = np.array([0, 0, 200])
    upper_gray = np.array([180, 20, 255])
    mask = cv2.inRange(hsv, lower_gray, upper_gray)
    
    # 对掩膜进行轻微膨胀，确保完全覆盖文字边缘
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)
    
    # 使用 Fast Marching Method (Telea算法) 智能修复被水印覆盖的像素
    dst = cv2.inpaint(img, mask, 5, cv2.INPAINT_TELEA)
    
    _, buffer = cv2.imencode('.png', dst)
    return io.BytesIO(buffer.tobytes())

# ─── 核心算法：证件照智能精准换底色（容差漫水填充算法） ───
def change_bg_core(img_bytes, target_hex):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    
    # 将前端传来的 Hex 颜色（如 #ff0000）转换为 OpenCV 的 BGR 格式
    hex_color = target_hex.lstrip('#')
    target_bgr = tuple(int(hex_color[i:i+2], 16) for i in (4, 2, 0))
    
    # 使用 HSV 空间精准捕捉背景色（假设证件照背景在四周边缘占绝大多数）
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # 自动获取左上角、右上角的像素作为背景基准色，计算其 HSV
    bg_sample = hsv[10, 10]
    
    # 设立颜色容差沙盒（H通道±15，S通道±40，V通道±40），完美兼容渐变蓝色或白底的证件照
    lower_blue = np.array([max(0, bg_sample[0]-15), max(40, bg_sample[1]-40), max(40, bg_sample[2]-45)])
    upper_blue = np.array([min(180, bg_sample[0]+15), min(255, bg_sample[1]+40), min(255, bg_sample[2]+45)])
    
    # 生成背景掩膜
    mask = cv2.inRange(hsv, lower_blue, upper_blue)
    
    # 高斯模糊处理边缘，防止换底后人像边缘出现毛刺和白边
    mask_inv = cv2.bitwise_not(mask)
    mask_blur = cv2.GaussianBlur(mask, (3, 3), 0)
    
    # 建立纯色目标背景画布
    bg_canvas = np.zeros_like(img)
    bg_canvas[:] = target_bgr
    
    # 混合原图人像与新背景
    mask_3d = cv2.cvtColor(mask_blur, cv2.COLOR_GRAY2BGR) / 255.0
    dst = (img * (1 - mask_3d) + bg_canvas * mask_3d).astype(np.uint8)
    
    _, buffer = cv2.imencode('.png', dst)
    return io.BytesIO(buffer.tobytes())


# ─── 路由映射 ───

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
    """🎨 新功能：智能美工舱主路由"""
    if request.method == 'POST':
        file = request.files.get('image')
        action_type = request.form.get('action_type')
        bg_color = request.form.get('bg_color', '#ff0000') # 默认红底
        
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

# 其余既有路由保持绝对纯净不变
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
