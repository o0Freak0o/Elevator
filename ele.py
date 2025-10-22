#!/usr/bin/env python3
"""
最终响应式控制器
完全复制bus_example的结构，只改进on_elevator_stopped的派遣逻辑
"""
from typing import List
from elevator_saga.client.base_controller import ElevatorController
from elevator_saga.client.proxy_models import ProxyElevator, ProxyFloor, ProxyPassenger
from elevator_saga.core.models import Direction, SimulationEvent


class FinalResponsiveController(ElevatorController):
    def __init__(self) -> None:
        super().__init__("http://127.0.0.1:8000", False)  # debug=False
        self.max_floor = 0
        self.all_passengers = {}  # 记录所有乘客信息
        self.elevator_destinations = {}  # 手动维护：{elevator_id: {passenger_id: destination}}

    def on_init(self, elevators: List[ProxyElevator], floors: List[ProxyFloor]) -> None:
        self.max_floor = floors[-1].floor
        
        # pending_list: (n, 2) shape，[floor][0]=up, [floor][1]=down
        n = len(floors)
        self.pending_list = [[False, False] for _ in range(n)]
        
        self.floors = floors
        self.elevators = elevators
        
        # 初始化每个电梯的destinations字典
        for elevator in elevators:
            self.elevator_destinations[elevator.id] = {}
        
        # 分散电梯
        for i, elevator in enumerate(elevators):
            target_floor = (i * (len(floors) - 1)) // len(elevators)
            elevator.go_to_floor(target_floor, immediate=True)

    def on_event_execute_start(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        """每个tick开始时，派遣idle电梯去pending楼层"""
        # 找出所有pending的楼层
        pending_floors = []
        for f in range(len(self.pending_list)):
            if self.pending_list[f][0] or self.pending_list[f][1]:
                pending_floors.append(f)
        
        if not pending_floors:
            return
        
        # 获取所有非idle电梯的目标楼层（这些楼层已经有电梯在去了）
        target_floors = set(e.target_floor for e in elevators if not e.is_idle)
        
        # 找出没有电梯去的pending楼层
        unserved_pending = [f for f in pending_floors if f not in target_floors]
        
        # 派遣idle电梯到无人服务的pending楼层
        for elevator in elevators:
            if elevator.is_idle and unserved_pending:
                current = elevator.current_floor
                # 找最近的无人服务pending楼层
                nearest = min(unserved_pending, key=lambda f: abs(f - current))
                elevator.go_to_floor(nearest)
                unserved_pending.remove(nearest)  # 避免本次循环重复派遣

    def on_event_execute_end(
        self, tick: int, events: List[SimulationEvent], elevators: List[ProxyElevator], floors: List[ProxyFloor]
    ) -> None:
        pass

    def on_passenger_call(self, passenger: ProxyPassenger, floor: ProxyFloor, direction: str) -> None:
        """标记pending_list"""
        call_floor = floor.floor
        direction_idx = 0 if direction == "up" else 1
        self.pending_list[call_floor][direction_idx] = True
        
        # 记录乘客信息
        self.all_passengers[passenger.id] = {
            'origin': passenger.origin,
            'destination': passenger.destination,
            'arrive_tick': passenger.arrive_tick,
            'direction': direction
        }

    def on_elevator_idle(self, elevator: ProxyElevator) -> None:
        """使用pending_list派遣idle电梯"""
        current = elevator.current_floor
        
        # 如果当前楼层有pending，设置方向
        if self.pending_list[current][0] and current < self.max_floor:  # up
            elevator.go_to_floor(current + 1)
            return
        elif self.pending_list[current][1] and current > 0:  # down
            elevator.go_to_floor(current - 1)
            return
        
        # 去最近的pending楼层
        waiting = []
        for f in range(len(self.pending_list)):
            if f != current and (self.pending_list[f][0] or self.pending_list[f][1]):
                waiting.append(f)
        
        if waiting:
            nearest = min(waiting, key=lambda f: abs(f - current))
            elevator.go_to_floor(nearest)

    def on_elevator_stopped(self, elevator: ProxyElevator, floor: ProxyFloor) -> None:
        """停靠后：更新pending_list，然后找同方向最近的目的地和有客楼层"""
        current = elevator.current_floor
        direction = elevator.last_tick_direction
        
        # 更新pending_list：直接根据floor的队列状态设置
        self.pending_list[current][0] = len(floor.up_queue) > 0
        self.pending_list[current][1] = len(floor.down_queue) > 0
        
        # 空载电梯逻辑：保持方向惯性
        if len(elevator.passengers) == 0:
            up_count = len(floor.up_queue) if current < self.max_floor else 0
            down_count = len(floor.down_queue) if current > 0 else 0
            
            if direction == Direction.UP:
                # 1. 当前楼层有上行的，继续上
                if up_count > 0:
                    elevator.go_to_floor(current + 1)
                    return
                
                # 2. 上面有同方向（上行）的pending，去最近的
                above_up = [f for f in range(current + 1, len(self.pending_list)) 
                           if self.pending_list[f][0]]  # 上行
                if above_up:
                    elevator.go_to_floor(min(above_up))  # 最近的同方向
                    return
                
                # 3. 上面有反方向（下行）的pending，去最远的
                above_down = [f for f in range(current + 1, len(self.pending_list)) 
                             if self.pending_list[f][1]]  # 下行
                if above_down:
                    elevator.go_to_floor(max(above_down))  # 最远的反方向
                    return
                
                # 4. 上面没人，当前也没上行的，换向下
                if down_count > 0:
                    elevator.go_to_floor(current - 1)
                    return
                
                # 5. 当前没人，去下面最近的pending
                below_pending = [f for f in range(current) 
                                if self.pending_list[f][0] or self.pending_list[f][1]]
                if below_pending:
                    elevator.go_to_floor(max(below_pending))
                    return
            
            elif direction == Direction.DOWN:
                # 1. 当前楼层有下行的，继续下
                if down_count > 0:
                    elevator.go_to_floor(current - 1)
                    return
                
                # 2. 下面有同方向（下行）的pending，去最近的
                below_down = [f for f in range(0, current) 
                             if self.pending_list[f][1]]  # 下行
                if below_down:
                    elevator.go_to_floor(max(below_down))  # 最近的同方向
                    return
                
                # 3. 下面有反方向（上行）的pending，去最远的
                below_up = [f for f in range(0, current) 
                           if self.pending_list[f][0]]  # 上行
                if below_up:
                    elevator.go_to_floor(min(below_up))  # 最远的反方向
                    return
                
                # 4. 下面没人，当前也没下行的，换向上
                if up_count > 0:
                    elevator.go_to_floor(current + 1)
                    return
                
                # 5. 当前没人，去上面最近的pending
                above_pending = [f for f in range(current + 1, len(self.pending_list)) 
                                if self.pending_list[f][0] or self.pending_list[f][1]]
                if above_pending:
                    elevator.go_to_floor(min(above_pending))
                    return
            
            else:  # STOPPED 或初始状态
                # 比较上下人数
                if up_count > 0 or down_count > 0:
                    if up_count >= down_count and up_count > 0:
                        elevator.go_to_floor(current + 1)
                        return
                    elif down_count > 0:
                        elevator.go_to_floor(current - 1)
                        return
                
                # 没人等，去最近的pending
                pending_floors = [f for f in range(len(self.pending_list)) 
                                 if f != current and (self.pending_list[f][0] or self.pending_list[f][1])]
                if pending_floors:
                    target = min(pending_floors, key=lambda f: abs(f - current))
                    elevator.go_to_floor(target)
                    return
        
        # 获取同方向的候选楼层
        candidates = []
        
        # 1. 电梯内乘客目的地（使用我们自己维护的destinations）
        my_destinations = self.elevator_destinations.get(elevator.id, {})
        if my_destinations:
            dests = [d for d in my_destinations.values() if d != current]
            if direction == Direction.UP:
                dests = [d for d in dests if d > current]
                if dests:
                    candidates.append(min(dests))
            elif direction == Direction.DOWN:
                dests = [d for d in dests if d < current]
                if dests:
                    candidates.append(max(dests))
        
        # 2. 同方向最近pending楼层
        pending_floors = []
        for f in range(len(self.pending_list)):
            if self.pending_list[f][0] or self.pending_list[f][1]:
                pending_floors.append(f)
        
        if direction == Direction.UP:
            above = [f for f in pending_floors if f > current]
            if above:
                candidates.append(min(above))
        elif direction == Direction.DOWN:
            below = [f for f in pending_floors if f < current]
            if below:
                candidates.append(max(below))
        
        # 选择最近的候选楼层
        if candidates:
            nearest = min(candidates, key=lambda f: abs(f - current))
            elevator.go_to_floor(nearest)

    def on_passenger_board(self, elevator: ProxyElevator, passenger: ProxyPassenger) -> None:
        # 记录乘客目的地
        self.elevator_destinations[elevator.id][passenger.id] = passenger.destination

    def on_passenger_alight(self, elevator: ProxyElevator, passenger: ProxyPassenger, floor: ProxyFloor) -> None:
        # 标记乘客完成
        if passenger.id in self.all_passengers:
            self.all_passengers[passenger.id]['completed'] = True
        
        # 移除乘客目的地记录
        self.elevator_destinations[elevator.id].pop(passenger.id, None)

    def on_elevator_passing_floor(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        pass

    def on_elevator_approaching(self, elevator: ProxyElevator, floor: ProxyFloor, direction: str) -> None:
        pass

    def on_elevator_move(
        self, elevator: ProxyElevator, from_position: float, to_position: float, direction: str, status: str
    ) -> None:
        pass


if __name__ == "__main__":
    controller = FinalResponsiveController()
    controller.start()
    
    # 打印最终floors状态
    print("\n🏢 最终floors实际状态:")
    for floor in controller.floors:
        if floor.up_queue or floor.down_queue:
            print(f"  F{floor.floor}: ↑{len(floor.up_queue)}人 ↓{len(floor.down_queue)}人")
    
    # 打印最终elevators状态
    print("\n🚇 最终elevators状态:")
    total_in_elevators = 0
    for elevator in controller.elevators:
        if elevator.passengers:
            total_in_elevators += len(elevator.passengers)
            print(f"  E{elevator.id} @ F{elevator.current_floor}: "
                  f"{len(elevator.passengers)}人(ID:{elevator.passengers}) "
                  f"→ destinations={elevator.passenger_destinations}")
    
    print(f"\n⚠️ 电梯里总共{total_in_elevators}人，但destinations为空！这是bug！")

