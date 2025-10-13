#!/usr/bin/env python3
"""
电梯调度系统 - Tkinter GUI界面
适合快速开发和本地演示
事件驱动实时更新版本
"""
import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
import json
from typing import List, Dict
from client import LOOKElevatorController
from elevator_saga.client.proxy_models import ProxyElevator, ProxyFloor, ProxyPassenger
from elevator_saga.core.models import SimulationEvent


class GUIElevatorController(LOOKElevatorController):
    """扩展的控制器，支持GUI事件回调"""
    
    def __init__(self, gui_callback=None):
        super().__init__()
        self.gui_callback = gui_callback
    
    def _notify_gui(self, event_type, data):
        """通知GUI更新"""
        if self.gui_callback:
            self.gui_callback(event_type, data)
    
    def on_init(self, elevators: List[ProxyElevator], floors: List[ProxyFloor]) -> None:
        """初始化 - 通知GUI"""
        super().on_init(elevators, floors)
        self._notify_gui('init', {
            'elevators': len(elevators),
            'floors': len(floors)
        })
    
    def on_passenger_call(self, passenger: ProxyPassenger, floor: ProxyFloor, direction: str) -> None:
        """乘客呼叫 - 通知GUI"""
        super().on_passenger_call(passenger, floor, direction)
        self._notify_gui('passenger_call', {
            'passenger_id': passenger.id,
            'floor': floor.floor,
            'direction': direction,
            'tick': self.current_tick
        })
    
    def on_elevator_stopped(self, elevator: ProxyElevator, floor: ProxyFloor) -> None:
        """电梯停靠 - 通知GUI"""
        super().on_elevator_stopped(elevator, floor)
        self._notify_gui('elevator_stopped', {
            'elevator_id': elevator.id,
            'floor': floor.floor,
            'tick': self.current_tick
        })
    
    def on_passenger_board(self, elevator: ProxyElevator, passenger: ProxyPassenger) -> None:
        """乘客上梯 - 通知GUI"""
        super().on_passenger_board(elevator, passenger)
        self._notify_gui('passenger_board', {
            'elevator_id': elevator.id,
            'passenger_id': passenger.id,
            'destination': passenger.destination,
            'tick': self.current_tick
        })
    
    def on_passenger_alight(self, elevator: ProxyElevator, passenger: ProxyPassenger, floor: ProxyFloor) -> None:
        """乘客下梯 - 通知GUI"""
        super().on_passenger_alight(elevator, passenger, floor)
        self._notify_gui('passenger_alight', {
            'elevator_id': elevator.id,
            'passenger_id': passenger.id,
            'floor': floor.floor,
            'tick': self.current_tick
        })
    
    def on_elevator_idle(self, elevator: ProxyElevator) -> None:
        """电梯空闲 - 通知GUI"""
        super().on_elevator_idle(elevator)
        self._notify_gui('elevator_idle', {
            'elevator_id': elevator.id,
            'floor': elevator.current_floor,
            'tick': self.current_tick
        })
    
    def on_elevator_passing_floor(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        """电梯经过楼层 - 通知GUI"""
        super().on_elevator_passing_floor(elevator, floor, direction)
        self._notify_gui('elevator_passing', {
            'elevator_id': elevator.id,
            'floor': floor.floor,
            'direction': direction,
            'tick': self.current_tick
        })
    
    def on_event_execute_end(self, tick: int, events: List[SimulationEvent], 
                            elevators: List[ProxyElevator], floors: List[ProxyFloor]) -> None:
        """每个tick结束 - 通知GUI全量更新"""
        super().on_event_execute_end(tick, events, elevators, floors)
        self._notify_gui('tick_update', {
            'tick': tick,
            'event_count': len(events)
        })


class ElevatorGUI:
    def __init__(self, root, config_file='traffic.json'):
        self.root = root
        self.root.title("电梯调度系统 - LOOK算法可视化 (事件驱动)")
        self.root.geometry("1400x800")
        self.root.configure(bg='#f0f0f0')
        
        # 读取配置文件
        self.config = self.load_config(config_file)
        self.num_floors = self.config.get('floors', 6)
        self.num_elevators = self.config.get('elevators', 2)
        self.elevator_capacity = self.config.get('elevator_capacity', 8)
        
        # 控制器实例
        self.controller = None
        self.is_running = False
        self.controller_thread = None
        
        # 事件队列（用于线程安全）
        self.event_queue = []
        self.event_lock = threading.Lock()
        
        # 颜色配置
        self.colors = {
            'primary': '#667eea',
            'success': '#4CAF50',
            'danger': '#f44336',
            'warning': '#FFC107',
            'elevator_empty': '#4CAF50',
            'elevator_full': '#FF5722',
            'elevator_idle': '#9E9E9E',
            'floor_line': '#dee2e6',
            'passenger': '#2196F3',
        }
        
        self.setup_ui()
    
    def load_config(self, config_file):
        """加载traffic.json配置"""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                building = data.get('building', {})
                return {
                    'floors': building.get('floors', 6),
                    'elevators': building.get('elevators', 2),
                    'elevator_capacity': building.get('elevator_capacity', 8),
                    'scenario': building.get('scenario', 'unknown'),
                    'description': building.get('description', '')
                }
        except Exception as e:
            print(f"[警告] 无法读取配置文件: {e}, 使用默认配置")
            return {'floors': 6, 'elevators': 2, 'elevator_capacity': 8}
        
    def setup_ui(self):
        """设置UI布局"""
        # 顶部标题栏
        header = tk.Frame(self.root, bg=self.colors['primary'], height=80)
        header.pack(fill=tk.X, side=tk.TOP)
        
        title_label = tk.Label(
            header, 
            text="电梯调度系统可视化", 
            font=('Microsoft YaHei UI', 24, 'bold'),
            bg=self.colors['primary'],
            fg='white'
        )
        title_label.pack(pady=20)
        
        # 显示配置信息
        config_text = f"基于 LOOK 算法的智能电梯调度 | {self.num_elevators}部电梯 | {self.num_floors}层楼 | {self.config.get('description', '')}"
        subtitle = tk.Label(
            header,
            text=config_text,
            font=('Microsoft YaHei UI', 11),
            bg=self.colors['primary'],
            fg='white'
        )
        subtitle.pack()
        
        # 控制面板
        control_frame = tk.Frame(self.root, bg='#e9ecef', height=60)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 左侧按钮
        btn_frame = tk.Frame(control_frame, bg='#e9ecef')
        btn_frame.pack(side=tk.LEFT, padx=20, pady=10)
        
        self.start_btn = tk.Button(
            btn_frame,
            text="启动仿真",
            command=self.start_simulation,
            bg=self.colors['success'],
            fg='white',
            font=('Microsoft YaHei UI', 12, 'bold'),
            padx=25,
            pady=12,
            relief=tk.FLAT,
            cursor='hand2'
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = tk.Button(
            btn_frame,
            text="停止仿真",
            command=self.stop_simulation,
            bg=self.colors['danger'],
            fg='white',
            font=('Microsoft YaHei UI', 12, 'bold'),
            padx=25,
            pady=12,
            relief=tk.FLAT,
            state=tk.DISABLED,
            cursor='hand2'
        )
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        # 右侧状态显示
        status_frame = tk.Frame(control_frame, bg='#e9ecef')
        status_frame.pack(side=tk.RIGHT, padx=20, pady=10)
        
        tk.Label(
            status_frame,
            text="当前 Tick:",
            font=('Microsoft YaHei UI', 14),
            bg='#e9ecef',
            fg='#495057'
        ).pack(side=tk.LEFT, padx=5)
        
        self.tick_var = tk.StringVar(value="0")
        tk.Label(
            status_frame,
            textvariable=self.tick_var,
            font=('Microsoft YaHei UI', 18, 'bold'),
            bg='#e9ecef',
            fg=self.colors['primary']
        ).pack(side=tk.LEFT, padx=5)
        
        # 主内容区域
        main_container = tk.Frame(self.root, bg='#f0f0f0')
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 左侧：电梯可视化
        left_panel = tk.Frame(main_container, bg='white', relief=tk.RAISED, bd=2)
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        viz_title = tk.Label(
            left_panel,
            text="电梯井道可视化",
            font=('Microsoft YaHei UI', 14, 'bold'),
            bg='white',
            fg='#212529'
        )
        viz_title.pack(pady=15)
        
        # 画布
        canvas_frame = tk.Frame(left_panel, bg='white')
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        self.canvas = tk.Canvas(
            canvas_frame,
            bg='#f8f9fa',
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 右侧：信息面板
        right_panel = tk.Frame(main_container, bg='white', width=450, relief=tk.RAISED, bd=2)
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(5, 0))
        right_panel.pack_propagate(False)
        
        # 电梯状态面板
        elevator_frame = tk.LabelFrame(
            right_panel,
            text="电梯状态",
            font=('Microsoft YaHei UI', 12, 'bold'),
            bg='white',
            fg=self.colors['primary'],
            padx=10,
            pady=10
        )
        elevator_frame.pack(fill=tk.BOTH, padx=10, pady=5, ipady=5)
        
        # 创建表格
        columns = ('ID', '楼层', '方向', '载客', '目标楼层')
        self.elevator_tree = ttk.Treeview(
            elevator_frame,
            columns=columns,
            show='headings',
            height=6
        )
        
        # 设置列
        col_widths = {'ID': 50, '楼层': 60, '方向': 80, '载客': 80, '目标楼层': 120}
        for col in columns:
            self.elevator_tree.heading(col, text=col)
            self.elevator_tree.column(col, width=col_widths.get(col, 80), anchor=tk.CENTER)
        
        # 滚动条
        tree_scroll = ttk.Scrollbar(elevator_frame, orient=tk.VERTICAL, command=self.elevator_tree.yview)
        self.elevator_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.elevator_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 待处理呼叫
        call_frame = tk.LabelFrame(
            right_panel,
            text="待处理呼叫",
            font=('Microsoft YaHei UI', 12, 'bold'),
            bg='white',
            fg=self.colors['primary'],
            padx=10,
            pady=10
        )
        call_frame.pack(fill=tk.BOTH, padx=10, pady=5, ipady=5)
        
        self.call_text = scrolledtext.ScrolledText(
            call_frame,
            height=4,
            font=('Consolas', 10),
            bg='#f8f9fa',
            relief=tk.FLAT
        )
        self.call_text.pack(fill=tk.BOTH, expand=True)
        
        # 运行日志
        log_frame = tk.LabelFrame(
            right_panel,
            text="运行日志",
            font=('Microsoft YaHei UI', 12, 'bold'),
            bg='white',
            fg=self.colors['primary'],
            padx=10,
            pady=10
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5, ipady=5)
        
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            font=('Consolas', 9),
            bg='#212529',
            fg='#00ff00',
            insertbackground='white',
            relief=tk.FLAT
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 统计信息
        stats_frame = tk.LabelFrame(
            right_panel,
            text="统计信息",
            font=('Microsoft YaHei UI', 12, 'bold'),
            bg='white',
            fg=self.colors['primary'],
            padx=10,
            pady=10
        )
        stats_frame.pack(fill=tk.X, padx=10, pady=5, ipady=5)
        
        self.stats_labels = {}
        stats_config = [
            ('电梯数量', 'elevator_count'),
            ('楼层数量', 'floor_count'),
            ('电梯容量', 'elevator_capacity'),
            ('待处理呼叫', 'pending_calls'),
        ]
        
        # 设置初始值
        initial_values = {
            'elevator_count': str(self.num_elevators),
            'floor_count': str(self.num_floors),
            'elevator_capacity': str(self.elevator_capacity),
            'pending_calls': '0'
        }
        
        for label, key in stats_config:
            row = tk.Frame(stats_frame, bg='white')
            row.pack(fill=tk.X, pady=3)
            
            tk.Label(
                row,
                text=f"{label}:",
                font=('Microsoft YaHei UI', 10),
                bg='white',
                fg='#6c757d'
            ).pack(side=tk.LEFT)
            
            var = tk.StringVar(value=initial_values.get(key, "0"))
            self.stats_labels[key] = var
            
            tk.Label(
                row,
                textvariable=var,
                font=('Microsoft YaHei UI', 10, 'bold'),
                bg='white',
                fg='#212529'
            ).pack(side=tk.RIGHT)
    
    def draw_elevator_system(self, floors=None, elevators=None):
        """绘制电梯系统"""
        # 使用配置文件中的值，如果没有传入参数
        if floors is None:
            floors = self.num_floors
        if elevators is None:
            elevators = self.num_elevators
        
        self.canvas.delete("all")
        
        # 获取画布尺寸
        self.canvas.update()
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        
        if width <= 1 or height <= 1:
            width, height = 700, 600
        
        # 计算布局参数
        floor_height = (height - 100) / floors
        elevator_width = 70
        elevator_spacing = 120
        start_x = (width - elevators * elevator_spacing) / 2 + 50
        
        # 绘制楼层线和标签
        for i in range(floors + 1):
            y = height - 50 - i * floor_height
            
            # 楼层线
            self.canvas.create_line(
                50, y, width - 50, y,
                fill=self.colors['floor_line'],
                width=2,
                dash=(5, 3) if i < floors else ()
            )
            
            # 楼层号标签
            if i < floors:
                self.canvas.create_text(
                    25, y - floor_height / 2,
                    text=f"{i + 1}F",
                    font=('Microsoft YaHei UI', 12, 'bold'),
                    fill='#495057'
                )
        
        # 绘制电梯井道
        for i in range(elevators):
            x = start_x + i * elevator_spacing
            
            # 井道背景
            self.canvas.create_rectangle(
                x - 5, height - 50 - floors * floor_height,
                x + elevator_width + 5, height - 50,
                outline='#6c757d',
                width=2,
                dash=(4, 4),
                fill='#e9ecef'
            )
            
            # 电梯编号标签
            self.canvas.create_text(
                x + elevator_width / 2, 20,
                text=f"电梯 {i + 1}",
                font=('Microsoft YaHei UI', 12, 'bold'),
                fill='#212529'
            )
            
            # 绘制示例电梯轿厢（初始在1楼）
            car_y = height - 50 - floor_height / 2
            self.create_elevator_car(i, x, car_y, elevator_width, floor_height)
        
        # 图例
        self.draw_legend(width, height)
    
    def create_elevator_car(self, elevator_id, x, y, width, height):
        """创建电梯轿厢"""
        car_height = height * 0.7
        
        # 电梯轿厢矩形
        car = self.canvas.create_rectangle(
            x, y - car_height / 2,
            x + width, y + car_height / 2,
            fill=self.colors['elevator_empty'],
            outline='#155724',
            width=3,
            tags=f"elevator_{elevator_id}"
        )
        
        # 电梯ID文字
        text = self.canvas.create_text(
            x + width / 2, y,
            text=f"#{elevator_id + 1}",
            font=('Microsoft YaHei UI', 14, 'bold'),
            fill='white',
            tags=f"elevator_{elevator_id}_text"
        )
        
        return car
    
    def draw_legend(self, width, height):
        """绘制图例"""
        legend_x = width - 180
        legend_y = 50
        
        legends = [
            ("空闲/运行", self.colors['elevator_empty']),
            ("满载", self.colors['elevator_full']),
            ("停止", self.colors['elevator_idle'])
        ]
        
        self.canvas.create_text(
            legend_x - 20, legend_y - 20,
            text="图例:",
            font=('Microsoft YaHei UI', 10, 'bold'),
            anchor=tk.W
        )
        
        for i, (label, color) in enumerate(legends):
            y = legend_y + i * 30
            
            self.canvas.create_rectangle(
                legend_x, y,
                legend_x + 25, y + 20,
                fill=color,
                outline='black',
                width=1
            )
            
            self.canvas.create_text(
                legend_x + 35, y + 10,
                text=label,
                font=('Microsoft YaHei UI', 9),
                anchor=tk.W
            )
    
    def handle_controller_event(self, event_type, data):
        """处理控制器事件（从后台线程调用）"""
        with self.event_lock:
            self.event_queue.append((event_type, data))
    
    def process_events(self):
        """处理事件队列（在主线程中调用）"""
        events_to_process = []
        with self.event_lock:
            events_to_process = self.event_queue[:]
            self.event_queue.clear()
        
        for event_type, data in events_to_process:
            self._handle_event(event_type, data)
    
    def _handle_event(self, event_type, data):
        """处理单个事件"""
        tick = data.get('tick', 0)
        
        if event_type == 'init':
            self.log_message(f"[初始化] {data['elevators']}个电梯, {data['floors']}层楼")
            self.stats_labels['elevator_count'].set(str(data['elevators']))
            self.stats_labels['floor_count'].set(str(data['floors']))
            # 绘制电梯井道
            self.draw_elevator_system(floors=data['floors'], elevators=data['elevators'])
        
        elif event_type == 'passenger_call':
            direction_text = "上行" if data['direction'] == 'up' else "下行"
            msg = f"[Tick {tick}] 乘客{data['passenger_id']}在{data['floor']}层呼叫电梯 ({direction_text})"
            self.log_message(msg)
        
        elif event_type == 'elevator_stopped':
            self.log_message(f"[Tick {tick}] 电梯{data['elevator_id']+1}停靠在{data['floor']}层")
        
        elif event_type == 'passenger_board':
            self.log_message(f"[Tick {tick}] 乘客{data['passenger_id']}上电梯{data['elevator_id']+1}, 去{data['destination']}层")
        
        elif event_type == 'passenger_alight':
            self.log_message(f"[Tick {tick}] 乘客{data['passenger_id']}在{data['floor']}层下电梯{data['elevator_id']+1}")
        
        elif event_type == 'elevator_idle':
            self.log_message(f"[Tick {tick}] 电梯{data['elevator_id']+1}空闲")
        
        elif event_type == 'elevator_passing':
            # 经过楼层时不显示日志（太频繁）
            pass
        
        elif event_type == 'tick_update':
            # 每个tick结束后更新完整状态
            self.tick_var.set(str(data['tick']))
    
    def update_display(self):
        """定期更新显示"""
        if not self.is_running or not self.controller:
            return
        
        try:
            # 处理事件队列
            self.process_events()
            
            # 更新Tick
            self.tick_var.set(str(self.controller.current_tick))
            
            # 更新电梯状态表格
            self.elevator_tree.delete(*self.elevator_tree.get_children())
            
            if hasattr(self.controller, 'elevators') and self.controller.elevators:
                # 更新统计
                self.stats_labels['elevator_count'].set(str(len(self.controller.elevators)))
                
                for elevator in self.controller.elevators:
                    elevator_id = elevator.id
                    targets = self.controller.elevator_targets.get(elevator_id, set())
                    direction = self.controller.elevator_directions.get(elevator_id, "stopped")
                    
                    # 计算当前载客数
                    current_passengers = int(elevator.load_factor * elevator.max_capacity)
                    
                    # 方向文字
                    direction_text = {
                        'up': '上行',
                        'down': '下行',
                        'stopped': '停止'
                    }.get(direction, direction)
                    
                    # 插入表格数据
                    self.elevator_tree.insert('', 'end', values=(
                        f"#{elevator_id + 1}",
                        f"{elevator.current_floor}F",
                        direction_text,
                        f"{current_passengers}/{elevator.max_capacity}",
                        ', '.join(map(str, sorted(targets))) if targets else "-"
                    ))
                    
                    # 更新可视化
                    self.update_elevator_position(elevator_id, elevator.current_floor, 
                                                  current_passengers, elevator.max_capacity)
            
            # 更新待处理呼叫
            self.call_text.delete(1.0, tk.END)
            if hasattr(self.controller, 'pending_calls'):
                pending = self.controller.pending_calls
                self.stats_labels['pending_calls'].set(str(len(pending)))
                
                if pending:
                    for floor, direction in sorted(pending.items()):
                        icon = '↑' if direction == 'up' else '↓'
                        self.call_text.insert(tk.END, f"  {icon} {floor}F → {direction}\n")
                else:
                    self.call_text.insert(tk.END, "  暂无待处理呼叫")
            
        except Exception as e:
            self.log_message(f"[错误] 更新显示失败: {e}")
        
        # 继续定期更新（事件驱动模式，更快速）
        if self.is_running:
            self.root.after(50, self.update_display)  # 50ms刷新，实时响应事件
    
    def update_elevator_position(self, elevator_id, floor, passengers, capacity):
        """更新电梯可视化位置"""
        try:
            # 获取画布尺寸
            height = self.canvas.winfo_height()
            
            # 计算位置（使用配置中的楼层数）
            floors = self.num_floors
            floor_height = (height - 100) / floors
            
            # 计算电梯轿厢的新Y坐标
            new_y = height - 50 - (floor - 0.5) * floor_height
            
            # 获取电梯标签
            car_items = self.canvas.find_withtag(f"elevator_{elevator_id}")
            
            if car_items:
                car = car_items[0]
                coords = self.canvas.coords(car)
                
                if len(coords) >= 4:
                    x1, _, x2, _ = coords
                    car_height = floor_height * 0.7
                    
                    # 移动电梯
                    self.canvas.coords(
                        car,
                        x1, new_y - car_height / 2,
                        x2, new_y + car_height / 2
                    )
                    
                    # 更新颜色
                    if passengers >= capacity:
                        color = self.colors['elevator_full']
                    elif passengers > 0:
                        color = self.colors['elevator_empty']
                    else:
                        color = self.colors['elevator_idle']
                    
                    self.canvas.itemconfig(car, fill=color)
                    
                    # 移动文字
                    text_items = self.canvas.find_withtag(f"elevator_{elevator_id}_text")
                    if text_items:
                        self.canvas.coords(text_items[0], (x1 + x2) / 2, new_y)
        except Exception as e:
            pass  # 忽略可视化错误
    
    def log_message(self, message):
        """添加日志"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def start_simulation(self):
        """启动仿真"""
        if self.is_running:
            return
        
        self.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        self.log_message("=" * 40)
        self.log_message("[启动] 仿真启动中...")
        self.log_message(f"[配置] {self.num_elevators}部电梯, {self.num_floors}层楼, 容量{self.elevator_capacity}人")
        self.log_message("=" * 40)
        
        # 绘制初始界面
        self.draw_elevator_system()
        
        # 创建控制器并在新线程运行
        def run_controller():
            # 使用事件驱动的控制器，传入GUI回调
            self.controller = GUIElevatorController(gui_callback=self.handle_controller_event)
            try:
                self.log_message("[连接] 连接到仿真服务器...")
                self.log_message("[监听] 事件监听已启动...")
                self.controller.start()
            except Exception as e:
                error_msg = str(e)
                self.log_message(f"[错误] {error_msg}")
                
                # 如果是状态不一致错误，给出提示
                if "not found in state" in error_msg:
                    self.log_message("")
                    self.log_message("[提示] 请重启仿真服务器")
                    self.log_message("   1. 停止服务器(Ctrl+C)")
                    self.log_message("   2. 重新运行: elevator-server --config traffic.json")
                    self.log_message("   3. 重新点击'启动仿真'")
                
                self.root.after(0, self.stop_simulation)
        
        self.controller_thread = threading.Thread(target=run_controller, daemon=True)
        self.controller_thread.start()
        
        # 启动UI更新（事件驱动模式，更频繁地检查事件队列）
        self.root.after(50, self.update_display)  # 50ms更新一次，更实时
    
    def stop_simulation(self):
        """停止仿真"""
        self.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        
        self.log_message("=" * 40)
        self.log_message("[停止] 仿真已停止")
        self.log_message("=" * 40)


def main():
    """主函数"""
    root = tk.Tk()
    
    # 设置图标（可选）
    try:
        root.iconbitmap('elevator.ico')
    except:
        pass
    
    app = ElevatorGUI(root)
    
    # 窗口关闭事件
    def on_closing():
        if app.is_running:
            app.stop_simulation()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()

