#!/usr/bin/env python3
from typing import Dict, List, Set, Tuple

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
        # 等待分配的呼叫请求 {(floor, direction): first_call_tick}
        self.pending_calls: Dict[Tuple[int, str], int] = {}
        
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
        self._assign_pending_calls(elevators, floors)

    def on_passenger_call(self, passenger: ProxyPassenger, floor: ProxyFloor, direction: str) -> None:
        """处理乘客呼叫"""
        print(f"Tick {self.current_tick}: 乘客{passenger.id}在{floor.floor}层呼叫电梯，方向: {direction}")
        
        # 将呼叫请求加入待处理队列
        call_key = (floor.floor, direction)
        if call_key not in self.pending_calls:
            self.pending_calls[call_key] = self.current_tick
        
        # 尝试立即分配给合适的电梯
        self._assign_call_to_elevator(floor.floor, direction)

    def on_elevator_idle(self, elevator: ProxyElevator) -> None:
        """电梯空闲时的处理"""
        print(f"Tick {self.current_tick}: 电梯{elevator.id}空闲")
        # 清除该电梯的方向和目标
        self.elevator_directions[elevator.id] = "stopped"
        self.elevator_targets[elevator.id].clear()
        # 尝试分配新任务
        self._assign_task_to_idle_elevator(elevator)

    def on_elevator_stopped(self, elevator: ProxyElevator, floor: ProxyFloor) -> None:
        """电梯停靠时的处理"""
        # 从目标集合中移除当前楼层
        if floor.floor in self.elevator_targets[elevator.id]:
            self.elevator_targets[elevator.id].discard(floor.floor)
        
        # 检查该楼层是否还有等待的乘客
        self._check_and_remove_pending_calls(floor)
        
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
        # 直接检查楼层的实际等待队列，而不是依赖pending_calls
        if not elevator.is_full:
            has_waiting = False
            if direction == "up" and len(floor.up_queue) > 0:
                has_waiting = True
            elif direction == "down" and len(floor.down_queue) > 0:
                has_waiting = True
            
            if has_waiting:
                self.elevator_targets[elevator.id].add(floor.floor)
                print(f"Tick {self.current_tick}: 电梯{elevator.id}顺路接客，增加目标楼层{floor.floor}")

    def on_elevator_approaching(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        """电梯即将到达楼层"""
        pass

    def _get_elevators_heading_to(self, floor: int, direction: str) -> List[ProxyElevator]:
        """获取正在前往指定楼层的电梯列表"""
        heading_elevators = []
        for elevator in self.elevators:
            # 检查目标中是否包含该楼层
            if floor not in self.elevator_targets[elevator.id]:
                continue
            
            elevator_dir = self.elevator_directions[elevator.id]
            current_floor = elevator.current_floor
            
            # 检查方向是否匹配
            if elevator_dir == direction:
                # 检查是否会经过该楼层
                if direction == "up" and current_floor <= floor:
                    heading_elevators.append(elevator)
                elif direction == "down" and current_floor >= floor:
                    heading_elevators.append(elevator)
            elif elevator_dir == "stopped" and floor in self.elevator_targets[elevator.id]:
                # 空闲但已分配该楼层
                heading_elevators.append(elevator)
        
        return heading_elevators

    def _assign_call_to_elevator(self, floor: int, direction: str) -> bool:
        """分配呼叫到最合适的电梯"""
        # 检查是否已经有足够的电梯在处理这个呼叫
        heading_elevators = self._get_elevators_heading_to(floor, direction)
        if heading_elevators:
            # 获取实际等待的乘客数量
            floor_obj = next((f for f in self.floors if f.floor == floor), None)
            if floor_obj:
                waiting_count = len(floor_obj.up_queue) if direction == "up" else len(floor_obj.down_queue)
                # 计算总可用容量
                total_capacity = sum(e.max_capacity - len(e.passengers) for e in heading_elevators)
                # 如果已有电梯且容量足够接走所有等待的乘客，就不再分配新电梯
                if total_capacity >= waiting_count:
                    return True
        
        best_elevator = None
        best_score = float('inf')
        
        for elevator in self.elevators:
            # 跳过满载的电梯
            if elevator.is_full:
                continue
            
            # 跳过已经在处理该呼叫的电梯
            if elevator in heading_elevators:
                continue
            
            current_floor = elevator.current_floor
            current_direction = self.elevator_directions[elevator.id]
            distance = abs(current_floor - floor)
            
            # 计算分配分数
            score = distance
            
            if current_direction == direction:
                if direction == "up" and current_floor <= floor:
                    score = distance  # 最优先
                elif direction == "down" and current_floor >= floor:
                    score = distance  # 最优先
                else:
                    score = distance + 20  # 需要掉头
            elif current_direction == "stopped":
                score = distance + 2  # 空闲电梯
            else:
                score = distance + 30  # 反方向
            
            if score < best_score:
                best_score = score
                best_elevator = elevator
        
        if best_elevator:
            self.elevator_targets[best_elevator.id].add(floor)
            if self.elevator_directions[best_elevator.id] == "stopped":
                self.elevator_directions[best_elevator.id] = direction
                self._set_next_target(best_elevator)
            return True
        
        return False

    def _assign_task_to_idle_elevator(self, elevator: ProxyElevator) -> None:
        """为空闲电梯分配任务"""
        # 直接检查所有楼层的等待队列
        min_score = float('inf')
        target_floor = None
        target_direction = None
        
        for floor in self.floors:
            # 检查上行队列
            if len(floor.up_queue) > 0:
                # 检查是否已有其他电梯在处理
                heading_elevators = self._get_elevators_heading_to(floor.floor, "up")
                if not heading_elevators:
                    distance = abs(elevator.current_floor - floor.floor)
                    # 考虑等待的乘客数量
                    score = distance - len(floor.up_queue) * 2
                    if score < min_score:
                        min_score = score
                        target_floor = floor.floor
                        target_direction = "up"
            
            # 检查下行队列
            if len(floor.down_queue) > 0:
                # 检查是否已有其他电梯在处理
                heading_elevators = self._get_elevators_heading_to(floor.floor, "down")
                if not heading_elevators:
                    distance = abs(elevator.current_floor - floor.floor)
                    # 考虑等待的乘客数量
                    score = distance - len(floor.down_queue) * 2
                    if score < min_score:
                        min_score = score
                        target_floor = floor.floor
                        target_direction = "down"
        
        if target_floor is not None and target_direction is not None:
            self.elevator_targets[elevator.id].add(target_floor)
            self.elevator_directions[elevator.id] = target_direction
            self._set_next_target(elevator)
            print(f"Tick {self.current_tick}: 为空闲电梯{elevator.id}分配任务: 前往{target_floor}层({target_direction})")

    def _set_next_target(self, elevator: ProxyElevator) -> None:
        """根据LOOK算法设置电梯的下一个目标"""
        targets = self.elevator_targets[elevator.id]
        
        if not targets:
            # 没有目标时，让电梯停在当前位置并触发IDLE
            self.elevator_directions[elevator.id] = "stopped"
            # 重要：发送go_to_floor到当前楼层，让模拟器知道电梯应该停止
            # 这样target_floor = current_floor，target_floor_direction = STOPPED
            # 从而触发IDLE事件
            if elevator.current_floor is not None:
                elevator.go_to_floor(elevator.current_floor)
            return
        
        current_floor = elevator.current_floor
        current_direction = self.elevator_directions[elevator.id]
        next_floor = current_floor
        
        # 根据当前方向选择下一个目标
        if current_direction == "up":
            up_targets = [f for f in targets if f > current_floor]
            if up_targets:
                next_floor = min(up_targets)
            else:
                # 没有上行目标，反向
                self.elevator_directions[elevator.id] = "down"
                down_targets = [f for f in targets if f <= current_floor]
                if down_targets:
                    next_floor = max(down_targets)
                else:
                    self.elevator_directions[elevator.id] = "stopped"
                    elevator.go_to_floor(current_floor)
                    return
        
        elif current_direction == "down":
            down_targets = [f for f in targets if f < current_floor]
            if down_targets:
                next_floor = max(down_targets)
            else:
                # 没有下行目标，反向
                self.elevator_directions[elevator.id] = "up"
                up_targets = [f for f in targets if f >= current_floor]
                if up_targets:
                    next_floor = min(up_targets)
                else:
                    self.elevator_directions[elevator.id] = "stopped"
                    elevator.go_to_floor(current_floor)
                    return
        
        else:  # stopped
            next_floor = min(targets, key=lambda f: abs(f - current_floor))
            if next_floor > current_floor:
                self.elevator_directions[elevator.id] = "up"
            elif next_floor < current_floor:
                self.elevator_directions[elevator.id] = "down"
            else:
                # 当前楼层就是目标
                return
        
        # 发送电梯移动指令
        if next_floor != current_floor:
            elevator.go_to_floor(next_floor)

    def _check_and_remove_pending_calls(self, floor: ProxyFloor) -> None:
        """检查并移除已完成的呼叫请求"""
        # 只有当队列为空时才删除pending_calls
        if len(floor.up_queue) == 0:
            call_key = (floor.floor, "up")
            if call_key in self.pending_calls:
                del self.pending_calls[call_key]
        
        if len(floor.down_queue) == 0:
            call_key = (floor.floor, "down")
            if call_key in self.pending_calls:
                del self.pending_calls[call_key]

    def _assign_pending_calls(self, elevators: List[ProxyElevator], floors: List[ProxyFloor]) -> None:
        """为所有待处理的呼叫分配电梯"""
        # 清理已经没有等待乘客的pending_calls
        for floor in floors:
            self._check_and_remove_pending_calls(floor)
        
        # 直接检查每个楼层的等待队列
        for floor in floors:
            # 检查上行队列
            if len(floor.up_queue) > 0:
                heading_elevators = self._get_elevators_heading_to(floor.floor, "up")
                if not heading_elevators:
                    self._assign_call_to_elevator(floor.floor, "up")
            
            # 检查下行队列
            if len(floor.down_queue) > 0:
                heading_elevators = self._get_elevators_heading_to(floor.floor, "down")
                if not heading_elevators:
                    self._assign_call_to_elevator(floor.floor, "down")


if __name__ == "__main__":
    algorithm = LOOKElevatorController()
    algorithm.start()
