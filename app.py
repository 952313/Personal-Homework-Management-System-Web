from flask import Flask, render_template_string, request, jsonify, make_response
import json
import os
from datetime import datetime, timedelta
import threading
import time
import hashlib

app = Flask(__name__)

# 数据文件
DATA_FILE = "homework_data.json"
COMPLETION_FILE = "completion_data.json"

# 内存缓存
homeworks = []
completions = {}  # {user_id: {homework_id: completion_data}}
data_lock = threading.Lock()

def load_data():
    """加载数据"""
    global homeworks, completions
    try:
        # 加载作业数据
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    homeworks = json.loads(content)
        
        # 加载完成状态数据
        if os.path.exists(COMPLETION_FILE):
            with open(COMPLETION_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    completions = json.loads(content)
                    
        print(f"✅ 加载了 {len(homeworks)} 条作业记录")
        print(f"✅ 加载了 {len(completions)} 个用户的完成状态")
    except Exception as e:
        print(f"❌ 加载数据失败: {e}")
        homeworks = []
        completions = {}

def async_save_data():
    """异步保存数据"""
    def save_task():
        try:
            with data_lock:
                homework_data = homeworks.copy()
                completion_data = completions.copy()
            
            # 保存作业数据
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(homework_data, f, ensure_ascii=False, indent=2)
            
            # 保存完成状态数据
            with open(COMPLETION_FILE, 'w', encoding='utf-8') as f:
                json.dump(completion_data, f, ensure_ascii=False, indent=2)
                
            print(f"💾 保存了 {len(homework_data)} 作业 + {len(completion_data)} 用户状态")
        except Exception as e:
            print(f"❌ 保存失败: {e}")
    
    thread = threading.Thread(target=save_task, daemon=True)
    thread.start()

def get_user_id(request):
    """生成或获取用户ID"""
    # 首先检查cookie
    user_id = request.cookies.get('user_id')
    
    if not user_id:
        # 基于IP和User-Agent生成指纹
        ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        user_agent = request.headers.get('User-Agent', '')
        fingerprint = f"{ip}-{user_agent}"
        
        # 生成唯一ID
        user_id = hashlib.md5(fingerprint.encode()).hexdigest()[:16]
    
    return user_id

def should_display_homework(hw, user_completion):
    """判断是否应该显示这个作业"""
    # 如果用户已经完成，不显示
    if user_completion.get('completed', False):
        return False
    
    # 检查截止日期
    try:
        due_date = datetime.strptime(hw['due_date'], "%d/%m/%Y")
        today = datetime.now()
        
        # 如果逾期超过3天，不显示
        if due_date.date() < today.date():
            days_overdue = (today.date() - due_date.date()).days
            if days_overdue > 3:
                return False
        
        return True
    except:
        return True

def get_filtered_homeworks(user_id, query_date=None, query_type=None):
    """获取过滤后的作业列表"""
    filtered_homeworks = []
    
    for hw in homeworks:
        user_completion = completions.get(user_id, {}).get(str(hw['id']), {
            'completed': False,
            'completed_at': None
        })
        
        # 如果指定了查询条件
        if query_date and query_type:
            try:
                query_date_obj = datetime.strptime(query_date, "%d/%m/%Y")
                hw_date_str = hw['due_date'] if query_type == 'due' else hw['create_date']
                hw_date_obj = datetime.strptime(hw_date_str, "%d/%m/%Y")
                
                if hw_date_obj.date() == query_date_obj.date():
                    filtered_homeworks.append((hw, user_completion))
            except:
                continue
        else:
            # 正常显示逻辑：未完成且未逾期超过3天
            if should_display_homework(hw, user_completion):
                filtered_homeworks.append((hw, user_completion))
    
    return filtered_homeworks

# 启动时加载数据
load_data()

HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>作业登记平台 - 个人进度</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: 'Microsoft YaHei', Arial, sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh; 
            padding: 20px; 
        }
        .container { 
            max-width: 1200px; 
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
        .user-info {
            background: #e3f2fd;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            text-align: center;
            border-left: 4px solid #2196f3;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            border: 2px solid #f0f0f0;
        }
        .stat-number {
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        .total { color: #2196f3; }
        .my-completed { color: #4caf50; }
        .class-completed { color: #ff9800; }
        .my-pending { color: #f44336; }
        
        .content-grid {
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 30px;
            margin-top: 20px;
        }
        @media (max-width: 768px) {
            .content-grid {
                grid-template-columns: 1fr;
            }
        }
        
        .form-section, .list-section {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 10px;
        }
        
        .query-section {
            background: #fff3cd;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            border-left: 4px solid #ffc107;
        }
        
        .form-group { margin: 15px 0; }
        input, button, select { 
            width: 100%; 
            padding: 12px; 
            margin: 8px 0; 
            border: 2px solid #e9ecef;
            border-radius: 8px;
            font-size: 16px;
        }
        input:focus, select:focus {
            outline: none;
            border-color: #2196f3;
        }
        .btn { 
            background: #2196f3; 
            color: white; 
            border: none; 
            cursor: pointer; 
            font-weight: bold;
            transition: all 0.3s;
        }
        .btn:hover {
            background: #1976d2;
            transform: translateY(-2px);
        }
        .btn-success { background: #4caf50; }
        .btn-success:hover { background: #45a049; }
        .btn-warning { background: #ff9800; }
        .btn-warning:hover { background: #e68900; }
        .btn-outline { 
            background: transparent; 
            border: 2px solid #2196f3;
            color: #2196f3;
        }
        .btn-outline:hover {
            background: #2196f3;
            color: white;
        }
        
        .homework-item { 
            border: 1px solid #e0e0e0; 
            padding: 20px; 
            margin: 15px 0; 
            border-radius: 10px;
            border-left: 5px solid #2196f3;
            transition: all 0.3s;
            background: white;
        }
        .homework-item:hover {
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        .homework-item.completed { 
            border-color: #4caf50;
            background: #f1f8e9;
        }
        .homework-item.overdue { 
            border-color: #f44336;
            background: #ffebee;
        }
        .homework-item.due-today { 
            border-color: #ff9800;
            background: #fff3e0;
        }
        
        .completion-stats {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            padding: 10px;
            background: #f5f5f5;
            border-radius: 5px;
            font-size: 0.9em;
        }
        
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
        
        .status-badge {
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.8em;
            font-weight: bold;
        }
        .status-completed { background: #4caf50; color: white; }
        .status-pending { background: #ff9800; color: white; }
        .status-overdue { background: #f44336; color: white; }
        .status-due-today { background: #ff9800; color: white; }
        
        .filter-info {
            background: #e7f3ff;
            padding: 10px 15px;
            border-radius: 8px;
            margin-bottom: 15px;
            border-left: 4px solid #2196f3;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 作业登记平台 - 个人进度</h1>
            <p>自动隐藏已完成和长期逾期作业 | 支持按日期查询</p>
        </div>
        
        <div class="user-info">
            <strong>👤 你的学习ID:</strong> <span id="userId">生成中...</span>
            <div style="font-size: 0.9em; color: #666; margin-top: 5px;">
                已完成的作业和逾期超过3天的作业会自动隐藏
            </div>
        </div>
        
        <div class="stats" id="stats">
            <div class="stat-card">
                <div class="stat-number total">0</div>
                <div>待完成作业</div>
            </div>
            <div class="stat-card">
                <div class="stat-number my-completed">0</div>
                <div>我已完成</div>
            </div>
            <div class="stat-card">
                <div class="stat-number class-completed">0%</div>
                <div>班级完成率</div>
            </div>
            <div class="stat-card">
                <div class="stat-number my-pending">0</div>
                <div>进行中</div>
            </div>
        </div>
        
        <div class="content-grid">
            <div class="form-section">
                <h3>📝 添加新作业</h3>
                <div class="alert" id="message"></div>
                <form onsubmit="addHomework(event)">
                    <input type="text" id="code" placeholder="作业代号" required>
                    <input type="text" id="subject" placeholder="科目" required>
                    <input type="text" id="content" placeholder="作业内容" required>
                    <input type="text" id="due_date" placeholder="截止日期 DD/MM/YYYY" required>
                    <button type="submit" class="btn">添加作业</button>
                </form>
                
                <div class="query-section">
                    <h4>🔍 按日期查询</h4>
                    <input type="text" id="queryDate" placeholder="查询日期 DD/MM/YYYY" value="{{ today }}">
                    <select id="queryType">
                        <option value="due">按截止日期查询</option>
                        <option value="create">按创建日期查询</option>
                    </select>
                    <button type="button" class="btn btn-warning" onclick="queryHomework()">查询作业</button>
                    <button type="button" class="btn btn-outline" onclick="clearQuery()" style="margin-top: 10px;">显示所有待完成</button>
                </div>
            </div>
            
            <div class="list-section">
                <div id="filterInfo" class="filter-info" style="display: none;">
                    <strong>📅 查询结果:</strong> <span id="queryResultText"></span>
                    <button class="btn btn-outline" onclick="clearQuery()" style="width: auto; padding: 5px 10px; margin-left: 10px;">返回正常视图</button>
                </div>
                <h3>📋 作业列表 (<span id="count">0</span>)</h3>
                <div id="homeworkList">加载中...</div>
            </div>
        </div>
    </div>

    <script>
        let userId = null;
        let currentQuery = null;
        
        // 获取今天日期
        const today = new Date();
        const todayFormatted = `${today.getDate().toString().padStart(2, '0')}/${(today.getMonth() + 1).toString().padStart(2, '0')}/${today.getFullYear()}`;
        document.getElementById('queryDate').value = todayFormatted;
        
        // 获取用户ID
        async function getUserId() {
            try {
                const response = await fetch('/api/user-id');
                const data = await response.json();
                if (data.success) {
                    userId = data.user_id;
                    document.getElementById('userId').textContent = userId;
                }
            } catch (error) {
                console.error('获取用户ID失败:', error);
            }
        }
        
        function showMessage(message, type = 'success') {
            const messageEl = document.getElementById('message');
            messageEl.textContent = message;
            messageEl.className = `alert alert-${type}`;
            messageEl.style.display = 'block';
            setTimeout(() => messageEl.style.display = 'none', 3000);
        }
        
        function updateStats(homeworks) {
            const total = homeworks.length;
            const myCompleted = homeworks.filter(hw => hw.my_completed).length;
            const classCompletedCount = homeworks.filter(hw => hw.completion_count > 0).length;
            const completionRate = total > 0 ? Math.round((classCompletedCount / total) * 100) : 0;
            const myPending = total - myCompleted;
            
            document.querySelector('.stat-number.total').textContent = total;
            document.querySelector('.stat-number.my-completed').textContent = myCompleted;
            document.querySelector('.stat-number.class-completed').textContent = completionRate + '%';
            document.querySelector('.stat-number.my-pending').textContent = myPending;
        }
        
        function getStatusClass(hw) {
            if (hw.my_completed) return 'completed';
            
            const dueDate = new Date(hw.due_date.split('/').reverse().join('-'));
            const today = new Date();
            const diffTime = dueDate - today;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            
            if (diffDays < 0) return 'overdue';
            if (diffDays === 0) return 'due-today';
            return '';
        }
        
        function getStatusText(hw) {
            if (hw.my_completed) {
                return '✅ 已完成';
            }
            
            const dueDate = new Date(hw.due_date.split('/').reverse().join('-'));
            const today = new Date();
            const diffTime = dueDate - today;
            const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            
            if (diffDays < 0) return '⚠️ 逾期';
            if (diffDays === 0) return '🔥 今天截止';
            if (diffDays <= 3) return '⏰ 即将截止';
            return '📝 进行中';
        }
        
        async function loadHomeworks(queryDate = null, queryType = null) {
            if (!userId) return;
            
            try {
                let url = '/api/homeworks';
                if (queryDate && queryType) {
                    url = `/api/query?date=${encodeURIComponent(queryDate)}&type=${queryType}`;
                    currentQuery = { date: queryDate, type: queryType };
                    
                    // 显示查询信息
                    document.getElementById('filterInfo').style.display = 'block';
                    const queryText = queryType === 'due' ? '截止' : '创建';
                    document.getElementById('queryResultText').textContent = `在 ${queryDate} ${queryText}的作业`;
                } else {
                    currentQuery = null;
                    document.getElementById('filterInfo').style.display = 'none';
                }
                
                const response = await fetch(url);
                const data = await response.json();
                
                if (data.success) {
                    renderHomeworks(data.homeworks || []);
                    updateStats(data.homeworks || []);
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
                if (currentQuery) {
                    container.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">没有找到符合条件的作业</div>';
                } else {
                    container.innerHTML = '<div style="text-align: center; padding: 40px; color: #666;">🎉 太棒了！没有待完成的作业</div>';
                }
                return;
            }
            
            container.innerHTML = homeworks.map(hw => {
                const statusClass = getStatusClass(hw);
                const statusText = getStatusText(hw);
                const completionCount = hw.completion_count || 0;
                const totalUsers = hw.total_users || 1;
                const completionRate = Math.round((completionCount / totalUsers) * 100);
                
                return `
                    <div class="homework-item ${statusClass}">
                        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                            <strong style="font-size: 1.1em;">${hw.code}</strong>
                            <span style="background: #2196f3; color: white; padding: 4px 12px; border-radius: 15px; font-size: 0.9em;">
                                ${hw.subject}
                            </span>
                        </div>
                        <div style="margin: 10px 0; line-height: 1.5;">${hw.content}</div>
                        <div style="display: flex; justify-content: space-between; color: #666; margin-bottom: 10px;">
                            <span>创建: ${hw.create_date}</span>
                            <span>截止: ${hw.due_date}</span>
                        </div>
                        
                        <div class="completion-stats">
                            <span>📊 班级完成: ${completionRate}% (${completionCount}/${totalUsers}人)</span>
                            <span class="status-badge status-${statusClass.replace('due-today', 'due-today')}">${statusText}</span>
                        </div>
                        
                        <div style="display: flex; gap: 10px; margin-top: 15px;">
                            ${!hw.my_completed ? 
                                `<button class="btn btn-success" onclick="markCompleted(${hw.id})" style="flex: 2;">
                                    ✅ 标记为我已完成
                                </button>` :
                                `<button class="btn btn-outline" onclick="markIncomplete(${hw.id})" style="flex: 2;">
                                    ↩️ 标记为未完成
                                </button>`
                            }
                            <button class="btn btn-danger" onclick="deleteHomework(${hw.id})" style="flex: 1;">
                                🗑️ 删除
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
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
        
        async function queryHomework() {
            const queryDate = document.getElementById('queryDate').value;
            const queryType = document.getElementById('queryType').value;
            
            if (!queryDate) {
                showMessage('请输入查询日期', 'error');
                return;
            }
            
            loadHomeworks(queryDate, queryType);
        }
        
        function clearQuery() {
            document.getElementById('queryDate').value = todayFormatted;
            loadHomeworks();
        }
        
        async function markCompleted(homeworkId) {
            if (!userId) return;
            
            try {
                const response = await fetch(`/api/complete/${homeworkId}`, {
                    method: 'POST'
                });
                const data = await response.json();
                
                if (data.success) {
                    showMessage('已标记为完成！');
                    loadHomeworks(currentQuery?.date, currentQuery?.type);
                } else {
                    showMessage('操作失败', 'error');
                }
            } catch (error) {
                showMessage('网络错误: ' + error, 'error');
            }
        }
        
        async function markIncomplete(homeworkId) {
            if (!userId) return;
            
            try {
                const response = await fetch(`/api/incomplete/${homeworkId}`, {
                    method: 'POST'
                });
                const data = await response.json();
                
                if (data.success) {
                    showMessage('已标记为未完成');
                    loadHomeworks(currentQuery?.date, currentQuery?.type);
                } else {
                    showMessage('操作失败', 'error');
                }
            } catch (error) {
                showMessage('网络错误: ' + error, 'error');
            }
        }
        
        async function deleteHomework(homeworkId) {
            if (!confirm('确定要删除这个作业吗？')) return;
            
            try {
                const response = await fetch(`/api/delete/${homeworkId}`, {
                    method: 'POST'
                });
                const data = await response.json();
                
                if (data.success) {
                    showMessage('作业删除成功！');
                    loadHomeworks(currentQuery?.date, currentQuery?.type);
                } else {
                    showMessage('删除失败', 'error');
                }
            } catch (error) {
                showMessage('网络错误: ' + error, 'error');
            }
        }
        
        // 初始化
        getUserId().then(() => {
            loadHomeworks();
            setInterval(() => {
                if (!currentQuery) {
                    loadHomeworks();
                }
            }, 15000);
        });
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return HTML

@app.route('/api/user-id')
def get_user_id_endpoint():
    """获取用户ID"""
    user_id = get_user_id(request)
    response = make_response(jsonify({'success': True, 'user_id': user_id}))
    response.set_cookie('user_id', user_id, max_age=365*24*60*60)
    return response

@app.route('/api/homeworks')
def get_homeworks():
    """获取过滤后的作业列表（隐藏已完成和长期逾期）"""
    try:
        user_id = get_user_id(request)
        
        with data_lock:
            filtered = get_filtered_homeworks(user_id)
            homework_data = []
            
            for hw, user_completion in filtered:
                homework_dict = hw.copy()
                
                # 计算完成人数
                completion_count = 0
                for user_completions in completions.values():
                    if str(hw['id']) in user_completions and user_completions[str(hw['id'])]['completed']:
                        completion_count += 1
                
                homework_dict['completion_count'] = completion_count
                homework_dict['total_users'] = len(completions) if completions else 1
                homework_dict['my_completed'] = user_completion['completed']
                
                homework_data.append(homework_dict)
            
            return jsonify({
                'success': True,
                'homeworks': homework_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/query')
def query_homeworks():
    """按日期查询作业"""
    try:
        user_id = get_user_id(request)
        query_date = request.args.get('date')
        query_type = request.args.get('type', 'due')
        
        if not query_date:
            return jsonify({'success': False, 'error': '请提供查询日期'})
        
        with data_lock:
            filtered = get_filtered_homeworks(user_id, query_date, query_type)
            homework_data = []
            
            for hw, user_completion in filtered:
                homework_dict = hw.copy()
                
                # 计算完成人数
                completion_count = 0
                for user_completions in completions.values():
                    if str(hw['id']) in user_completions and user_completions[str(hw['id'])]['completed']:
                        completion_count += 1
                
                homework_dict['completion_count'] = completion_count
                homework_dict['total_users'] = len(completions) if completions else 1
                homework_dict['my_completed'] = user_completion['completed']
                
                homework_data.append(homework_dict)
            
            return jsonify({
                'success': True,
                'homeworks': homework_data
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# 其他API路由保持不变（add, complete, incomplete, delete等）
# 这里省略了其他路由的代码，保持与之前相同

@app.route('/api/add', methods=['POST'])
def add_homework():
    """添加作业"""
    try:
        data = request.json
        
        if not all([data.get('code'), data.get('subject'), data.get('content'), data.get('due_date')]):
            return jsonify({'success': False, 'error': '请填写所有字段'})
        
        with data_lock:
            # 检查重复
            for hw in homeworks:
                if hw['code'] == data['code']:
                    return jsonify({'success': False, 'error': '作业代号已存在'})
            
            # 添加作业
            homework = {
                'id': len(homeworks) + 1,
                'code': data['code'],
                'subject': data['subject'],
                'content': data['content'],
                'create_date': datetime.now().strftime("%d/%m/%Y"),
                'due_date': data['due_date']
            }
            homeworks.append(homework)
        
        async_save_data()
        return jsonify({'success': True, 'message': '添加成功'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/complete/<int:hw_id>', methods=['POST'])
def complete_homework(hw_id):
    """标记作业完成"""
    try:
        user_id = get_user_id(request)
        
        with data_lock:
            if user_id not in completions:
                completions[user_id] = {}
            
            completions[user_id][str(hw_id)] = {
                'completed': True,
                'completed_at': datetime.now().isoformat()
            }
        
        async_save_data()
        return jsonify({'success': True, 'message': '标记完成成功'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/incomplete/<int:hw_id>', methods=['POST'])
def incomplete_homework(hw_id):
    """标记作业未完成"""
    try:
        user_id = get_user_id(request)
        
        with data_lock:
            if user_id in completions and str(hw_id) in completions[user_id]:
                completions[user_id][str(hw_id)] = {
                    'completed': False,
                    'completed_at': None
                }
        
        async_save_data()
        return jsonify({'success': True, 'message': '标记未完成成功'})
            
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
            
            # 同时删除所有用户的完成记录
            for user_completions in completions.values():
                if str(hw_id) in user_completions:
                    del user_completions[str(hw_id)]
        
        if deleted:
            async_save_data()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '作业不存在'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    user_id = get_user_id(request)
    return jsonify({
        'status': 'healthy', 
        'homeworks_count': len(homeworks),
        'users_count': len(completions),
        'current_user': user_id
    })

# Vercel需要
application = app

if __name__ == '__main__':
    app.run(debug=True)
