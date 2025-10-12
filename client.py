#!/usr/bin/env python3
from typing import List
import json
import os
from collections import defaultdict

from elevator_saga.client.base_controller import ElevatorController
from elevator_saga.client.proxy_models import ProxyElevator, ProxyFloor, ProxyPassenger
from elevator_saga.core.models import SimulationEvent

# Look算法based调度

class TestElevatorBusController(ElevatorController):
    def __init__(self):
        super().__init__("http://127.0.0.1:8000", True)
        
        # 读取traffic.json配置文件
        config_path = os.path.join(os.path.dirname(__file__), 'traffic.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        
        # 建筑配置信息
        self.building_config = self.config['building']
        self.num_floors = self.building_config['floors']  # 楼层数
        self.num_elevators = self.building_config['elevators']  # 电梯数
        self.elevator_capacity = self.building_config['elevator_capacity']  # 电梯容量
        self.scenario = self.building_config['scenario']  # 场景类型
        self.duration = self.building_config['duration']  # 仿真持续时间
        
        # 乘客流量数据
        self.traffic_data = self.config['traffic']
        self.passenger_schedule = {}  # {tick: [passenger_data]}
        for passenger in self.traffic_data:
            tick = passenger['tick']
            if tick not in self.passenger_schedule:
                self.passenger_schedule[tick] = []
            self.passenger_schedule[tick].append(passenger)
        
        # 呼叫队列：记录每层楼的上/下行呼叫请求
        # {floor_id: {'up': [passenger_ids], 'down': [passenger_ids]}}
        self.hall_calls = defaultdict(lambda: {'up': [], 'down': []})
        
        # 电梯任务队列：记录每个电梯的目标楼层列表
        # {elevator_id: set(floor_ids)}  使用set避免重复楼层
        self.elevator_tasks = {}
        
        # 电梯状态跟踪
        # {elevator_id: {'direction': 'up/down/idle', 'current_floor': int, 'passengers': []}}
        self.elevator_states = {}
        
        # 电梯内乘客目标楼层
        # {elevator_id: {floor_id: [passenger_ids]}}
        self.elevator_destinations = {}
        
        # 当前tick
        self.current_tick = 0
        
        # 电梯对象引用（在on_init中初始化）
        self.elevators = []
        self.floors = []
        

    def on_init(self, elevators: List[ProxyElevator], floors: List[ProxyFloor]) -> None:
        """初始化电梯系统，设置所有电梯的初始状态"""
        print(f"初始化电梯调度系统...")
        print(f"楼层数: {self.num_floors}, 电梯数: {self.num_elevators}, 电梯容量: {self.elevator_capacity}")
        
        # 保存电梯和楼层代理对象引用
        self.elevators = elevators
        self.floors = floors
        
        # 验证电梯和楼层数量
        if len(elevators) != self.num_elevators:
            print(f"警告：实际电梯数({len(elevators)})与配置({self.num_elevators})不符")
        if len(floors) != self.num_floors:
            print(f"警告：实际楼层数({len(floors)})与配置({self.num_floors})不符")
        
        # 初始化每个电梯的状态
        for elevator in elevators:
            elevator_id = elevator.id
            
            # 初始化电梯任务队列（使用set存储目标楼层，避免重复）
            self.elevator_tasks[elevator_id] = set()
            
            # 初始化电梯状态，使用ProxyElevator的属性
            self.elevator_states[elevator_id] = {
                'direction': 'idle',  # 初始为空闲状态
                'current_floor': elevator.current_floor,  # 从ProxyElevator获取当前楼层
                'passengers': list(elevator.passengers),  # 复制乘客ID列表
                'load_factor': elevator.load_factor,  # 载重系数
                'is_full': elevator.is_full,  # 是否满载
                'pressed_floors': list(elevator.pressed_floors)  # 已按下的楼层按钮
            }
            
            # 初始化电梯内乘客目标楼层映射
            self.elevator_destinations[elevator_id] = defaultdict(list)
            # 如果电梯已有乘客，初始化其目标楼层
            if elevator.passenger_destinations:
                for passenger_id, destination in elevator.passenger_destinations.items():
                    self.elevator_destinations[elevator_id][destination].append(passenger_id)
            
            # 打印电梯初始状态
            print(f"电梯{elevator_id}: 当前楼层{elevator.current_floor}, "
                  f"状态{elevator.run_status.value}, 乘客数{len(elevator.passengers)}")
            
            # 可以考虑将电梯分布在不同楼层待命
            if self.num_elevators > 1 and elevator.is_idle:
                # 将电梯均匀分布在各楼层（楼层编号从0开始）
                # 例如：2部电梯，6层楼（0-5），分配到0楼和5楼
                if self.num_elevators > 1:
                    initial_floor = elevator_id * (self.num_floors - 1) // (self.num_elevators - 1)
                else:
                    initial_floor = 0  # 单电梯默认在底层
                
                if initial_floor != elevator.current_floor:
                    # 使用ProxyElevator的go_to_floor方法
                    success = elevator.go_to_floor(initial_floor)
                    if success:
                        print(f"派遣电梯{elevator_id}到{initial_floor}楼待命")
        
        # 打印楼层初始状态
        print(f"楼层编号范围: {[f.floor for f in floors]}")
        for floor in floors:
            if floor.has_waiting_passengers:
                print(f"楼层{floor.floor}: 上行等待{len(floor.up_queue)}人, 下行等待{len(floor.down_queue)}人")
                
        print(f"电梯系统初始化完成。共有{len(elevators)}台电梯，{len(floors)}个楼层。")
        print(f"预计总乘客数: {len(self.traffic_data)}，仿真时长: {self.duration} ticks")

    def on_event_execute_start(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        """每个tick开始时的事件处理"""
        self.current_tick = tick
        
        # 更新电梯和楼层引用
        self.elevators = elevators
        self.floors = floors
        
        # 检查是否有新乘客在这个tick到达（基于预加载的流量数据）
        if tick in self.passenger_schedule:
            passengers_arriving = self.passenger_schedule[tick]
            for passenger_data in passengers_arriving:
                # 注意：traffic.json中楼层从1开始，需要转换为0开始（如果系统使用0开始）
                origin = passenger_data['origin']
                destination = passenger_data['destination']
                passenger_id = passenger_data['id']
                
                # 检查楼层编号系统（通过查看floors列表）
                if self.floors and self.floors[0].floor == 0:
                    # 系统使用0开始的楼层编号，需要转换
                    origin = origin - 1
                    destination = destination - 1
                
                # 确定呼叫方向
                direction = 'up' if destination > origin else 'down'
                
                # 记录呼叫请求到hall_calls（使用转换后的楼层号）
                self.hall_calls[origin][direction].append(passenger_id)
                
                print(f"Tick {tick}: 乘客{passenger_id}在{origin}楼呼叫电梯，目标{destination}楼，方向{direction}")
        
        # 更新所有电梯的当前状态（从ProxyElevator获取最新状态）
        for elevator in elevators:
            elevator_id = elevator.id
            
            # 更新电梯状态，同步ProxyElevator的属性
            self.elevator_states[elevator_id].update({
                'current_floor': elevator.current_floor,
                'passengers': list(elevator.passengers),
                'load_factor': elevator.load_factor,
                'is_full': elevator.is_full,
                'pressed_floors': list(elevator.pressed_floors),
                'run_status': elevator.run_status.value
            })
            
            # 根据电梯运行状态和任务确定方向
            if elevator.is_idle and not self.elevator_tasks[elevator_id]:
                self.elevator_states[elevator_id]['direction'] = 'idle'
            elif elevator.target_floor > elevator.current_floor:
                self.elevator_states[elevator_id]['direction'] = 'up'
            elif elevator.target_floor < elevator.current_floor:
                self.elevator_states[elevator_id]['direction'] = 'down'
            
            # 同步乘客目标楼层信息
            self.elevator_destinations[elevator_id].clear()
            for passenger_id, destination in elevator.passenger_destinations.items():
                self.elevator_destinations[elevator_id][destination].append(passenger_id)

    def on_event_execute_end(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        """每个tick结束时的事件处理"""
        # 更新引用
        self.elevators = elevators
        self.floors = floors
        
        # 处理LOOK算法的调度逻辑
        for elevator in elevators:
            elevator_id = elevator.id
            state = self.elevator_states[elevator_id]
            
            # 如果电梯处于idle状态，检查是否有呼叫需要响应
            if elevator.is_idle and not self.elevator_tasks[elevator_id]:
                # 查找最近的呼叫请求
                self._assign_nearest_call_to_idle_elevator(elevator)
            
            # 清理已经完成的任务
            current_floor = elevator.current_floor
            if current_floor in self.elevator_tasks[elevator_id]:
                # 检查该楼层是否还有乘客需要下电梯或上电梯
                floor_obj = self._get_floor_by_number(current_floor)
                if floor_obj and not self._has_passengers_for_floor(elevator, floor_obj):
                    self.elevator_tasks[elevator_id].discard(current_floor)
        
        # 同步楼层等待队列状态
        for floor in floors:
            # 清理已经上电梯的乘客
            actual_up_queue = [pid for pid in self.hall_calls[floor.floor]['up'] 
                             if pid in floor.up_queue]
            actual_down_queue = [pid for pid in self.hall_calls[floor.floor]['down'] 
                               if pid in floor.down_queue]
            self.hall_calls[floor.floor]['up'] = actual_up_queue
            self.hall_calls[floor.floor]['down'] = actual_down_queue
        
        # 打印当前系统状态（用于调试）
        if tick % 10 == 0:  # 每10个tick打印一次
            self._print_system_status(tick)
    
    def _get_floor_by_number(self, floor_number: int) -> ProxyFloor:
        """根据楼层号获取楼层对象"""
        for floor in self.floors:
            if floor.floor == floor_number:
                return floor
        return None
    
    def _assign_nearest_call_to_idle_elevator(self, elevator: ProxyElevator):
        """为空闲电梯分配最近的呼叫请求"""
        elevator_id = elevator.id
        current_floor = elevator.current_floor
        
        nearest_floor = None
        min_distance = float('inf')
        
        # 遍历所有楼层的呼叫请求
        for floor in self.floors:
            floor_calls = self.hall_calls[floor.floor]
            # 检查楼层是否有等待的乘客
            if floor.has_waiting_passengers or floor_calls['up'] or floor_calls['down']:
                distance = abs(floor.floor - current_floor)
                if distance < min_distance:
                    min_distance = distance
                    nearest_floor = floor.floor
        
        # 如果找到呼叫请求，分配给电梯
        if nearest_floor is not None:
            self.elevator_tasks[elevator_id].add(nearest_floor)
            # 使用ProxyElevator的go_to_floor方法发送命令
            success = elevator.go_to_floor(nearest_floor)
            
            if success:
                # 更新内部状态
                if nearest_floor > current_floor:
                    self.elevator_states[elevator_id]['direction'] = 'up'
                elif nearest_floor < current_floor:
                    self.elevator_states[elevator_id]['direction'] = 'down'
                else:
                    # 已经在目标楼层
                    self.elevator_states[elevator_id]['direction'] = 'idle'
                
                print(f"分配电梯{elevator_id}响应{nearest_floor}楼的呼叫")
    
    def _has_passengers_for_floor(self, elevator: ProxyElevator, floor: ProxyFloor) -> bool:
        """检查电梯在指定楼层是否有乘客需要上下"""
        elevator_id = elevator.id
        floor_number = floor.floor
        
        # 检查是否有乘客要在这层下电梯（使用ProxyElevator的属性）
        if floor_number in elevator.pressed_floors:
            return True
        
        # 检查电梯内是否有乘客的目标楼层是这层
        if floor_number in elevator.passenger_destinations.values():
            return True
        
        # 检查是否有乘客在这层等待上电梯（使用ProxyFloor的属性）
        if floor.has_waiting_passengers:
            direction = self.elevator_states[elevator_id]['direction']
            # 检查等待方向是否与电梯方向一致
            if direction == 'up' and floor.up_queue:
                return True
            elif direction == 'down' and floor.down_queue:
                return True
            # 如果电梯空闲，任何方向的等待乘客都可以
            elif direction == 'idle' and (floor.up_queue or floor.down_queue):
                return True
        
        return False
    
    def _print_system_status(self, tick: int):
        """打印系统状态用于调试"""
        print(f"\n=== Tick {tick} 系统状态 ===")
        
        # 使用ProxyElevator对象打印电梯状态
        for elevator in self.elevators:
            tasks = list(self.elevator_tasks[elevator.id])
            direction = self.elevator_states[elevator.id]['direction']
            print(f"电梯{elevator.id}: 楼层{elevator.current_floor:.1f}, "
                  f"状态{elevator.run_status.value}, 方向{direction}, "
                  f"任务{tasks}, 乘客数{len(elevator.passengers)}/{elevator.max_capacity}")
            if elevator.passengers:
                destinations = [elevator.passenger_destinations.get(pid, '?') 
                              for pid in elevator.passengers]
                print(f"  乘客目标楼层: {destinations}")
        
        # 使用ProxyFloor对象打印楼层状态
        for floor in self.floors:
            if floor.has_waiting_passengers:
                print(f"楼层{floor.floor}: 上行等待{len(floor.up_queue)}人, "
                      f"下行等待{len(floor.down_queue)}人")
                # 显示等待乘客的详细信息
                if floor.up_queue:
                    print(f"  上行乘客ID: {floor.up_queue}")
                if floor.down_queue:
                    print(f"  下行乘客ID: {floor.down_queue}")
    
    def _should_stop_at_floor(self, elevator: ProxyElevator, floor: ProxyFloor) -> bool:
        """根据LOOK算法判断电梯是否应该在该楼层停靠"""
        elevator_id = elevator.id
        floor_number = floor.floor
        direction = self.elevator_states[elevator_id]['direction']
        
        # 1. 有乘客要在这层下电梯
        if floor_number in elevator.pressed_floors:
            return True
        
        # 2. 电梯不满，且有同方向的乘客等待
        if not elevator.is_full:
            if direction == 'up' and floor.up_queue:
                return True
            elif direction == 'down' and floor.down_queue:
                return True
        
        # 3. 这是电梯的任务楼层之一
        if floor_number in self.elevator_tasks[elevator_id]:
            # 检查是否有乘客等待（任意方向）
            if floor.has_waiting_passengers:
                return True
        
        return False
    
    def _get_next_floor_in_direction(self, elevator: ProxyElevator) -> int:
        """获取电梯当前方向上的下一个目标楼层（LOOK算法）"""
        elevator_id = elevator.id
        current_floor = elevator.current_floor
        direction = self.elevator_states[elevator_id]['direction']
        
        candidate_floors = []
        
        # 1. 电梯内乘客的目标楼层（最高优先级）
        for destination in elevator.pressed_floors:
            if direction == 'up' and destination > current_floor:
                candidate_floors.append(destination)
            elif direction == 'down' and destination < current_floor:
                candidate_floors.append(destination)
        
        # 2. 同方向的楼层呼叫
        for floor in self.floors:
            floor_num = floor.floor
            if direction == 'up' and floor_num > current_floor:
                if floor.up_queue and not elevator.is_full:
                    candidate_floors.append(floor_num)
            elif direction == 'down' and floor_num < current_floor:
                if floor.down_queue and not elevator.is_full:
                    candidate_floors.append(floor_num)
        
        # 3. 如果电梯不满，也考虑反方向的呼叫（在当前方向上）
        if not elevator.is_full:
            for floor in self.floors:
                floor_num = floor.floor
                if direction == 'up' and floor_num > current_floor:
                    if floor.down_queue and floor_num not in candidate_floors:
                        candidate_floors.append(floor_num)
                elif direction == 'down' and floor_num < current_floor:
                    if floor.up_queue and floor_num not in candidate_floors:
                        candidate_floors.append(floor_num)
        
        if not candidate_floors:
            return None
        
        # 返回最近的楼层（LOOK算法特点）
        if direction == 'up':
            return min(candidate_floors)
        else:
            return max(candidate_floors)
    
    def _get_furthest_call_in_direction(self, elevator: ProxyElevator) -> int:
        """获取电梯当前方向上最远的呼叫楼层"""
        elevator_id = elevator.id
        current_floor = elevator.current_floor
        direction = self.elevator_states[elevator_id]['direction']
        
        furthest_floor = None
        
        # 检查电梯内乘客的目标楼层
        for destination in elevator.pressed_floors:
            if direction == 'up' and destination > current_floor:
                if furthest_floor is None or destination > furthest_floor:
                    furthest_floor = destination
            elif direction == 'down' and destination < current_floor:
                if furthest_floor is None or destination < furthest_floor:
                    furthest_floor = destination
        
        # 检查楼层呼叫
        for floor in self.floors:
            floor_num = floor.floor
            if direction == 'up' and floor_num > current_floor:
                if floor.up_queue or (not elevator.is_full and floor.down_queue):
                    if furthest_floor is None or floor_num > furthest_floor:
                        furthest_floor = floor_num
            elif direction == 'down' and floor_num < current_floor:
                if floor.down_queue or (not elevator.is_full and floor.up_queue):
                    if furthest_floor is None or floor_num < furthest_floor:
                        furthest_floor = floor_num
        
        return furthest_floor
    
    def _choose_best_elevator_for_call(self, floor: ProxyFloor, direction: str) -> ProxyElevator:
        """为楼层呼叫选择最佳电梯（LOOK算法）"""
        best_elevator = None
        min_cost = float('inf')
        
        for elevator in self.elevators:
            if elevator.is_full:
                continue
            
            cost = self._calculate_elevator_cost(elevator, floor.floor, direction)
            if cost < min_cost:
                min_cost = cost
                best_elevator = elevator
        
        return best_elevator
    
    def _calculate_elevator_cost(self, elevator: ProxyElevator, target_floor: int, call_direction: str) -> float:
        """计算电梯响应呼叫的成本"""
        elevator_id = elevator.id
        current_floor = elevator.current_floor
        elevator_direction = self.elevator_states[elevator_id]['direction']
        
        distance = abs(target_floor - current_floor)
        
        # LOOK算法的成本计算
        if elevator_direction == 'idle':
            # 空闲电梯：距离成本
            return distance
        
        elif elevator_direction == call_direction:
            # 同方向
            if (elevator_direction == 'up' and target_floor >= current_floor) or \
               (elevator_direction == 'down' and target_floor <= current_floor):
                # 电梯正在向呼叫楼层方向移动
                return distance
            else:
                # 电梯已经过了呼叫楼层，需要反向
                return distance + 1000  # 高成本
        
        else:
            # 反方向：需要先完成当前方向的所有请求
            furthest_floor = self._get_furthest_call_in_direction(elevator)
            if furthest_floor is not None:
                return abs(furthest_floor - current_floor) + abs(furthest_floor - target_floor) + 500
            else:
                return distance + 500

    def on_passenger_call(self, passenger:ProxyPassenger, floor: ProxyFloor, direction: str) -> None:
        """处理乘客呼叫电梯事件"""
        print(f"乘客{passenger.id}在{floor.floor}楼呼叫电梯，方向：{direction}，目标：{passenger.destination}楼")
        
        # 选择最佳电梯响应呼叫
        best_elevator = self._choose_best_elevator_for_call(floor, direction)
        
        if best_elevator:
            elevator_id = best_elevator.id
            # 添加到电梯任务队列
            self.elevator_tasks[elevator_id].add(floor.floor)
            
            # 如果电梯空闲，立即派遣
            if best_elevator.is_idle:
                success = best_elevator.go_to_floor(floor.floor)
                if success:
                    # 更新电梯方向
                    if floor.floor > best_elevator.current_floor:
                        self.elevator_states[elevator_id]['direction'] = 'up'
                    elif floor.floor < best_elevator.current_floor:
                        self.elevator_states[elevator_id]['direction'] = 'down'
                    print(f"派遣空闲电梯{elevator_id}去{floor.floor}楼接乘客")

    def on_elevator_idle(self, elevator: ProxyElevator) -> None:
        """处理电梯空闲事件"""
        elevator_id = elevator.id
        print(f"电梯{elevator_id}进入空闲状态，当前在{elevator.current_floor}楼")
        
        # 更新电梯状态为空闲
        self.elevator_states[elevator_id]['direction'] = 'idle'
        
        # 查找需要响应的呼叫
        self._assign_nearest_call_to_idle_elevator(elevator)

    def on_elevator_stopped(self, elevator: ProxyElevator, floor: ProxyFloor) -> None:
        """处理电梯停靠事件（LOOK算法核心）"""
        elevator_id = elevator.id
        floor_number = floor.floor
        direction = self.elevator_states[elevator_id]['direction']
        
        print(f"电梯{elevator_id}停靠在{floor_number}楼，方向：{direction}，乘客数：{len(elevator.passengers)}")
        
        # 从任务队列中移除当前楼层
        self.elevator_tasks[elevator_id].discard(floor_number)
        
        # 决定下一步行动
        if direction == 'idle':
            # 电梯已经空闲，检查是否有新任务
            self._assign_nearest_call_to_idle_elevator(elevator)
            return
        
        # LOOK算法核心逻辑：获取下一个目标楼层
        next_floor = self._get_next_floor_in_direction(elevator)
        
        if next_floor is not None:
            # 继续当前方向
            self.elevator_tasks[elevator_id].add(next_floor)
            success = elevator.go_to_floor(next_floor)
            if success:
                print(f"电梯{elevator_id}继续{direction}行，下一站：{next_floor}楼")
        else:
            # 当前方向没有更多请求，尝试反向
            original_direction = direction
            if direction == 'up':
                self.elevator_states[elevator_id]['direction'] = 'down'
            else:
                self.elevator_states[elevator_id]['direction'] = 'up'
            
            # 获取反方向的下一个楼层
            next_floor = self._get_next_floor_in_direction(elevator)
            
            if next_floor is not None:
                # 反向有任务
                self.elevator_tasks[elevator_id].add(next_floor)
                success = elevator.go_to_floor(next_floor)
                if success:
                    new_direction = self.elevator_states[elevator_id]['direction']
                    print(f"电梯{elevator_id}从{original_direction}转向{new_direction}，前往{next_floor}楼")
            else:
                # 两个方向都没有任务
                self.elevator_states[elevator_id]['direction'] = 'idle'
                print(f"电梯{elevator_id}完成所有任务，进入空闲状态")
                
                # 空闲后立即检查是否有新的呼叫
                self._assign_nearest_call_to_idle_elevator(elevator)

    def on_passenger_board(self, elevator: ProxyElevator, passenger: ProxyPassenger) -> None:
        """处理乘客上电梯事件"""
        elevator_id = elevator.id
        print(f"乘客{passenger.id}进入电梯{elevator_id}，目标楼层：{passenger.destination}")
        
        # 更新电梯状态中的乘客列表
        if passenger.id not in self.elevator_states[elevator_id]['passengers']:
            self.elevator_states[elevator_id]['passengers'].append(passenger.id)
        
        # 确保目标楼层在电梯任务中
        self.elevator_tasks[elevator_id].add(passenger.destination)
        
        # 如果电梯当前是空闲的，需要设置方向并前往目标楼层
        if self.elevator_states[elevator_id]['direction'] == 'idle':
            if passenger.destination > elevator.current_floor:
                self.elevator_states[elevator_id]['direction'] = 'up'
            elif passenger.destination < elevator.current_floor:
                self.elevator_states[elevator_id]['direction'] = 'down'
            
            # 发送电梯到目标楼层
            success = elevator.go_to_floor(passenger.destination)
            if success:
                print(f"电梯{elevator_id}开始移动到乘客目标楼层{passenger.destination}")

    def on_passenger_alight(self, elevator: ProxyElevator, passenger: ProxyPassenger, floor: ProxyFloor) -> None:
        """处理乘客下电梯事件"""
        elevator_id = elevator.id
        print(f"乘客{passenger.id}在{floor.floor}楼离开电梯{elevator_id}")
        
        # 从电梯状态中移除乘客
        if passenger.id in self.elevator_states[elevator_id]['passengers']:
            self.elevator_states[elevator_id]['passengers'].remove(passenger.id)
        
        # 更新统计信息（如果需要）
        print(f"乘客{passenger.id}完成行程：{passenger.origin}楼 -> {passenger.destination}楼")

    def on_elevator_passing_floor(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        """处理电梯经过楼层事件"""
        elevator_id = elevator.id
        floor_number = floor.floor
        
        # 更新电梯当前位置
        self.elevator_states[elevator_id]['current_floor'] = elevator.current_floor
        
        # 可以用于优化：检查是否有新的同方向请求可以顺便处理
        if not elevator.is_full and direction == self.elevator_states[elevator_id]['direction']:
            # 检查该楼层是否有同方向的等待乘客
            if (direction == 'up' and floor.up_queue) or (direction == 'down' and floor.down_queue):
                # 可以考虑动态添加停靠（但需要谨慎，避免频繁改变计划）
                print(f"电梯{elevator_id}经过{floor_number}楼，方向：{direction}")

    def on_elevator_approaching(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        """处理电梯接近楼层事件"""
        elevator_id = elevator.id
        floor_number = floor.floor
        
        # 检查是否应该在这层停靠
        should_stop = self._should_stop_at_floor(elevator, floor)
        
        if should_stop:
            print(f"电梯{elevator_id}即将到达{floor_number}楼，准备停靠")
            # 确保该楼层在任务列表中（以防万一）
            self.elevator_tasks[elevator_id].add(floor_number)
        else:
            # 如果不需要停靠，从任务列表中移除（如果存在）
            self.elevator_tasks[elevator_id].discard(floor_number)
            
        # 这个事件可以用于提前准备，比如通知等待的乘客准备上电梯

if __name__ == "__main__":
    print("="*60)
    print("电梯调度系统 - LOOK算法实现")
    print("="*60)
    print("配置文件: traffic.json")
    print("算法类型: LOOK (改进的SCAN算法)")
    print("特点: 电梯在一个方向上持续运行，到达最远请求后反向")
    print("="*60)
    
    algorithm = TestElevatorBusController()
    algorithm.start()
