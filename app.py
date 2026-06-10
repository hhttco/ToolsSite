import os
from flask import Flask, render_template, request, send_file, jsonify, make_response
from PIL import Image
from functools import wraps
from threading import Lock
import io
import sqlite3
import time
import cv2
import numpy as np

app = Flask(__name__)

# 全局存储 IP 访问时间戳
# 格式: { "127.0.0.1": [timestamp1, timestamp2, ...] }
IP_RECORDS = {}
ip_lock = Lock()  # 确保多线程安全

# ─── 💡 新增：小黑屋（封禁）存储字典 ───
# 格式：{ "恶意IP": 封禁结束的时间戳(float) }
IP_BLACKLIST = {}

def limit_by_ip(max_requests=30):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_ip = get_real_ip()  
            current_time = time.time()
            
            with ip_lock:
                # ─── 🛑 第一步：高能前置拦截（小黑屋检查） ───
                if user_ip in IP_BLACKLIST:
                    # 检查封禁时间是否到期
                    if current_time < IP_BLACKLIST[user_ip]:
                        # 计算小黑屋还剩多少分钟释放
                        time_left_mins = max(1, int((IP_BLACKLIST[user_ip] - current_time) / 60))
                        # print(f"[频限触发监控] 当前访客 IP: {user_ip} 还在小黑屋中")
                        return jsonify({
                            "status": "error",
                            "message": f"系统检测到您存在恶意刷接口的行为，IP已被封禁！请在 {time_left_mins} 分钟后再试。"
                        }), 403 # 💡 使用 403 明确拒绝访问
                    else:
                        # 封禁时间已过，释放出狱
                        del IP_BLACKLIST[user_ip]

                # ─── 🔄 第二步：正常滚动窗口逻辑 ───
                if user_ip not in IP_RECORDS:
                    IP_RECORDS[user_ip] = []
                
                # 过滤掉 60 秒之前的历史记录
                IP_RECORDS[user_ip] = [t for t in IP_RECORDS[user_ip] if current_time - t < 60.0]
                
                # ─── 🚨 第三步：触发流控及惩罚判定 ───
                if len(IP_RECORDS[user_ip]) >= max_requests:
                    # 【核心惩罚点】：
                    # 如果当前窗口里的请求数，已经超过了上限 3 次（说明对方无视了429提示，在用脚本顶着报错疯狂对轰）
                    if len(IP_RECORDS[user_ip]) >= (max_requests + 3):
                        # 立刻关进小黑屋，封禁 3600 秒（1小时）
                        IP_BLACKLIST[user_ip] = current_time + 3600.0
                        
                        # print(f"[频限触发监控] 当前访客 IP: {user_ip} 已经关进了小黑屋")
                        return jsonify({
                            "status": "error",
                            "message": "警告：由于您无视流控限制持续高频请求，已被系统判定为恶意攻击，IP正式封禁1小时！"
                        }), 403
                    
                    # 还没达到恶意判定线，正常给对方记录这次越界，并返回 429 和倒计时
                    IP_RECORDS[user_ip].append(current_time)
                    
                    remaining_time = max(1, int(60.0 - (current_time - IP_RECORDS[user_ip][0])))
                    return jsonify({
                        "status": "error",
                        "message": f"操作太频繁，请在 {remaining_time} 秒后再试。"
                    }), 429
                
                # ─── ✅ 第四步：正常请求，安全放行 ───
                IP_RECORDS[user_ip].append(current_time)
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

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
    """证件照换底色核心算法（多区域采样 + 边缘高斯羽化融合）"""
    try:
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return io.BytesIO(img_bytes)

        # 1. 💡 修复色彩解析核心冲突：正确按 RGB (0, 2, 4) 提取并重构成 OpenCV 需要的 BGR 通道
        hex_color = target_hex.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        target_bgr = (b, g, r) # OpenCV 色彩空间为 BGR

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # 2. 💡 修复固定单像素采样失效：通过获取左上角与右上角 5x5 的综合均值来捕获真实背景色基准
        bg_sample_left = hsv[0:5, 0:5]
        bg_sample_right = hsv[0:5, -5:]
        bg_combined = np.concatenate((bg_sample_left, bg_sample_right), axis=0)
        mean_hsv = np.mean(bg_combined, axis=(0, 1))

        # 3. 动态配置证件背景识别色彩屏障
        lower_blue = np.array([max(0, mean_hsv[0] - 15), max(30, mean_hsv[1] - 55), max(30, mean_hsv[2] - 55)])
        upper_blue = np.array([min(180, mean_hsv[0] + 15), min(255, mean_hsv[1] + 55), min(255, mean_hsv[2] + 55)])

        mask = cv2.inRange(hsv, lower_blue, upper_blue)

        # 4. 消除孔洞，平滑发丝，进行高斯羽化软边缘融合，消除换底后的白边和硬锯齿
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask_blur = cv2.GaussianBlur(mask, (5, 5), 0)

        # 5. 生成纯色画布并按权重比例线性融合
        bg_canvas = np.zeros_like(img)
        bg_canvas[:] = target_bgr

        mask_3d = cv2.cvtColor(mask_blur, cv2.COLOR_GRAY2BGR) / 255.0
        dst = (img * (1.0 - mask_3d) + bg_canvas * mask_3d).astype(np.uint8)

        _, buffer = cv2.imencode('.png', dst)
        return io.BytesIO(buffer.tobytes())
    except Exception as e:
        # 出错时安全降级回原图，防服务中断
        return io.BytesIO(img_bytes)


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
                
                # ─── 核心修复：先读入内存，再由 finally 安全物理删除 ───
                return_data = io.BytesIO()
                with open(output_path, 'rb') as f:
                    return_data.write(f.read())
                return_data.seek(0)
                
                return send_file(return_data, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', as_attachment=True, download_name=output_name)
            except Exception as e:
                return f"转换失败: {str(e)}", 500
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
                
                # ─── 核心修复：先读入内存，再由 finally 安全物理删除 ───
                return_data = io.BytesIO()
                with open(output_path, 'rb') as f:
                    return_data.write(f.read())
                return_data.seek(0)
                
                return send_file(return_data, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=output_name)
            except Exception as e:
                return f"转换失败: {str(e)}", 500
            finally:
                if os.path.exists(input_path): os.remove(input_path)
                if os.path.exists(output_path): os.remove(output_path)

        # 🌐 新增核心：PDF 转换成 HTML 网页（支持真正的 HTML 表格还原！）
        elif convert_type == 'pdf_to_html' and file and file.filename != '':
            inc_counter('doc_convert')
            input_path = os.path.join(UPLOAD_FOLDER, file.filename)
            output_name = file.filename.rsplit('.', 1)[0] + '.html'
            output_path = os.path.join(UPLOAD_FOLDER, output_name)
            file.save(input_path)
            try:
                import fitz  # PyMuPDF 用于基础文本样式
                import pdfplumber  # 用于提取真正的表格结构
                
                # 开始拼接标准的 HTML5 页面结构（内置优雅的现代表格样式）
                html_content = (
                    "<!DOCTYPE html>\n<html>\n<head>\n"
                    '<meta charset="utf-8">\n'
                    f"<title>{output_name}</title>\n"
                    "<style>\n"
                    "  body { background-color: #f7fafc; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #2d3748; }\n"
                    "  .pdf-page { background: white; margin: 20px auto; padding: 40px; max-width: 900px; "
                    "box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-radius: 8px; min-height: 500px; }\n"
                    "  /* ── 现代高颜值表格样式 ── */\n"
                    "  table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; text-align: left; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-radius: 6px; overflow: hidden; }\n"
                    "  th { background-color: #3182ce; color: white; font-weight: bold; padding: 12px 15px; }\n"
                    "  td { padding: 10px 15px; border-bottom: 1px solid #e2e8f0; }\n"
                    "  tr:nth-version(even) { background-color: #f7fafc; }\n"
                    "  tr:hover { background-color: #edf2f7; }\n"
                    "</style>\n</head>\n<body>\n"
                )
                
                # 同时打开两个转换器
                doc_fitz = fitz.open(input_path)
                with pdfplumber.open(input_path) as doc_plumber:
                    
                    for page_idx in range(len(doc_fitz)):
                        page_fitz = doc_fitz[page_idx]
                        page_plumber = doc_plumber.pages[page_idx]
                        
                        html_content += f'<div class="pdf-page" id="page_{page_idx + 1}">\n'
                        
                        # 1. 检查当前页是否存在表格
                        tables = page_plumber.extract_tables()
                        
                        if tables:
                            # 存在表格：生成真正的 <table> 标签
                            for table in tables:
                                html_content += "<table>\n"
                                for row_idx, row in enumerate(table):
                                    html_content += "  <tr>\n"
                                    for cell in row:
                                        # 防止单元格为 None 导致报错，转为空字符串
                                        cell_text = str(cell).replace('\n', '<br>') if cell is not None else ""
                                        if row_idx == 0:
                                            html_content += f"    <th>{cell_text}</th>\n"
                                        else:
                                            html_content += f"    <td>{cell_text}</td>\n"
                                    html_content += "  </tr>\n"
                                html_content += "</table>\n"
                        else:
                            # 2. 如果没有表格，则还原纯文本的版面样式
                            page_html = page_fitz.get_text("html")
                            html_content += page_html
                            
                        html_content += '</div>\n'
                
                html_content += "</body>\n</html>"
                doc_fitz.close()
                
                # 写入临时的物理输出文件
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                # 复用安全流机制
                return_data = io.BytesIO()
                with open(output_path, 'rb') as f:
                    return_data.write(f.read())
                return_data.seek(0)
                
                return send_file(
                    return_data, 
                    mimetype='text/html', 
                    as_attachment=True, 
                    download_name=output_name
                )
            except Exception as e:
                return f"转换失败: {str(e)}", 500
            finally:
                if os.path.exists(input_path): os.remove(input_path)
                if os.path.exists(output_path): os.remove(output_path)

        elif convert_type == 'pdf_merge':
            files = request.files.getlist('merge_files')
            if files and len(files) > 1:
                inc_counter('doc_convert')
            
                # ─── 核心修复：在新版 pypdf 中，使用 PdfWriter 来处理合并 ───
                from pypdf import PdfWriter
                writer = PdfWriter()
                try:
                    # 纯内存操作：直接把上传的文件流追加到 writer 中
                    for f in files:
                        if f.filename != '':
                            writer.append(f.stream)
                
                    # 创建内存文件对象
                    return_data = io.BytesIO()
                    writer.write(return_data)
                    writer.close()
                
                    # 将指针复位，供 Flask 读取并安全发送
                    return_data.seek(0)
                
                    return send_file(
                        return_data, 
                        mimetype='application/pdf', 
                        as_attachment=True, 
                        download_name='合并文档.pdf'
                    )
                except Exception as e:
                    return f"合并失败: {str(e)}", 500

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
@limit_by_ip(5)  # 👈 直接加在这里，GET 和 POST 都会共享这 5 次限制
def inc_password():
    inc_counter('password')
    return '', 204

@app.route('/api/inc-counter/<string:tool_key>', methods=['POST'])
@limit_by_ip(5)  # 👈 直接加在这里，GET 和 POST 都会共享这 5 次限制
def inc_generic_counter(tool_key):
    if tool_key in ['text_clean', 'client_compress', 'time_capsule']:
        inc_counter(tool_key)
    return '', 204

@app.route('/api/qr-generate', methods=['POST'])
@limit_by_ip(5)  # 👈 直接加在这里，GET 和 POST 都会共享这 5 次限制
def qr_generate():
    text = request.form.get('qr_text', '').strip()
    fill_color = request.form.get('fill_color', '#000000')
    back_color = request.form.get('back_color', '#ffffff')
    if not text: return "内容不能为空", 400
    try:
        import qrcode
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill_color, back_color=back_color)
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        inc_counter('qrcode_tool')
        return send_file(img_io, mimetype='image/png', as_attachment=True, download_name='qrcode.png')
    except Exception as e:
        return f"生成失败: {str(e)}", 500

