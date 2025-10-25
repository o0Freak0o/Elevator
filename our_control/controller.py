#!/usr/bin/env python3

import random
from typing import List
import sys
sys.path.append("D:/homework/soft_engineering/project/Elevator_shen")
from elevator_saga.client.base_controller import ElevatorController
from elevator_saga.client.proxy_models import ProxyElevator, ProxyFloor, ProxyPassenger
from elevator_saga.core.models import Direction, SimulationEvent


class NewElevatorController(ElevatorController):
    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:8000", False, "algorithm")  # debug=False, client_type="algorithm"
        self.max_level = 0
        self.user_data = {}  # 记录所有乘客信息
        self.elevator_goals = {}  # 手动维护：{elevator_id: {passenger_id: destination}}

    def on_init(self, elevators: List[ProxyElevator], floors: List[ProxyFloor]) -> None:
        self.max_level = floors[-1].floor

        
        n = len(floors)
        self.request_queue = [[False, False] for _ in range(n)]
        
        self.building_floors = floors
        self.elevator_fleet = elevators
        
        # 初始化每个电梯的goals字典
        for elevator in elevators:
            self.elevator_goals[elevator.id] = {}
        
        # 随机分散电梯
        for i, elevator in enumerate(elevators):
            target_floor = random.randint(0, len(floors) - 1)
            elevator.go_to_floor(target_floor, immediate=True)

    def on_event_execute_start(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        """每个tick开始时，随机派遣idle电梯"""
        # 找出所有request的楼层
        request_floors = []
        for f in range(len(self.request_queue)):
            if self.request_queue[f][0] or self.request_queue[f][1]:
                request_floors.append(f)
        
        if not request_floors:
            return
        
        # 获取所有非idle电梯的目标楼层
        target_floors = set(e.target_floor for e in elevators if not e.is_idle)
        
        # 找出没有电梯去的request楼层
        unserved_requests = [f for f in request_floors if f not in target_floors]
        
        idle_elevators = [e for e in elevators if e.is_idle]
        for elevator in idle_elevators:
            if unserved_requests:
                distances = [(abs(elevator.current_floor - floor), floor) for floor in unserved_requests]
                distances.sort()
                target_floor = distances[0][1]

                elevator.go_to_floor(target_floor)
                unserved_requests.remove(target_floor)

    def on_event_execute_end(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        pass

    def on_passenger_call(self, passenger: ProxyPassenger, floor: ProxyFloor, direction: str) -> None:
        """标记request_queue"""
        call_floor = floor.floor
        direction_idx = 0 if direction == "up" else 1
        self.request_queue[call_floor][direction_idx] = True
        
        # 记录乘客信息
        self.user_data[passenger.id] = {
            'origin': passenger.origin,
            'destination': passenger.destination,
            'arrive_tick': passenger.arrive_tick,
            'direction': direction
        }

    def on_elevator_idle(self, elevator: ProxyElevator) -> None:
        """智能派遣idle电梯"""
        current = elevator.current_floor
        
        # 如果当前楼层有request，优先处理
        if self.request_queue[current][0] and current < self.max_level:  # up
            elevator.go_to_floor(current + 1)
            return
        elif self.request_queue[current][1] and current > 0:  # down
            elevator.go_to_floor(current - 1)
            return
        
        # 寻找其他楼层的request
        waiting = []
        for f in range(len(self.request_queue)):
            if f != current and (self.request_queue[f][0] or self.request_queue[f][1]):
                waiting.append(f)
        
        if waiting:
            distances = [(abs(f - current), f) for f in waiting]
            distances.sort()
            target_floor = distances[0][1]

            elevator.go_to_floor(target_floor)

    def on_elevator_stopped(self, elevator: ProxyElevator, floor: ProxyFloor) -> None:
        """停靠后：更新request_queue，然后随机选择下一个目标"""
        current = elevator.current_floor
        direction = elevator.last_tick_direction
        
        # 更新request_queue：直接根据floor的队列状态设置
        self.request_queue[current][0] = len(floor.up_queue) > 0
        self.request_queue[current][1] = len(floor.down_queue) > 0
        
        if len(elevator.passengers) == 0:
            up_count = len(floor.up_queue) if current < self.max_level else 0
            down_count = len(floor.down_queue) if current > 0 else 0
            
            if direction == Direction.UP:
                if up_count > 0:
                    elevator.go_to_floor(current + 1)
                    return
                elif down_count > 0:
                    elevator.go_to_floor(current - 1)
                    return
            elif direction == Direction.DOWN:
                if down_count > 0:
                    elevator.go_to_floor(current - 1)
                    return
                elif up_count > 0:
                    elevator.go_to_floor(current + 1)
                    return
            
            if up_count > 0 or down_count > 0:
                if up_count > 0:
                    elevator.go_to_floor(current + 1)
                    return
                elif down_count > 0:
                    elevator.go_to_floor(current - 1)
                    return
            
            request_floors = [f for f in range(len(self.request_queue)) 
                             if f != current and (self.request_queue[f][0] or self.request_queue[f][1])]
            if request_floors:
                distances = [(abs(f - current), f) for f in request_floors]
                distances.sort()
                target = distances[0][1]
 
                elevator.go_to_floor(target)
                return
        
        # 获取候选楼层
        candidates = []
        
        # 1. 电梯内乘客目的地
        my_goals = self.elevator_goals.get(elevator.id, {})
        if my_goals:
            dests = [d for d in my_goals.values() if d != current]
            if direction == Direction.UP:
                dests = [d for d in dests if d > current]
                if dests:
                    candidates.append(min(dests))
            elif direction == Direction.DOWN:
                dests = [d for d in dests if d < current]
                if dests:
                    candidates.append(max(dests))
        
        # 2. 同方向request楼层
        request_floors = []
        for f in range(len(self.request_queue)):
            if self.request_queue[f][0] or self.request_queue[f][1]:
                request_floors.append(f)
        
        if direction == Direction.UP:
            above = [f for f in request_floors if f > current]
            if above:
                candidates.append(min(above))
        elif direction == Direction.DOWN:
            below = [f for f in request_floors if f < current]
            if below:
                candidates.append(max(below))
        
        if candidates:
            distances = [(abs(f - current), f) for f in candidates]
            distances.sort()
            target_floor = distances[0][1]

            elevator.go_to_floor(target_floor)

    def on_passenger_board(self, elevator: ProxyElevator, passenger: ProxyPassenger) -> None:
        # 记录乘客目的地
        self.elevator_goals[elevator.id][passenger.id] = passenger.destination

    def on_passenger_alight(self, elevator: ProxyElevator, passenger: ProxyPassenger, floor: ProxyFloor) -> None:
        # 标记乘客完成
        if passenger.id in self.user_data:
            self.user_data[passenger.id]['completed'] = True
        
        # 移除乘客目的地记录
        self.elevator_goals[elevator.id].pop(passenger.id, None)

    def on_elevator_passing_floor(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        pass

    def on_elevator_approaching(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        pass

    def on_elevator_move(
        self, elevator: ProxyElevator, from_position: float, to_position: float, direction: str, status: str
    ) -> None:
        pass


if __name__ == "__main__":
    
    controller = NewElevatorController()
    try:
        controller.start()
    except KeyboardInterrupt:
        print("\n[CTRL+C] Stopping gracefully...")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # 确保清理，无论正常退出、异常还是 Ctrl+C
        try:
            controller.on_stop()   # 或 controller.stop()
        except Exception:
            pass
