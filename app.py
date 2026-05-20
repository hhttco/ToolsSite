import os
from flask import Flask, render_template, request, send_file
from PIL import Image
import io
import sqlite3

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp/tool_site_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── 轻量级 SQLite 计数器初始化 ───
DB_PATH = os.path.join(os.path.dirname(__file__), 'counters.db')

def init_db():
    """初始化数据库，创建计数器表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS counters (
            key TEXT PRIMARY KEY,
            count INTEGER DEFAULT 0
        )
    ''')
    # 初始化默认值
    defaults = [('total_visit', 0), ('image_convert', 0), ('doc_convert', 0), ('calculator', 0), ('password', 0)]
    for key, val in defaults:
        cursor.execute('INSERT OR IGNORE INTO counters (key, count) VALUES (?, ?)', (key, val))
    conn.commit()
    conn.close()

def get_and_inc_counter(key, inc_visit=True):
    """增加某个功能的计数，并获取所有计数器的当前值"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 增加当前页面的使用次数
    cursor.execute('UPDATE counters SET count = count + 1 WHERE key = ?', (key,))
    # 如果打开任意页面，全局访问量也同步 +1
    if inc_visit:
        cursor.execute('UPDATE counters SET count = count + 1 WHERE key = "total_visit"')
        
    conn.commit()
    
    # 获取所有的计数器传递给前端
    cursor.execute('SELECT key, count FROM counters')
    counts = dict(cursor.fetchall())
    conn.close()
    return counts

# 程序启动时首先初始化数据库
init_db()


# ─── 页面路由与计数逻辑 ───

# 1. 图片格式转换
@app.route('/', methods=['GET', 'POST'])
@app.route('/image-convert', methods=['GET', 'POST'])
def image_convert():
    # 判定：如果是 POST 提交文件代表“使用了一次功能”，如果是 GET 仅代表“访问了页面”
    is_post = (request.method == 'POST')
    counts = get_and_inc_counter('image_convert', inc_visit=not is_post)
    
    if is_post:
        file = request.files.get('image')
        target_format = request.form.get('format', 'PNG').upper()
        quality = int(request.form.get('quality', 90))
        scale = float(request.form.get('scale', 1.0))
        ico_size = int(request.form.get('ico_size', 32))
        
        if file and file.filename != '':
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
            
    return render_template('image_convert.html', active_page='image_convert', counts=counts)

# 2. 文档转换舱
@app.route('/doc-convert', methods=['GET', 'POST'])
def doc_convert():
    is_post = (request.method == 'POST')
    counts = get_and_inc_counter('doc_convert', inc_visit=not is_post)
    
    if is_post:
        convert_type = request.form.get('convert_type')
        file = request.files.get('doc_file')
        
        if convert_type == 'pdf_to_word' and file and file.filename != '':
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
                    
    return render_template('doc_convert.html', active_page='doc_convert', counts=counts)

# 3. 在线计算机 (每次用户点击等号计算时，前端通过 AJAX 异步触发使用次数 +1)
@app.route('/calculator')
def calculator():
    counts = get_and_inc_counter('calculator', inc_visit=True)
    return render_template('calculator.html', active_page='calculator', counts=counts)

@app.route('/api/inc-calculator', methods=['POST'])
def inc_calculator():
    get_and_inc_counter('calculator', inc_visit=False)
    return '', 204

# 4. 密码生成器 (每次用户点击生成密码时，前端通过 AJAX 异步触发使用次数 +1)
@app.route('/password')
def password_generator():
    counts = get_and_inc_counter('password', inc_visit=True)
    return render_template('password.html', active_page='password', counts=counts)

@app.route('/api/inc-password', methods=['POST'])
def inc_password():
    get_and_inc_counter('password', inc_visit=False)
    return '', 204

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
