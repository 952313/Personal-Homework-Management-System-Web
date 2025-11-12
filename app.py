# app.py - Flask Web版本
from flask import Flask, render_template, request, jsonify
import json
from datetime import datetime, timedelta
import os

app = Flask(__name__)

class HomeworkManager:
    def __init__(self):
        self.data_file = "homework_data.json"
        self.load_data()
    
    def load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                self.homeworks = json.load(f)
        else:
            self.homeworks = []
    
    def save_data(self):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.homeworks, f, ensure_ascii=False, indent=2)

manager = HomeworkManager()

@app.route('/')
def index():
    return render_template('index.html', homeworks=manager.homeworks)

@app.route('/api/add', methods=['POST'])
def add_homework():
    data = request.json
    homework = {
        'id': len(manager.homeworks) + 1,
        'code': data['code'],
        'subject': data['subject'],
        'content': data['content'],
        'create_date': data['create_date'],
        'due_date': data['due_date'],
        'status': 'pending'
    }
    manager.homeworks.append(homework)
    manager.save_data()
    return jsonify({'success': True})

@app.route('/api/homeworks')
def get_homeworks():
    return jsonify(manager.homeworks)

if __name__ == '__main__':
    app.run(debug=True)
