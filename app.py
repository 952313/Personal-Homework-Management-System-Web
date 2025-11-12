from flask import Flask, render_template_string, request, jsonify, make_response
import json
import os
from datetime import datetime, timedelta
import threading
import time
import hashlib
from collections import defaultdict, deque

app = Flask(__name__)

# 数据文件
DATA_FILE = "homework_data.json"
COMPLETION_FILE = "completion_data.json"
USER_STATS_FILE = "user_stats.json"

# 内存缓存
homeworks = []
completions = {}  # {user_id: {homework_id: completion_data}}
user_stats = {}   # 用户行为统计
data_lock = threading.Lock()

# 删除操作记录（内存中，用于频率限制）
delete_operations = defaultdict(deque)
user_trust_scores = defaultdict(int)  # 用户信任分数

# 防滥用配置
DELETE_RULES = {
    'max_per_hour': 3,      # 每小时最多3次删除
    'max_per_day': 10,      # 每天最多10次删除
    'cooldown_minutes': 5,  # 删除后冷却5分钟
    'require_reason': True, # 必须选择删除原因
    'default_trust_score': 70,  # 初始信任分数
}

DELETE_REASONS = [
    "作业已取消",
    "重复作业", 
    "信息错误",
    "个人原因不需要",
    "其他原因"
]

