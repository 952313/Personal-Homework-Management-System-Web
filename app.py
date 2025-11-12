from flask import Flask, render_template, request, jsonify, send_file
import json
import os
from datetime import datetime
from threading import Lock

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# 线程锁确保数据安全
data_lock = Lock()

class HomeworkManager:
    def __init__(self):
        self.data_file = "homework_data.json"
        self.homeworks = []
        self.load_data()
    
    def load_data(self):
        """加载作业数据"""
        try:
            with data_lock:
                if os.path.exists(self.data_file):
                    with open(self.data_file, 'r', encoding='utf-8') as f:
                        data = f.read().strip()
                        if data:
                            self.homeworks = json.loads(data)
                        else:
                            self.homeworks = []
                else:
                    self.homeworks = []
                    # 创建初始数据文件
                    self.save_data()
        except Exception as e:
            print(f"加载数据错误: {e}")
            self.homeworks = []
    
    def save_data(self):
        """保存作业数据"""
        try:
            with data_lock:
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(self.homeworks, f, ensure_ascii=False, indent=2)
                return True
        except Exception as e:
            print(f"保存数据错误: {e}")
            return False
    
    def add_homework(self, code, subject, content, due_date):
        """添加新作业"""
        homework = {
            'id': len(self.homeworks) + 1,
            'code': code,
            'subject': subject,
            'content': content,
            'create_date': datetime.now().strftime("%d/%m/%Y"),
            'due_date': due_date,
            'status': 'pending'
        }
        self.homeworks.append(homework)
        return self.save_data()
    
    def delete_homework(self, homework_id):
        """删除作业"""
        try:
            homework_id = int(homework_id)
            self.homeworks = [hw for hw in self.homeworks if hw['id'] != homework_id]
            return self.save_data()
        except:
            return False
    
    def mark_completed(self, homework_id):
        """标记为已完成"""
        try:
            homework_id = int(homework_id)
            for hw in self.homeworks:
                if hw['id'] == homework_id:
                    hw['status'] = 'completed'
                    break
            return self.save_data()
        except:
            return False
    
    def get_homework_status(self, due_date_str):
        """获取作业状态"""
        try:
            due_date = datetime.strptime(due_date_str, "%d/%m/%Y")
            today = datetime.now().date()
            due = due_date.date()
            
            if due < today:
                return "overdue"
            elif due == today:
                return "due_today"
            elif (due - today).days <= 3:  # 3天内截止
                return "due_soon"
            else:
                return "pending"
        except:
            return "pending"

# 创建全局管理器实例
manager = HomeworkManager()

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/homeworks', methods=['GET'])
def get_homeworks():
    """获取所有作业"""
    try:
        return jsonify({
            'success': True,
            'homeworks': manager.homeworks
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/add', methods=['POST'])
def add_homework():
    """添加新作业"""
    try:
        data = request.json
        if not all([data.get('code'), data.get('subject'), data.get('content'), data.get('due_date')]):
            return jsonify({'success': False, 'error': '请填写所有字段'})
        
        # 检查作业代号是否重复
        for hw in manager.homeworks:
            if hw['code'] == data['code']:
                return jsonify({'success': False, 'error': '作业代号已存在'})
        
        success = manager.add_homework(
            data['code'],
            data['subject'],
            data['content'],
            data['due_date']
        )
        
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': '保存失败'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/delete/<homework_id>', methods=['POST'])
def delete_homework(homework_id):
    """删除作业"""
    try:
        success = manager.delete_homework(homework_id)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/complete/<homework_id>', methods=['POST'])
def complete_homework(homework_id):
    """标记作业完成"""
    try:
        success = manager.mark_completed(homework_id)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """获取统计信息"""
    try:
        total = len(manager.homeworks)
        completed = len([hw for hw in manager.homeworks if hw.get('status') == 'completed'])
        pending = total - completed
        
        # 计算今天截止的作业
        today_str = datetime.now().strftime("%d/%m/%Y")
        due_today = len([hw for hw in manager.homeworks 
                        if hw['due_date'] == today_str and hw.get('status') != 'completed'])
        
        return jsonify({
            'success': True,
            'stats': {
                'total': total,
                'completed': completed,
                'pending': pending,
                'due_today': due_today
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# 健康检查端点
@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    app.run(debug=True)
