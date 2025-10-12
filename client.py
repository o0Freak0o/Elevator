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
        
        # 保存电梯和楼层对象引用
        self.elevators = elevators
        self.floors = floors
        
        # 初始化每个电梯的状态
        for elevator in elevators:
            elevator_id = elevator.id
            
            # 初始化电梯任务队列（使用set存储目标楼层，避免重复）
            self.elevator_tasks[elevator_id] = set()
            
            # 初始化电梯状态
            self.elevator_states[elevator_id] = {
                'direction': 'idle',  # 初始为空闲状态
                'current_floor': elevator.current_floor,  # 假设电梯有current_floor属性
                'passengers': []  # 电梯内的乘客列表
            }
            
            # 初始化电梯内乘客目标楼层映射
            self.elevator_destinations[elevator_id] = defaultdict(list)
            
            # 可以考虑将电梯分布在不同楼层待命
            # 例如：第一台电梯在1楼，第二台在中间楼层等
            if self.num_elevators > 1:
                # 将电梯均匀分布在各楼层
                initial_floor = 1 + (elevator_id * (self.num_floors - 1)) // (self.num_elevators - 1)
                # 发送电梯到初始楼层的命令（如果有相应的API）
                # elevator.goto_floor(initial_floor)
                
        print(f"电梯系统初始化完成。共有{len(elevators)}台电梯，{len(floors)}个楼层。")

    def on_event_execute_start(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        """每个tick开始时的事件处理"""
        self.current_tick = tick
        
        # 检查是否有新乘客在这个tick到达
        if tick in self.passenger_schedule:
            passengers_arriving = self.passenger_schedule[tick]
            for passenger_data in passengers_arriving:
                origin = passenger_data['origin']
                destination = passenger_data['destination']
                passenger_id = passenger_data['id']
                
                # 确定呼叫方向
                direction = 'up' if destination > origin else 'down'
                
                # 记录呼叫请求到hall_calls
                self.hall_calls[origin][direction].append(passenger_id)
                
                print(f"Tick {tick}: 乘客{passenger_id}在{origin}楼呼叫电梯，目标{destination}楼，方向{direction}")
        
        # 更新所有电梯的当前状态
        for elevator in elevators:
            elevator_id = elevator.id
            # 更新电梯当前楼层（假设电梯对象有current_floor属性）
            if hasattr(elevator, 'current_floor'):
                self.elevator_states[elevator_id]['current_floor'] = elevator.current_floor
            
            # 如果电梯为空且没有任务，设置为idle状态
            if (not self.elevator_states[elevator_id]['passengers'] and 
                not self.elevator_tasks[elevator_id]):
                self.elevator_states[elevator_id]['direction'] = 'idle'

    def on_event_execute_end(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        """每个tick结束时的事件处理"""
        # 处理LOOK算法的调度逻辑
        for elevator in elevators:
            elevator_id = elevator.id
            state = self.elevator_states[elevator_id]
            
            # 如果电梯处于idle状态，检查是否有呼叫需要响应
            if state['direction'] == 'idle':
                # 查找最近的呼叫请求
                self._assign_nearest_call_to_idle_elevator(elevator)
            
            # 清理已经完成的任务
            current_floor = state['current_floor']
            if current_floor in self.elevator_tasks[elevator_id]:
                # 检查该楼层是否还有乘客需要下电梯或上电梯
                if not self._has_passengers_for_floor(elevator_id, current_floor):
                    self.elevator_tasks[elevator_id].discard(current_floor)
        
        # 打印当前系统状态（用于调试）
        if tick % 10 == 0:  # 每10个tick打印一次
            self._print_system_status(tick)
    
    def _assign_nearest_call_to_idle_elevator(self, elevator: ProxyElevator):
        """为空闲电梯分配最近的呼叫请求"""
        elevator_id = elevator.id
        current_floor = self.elevator_states[elevator_id]['current_floor']
        
        nearest_floor = None
        min_distance = float('inf')
        
        # 遍历所有楼层的呼叫请求
        for floor_id, calls in self.hall_calls.items():
            if calls['up'] or calls['down']:
                distance = abs(floor_id - current_floor)
                if distance < min_distance:
                    min_distance = distance
                    nearest_floor = floor_id
        
        # 如果找到呼叫请求，分配给电梯
        if nearest_floor is not None:
            self.elevator_tasks[elevator_id].add(nearest_floor)
            # 设置电梯方向
            if nearest_floor > current_floor:
                self.elevator_states[elevator_id]['direction'] = 'up'
            elif nearest_floor < current_floor:
                self.elevator_states[elevator_id]['direction'] = 'down'
            else:
                # 已经在目标楼层
                self.elevator_states[elevator_id]['direction'] = 'idle'
            
            print(f"分配电梯{elevator_id}响应{nearest_floor}楼的呼叫")
    
    def _has_passengers_for_floor(self, elevator_id: int, floor: int) -> bool:
        """检查电梯在指定楼层是否有乘客需要上下"""
        # 检查是否有乘客要在这层下电梯
        if floor in self.elevator_destinations[elevator_id]:
            if self.elevator_destinations[elevator_id][floor]:
                return True
        
        # 检查是否有乘客在这层等待上电梯
        direction = self.elevator_states[elevator_id]['direction']
        if direction in ['up', 'down']:
            if self.hall_calls[floor][direction]:
                return True
        
        return False
    
    def _print_system_status(self, tick: int):
        """打印系统状态用于调试"""
        print(f"\n=== Tick {tick} 系统状态 ===")
        for elevator_id, state in self.elevator_states.items():
            tasks = list(self.elevator_tasks[elevator_id])
            print(f"电梯{elevator_id}: 楼层{state['current_floor']}, 方向{state['direction']}, "
                  f"任务{tasks}, 乘客数{len(state['passengers'])}")
        
        # 打印有呼叫请求的楼层
        for floor_id, calls in self.hall_calls.items():
            if calls['up'] or calls['down']:
                print(f"楼层{floor_id}: 上行呼叫{len(calls['up'])}个, 下行呼叫{len(calls['down'])}个")

    def on_passenger_call(self, passenger:ProxyPassenger, floor: ProxyFloor, direction: str) -> None:
        pass

    def on_elevator_idle(self, elevator: ProxyElevator) -> None:
        pass

    def on_elevator_stopped(self, elevator: ProxyElevator, floor: ProxyFloor) -> None:
        pass

    def on_passenger_board(self, elevator: ProxyElevator, passenger: ProxyPassenger) -> None:
        pass

    def on_passenger_alight(self, elevator: ProxyElevator, passenger: ProxyPassenger, floor: ProxyFloor) -> None:
        pass

    def on_elevator_passing_floor(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        pass

    def on_elevator_approaching(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        pass

if __name__ == "__main__":
    algorithm = TestElevatorBusController()
    algorithm.start()
