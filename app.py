from flask import Flask, render_template_string, request, jsonify
import json
import os
from datetime import datetime
import threading
import time

app = Flask(__name__)

# 数据文件
DATA_FILE = "homework_data.json"

# 内存缓存 + 线程安全
homeworks = []
data_lock = threading.Lock()
last_save_time = 0
save_queue = []

def load_data():
    """快速加载数据 - 只在启动时执行"""
    global homeworks
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    homeworks = json.loads(content)
                    print(f"✅ 加载了 {len(homeworks)} 条作业记录")
                else:
                    homeworks = []
        else:
            homeworks = []
    except Exception as e:
        print(f"❌ 加载数据失败: {e}")
        homeworks = []

def async_save_data():
    """后台异步保存数据 - 不阻塞主线程"""
    def save_task():
        global last_save_time
        try:
            with data_lock:
                data_to_save = homeworks.copy()
            
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=2)
            
            last_save_time = time.time()
            print(f"💾 后台保存了 {len(data_to_save)} 条记录")
        except Exception as e:
            print(f"❌ 保存失败: {e}")
    
    # 在新线程中执行保存
    thread = threading.Thread(target=save_task, daemon=True)
    thread.start()

def queue_save():
    """排队保存，避免频繁IO"""
    global save_queue
    save_queue.append(time.time())
    
    # 如果5秒内没有保存过，立即保存；否则等待
    if time.time() - last_save_time > 5:
        async_save_data()
    else:
        # 延迟保存，合并多次操作
        if len(save_queue) == 1:  # 第一次触发
            threading.Timer(3.0, delayed_save).start()

def delayed_save():
    """延迟保存，合并操作"""
    async_save_data()

# 启动时加载数据
load_data()

HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>作业登记平台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Microsoft YaHei', Arial, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; 
            padding: 20px; 
        }
        .container { 
            max-width: 1000px; 
            margin: 0 auto; 
            background: white; 
            border-radius: 15px; 
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        }
        .header { 
            text-align: center; 
            margin-bottom: 30px;
            background: linear-gradient(135deg, #2c3e50, #34495e);
            color: white;
            padding: 25px;
            margin: -30px -30px 30px -30px;
            border-radius: 15px 15px 0 0;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin: 20px 0;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
        }
        .stat-card {
            background: white;
            padding: 15px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 3px 10px rgba(0,0,0,0.1);
        }
        .stat-number {
            font-size: 1.8em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .total { color: #3498db; }
        .completed { color: #27ae60; }
        .pending { color: #e74c3c; }
        .form-group { margin: 15px 0; }
        input, button { 
            width: 100%; 
            padding: 12px; 
            margin: 8px 0; 
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 16px;
        }
        input:focus {
            outline: none;
            border-color: #3498db;
        }
        .btn { 
            background: #3498db; 
            color: white; 
            border: none; 
            cursor: pointer; 
            font-weight: bold;
            transition: all 0.3s;
        }
        .btn:hover {
            background: #2980b9;
            transform: translateY(-2px);
        }
        .btn-success { background: #27ae60; }
        .btn-success:hover { background: #219a52; }
        .btn-danger { background: #e74c3c; }
        .btn-danger:hover { background: #c0392b; }
        .homework-item { 
            border: 1px solid #ddd; 
            padding: 20px; 
            margin: 15px 0; 
            border-radius: 10px;
            border-left: 5px solid #3498db;
            transition: all 0.3s;
        }
        .homework-item:hover {
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            transform: translateY(-2px);
        }
        .completed { 
            background: #f0fff4; 
            border-color: #27ae60;
            opacity: 0.9;
        }
        .overdue { 
            background: #ffeaea; 
            border-color: #e74c3c;
        }
        .due-today { 
            background: #fff3cd; 
            border-color: #f39c12;
        }
        .status-badge {
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.8em;
            font-weight: bold;
            margin-left: 10px;
        }
        .status-completed { background: #27ae60; color: white; }
        .status-overdue { background: #e74c3c; color: white; }
        .status-due-today { background: #f39c12; color: white; }
        .alert {
            padding: 15px;
            margin: 15px 0;
            border-radius: 8px;
            display: none;
        }
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 作业登记平台</h1>
            <p>稳定版 - 即时响应 + 数据持久化</p>
        </div>
        
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-number total">0</div>
                <div>总作业数</div>
            </div>
            <div class="stat-card">
                <div class="stat-number completed">0</div>
                <div>已完成</div>
            </div>
            <div class="stat-card">
                <div class="stat-number pending">0</div>
                <div>待完成</div>
            </div>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 30px;">
            <div class="form-section">
                <h3>添加新作业</h3>
                <div class="alert" id="message"></div>
                <form onsubmit="addHomework(event)">
                    <input type="text" id="code" placeholder="作业代号" required>
                    <input type="text" id="subject" placeholder="科目" required>
                    <input type="text" id="content" placeholder="作业内容" required>
                    <input type="text" id="due_date" placeholder="截止日期 DD/MM/YYYY" required>
                    <button type="submit" class="btn">添加作业</button>
                </form>
            </div>
            
            <div class="list-section">
                <h3>作业列表 (<span id="count">0</span>)</h3>
                <div id="homeworkList">加载中...</div>
            </div>
        </div>
        
        <div style="text-align: center; margin-top: 20px; color: #666; font-size: 14px;">
            💡 数据已保存，重启不会丢失 | 最后保存: <span id="lastSave">刚刚</span>
        </div>
    </div>

    <script>
        let lastUpdate = Date.now();
        
        function showMessage(message, type = 'success') {
            const messageEl = document.getElementById('message');
            messageEl.textContent = message;
            messageEl.className = `alert alert-${type}`;
            messageEl.style.display = 'block';
            setTimeout(() => messageEl.style.display = 'none', 3000);
        }

        function updateStats(homeworks) {
            const total = homeworks.length;
            const completed = homeworks.filter(hw => hw.status === 'completed').length;
            const pending = total - completed;
            
            document.querySelector('.stat-number.total').textContent = total;
            document.querySelector('.stat-number.completed').textContent = completed;
            document.querySelector('.stat-number.pending').textContent = pending;
        }

        function getStatusClass(hw) {
            if (hw.status === 'completed') return 'completed';
            
            const dueDate = new Date(hw.due_date.split('/').reverse().join('-'));
            const today = new Date();
            const diffTime = dueDate - today;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            
            if (diffDays < 0) return 'overdue';
            if (diffDays === 0) return 'due-today';
            return '';
        }

        function getStatusText(hw) {
            if (hw.status === 'completed') return '✅ 已完成';
            
            const dueDate = new Date(hw.due_date.split('/').reverse().join('-'));
            const today = new Date();
            const diffTime = dueDate - today;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            
            if (diffDays < 0) return '⚠️ 逾期';
            if (diffDays === 0) return '🔥 今天截止';
            if (diffDays <= 3) return '⏰ 即将截止';
            return '📝 进行中';
        }

        async function loadHomeworks() {
            try {
                const response = await fetch('/api/homeworks');
                const data = await response.json();
                
                if (data.success) {
                    renderHomeworks(data.homeworks || []);
                    updateStats(data.homeworks || []);
                    lastUpdate = Date.now();
                    document.getElementById('lastSave').textContent = '刚刚';
                }
            } catch (error) {
                document.getElementById('homeworkList').innerHTML = '加载失败，请刷新页面';
            }
        }

        function renderHomeworks(homeworks) {
            const container = document.getElementById('homeworkList');
            const countEl = document.getElementById('count');
            
            countEl.textContent = homeworks.length;
            
            if (homeworks.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">暂无作业，添加第一个作业吧！</div>';
                return;
            }

            container.innerHTML = homeworks.map(hw => `
                <div class="homework-item ${getStatusClass(hw)}">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                        <strong style="font-size: 1.1em;">${hw.code}</strong>
                        <span style="background: #3498db; color: white; padding: 4px 12px; border-radius: 15px; font-size: 0.9em;">
                            ${hw.subject}
                        </span>
                    </div>
                    <div style="margin: 10px 0; line-height: 1.5;">${hw.content}</div>
                    <div style="display: flex; justify-content: space-between; color: #666; margin-bottom: 15px;">
                        <span>创建: ${hw.create_date}</span>
                        <span>截止: ${hw.due_date}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span class="status-badge status-${getStatusClass(hw)}">${getStatusText(hw)}</span>
                        <div style="display: flex; gap: 10px;">
                            ${hw.status !== 'completed' ? 
                                `<button class="btn btn-success" onclick="markCompleted(${hw.id})" style="width: auto; padding: 8px 15px;">
                                    ✅ 完成
                                </button>` : ''
                            }
                            <button class="btn btn-danger" onclick="deleteHomework(${hw.id})" style="width: auto; padding: 8px 15px;">
                                🗑️ 删除
                            </button>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        async function addHomework(e) {
            e.preventDefault();
            const homework = {
                code: document.getElementById('code').value,
                subject: document.getElementById('subject').value,
                content: document.getElementById('content').value,
                due_date: document.getElementById('due_date').value
            };

            try {
                const response = await fetch('/api/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(homework)
                });
                const data = await response.json();
                
                if (data.success) {
                    showMessage('作业添加成功！');
                    e.target.reset();
                    loadHomeworks();
                } else {
                    showMessage('添加失败: ' + (data.error || '未知错误'), 'error');
                }
            } catch (error) {
                showMessage('网络错误: ' + error, 'error');
            }
        }

        async function deleteHomework(id) {
            if (!confirm('确定要删除这个作业吗？')) return;
            
            try {
                const response = await fetch('/api/delete/' + id, {method: 'POST'});
                const data = await response.json();
                
                if (data.success) {
                    showMessage('作业删除成功！');
                    loadHomeworks();
                } else {
                    showMessage('删除失败', 'error');
                }
            } catch (error) {
                showMessage('网络错误: ' + error, 'error');
            }
        }

        async function markCompleted(id) {
            try {
                const response = await fetch('/api/complete/' + id, {method: 'POST'});
                const data = await response.json();
                
                if (data.success) {
                    showMessage('作业标记为已完成！');
                    loadHomeworks();
                } else {
                    showMessage('操作失败', 'error');
                }
            } catch (error) {
                showMessage('网络错误: ' + error, 'error');
            }
        }

        // 初始化
        loadHomeworks();
        
        // 自动刷新和更新保存时间
        setInterval(() => {
            const secondsAgo = Math.floor((Date.now() - lastUpdate) / 1000);
            if (secondsAgo > 60) {
                document.getElementById('lastSave').textContent = `${Math.floor(secondsAgo / 60)}分钟前`;
            } else if (secondsAgo > 10) {
                document.getElementById('lastSave').textContent = `${secondsAgo}秒前`;
            }
        }, 5000);
        
        setInterval(loadHomeworks, 15000); // 15秒刷新一次
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return HTML

@app.route('/api/homeworks')
def get_homeworks():
    """获取作业列表 - 快速响应，直接从内存读取"""
    try:
        with data_lock:
            return jsonify({
                'success': True,
                'homeworks': homeworks
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/add', methods=['POST'])
def add_homework():
    """添加作业 - 先更新内存，后异步保存"""
    try:
        data = request.json
        
        # 基础验证
        if not all([data.get('code'), data.get('subject'), data.get('content'), data.get('due_date')]):
            return jsonify({'success': False, 'error': '请填写所有字段'})
        
        # 检查重复
        with data_lock:
            for hw in homeworks:
                if hw['code'] == data['code']:
                    return jsonify({'success': False, 'error': '作业代号已存在'})
            
            # 添加到内存
            homework = {
                'id': len(homeworks) + 1,
                'code': data['code'],
                'subject': data['subject'],
                'content': data['content'],
                'create_date': datetime.now().strftime("%d/%m/%Y"),
                'due_date': data['due_date'],
                'status': 'pending'
            }
            homeworks.append(homework)
        
        # 异步保存到文件（不阻塞响应）
        queue_save()
        
        return jsonify({'success': True, 'message': '添加成功'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete/<int:hw_id>', methods=['POST'])
def delete_homework(hw_id):
    """删除作业"""
    try:
        with data_lock:
            global homeworks
            original_count = len(homeworks)
            homeworks = [hw for hw in homeworks if hw['id'] != hw_id]
            deleted = len(homeworks) < original_count
        
        if deleted:
            queue_save()  # 异步保存
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '作业不存在'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/complete/<int:hw_id>', methods=['POST'])
def complete_homework(hw_id):
    """标记完成"""
    try:
        with data_lock:
            found = False
            for hw in homeworks:
                if hw['id'] == hw_id:
                    hw['status'] = 'completed'
                    found = True
                    break
        
        if found:
            queue_save()  # 异步保存
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '作业不存在'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy', 
        'homeworks_count': len(homeworks),
        'last_save': last_save_time
    })

# Vercel需要
application = app

if __name__ == '__main__':
    app.run(debug=True)
