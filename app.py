from flask import Flask, render_template_string
import os

app = Flask(__name__)

# 极简HTML模板
MINIMAL_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>作业平台测试</title>
    <style>
        body { font-family: Arial; padding: 40px; }
        .success { color: green; font-size: 24px; }
    </style>
</head>
<body>
    <h1>🚀 作业登记平台 - 测试页面</h1>
    <p class="success">✅ Flask应用运行成功！</p>
    <p>环境: {{ environment }}</p>
    <p>时间: {{ timestamp }}</p>
    <div id="status">正在检查API...</div>
    
    <script>
        // 测试API连接
        fetch('/api/health')
            .then(response => response.json())
            .then(data => {
                document.getElementById('status').innerHTML = 
                    '✅ API连接正常: ' + JSON.stringify(data);
            })
            .catch(error => {
                document.getElementById('status').innerHTML = 
                    '❌ API连接失败: ' + error;
            });
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    from datetime import datetime
    return render_template_string(MINIMAL_HTML, 
        environment=os.environ.get('VERCEL', 'local'),
        timestamp=datetime.now().isoformat()
    )

@app.route('/api/health')
def health():
    return {"status": "healthy", "service": "homework-platform"}

@app.route('/api/test')
def test():
    return {"message": "API测试成功", "data": [1, 2, 3]}

if __name__ == '__main__':
    app.run(debug=True)
