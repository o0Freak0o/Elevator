#!/usr/bin/env python3
"""
电梯控制器GUI可视化界面 - 为现有的NewElevatorController提供动态可视化
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sys
from typing import List

# 添加项目路径
sys.path.append("D:/homework/soft_engineering/project/Elevator_shen")

from elevator_saga.client.proxy_models import ProxyElevator, ProxyFloor
from elevator_saga.core.models import Direction
from our_control.controller import NewElevatorController


class ElevatorGUI:
    """电梯可视化GUI界面 - 包装现有的NewElevatorController"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("电梯调度可视化系统")
        self.root.geometry("1400x900")
        
        # 数据存储
        self.elevators: List[ProxyElevator] = []
        self.floors: List[ProxyFloor] = []
        self.current_tick = 0
        self.is_running = False
        
        # 控制器引用
        self.controller = None
        
        # 可视化元素存储
        self.elevator_rects = {}  # 存储电梯矩形ID
        self.passenger_indicators = {}  # 存储乘客指示器
        self.elevator_states = {}  # 存储电梯状态缓存，避免频繁重绘
        
        # 可视化参数
        self.floor_height = 60
        self.base_elevator_width = 80
        self.base_elevator_height = 50
        self.min_elevator_width = 40
        self.min_elevator_height = 30
        self.canvas_width = 800
        self.canvas_height = 600
        
        # 动态电梯参数（根据电梯数量调整）
        self.elevator_width = self.base_elevator_width
        self.elevator_height = self.base_elevator_height
        
        # 设置快捷键
        # self.setup_shortcuts()
        
        # 创建界面
        self.setup_ui()
        
        # 更新线程
        self.update_thread = None
        
    def calculate_elevator_params(self, num_elevators):
        """根据电梯数量计算电梯参数"""
        if num_elevators <= 0:
            return self.base_elevator_width, self.base_elevator_height
        
        # 根据电梯数量调整大小
        if num_elevators <= 2:
            # 1-2个电梯：使用原始大小
            width = self.base_elevator_width
            height = self.base_elevator_height
        elif num_elevators <= 4:
            # 3-4个电梯：稍微缩小
            width = max(self.min_elevator_width, self.base_elevator_width * 0.8)
            height = max(self.min_elevator_height, self.base_elevator_height * 0.8)
        elif num_elevators <= 6:
            # 5-6个电梯：进一步缩小
            width = max(self.min_elevator_width, self.base_elevator_width * 0.6)
            height = max(self.min_elevator_height, self.base_elevator_height * 0.6)
        else:
            # 7个以上电梯：最小尺寸
            width = self.min_elevator_width
            height = self.min_elevator_height
        
        return int(width), int(height)
        
    def setup_ui(self):
        """设置用户界面"""
        # 主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 左侧控制面板
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        
        # 右侧可视化面板
        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # 控制面板
        self.setup_control_panel(left_frame)
        
        # 电梯状态面板
        self.setup_elevator_panel(left_frame)
        
        # 楼层状态面板
        self.setup_floor_panel(left_frame)
        
        # 统计信息面板
        self.setup_stats_panel(left_frame)
        
        # 可视化面板
        self.setup_visualization_panel(right_frame)
        
    def setup_control_panel(self, parent):
        """设置控制面板"""
        control_frame = ttk.LabelFrame(parent, text="控制面板", padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 按钮
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X)
        
        self.start_btn = ttk.Button(button_frame, text="启动模拟", command=self.start_simulation)
        self.start_btn.pack(fill=tk.X, pady=(0, 5))
        
        self.stop_btn = ttk.Button(button_frame, text="停止模拟", command=self.stop_simulation, state=tk.DISABLED)
        self.stop_btn.pack(fill=tk.X, pady=(0, 5))
        
        self.reset_btn = ttk.Button(button_frame, text="重置", command=self.reset_simulation)
        self.reset_btn.pack(fill=tk.X)
        
        # 状态显示
        status_frame = ttk.Frame(control_frame)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(status_frame, text="当前Tick:").pack()
        self.tick_label = ttk.Label(status_frame, text="0", font=("Arial", 12, "bold"))
        self.tick_label.pack()
        
        ttk.Label(status_frame, text="状态:").pack(pady=(5, 0))
        self.status_label = ttk.Label(status_frame, text="未启动", font=("Arial", 12, "bold"))
        self.status_label.pack()
        
    def setup_elevator_panel(self, parent):
        """设置电梯状态面板"""
        elevator_frame = ttk.LabelFrame(parent, text="电梯状态", padding=10)
        elevator_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 创建滚动区域
        canvas = tk.Canvas(elevator_frame, width=300, height=200)
        scrollbar = ttk.Scrollbar(elevator_frame, orient="vertical", command=canvas.yview)
        self.elevator_scroll_frame = ttk.Frame(canvas)
        
        self.elevator_scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.elevator_scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 电梯信息标签
        self.elevator_labels = {}
        
    def setup_floor_panel(self, parent):
        """设置楼层状态面板"""
        floor_frame = ttk.LabelFrame(parent, text="楼层状态", padding=10)
        floor_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 创建滚动区域
        canvas = tk.Canvas(floor_frame, width=300, height=150)
        scrollbar = ttk.Scrollbar(floor_frame, orient="vertical", command=canvas.yview)
        self.floor_scroll_frame = ttk.Frame(canvas)
        
        self.floor_scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.floor_scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 楼层信息标签
        self.floor_labels = {}
        
    def setup_stats_panel(self, parent):
        """设置统计信息面板"""
        stats_frame = ttk.LabelFrame(parent, text="统计信息", padding=10)
        stats_frame.pack(fill=tk.X)
        
        # 统计信息标签
        self.stats_labels = {}
        stats_info = [
            ("总乘客数", "total_passengers"),
            ("已完成乘客", "completed_passengers"),
            ("完成率", "completion_rate")
        ]
        
        for label_text, key in stats_info:
            frame = ttk.Frame(stats_frame)
            frame.pack(fill=tk.X, pady=2)
            
            ttk.Label(frame, text=f"{label_text}:").pack(side=tk.LEFT)
            self.stats_labels[key] = ttk.Label(frame, text="0", font=("Arial", 10, "bold"))
            self.stats_labels[key].pack(side=tk.RIGHT)
    
    def setup_visualization_panel(self, parent):
        """设置可视化面板"""
        viz_frame = ttk.LabelFrame(parent, text="电梯可视化", padding=10)
        viz_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建画布
        self.canvas = tk.Canvas(viz_frame, width=self.canvas_width, height=self.canvas_height, 
                               bg="white", relief=tk.SUNKEN, bd=2)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # 电梯矩形对象
        self.elevator_rects = {}
        self.floor_lines = {}
        self.passenger_indicators = {}
        
    def start_simulation(self):
        """启动模拟"""
        if self.is_running:
            print("模拟已在运行中")
            return
            
        try:
            # 创建控制器 - 使用algorithm类型而不是gui类型
            self.controller = NewElevatorController()
            
            # 为控制器添加GUI回调功能
            self.add_gui_callbacks()
            print("GUI回调已添加")
            
            # 启动控制器线程
            self.is_running = True
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            self.status_label.config(text="运行中")
            
            # 在新线程中运行控制器
            self.update_thread = threading.Thread(target=self.run_controller, daemon=True)
            self.update_thread.start()
            print("模拟启动成功")
            
        except Exception as e:
            print(f"启动模拟失败: {e}")
            messagebox.showerror("错误", f"启动模拟失败: {str(e)}")
            self.is_running = False
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.status_label.config(text="启动失败")
    
    def add_gui_callbacks(self):
        """为现有控制器添加GUI回调功能 - 完全不干扰算法"""
        if not self.controller:
            return
            
        # 保存原始方法
        original_on_init = self.controller.on_init
        original_on_event_execute_start = self.controller.on_event_execute_start
        original_on_event_execute_end = self.controller.on_event_execute_end
        
        def gui_on_init(elevators, floors):
            """带GUI回调的初始化"""
            result = original_on_init(elevators, floors)
            current_tick = getattr(self.controller, 'current_tick', 0)
            self.update_display(elevators, floors, current_tick)
            # 只在初始化时绘制建筑物
            self.draw_building()
            return result
            
        def gui_on_event_execute_start(tick, events, elevators, floors):
            """带GUI回调的事件执行前"""
            result = original_on_event_execute_start(tick, events, elevators, floors)
            self.update_display(elevators, floors, tick)
            return result
            
        def gui_on_event_execute_end(tick, events, elevators, floors):
            """带GUI回调的事件执行后"""
            result = original_on_event_execute_end(tick, events, elevators, floors)
            self.update_display(elevators, floors, tick)
            self.update_visualization()
            return result
        
        # 替换方法
        self.controller.on_init = gui_on_init
        self.controller.on_event_execute_start = gui_on_event_execute_start
        self.controller.on_event_execute_end = gui_on_event_execute_end
        
    def stop_simulation(self):
        """停止模拟"""
        if not self.is_running:
            return
            
        print("正在停止模拟...")
        self.is_running = False
        
        if self.controller:
            try:
                self.controller.stop()
                print("控制器已停止")
            except Exception as e:
                print(f"停止控制器时出错: {e}")
        
        # 等待线程结束
        if hasattr(self, 'update_thread') and self.update_thread and self.update_thread.is_alive():
            print("等待线程结束...")
            self.update_thread.join(timeout=2.0)
            
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="已停止")
        print("模拟已停止")
        
    def reset_simulation(self):
        """重置模拟"""
        self.stop_simulation()
        
        # 清理数据
        self.elevators = []
        self.floors = []
        self.current_tick = 0
        
        # 清理控制器
        self.controller = None
        
        # 清理画布
        self.canvas.delete("all")
        
        # 清理电梯矩形字典和状态缓存
        self.elevator_rects = {}
        self.elevator_states = {}
        
        # 更新显示
        self.update_display()
        
        # 重置按钮状态
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.status_label.config(text="已重置")
        
        print("模拟已重置，可以重新启动")
            
    def run_controller(self):
        """运行控制器"""
        try:
            if self.controller:
                self.controller.start()
        except Exception as e:
            print(f"控制器运行错误: {e}")
        finally:
            self.is_running = False
            self.root.after(0, lambda: self.stop_simulation())
    
    def update_display(self, elevators=None, floors=None, tick=None):
        """更新显示"""
        if not self.is_running:
            return
            
        # 更新数据
        if elevators is not None:
            self.elevators = elevators
        if floors is not None:
            self.floors = floors
        if tick is not None:
            self.current_tick = tick
            
        # 在主线程中更新UI
        self.root.after(0, self._update_ui)
    
    def _update_ui(self):
        """更新UI元素"""
        # 更新tick显示
        self.tick_label.config(text=str(self.current_tick))
        
        # 更新电梯状态
        self.update_elevator_display()
        
        # 更新楼层状态
        self.update_floor_display()
        
        # 更新统计信息
        self.update_stats_display()
    
    def draw_building(self):
        """绘制建筑物 - 美化版本，只在初始化时调用"""
        if not self.floors:
            return
            
        # 只清除背景，保留电梯
        self.canvas.delete("background")
        self.canvas.delete("floor")
        
        # 绘制背景渐变效果
        for i in range(self.canvas_height):
            color_intensity = int(255 - (i / self.canvas_height) * 50)
            color = f"#{color_intensity:02x}{color_intensity:02x}{255:02x}"
            self.canvas.create_line(0, i, self.canvas_width, i, fill=color, width=1, tags="background")
        
        # 绘制楼层线
        for floor in self.floors:
            y = self.canvas_height - (floor.floor + 1) * self.floor_height
            
            # 绘制楼层背景
            self.canvas.create_rectangle(
                0, y - self.floor_height + 5,
                self.canvas_width, y - 5,
                fill="#F5F5F5", outline="#E0E0E0", width=1, tags="floor"
            )
            
            # 绘制楼层线
            self.floor_lines[floor.floor] = self.canvas.create_line(
                0, y, self.canvas_width, y, fill="#424242", width=3, tags="floor"
            )
            
            # 绘制楼层号 - 更美观的样式，楼层号从1开始显示
            self.canvas.create_rectangle(
                5, y - 25, 35, y - 5,
                fill="#2196F3", outline="#1976D2", width=2, tags="floor"
            )
            self.canvas.create_text(20, y - 15, text=f"F{floor.floor + 1}", 
                                   font=("Arial", 12, "bold"), fill="white", tags="floor")
            
            # 绘制楼层装饰线
            self.canvas.create_line(40, y - 15, 100, y - 15, fill="#BDBDBD", width=1, tags="floor")
            
            # 绘制电梯区域和乘客等待区域的分隔线
            separator_x = self.canvas_width - 200
            self.canvas.create_line(separator_x, y - self.floor_height + 5, separator_x, y - 5, 
                                   fill="#E0E0E0", width=1, dash=(5, 5), tags="floor")
    
    def update_visualization(self):
        """更新可视化 - 平滑动画，只更新电梯位置"""
        if not self.elevators or not self.floors:
            return
            
        # 检查电梯数量是否发生变化，如果变化则重新创建所有电梯
        current_elevator_count = len(self.elevators)
        if hasattr(self, '_last_elevator_count') and self._last_elevator_count != current_elevator_count:
            # 电梯数量发生变化，清理现有电梯并重新创建
            self.canvas.delete("elevator")
            self.elevator_rects = {}
            self.elevator_states = {}
        
        self._last_elevator_count = current_elevator_count
            
        # 只更新电梯位置，不清除现有元素
        for i, elevator in enumerate(self.elevators):
            self.update_elevator_position(elevator, i)
            
        # 更新楼层等待乘客显示
        self.update_floor_passengers_display()
    
    def update_floor_passengers_display(self):
        """更新楼层等待乘客显示 - 只更新，不重绘整个建筑物"""
        if not self.floors:
            return
            
        # 清除旧的乘客指示器
        self.canvas.delete("queue_text")
        self.canvas.delete("queue_icon")
        self.canvas.delete("more_indicator")
        
        # 为每个楼层绘制等待乘客
        for floor in self.floors:
            self.draw_floor_passengers_for_floor(floor)
    
    def draw_floor_passengers_for_floor(self, floor):
        """为单个楼层绘制等待乘客"""
        floor_num = getattr(floor, 'floor', 0)
        y = self.canvas_height - (floor_num + 1) * self.floor_height
        
        # 计算乘客等待状态显示区域（电梯右侧）
        passenger_area_start = self.canvas_width - 200  # 从右侧200像素开始
        
        # 绘制上行等待乘客
        up_queue = getattr(floor, 'up_queue', [])
        if up_queue:
            # 上行乘客标签
            self.canvas.create_text(passenger_area_start + 20, y - 25, text="↑ 上行", font=("Arial", 9, "bold"), fill="#2196F3", tags="queue_text")
            
            for i in range(min(5, len(up_queue))):  # 最多显示5个
                x = passenger_area_start + 20 + i * 18
                # 乘客图标背景
                self.canvas.create_oval(x - 6, y - 16, x + 6, y - 4, 
                                       fill="#E3F2FD", outline="#2196F3", width=2, tags="queue_icon")
                self.canvas.create_text(x, y - 10, text="👤", font=("Arial", 8), tags="queue_icon")
                
            if len(up_queue) > 5:
                # 更多乘客指示器
                more_x = passenger_area_start + 20 + 5 * 18 + 10
                self.canvas.create_oval(more_x - 8, y - 16, more_x + 8, y - 4,
                                       fill="#FF9800", outline="#F57C00", width=2, tags="more_indicator")
                self.canvas.create_text(more_x, y - 10, text=f"+{len(up_queue)-5}", 
                                       font=("Arial", 8, "bold"), fill="white", tags="more_indicator")
        
        # 绘制下行等待乘客
        down_queue = getattr(floor, 'down_queue', [])
        if down_queue:
            # 下行乘客标签
            self.canvas.create_text(passenger_area_start + 20, y - 35, text="↓ 下行", font=("Arial", 9, "bold"), fill="#F44336", tags="queue_text")
            
            for i in range(min(5, len(down_queue))):  # 最多显示5个
                x = passenger_area_start + 20 + i * 18
                # 乘客图标背景
                self.canvas.create_oval(x - 6, y - 26, x + 6, y - 14, 
                                       fill="#FFEBEE", outline="#F44336", width=2, tags="queue_icon")
                self.canvas.create_text(x, y - 20, text="👤", font=("Arial", 8), tags="queue_icon")
                
            if len(down_queue) > 5:
                # 更多乘客指示器
                more_x = passenger_area_start + 20 + 5 * 18 + 10
                self.canvas.create_oval(more_x - 8, y - 26, more_x + 8, y - 14,
                                       fill="#FF9800", outline="#F57C00", width=2, tags="more_indicator")
                self.canvas.create_text(more_x, y - 20, text=f"+{len(down_queue)-5}", 
                                       font=("Arial", 8, "bold"), fill="white", tags="more_indicator")
    
    def update_elevator_position(self, elevator, index):
        """更新电梯位置 - 平滑移动，避免频繁重绘，支持动态大小"""
        # 计算电梯位置
        current_floor = getattr(elevator, 'current_floor', 0)
        current_floor_float = getattr(elevator, 'current_floor_float', current_floor)
        
        # 计算楼层线Y坐标
        floor_y = self.canvas_height - (current_floor_float + 1) * self.floor_height
        
        # 根据电梯数量动态调整电梯大小
        num_elevators = len(self.elevators)
        self.elevator_width, self.elevator_height = self.calculate_elevator_params(num_elevators)
        
        # 计算电梯Y坐标 - 电梯底部与楼层线对齐
        y = floor_y - self.elevator_height
        
        # 计算X坐标（多个电梯并排，考虑动态大小，向右偏移为乘客等待状态留空间）
        # 为乘客等待状态预留空间（约200像素）
        passenger_area_width = 200
        available_width = self.canvas_width - passenger_area_width
        
        if num_elevators == 1:
            # 单个电梯在可用区域的中心显示
            x = (available_width - self.elevator_width) // 2
        else:
            # 多个电梯在可用区域内均匀分布
            total_width = num_elevators * self.elevator_width
            spacing = max(10, (available_width - total_width) // (num_elevators + 1))
            x = spacing + index * (self.elevator_width + spacing)
        
        # 获取当前电梯状态
        current_state = {
            'is_idle': getattr(elevator, 'is_idle', True),
            'direction': getattr(elevator, 'last_tick_direction', Direction.STOPPED),
            'passenger_count': len(getattr(elevator, 'passengers', [])),
            'current_floor': current_floor
        }
        
        # 如果电梯矩形不存在，创建它
        if elevator.id not in self.elevator_rects:
            self.elevator_rects[elevator.id] = self.create_elevator_rect(elevator, x, y, index)
            self.elevator_states[elevator.id] = current_state
        else:
            # 检查位置或状态是否真的改变了
            rect_id = self.elevator_rects[elevator.id]
            current_coords = self.canvas.coords(rect_id)
            previous_state = self.elevator_states.get(elevator.id, {})
            
            position_changed = False
            state_changed = False
            
            if current_coords:
                current_x, current_y = current_coords[0], current_coords[1]
                # 检查位置变化
                if abs(current_x - x) > 1 or abs(current_y - y) > 1:
                    position_changed = True
                    # 移动现有矩形到新位置
                    self.canvas.coords(rect_id, x, y, x + self.elevator_width, y + self.elevator_height)
            
            # 检查状态变化
            if previous_state != current_state:
                state_changed = True
                self.elevator_states[elevator.id] = current_state
            
            # 只有当位置或状态真正改变时才更新文本
            if position_changed or state_changed:
                self.update_elevator_text(rect_id, elevator, x, y)
    
    def create_elevator_rect(self, elevator, x, y, index):
        """创建电梯矩形 - 使用动态大小"""
        # 获取电梯状态
        is_idle = getattr(elevator, 'is_idle', True)
        direction = getattr(elevator, 'last_tick_direction', Direction.STOPPED)
        
        # 根据状态选择颜色
        if is_idle:
            fill_color = "#E8F5E8"  # 浅绿色 - 空闲
            outline_color = "#4CAF50"  # 绿色边框
        else:
            if direction == Direction.UP:
                fill_color = "#E3F2FD"  # 浅蓝色 - 上行
                outline_color = "#2196F3"  # 蓝色边框
            elif direction == Direction.DOWN:
                fill_color = "#FFF3E0"  # 浅橙色 - 下行
                outline_color = "#FF9800"  # 橙色边框
            else:
                fill_color = "#F3E5F5"  # 浅紫色 - 停止
                outline_color = "#9C27B0"  # 紫色边框
        
        # 根据电梯大小调整边框宽度
        border_width = 2 if self.elevator_width >= 50 else 1
        
        # 创建电梯矩形
        rect_id = self.canvas.create_rectangle(
            x, y, x + self.elevator_width, y + self.elevator_height,
            fill=fill_color, outline=outline_color, width=border_width,
            tags="elevator"
        )
        
        # 添加电梯文本
        self.update_elevator_text(rect_id, elevator, x, y)
        
        return rect_id
    
    def update_elevator_text(self, rect_id, elevator, x, y):
        """更新电梯内的文本 - 优化版本，避免频繁重绘，适应动态大小"""
        # 检查文本是否已存在
        existing_texts = self.canvas.find_withtag(f"elevator_text_{elevator.id}")
        
        # 根据电梯大小调整字体大小
        if self.elevator_width < 50:
            id_font = ("Arial", 8, "bold")
            info_font = ("Arial", 6)
            text_spacing = 8
        elif self.elevator_width < 70:
            id_font = ("Arial", 9, "bold")
            info_font = ("Arial", 7)
            text_spacing = 10
        else:
            id_font = ("Arial", 10, "bold")
            info_font = ("Arial", 8)
            text_spacing = 12
        
        if not existing_texts:
            # 如果文本不存在，创建它们
            # 电梯ID
            self.canvas.create_text(
                x + self.elevator_width // 2, y + text_spacing,
                text=f"E{elevator.id}", font=id_font,
                fill="black", tags=f"elevator_text_{elevator.id}"
            )
            
            # 乘客数量
            passenger_count = len(getattr(elevator, 'passengers', []))
            self.canvas.create_text(
                x + self.elevator_width // 2, y + text_spacing * 2,
                text=f"👥{passenger_count}", font=info_font,
                fill="black", tags=f"elevator_text_{elevator.id}"
            )
            
            # 当前楼层 - 楼层号从1开始显示
            current_floor = getattr(elevator, 'current_floor', 0)
            self.canvas.create_text(
                x + self.elevator_width // 2, y + text_spacing * 3,
                text=f"F{current_floor + 1}", font=info_font,
                fill="black", tags=f"elevator_text_{elevator.id}"
            )
        else:
            # 如果文本已存在，只更新位置和内容
            texts = list(existing_texts)
            if len(texts) >= 3:
                # 更新位置
                self.canvas.coords(texts[0], x + self.elevator_width // 2, y + text_spacing)  # ID
                self.canvas.coords(texts[1], x + self.elevator_width // 2, y + text_spacing * 2)  # 乘客
                self.canvas.coords(texts[2], x + self.elevator_width // 2, y + text_spacing * 3)  # 楼层
                
                # 更新字体大小
                self.canvas.itemconfig(texts[0], font=id_font)
                self.canvas.itemconfig(texts[1], font=info_font)
                self.canvas.itemconfig(texts[2], font=info_font)
                
                # 更新内容（如果需要）
                passenger_count = len(getattr(elevator, 'passengers', []))
                current_floor = getattr(elevator, 'current_floor', 0)
                
                self.canvas.itemconfig(texts[1], text=f"👥{passenger_count}")
                self.canvas.itemconfig(texts[2], text=f"F{current_floor + 1}")
    
    def draw_elevator(self, elevator, index):
        """绘制单个电梯 - 美化版本"""
        # 计算电梯位置
        current_floor = getattr(elevator, 'current_floor', 0)
        current_floor_float = getattr(elevator, 'current_floor_float', current_floor)
        
        # 计算楼层线Y坐标
        floor_y = self.canvas_height - (current_floor_float + 1) * self.floor_height
        
        # 计算电梯Y坐标 - 电梯底部与楼层线对齐
        y = floor_y - self.elevator_height
        
        # 计算X坐标（多个电梯并排）
        num_elevators = len(self.elevators)
        x_spacing = self.canvas_width // (num_elevators + 1)
        x = x_spacing * (index + 1) - self.elevator_width // 2
        
        # 获取电梯状态
        is_idle = getattr(elevator, 'is_idle', True)
        direction = getattr(elevator, 'last_tick_direction', Direction.STOPPED)
        passenger_count = len(getattr(elevator, 'passengers', []))
        
        # 根据状态选择颜色
        if is_idle:
            fill_color = "#E8F5E8"  # 浅绿色 - 空闲
            outline_color = "#4CAF50"  # 绿色边框
        else:
            if direction == Direction.UP:
                fill_color = "#E3F2FD"  # 浅蓝色 - 上行
                outline_color = "#2196F3"  # 蓝色边框
            elif direction == Direction.DOWN:
                fill_color = "#FFEBEE"  # 浅红色 - 下行
                outline_color = "#F44336"  # 红色边框
            else:
                fill_color = "#FFF3E0"  # 浅橙色 - 其他状态
                outline_color = "#FF9800"  # 橙色边框
        
        # 绘制电梯主体 - 圆角矩形效果
        rect_id = self.canvas.create_rectangle(
            x + 2, y + 2,
            x + self.elevator_width - 2, y + self.elevator_height - 2,
            fill=fill_color, outline=outline_color, width=3, tags="elevator"
        )
        self.elevator_rects[elevator.id] = rect_id
        
        # 绘制电梯门（装饰性）
        door_width = 8
        door_x = x + self.elevator_width // 2 - door_width // 2
        self.canvas.create_rectangle(
            door_x, y + 8,
            door_x + door_width, y + self.elevator_height - 8,
            fill=outline_color, outline="", width=0, tags="elevator"
        )
        
        # 绘制电梯ID - 更美观的字体
        self.canvas.create_text(
            x + self.elevator_width // 2, y + 15,
            text=f"电梯 {elevator.id}", font=("Arial", 11, "bold"), fill=outline_color, tags="elevator"
        )
        
        # 绘制当前楼层 - 大字体显示，楼层号从1开始显示
        self.canvas.create_text(
            x + self.elevator_width // 2, y + self.elevator_height // 2,
            text=f"{current_floor + 1}", font=("Arial", 16, "bold"), fill="black", tags="elevator"
        )
        
        # 绘制乘客数量 - 更美观的显示
        if passenger_count > 0:
            # 乘客图标背景
            self.canvas.create_oval(
                x + 5, y + 5, x + 20, y + 20,
                fill="#FFC107", outline="#FF9800", width=2, tags="passenger"
            )
            self.canvas.create_text(
                x + 12, y + 12,
                text=f"{passenger_count}", font=("Arial", 9, "bold"), fill="white", tags="passenger"
            )
        
        # 绘制方向指示器 - 更美观的箭头
        if direction == Direction.UP:
            # 上行箭头
            arrow_points = [
                x + self.elevator_width - 15, y + 10,
                x + self.elevator_width - 10, y + 15,
                x + self.elevator_width - 5, y + 10,
                x + self.elevator_width - 10, y + 5
            ]
            self.canvas.create_polygon(arrow_points, fill="#4CAF50", outline="#2E7D32", width=1, tags="arrow")
        elif direction == Direction.DOWN:
            # 下行箭头
            arrow_points = [
                x + self.elevator_width - 15, y + 15,
                x + self.elevator_width - 10, y + 10,
                x + self.elevator_width - 5, y + 15,
                x + self.elevator_width - 10, y + 20
            ]
            self.canvas.create_polygon(arrow_points, fill="#F44336", outline="#C62828", width=1, tags="arrow")
        
        # 绘制状态指示器
        status_x = x + 5
        status_y = y + self.elevator_height - 5
        if is_idle:
            # 空闲状态 - 绿色圆点
            self.canvas.create_oval(
                status_x, status_y - 3, status_x + 6, status_y + 3,
                fill="#4CAF50", outline="", tags="status"
            )
        else:
            # 运行状态 - 红色圆点
            self.canvas.create_oval(
                status_x, status_y - 3, status_x + 6, status_y + 3,
                fill="#F44336", outline="", tags="status"
            )
        
    
    def update_elevator_display(self):
        """更新电梯显示 - 避免重复创建组件"""
        if not self.elevators:
            return
            
        # 清除现有标签
        for widget in self.elevator_scroll_frame.winfo_children():
            widget.destroy()
        self.elevator_labels = {}
            
        # 创建电梯信息
        for elevator in self.elevators:
            frame = ttk.Frame(self.elevator_scroll_frame)
            frame.pack(fill=tk.X, pady=2)
            
            # 电梯ID
            ttk.Label(frame, text=f"电梯 {elevator.id}", font=("Arial", 10, "bold")).pack(side=tk.LEFT, padx=(0, 5))
            
            # 当前位置 - 楼层号从1开始显示
            current_floor = getattr(elevator, 'current_floor', 0)
            ttk.Label(frame, text=f"F{current_floor + 1}").pack(side=tk.LEFT, padx=(0, 5))
            
            # 目标楼层 - 楼层号从1开始显示
            target_floor = getattr(elevator, 'target_floor', current_floor)
            ttk.Label(frame, text=f"→F{target_floor + 1}").pack(side=tk.LEFT, padx=(0, 5))
            
            # 状态
            status = "运行中" if not getattr(elevator, 'is_idle', True) else "空闲"
            status_color = "red" if status == "运行中" else "green"
            status_label = ttk.Label(frame, text=status, foreground=status_color)
            status_label.pack(side=tk.LEFT, padx=(0, 5))
            
            # 乘客数量
            passenger_count = len(getattr(elevator, 'passengers', []))
            ttk.Label(frame, text=f"👥{passenger_count}").pack(side=tk.LEFT)
    
    def update_floor_display(self):
        """更新楼层显示"""
        # 清除现有标签
        for widget in self.floor_scroll_frame.winfo_children():
            widget.destroy()
        self.floor_labels = {}
        
        if not self.floors:
            return
            
        # 创建楼层信息 - 从高楼层到低楼层显示
        for floor in reversed(self.floors):
            frame = ttk.Frame(self.floor_scroll_frame)
            frame.pack(fill=tk.X, pady=1)
            
            # 楼层号 - 楼层号从1开始显示
            floor_num = getattr(floor, 'floor', 0)
            ttk.Label(frame, text=f"F{floor_num + 1}", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(0, 5))
            
            # 上行队列
            up_queue = getattr(floor, 'up_queue', [])
            up_count = len(up_queue) if up_queue else 0
            if up_count > 0:
                ttk.Label(frame, text=f"↑{up_count}", foreground="blue").pack(side=tk.LEFT, padx=(0, 5))
            
            # 下行队列
            down_queue = getattr(floor, 'down_queue', [])
            down_count = len(down_queue) if down_queue else 0
            if down_count > 0:
                ttk.Label(frame, text=f"↓{down_count}", foreground="red").pack(side=tk.LEFT, padx=(0, 5))
            
            # 总等待人数
            total_waiting = up_count + down_count
            if total_waiting > 0:
                ttk.Label(frame, text=f"等待:{total_waiting}", foreground="orange").pack(side=tk.LEFT, padx=(5, 0))
            else:
                ttk.Label(frame, text="空闲", foreground="green").pack(side=tk.LEFT, padx=(5, 0))
    
    def update_stats_display(self):
        """更新统计信息显示"""
        # 显示从控制器获取的统计信息
        if self.controller and hasattr(self.controller, 'user_data'):
            total_passengers = len(self.controller.user_data)
            completed_passengers = sum(1 for data in self.controller.user_data.values() 
                                     if data.get('completed', False))
            
            self.stats_labels['total_passengers'].config(text=str(total_passengers))
            self.stats_labels['completed_passengers'].config(text=str(completed_passengers))
            
            if total_passengers > 0:
                completion_rate = completed_passengers / total_passengers
                self.stats_labels['completion_rate'].config(text=f"{completion_rate:.2%}")
    
    def run(self):
        """运行GUI"""
        self.root.mainloop()


if __name__ == "__main__":
    # 启动GUI
    gui = ElevatorGUI()
    gui.run()