import os
from flask import Flask, render_template, request, send_file, jsonify, make_response
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
    # A. 基础功能计数表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
    ''')
    # 初始化 6 个基础计数组件（剔除了不需要统计的计算机）
    defaults = [
        ('total_visit', 0), 
        ('image_convert', 0), 
        ('doc_convert', 0), 
        ('password', 0),
        ('text_clean', 0),
        ('qrcode_tool', 0)
    ]
    for key, val in defaults:
        cursor.execute('INSERT OR IGNORE INTO counters (key, count) VALUES (?, ?)', (key, val))
        
    # B. 核心新增：轻量级 IP 防刷沙盒日志表
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
    
    # 查找此 IP 是否在沙盒中
    cursor.execute('SELECT last_visit_time FROM ip_logs WHERE ip = ?', (user_ip,))
    row = cursor.fetchone()
    
    if row is None:
        # 情况 A: 这是一个全新的 IP，直接加1，并插入沙盒
        cursor.execute('INSERT INTO ip_logs (ip, last_visit_time) VALUES (?, ?)', (user_ip, current_time))
        conn.commit()
        conn.close()
        inc_counter('total_visit')
    else:
        last_visit = row[0]
        # 情况 B: 该 IP 曾经来过，检查时间是否超过 1 小时
        if current_time - last_visit > one_hour_secs:
            # 超过一小时，重新计入一次，并更新时间戳
            cursor.execute('UPDATE ip_logs SET last_visit_time = ? WHERE ip = ?', (current_time, user_ip))
            conn.commit()
            conn.close()
            inc_counter('total_visit')
        else:
            # 在一小时滚动限制期内，静默放行，总访问量绝对不加
            conn.close()


# ─── 页面路由与各个功能舱舱位控制 ───

# 1. 功能菜单：高级图片格式转换
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
            inc_counter('image_convert')  # 仅在真正开始转换时功能次数 +1
            
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


# 2. 功能菜单：智能文档处理舱
@app.route('/doc-convert', methods=['GET', 'POST'])
def doc_convert():
    if request.method == 'POST':
        convert_type = request.form.get('convert_type')
        file = request.files.get('doc_file')
        
        # 功能 A: PDF 转 Word
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
                    
        # 功能 B: PDF 转 Excel 
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

        # 功能 C: PDF 合并
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


# 3. 功能菜单：在线拟物计算机（不统计该功能使用次数）
@app.route('/calculator')
def calculator():
    check_and_inc_total_visit()
    return render_template('calculator.html', active_page='calculator', counts=get_counters())


# 4. 功能菜单：智能强密码生成器
@app.route('/password')
def password_generator():
    check_and_inc_total_visit()
    return render_template('password.html', active_page='password', counts=get_counters())


# 5. 折叠扩展子功能：文本清洗与去重舱
@app.route('/text-clean')
def text_clean_page():
    check_and_inc_total_visit()
    return render_template('text_clean.html', active_page='text_clean', counts=get_counters())


# 6. 折叠扩展子功能：现代二维码矩阵舱
@app.route('/qrcode-tool')
def qrcode_tool_page():
    check_and_inc_total_visit()
    return render_template('qrcode_tool.html', active_page='qrcode_tool', counts=get_counters())


# 7. 折叠扩展子功能：本地零负载图片压缩
@app.route('/client-compress')
def client_compress_page():
    check_and_inc_total_visit()
    return render_template('client_compress.html', active_page='client_compress', counts=get_counters())


# 8. 折叠扩展子功能：现代科幻时间舱
@app.route('/time-capsule')
def time_capsule_page():
    check_and_inc_total_visit()
    return render_template('time_capsule.html', active_page='time_capsule', counts=get_counters())


# ─── 异步 AJAX 纯前端交互专用轻量级计数器 API ───

@app.route('/api/inc-password', methods=['POST'])
def inc_password():
    inc_counter('password')
    return '', 204

@app.route('/api/inc-counter/<string:tool_key>', methods=['POST'])
def inc_generic_counter(tool_key):
    """用于文本清洗、本地压缩、时间转换等工具在用户执行成功时异步调用 +1"""
    if tool_key in ['text_clean', 'client_compress', 'time_capsule']:
        inc_counter(tool_key)
    return '', 204

@app.route('/api/qr-generate', methods=['POST'])
def qr_generate():
    """高保真 RGB 通道彩色二维码生成器接口"""
    text = request.form.get('qr_text', '').strip()
    fill_color = request.form.get('fill_color', '#000000')
    back_color = request.form.get('back_color', '#ffffff')
    
    if not text:
        return "内容不能为空", 400
        
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(text)
        qr.make(fit=True)
        
        # 渲染出位图，并强制升级通道深度为 RGB 真彩色，彻底防止 PNG 保存报错
        img = qr.make_image(fill_color=fill_color, back_color=back_color).convert('RGB')
        
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        # 仅在二维码成功渲染并下发时，才执行计数 +1
        inc_counter('qrcode_tool')
        return send_file(img_io, mimetype='image/png')
    except Exception as e:
        print(f"二维码矩阵渲染异常: {str(e)}")
        return "渲染内部错误", 500

@app.route('/api/qr-decode', methods=['POST'])
def qr_decode():
    """利用轻量 Pillow 原生像素分析或系统集成库的二维码读取接口"""
    file = request.files.get('qr_image')
    if not file:
        return jsonify({'status': 'error', 'message': '未捕获到上传文件'}), 400
        
    try:
        # 在 Linux 纯净环境下，优先使用免外部动态依赖的高效 OpenCV/Pillow 探测方案
        import cv2
        import numpy as np
        
        img_bytes = file.read()
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # 激活 OpenCV 原生高精度二维码矩阵探测仪
        detector = cv2.QRCodeDetector()
        data, bbox, straight_qrcode = detector.detectAndDecode(img)
        
        if data:
            inc_counter('qrcode_tool') # 成功读取，次数 +1
            return jsonify({'status': 'success', 'data': data})
        else:
            return jsonify({'status': 'error', 'message': '未在图片中检测到清晰的二维码矩阵图案'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'底层解码核心运行异常: {str(e)}'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