@app.route('/api/qr-decode', methods=['POST'])
@limit_by_ip(5)  # 👈 直接加在这里，GET 和 POST 都会共享这 5 次限制
def qr_decode():
    if 'qr_image' not in request.files:
        return jsonify({'status': 'error', 'message': '未检测到上传的图片文件'}), 400
        
    file = request.files['qr_image']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '未选择任何图片'}), 400

    try:
        # 1. 直接将文件流转换为字节数组，再用 OpenCV 读取到内存
        file_bytes = np.frombuffer(file.read(), np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        
        if img is None:
            return jsonify({'status': 'error', 'message': '图片文件可能已损坏，无法解析。'}), 400

        # 2. 启用 OpenCV 强大的内置二维码探测器
        detector = cv2.QRCodeDetector()
        qr_data, points, straight_qrcode = detector.detectAndDecode(img)
        
        # 3. 如果没扫出来，尝试进行全图灰度对比度增强处理（防止实拍照片光线暗淡）
        if not qr_data:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            qr_data, points, straight_qrcode = detector.detectAndDecode(gray)

        # 4. 判断最终是否捕获到数据
        if not qr_data:
            return jsonify({'status': 'error', 'message': '未检测到有效的二维码。请确保图片清晰且正对镜头。'}), 200
            
        # 5. 安全自增计数
        try:
            inc_counter('qrcode_tool')
        except Exception as e:
            print(f"计数器自增失败: {e}")

        # 6. 返回数据给前端归位
        return jsonify({
            'status': 'success',
            'data': qr_data
        }), 200

    except Exception as e:
        return jsonify({'status': 'error', 'message': f'解析核心崩溃: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
