import os
from flask import Flask, render_template, request, send_file
from PIL import Image
import io

app = Flask(__name__)

UPLOAD_FOLDER = '/tmp/tool_site_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('image_convert.html', active_page='image_convert')

# 1. 图片格式转换
@app.route('/image-convert', methods=['GET', 'POST'])
def image_convert():
    if request.method == 'POST':
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
            
    return render_template('image_convert.html', active_page='image_convert')

# 2. 在线计算机与 3. 密码生成器保持原样
@app.route('/calculator')
def calculator(): return render_template('calculator.html', active_page='calculator')

@app.route('/password')
def password_generator(): return render_template('password.html', active_page='password')


# 4. 升级版轻量文档处理舱 (PDF转Word / PDF转Excel / PDF合并)
@app.route('/doc-convert', methods=['GET', 'POST'])
def doc_convert():
    if request.method == 'POST':
        convert_type = request.form.get('convert_type')
        file = request.files.get('doc_file')
        
        # 功能 A: PDF 转 Word
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
                    
        # 功能 B: 纯 Python 实现 PDF 转 Excel 
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
                                # 过滤掉全空行，写入 Excel
                                if any(row): ws.append(row)
                                
                wb.save(output_path)
                return send_file(output_path, as_attachment=True, download_name=output_name)
            except Exception as e:
                return f"转换失败，可能PDF中不包含标准表格结构。错误: {str(e)}", 500
            finally:
                if os.path.exists(input_path): os.remove(input_path)
                if os.path.exists(output_path): os.remove(output_path)

        # 功能 C: PDF 合并保持原样
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
                    
    return render_template('doc_convert.html', active_page='doc_convert')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
