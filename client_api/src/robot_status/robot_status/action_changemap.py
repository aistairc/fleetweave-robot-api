import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer
from rclpy.action import GoalResponse
from rclpy.logging import LoggingSeverity
from custom_msgs.action import ChangeMap


# ROS2 マップ変更アクションサーバー
class ActionChangeMap:
    def __init__(self, node: Node):
        self.node = node
        self.act_srv = ActionServer(
            node,
            ChangeMap,
            '/client_api/action/change_map',
            self._execute_callback,
            goal_callback=self._goal_callback,
        )


    def _goal_callback(self, goal_request):
        self.node.get_logger().info("[ActionChangeMap]Received change map goal request")
        self.map_int = goal_request.map_id
        return GoalResponse.ACCEPT

    async def _execute_callback(self, goal_handle):
        self.node.get_logger().info("[ActionChangeMap]Executing change map goal...")
        feedback = ChangeMap.Feedback()
        result = ChangeMap.Result()
        resp_int = 0  # 0:応答(使用しない)　1:成功　2:失敗
        rimit_cnt = 90

        try:
            while rclpy.ok():
                # loop内でマップIDを監視して同じマップIDになった場合成功、タイムリミットで失敗とする
                rclpy.spin_once(self.node, timeout_sec=0.5)
                map_id = self.map_string_to_int(self.node.map_name)
                if map_id == self.map_int:
                    goal_handle.succeed()
                    resp_int = 1
                    break
                else:
                    rimit_cnt -= 1
                    feedback.status = self.node.robot_status
                    goal_handle.publish_feedback(feedback)
                    if rimit_cnt <= 0:
                        goal_handle.abort()
                        resp_int = 2
                        break
                    pass

        except Exception as e:
            self.node.get_logger().error(f"[ActionChangeMap]Exception in execute callback: {e}")
            goal_handle.abort()
            resp_int = 2

        result.response_code = resp_int

        # 次の命令を受けられるように状態を解除
        try:
            self.node.use_order_type = None
        except Exception:
            pass

        self.node.get_logger().info(f"[ActionChangeMap]Change map action result: response_code={resp_int}")


        return result
    

    def map_string_to_int(self, map_name):
        map_dict = {
            "buildingA" : 0,
            "road"      : 1,
            "buildingB" : 2
        }
        # dictになければ-1を返す
        return map_dict.get(map_name, -1)