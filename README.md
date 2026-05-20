# 🧰 智能交互多功能工具箱站 (ToolsSite)

一款主打**极致轻量化、高颜值、零外部软件依赖（纯 Python 驱动）**的现代化生产力工具导航站。
本项目全面适配 **「✨ 极光 (Light) / 🌙 深邃 (Dark)」** 双主题秒切皮肤，并具备工业级的防刷计数与持久化能力。

🌐 **生产环境示范域名**：[http://x.top](http://x.top)  
📚 **战略级联动外链**：[📚 小说检索舱 ↗](https://12332167.xyz)

---

## 📂 项目文件目录树

```text
my_tools_site/
├── app.py                 # 🧠 Python 后端主程序 (多层IP穿透、SQLite持久化、核心算法)
├── README.md              # 📄 项目开发与部署说明文档
│
├── instance/              # 🔒 Flask 内核级受保护实例数据区 (自动生成)
│   └── counters.db        # 💾 SQLite 轻量数据库文件 (保存IP防刷日志与功能使用次数)
│
└── templates/             # 🎨 现代响应式前端模板夹
    ├── base.html          # 🌟 全局公共母版 (毛玻璃导航栏、二级折叠菜单、总访问量页脚)
    ├── image_convert.html # 🖼️ 功能1：高级图片格式转换
    ├── doc_convert.html   # 📄 功能2：智能文档处理舱
    ├── calculator.html    # 🧮 功能3：在线拟物计算器
    ├── password.html      # 🔐 功能4：智能强密码生成器
    ├── text_clean.html    # 📋 新功能1：文本清洗与去重舱
    ├── qrcode_tool.html   # 🔤 新功能2：现代二维码矩阵舱
    ├── time_capsule.html  # ⏱️ 新功能3：时间戳转换舱
    └── client_compress.html # 🗜️ 新功能4：零负载本地图片压缩
```

---

## 🛠️ 八大核心功能舱详述

### 1. 🖼️ 高级图片格式转换舱
* **功能介绍**：支持 `PNG`、`JPEG`、`WEBP`、`GIF`、`ICO` 五大主流图像格式的全量智能互转。
* **高阶调优**：
  * **压缩质量滑块**：针对 `JPEG/WEBP` 开放 `10% - 100%` 体积画质无级控制。
  * **等比例缩放滑块**：开放 `0.1x - 2.0x` 分辨率极速重绘。
  * **ICO 专属规格**：转为 ICO 图标时自动开启联动，提供 `16x16` 至 `256x256` 黄金像素规格。
* **应用举例**：将手机拍摄的 6MB `PNG` 证件照原图，一键缩放至 `0.5x` 并转为 `WEBP`，体积瞬间降至 150KB，且肉眼几乎无损，完美应对各大政务网上传要求。

### 2. 📄 智能文档处理舱
* **功能介绍**：依托纯 Python 内核（非 LibreOffice 等重型软件）打造的极速绿色文档流操作系统。
* **三大子服务**：
  * **PDF 转 Word**：分析文档内嵌网格及文本坐标，高保真还原为 `.docx` 可编辑文本。
  * **PDF 提取转 Excel**：智能提取 PDF 中嵌套的表格线，过滤空行并完美重组为 `.xlsx` 电子表格。
  * **多 PDF 快速合并**：像粘纸一样在内存中无损拼接多份 PDF 数据流，极速导出。
* **应用举例**：财务人员需要合并 5 份本月的 PDF 电子发票，或需要提取 PDF 报表中的账目到 Excel 中，无需开通各类付费文档会员，在本舱上传即转。

### 3. 🧮 在线拟物计算器
* **功能介绍**：完美复刻经典的苹果 iOS 磨砂黑橘风格，按键带有物理缩放反弹动效。
* **特色机制**：本工具为纯前端 JS 驱动。为了给用户提供绝对纯净的计算环境，本模块**彻底剔除了使用次数统计**，纯粹用于临时连续四则运算及百分比求解。

### 4. 🔐 智能强密码生成器
* **功能介绍**：可定制长度（6-32位）的最高安全级本地随机密码算法。
* **安全机制**：
  * 默认勾选大写字母、小写字母、数字和特殊字符。
  * **首屏静默加载**：进入页面时自动预生成一份密码，该次动作**不计入功能使用次数**，只有点击“重新生成”大按钮时才精准自增。
* **应用举例**：在注册重要加密货币钱包或服务器 Root 密码时，一键生成 16 位包含特殊字符的高强度无规则密码，一键复制，彻底杜绝暴力破解。

### 5. 📋 文本清洗与去重舱
* **功能介绍**：自媒体运营及程序员刚需的超轻量文案批量处理矩阵。
* **核心动作**：支持万行文本一键行去重、快速大小写转换、剔除空白行/首尾空格。
* **全量数据分析看板**：实时、无刷新输出当前文本的：中文字数、英文字数、数字个数、标点符号个数以及段落总数。

### 6. 🔤 现代二维码矩阵舱
* **功能介绍**：高清晰度二维码的动态生成与反编译解码提取双向控制中心。
* **高阶调优**：
  * **色彩自适应**：支持调用原生色彩面板更改二维码矩阵颜色与底色。
  * **图像解码穿透**：上传实拍或手机截图的二维码，后端通过 OpenCV 矩阵探测器一键反编译出隐藏文本链接。
* **应用举例**：输入网址 `https://12332167.xyz`，将矩阵色设为深蓝色，一键打包下载高清 PNG，直接用于线下的传单和展架印刷。

### 7. ⏱️ 现代科幻时间舱
* **功能介绍**：内置酷炫的微暗黑 LED 3D 液晶数字实时时钟，展示当前的北京时间与全球 Unix 核心基准时间戳。
* **应用举例**：网络工程师排查服务器数据库错误日志时，抓到了秒级时间戳 `1779339045`，将其输入左侧面板，一键精准解码出人类直观时间 `2026-05-20 15:30:45`。

### 8. 🗜️ 零负载本地图片压缩舱
* **功能介绍**：极致彻底的 **“服务器 0 带宽、0 负载、0 内存占用”** 隐私防泄密压缩引擎。
* **核心机制**：利用 HTML5 的离屏 `Canvas` 硬件加速技术，完全调用用户本地的电脑/手机硬件完成画面重绘压缩，**图片数据完全不经过网络上传**。
* **自适应指示灯**：配备了拟物化的“原始”与“压缩预期”双资产状态卡片，成功导入图片后会自动唤醒呼吸灯特效并自适应换算文件单位（Bytes/KB/MB）。

---

## ⚙️ 工业级底层技术指标

### 🛡️ 1小时滚动沙盒 IP 校验穿透器
为了防止全站总访问量（`total_visit`）被用户反复点击导航栏工具或者按 F5 恶性刷新所污染，后端集成了代理穿透技术：
* **多层代理穿透**：通过提取 `X-Forwarded-For` 请求头，完美穿透 Nginx 反向代理，锁死外网用户的真实公网 IP。
* **小时级沙盒**：将用户的 IP 和最后到访时间戳记录于 SQLite。同一 IP 只要在 1 小时内有访问记录，全站总访问量数字**死锁不加**。

### 🔒 零漂移动态持久化安全锁 (`instance_path`)
为了避免将服务托管给系统 `systemctl` 守护进程后工作目录发生漂移、导致重启服务数据归零的通病，项目采用了 Flask 官方推荐的标准架构：
* 代码中**不包含任何写死的绝对路径**（极易迁移部署）。
* 显式启用 `instance_relative_config`，强制让数据库和敏感文件常驻在项目根目录下的 `instance/` 独立保护区中。无论怎么重启服务、开机自启，**数据岿然不动，永不重置**。

### 📥 即用即删（零文件残留）
在文档和图片转换路由中，后端全部引入了 `try...finally` 强突围机制。无论转换是成功还是意外失败，暂存在系统 `/tmp/tool_site_files/` 下的原始文件都会在 `finally` 阶段被**瞬间强制执行 `os.remove()` 彻底粉碎**，保障隐私的同时绝不占用服务器 1KB 的无用硬盘空间。

---

## 🚀 云服务器生产环境标准部署指南

本教程以 **Ubuntu / Debian** 系统，域名 **`1.x.top`**，代码存放于 **`/root/my_tools_site`** 为标准进行量产配置。

### 1. 基础依赖与 Python 虚拟环境初始化
```bash
# 安装系统级依赖库
sudo apt update
sudo apt install python3-venv python3-pip nginx-full ffmpeg libsm6 libxext6 -y

# 建立并激活专用的 tool_env 虚拟环境
cd /root
python3 -m venv tool_env
source tool_env/bin/activate

# 依次安装项目所需的全部轻量级纯 Python 库
pip install --upgrade pip
pip install Flask Pillow gunicorn pypdf pdf2docx pdfplumber openpyxl qrcode opencv-python-headless numpy
```

### 2. 配置 systemctl 守护服务
1. 新建服务配置文件：
   ```bash
   sudo nano /etc/systemd/system/my_tools.service
   ```
2. 写入以下生产级守护配置：
   ```ini
   [Unit]
   Description=Gunicorn instance to serve Flask Tools Site
   After=network.target

   [Service]
   User=root
   WorkingDirectory=/root/my_tools_site
   ExecStart=/root/tool_env/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=multi-user.target
   ```
3. 保存退出，并将其激活为**开机自启**：
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start my_tools
   sudo systemctl enable my_tools
   ```

### 3. 配置 Nginx 反向代理
1. 新建并编辑 Nginx 站点配置文件：
   ```bash
   sudo nano /etc/nginx/sites-available/my_tools
   ```
2. 写入以下反向代理与大文件上传放行规则：
   ```nginx
   server {
       listen 80;
       listen [::]:80;
       server_name 1.x.top;

       # 放开大文件上传限制，防止上传大图片、大 PDF 时被 Nginx 拦截
       client_max_body_size 50m;

       location / {
           proxy_pass http://127.0.0.1:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
           
           proxy_connect_timeout 90s;
           proxy_read_timeout 90s;
           proxy_send_timeout 90s;
       }
   }
   ```
3. 激活站点配置并重启 Nginx：
   ```bash
   sudo ln -s /etc/nginx/sites-available/my_tools /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

---

## 🔄 自动化 Git 生产线运维流程
当你在本地修改了前端网页或更新了代码，并成功执行了 `git push` 后，在云服务器上只需执行以下**三行标准流水线指令**，即可在 2 秒内完成公网全量热更新部署：

```bash
cd /root/my_tools_site

# 1. 从 GitHub 一键拉取最新纯净代码
git pull origin main

# 2. 热重启后台常驻的守护进程
sudo systemctl restart my_tools
```
