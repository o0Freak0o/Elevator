#!/usr/bin/env python3
"""
电梯调度GUI界面
启动并显示LOOKElevatorController的调度状态

使用方法:
1. 运行 python elevator_gui.py 启动GUI
2. 点击"启动模拟"按钮开始电梯调度
3. 观察LOOK算法的调度过程

注意: GUI会启动LOOKElevatorController，无需单独运行client.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
from typing import Dict, List, Optional, Set
import math

# 导入LOOKElevatorController
try:
    from client import LOOKElevatorController
except ImportError:
    print("无法导入LOOKElevatorController，请确保client.py在同一目录下")
    LOOKElevatorController = None


class ElevatorGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("电梯调度模拟器 - LOOK算法")
        self.root.geometry("1200x800")
        self.root.configure(bg='#f0f0f0')
        
        # 设置窗口图标和样式
        self.root.resizable(True, True)
        self.root.minsize(1000, 700)
        
        # 控制器引用
        self.controller = None
        self.controller_thread = None
        self.is_running = False
        
        # 颜色主题
        self.colors = {
            'primary': '#2c3e50',
            'secondary': '#3498db',
            'success': '#27ae60',
            'warning': '#f39c12',
            'danger': '#e74c3c',
            'light': '#ecf0f1',
            'dark': '#34495e',
            'elevator_up': '#2ecc71',
            'elevator_down': '#e74c3c',
            'elevator_stopped': '#3498db',
            'call_up': '#f39c12',
            'call_down': '#9b59b6'
        }
        
        # 从traffic.json读取配置
        self.building_config = self._load_building_config()
        self.floors = self.building_config.get('floors', 6)
        self.elevators_count = self.building_config.get('elevators', 2)
        self.elevator_capacity = self.building_config.get('elevator_capacity', 8)
        
        # 电梯状态数据
        self.elevator_states = {}
        self.passenger_data = {}
        self.current_tick = 0
        
        # 创建GUI组件
        self._create_widgets()
        
        # 启动状态更新线程
        self.update_thread = threading.Thread(target=self._update_status, daemon=True)
        self.update_thread.start()
        
    def _load_building_config(self) -> Dict:
        """从traffic.json加载建筑配置"""
        try:
            with open('traffic.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('building', {})
        except FileNotFoundError:
            return {'floors': 6, 'elevators': 2, 'elevator_capacity': 8}
    
    def _create_widgets(self):
        """创建GUI组件"""
        # 主框架
        main_frame = tk.Frame(self.root, bg='#f0f0f0')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # 标题区域
        self._create_header(main_frame)
        
        # 内容区域
        content_frame = tk.Frame(main_frame, bg='#f0f0f0')
        content_frame.pack(fill=tk.BOTH, expand=True, pady=(20, 0))
        
        # 左侧信息面板
        left_panel = self._create_info_panel(content_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # 右侧电梯显示面板
        right_panel = self._create_elevator_panel(content_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # 底部控制面板
        self._create_control_panel(main_frame)
        
        # 状态栏
        self._create_status_bar(main_frame)
    
    def _create_header(self, parent):
        """创建标题区域"""
        header_frame = tk.Frame(parent, bg=self.colors['primary'], height=80)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        header_frame.pack_propagate(False)
        
        # 标题
        title_label = tk.Label(
            header_frame, 
            text="电梯调度模拟器", 
            font=("Microsoft YaHei UI", 24, "bold"),
            fg='white',
            bg=self.colors['primary']
        )
        title_label.pack(expand=True)
        
        # 副标题
        subtitle_label = tk.Label(
            header_frame,
            text="LOOK算法调度系统",
            font=("Microsoft YaHei UI", 12),
            fg='#bdc3c7',
            bg=self.colors['primary']
        )
        subtitle_label.pack()
    
    def _create_info_panel(self, parent):
        """创建信息面板"""
        info_frame = tk.Frame(parent, bg='white', relief=tk.RAISED, bd=2)
        
        # 标题
        title_frame = tk.Frame(info_frame, bg=self.colors['secondary'], height=40)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="系统状态",
            font=("Microsoft YaHei UI", 14, "bold"),
            fg='white',
            bg=self.colors['secondary']
        )
        title_label.pack(expand=True)
        
        # 信息显示区域
        info_content = tk.Frame(info_frame, bg='white')
        info_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建带滚动条的文本框
        text_frame = tk.Frame(info_content, bg='white')
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.info_text = tk.Text(
            text_frame, 
            wrap=tk.WORD,
            font=("Consolas", 10),
            bg='#f8f9fa',
            fg='#2c3e50',
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=10
        )
        
        # 自定义滚动条
        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=scrollbar.set)
        
        self.info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        return info_frame
    
    def _create_elevator_panel(self, parent):
        """创建电梯显示面板"""
        elevator_frame = tk.Frame(parent, bg='white', relief=tk.RAISED, bd=2)
        
        # 标题
        title_frame = tk.Frame(elevator_frame, bg=self.colors['success'], height=40)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="电梯运行状态",
            font=("Microsoft YaHei UI", 14, "bold"),
            fg='white',
            bg=self.colors['success']
        )
        title_label.pack(expand=True)
        
        # 创建电梯显示区域
        self._create_elevator_display(elevator_frame)
        
        return elevator_frame
    
    def _create_control_panel(self, parent):
        """创建控制面板"""
        control_frame = tk.Frame(parent, bg='#f0f0f0', height=60)
        control_frame.pack(fill=tk.X, pady=(20, 0))
        control_frame.pack_propagate(False)
        
        # 按钮容器
        button_frame = tk.Frame(control_frame, bg='#f0f0f0')
        button_frame.pack(expand=True)
        
        # 启动按钮
        self.start_button = tk.Button(
            button_frame,
            text="启动模拟",
            command=self._start_simulation,
            font=("Microsoft YaHei UI", 12, "bold"),
            bg=self.colors['success'],
            fg='white',
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=10,
            cursor='hand2'
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 15))
        
        # 停止按钮
        self.stop_button = tk.Button(
            button_frame,
            text="停止模拟",
            command=self._stop_simulation,
            font=("Microsoft YaHei UI", 12, "bold"),
            bg=self.colors['danger'],
            fg='white',
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=10,
            state=tk.DISABLED,
            cursor='hand2'
        )
        self.stop_button.pack(side=tk.LEFT, padx=(0, 15))
        
        # 刷新按钮
        self.refresh_button = tk.Button(
            button_frame,
            text="刷新状态",
            command=self._refresh_status,
            font=("Microsoft YaHei UI", 12, "bold"),
            bg=self.colors['secondary'],
            fg='white',
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=10,
            cursor='hand2'
        )
        self.refresh_button.pack(side=tk.LEFT, padx=(0, 15))
        
        # 重置按钮
        self.reset_button = tk.Button(
            button_frame,
            text="重置模拟",
            command=self._reset_simulation,
            font=("Microsoft YaHei UI", 12, "bold"),
            bg=self.colors['warning'],
            fg='white',
            relief=tk.FLAT,
            bd=0,
            padx=20,
            pady=10,
            cursor='hand2'
        )
        self.reset_button.pack(side=tk.LEFT)
        
        # 添加按钮悬停效果
        self._add_button_hover_effects()
    
    def _create_status_bar(self, parent):
        """创建状态栏"""
        status_frame = tk.Frame(parent, bg=self.colors['dark'], height=30)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        status_frame.pack_propagate(False)
        
        self.status_var = tk.StringVar()
        self.status_var.set("系统就绪")
        
        status_label = tk.Label(
            status_frame,
            textvariable=self.status_var,
            font=("Microsoft YaHei UI", 10),
            fg='white',
            bg=self.colors['dark']
        )
        status_label.pack(side=tk.LEFT, padx=10, pady=5)
        
        # 添加时间显示
        self.time_var = tk.StringVar()
        time_label = tk.Label(
            status_frame,
            textvariable=self.time_var,
            font=("Microsoft YaHei UI", 10),
            fg='#bdc3c7',
            bg=self.colors['dark']
        )
        time_label.pack(side=tk.RIGHT, padx=10, pady=5)
        
        # 更新时间
        self._update_time()
    
    def _add_button_hover_effects(self):
        """添加按钮悬停效果"""
        def on_enter(event, color):
            event.widget.config(bg=color)
        
        def on_leave(event, original_color):
            if event.widget['state'] != 'disabled':
                event.widget.config(bg=original_color)
        
        # 启动按钮
        self.start_button.bind("<Enter>", lambda e: on_enter(e, '#229954'))
        self.start_button.bind("<Leave>", lambda e: on_leave(e, self.colors['success']))
        
        # 停止按钮
        self.stop_button.bind("<Enter>", lambda e: on_enter(e, '#c0392b'))
        self.stop_button.bind("<Leave>", lambda e: on_leave(e, self.colors['danger']))
        
        # 刷新按钮
        self.refresh_button.bind("<Enter>", lambda e: on_enter(e, '#2980b9'))
        self.refresh_button.bind("<Leave>", lambda e: on_leave(e, self.colors['secondary']))
        
        # 重置按钮
        self.reset_button.bind("<Enter>", lambda e: on_enter(e, '#e67e22'))
        self.reset_button.bind("<Leave>", lambda e: on_leave(e, self.colors['warning']))
    
    def _update_time(self):
        """更新时间显示"""
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        self.time_var.set(current_time)
        self.root.after(1000, self._update_time)
        
    def _create_elevator_display(self, parent):
        """创建电梯显示区域"""
        # 创建画布容器
        canvas_container = tk.Frame(parent, bg='white')
        canvas_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 创建画布
        self.canvas = tk.Canvas(
            canvas_container, 
            bg='#f8f9fa', 
            width=500, 
            height=500,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0
        )
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # 自定义滚动条
        v_scrollbar = tk.Scrollbar(
            canvas_container, 
            orient=tk.VERTICAL, 
            command=self.canvas.yview,
            bg='#ecf0f1',
            troughcolor='#bdc3c7',
            activebackground='#95a5a6'
        )
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.configure(yscrollcommand=v_scrollbar.set)
        
        # 绘制建筑结构
        self._draw_building()
        
    def _draw_building(self):
        """绘制建筑结构"""
        self.canvas.delete("all")
        
        # 计算尺寸
        canvas_width = 500
        canvas_height = max(500, self.floors * 70 + 120)
        self.canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))
        
        # 楼层高度和电梯尺寸
        floor_height = 60
        elevator_width = 70
        elevator_spacing = 90
        
        # 绘制建筑背景
        self.canvas.create_rectangle(
            0, 0, canvas_width, canvas_height,
            fill='#f8f9fa', outline='', width=0
        )
        
        # 绘制楼层
        for floor in range(self.floors):
            y = canvas_height - (floor + 1) * floor_height - 60
            
            # 楼层背景
            floor_color = '#ffffff' if floor % 2 == 0 else '#f1f3f4'
            self.canvas.create_rectangle(
                0, y - floor_height + 10, canvas_width, y - 10,
                fill=floor_color, outline='', width=0
            )
            
            # 楼层线
            self.canvas.create_line(
                0, y, canvas_width, y, 
                fill="#e0e0e0", width=2
            )
            
            # 楼层标签
            self.canvas.create_text(
                20, y - floor_height//2, 
                text=f"F{floor + 1}", 
                font=("Microsoft YaHei UI", 12, "bold"),
                fill=self.colors['primary']
            )
            
            # 电梯井道
            for i in range(self.elevators_count):
                x = 120 + i * elevator_spacing
                
                # 电梯井道背景
                self.canvas.create_rectangle(
                    x - 5, y - floor_height + 15,
                    x + elevator_width + 5, y - 15,
                    fill='#ecf0f1', outline='', width=0
                )
                
                # 电梯井道边框
                self.canvas.create_rectangle(
                    x, y - floor_height + 10,
                    x + elevator_width, y - 10,
                    outline=self.colors['dark'], width=2, fill="white"
                )
                
                # 电梯门
                door_width = elevator_width // 2
                door_x = x + (elevator_width - door_width) // 2
                self.canvas.create_rectangle(
                    door_x, y - floor_height + 15,
                    door_x + door_width, y - 15,
                    outline="#95a5a6", width=1, fill="#ffffff", 
                    tags=f"door_{i}_{floor}"
                )
                
                # 电梯门把手
                handle_x = door_x + door_width - 8
                self.canvas.create_oval(
                    handle_x, y - floor_height//2 - 3,
                    handle_x + 6, y - floor_height//2 + 3,
                    fill="#bdc3c7", outline="", tags=f"handle_{i}_{floor}"
                )
        
        # 绘制电梯
        self._draw_elevators()
        
    def _draw_elevators(self):
        """绘制电梯"""
        canvas_height = max(500, self.floors * 70 + 120)
        floor_height = 60
        elevator_width = 70
        elevator_spacing = 90
        
        # 清除之前的电梯和目标标记
        self.canvas.delete("elevator")
        self.canvas.delete("target")
        
        for i in range(self.elevators_count):
            x = 120 + i * elevator_spacing
            
            # 获取电梯当前楼层（默认为1层）
            current_floor = self.elevator_states.get(i, {}).get('current_floor', 1)
            y = canvas_height - current_floor * floor_height - 30
            
            # 电梯主体（带阴影效果）
            shadow_offset = 3
            self.canvas.create_rectangle(
                x + shadow_offset, y - 25 + shadow_offset,
                x + elevator_width + shadow_offset, y + 25 + shadow_offset,
                fill='#bdc3c7', outline='', width=0, tags=f"elevator_{i} elevator"
            )
            
            # 电梯主体
            color = self.elevator_states.get(i, {}).get('color', self.colors['elevator_stopped'])
            self.canvas.create_rectangle(
                x, y - 25,
                x + elevator_width, y + 25,
                fill=color, outline=self.colors['dark'], width=2, 
                tags=f"elevator_{i} elevator"
            )
            
            # 电梯编号
            self.canvas.create_text(
                x + elevator_width//2, y - 8,
                text=f"E{i+1}", 
                font=("Microsoft YaHei UI", 10, "bold"), 
                fill='white',
                tags=f"elevator_{i} elevator"
            )
            
            # 电梯状态信息
            direction = self.elevator_states.get(i, {}).get('direction', 'stopped')
            passengers = self.elevator_states.get(i, {}).get('passengers', 0)
            targets = self.elevator_states.get(i, {}).get('targets', [])
            
            # 方向指示器
            direction_symbol = "UP" if direction == "up" else "DN" if direction == "down" else "ST"
            self.canvas.create_text(
                x + elevator_width//2, y + 5,
                text=direction_symbol, 
                font=("Microsoft YaHei UI", 8, "bold"), 
                fill='white',
                tags=f"elevator_{i} elevator"
            )
            
            # 载客数显示
            self.canvas.create_text(
                x + elevator_width//2, y + 18,
                text=f"{passengers}/{self.elevator_capacity}", 
                font=("Microsoft YaHei UI", 8), 
                fill='white',
                tags=f"elevator_{i} elevator"
            )
            
            # 绘制目标楼层标记
            if targets:
                target_text = f"目标: {','.join(map(str, sorted(targets)))}"
                self.canvas.create_text(
                    x + elevator_width//2, y + 35,
                    text=target_text, 
                    font=("Microsoft YaHei UI", 7), 
                    fill=self.colors['danger'],
                    tags=f"elevator_{i} elevator"
                )
        
        # 绘制待处理呼叫标记
        self._draw_pending_calls(canvas_height, floor_height)
    
    def _draw_pending_calls(self, canvas_height, floor_height):
        """绘制待处理呼叫标记"""
        # 清除之前的呼叫标记
        self.canvas.delete("call")
        
        if not self.controller:
            return
            
        try:
            pending_calls = getattr(self.controller, 'pending_calls', {})
            for floor, direction in pending_calls.items():
                y = canvas_height - floor * floor_height - 30
                
                # 在楼层右侧绘制呼叫标记
                call_x = 50 + self.elevators_count * 90 + 30
                color = self.colors['call_up'] if direction == "up" else self.colors['call_down']
                
                # 呼叫标记背景（带阴影）
                shadow_offset = 2
                self.canvas.create_oval(
                    call_x + shadow_offset, y - 12 + shadow_offset,
                    call_x + 24 + shadow_offset, y + 12 + shadow_offset,
                    fill='#bdc3c7', outline='', width=0, tags="call"
                )
                
                # 呼叫标记
                self.canvas.create_oval(
                    call_x, y - 12,
                    call_x + 24, y + 12,
                    fill=color, outline=self.colors['dark'], width=2, tags="call"
                )
                
                # 方向箭头
                arrow = "UP" if direction == "up" else "DN"
                self.canvas.create_text(
                    call_x + 12, y,
                    text=arrow, 
                    font=("Microsoft YaHei UI", 8, "bold"), 
                    fill="white", 
                    tags="call"
                )
                
                # 楼层号
                self.canvas.create_text(
                    call_x + 35, y,
                    text=f"F{floor}", 
                    font=("Microsoft YaHei UI", 10, "bold"), 
                    fill=self.colors['primary'],
                    tags="call"
                )
                
                # 呼叫状态文本
                status_text = "上行呼叫" if direction == "up" else "下行呼叫"
                self.canvas.create_text(
                    call_x + 35, y + 15,
                    text=status_text, 
                    font=("Microsoft YaHei UI", 8), 
                    fill=self.colors['dark'],
                    tags="call"
                )
        except Exception as e:
            print(f"绘制呼叫标记时出错: {e}")
    
    def _update_status(self):
        """更新状态信息"""
        while True:
            try:
                if self.controller and self.is_running:
                    # 从控制器获取状态
                    self._update_from_controller()
                else:
                    # 没有控制器或未运行，显示默认状态
                    if not LOOKElevatorController:
                        self._update_info_display({"tick": 0, "message": "无法导入LOOKElevatorController"})
                    elif not self.is_running:
                        self._update_info_display({"tick": 0, "message": "点击'启动模拟'开始电梯调度..."})
                    else:
                        self._update_info_display({"tick": 0, "message": "等待控制器启动..."})
            except Exception as e:
                self._update_info_display({"tick": 0, "message": f"更新状态时出错: {e}"})
            
            time.sleep(0.5)  # 每0.5秒更新一次
    
    def _update_from_controller(self):
        """从控制器获取状态并更新显示"""
        try:
            # 获取控制器状态
            current_tick = getattr(self.controller, 'current_tick', 0)
            elevator_targets = getattr(self.controller, 'elevator_targets', {})
            elevator_directions = getattr(self.controller, 'elevator_directions', {})
            pending_calls = getattr(self.controller, 'pending_calls', {})
            elevators = getattr(self.controller, 'elevators', [])
            
            # 更新电梯状态
            for i, elevator in enumerate(elevators):
                if hasattr(elevator, 'current_floor') and hasattr(elevator, 'load_factor'):
                    direction = elevator_directions.get(i, 'stopped')
                    targets = list(elevator_targets.get(i, set()))
                    
                    self.elevator_states[i] = {
                        'current_floor': elevator.current_floor,
                        'direction': direction,
                        'passengers': int(elevator.load_factor * self.elevator_capacity) if hasattr(elevator, 'load_factor') else 0,
                        'targets': targets,
                        'color': self._get_elevator_color(direction)
                    }
            
            # 更新信息显示
            self._update_info_display({
                'tick': current_tick,
                'elevator_targets': elevator_targets,
                'elevator_directions': elevator_directions,
                'pending_calls': pending_calls,
                'elevators': elevators
            })
            
            # 重绘电梯
            self.root.after(0, self._draw_elevators)
            
        except Exception as e:
            print(f"更新控制器状态时出错: {e}")
    
    def _update_elevator_states(self, data):
        """更新电梯状态（保留兼容性）"""
        if 'elevators' in data:
            for i, elevator_data in enumerate(data['elevators']):
                self.elevator_states[i] = {
                    'current_floor': elevator_data.get('current_floor', 1),
                    'direction': elevator_data.get('direction', 'stopped'),
                    'passengers': elevator_data.get('passengers', 0),
                    'color': self._get_elevator_color(elevator_data.get('direction', 'stopped'))
                }
        
        # 重绘电梯
        self.root.after(0, self._draw_elevators)
    
    def _get_elevator_color(self, direction):
        """根据电梯方向获取颜色"""
        color_map = {
            'up': self.colors['elevator_up'],
            'down': self.colors['elevator_down'],
            'stopped': self.colors['elevator_stopped']
        }
        return color_map.get(direction, self.colors['elevator_stopped'])
    
    def _update_info_display(self, data):
        """更新信息显示"""
        self.current_tick = data.get('tick', 0)
        
        # 使用更美观的格式
        info_text = f"当前Tick: {self.current_tick}\n"
        info_text += f"楼层数: {self.floors}\n"
        info_text += f"电梯数: {self.elevators_count}\n"
        info_text += f"电梯容量: {self.elevator_capacity}\n\n"
        
        # 显示电梯状态
        if 'elevator_targets' in data and 'elevator_directions' in data:
            info_text += "电梯调度状态\n"
            info_text += "=" * 20 + "\n"
            elevator_targets = data['elevator_targets']
            elevator_directions = data['elevator_directions']
            
            for i in range(self.elevators_count):
                direction = elevator_directions.get(i, 'stopped')
                targets = list(elevator_targets.get(i, set()))
                current_floor = self.elevator_states.get(i, {}).get('current_floor', 1)
                passengers = self.elevator_states.get(i, {}).get('passengers', 0)
                
                # 方向符号
                direction_symbol = "UP" if direction == "up" else "DN" if direction == "down" else "ST"
                
                info_text += f"电梯{i+1}: 楼层{current_floor} {direction_symbol} {direction}\n"
                info_text += f"   目标: {targets if targets else '无'}\n"
                info_text += f"   载客: {passengers}/{self.elevator_capacity}\n\n"
        
        # 显示待处理呼叫
        if 'pending_calls' in data:
            pending_calls = data['pending_calls']
            if pending_calls:
                info_text += "待处理呼叫\n"
                info_text += "=" * 15 + "\n"
                for floor, direction in pending_calls.items():
                    direction_symbol = "UP" if direction == "up" else "DN"
                    info_text += f"楼层{floor}: {direction_symbol} {direction}方向\n"
                info_text += "\n"
        
        if 'message' in data:
            info_text += f"{data['message']}\n"
        
        # 更新显示
        self.root.after(0, lambda: self._update_info_text(info_text))
    
    def _update_info_text(self, text):
        """更新信息文本"""
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, text)
        self.info_text.see(tk.END)
    
    def _start_simulation(self):
        """启动模拟"""
        if not LOOKElevatorController:
            self._log_message("错误: 无法导入LOOKElevatorController")
            return
            
        if self.is_running:
            self._log_message("模拟已在运行中")
            return
            
        try:
            # 先重置状态（不显示消息）
            self._reset_simulation(show_message=False)
            
            # 创建控制器实例
            self.controller = LOOKElevatorController()
            
            # 在单独线程中启动控制器
            self.controller_thread = threading.Thread(target=self._run_controller, daemon=True)
            self.controller_thread.start()
            
            self.is_running = True
            self.status_var.set("模拟运行中...")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            
            self._log_message("LOOKElevatorController启动成功")
            self._log_message("模拟器已重置，开始新的模拟...")
            
        except Exception as e:
            self._log_message(f"启动模拟器失败: {e}")
            self.controller = None
    
    def _run_controller(self):
        """在单独线程中运行控制器"""
        try:
            if self.controller:
                self.controller.start()
        except Exception as e:
            self._log_message(f"控制器运行出错: {e}")
        finally:
            self.is_running = False
            self.root.after(0, self._on_controller_stopped)
    
    def _on_controller_stopped(self):
        """控制器停止时的回调"""
        self.status_var.set("模拟已停止")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self._log_message("控制器已停止")
    
    def _stop_simulation(self):
        """停止模拟"""
        if not self.is_running:
            self._log_message("模拟未在运行")
            return
            
        try:
            if self.controller:
                # 停止控制器
                if hasattr(self.controller, 'stop'):
                    self.controller.stop()
                else:
                    # 如果没有stop方法，设置标志位
                    self.is_running = False
                    
            self._log_message("正在停止模拟器...")
            
        except Exception as e:
            self._log_message(f"停止模拟器失败: {e}")
    
    def _refresh_status(self):
        """手动刷新状态"""
        self._log_message("手动刷新状态")
        self._draw_elevators()
    
    def _reset_simulation(self, show_message=True):
        """重置模拟"""
        if self.is_running:
            # 如果模拟正在运行，先停止
            self._stop_simulation()
            time.sleep(1)  # 等待停止完成
        
        try:
            # 重置电梯状态
            self.elevator_states = {}
            self.passenger_data = {}
            self.current_tick = 0
            
            # 清空信息显示
            self.info_text.delete(1.0, tk.END)
            if show_message:
                self.info_text.insert(1.0, "模拟已重置，点击'启动模拟'开始新的模拟...\n")
            
            # 重绘电梯显示
            self._draw_elevators()
            
            # 更新状态
            if show_message:
                self.status_var.set("模拟已重置")
                self._log_message("模拟器状态已重置")
            
        except Exception as e:
            self._log_message(f"重置模拟失败: {e}")
    
    def _log_message(self, message):
        """记录消息"""
        timestamp = time.strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        self.info_text.insert(tk.END, log_message)
        self.info_text.see(tk.END)
    
    def run(self):
        """运行GUI"""
        self.root.mainloop()


def main():
    """主函数"""
    try:
        gui = ElevatorGUI()
        gui.run()
    except Exception as e:
        print(f"GUI启动失败: {e}")


if __name__ == "__main__":
    main()
