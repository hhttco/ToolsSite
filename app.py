import os
from flask import Flask, render_template, request, send_file
from PIL import Image
import io
import subprocess
import shutil

app = Flask(__name__)

# 配置临时文件存放目录
UPLOAD_FOLDER = '/tmp/tool_site_files'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/')
def index():
    return render_template('image_convert.html', active_page='image_convert')

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

@app.route('/calculator')
def calculator():
    return render_template('calculator.html', active_page='calculator')

@app.route('/password')
def password_generator():
    return render_template('password.html', active_page='password')

# 📄 新增：文档转换页面与逻辑
@app.route('/doc-convert', methods=['GET', 'POST'])
def doc_convert():
    if request.method == 'POST':
        file = request.files.get('doc_file')
        convert_type = request.form.get('convert_type')
        
        if file and file.filename != '':
            filename = file.filename
            input_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(input_path)
            
            # 功能 A：PDF 转 Word
            if convert_type == 'pdf_to_word' and filename.lower().endswith('.pdf'):
                from pdf2docx import Converter
                output_name = filename.rsplit('.', 1)[0] + '.docx'
                output_path = os.path.join(UPLOAD_FOLDER, output_name)
                
                try:
                    cv = Converter(input_path)
                    cv.convert(output_path, start=0, end=None)
                    cv.close()
                    return send_file(output_path, as_attachment=True, download_name=output_name)
                finally:
                    if os.path.exists(input_path): os.remove(input_path)
                    if os.path.exists(output_path): os.remove(output_path)
            
            # 功能 B：Excel 转 PDF (使用 LibreOffice 命令行后台运行)
            elif convert_type == 'excel_to_pdf' and filename.lower().endswith(('.xlsx', '.xls')):
                output_name = filename.rsplit('.', 1)[0] + '.pdf'
                output_path = os.path.join(UPLOAD_FOLDER, output_name)
                
                try:
                    # 调用 LibreOffice headless 模式一键转换
                    cmd = ['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', UPLOAD_FOLDER, input_path]
                    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return send_file(output_path, as_attachment=True, download_name=output_name)
                finally:
                    if os.path.exists(input_path): os.remove(input_path)
                    if os.path.exists(output_path): os.remove(output_path)
                    
    return render_template('doc_convert.html', active_page='doc_convert')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

