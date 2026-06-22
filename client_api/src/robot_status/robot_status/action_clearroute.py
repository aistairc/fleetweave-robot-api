import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, GoalResponse
from rclpy.logging import LoggingSeverity
from custom_msgs.action import CancelRoute

# ROS2 クリアルートアクションサーバー

class ActionClearRoute:
    def __init__(self, node: Node):
        self.node = node
        self.act_srv = ActionServer(
            node,
            CancelRoute,
            '/client_api/action/clear_route',
            self._execute_callback,
            goal_callback=self._goal_callback,
        )


    def _goal_callback(self, goal_request):
        self.node.get_logger().info("[ActionClearRoute]Received clear route goal request")
        self.nowid = goal_request.id
        self.unSkip = goal_request.un_skip
        return GoalResponse.ACCEPT

    async def _execute_callback(self, goal_handle):
        self.node.get_logger().info("[ActionClearRoute]Executing clear route goal...")
        feedback = CancelRoute.Feedback()
        result = CancelRoute.Result()
        resp_int = 0  # 0:応答(使用しない)　1:成功　2:失敗  7:未走行

        try:
            #Skipしない


            if self.unSkip == True:
                # 移動に関する命令をクリア
                self.node.cancel_flag = True
                self.node.get_logger().info("[ActionClearRoute]unSkip is True: will treat waiting as completion.")
                while rclpy.ok():
                    # ステータスをチェックして移動中から待機になること確認するロジックをここに追加
                    rclpy.spin_once(self.node, timeout_sec=0.5)
                    robot_status = self.node.robot_status
                    if robot_status == 3 or self.node.plan_2d_status == 3: #待機中
                        goal_handle.succeed()
                        resp_int = 1
                        break
                    elif robot_status == 1: #移動中
                        feedback.status = 1
                        goal_handle.publish_feedback(feedback)
                        pass
                    elif robot_status == 0: #移動完了
                        feedback.status = 0
                        goal_handle.publish_feedback(feedback)
                        pass
                    else:
                        # 以上な状態の場合の処理
                        goal_handle.abort()
                        resp_int = 2
                        break
            #Skipする
            else:
                self.node.get_logger().info("[ActionClearRoute]unSkip is False: will treat any non-moving status as completion.")
                goal_handle.succeed()
                resp_int = 7 #未走行

                pass

        except Exception as e:
            self.node.get_logger().error(f"[ActionClearRoute]Exception in execute loop: {e}")
            try:
                goal_handle.abort()
            except Exception:
                pass
            resp_int = 2 #失敗

        # 実行結果の設定
        result.id = self.nowid
        result.response_code = resp_int

        # 次の命令を受け付けられるよう状態を解除
        try:
            self.node.get_logger().info("[ActionClearRoute]Clearing use_order_type. : %s > None" % str(self.node.use_order_type))
            self.node.use_order_type = None
        except Exception:
            pass

        self.node.get_logger().info("[ActionClearRoute]Clear route goal completed with response_code=%d" % resp_int)
        return result