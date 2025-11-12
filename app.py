from flask import Flask, render_template_string, request, jsonify
import json
import os
from datetime import datetime

app = Flask(__name__)

# 使用内存存储（避免文件IO超时）
homeworks = []

# 极简HTML界面 - 直接嵌入，避免模板文件
HTML = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>作业登记平台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial; background: #f0f2f5; padding: 20px; }
        .container { max-width: 1000px; margin: 0 auto; background: white; border-radius: 10px; padding: 20px; }
        .header { text-align: center; margin-bottom: 20px; }
        .form-group { margin: 10px 0; }
        input, button { width: 100%; padding: 10px; margin: 5px 0; }
        .btn { background: #1890ff; color: white; border: none; border-radius: 5px; cursor: pointer; }
        .btn-success { background: #52c41a; }
        .btn-danger { background: #ff4d4f; }
        .homework-item { border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .completed { background: #f6ffed; border-color: #b7eb8f; }
        .overdue { background: #fff2f0; border-color: #ffccc7; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 作业登记平台</h1>
            <p>简易版 - 数据在内存中（刷新页面会重置）</p>
        </div>
        
        <div class="form-section">
            <h3>添加新作业</h3>
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

    <script>
        async function loadHomeworks() {
            try {
                const response = await fetch('/api/homeworks');
                const data = await response.json();
                renderHomeworks(data.homeworks || []);
            } catch (error) {
                document.getElementById('homeworkList').innerHTML = '加载失败: ' + error;
            }
        }

        function renderHomeworks(homeworks) {
            const container = document.getElementById('homeworkList');
            const countEl = document.getElementById('count');
            
            countEl.textContent = homeworks.length;
            
            if (homeworks.length === 0) {
                container.innerHTML = '<p>暂无作业</p>';
                return;
            }

            container.innerHTML = homeworks.map(hw => `
                <div class="homework-item ${hw.status === 'completed' ? 'completed' : ''}">
                    <strong>${hw.code}</strong> - ${hw.subject}<br>
                    ${hw.content}<br>
                    创建: ${hw.create_date} | 截止: ${hw.due_date}
                    <div style="margin-top: 10px;">
                        ${hw.status !== 'completed' ? 
                            `<button class="btn btn-success" onclick="markCompleted(${hw.id})">完成</button>` : 
                            '<span>✅ 已完成</span>'
                        }
                        <button class="btn btn-danger" onclick="deleteHomework(${hw.id})">删除</button>
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
                    e.target.reset();
                    loadHomeworks();
                } else {
                    alert('添加失败: ' + (data.error || '未知错误'));
                }
            } catch (error) {
                alert('网络错误: ' + error);
            }
        }

        async function deleteHomework(id) {
            if (!confirm('确定删除？')) return;
            try {
                await fetch('/api/delete/' + id, {method: 'POST'});
                loadHomeworks();
            } catch (error) {
                alert('删除失败: ' + error);
            }
        }

        async function markCompleted(id) {
            try {
                await fetch('/api/complete/' + id, {method: 'POST'});
                loadHomeworks();
            } catch (error) {
                alert('操作失败: ' + error);
            }
        }

        // 初始化
        loadHomeworks();
        setInterval(loadHomeworks, 10000); // 10秒刷新
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return HTML

@app.route('/api/homeworks')
def get_homeworks():
    """获取作业列表 - 极简版本"""
    try:
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
    """添加作业 - 极简版本"""
    try:
        data = request.json
        
        # 基础验证
        if not all([data.get('code'), data.get('subject'), data.get('content'), data.get('due_date')]):
            return jsonify({'success': False, 'error': '请填写所有字段'})
        
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
            'due_date': data['due_date'],
            'status': 'pending'
        }
        
        homeworks.append(homework)
        return jsonify({'success': True, 'message': '添加成功'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete/<int:hw_id>', methods=['POST'])
def delete_homework(hw_id):
    """删除作业"""
    try:
        global homeworks
        homeworks = [hw for hw in homeworks if hw['id'] != hw_id]
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/complete/<int:hw_id>', methods=['POST'])
def complete_homework(hw_id):
    """标记完成"""
    try:
        for hw in homeworks:
            if hw['id'] == hw_id:
                hw['status'] = 'completed'
                break
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'homeworks_count': len(homeworks)})

# Vercel需要这个
application = app