def load_data():
    """加载所有数据"""
    global homeworks, completions, user_stats, user_trust_scores
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
        
        # 加载用户统计
        if os.path.exists(USER_STATS_FILE):
            with open(USER_STATS_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    user_stats = json.loads(content)
        
        # 初始化信任分数
        for user_id in set(list(completions.keys()) + list(user_stats.keys())):
            user_trust_scores[user_id] = calculate_trust_score(user_id)
                    
        print(f"✅ 加载了 {len(homeworks)} 条作业记录")
        print(f"✅ 加载了 {len(completions)} 个用户的完成状态")
        print(f"✅ 加载了 {len(user_stats)} 个用户的行为统计")
    except Exception as e:
        print(f"❌ 加载数据失败: {e}")
        homeworks = []
        completions = {}
        user_stats = {}

def async_save_data():
    """异步保存数据"""
    def save_task():
        try:
            with data_lock:
                homework_data = homeworks.copy()
                completion_data = completions.copy()
                user_stats_data = user_stats.copy()
            
            # 保存作业数据
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(homework_data, f, ensure_ascii=False, indent=2)
            
            # 保存完成状态数据
            with open(COMPLETION_FILE, 'w', encoding='utf-8') as f:
                json.dump(completion_data, f, ensure_ascii=False, indent=2)
            
            # 保存用户统计
            with open(USER_STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(user_stats_data, f, ensure_ascii=False, indent=2)
                
            print(f"💾 保存了 {len(homework_data)} 作业 + {len(completion_data)} 用户状态")
        except Exception as e:
            print(f"❌ 保存失败: {e}")
    
    thread = threading.Thread(target=save_task, daemon=True)
    thread.start()

def get_user_id(request):
    """生成或获取用户ID"""
    user_id = request.cookies.get('user_id')
    
    if not user_id:
        # 基于IP和User-Agent生成指纹
        ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        user_agent = request.headers.get('User-Agent', '')
        fingerprint = f"{ip}-{user_agent}"
        
        # 生成唯一ID
        user_id = hashlib.md5(fingerprint.encode()).hexdigest()[:16]
    
    return user_id

def update_user_stats(user_id, action, homework_id=None):
    """更新用户行为统计"""
    if user_id not in user_stats:
        user_stats[user_id] = {
            'homeworks_added': 0,
            'homeworks_completed': 0,
            'homeworks_deleted': 0,
            'delete_reasons': defaultdict(int),
            'last_actions': [],
            'trust_score': DELETE_RULES['default_trust_score'],
            'first_seen': datetime.now().isoformat()
        }
    
    stats = user_stats[user_id]
    
    if action == 'add':
        stats['homeworks_added'] += 1
        # 添加作业增加信任分
        user_trust_scores[user_id] = min(100, user_trust_scores.get(user_id, 70) + 2)
    elif action == 'complete':
        stats['homeworks_completed'] += 1
        # 完成作业增加信任分
        user_trust_scores[user_id] = min(100, user_trust_scores.get(user_id, 70) + 3)
    elif action == 'delete':
        stats['homeworks_deleted'] += 1
        # 删除作业减少信任分（但不多）
        user_trust_scores[user_id] = max(0, user_trust_scores.get(user_id, 70) - 2)
    
    # 记录最近操作
    stats['last_actions'].append({
        'action': action,
        'homework_id': homework_id,
        'timestamp': datetime.now().isoformat()
    })
    
    # 只保留最近50个操作
    stats['last_actions'] = stats['last_actions'][-50:]

def calculate_trust_score(user_id):
    """计算用户信任分数"""
    if user_id not in user_stats:
        return DELETE_RULES['default_trust_score']
    
    stats = user_stats[user_id]
    base_score = DELETE_RULES['default_trust_score']
    
    # 基于行为的分数调整
    completed_ratio = stats['homeworks_completed'] / max(1, stats['homeworks_added'] + stats['homeworks_completed'])
    delete_ratio = stats['homeworks_deleted'] / max(1, stats['homeworks_added'] + stats['homeworks_completed'] + stats['homeworks_deleted'])
    
    # 完成率高 → 加分
    if completed_ratio > 0.7:
        base_score += 20
    elif completed_ratio > 0.3:
        base_score += 10
    
    # 删除率过高 → 减分
    if delete_ratio > 0.5:
        base_score -= 30
    elif delete_ratio > 0.3:
        base_score -= 15
    
    return max(0, min(100, base_score))

def can_user_delete(user_id):
    """检查用户是否可以执行删除操作"""
    now = time.time()
    user_deletes = delete_operations[user_id]
    
    # 清理过期的删除记录（1小时前）
    while user_deletes and now - user_deletes[0] > 3600:
        user_deletes.popleft()
    
    # 检查频率限制
    hour_count = len(user_deletes)
    if hour_count >= DELETE_RULES['max_per_hour']:
        return False, f"每小时最多删除 {DELETE_RULES['max_per_hour']} 次（已用：{hour_count}次）"
    
    # 检查冷却时间
    if user_deletes and now - user_deletes[-1] < DELETE_RULES['cooldown_minutes'] * 60:
        remaining = int(DELETE_RULES['cooldown_minutes'] * 60 - (now - user_deletes[-1]))
        return False, f"请等待 {remaining} 秒后再删除"
    
    # 检查信任分数限制
    trust_score = user_trust_scores.get(user_id, DELETE_RULES['default_trust_score'])
    if trust_score < 30:
        return False, "信任分数过低，删除功能已被限制"
    elif trust_score < 60:
        max_daily = 3
    elif trust_score < 80:
        max_daily = 6
    else:
        max_daily = DELETE_RULES['max_per_day']
    
    # 这里可以添加每日限制检查（需要更复杂的日期跟踪）
    
    return True, "可以删除"

def record_delete_operation(user_id):
    """记录删除操作"""
    now = time.time()
    delete_operations[user_id].append(now)

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
    <title>作业登记平台 - 智能防滥用版</title>
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
            border-left: 4px solid #2196f3;
        }
        .trust-score {
            display: inline-block;
            background: #4caf50;
            color: white;
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.9em;
            margin-left: 10px;
        }
        .trust-low { background: #f44336; }
        .trust-medium { background: #ff9800; }
        .trust-high { background: #4caf50; }
        
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
        
        .delete-limits {
            background: #ffebee;
            padding: 15px;
            border-radius: 8px;
            margin-top: 20px;
            border-left: 4px solid #f44336;
            font-size: 0.9em;
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
        .btn-danger { background: #f44336; }
        .btn-danger:hover { background: #d32f2f; }
        .btn-outline { 
            background: transparent; 
            border: 2px solid #2196f3;
            color: #2196f3;
        }
        .btn-outline:hover {
            background: #2196f3;
            color: white;
        }
        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
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
        
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.5);
        }
        .modal-content {
            background-color: white;
            margin: 15% auto;
            padding: 30px;
            border-radius: 10px;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .close {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }
        .close:hover {
            color: black;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 作业登记平台 - 智能防滥用版</h1>
            <p>公平使用 | 信任评分 | 防滥用保护</p>
        </div>
        
        <div class="user-info">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>👤 你的学习ID:</strong> <span id="userId">生成中...</span>
                    <span id="trustScore" class="trust-score">信任分: --</span>
                </div>
                <div style="font-size: 0.9em;">
                    <span id="deleteLimits">删除限制: 加载中...</span>
                </div>
            </div>
            <div style="font-size: 0.9em; color: #666; margin-top: 5px;">
                已完成的作业和逾期超过3天的作业会自动隐藏 | 删除操作受信任分数限制
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
                    <input type="text" id="queryDate" placeholder="查询日期 DD/MM/YYYY">
                    <select id="queryType">
                        <option value="due">按截止日期查询</option>
                        <option value="create">按创建日期查询</option>
                    </select>
                    <button type="button" class="btn btn-warning" onclick="queryHomework()">查询作业</button>
                    <button type="button" class="btn btn-outline" onclick="clearQuery()" style="margin-top: 10px;">显示所有待完成</button>
                </div>
                
                <div class="delete-limits">
                    <h4>⚡ 删除限制</h4>
                    <div>• 每小时最多删除: <strong id="hourLimit">3</strong> 次</div>
                    <div>• 删除冷却时间: <strong id="cooldownTime">5</strong> 分钟</div>
                    <div>• 当前信任等级: <strong id="trustLevel">--</strong></div>
                    <div style="margin-top: 10px; font-size: 0.8em; color: #666;">
                        完成作业可以提升信任分数，获得更多删除权限
                    </div>
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

    <!-- 删除确认模态框 -->
    <div id="deleteModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeDeleteModal()">&times;</span>
            <h3>🗑️ 确认删除作业</h3>
            <p>你将删除作业: <strong id="deleteHomeworkTitle">...</strong></p>
            
            <div class="form-group">
                <label for="deleteReason">请选择删除原因:</label>
                <select id="deleteReason" required>
                    <option value="">请选择原因...</option>
                    <option value="作业已取消">作业已取消</option>
                    <option value="重复作业">重复作业</option>
                    <option value="信息错误">信息错误</option>
                    <option value="个人原因不需要">个人原因不需要</option>
                    <option value="其他原因">其他原因</option>
                </select>
            </div>
            
            <div id="deleteLimitsInfo" style="background: #fff3cd; padding: 10px; border-radius: 5px; margin: 15px 0; font-size: 0.9em;">
                删除限制信息加载中...
            </div>
            
            <div style="display: flex; gap: 10px;">
                <button type="button" class="btn btn-danger" onclick="confirmDelete()" id="confirmDeleteBtn">确认删除</button>
                <button type="button" class="btn btn-outline" onclick="closeDeleteModal()">取消</button>
            </div>
        </div>
    </div>

    <script>
        let userId = null;
        let currentQuery = null;
        let currentDeleteHomeworkId = null;
        let userTrustScore = 70;
        
        // 获取今天日期
        const today = new Date();
        const todayFormatted = `${today.getDate().toString().padStart(2, '0')}/${(today.getMonth() + 1).toString().padStart(2, '0')}/${today.getFullYear()}`;
        document.getElementById('queryDate').value = todayFormatted;
        
        // 获取用户ID和信任分数
        async function getUserId() {
            try {
                const response = await fetch('/api/user-id');
                const data = await response.json();
                if (data.success) {
                    userId = data.user_id;
                    userTrustScore = data.trust_score || 70;
                    document.getElementById('userId').textContent = userId;
                    updateTrustScoreDisplay();
                    updateDeleteLimits();
                }
            } catch (error) {
                console.error('获取用户ID失败:', error);
            }
        }
        
        function updateTrustScoreDisplay() {
            const trustScoreEl = document.getElementById('trustScore');
            trustScoreEl.textContent = `信任分: ${userTrustScore}`;
            
            // 根据分数设置颜色
            trustScoreEl.className = 'trust-score';
            if (userTrustScore < 40) {
                trustScoreEl.classList.add('trust-low');
            } else if (userTrustScore < 70) {
                trustScoreEl.classList.add('trust-medium');
            } else {
                trustScoreEl.classList.add('trust-high');
            }
        }
        
        function updateDeleteLimits() {
            let hourLimit, dailyLimit, trustLevel;
            
            if (userTrustScore < 30) {
                hourLimit = 0;
                dailyLimit = 0;
                trustLevel = '受限';
            } else if (userTrustScore < 60) {
                hourLimit = 2;
                dailyLimit = 5;
                trustLevel = '基础';
            } else if (userTrustScore < 80) {
                hourLimit = 4;
                dailyLimit = 8;
                trustLevel = '标准';
            } else {
                hourLimit = 6;
                dailyLimit = 12;
                trustLevel = '高级';
            }
            
            document.getElementById('hourLimit').textContent = hourLimit;
            document.getElementById('trustLevel').textContent = trustLevel;
            document.getElementById('deleteLimits').textContent = `删除权限: ${trustLevel}等级`;
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
                            <button class="btn btn-danger" onclick="openDeleteModal(${hw.id}, '${hw.code} - ${hw.subject}')" style="flex: 1;">
                                🗑️ 删除
                            </button>
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        // 删除相关函数
        function openDeleteModal(homeworkId, homeworkTitle) {
            currentDeleteHomeworkId = homeworkId;
            document.getElementById('deleteHomeworkTitle').textContent = homeworkTitle;
            document.getElementById('deleteReason').value = '';
            
            // 检查删除限制
            checkDeleteLimits().then(limits => {
                document.getElementById('deleteLimitsInfo').innerHTML = limits.message;
                document.getElementById('confirmDeleteBtn').disabled = !limits.canDelete;
            });
            
            document.getElementById('deleteModal').style.display = 'block';
        }
        
        function closeDeleteModal() {
            document.getElementById('deleteModal').style.display = 'none';
            currentDeleteHomeworkId = null;
        }
        
        async function checkDeleteLimits() {
            try {
                const response = await fetch('/api/check-delete-limits');
                const data = await response.json();
                return data;
            } catch (error) {
                return { canDelete: false, message: '检查删除限制时出错' };
            }
        }
        
        async function confirmDelete() {
            const reason = document.getElementById('deleteReason').value;
            if (!reason) {
                alert('请选择删除原因');
                return;
            }
            
            try {
                const response = await fetch(`/api/delete/${currentDeleteHomeworkId}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ reason: reason })
                });
                const data = await response.json();
                
                if (data.success) {
                    showMessage('作业删除成功！');
                    closeDeleteModal();
                    loadHomeworks(currentQuery?.date, currentQuery?.type);
                    // 更新信任分数显示
                    getUserId();
                } else {
                    showMessage('删除失败: ' + data.error, 'error');
                }
            } catch (error) {
                showMessage('网络错误: ' + error, 'error');
            }
        }
        
        // 其他函数保持不变
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
                    getUserId(); // 更新信任分数
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
                    getUserId(); // 更新信任分数
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
        
        // 点击模态框外部关闭
        window.onclick = function(event) {
            const modal = document.getElementById('deleteModal');
            if (event.target == modal) {
                closeDeleteModal();
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
    """获取用户ID和信任分数"""
    user_id = get_user_id(request)
    trust_score = user_trust_scores.get(user_id, DELETE_RULES['default_trust_score'])
    
    response = make_response(jsonify({
        'success': True, 
        'user_id': user_id,
        'trust_score': trust_score
    }))
    response.set_cookie('user_id', user_id, max_age=365*24*60*60)
    return response

@app.route('/api/check-delete-limits')
def check_delete_limits():
    """检查用户删除限制"""
    user_id = get_user_id(request)
    can_delete, message = can_user_delete(user_id)
    trust_score = user_trust_scores.get(user_id, DELETE_RULES['default_trust_score'])
    
    return jsonify({
        'success': True,
        'canDelete': can_delete,
        'message': message,
        'trust_score': trust_score
    })

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

@app.route('/api/add', methods=['POST'])
def add_homework():
    """添加作业"""
    try:
        data = request.json
        user_id = get_user_id(request)
        
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
        
        # 更新用户统计
        update_user_stats(user_id, 'add', homework['id'])
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
        
        # 更新用户统计
        update_user_stats(user_id, 'complete', hw_id)
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
    global homeworks
    """删除作业（带防滥用检查）"""
    try:
        user_id = get_user_id(request)
        data = request.json
        
        # 检查删除限制
        can_delete, message = can_user_delete(user_id)
        if not can_delete:
            return jsonify({'success': False, 'error': message})
        
        # 检查删除原因
        if DELETE_RULES['require_reason'] and (not data or 'reason' not in data or not data['reason']):
            return jsonify({'success': False, 'error': '请提供删除原因'})
        
        with data_lock:
            # 查找作业信息
            homework_to_delete = None
            for hw in homeworks:
                if hw['id'] == hw_id:
                    homework_to_delete = hw
                    break
            
            if not homework_to_delete:
                return jsonify({'success': False, 'error': '作业不存在'})
            
            # 执行删除
            homeworks = [hw for hw in homeworks if hw['id'] != hw_id]
            
            # 同时删除所有用户的完成记录
            for user_completions in completions.values():
                if str(hw_id) in user_completions:
                    del user_completions[str(hw_id)]
        
        # 记录删除操作
        record_delete_operation(user_id)
        
        # 更新用户统计
        update_user_stats(user_id, 'delete', hw_id)
        if data and 'reason' in data:
            user_stats[user_id]['delete_reasons'][data['reason']] += 1
        
        async_save_data()
        return jsonify({'success': True, 'message': '作业删除成功'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    user_id = get_user_id(request)
    return jsonify({
        'status': 'healthy', 
        'homeworks_count': len(homeworks),
        'users_count': len(completions),
        'current_user': user_id,
        'trust_score': user_trust_scores.get(user_id, 70)
    })

# Vercel需要
application = app

if __name__ == '__main__':
    app.run(debug=True)
