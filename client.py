#!/usr/bin/env python3
from typing import Dict, List, Set

from elevator_saga.client.base_controller import ElevatorController
from elevator_saga.client.proxy_models import ProxyElevator, ProxyFloor, ProxyPassenger
from elevator_saga.core.models import SimulationEvent


class LOOKElevatorController(ElevatorController):
    """基于LOOK算法的电梯调度控制器"""
    
    def __init__(self):
        super().__init__("http://127.0.0.1:8000", True)
        # 每个电梯的目标楼层集合
        self.elevator_targets: Dict[int, Set[int]] = {}
        # 每个电梯的当前方向（"up", "down", "stopped"）
        self.elevator_directions: Dict[int, str] = {}
        # 等待分配的呼叫请求 {floor: direction}
        self.pending_calls: Dict[int, str] = {}
        
    def on_init(self, elevators: List[ProxyElevator], floors: List[ProxyFloor]) -> None:
        """初始化电梯状态"""
        print(f"初始化: {len(elevators)}个电梯, {len(floors)}层楼")
        for elevator in elevators:
            self.elevator_targets[elevator.id] = set()
            self.elevator_directions[elevator.id] = "stopped"

    def on_event_execute_start(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        """事件执行前的处理"""
        pass

    def on_event_execute_end(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        """事件执行后的处理 - 为空闲电梯分配任务"""
        self._assign_pending_calls(elevators)

    def on_passenger_call(self, passenger: ProxyPassenger, floor: ProxyFloor, direction: str) -> None:
        """处理乘客呼叫"""
        print(f"Tick {self.current_tick}: 乘客{passenger.id}在{floor.floor}层呼叫电梯，方向: {direction}")
        # 将呼叫请求加入待处理队列
        self.pending_calls[floor.floor] = direction
        
        # 尝试立即分配给合适的电梯
        self._assign_call_to_elevator(floor.floor, direction)

    def on_elevator_idle(self, elevator: ProxyElevator) -> None:
        """电梯空闲时的处理"""
        # 清除该电梯的方向
        self.elevator_directions[elevator.id] = "stopped"
        # 尝试分配新任务
        self._assign_task_to_idle_elevator(elevator)

    def on_elevator_stopped(self, elevator: ProxyElevator, floor: ProxyFloor) -> None:
        """电梯停靠时的处理"""
        # 从目标集合中移除当前楼层
        if floor.floor in self.elevator_targets[elevator.id]:
            self.elevator_targets[elevator.id].discard(floor.floor)
        
        # 如果这是一个待处理的呼叫楼层，移除它
        if floor.floor in self.pending_calls:
            del self.pending_calls[floor.floor]
        
        # 为电梯设置下一个目标
        self._set_next_target(elevator)

    def on_passenger_board(self, elevator: ProxyElevator, passenger: ProxyPassenger) -> None:
        """乘客上梯时添加目的楼层"""
        dest = passenger.destination
        self.elevator_targets[elevator.id].add(dest)
        print(f"Tick {self.current_tick}: 乘客{passenger.id}上电梯{elevator.id}，目的地{dest}层")

    def on_passenger_alight(self, elevator: ProxyElevator, passenger: ProxyPassenger, floor: ProxyFloor) -> None:
        """乘客下梯"""
        print(f"Tick {self.current_tick}: 乘客{passenger.id}在{floor.floor}层下电梯{elevator.id}")

    def on_elevator_passing_floor(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        """电梯经过楼层 - LOOK算法核心：顺路接客"""
        # 检查该楼层是否有同方向的呼叫
        if floor.floor in self.pending_calls and self.pending_calls[floor.floor] == direction:
            # 如果电梯未满，添加该楼层为目标
            if not elevator.is_full:
                self.elevator_targets[elevator.id].add(floor.floor)

    def on_elevator_approaching(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        """电梯即将到达楼层"""
        pass

    def _assign_call_to_elevator(self, floor: int, direction: str) -> bool:
        """分配呼叫到最合适的电梯"""
        best_elevator = None
        best_score = float('inf')
        
        for elevator in self.elevators:
            # 跳过满载的电梯
            if elevator.is_full:
                continue
                
            # 计算分配分数（距离 + 方向匹配度）
            distance = abs(elevator.current_floor - floor)
            
            # 如果电梯正在朝该方向移动且会经过该楼层
            if self.elevator_directions[elevator.id] == direction:
                if direction == "up" and elevator.current_floor <= floor:
                    score = distance
                elif direction == "down" and elevator.current_floor >= floor:
                    score = distance
                else:
                    score = distance + 10  # 方向不匹配，增加惩罚
            elif self.elevator_directions[elevator.id] == "stopped":
                score = distance + 5  # 空闲电梯，中等优先级
            else:
                score = distance + 20  # 反方向，最低优先级
            
            if score < best_score:
                best_score = score
                best_elevator = elevator
        
        if best_elevator:
            self.elevator_targets[best_elevator.id].add(floor)
            # 如果电梯是空闲的，设置方向并立即分配任务
            if self.elevator_directions[best_elevator.id] == "stopped":
                self.elevator_directions[best_elevator.id] = direction
                self._set_next_target(best_elevator)
            return True
        
        return False

    def _assign_task_to_idle_elevator(self, elevator: ProxyElevator) -> None:
        """为空闲电梯分配任务"""
        if not self.pending_calls:
            return
        
        # 找到最近的待处理呼叫
        min_distance = float('inf')
        target_floor = None
        target_direction = None
        
        for floor, direction in self.pending_calls.items():
            distance = abs(elevator.current_floor - floor)
            if distance < min_distance:
                min_distance = distance
                target_floor = floor
                target_direction = direction
        
        if target_floor is not None and target_direction is not None:
            self.elevator_targets[elevator.id].add(target_floor)
            self.elevator_directions[elevator.id] = target_direction
            self._set_next_target(elevator)

    def _set_next_target(self, elevator: ProxyElevator) -> None:
        """根据LOOK算法设置电梯的下一个目标"""
        targets = self.elevator_targets[elevator.id]
        
        if not targets:
            self.elevator_directions[elevator.id] = "stopped"
            return
        
        current_floor = elevator.current_floor
        current_direction = self.elevator_directions[elevator.id]
        
        # 根据当前方向选择下一个目标
        if current_direction == "up":
            # 选择当前楼层以上的最近目标
            up_targets = [f for f in targets if f > current_floor]
            if up_targets:
                next_floor = min(up_targets)
            else:
                # 没有上行目标，反向
                self.elevator_directions[elevator.id] = "down"
                down_targets = [f for f in targets if f < current_floor]
                if down_targets:
                    next_floor = max(down_targets)
                else:
                    next_floor = min(targets) if targets else current_floor
        
        elif current_direction == "down":
            # 选择当前楼层以下的最近目标
            down_targets = [f for f in targets if f < current_floor]
            if down_targets:
                next_floor = max(down_targets)
            else:
                # 没有下行目标，反向
                self.elevator_directions[elevator.id] = "up"
                up_targets = [f for f in targets if f > current_floor]
                if up_targets:
                    next_floor = min(up_targets)
                else:
                    next_floor = max(targets) if targets else current_floor
        
        else:  # stopped
            # 选择最近的目标并设置方向
            next_floor = min(targets, key=lambda f: abs(f - current_floor))
            if next_floor > current_floor:
                self.elevator_directions[elevator.id] = "up"
            elif next_floor < current_floor:
                self.elevator_directions[elevator.id] = "down"
        
        # 发送电梯移动指令
        if next_floor != current_floor:
            elevator.go_to_floor(next_floor)

    def _assign_pending_calls(self, elevators: List[ProxyElevator]) -> None:
        """为所有待处理的呼叫分配电梯"""
        calls_to_remove = []
        for floor, direction in list(self.pending_calls.items()):
            # 检查是否有电梯正在前往该楼层
            assigned = False
            for elevator in elevators:
                if floor in self.elevator_targets[elevator.id]:
                    assigned = True
                    break
            
            if not assigned:
                # 尝试重新分配
                if self._assign_call_to_elevator(floor, direction):
                    calls_to_remove.append(floor)
        
        # 清理已分配的呼叫（保留在pending中直到电梯真正到达）
        # for floor in calls_to_remove:
        #     del self.pending_calls[floor]


if __name__ == "__main__":
    algorithm = LOOKElevatorController()
    algorithm.start()
